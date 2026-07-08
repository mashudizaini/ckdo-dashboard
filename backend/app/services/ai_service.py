"""
AI Service — Claude API wrapper with RAG (Retrieval Augmented Generation)

If Voyage AI is configured and relevant company documents are found,
answers are grounded in those documents (with cited sources). Otherwise
falls back to a plain Claude chat — the chatbot always works either way.
"""
import asyncio
import json
import anthropic
from app.config import get_settings
from app.services import rag_service
import structlog

logger = structlog.get_logger()
settings = get_settings()

RAG_TIMEOUT_SECONDS = 6.0


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def stream_chat(self, message: str, history: list[dict], user, department_filter: list[str] = None):
        """
        Stream chat response from Claude API as SSE, grounded in company docs when available.
        department_filter: list of departments the user may see (None = unrestricted, e.g. IT/Admin).
        """
        try:
            retrieval = await asyncio.wait_for(
                asyncio.to_thread(rag_service.retrieve_context, message, department_filter),
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
            "- Langsung ke inti jawaban — jangan awali dengan frasa basa-basi seperti "
            "\"Berdasarkan dokumen...\", \"Tentu saja!\", \"Baik, saya akan...\".\n"
            "- Jangan tutup jawaban dengan frasa generik seperti \"Jika ada pertanyaan lebih lanjut...\", "
            "\"Semoga membantu!\", atau sejenisnya.\n"
            "- Gunakan **bold** untuk istilah penting, tabel untuk data perbandingan, "
            "bullet/numbered list untuk langkah-langkah atau daftar — hanya jika memang membantu kejelasan.\n"
            "- Untuk pertanyaan singkat, jawab singkat dan padat. "
            "Untuk pertanyaan teknis atau prosedural, gunakan struktur yang jelas.\n"
            "- Gunakan Bahasa Indonesia yang natural dan profesional. "
            "Gunakan Bahasa Inggris hanya jika diminta atau untuk istilah teknis yang lebih tepat.\n"
            "- Fokus topik: Oracle EBS, produksi farmasi, HR, keuangan, purchasing, dan IT perusahaan.\n"
        )
        if department_filter is not None:
            base_system += (
                f"\nAkses dokumen user ini dibatasi pada departemen: **{', '.join(department_filter)}**. "
                "Jangan bocorkan isi dokumen departemen lain."
            )

        if context:
            system = (
                f"{base_system}\n\n"
                "## Dokumen Internal Perusahaan\n"
                "Gunakan dokumen berikut sebagai sumber utama jika relevan. "
                "Jika tidak relevan, jawab dari pengetahuan umum — jangan paksa mengutip dokumen yang tidak nyambung.\n\n"
                f"{context}"
            )
        else:
            system = base_system

        messages = history + [{"role": "user", "content": message}]

        with self.client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
