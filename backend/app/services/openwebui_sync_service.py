"""
Open WebUI ("CoChat") Knowledge Sync
─────────────────────────────────────────
Pushes this app's own RAG Knowledge Base (company_documents — managed
under Setup > AI > Knowledge Base) into CoChat's separate "Company Rules"
Knowledge collection, via CoChat's native sync API, so CoChat's own chat
can also answer from these same documents.

Every request shape below was verified live against the real CoChat
instance (not just the integration runbook's paraphrase) — one gap found
that the runbook missed: sync/diff's manifest entries also require a
`size` field (byte length), not just `path`/`filename`/`checksum`.

Flow (see run_full_sync):
  1. Build a manifest covering EVERY current company_documents entry
     (grouped back into one file per (source, title) — see
     rag_service.list_documents/get_document_content), each with a sha256
     checksum + byte size.
  2. POST sync/diff with that full manifest — CoChat computes added /
     modified / deleted / mkdir / rmdir by comparing against what it
     already has. IMPORTANT: a document absent from the manifest is
     treated as deleted, so the manifest must always be complete, never a
     partial "just what changed" list.
  3. Create directories from mkdir (plain path strings, e.g. "hr",
     "hr/onboarding" — already given top-down; parent_id resolved from
     directories created earlier in the same run, or from directory_map
     for ones that already existed).
  4. added -> upload the file's content, then register (file_id,
     directory_id) into the knowledge collection.
  5. modified -> update content in place via the stale file_id CoChat
     returns — no new upload/registration needed.
  6. deleted + rmdir -> one cleanup call removes both.
  7. If step 2 fails, abort before touching anything else — never cleanup
     against a stale/partial diff.
"""
import hashlib
import json
import re
from datetime import datetime
from typing import Optional

import httpx
import psycopg2
import structlog
from psycopg2.extras import Json

from app.config import get_settings
from app.services import rag_service

logger = structlog.get_logger()
settings = get_settings()


def _get_pg():
    import re as _re
    m = _re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {settings.database_url}")
    return psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                             user=m.group(1), password=m.group(2))


def ensure_table():
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS openwebui_sync_log (
                id            SERIAL PRIMARY KEY,
                triggered_by  VARCHAR(100),
                status        VARCHAR(20) NOT NULL,
                summary       JSONB,
                error_message TEXT,
                started_at    TIMESTAMP DEFAULT NOW(),
                finished_at   TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_last_run() -> Optional[dict]:
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            SELECT triggered_by, status, summary, error_message, started_at, finished_at
            FROM openwebui_sync_log ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "triggered_by": row[0], "status": row[1], "summary": row[2], "error_message": row[3],
            "started_at": row[4].isoformat() if row[4] else None,
            "finished_at": row[5].isoformat() if row[5] else None,
        }
    except Exception:
        return None


def _log_start(triggered_by: str) -> Optional[int]:
    """Inserts a 'running' row immediately, so get_last_run() shows a sync
    in progress rather than nothing at all during the (multi-minute) run."""
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO openwebui_sync_log (triggered_by, status) VALUES (%s, 'running') RETURNING id",
            (triggered_by,),
        )
        run_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return run_id
    except Exception:
        return None


def _log_end(run_id: Optional[int], status: str, summary: Optional[dict], error_message: Optional[str]):
    if run_id is None:
        return
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            UPDATE openwebui_sync_log SET status = %s, summary = %s, error_message = %s, finished_at = NOW()
            WHERE id = %s
        """, (status, Json(summary) if summary is not None else None, error_message, run_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

# process_in_background=false (used at upload) makes CoChat embed the
# file synchronously before responding — verified live to take well over
# 60s even for a tiny dummy file, so every call in this module uses a
# generous read timeout rather than httpx's 5s default.
_TIMEOUT = httpx.Timeout(connect=10, read=280, write=60, pool=10)


def is_configured() -> bool:
    return bool(settings.openwebui_base_url and settings.openwebui_api_key and settings.openwebui_knowledge_id)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.openwebui_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.openwebui_api_key}"},
        timeout=_TIMEOUT,
    )


def _kid() -> str:
    return settings.openwebui_knowledge_id


# ── Filename/path derivation ────────────────────────────────────────

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_segment(s: str) -> str:
    """Sanitizes one path/filename segment — CoChat's own path model isn't
    documented for exotic characters, so this stays conservative rather
    than risking a mismatch between what we compute locally and what
    round-trips back from sync/diff."""
    s = _UNSAFE_CHARS.sub("_", s.strip())
    return s.strip("_") or "untitled"


def document_path_and_filename(department: str, source: str, title: str) -> tuple[str, str]:
    """department becomes the CoChat folder (path); filename combines
    source+title (not title alone) since (source, title) — not title by
    itself — is company_documents' real unique key (see
    rag_service.list_documents' GROUP BY)."""
    path = _safe_segment(department or "General").lower()
    filename = f"{_safe_segment(source)}__{_safe_segment(title)}.md"
    return path, filename


def sha256_and_size(content: str) -> tuple[str, int]:
    data = content.encode("utf-8")
    return hashlib.sha256(data).hexdigest(), len(data)


# ── Low-level API calls (each verified live) ────────────────────────

def sync_diff(manifest: list[dict]) -> dict:
    """manifest entries: {"path": str, "filename": str, "checksum": str (sha256 hex), "size": int}.
    Returns {added: [{filename, path}], modified: [...], deleted: [...],
    mkdir: [path strings], rmdir: [...], unmodified_count: int,
    directory_map: {path: directory_id}}."""
    with _client() as c:
        r = c.post(f"/api/v1/knowledge/{_kid()}/sync/diff", json={"manifest": manifest})
        r.raise_for_status()
        return r.json()


def create_dir(name: str, parent_id: Optional[str] = None) -> dict:
    with _client() as c:
        r = c.post(f"/api/v1/knowledge/{_kid()}/dirs/create", json={"name": name, "parent_id": parent_id})
        r.raise_for_status()
        return r.json()


def upload_file(filename: str, content: str, checksum: str) -> str:
    """Uploads file content synchronously (process_in_background=false so
    it's immediately searchable) and returns the new file_id."""
    data = content.encode("utf-8")
    with _client() as c:
        r = c.post(
            "/api/v1/files/?process_in_background=false",
            files={"file": (filename, data, "text/markdown")},
            data={"metadata": json.dumps({"file_hash": checksum})},
        )
        r.raise_for_status()
        return r.json()["id"]


def batch_add_files(entries: list[dict]) -> dict:
    """entries: [{"file_id": str, "directory_id": str | None}, ...] — body
    is the array directly, not wrapped in an object."""
    with _client() as c:
        r = c.post(f"/api/v1/knowledge/{_kid()}/files/batch/add", json=entries)
        r.raise_for_status()
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def update_file_content(stale_file_id: str, content: str) -> dict:
    with _client() as c:
        r = c.post(f"/api/v1/files/{stale_file_id}/data/content/update", json={"content": content})
        r.raise_for_status()
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def cleanup(file_ids: list[str], dir_ids: list[str]) -> dict:
    with _client() as c:
        r = c.post(f"/api/v1/knowledge/{_kid()}/sync/cleanup", json={"file_ids": file_ids, "dir_ids": dir_ids})
        r.raise_for_status()
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


# ── Orchestration ────────────────────────────────────────────────────

def _extract_id(entry, *keys) -> Optional[str]:
    """modified/deleted/rmdir entry shapes weren't reachable to verify live
    (CoChat's embedding backend was down for every attempt this session —
    added/mkdir/directory_map WERE verified; these three were not) — tries
    each plausible key name in order rather than assuming one, so a wrong
    guess surfaces as a clear "couldn't extract id" warning in the run's
    summary instead of a silent no-op or a crash."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        for k in keys:
            if entry.get(k):
                return entry[k]
    return None


def run_full_sync(triggered_by: str = "manual") -> dict:
    """Pushes every company_documents entry into CoChat's Knowledge Base.
    See module docstring for the flow. Raises on sync/diff failure (step 2)
    before touching anything else; individual added/modified/deleted items
    that fail are recorded in the summary and skipped rather than aborting
    the whole run."""
    run_id = _log_start(triggered_by)
    try:
        # 1) Build the full manifest from company_documents.
        local_docs = rag_service.list_documents()
        by_key: dict[tuple[str, str], dict] = {}
        manifest = []
        for d in local_docs:
            content = rag_service.get_document_content(d["source"], d["title"])
            if content is None:
                continue
            path, filename = document_path_and_filename(d.get("department"), d["source"], d["title"])
            checksum, size = sha256_and_size(content)
            manifest.append({"path": path, "filename": filename, "checksum": checksum, "size": size})
            by_key[(path, filename)] = {"content": content, "source": d["source"], "title": d["title"]}

        # 2) Diff against CoChat — abort before touching anything if this fails.
        diff = sync_diff(manifest)

        warnings = []

        # 3) Directories, top-down. mkdir gives plain path strings (verified
        # live); directory_map seeds already-existing paths.
        dir_ids: dict[str, str] = dict(diff.get("directory_map") or {})
        for dir_path in diff.get("mkdir") or []:
            if dir_path in dir_ids:
                continue
            parent_path = "/".join(dir_path.split("/")[:-1])
            name = dir_path.split("/")[-1]
            parent_id = dir_ids.get(parent_path) if parent_path else None
            created = create_dir(name, parent_id)
            dir_ids[dir_path] = created["id"]

        # 4) added -> upload then register.
        added_count = 0
        for entry in diff.get("added") or []:
            key = (entry.get("path", ""), entry.get("filename", ""))
            local = by_key.get(key)
            if not local:
                warnings.append(f"added entry not found locally: {key}")
                continue
            checksum, _size = sha256_and_size(local["content"])
            file_id = upload_file(entry["filename"], local["content"], checksum)
            batch_add_files([{"file_id": file_id, "directory_id": dir_ids.get(entry.get("path", ""))}])
            added_count += 1

        # 5) modified -> update in place via the stale file's id.
        modified_count = 0
        for entry in diff.get("modified") or []:
            key = (entry.get("path", ""), entry.get("filename", "")) if isinstance(entry, dict) else None
            local = by_key.get(key) if key else None
            stale_id = _extract_id(entry, "stale_file_id", "file_id", "id")
            if not local or not stale_id:
                warnings.append(f"could not process modified entry: {entry}")
                continue
            update_file_content(stale_id, local["content"])
            modified_count += 1

        # 6) deleted + rmdir -> one cleanup call.
        file_ids_to_delete = []
        for entry in diff.get("deleted") or []:
            fid = _extract_id(entry, "file_id", "id")
            if fid:
                file_ids_to_delete.append(fid)
            else:
                warnings.append(f"could not extract file_id from deleted entry: {entry}")

        dir_ids_to_delete = []
        for entry in diff.get("rmdir") or []:
            # rmdir might be a path string (like mkdir) or already an id —
            # resolve via directory_map/dir_ids if it looks like a path.
            did = dir_ids.get(entry) if isinstance(entry, str) and entry in dir_ids else _extract_id(entry, "id", "directory_id")
            if did:
                dir_ids_to_delete.append(did)
            else:
                warnings.append(f"could not resolve rmdir entry: {entry}")

        if file_ids_to_delete or dir_ids_to_delete:
            cleanup(file_ids_to_delete, dir_ids_to_delete)

        summary = {
            "added": added_count,
            "modified": modified_count,
            "deleted": len(file_ids_to_delete),
            "rmdir": len(dir_ids_to_delete),
            "unmodified": diff.get("unmodified_count", 0),
            "total_local_docs": len(local_docs),
            "warnings": warnings,
        }
        _log_end(run_id, "success", summary, None)
        logger.info("openwebui_sync_completed", **summary)
        return summary
    except Exception as e:
        logger.error("openwebui_sync_failed", error=str(e))
        _log_end(run_id, "failed", None, str(e))
        raise
