"""
AI Chatbot Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/chatbot
Required role: any authenticated user (chat) / any staff role (knowledge base)

Endpoints:
  POST   /chat                — Policy chat: send message, get AI response (streaming, RAG-grounded)
  POST   /oracle-chat         — Oracle EBS data chat: tool-calling over Postgres EIS (streaming)
  POST   /general-chat        — General-purpose chat: no RAG, no tools (streaming)
  GET    /documents           — List ingested knowledge base documents
  GET    /documents/content   — Full concatenated text of one document (for editing)
  POST   /documents           — Ingest a new document (paste text or upload file)
  DELETE /documents           — Delete a document by source+title
  GET    /status               — Whether RAG (local Ollama embeddings) is configured

All 3 chat endpoints take an optional `provider` field on the request body:
"onprem" (default, local Ollama) or "gemini" (Google Gemini API).
"""
import asyncio
import os
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, require_role, CurrentUser, Roles
from app.services.ai_service import AIService
from app.services.oracle_chat_service import OracleChatService
from app.services import rag_service
from app.services import user_api_key_service

router = APIRouter()
settings = get_settings()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "kb_tmp")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []
    provider: str = "onprem"  # "onprem" (default, local Ollama) or "gemini"


async def _resolve_gemini_key(db: AsyncSession, user: CurrentUser) -> str:
    """User's own saved Gemini key if they set one, else the shared company key."""
    user_key = await user_api_key_service.get_user_key(db, user.username, "gemini")
    return user_key or settings.gemini_api_key


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI Chatbot — streaming response (local Ollama or Gemini), otomatis
    grounded ke dokumen perusahaan jika relevan. Dokumen yang bisa diakses
    dibatasi sesuai departemen user (IT/Admin bebas akses semua departemen).
    """
    if request.provider not in ("onprem", "gemini"):
        raise HTTPException(400, 'Invalid provider — use "onprem" or "gemini"')

    is_unrestricted = user.has_any_role("it_staff", "admin")
    department_filter = rag_service.departments_for_roles(user.roles, is_unrestricted)
    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None

    service = AIService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user, department_filter, request.provider, gemini_key),
        media_type="text/event-stream",
    )


@router.post("/oracle-chat")
async def oracle_chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Oracle EBS Data Chat — streaming response (local Ollama or Gemini,
    tool-calling). The model picks a predefined, parameterized query
    (sales/production/budget/financial) instead of writing SQL itself; the
    query runs against Postgres EIS through a read-only DB role. See
    oracle_chat_service.py.
    """
    if request.provider not in ("onprem", "gemini"):
        raise HTTPException(400, 'Invalid provider — use "onprem" or "gemini"')

    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None

    service = OracleChatService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user, request.provider, gemini_key),
        media_type="text/event-stream",
    )


@router.post("/general-chat")
async def general_chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    General-purpose chat — streaming response (local Ollama or Gemini), no
    RAG retrieval, no tools. For questions outside company policy docs and
    Oracle ERP data.
    """
    if request.provider not in ("onprem", "gemini"):
        raise HTTPException(400, 'Invalid provider — use "onprem" or "gemini"')

    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None

    service = AIService()
    return StreamingResponse(
        service.stream_general_chat(request.message, request.conversation_history, user, request.provider, gemini_key),
        media_type="text/event-stream",
    )


@router.get("/status")
async def rag_status(user: CurrentUser = Depends(get_current_user)):
    return {"rag_configured": rag_service.is_configured(), "departments": rag_service.DEPARTMENTS}


@router.get("/documents")
async def list_documents(
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.HR, Roles.ACCOUNTING, Roles.PAC, Roles.PURCHASING, Roles.ADMIN)),
):
    if not rag_service.is_configured():
        raise HTTPException(400, "OLLAMA_API_URL belum diset — knowledge base belum aktif")
    return rag_service.list_documents()


@router.get("/documents/content")
async def get_document_content(
    source: str,
    title: str,
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.HR, Roles.ACCOUNTING, Roles.PAC, Roles.PURCHASING, Roles.ADMIN)),
):
    """Full concatenated text of a document's chunks — used by Document Converter's 'reopen for editing'."""
    content = rag_service.get_document_content(source, title)
    if content is None:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return {"content": content}


@router.post("/documents")
async def ingest_document(
    source: str = Form(...),
    title: str = Form(...),
    text: str = Form(""),
    department: str = Form("General"),
    file: UploadFile = File(None),
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.HR, Roles.ACCOUNTING, Roles.PAC, Roles.PURCHASING, Roles.ADMIN)),
):
    if department not in rag_service.DEPARTMENTS:
        raise HTTPException(400, f"Department harus salah satu dari: {', '.join(rag_service.DEPARTMENTS)}")
    if not rag_service.is_configured():
        raise HTTPException(400, "OLLAMA_API_URL belum diset di environment. Tambahkan dulu lalu restart backend.")

    content    = text.strip()
    from_file  = False
    file_name  = None
    used_ocr   = False

    if file is not None and file.filename:
        from_file = True
        file_name = file.filename
        ext = os.path.splitext(file.filename)[1].lower()
        raw = await file.read()
        tmp_path = os.path.join(_UPLOAD_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}")
        with open(tmp_path, "wb") as f:
            f.write(raw)
        try:
            if ext == ".pdf":
                import fitz
                import subprocess, shutil
                import os as _os
                # Force-set (not setdefault) — the Docker image's baked-in
                # TESSDATA_PREFIX targets Tesseract 4.x's path, but the image
                # actually ships Tesseract 5.x (tessdata moved to .../5/tessdata),
                # so setdefault alone is a no-op once the wrong value is already set.
                _os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/5/tessdata"
                doc = fitz.open(tmp_path)
                pages_text = []
                ocr_errors = []
                for page in doc:
                    text = page.get_text()
                    if not text.strip():
                        # Scanned/image PDF — try OCR via Tesseract
                        try:
                            # 300 dpi (not 200) — verified on a real scanned
                            # table that 200 dpi drops/garbles small table
                            # labels (e.g. "Manager" row read as noise
                            # fragments), while 300 dpi reads it correctly,
                            # for ~14% more time per page.
                            tp = page.get_textpage_ocr(dpi=300, language="ind+eng", full=True)
                            text = page.get_text(textpage=tp)
                            used_ocr = True
                        except Exception as ocr_err:
                            ocr_errors.append(str(ocr_err))
                    pages_text.append(text)
                doc.close()
                content = "\n".join(pages_text)
                if not content.strip() and ocr_errors:
                    # Expose OCR error so admin can diagnose
                    tess_path = shutil.which("tesseract") or "not found"
                    raise HTTPException(500, f"OCR gagal (tesseract: {tess_path}): {ocr_errors[0]}")
            elif ext in (".docx", ".doc"):
                import docx
                d = docx.Document(tmp_path)
                content = "\n".join(p.text for p in d.paragraphs)
            elif ext == ".txt":
                with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            else:
                raise HTTPException(400, f"Format file tidak didukung: {ext}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if not content.strip():
        detail = "Tidak ada teks yang berhasil diekstrak dari file."
        if from_file and file_name and file_name.lower().endswith(".pdf"):
            detail += " PDF ini mungkin merupakan file scan (image-only). Pastikan Tesseract OCR terinstall di server, atau konversi PDF ke format digital terlebih dahulu."
        raise HTTPException(400, detail)

    # OCR'd text loses paragraph structure (table cells/fragments often land
    # one-per-line), so a scanned PDF gets a larger chunk_size — keeps a
    # whole table's row labels and values more likely to land in the same
    # chunk instead of getting split apart at the default 700-char size.
    ingest_kwargs = {"chunk_size": 1500, "overlap": 200, "line_aware": True} if used_ocr else {}

    try:
        ids = await asyncio.wait_for(
            asyncio.to_thread(
                rag_service.ingest_text,
                source.strip(), title.strip(), content, user.username,
                department, from_file, file_name, **ingest_kwargs,
            ),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Timeout: server AI lokal tidak merespons dalam 40 detik. Periksa koneksi ke ai-engine (172.21.2.27).")
    except Exception as e:
        raise HTTPException(500, f"Gagal ingest dokumen: {str(e)}")

    return {
        "message":   f"Berhasil menyimpan {len(ids)} chunk dari dokumen '{title}'",
        "chunk_ids": ids,
        "from_file": from_file,
        "file_name": file_name,
    }


@router.delete("/documents")
async def delete_document(
    source: str,
    title: str,
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.HR, Roles.ACCOUNTING, Roles.PAC, Roles.PURCHASING, Roles.ADMIN)),
):
    rag_service.delete_document(source, title)
    return {"message": "Deleted"}


@router.delete("/documents/cleanup/text-only")
async def cleanup_text_only(
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.ADMIN)),
):
    """IT/Admin only: delete all knowledge base entries that came from text-paste (no real file)."""
    deleted = await asyncio.to_thread(rag_service.delete_text_only_documents)
    return {"message": f"Deleted {deleted} text-paste chunks from knowledge base", "deleted_chunks": deleted}


@router.delete("/documents/cleanup/all")
async def cleanup_all(
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.ADMIN)),
):
    """IT/Admin only: wipe the entire knowledge base."""
    deleted = await asyncio.to_thread(rag_service.delete_all_documents)
    return {"message": f"Knowledge base wiped — {deleted} chunks removed", "deleted_chunks": deleted}
