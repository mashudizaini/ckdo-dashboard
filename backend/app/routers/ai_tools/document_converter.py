"""
Document Converter Router
─────────────────────────────────────────
Route prefix: /api/v1/ai/document-converter
Required role: any authenticated user

Endpoints:
  POST /convert — upload PDF/DOCX/image, streams per-page conversion
                  progress + final RAG-friendly markdown (SSE)

The resulting markdown is meant to be reviewed then sent to the AI
Chatbot's Knowledge Base via the existing paste-text ingest endpoint
(POST /api/v1/ai/chatbot/documents with `text=<markdown>`) — this router
only handles conversion, not storage.
"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from app.dependencies import get_current_user, CurrentUser
from app.services import document_converter_service as svc

router = APIRouter()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "doc_converter_tmp")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


@router.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in svc.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Format tidak didukung: {ext}. Gunakan PDF, DOCX, atau gambar (PNG/JPG).")

    tmp_path = os.path.join(_UPLOAD_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}")
    raw = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(raw)

    async def stream_and_cleanup():
        try:
            async for chunk in svc.convert_stream(tmp_path, ext):
                yield chunk
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return StreamingResponse(stream_and_cleanup(), media_type="text/event-stream")
