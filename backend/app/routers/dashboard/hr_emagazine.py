"""
E-Magazine Router — HR Sub-module
Route prefix : /api/v1/dashboard/hr/e-magazine
Required role: hr_staff OR admin

Upload dir is mounted from host: ./e-magazine/magazines -> /app/magazine-uploads
index.json in that dir is the canonical list served statically by nginx.
"""
import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.dependencies import CurrentUser, Roles, require_role

router = APIRouter()

UPLOAD_DIR = Path("/app/magazine-uploads")
INDEX_FILE = UPLOAD_DIR / "index.json"
MAX_PDF_MB = 100
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_MB = 20


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


def _extract_pdf_pages_text(pdf_path: Path) -> list[str]:
    """Per-page text extraction — based on the AI Chatbot's document ingest
    pipeline (chatbot.py POST /documents), but OCR runs on EVERY page here
    rather than only pages with zero native text. That "OCR only if fully
    blank" heuristic works for a plain policy document (usually either
    fully-scanned or fully-digital), but a designed magazine spread
    routinely mixes a tiny bit of real text (a running footer/page number)
    with a full-bleed graphic headline or photo layout that carries no text
    layer at all — confirmed live: several pages extracted to just "CKD OTTO
    e-Magz ... | July 2026\\n8" (the footer) while the actual article title
    and body were part of the page's image content, silently invisible to
    search. OCR-ing every page and merging both catches that content too, at
    the cost of a slower conversion (already an accepted trade-off for this
    on-premise, on-demand button)."""
    import fitz
    os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/5/tessdata"
    doc = fitz.open(pdf_path)
    pages = []
    try:
        for page in doc:
            native = page.get_text().strip()
            ocr_text = ""
            try:
                tp = page.get_textpage_ocr(dpi=300, language="ind+eng", full=True)
                ocr_text = page.get_text(textpage=tp).strip()
            except Exception:
                pass
            pages.append("\n".join(t for t in (native, ocr_text) if t))
    finally:
        doc.close()
    return pages


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
    description:   str        = Form(""),
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
        "type":        "magazine",
        "filename":    safe_name,
        "title":       title.strip(),
        "date":        date_label.strip(),
        "description": description.strip(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "qr_links":    qr_links,
    })
    _write_index(entries)
    return {"ok": True, "filename": safe_name, "entries": len(entries)}


@router.post("/upload-album")
async def upload_album(
    title:         str               = Form(...),
    date_label:    str               = Form(""),
    description:   str               = Form(""),
    qr_links_json: str               = Form("[]"),
    photos:        list[UploadFile]  = File(...),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Upload a photo album 'edition' — shown in the same public reading
    room (magazines/index.json -> e-magazine/index.html) as a PDF
    e-magazine, just as a folder of photos flipped through page-by-page
    instead of PDF pages. Reuses every other endpoint below (qr-links,
    meta, delete) since they're all keyed generically by the entry's
    `filename` — here that's the album's folder name, not a real file."""
    if not photos:
        raise HTTPException(400, "Minimal 1 foto diperlukan.")
    for p in photos:
        if p.content_type not in ALLOWED_PHOTO_TYPES:
            raise HTTPException(400, f"'{p.filename}' bukan tipe gambar yang didukung (JPEG/PNG/WebP).")

    try:
        qr_links = json.loads(qr_links_json) if qr_links_json else []
        qr_links = [q for q in qr_links if q.get("url","").strip()]
    except Exception:
        qr_links = []

    album_id = f"album_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{_safe_filename(title)[:40] or 'photos'}"
    album_dir = UPLOAD_DIR / album_id
    album_dir.mkdir(parents=True, exist_ok=True)

    photo_names = []
    try:
        for i, p in enumerate(photos, start=1):
            content = await p.read()
            if len(content) > MAX_PHOTO_MB * 1024 * 1024:
                raise HTTPException(413, f"'{p.filename}' melebihi {MAX_PHOTO_MB} MB.")
            ext = Path(p.filename or "").suffix.lower() or ".jpg"
            photo_filename = f"photo_{i}{ext}"
            (album_dir / photo_filename).write_bytes(content)
            photo_names.append(photo_filename)
    except HTTPException:
        shutil.rmtree(album_dir, ignore_errors=True)
        raise

    entries = _read_index()
    entries.insert(0, {
        "type":        "photo_album",
        "filename":    album_id,
        "title":       title.strip(),
        "date":        date_label.strip(),
        "description": description.strip(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "qr_links":    qr_links,
        "photos":      photo_names,
    })
    _write_index(entries)
    return {"ok": True, "filename": album_id, "entries": len(entries), "photos": len(photo_names)}


@router.post("/files/{filename}/add-photos")
async def add_photos(
    filename:      str,
    title:         str               = Form(""),
    date_label:    str               = Form(""),
    description:   str               = Form(""),
    photos:        list[UploadFile]  = File(...),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Append more photos to an existing photo album, optionally renaming
    it in the same call — the Edit button on a photo_album row reopens the
    top upload form pre-filled with this album instead of the small
    title/date-only inline editor, so the admin can add more event photos
    without recreating the whole album."""
    safe_name = _safe_filename(filename)
    entries = _read_index()
    entry = next((e for e in entries if e["filename"] == safe_name), None)
    if not entry:
        raise HTTPException(404, "Album tidak ditemukan.")
    if entry.get("type") != "photo_album":
        raise HTTPException(400, "Hanya photo album yang bisa ditambah foto.")
    if not photos:
        raise HTTPException(400, "Minimal 1 foto diperlukan.")
    for p in photos:
        if p.content_type not in ALLOWED_PHOTO_TYPES:
            raise HTTPException(400, f"'{p.filename}' bukan tipe gambar yang didukung (JPEG/PNG/WebP).")

    album_dir = UPLOAD_DIR / safe_name
    album_dir.mkdir(parents=True, exist_ok=True)
    existing_photos = entry.get("photos", [])

    new_names = []
    try:
        for i, p in enumerate(photos, start=len(existing_photos) + 1):
            content = await p.read()
            if len(content) > MAX_PHOTO_MB * 1024 * 1024:
                raise HTTPException(413, f"'{p.filename}' melebihi {MAX_PHOTO_MB} MB.")
            ext = Path(p.filename or "").suffix.lower() or ".jpg"
            photo_filename = f"photo_{i}{ext}"
            (album_dir / photo_filename).write_bytes(content)
            new_names.append(photo_filename)
    except HTTPException:
        for name in new_names:
            (album_dir / name).unlink(missing_ok=True)
        raise

    entry["photos"] = existing_photos + new_names
    if title.strip():
        entry["title"] = title.strip()
    if date_label.strip():
        entry["date"] = date_label.strip()
    if description.strip():
        entry["description"] = description.strip()
    _write_index(entries)
    return {"ok": True, "filename": safe_name, "photos": len(entry["photos"]), "added": len(new_names)}


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


@router.patch("/files/{filename}/meta")
async def update_meta(
    filename: str,
    payload: dict,
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Update title/period/description for an existing edition (without
    re-uploading the PDF)."""
    safe_name = _safe_filename(filename)
    entries   = _read_index()
    found     = False
    for e in entries:
        if e["filename"] == safe_name:
            if "title" in payload:
                title = (payload.get("title") or "").strip()
                if not title:
                    raise HTTPException(400, "Title tidak boleh kosong.")
                e["title"] = title
            if "date" in payload:
                e["date"] = (payload.get("date") or "").strip()
            if "description" in payload:
                e["description"] = (payload.get("description") or "").strip()
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
    """Delete an edition (PDF magazine or photo album) and remove it from
    index.json."""
    safe_name = _safe_filename(filename)
    entries = _read_index()
    entry = next((e for e in entries if e["filename"] == safe_name), None)
    if not entry:
        raise HTTPException(404, "File tidak ditemukan.")

    if entry.get("type") == "photo_album":
        shutil.rmtree(UPLOAD_DIR / safe_name, ignore_errors=True)
    else:
        dest = UPLOAD_DIR / safe_name
        if dest.exists():
            dest.unlink()

    entries = [e for e in entries if e["filename"] != safe_name]
    _write_index(entries)
    return {"ok": True, "deleted": safe_name}


@router.post("/files/{filename}/convert-to-text")
async def convert_to_text(
    filename: str,
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Extract per-page text from a magazine PDF and write it as a sibling
    {filename}.pages.json next to the PDF — the same directory nginx serves
    statically at /e-magazine/magazines/, so the public viewer's search
    feature can fetch it directly with no new read endpoint."""
    entries = _read_index()
    entry = next((e for e in entries if e["filename"] == _safe_filename(filename)), None)
    if entry and entry.get("type") == "photo_album":
        raise HTTPException(400, "Convert to Text hanya berlaku untuk e-Magazine PDF, bukan photo album.")

    safe_name = _safe_filename(filename)
    pdf_path = UPLOAD_DIR / safe_name
    if not pdf_path.exists():
        raise HTTPException(404, "File tidak ditemukan.")

    try:
        pages = await asyncio.to_thread(_extract_pdf_pages_text, pdf_path)
    except Exception as e:
        raise HTTPException(500, f"Konversi teks gagal: {e}")

    converted_at = datetime.now(timezone.utc).isoformat()
    text_path = UPLOAD_DIR / f"{safe_name}.pages.json"
    text_path.write_text(
        json.dumps({"pages": pages, "converted_at": converted_at}, ensure_ascii=False),
        encoding="utf-8",
    )

    entries = _read_index()
    for e in entries:
        if e["filename"] == safe_name:
            e["text_pages"] = len(pages)
            e["text_converted_at"] = converted_at
            break
    _write_index(entries)

    return {"ok": True, "filename": safe_name, "pages": len(pages), "chars": sum(len(p) for p in pages)}
