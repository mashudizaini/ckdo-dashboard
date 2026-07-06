"""
E-Magazine Router — HR Sub-module
Route prefix : /api/v1/dashboard/hr/e-magazine
Required role: hr_staff OR admin

Upload dir is mounted from host: ./e-magazine/magazines -> /app/magazine-uploads
index.json in that dir is the canonical list served statically by nginx.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.dependencies import CurrentUser, Roles, require_role

router = APIRouter()

UPLOAD_DIR = Path("/app/magazine-uploads")
INDEX_FILE = UPLOAD_DIR / "index.json"
MAX_PDF_MB = 100


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w\s\-.]", "", name).strip()
    return name or "magazine.pdf"


def _read_index() -> list[dict]:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Rebuild from existing PDFs if index is missing / corrupt
    entries = []
    for p in sorted(UPLOAD_DIR.glob("*.pdf"), key=lambda f: f.stat().st_mtime):
        entries.append({"filename": p.name, "title": p.stem, "date": "", "uploaded_at": ""})
    return entries


def _write_index(entries: list[dict]) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files(user: CurrentUser = Depends(require_role(Roles.HR))):
    """Return the edition list from index.json."""
    return _read_index()


@router.post("/upload")
async def upload_magazine(
    file:          UploadFile = File(...),
    title:         str        = Form(...),
    date_label:    str        = Form(""),
    qr_links_json: str        = Form("[]"),   # JSON: [{"label":"...","url":"..."}]
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Upload a PDF magazine and register it in index.json."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Hanya file PDF yang diperbolehkan.")

    content = await file.read()
    if len(content) > MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(413, f"Ukuran file melebihi {MAX_PDF_MB} MB.")

    try:
        qr_links = json.loads(qr_links_json) if qr_links_json else []
        qr_links = [q for q in qr_links if q.get("url","").strip()]
    except Exception:
        qr_links = []

    safe_name = _safe_filename(file.filename)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)

    entries = _read_index()
    entries = [e for e in entries if e["filename"] != safe_name]
    entries.insert(0, {
        "filename":    safe_name,
        "title":       title.strip(),
        "date":        date_label.strip(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "qr_links":    qr_links,
    })
    _write_index(entries)
    return {"ok": True, "filename": safe_name, "entries": len(entries)}


@router.patch("/files/{filename}/qr-links")
async def update_qr_links(
    filename: str,
    qr_links: list[dict],
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Update QR links for an existing edition (without re-uploading the PDF)."""
    safe_name = _safe_filename(filename)
    entries   = _read_index()
    found     = False
    for e in entries:
        if e["filename"] == safe_name:
            e["qr_links"] = [q for q in qr_links if q.get("url","").strip()]
            found = True
            break
    if not found:
        raise HTTPException(404, "Edisi tidak ditemukan.")
    _write_index(entries)
    return {"ok": True, "filename": safe_name}


@router.delete("/files/{filename}")
async def delete_magazine(
    filename: str,
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Delete a magazine PDF and remove it from index.json."""
    safe_name = _safe_filename(filename)
    dest = UPLOAD_DIR / safe_name
    if not dest.exists():
        raise HTTPException(404, "File tidak ditemukan.")
    dest.unlink()

    entries = [e for e in _read_index() if e["filename"] != safe_name]
    _write_index(entries)
    return {"ok": True, "deleted": safe_name}
