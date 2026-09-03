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
"onprem" (default, local Ollama), "gemini" (Google Gemini API), or —
/chat and /general-chat only — "anthropic" (Claude — shared company key by
default, on claude-sonnet-5; or the user's own key + model choice if set
via My API Key, see user_api_key_service.ALLOWED_MODELS).
/oracle-chat doesn't support "anthropic" yet — it's a tool-calling pipeline
with its own separate Ollama/Gemini implementations (see
oracle_chat_service.py); adding Claude there means building a third
tool-calling path against Anthropic's own tool-use API, not just this
plain-chat wiring.

General Chat's "anthropic" and "gemini" both additionally ground every
answer in that provider's own live web search (Claude's web_search tool,
see ai_service.py's _anthropic_complete_with_search_history; Gemini's
Google Search grounding tool, see gemini_service.stream_generate_grounded)
— the two modes in this interactive chatbot that aren't capped at a
model's training-data cutoff. "onprem" in General Chat has no such
grounding (pure model knowledge only).
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
from app.services import ai_chat_provider_service

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


async def _ensure_provider_enabled(db: AsyncSession, provider: str):
    if not await ai_chat_provider_service.is_provider_enabled(db, provider):
        label = ai_chat_provider_service.PROVIDERS.get(provider, provider)
        raise HTTPException(403, f"{label} is currently disabled for the AI Chatbot — ask IT to re-enable it in Setup > AI.")


async def _resolve_anthropic(db: AsyncSession, user: CurrentUser) -> tuple[str | None, str | None]:
    """(api_key, model) from the user's own saved Claude key/model preference
    (see My API Key), or (None, None) to fall back to the shared company key
    and default chat model — mirrors _resolve_gemini_key but returns None
    instead of the shared key so ai_service can distinguish "no override"
    from "here's the key to use", since unlike Gemini the model choice also
    needs to fall through independently."""
    row_key = await user_api_key_service.get_user_key(db, user.username, "anthropic")
    if not row_key:
        return None, None
    model = await user_api_key_service.get_user_model(db, user.username, "anthropic")
    return row_key, model


@router.get("/provider-status")
async def get_provider_status(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Which of the 3 chat providers are currently enabled — any
    authenticated user (the chatbot's own provider dropdown needs this to
    decide what to show)."""
    return await ai_chat_provider_service.list_provider_status(db)


class ProviderStatusUpdate(BaseModel):
    enabled: bool


@router.put("/provider-status/{provider}")
async def set_provider_status(
    provider: str,
    body: ProviderStatusUpdate,
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """IT/admin only — a usage/cost control lever, see ai_chat_provider_service.py."""
    if provider not in ai_chat_provider_service.PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {provider}")
    await ai_chat_provider_service.set_provider_enabled(db, provider, body.enabled, user.username)
    return await ai_chat_provider_service.list_provider_status(db)


@router.get("/default-providers")
async def get_default_providers(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Which provider each of the 3 chat modes (Policy/Oracle/General)
    starts on — any authenticated user (Chatbot.jsx/ChatWidget.jsx read
    this on mount instead of a hardcoded default)."""
    return await ai_chat_provider_service.list_default_providers(db)


class DefaultProviderUpdate(BaseModel):
    provider: str


@router.put("/default-providers/{mode}")
async def set_default_provider(
    mode: str,
    body: DefaultProviderUpdate,
    user: CurrentUser = Depends(require_role(Roles.IT, Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """IT/admin only — see ai_chat_provider_service.py."""
    if mode not in ai_chat_provider_service.MODES:
        raise HTTPException(400, f"Unknown chat mode: {mode}")
    if body.provider not in ai_chat_provider_service.PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    await ai_chat_provider_service.set_default_provider(db, mode, body.provider, user.username)
    return await ai_chat_provider_service.list_default_providers(db)


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI Chatbot — streaming response (local Ollama, Gemini, or Claude),
    otomatis grounded ke dokumen perusahaan jika relevan. Dokumen yang bisa
    diakses dibatasi sesuai departemen user (IT/Admin bebas akses semua departemen).
    """
    if request.provider not in ("onprem", "gemini", "anthropic"):
        raise HTTPException(400, 'Invalid provider — use "onprem", "gemini", or "anthropic"')
    await _ensure_provider_enabled(db, request.provider)

    is_unrestricted = user.has_any_role("it_staff", "admin")
    department_filter = rag_service.departments_for_roles(user.roles, is_unrestricted)
    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None
    anthropic_key, anthropic_model = await _resolve_anthropic(db, user) if request.provider == "anthropic" else (None, None)

    service = AIService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user, department_filter, request.provider, gemini_key, anthropic_key, anthropic_model),
        media_type="text/event-stream",
    )


@router.post("/oracle-chat")
async def oracle_chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Oracle EBS Data Chat — streaming response (local Ollama, Gemini, or
    Claude — tool-calling). The model picks a predefined, parameterized
    query (sales/production/budget/financial) instead of writing SQL
    itself; the query runs against Postgres EIS through a read-only DB
    role. See oracle_chat_service.py — each provider has its own
    tool-calling implementation there (Ollama/OpenAI-style, Gemini
    functionDeclarations, Anthropic tool_use/tool_result blocks).
    """
    if request.provider not in ("onprem", "gemini", "anthropic"):
        raise HTTPException(400, 'Invalid provider — use "onprem", "gemini", or "anthropic"')
    await _ensure_provider_enabled(db, request.provider)

    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None
    anthropic_key, anthropic_model = await _resolve_anthropic(db, user) if request.provider == "anthropic" else (None, None)

    service = OracleChatService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user, request.provider, gemini_key, anthropic_key, anthropic_model),
        media_type="text/event-stream",
    )


@router.post("/general-chat")
async def general_chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    General-purpose chat — streaming response (local Ollama, Gemini, or
    Claude), no RAG retrieval, no tools. For questions outside company
    policy docs and Oracle ERP data. provider="anthropic" here is grounded
    in live web search (see ai_service.py) — the only mode in this app's
    interactive chatbot that isn't capped at a training-data cutoff.
    """
    if request.provider not in ("onprem", "gemini", "anthropic"):
        raise HTTPException(400, 'Invalid provider — use "onprem", "gemini", or "anthropic"')
    await _ensure_provider_enabled(db, request.provider)

    gemini_key = await _resolve_gemini_key(db, user) if request.provider == "gemini" else None
    anthropic_key, anthropic_model = await _resolve_anthropic(db, user) if request.provider == "anthropic" else (None, None)

    service = AIService()
    return StreamingResponse(
        service.stream_general_chat(request.message, request.conversation_history, user, request.provider, gemini_key, anthropic_key, anthropic_model),
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
    deleted = await asyncio.to_thread(rag_service.delete_document, source, title)
    if deleted == 0:
        raise HTTPException(404, f"No document matched source={source!r} title={title!r} — nothing was deleted.")
    return {"message": f"Deleted {deleted} chunk(s)"}


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
