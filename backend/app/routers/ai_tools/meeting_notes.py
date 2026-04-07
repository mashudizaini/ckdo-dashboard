"""
Meeting Notes Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/meeting-notes
Required role: any authenticated user

Endpoints:
  POST /transcribe  — Upload audio → transkripsi (Whisper)
  POST /generate    — Transkripsi → MOM document (Claude)
"""
from fastapi import APIRouter, Depends, UploadFile, File
from app.dependencies import get_current_user, CurrentUser

router = APIRouter()


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Upload audio file → transkripsi menggunakan Whisper lokal."""
    # TODO: implement WhisperService
    return {"status": "ready", "message": "Implement WhisperService"}


@router.post("/generate")
async def generate_mom(
    transcript: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Transkripsi → Minutes of Meeting document via Claude API."""
    # TODO: implement MOM generation via AIService
    return {"status": "ready", "message": "Implement MOM generation"}
