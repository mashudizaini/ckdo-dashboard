"""
AI Chatbot Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/chatbot
Required role: any authenticated user (chat) / any staff role (knowledge base)

Endpoints:
  POST   /chat                — Send message, get AI response (streaming, RAG-grounded)
  GET    /documents           — List ingested knowledge base documents
  POST   /documents           — Ingest a new document (paste text or upload file)
  DELETE /documents           — Delete a document by source+title
  GET    /status               — Whether RAG (Voyage AI) is configured
"""
import asyncio
import os
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.dependencies import get_current_user, require_role, CurrentUser, Roles
from app.services.ai_service import AIService
from app.services import rag_service

router = APIRouter()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "kb_tmp")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    AI Chatbot dengan Claude API — streaming response, otomatis grounded ke
    dokumen perusahaan jika relevan. Dokumen yang bisa diakses dibatasi sesuai
    departemen user (IT/Admin bebas akses semua departemen).
    """
    is_unrestricted = user.has_any_role("it_staff", "admin")
    department_filter = rag_service.departments_for_roles(user.roles, is_unrestricted)

    service = AIService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user, department_filter),
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
        raise HTTPException(400, "VOYAGE_API_KEY belum diset — knowledge base belum aktif")
    return rag_service.list_documents()


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
        raise HTTPException(400, "VOYAGE_API_KEY belum diset di environment. Tambahkan dulu lalu restart backend.")

    content = text.strip()

    if file is not None and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        raw = await file.read()
        tmp_path = os.path.join(_UPLOAD_DIR, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}")
        with open(tmp_path, "wb") as f:
            f.write(raw)
        try:
            if ext == ".pdf":
                import fitz
                doc = fitz.open(tmp_path)
                content = "\n".join(page.get_text() for page in doc)
                doc.close()
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
        raise HTTPException(400, "Tidak ada teks untuk di-ingest (isi text atau upload file)")

    try:
        ids = await asyncio.wait_for(
            asyncio.to_thread(
                rag_service.ingest_text, source.strip(), title.strip(), content, user.username, department
            ),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Timeout: Voyage AI tidak merespons dalam 40 detik. Periksa koneksi server ke api.voyageai.com")
    except Exception as e:
        raise HTTPException(500, f"Gagal ingest dokumen: {str(e)}")

    return {"message": f"Berhasil menyimpan {len(ids)} chunk dari dokumen '{title}'", "chunk_ids": ids}


@router.delete("/documents")
async def delete_document(
    source: str,
    title: str,
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.HR, Roles.ACCOUNTING, Roles.PAC, Roles.PURCHASING, Roles.ADMIN)),
):
    rag_service.delete_document(source, title)
    return {"message": "Deleted"}
