"""
AI Service — Claude API wrapper
"""
import anthropic
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def stream_chat(self, message: str, history: list[dict], user):
        """Stream chat response dari Claude API sebagai SSE."""
        messages = history + [{"role": "user", "content": message}]
        system = (
            f"Kamu adalah asisten AI internal PT CKD OTTO Pharmaceuticals. "
            f"User: {user.full_name} ({', '.join(user.roles)}). "
            "Jawab dalam Bahasa Indonesia kecuali diminta selainnya. "
            "Fokus pada topik pekerjaan: Oracle EBS, produksi farmasi, HR, keuangan, dan IT."
        )
        with self.client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"
