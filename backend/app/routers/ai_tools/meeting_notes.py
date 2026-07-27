"""
Meeting Notes Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/meeting-notes
Required role: any authenticated user

Endpoints:
  POST   /transcribe                  — Upload/recorded audio -> saved permanently + transcribed
                                         (remote GPU Whisper, ai-engine 172.21.2.27; no provider
                                         choice — Claude has no audio transcription capability)
  GET    /recordings                  — List all recordings (recorded + uploaded, unified)
  GET    /recordings/{id}             — Full detail (transcript, mom_json if generated)
  GET    /recordings/{id}/audio       — Download the stored audio file
  DELETE /recordings/{id}             — Delete a recording (audio file + row)
  POST   /recordings/{id}/generate-mom — Transcript -> structured MOM (`provider`: "onprem" or "anthropic")
  PUT    /recordings/{id}/mom          — Save user-edited MOM JSON back onto the recording
  GET    /recordings/{id}/mom/docx     — Render the (possibly edited) MOM as a .docx download
"""
import asyncio
import os
from datetime import datetime
import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user, CurrentUser
from app.models.meeting_recording import MeetingRecording
from app.services.meeting_notes_service import MeetingNotesService
import structlog

logger = structlog.get_logger()
router = APIRouter()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "meeting_notes")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


async def _get_recording_or_404(db: AsyncSession, recording_id: int) -> MeetingRecording:
    result = await db.execute(select(MeetingRecording).where(MeetingRecording.id == recording_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Recording tidak ditemukan")
    return rec


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form(None),
    source: str = Form("uploaded"),  # "recorded" | "uploaded"
    meeting_title: str = Form(""),
    participants: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the audio permanently (recorded and uploaded files both land here,
    in one unified history), then transcribe via the GPU Whisper service."""
    if source not in ("recorded", "uploaded"):
        raise HTTPException(400, 'Invalid source — use "recorded" or "uploaded"')

    content = await file.read()
    ext = os.path.splitext(file.filename or "")[1] or ".webm"
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
    stored_path = os.path.join(_UPLOAD_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(content)

    rec = MeetingRecording(
        filename=stored_name,
        original_name=file.filename or stored_name,
        source=source,
        status="transcribing",
        meeting_title=meeting_title,
        participants=participants,
        created_by=user.username,
    )
    db.add(rec)
    await db.flush()
    await db.commit()
    await db.refresh(rec)

    try:
        result = await MeetingNotesService().transcribe(content, file.filename or stored_name, language)
    except httpx.TimeoutException:
        rec.status = "error"
        rec.error_message = "Transcription timed out — the ai-engine GPU service took too long to respond."
        await db.commit()
        raise HTTPException(504, rec.error_message)
    except httpx.HTTPStatusError as e:
        rec.status = "error"
        rec.error_message = f"Whisper service error: {e.response.text[:300]}"
        await db.commit()
        logger.error("whisper_service_error", status=e.response.status_code, body=e.response.text[:500])
        raise HTTPException(502, rec.error_message)
    except httpx.ConnectError:
        rec.status = "error"
        rec.error_message = "Cannot reach the Whisper transcription service (ai-engine 172.21.2.27:9500) — is it running?"
        await db.commit()
        raise HTTPException(503, rec.error_message)

    rec.status = "transcribed"
    rec.transcript = result.get("text", "")
    rec.transcript_language = result.get("language")
    rec.audio_duration_seconds = result.get("audio_duration_seconds")
    rec.processing_time_seconds = result.get("processing_time_seconds")
    await db.commit()
    await db.refresh(rec)

    return {"success": True, "id": rec.id, **result}


@router.get("/recordings")
async def list_recordings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MeetingRecording).order_by(MeetingRecording.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "meeting_title": r.meeting_title,
            "participants": r.participants,
            "source": r.source,
            "status": r.status,
            "audio_duration_seconds": r.audio_duration_seconds,
            "transcript_preview": (r.transcript or "")[:200],
            "has_mom": r.mom_json is not None,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/recordings/{recording_id}")
async def get_recording(
    recording_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await _get_recording_or_404(db, recording_id)
    return {
        "id": rec.id,
        "meeting_title": rec.meeting_title,
        "participants": rec.participants,
        "source": rec.source,
        "status": rec.status,
        "error_message": rec.error_message,
        "transcript": rec.transcript,
        "transcript_language": rec.transcript_language,
        "audio_duration_seconds": rec.audio_duration_seconds,
        "processing_time_seconds": rec.processing_time_seconds,
        "mom_json": rec.mom_json,
        "mom_meta": rec.mom_meta,
        "created_by": rec.created_by,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


@router.get("/recordings/{recording_id}/audio")
async def download_audio(
    recording_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await _get_recording_or_404(db, recording_id)
    path = os.path.join(_UPLOAD_DIR, rec.filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File audio tidak ditemukan di server")
    with open(path, "rb") as f:
        data = f.read()
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rec.original_name or rec.filename}"'},
    )


@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await _get_recording_or_404(db, recording_id)
    path = os.path.join(_UPLOAD_DIR, rec.filename)
    if os.path.exists(path):
        os.remove(path)
    await db.delete(rec)
    await db.commit()
    return {"message": "Deleted"}


class GenerateMomRequest(BaseModel):
    provider: str = "onprem"  # "onprem" (default, local Ollama) or "anthropic" (Claude)
    date: str = ""
    time: str = ""
    venue: str = ""
    agenda: str = ""


@router.post("/recordings/{recording_id}/generate-mom")
async def generate_mom(
    recording_id: int,
    body: GenerateMomRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transcript -> structured Minutes of Meeting (departments/topics/discussion_points/action_plans)."""
    if body.provider not in ("onprem", "anthropic"):
        raise HTTPException(400, 'Invalid provider — use "onprem" or "anthropic"')
    rec = await _get_recording_or_404(db, recording_id)
    if not (rec.transcript or "").strip():
        raise HTTPException(400, "Recording ini belum punya transcript")

    try:
        mom_json = await asyncio.to_thread(
            MeetingNotesService().generate_mom, rec.transcript, rec.meeting_title or "", rec.participants or "", body.provider
        )
    except Exception as e:
        logger.error("mom_generation_error", error=str(e), provider=body.provider)
        raise HTTPException(500, f"MOM generation failed: {e}")

    mom_meta = {"date": body.date, "time": body.time, "venue": body.venue, "agenda": body.agenda}
    rec.mom_json = mom_json
    rec.mom_meta = mom_meta
    await db.commit()

    return {"success": True, "mom_json": mom_json, "mom_meta": mom_meta}


class SaveMomRequest(BaseModel):
    mom_json: dict
    mom_meta: dict = {}
    meeting_title: str | None = None
    participants: str | None = None


@router.put("/recordings/{recording_id}/mom")
async def save_mom(
    recording_id: int,
    body: SaveMomRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist the user's reviewed/edited MOM back onto the recording."""
    rec = await _get_recording_or_404(db, recording_id)
    rec.mom_json = body.mom_json
    rec.mom_meta = body.mom_meta
    if body.meeting_title is not None:
        rec.meeting_title = body.meeting_title
    if body.participants is not None:
        rec.participants = body.participants
    await db.commit()
    return {"message": "MOM saved"}


@router.get("/recordings/{recording_id}/mom/docx")
async def download_mom_docx(
    recording_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await _get_recording_or_404(db, recording_id)
    if not rec.mom_json:
        raise HTTPException(400, "MOM belum di-generate untuk recording ini")

    docx_bytes = MeetingNotesService().build_mom_docx(
        rec.mom_json, rec.meeting_title or "Meeting", rec.participants or "", rec.mom_meta or {}
    )
    filename = f"{(rec.meeting_title or 'MOM').replace(' ', '_')}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
