"""
Meeting Notes Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/meeting-notes
Required role: any authenticated user

Endpoints:
  POST   /transcribe                  — Upload/recorded audio -> saved permanently + transcribed
                                         (remote GPU Whisper, ai-engine 172.21.2.27; no provider
                                         choice — Claude has no audio transcription capability)
  POST   /recordings/start             — Create a draft recording row + empty file, before any
                                         audio exists — the live in-browser recorder streams into
                                         it via the two endpoints below instead of one big upload
                                         at the end, so it's safe on the server from second one.
  POST   /recordings/{id}/chunk        — Append one MediaRecorder chunk to the recording's file
  POST   /recordings/{id}/finalize     — Mark a live recording's audio as fully captured
  POST   /recordings/{id}/transcribe   — Transcribe audio already on the server (no re-upload)
  POST   /transcript/manual            — Paste a transcript directly -> saved (skips Whisper)
  POST   /transcript/upload-file       — Upload a transcript file (.txt/.srt/.vtt/.docx) -> saved
  GET    /recordings                  — List all recordings (recorded + uploaded, unified)
  GET    /recordings/{id}             — Full detail (transcript, mom_json if generated)
  GET    /recordings/{id}/audio       — Download the stored audio file
  DELETE /recordings/{id}             — Delete a recording (audio file + row)
  POST   /recordings/{id}/generate-mom — Transcript -> structured MOM (`provider`: onprem/anthropic/
                                         gemini/deepseek/openai/kimi — uses the caller's own saved
                                         key when set, see user_api_key_service.py)
  PUT    /recordings/{id}/mom          — Save user-edited MOM JSON back onto the recording
  GET    /recordings/{id}/mom/docx     — Render the (possibly edited) MOM as a .docx download
  POST   /speakers                     — Enroll a person's voice (clip -> embedding, via ai-engine)
  GET    /speakers                     — List enrolled speakers
  DELETE /speakers/{id}                — Remove an enrolled speaker
  POST   /recordings/{id}/identify-speakers — Diarize + match speakers against enrolled voiceprints
"""
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
from app.models.speaker_voiceprint import SpeakerVoiceprint
from app.services.meeting_notes_service import MeetingNotesService, MomProviderCreditError
from app.services import user_api_key_service, speaker_id_service
from app.services.speaker_id_service import SpeakerIdError
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


async def _run_transcription(db: AsyncSession, rec: MeetingRecording, content: bytes, filename: str, language: str | None) -> dict:
    """Shared by POST /transcribe (fresh upload) and POST /recordings/{id}/transcribe
    (audio already stored server-side) — same Whisper call, same status/error handling,
    so the two entry points behave identically once the bytes are in hand."""
    try:
        result = await MeetingNotesService().transcribe(content, filename, language)
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
    rec.transcript_segments = result.get("segments")  # None if the Whisper service doesn't return per-segment timestamps
    rec.audio_duration_seconds = result.get("audio_duration_seconds")
    rec.processing_time_seconds = result.get("processing_time_seconds")
    await db.commit()
    await db.refresh(rec)
    return result


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

    result = await _run_transcription(db, rec, content, file.filename or stored_name, language)
    return {"success": True, "id": rec.id, **result}


def _ext_for_mime(mime_type: str) -> str:
    m = (mime_type or "").lower()
    if "mp4" in m:
        return ".m4a"
    if "ogg" in m:
        return ".ogg"
    return ".webm"


class StartRecordingRequest(BaseModel):
    source: str = "recorded"
    meeting_title: str = ""
    participants: str = ""
    mime_type: str = "audio/webm"


@router.post("/recordings/start")
async def start_recording(
    body: StartRecordingRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a draft recording row + an empty file on disk *before* any audio
    exists. MediaRecorder chunks then stream in via POST .../chunk as they're
    produced (same 30s cadence as the local IndexedDB backup, see
    meetingRecordingRecovery.js), so the meeting is safe on the server from
    its first second — recoverable from History on any device/login, not
    only the browser that recorded it."""
    ext = _ext_for_mime(body.mime_type)
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
    stored_path = os.path.join(_UPLOAD_DIR, stored_name)
    open(stored_path, "wb").close()

    rec = MeetingRecording(
        filename=stored_name,
        original_name=stored_name,
        source=body.source if body.source in ("recorded", "uploaded") else "recorded",
        status="recording",
        meeting_title=body.meeting_title,
        participants=body.participants,
        created_by=user.username,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {"id": rec.id, "filename": rec.filename}


@router.post("/recordings/{recording_id}/chunk")
async def upload_recording_chunk(
    recording_id: int,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append one MediaRecorder chunk to the recording's file on disk. Chunks
    arrive in order, so appending them here is equivalent to the client's own
    Blob(chunks) concatenation on stop — the resulting file is playable the
    same way a normally-stopped recording's file is."""
    rec = await _get_recording_or_404(db, recording_id)
    if rec.status != "recording":
        raise HTTPException(409, f"Recording is not in progress (status={rec.status})")
    content = await file.read()
    path = os.path.join(_UPLOAD_DIR, rec.filename)
    with open(path, "ab") as f:
        f.write(content)
    rec.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "bytes_received": len(content)}


class FinalizeRecordingRequest(BaseModel):
    audio_duration_seconds: float | None = None


@router.post("/recordings/{recording_id}/finalize")
async def finalize_recording(
    recording_id: int,
    body: FinalizeRecordingRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a live recording's audio as fully captured. Kept separate from
    transcription so the recording is durably saved — and shows up in
    History as ready to transcribe — whether or not the user transcribes it
    right away, or ever gets back to this browser at all."""
    rec = await _get_recording_or_404(db, recording_id)
    if rec.status == "recording":
        rec.status = "uploaded"
    if body.audio_duration_seconds is not None:
        rec.audio_duration_seconds = body.audio_duration_seconds
    await db.commit()
    return {"ok": True}


class TranscribeExistingRequest(BaseModel):
    language: str | None = None
    meeting_title: str | None = None
    participants: str | None = None


@router.post("/recordings/{recording_id}/transcribe")
async def transcribe_existing_recording(
    recording_id: int,
    body: TranscribeExistingRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transcribe audio that's already sitting on the server — streamed in via
    .../chunk, or any past recording's stored file — without re-uploading it,
    unlike POST /transcribe which expects the full file in the request body."""
    rec = await _get_recording_or_404(db, recording_id)
    path = os.path.join(_UPLOAD_DIR, rec.filename) if rec.filename else None
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(400, "No audio file found on the server for this recording")

    if body.meeting_title is not None:
        rec.meeting_title = body.meeting_title
    if body.participants is not None:
        rec.participants = body.participants
    rec.status = "transcribing"
    await db.commit()

    with open(path, "rb") as f:
        content = f.read()

    result = await _run_transcription(db, rec, content, rec.filename, body.language)
    return {"success": True, "id": rec.id, **result}


async def _save_manual_transcript(
    db: AsyncSession, user: CurrentUser, text: str, source: str,
    meeting_title: str, participants: str, original_name: str = "",
) -> dict:
    """Shared by the paste and file-upload entry points below — creates a
    MeetingRecording row directly from already-available text, skipping
    Whisper entirely. filename is left blank (no audio file exists for
    these); the NOT NULL constraint is satisfied with "" rather than
    requiring a schema migration for a nullable column. Returns the same
    shape /transcribe does ({success, id, text, ...}) so the frontend can
    feed it into the exact same setTranscript()/step="transcript" flow."""
    text = (text or "").strip()
    if not text:
        raise HTTPException(400, "Transcript tidak boleh kosong")

    rec = MeetingRecording(
        filename="",
        original_name=original_name,
        source=source,
        status="transcribed",
        meeting_title=meeting_title,
        participants=participants,
        transcript=text,
        created_by=user.username,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    return {
        "success": True, "id": rec.id, "text": text, "language": None,
        "audio_duration_seconds": None, "processing_time_seconds": None,
    }


class ManualTranscriptRequest(BaseModel):
    text: str
    meeting_title: str = ""
    participants: str = ""


@router.post("/transcript/manual")
async def submit_manual_transcript(
    body: ManualTranscriptRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paste-a-transcript entry point — for a meeting that was already
    transcribed elsewhere (or typed up from notes), skipping audio/Whisper
    entirely so it can go straight to Generate MOM."""
    return await _save_manual_transcript(db, user, body.text, "pasted", body.meeting_title, body.participants)


@router.post("/transcript/upload-file")
async def upload_transcript_file(
    file: UploadFile = File(...),
    meeting_title: str = Form(""),
    participants: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload-a-transcript-file entry point (.txt/.srt/.vtt/.docx) — same
    purpose as the paste endpoint above, for a transcript that already
    exists as a file instead of being typed/pasted by hand."""
    content = await file.read()
    try:
        text = MeetingNotesService().extract_text_from_upload(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _save_manual_transcript(
        db, user, text, "uploaded_transcript", meeting_title, participants, file.filename or "",
    )


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
        "speaker_segments": rec.speaker_segments,
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


_MOM_PROVIDERS = ("onprem", "anthropic", "gemini", "deepseek", "openai", "kimi")

# Which providers support a per-user key override (must line up with
# user_api_key_service.ALLOWED_PROVIDERS) — "deepseek" is intentionally
# excluded for now, shared-key only, since nobody's asked for it yet.
_USER_KEY_PROVIDERS = {"anthropic", "gemini", "openai", "kimi"}


class GenerateMomRequest(BaseModel):
    provider: str = "onprem"  # "onprem" (default, local Ollama), "anthropic" (Claude), "gemini", "deepseek", "openai" (ChatGPT), or "kimi"
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
    if body.provider not in _MOM_PROVIDERS:
        raise HTTPException(400, f'Invalid provider — use one of {", ".join(_MOM_PROVIDERS)}')
    rec = await _get_recording_or_404(db, recording_id)
    if not (rec.transcript or "").strip():
        raise HTTPException(400, "Recording ini belum punya transcript")

    api_key = None
    if body.provider in _USER_KEY_PROVIDERS:
        api_key = await user_api_key_service.get_user_key(db, user.username, body.provider)

    try:
        mom_json = await MeetingNotesService().generate_mom(
            rec.transcript, rec.meeting_title or "", rec.participants or "", body.provider, api_key, body.agenda
        )
    except MomProviderCreditError as e:
        logger.warning("mom_generation_credit_error", error=str(e), provider=body.provider)
        raise HTTPException(402, str(e))
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
    # "MOM {title} {short date}.docx" — matches the naming convention of the
    # company's own MOM files (e.g. "MOM Admin Jul 24, 2026.docx"), using the
    # recording's actual timestamp rather than the free-text date field so
    # it's always well-formed regardless of what the user typed there.
    date_part = rec.created_at.strftime("%b %-d, %Y") if rec.created_at else ""
    filename = f"MOM {rec.meeting_title or 'Meeting'} {date_part}.docx".replace("  ", " ").strip()
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Speaker identification ──────────────────────────────────────────────
# Enroll a person's voice once (a short solo clip -> one embedding vector,
# computed by the ai-engine diarization service), then match it against
# speaker clusters detected in future recordings. See speaker_id_service.py.

@router.post("/speakers")
async def enroll_speaker(
    file: UploadFile = File(...),
    name: str = Form(...),
    gender: str = Form(""),
    position: str = Form(""),
    team: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enroll one person's voice from a short (ideally single-speaker,
    20s+) clip. Re-enrolling the same name overwrites their embedding
    (e.g. a better/cleaner sample recorded later)."""
    if not name.strip():
        raise HTTPException(400, "Nama tidak boleh kosong")
    content = await file.read()
    try:
        embedding = await speaker_id_service.embed_clip(content, file.filename or "clip.wav")
    except SpeakerIdError as e:
        raise HTTPException(502, str(e))

    result = await db.execute(select(SpeakerVoiceprint).where(SpeakerVoiceprint.name == name.strip()))
    existing = result.scalar_one_or_none()
    if existing:
        existing.gender = gender
        existing.position = position
        existing.team = team
        existing.embedding = embedding
        existing.sample_filename = file.filename
        existing.updated_at = datetime.utcnow()
    else:
        db.add(SpeakerVoiceprint(
            name=name.strip(), gender=gender, position=position, team=team,
            embedding=embedding, sample_filename=file.filename, created_by=user.username,
        ))
    await db.commit()
    return {"success": True, "name": name.strip()}


@router.get("/speakers")
async def list_speakers(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SpeakerVoiceprint).order_by(SpeakerVoiceprint.name))
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "name": r.name, "gender": r.gender, "position": r.position, "team": r.team,
            "sample_filename": r.sample_filename, "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/speakers/{speaker_id}")
async def delete_speaker(
    speaker_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SpeakerVoiceprint).where(SpeakerVoiceprint.id == speaker_id))
    vp = result.scalar_one_or_none()
    if not vp:
        raise HTTPException(404, "Speaker tidak ditemukan")
    await db.delete(vp)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/recordings/{recording_id}/identify-speakers")
async def identify_speakers(
    recording_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Diarize this recording's stored audio, match each detected speaker
    cluster against enrolled voiceprints, and save the result. Requires the
    recording to already be transcribed (needs the audio file on disk;
    per-line text alignment additionally needs transcript_segments — falls
    back to un-aligned per-turn speaker labels if the transcription service
    didn't return per-segment timestamps)."""
    rec = await _get_recording_or_404(db, recording_id)
    if not rec.filename:
        raise HTTPException(400, "Recording ini tidak punya file audio")
    path = os.path.join(_UPLOAD_DIR, rec.filename)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(400, "File audio tidak ditemukan di server")

    result = await db.execute(select(SpeakerVoiceprint))
    voiceprints = result.scalars().all()
    if not voiceprints:
        raise HTTPException(400, "Belum ada speaker yang di-enroll — tambahkan lewat POST /speakers dulu")

    with open(path, "rb") as f:
        content = f.read()

    try:
        diarization = await speaker_id_service.diarize_audio(content, rec.filename)
    except SpeakerIdError as e:
        raise HTTPException(502, str(e))

    speaker_names = speaker_id_service.match_speakers(diarization["speaker_embeddings"], voiceprints)

    if rec.transcript_segments:
        merged = speaker_id_service.merge_transcript_with_speakers(
            rec.transcript_segments, diarization["segments"], speaker_names
        )
    else:
        # No per-line transcript timestamps available — still useful as a
        # "who spoke when" breakdown, just not aligned to specific text.
        merged = [
            {"start": d["start"], "end": d["end"], "text": None, "speaker": speaker_names.get(d["speaker"], "Unknown speaker")}
            for d in diarization["segments"]
        ]

    rec.speaker_segments = merged
    await db.commit()
    return {"success": True, "speaker_segments": merged, "speakers_detected": list(speaker_names.values())}
