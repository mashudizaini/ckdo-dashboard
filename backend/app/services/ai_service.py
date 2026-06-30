"""
AI Service — Claude API wrapper with RAG (Retrieval Augmented Generation)

If Voyage AI is configured and relevant company documents are found,
answers are grounded in those documents (with cited sources). Otherwise
falls back to a plain Claude chat — the chatbot always works either way.
"""
import json
import anthropic
from app.config import get_settings
from app.services import rag_service
import structlog

logger = structlog.get_logger()
settings = get_settings()


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def stream_chat(self, message: str, history: list[dict], user):
        """Stream chat response from Claude API as SSE, grounded in company docs when available."""
        import asyncio

        retrieval = await asyncio.to_thread(rag_service.retrieve_context, message)
        context = retrieval["context"]
        sources = retrieval["sources"]

        base_system = (
            f"Kamu adalah asisten AI internal PT CKD OTTO Pharmaceuticals. "
            f"User: {user.full_name} ({', '.join(user.roles)}). "
            "Jawab dalam Bahasa Indonesia kecuali diminta selainnya. "
            "Fokus pada topik pekerjaan: Oracle EBS, produksi farmasi, HR, keuangan, dan IT."
        )

        if context:
            system = (
                f"{base_system}\n\n"
                "Kamu punya akses ke dokumen internal perusahaan di bawah ini. "
                "Gunakan dokumen ini sebagai sumber utama jika relevan dengan pertanyaan. "
                "Jika dokumen tidak relevan dengan pertanyaan, jawab berdasarkan pengetahuan umum saja "
                "dan jangan paksakan mengutip dokumen yang tidak nyambung.\n\n"
                f"Dokumen internal:\n\n{context}"
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
