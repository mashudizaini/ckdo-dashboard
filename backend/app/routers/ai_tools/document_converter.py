"""
Document Converter Router
─────────────────────────────────────────
Route prefix: /api/v1/ai/document-converter
Required role: any authenticated user

Endpoints:
  POST   /convert          — upload PDF/DOCX/image, dispatches a background
                             conversion job (Celery) and returns immediately
  GET    /jobs             — list conversion jobs (history + in-progress),
                             newest first, with status/progress per job
  GET    /jobs/{id}        — single job detail, including the full markdown
                             once done
  POST   /jobs/{id}/stop   — revoke a pending/processing job
  DELETE /jobs/{id}        — remove a job from history
  POST   /jobs/{id}/translate — translate a done job's extracted content to
                             EN/ID/both, dispatches a background task
  GET    /jobs/{id}/render — stream the job as MD/DOCX/XLSX/JSONL, original
                             or translated — synchronous, no LLM call
  GET/POST/PUT/DELETE /glossary — term dictionary CRUD, shared across every
                             translation (see document_glossary.py)

Conversion used to run inline inside a single SSE-streamed request — closing
the browser tab (or a JWT expiring mid-stream) abandoned the in-flight
docling conversion with no record of it ever having happened. It now runs
as a Celery background task with progress persisted in
document_conversion_jobs, independent of any HTTP connection, so it
survives a closed tab or a logout/re-login — the frontend just polls
GET /jobs instead of holding a live stream open.

The resulting markdown is meant to be reviewed then sent to the AI
Chatbot's Knowledge Base via the existing paste-text ingest endpoint
(POST /api/v1/ai/chatbot/documents with `text=<markdown>`) — this router
only handles conversion, not storage.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, CurrentUser
from app.models.document_conversion_job import DocumentConversionJob
from app.models.document_glossary import DocumentGlossaryTerm
from app.services import document_converter_service as svc
from app.services import document_render_service as render_svc
from app.services import user_api_key_service

router = APIRouter()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "doc_converter_jobs")
os.makedirs(_UPLOAD_DIR, exist_ok=True)

# Providers with per-user saved keys (see user_api_key_service.ALLOWED_
# PROVIDERS) — same convention/exclusions as meeting_notes.py's
# _USER_KEY_PROVIDERS (deepseek intentionally left out, shared-key only).
_USER_KEY_PROVIDERS = {"anthropic", "gemini", "openai", "kimi"}


def _job_to_dict(job: DocumentConversionJob, include_markdown: bool = False, include_blocks: bool = False) -> dict:
    d = {
        "id": job.id,
        "filename": job.filename,
        "language": job.language,
        "status": job.status,
        "total_pages": job.total_pages,
        "current_page": job.current_page,
        "progress_percent": job.progress_percent,
        "status_message": job.status_message,
        "error_message": job.error_message,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "translate_status": job.translate_status,
        "translate_provider": job.translate_provider,
        "translate_error": job.translate_error,
        "has_translation_en": bool(job.translated_en),
        "has_translation_id": bool(job.translated_id),
        "translate_qa_warnings": job.translate_qa_warnings or [],
    }
    if include_markdown:
        d["markdown"] = job.markdown
    if include_blocks:
        d["extracted_blocks"] = job.extracted_blocks
        d["translated_en"] = job.translated_en
        d["translated_id"] = job.translated_id
    return d


async def _get_job_or_404(db: AsyncSession, job_id: int) -> DocumentConversionJob:
    result = await db.execute(select(DocumentConversionJob).where(DocumentConversionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Conversion job not found")
    return job


@router.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    language: str = Form("auto", description='"auto" (default OCR pipeline) or one of document_converter_service.OCR_LANGUAGE_PACKS, e.g. "korean"'),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in svc.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Format tidak didukung: {ext}. Gunakan PDF, DOCX, atau gambar (PNG/JPG).")

    stored_path = os.path.join(_UPLOAD_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}")
    raw = await file.read()
    with open(stored_path, "wb") as f:
        f.write(raw)

    job = DocumentConversionJob(
        filename=file.filename or os.path.basename(stored_path),
        stored_path=stored_path,
        ext=ext,
        language=language,
        status="pending",
        created_by=user.username,
    )
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    from app.tasks.celery_app import celery_app
    result = celery_app.send_task(
        "app.tasks.document_converter_tasks.convert_document",
        kwargs={"job_id": job.id, "file_path": stored_path, "ext": ext, "language": language},
    )
    job.celery_task_id = result.id
    await db.commit()

    return {"job_id": job.id, "task_id": result.id}


@router.get("/jobs")
async def list_jobs(
    limit: int = 30,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Newest first — org-wide history (like Meeting Notes), not just the
    current user's own jobs, so anyone can see what's converting/converted."""
    result = await db.execute(
        select(DocumentConversionJob).order_by(DocumentConversionJob.created_at.desc()).limit(limit)
    )
    return [_job_to_dict(j) for j in result.scalars().all()]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job_or_404(db, job_id)
    return _job_to_dict(job, include_markdown=True, include_blocks=True)


@router.post("/jobs/{job_id}/stop")
async def stop_job(
    job_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import asyncio
    job = await _get_job_or_404(db, job_id)
    if job.status not in ("pending", "processing"):
        raise HTTPException(400, f"Job is already {job.status} — nothing to stop.")

    if job.celery_task_id:
        from app.tasks.celery_app import celery_app
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM", reply=False),
            )
        except Exception:
            pass  # revoke failure should not prevent the DB update below

    job.status = "stopped"
    job.error_message = "Stopped by user"
    await db.commit()
    return {"message": "Job stopped"}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job_or_404(db, job_id)
    if job.status in ("pending", "processing"):
        raise HTTPException(400, "Stop the job before deleting it.")
    if job.stored_path and os.path.exists(job.stored_path):
        os.remove(job.stored_path)
    await db.delete(job)
    await db.commit()
    return {"message": "Deleted"}


# ── Translation ───────────────────────────────────────────────────────────

class TranslateBody(BaseModel):
    target: str = "en"      # "en" | "id" | "both"
    provider: str = "onprem"  # "onprem" | "gemini" | "anthropic" | "openai" | "kimi"


@router.post("/jobs/{job_id}/translate")
async def translate_job(
    job_id: int,
    body: TranslateBody,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.target not in ("en", "id", "both"):
        raise HTTPException(400, 'target must be "en", "id", or "both"')

    job = await _get_job_or_404(db, job_id)
    if job.status != "done":
        raise HTTPException(400, "Conversion isn't done yet — wait for the extraction to finish before translating.")
    if not job.extracted_blocks:
        raise HTTPException(400, "This job has no extracted content to translate (converted before this feature shipped — re-convert the file).")

    api_key = None
    if body.provider in _USER_KEY_PROVIDERS:
        api_key = await user_api_key_service.get_user_key(db, user.username, body.provider)

    job.translate_status = "pending"
    job.translate_error = None
    await db.commit()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.document_translation_tasks.translate_document",
        kwargs={"job_id": job.id, "target": body.target, "provider": body.provider, "api_key": api_key},
    )
    return {"message": "Translation started"}


# ── Rendering ─────────────────────────────────────────────────────────────

_LANG_FIELD = {"en": "translated_en", "id": "translated_id"}


@router.get("/jobs/{job_id}/render")
async def render_job(
    job_id: int,
    format: str = Query(..., pattern="^(md|docx|xlsx|jsonl)$"),
    lang: str = Query("original", pattern="^(original|en|id|both)$"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job_or_404(db, job_id)
    if not job.extracted_blocks:
        raise HTTPException(400, "This job has no extracted content yet.")

    blocks = job.extracted_blocks
    blocks_translated = None
    if lang == "both":
        blocks_translated = job.translated_en or job.translated_id
        if not blocks_translated:
            raise HTTPException(400, "No translation available for this job yet — translate it first.")
    elif lang in ("en", "id"):
        blocks = getattr(job, _LANG_FIELD[lang])
        if not blocks:
            raise HTTPException(400, f"No {lang.upper()} translation available for this job yet — translate it first.")

    title = os.path.splitext(job.filename or "document")[0]
    stamp = job.updated_at.strftime("%Y%m%d") if job.updated_at else datetime.utcnow().strftime("%Y%m%d")
    base_fname = f"{title}_{lang}_{stamp}"

    if format == "md":
        return render_svc.render_md_response(blocks, blocks_translated, title, f"{base_fname}.md")
    if format == "docx":
        return render_svc.render_docx_response(blocks, blocks_translated, title, f"{base_fname}.docx")
    if format == "xlsx":
        return render_svc.render_xlsx_response(blocks, blocks_translated, title, f"{base_fname}.xlsx")
    # jsonl
    doc_meta = {"job_id": job.id, "title": title, "source_filename": job.filename}
    return render_svc.render_jsonl_response(blocks, blocks_translated, doc_meta, f"{base_fname}.jsonl")


# ── Glossary ──────────────────────────────────────────────────────────────

class GlossaryTermBody(BaseModel):
    source_term: str
    target_en: Optional[str] = None
    target_id: Optional[str] = None
    domain: Optional[str] = None
    notes: Optional[str] = None


@router.get("/glossary")
async def list_glossary(
    q: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DocumentGlossaryTerm).order_by(DocumentGlossaryTerm.source_term)
    if q:
        stmt = stmt.where(DocumentGlossaryTerm.source_term.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return [
        {
            "id": t.id, "source_term": t.source_term, "target_en": t.target_en,
            "target_id": t.target_id, "domain": t.domain, "notes": t.notes,
            "created_by": t.created_by,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in result.scalars().all()
    ]


@router.post("/glossary")
async def create_glossary_term(
    body: GlossaryTermBody,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.source_term.strip():
        raise HTTPException(400, "source_term is required")
    term = DocumentGlossaryTerm(
        source_term=body.source_term.strip(), target_en=body.target_en, target_id=body.target_id,
        domain=body.domain, notes=body.notes, created_by=user.username,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return {"id": term.id, "message": "Term added"}


@router.put("/glossary/{term_id}")
async def update_glossary_term(
    term_id: int,
    body: GlossaryTermBody,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DocumentGlossaryTerm).where(DocumentGlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(404, "Term not found")
    term.source_term = body.source_term.strip() or term.source_term
    term.target_en = body.target_en
    term.target_id = body.target_id
    term.domain = body.domain
    term.notes = body.notes
    await db.commit()
    return {"message": "Term updated"}


@router.delete("/glossary/{term_id}")
async def delete_glossary_term(
    term_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DocumentGlossaryTerm).where(DocumentGlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(404, "Term not found")
    await db.delete(term)
    await db.commit()
    return {"message": "Term deleted"}
