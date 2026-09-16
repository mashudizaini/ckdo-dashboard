"""
AP Autoinvoice — Google Drive auto-sync
─────────────────────────────────────────
Each user gets their own subfolder inside one Shared Drive (service account
is a Content Manager member of the Shared Drive itself — Shared Drive
permissions are inherited by every subfolder automatically, so it only had
to be granted once, not per-subfolder). A Celery Beat job polls the
configured subfolders every few minutes, feeds any new PDF through the
EXACT SAME extraction pipeline the manual /upload endpoint already uses
(ap_invoice_service.extract_pdf + save_to_staging), then moves the source
file into that subfolder's own "Processed" or "Error" sub-subfolder so:
  - it's never re-processed on the next poll (also belt-and-suspenders
    guarded by gdrive_file_id already existing in ap_invoice_stg), and
  - the uploader can see the outcome without opening the Dashboard at all —
    a failed file is also renamed with an "[ERROR - <reason>] " prefix,
    since this codebase has no outbound-email capability yet to notify them
    directly (see the Google Drive integration discussion this was built
    from — that's flagged there as a deliberate v1 simplification, not an
    oversight).

Folder IDs are managed through ap_invoice_gdrive_folder_map (admin CRUD,
see the router) rather than hardcoded — HR/Accounting can add or retire a
user's watched folder without a code change.
"""
import io
import os
import re
from datetime import datetime
from typing import Optional

import psycopg2
import structlog
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.config import get_settings
from app.services import ap_invoice_service as svc

logger = structlog.get_logger()
settings = get_settings()

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_PDF_MIME = "application/pdf"
_FOLDER_MIME = "application/vnd.google-apps.folder"
_PROCESSED_SUBFOLDER = "Processed"
_ERROR_SUBFOLDER = "Error"


def _get_pg():
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {settings.database_url}")
    return psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                             user=m.group(1), password=m.group(2))


def ensure_tables():
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ap_invoice_gdrive_folder_map (
                id          SERIAL PRIMARY KEY,
                user_label  VARCHAR(150) NOT NULL,
                folder_id   VARCHAR(100) NOT NULL UNIQUE,
                active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ap_invoice_gdrive_sync_log (
                id            SERIAL PRIMARY KEY,
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


def is_configured() -> bool:
    return bool(settings.gdrive_service_account_json and settings.gdrive_shared_drive_id
                and os.path.exists(settings.gdrive_service_account_json))


def _get_drive_client():
    creds = service_account.Credentials.from_service_account_file(
        settings.gdrive_service_account_json, scopes=_SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── Folder map CRUD (admin) ─────────────────────────────────────────────

def list_folder_maps() -> list[dict]:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_label, folder_id, active, created_at
            FROM ap_invoice_gdrive_folder_map ORDER BY user_label
        """)
        return [
            {"id": r[0], "user_label": r[1], "folder_id": r[2], "active": r[3],
             "created_at": r[4].isoformat() if r[4] else None}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def add_folder_map(user_label: str, folder_id: str) -> dict:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ap_invoice_gdrive_folder_map (user_label, folder_id)
            VALUES (%s, %s)
            ON CONFLICT (folder_id) DO UPDATE SET user_label = EXCLUDED.user_label, active = TRUE
            RETURNING id
        """, (user_label, folder_id))
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"id": row_id, "user_label": user_label, "folder_id": folder_id}
    finally:
        conn.close()


def set_folder_map_active(map_id: int, active: bool):
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ap_invoice_gdrive_folder_map SET active = %s WHERE id = %s", (active, map_id))
        conn.commit()
    finally:
        conn.close()


def delete_folder_map(map_id: int):
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ap_invoice_gdrive_folder_map WHERE id = %s", (map_id,))
        conn.commit()
    finally:
        conn.close()


def list_shared_drive_subfolders() -> list[dict]:
    """Top-level folders directly under the configured Shared Drive — lets
    the admin UI offer a picker instead of requiring a hand-copied folder
    ID. Excludes each folder's own Processed/Error housekeeping
    subfolders (those only ever appear one level deeper, under a folder
    that's already been picked here, so they'd never show up regardless —
    kept explicit for clarity)."""
    service = _get_drive_client()
    folders = _list_children(service, settings.gdrive_shared_drive_id, mime_type=_FOLDER_MIME)
    return [{"id": f["id"], "name": f["name"]} for f in folders]


# ── Sync log ─────────────────────────────────────────────────────────────

def get_last_sync() -> Optional[dict]:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT status, summary, error_message, started_at, finished_at
            FROM ap_invoice_gdrive_sync_log ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return None
        return {
            "status": row[0], "summary": row[1], "error_message": row[2],
            "started_at": row[3].isoformat() if row[3] else None,
            "finished_at": row[4].isoformat() if row[4] else None,
        }
    finally:
        conn.close()


def _log_start() -> Optional[int]:
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("INSERT INTO ap_invoice_gdrive_sync_log (status) VALUES ('running') RETURNING id")
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
        from psycopg2.extras import Json
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            UPDATE ap_invoice_gdrive_sync_log
            SET status = %s, summary = %s, error_message = %s, finished_at = NOW()
            WHERE id = %s
        """, (status, Json(summary) if summary is not None else None, error_message, run_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Drive helpers ────────────────────────────────────────────────────────

def _list_children(service, parent_id: str, mime_type: Optional[str] = None) -> list[dict]:
    q = f"'{parent_id}' in parents and trashed = false"
    if mime_type:
        q += f" and mimeType = '{mime_type}'"
    out, page_token = [], None
    while True:
        resp = service.files().list(
            q=q, spaces="drive", fields="nextPageToken, files(id, name, mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True, pageToken=page_token,
        ).execute()
        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def _get_or_create_subfolder(service, parent_id: str, name: str) -> str:
    for f in _list_children(service, parent_id, mime_type=_FOLDER_MIME):
        if f["name"] == name:
            return f["id"]
    created = service.files().create(
        body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
        fields="id", supportsAllDrives=True,
    ).execute()
    return created["id"]


def _download_file(service, file_id: str, dest_path: str):
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.FileIO(dest_path, "wb")
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    buf.close()


def _move_file(service, file_id: str, new_parent_id: str, old_parent_id: str, new_name: Optional[str] = None):
    body = {"name": new_name} if new_name else {}
    service.files().update(
        fileId=file_id, addParents=new_parent_id, removeParents=old_parent_id,
        body=body, supportsAllDrives=True,
    ).execute()


_ERROR_PREFIX_RE = re.compile(r"^\[ERROR[^\]]*\]\s*")


def _already_processed(gdrive_file_id: str) -> bool:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM ap_invoice_stg WHERE gdrive_file_id = %s LIMIT 1", (gdrive_file_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def _tag_staging_row(stg_id: int, gdrive_file_id: str, user_label: str):
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE ap_invoice_stg SET source_channel = 'gdrive', gdrive_file_id = %s, gdrive_uploader = %s
            WHERE stg_id = %s
        """, (gdrive_file_id, user_label, stg_id))
        conn.commit()
    finally:
        conn.close()


def sync_folder(service, folder_id: str, user_label: str) -> dict:
    """One watched folder: new PDFs in -> staged + moved to Processed/Error.
    Returns {"processed": n, "errors": n, "skipped": n}."""
    processed_id = _get_or_create_subfolder(service, folder_id, _PROCESSED_SUBFOLDER)
    error_id = _get_or_create_subfolder(service, folder_id, _ERROR_SUBFOLDER)

    files = _list_children(service, folder_id, mime_type=_PDF_MIME)
    result = {"processed": 0, "errors": 0, "skipped": 0}

    for f in files:
        file_id, filename = f["id"], f["name"]
        if _already_processed(file_id):
            result["skipped"] += 1
            continue

        local_name = f"gdrive_{file_id}_{re.sub(r'[^A-Za-z0-9._-]', '_', filename)}"
        local_path = os.path.join(svc.UPLOAD_DIR, local_name)
        try:
            _download_file(service, file_id, local_path)
            invoice_data = svc.extract_pdf(local_path, filename, provider="onprem")
            if not invoice_data.get("invoice_num"):
                raise ValueError("Invoice Number tidak ditemukan dalam PDF")

            pg_conn = _get_pg()
            try:
                stg_id = svc.save_to_staging(pg_conn, invoice_data)
            finally:
                pg_conn.close()
            _tag_staging_row(stg_id, file_id, user_label)

            _move_file(service, file_id, processed_id, folder_id)
            result["processed"] += 1
            logger.info("gdrive_invoice_processed", folder_id=folder_id, user_label=user_label,
                        filename=filename, stg_id=stg_id)
        except Exception as e:
            error_reason = str(e)[:150]
            clean_name = _ERROR_PREFIX_RE.sub("", filename)
            try:
                _move_file(service, file_id, error_id, folder_id, new_name=f"[ERROR - {error_reason}] {clean_name}")
            except Exception:
                pass  # the extraction error itself is the one worth keeping in the log below
            result["errors"] += 1
            logger.warning("gdrive_invoice_failed", folder_id=folder_id, user_label=user_label,
                           filename=filename, error=error_reason)
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    return result


def sync_all(triggered_by: str = "scheduler") -> dict:
    if not is_configured():
        # Not an error — the Beat schedule fires every 10 minutes
        # unconditionally, and logging a 'failed' run every time nobody's
        # configured a service account yet would just be noise. The manual
        # "Sync Now" button in Setup still surfaces this clearly via
        # is_configured() directly, so it's not silently hidden either.
        return {"skipped": True, "reason": "not_configured"}

    run_id = _log_start()
    try:
        service = _get_drive_client()
        folder_maps = [m for m in list_folder_maps() if m["active"]]
        totals = {"processed": 0, "errors": 0, "skipped": 0, "folders": len(folder_maps)}
        per_folder = []
        for m in folder_maps:
            r = sync_folder(service, m["folder_id"], m["user_label"])
            per_folder.append({"user_label": m["user_label"], **r})
            totals["processed"] += r["processed"]
            totals["errors"] += r["errors"]
            totals["skipped"] += r["skipped"]

        summary = {"triggered_by": triggered_by, **totals, "per_folder": per_folder}
        _log_end(run_id, "success", summary, None)
        return summary
    except Exception as e:
        _log_end(run_id, "failed", None, str(e))
        raise
