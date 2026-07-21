"""
Oracle EBS Data Chat — tool-calling over Postgres EIS

Two-step flow against the local Ollama server:
  1. Send the question + tool definitions (no tools executed yet) — the model
     decides which tool(s), if any, answer the question and with what
     arguments.
  2. Execute the chosen tool(s) against Postgres EIS (parameterized, via a
     read-only DB role — see eis_tools.py) and send the results back to the
     model for a final natural-language answer, which is streamed to the
     client exactly like the Policy Chat.

See sumber/AI_Chat_Implementation_Guide.md section 5.
"""
import json
import httpx
from app.config import get_settings
from app.services import eis_tools
import structlog

logger = structlog.get_logger()
settings = get_settings()

TOOL_SELECTION_TIMEOUT_SECONDS = 60.0
FINAL_ANSWER_TIMEOUT_SECONDS = 120.0

SYSTEM_PROMPT = (
    "Kamu adalah asisten data perusahaan PT CKD OTTO Pharmaceuticals bernama CKDO Data Assistant. "
    "Kamu menjawab pertanyaan tentang data penjualan, produksi, budget, dan keuangan perusahaan "
    "(sumber: Oracle EBS, sudah di-ETL ke data warehouse).\n\n"
    "## Aturan\n"
    "- SELALU gunakan tools yang tersedia untuk mengambil data. JANGAN PERNAH mengarang angka.\n"
    "- Anggap semua periode yang disebutkan user adalah periode data historis yang valid dan "
    "tersedia di sistem — jangan menolak dengan alasan 'periode di masa depan' atau semacamnya.\n"
    "- Jika user tidak menyebutkan periode, tanyakan periode mana yang dimaksud (format YYYY-MM) "
    "alih-alih menebak.\n"
    "- Setelah mendapat hasil data, jawab dalam Bahasa Indonesia yang natural — jangan hanya "
    "membalas mentahan JSON, susun jadi kalimat/insight yang mudah dibaca. Gunakan **bold** untuk "
    "angka kunci dan tabel markdown kalau membandingkan banyak baris.\n"
    "- Jika data yang diminta tidak ditemukan (list kosong), katakan terus terang tidak ada data "
    "untuk periode/filter tersebut — jangan mengarang.\n"
)


class OracleChatService:
    def __init__(self):
        self.base_url = settings.ollama_api_url.rstrip("/")
        self.model = settings.ollama_tool_model

    async def stream_chat(self, message: str, history: list[dict], user):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": message}]

        try:
            async with httpx.AsyncClient(timeout=TOOL_SELECTION_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": messages, "tools": eis_tools.EIS_TOOLS, "stream": False},
                )
                resp.raise_for_status()
                result = resp.json()
        except Exception as e:
            logger.error("oracle_tool_selection_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        assistant_msg = result.get("message", {})
        tool_calls = assistant_msg.get("tool_calls") or []
        sources = []

        if tool_calls:
            messages.append(assistant_msg)
            for call in tool_calls:
                fn = call.get("function", {})
                tool_name = fn.get("name")
                arguments = fn.get("arguments") or {}
                try:
                    data = eis_tools.execute_tool(tool_name, arguments)
                    error = None
                except Exception as e:
                    data = []
                    error = str(e)
                    logger.warning("oracle_tool_execution_error", tool=tool_name, arguments=arguments, error=error)

                sources.append({"tool": tool_name, "arguments": arguments, "row_count": len(data), "error": error})
                messages.append({
                    "role": "tool",
                    "content": json.dumps({"error": error} if error else {"data": data}, default=str),
                })

        # Final answer — streamed either way (with tool results in context, or
        # the model's own direct reply if it chose not to call a tool at all,
        # e.g. to ask a clarifying question about which period is meant).
        try:
            async with httpx.AsyncClient(timeout=FINAL_ANSWER_TIMEOUT_SECONDS) as client:
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
            logger.error("oracle_final_answer_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
