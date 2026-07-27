"""
AI Service — local Ollama wrapper with RAG (Retrieval Augmented Generation)

If relevant company documents are found via RAG, answers are grounded in
those documents (with cited sources). Otherwise falls back to a plain
chat — the chatbot always works either way.

Chat completion and RAG retrieval both run on the local "ai-engine" Ollama
server (172.21.2.27) instead of paid APIs — see
sumber/AI_Chat_Implementation_Guide.md (chat: qwen2.5, embeddings: nomic-embed-text).
"""
import asyncio
import json
import httpx
from app.config import get_settings
from app.services import rag_service
from app.services import gemini_service
import structlog

logger = structlog.get_logger()
settings = get_settings()

RAG_TIMEOUT_SECONDS = 6.0
OLLAMA_CHAT_TIMEOUT_SECONDS = 120.0

GENERAL_CHAT_SYSTEM_PROMPT = (
    "Kamu adalah asisten AI internal PT CKD OTTO Pharmaceuticals bernama CKDO Assistant, "
    "untuk pertanyaan umum sehari-hari (di luar kebijakan perusahaan spesifik dan data ERP Oracle "
    "— untuk itu ada mode chat terpisah).\n\n"
    "## Gaya Jawaban\n"
    "- Langsung ke inti — jangan awali dengan basa-basi seperti \"Tentu!\", \"Baik saya akan...\".\n"
    "- Gunakan **bold** untuk istilah kunci, tabel untuk perbandingan multi-kolom, list untuk "
    "langkah-langkah. Pakai format hanya jika benar-benar membantu kejelasan.\n"
    "- Pertanyaan singkat -> jawab singkat.\n"
    "- Balas dalam bahasa yang SAMA dengan bahasa pertanyaan user: Bahasa Indonesia -> jawab dalam "
    "Bahasa Indonesia; Bahasa Inggris -> jawab dalam Bahasa Inggris.\n"
)


class AIService:
    def __init__(self):
        self.base_url = settings.ollama_api_url.rstrip("/")
        self.model = settings.ollama_chat_model

    async def stream_chat(self, message: str, history: list[dict], user, department_filter: list[str] = None, provider: str = "onprem", gemini_api_key: str = None):
        """
        Stream chat response from the local Ollama server as SSE, grounded in company docs when available.
        department_filter: list of departments the user may see (None = unrestricted, e.g. IT/Admin).
        """
        # The local qwen2.5:14b model reliably uses up to ~16 sources in
        # context but degrades (or outright hallucinates a wrong number
        # pulled from an unrelated chunk) past ~18 — validated empirically.
        # Gemini handles the full top_k=30 fine. DB search stays broad either
        # way (top_k=30 default) for recall; only the prompt content differs.
        context_k = 16 if provider == "onprem" else 30
        try:
            retrieval = await asyncio.wait_for(
                asyncio.to_thread(rag_service.retrieve_context, message, department_filter, 30, 0.15, context_k),
                timeout=RAG_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("rag_retrieval_timeout", message=message[:80])
            retrieval = {"context": None, "sources": []}
        except Exception as e:
            logger.warning("rag_retrieval_error", error=str(e))
            retrieval = {"context": None, "sources": []}

        context = retrieval["context"]
        sources = retrieval["sources"]

        base_system = (
            f"Kamu adalah asisten AI internal PT CKD OTTO Pharmaceuticals bernama CKDO Intelligence. "
            f"Sedang berbicara dengan: {user.full_name} ({', '.join(user.roles)}).\n\n"

            "## Gaya Jawaban\n"
            "- Langsung ke inti — jangan awali dengan basa-basi seperti \"Berdasarkan dokumen...\", "
            "\"Tentu!\", \"Baik saya akan...\".\n"
            "- Jangan tutup dengan frasa generik \"Jika ada pertanyaan...\", \"Semoga membantu!\", dll.\n"
            "- Gunakan **bold** untuk angka/istilah kunci, tabel untuk perbandingan multi-kolom, "
            "list untuk langkah-langkah. Pakai format hanya jika benar-benar membantu kejelasan.\n"
            "- Pertanyaan singkat → jawab singkat. Pertanyaan prosedural/policy → jawab dengan struktur lengkap.\n"
            "- Balas dalam bahasa yang SAMA dengan bahasa pertanyaan user: user bertanya dalam Bahasa "
            "Indonesia → jawab dalam Bahasa Indonesia profesional; user bertanya dalam Bahasa Inggris → "
            "jawab dalam Bahasa Inggris. Jika bahasa pertanyaan tidak jelas (mis. hanya angka/kode), "
            "default ke Bahasa Inggris. Istilah teknis boleh tetap dalam Bahasa Inggris di kedua kasus.\n\n"

            "## Cara Menalar dari Dokumen\n"
            "- Pertanyaan user sering menggunakan kata berbeda dari yang ada di dokumen. "
            "Kenali MAKSUD pertanyaan, bukan hanya kata-katanya. Contoh:\n"
            "  · \"biaya yang diperbolehkan\" = bisa berarti \"plafon\", \"budget\", \"amount\", \"limit\"\n"
            "  · \"level manager\" = bisa berarti baris dengan kata Manager/Manajer di tabel\n"
            "  · \"training\" = bisa ada di tabel Approval Matrix, Budget Policy, SOP, dll.\n"
            "- Jika dokumen berisi TABEL atau MATRIKS yang relevan, ekstrak dan tampilkan SELURUH "
            "isi yang berkaitan — jangan hanya sebagian.\n"
            "- Jika informasi tersebar di beberapa bagian dokumen, GABUNGKAN menjadi jawaban yang koheren.\n"
            "- Jika dokumen menyebut kondisi, pengecualian, atau catatan penting terkait topik — sertakan.\n"
            "- JANGAN menjawab 'informasi tidak tersedia' atau 'tidak tercantum' selama konteks dokumen "
            "masih mengandung data yang relevan, meski tidak persis sama kata-katanya. "
            "Gunakan nalar untuk menyimpulkan dan jelaskan dari mana kesimpulan itu berasal.\n"
            "- Hanya katakan 'tidak ada informasi' jika setelah bernalar dengan cermat, "
            "dokumen memang benar-benar tidak memiliki informasi yang relevan sama sekali.\n\n"

            "Fokus topik: Oracle EBS, produksi farmasi, HR (termasuk training, benefit, cuti, "
            "perjalanan dinas), keuangan, purchasing, dan IT perusahaan.\n"
        )
        if department_filter is not None:
            base_system += (
                f"\nAkses dokumen user dibatasi pada departemen: **{', '.join(department_filter)}**. "
                "Jangan bocorkan isi dokumen departemen lain."
            )

        if context:
            system = (
                f"{base_system}\n\n"
                "## Dokumen Internal yang Tersedia\n"
                "Gunakan dokumen berikut sebagai sumber utama. "
                "Nalar dari seluruh konteks yang ada — "
                "meski kata-katanya berbeda dari pertanyaan, cari hubungan semantiknya.\n\n"
                f"{context}"
            )
        else:
            system = base_system

        # The SSE response has already committed a 200 OK by the time this
        # generator runs (StreamingResponse sends headers before iterating
        # the body), so an unhandled exception here doesn't become a clean
        # HTTP error — it just drops the connection mid-stream and the
        # browser reports it to fetch() as an opaque "network error" with no
        # indication of what went wrong. Catch it and emit a proper SSE
        # error event so the frontend can show a real message instead.
        if provider == "gemini":
            contents = gemini_service.to_contents(history, message)
            try:
                async for text in gemini_service.stream_generate(system, contents, gemini_api_key):
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
            except Exception as e:
                logger.error("gemini_stream_error", error=str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
                return
        else:
            # Ollama takes the system prompt as a regular message in the list
            # (unlike Anthropic/Gemini, which have a separate top-level `system` param).
            messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
            try:
                async with httpx.AsyncClient(timeout=OLLAMA_CHAT_TIMEOUT_SECONDS) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/api/chat",
                        json={"model": self.model, "messages": messages, "stream": True},
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            chunk = json.loads(line)
                            if chunk.get("error"):
                                raise RuntimeError(chunk["error"])
                            text = chunk.get("message", {}).get("content", "")
                            if text:
                                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
                            if chunk.get("done"):
                                break
            except Exception as e:
                logger.error("ollama_stream_error", error=str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
                return

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"

    async def stream_general_chat(self, message: str, history: list[dict], user, provider: str = "onprem", gemini_api_key: str = None):
        """
        General-purpose chat — no RAG retrieval, no tools. Simplest of the
        3 chat modes; for questions that aren't about company policy docs
        or Oracle ERP data.
        """
        if provider == "gemini":
            contents = gemini_service.to_contents(history, message)
            try:
                async for text in gemini_service.stream_generate(GENERAL_CHAT_SYSTEM_PROMPT, contents, gemini_api_key):
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
            except Exception as e:
                logger.error("gemini_general_chat_error", error=str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
                return
        else:
            messages = [{"role": "system", "content": GENERAL_CHAT_SYSTEM_PROMPT}] + history + [{"role": "user", "content": message}]
            try:
                async with httpx.AsyncClient(timeout=OLLAMA_CHAT_TIMEOUT_SECONDS) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/api/chat",
                        json={"model": self.model, "messages": messages, "stream": True},
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            chunk = json.loads(line)
                            if chunk.get("error"):
                                raise RuntimeError(chunk["error"])
                            text = chunk.get("message", {}).get("content", "")
                            if text:
                                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
                            if chunk.get("done"):
                                break
            except Exception as e:
                logger.error("ollama_general_chat_error", error=str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
                return

        yield "data: [DONE]\n\n"
