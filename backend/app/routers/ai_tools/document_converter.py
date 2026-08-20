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
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user, CurrentUser
from app.models.document_conversion_job import DocumentConversionJob
from app.services import document_converter_service as svc

router = APIRouter()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "doc_converter_jobs")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _job_to_dict(job: DocumentConversionJob, include_markdown: bool = False) -> dict:
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
    }
    if include_markdown:
        d["markdown"] = job.markdown
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
    return _job_to_dict(job, include_markdown=True)


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
