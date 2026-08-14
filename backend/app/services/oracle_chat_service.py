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
from app.services import gemini_service
import structlog

logger = structlog.get_logger()
settings = get_settings()

TOOL_SELECTION_TIMEOUT_SECONDS = 60.0
FINAL_ANSWER_TIMEOUT_SECONDS = 120.0

# The local model doesn't reliably follow a general "match the question's
# language" rule buried in the system prompt (verified: an Indonesian question
# still came back in English). Detecting the language ourselves and injecting
# an explicit, single-purpose instruction as the LAST message before the final
# generation call — closest to where the model actually writes its reply — is
# far more reliable for smaller local models than a rule stated once up front.
_INDONESIAN_HINTS = {
    "yang", "dan", "untuk", "dari", "dengan", "bagaimana", "apa", "apakah", "berapa",
    "ini", "itu", "adalah", "tidak", "saya", "kita", "kami", "bulan", "tahun", "periode",
    "bandingkan", "ringkasan", "kinerja", "penjualan", "produksi", "keuangan", "dibanding",
    "terhadap", "pada", "atau", "juga", "sudah", "belum", "bisa", "tolong", "mohon",
}


def _detect_language(text: str) -> str:
    words = {w.strip(".,?!:;()").lower() for w in text.split()}
    return "id" if words & _INDONESIAN_HINTS else "en"

SYSTEM_PROMPT = (
    "Kamu adalah asisten data perusahaan PT CKD OTTO Pharmaceuticals bernama CKDO Data Assistant. "
    "Kamu menjawab pertanyaan tentang data penjualan, COGS/margin per produk, produksi, budget, "
    "piutang & hutang usaha (AR/AP), persediaan (inventory), purchase order (PO), headcount dan "
    "daftar karyawan (department/team/posisi), dan keuangan perusahaan (sumber: Oracle EBS, sudah "
    "di-ETL ke data warehouse).\n\n"
    "## Aturan\n"
    "- SELALU gunakan tools yang tersedia untuk mengambil data. JANGAN PERNAH mengarang angka.\n"
    "- Anggap semua periode yang disebutkan user adalah periode data historis yang valid dan "
    "tersedia di sistem — jangan menolak dengan alasan 'periode di masa depan' atau semacamnya.\n"
    "- Jika user tidak menyebutkan periode, tanyakan periode mana yang dimaksud (format YYYY-MM) "
    "alih-alih menebak.\n"
    "- Jawab dalam bahasa yang SAMA dengan bahasa pertanyaan user: jika user bertanya dalam Bahasa "
    "Inggris, jawab dalam Bahasa Inggris; jika user bertanya dalam Bahasa Indonesia, jawab dalam "
    "Bahasa Indonesia. Ikuti bahasa pertanyaan TERBARU dari user, bukan bahasa pesan sebelumnya di "
    "percakapan ini.\n"
    "- Setelah mendapat hasil data, jawab dengan kalimat natural — jangan hanya membalas mentahan "
    "JSON, susun jadi kalimat/insight yang mudah dibaca. Gunakan **bold** untuk angka kunci dan "
    "tabel markdown kalau membandingkan banyak baris.\n"
    "- Jika data yang diminta tidak ditemukan (list kosong), katakan terus terang tidak ada data "
    "untuk periode/filter tersebut — jangan mengarang.\n"
)


class OracleChatService:
    def __init__(self):
        self.base_url = settings.ollama_api_url.rstrip("/")
        self.model = settings.ollama_tool_model

    async def stream_chat(self, message: str, history: list[dict], user, provider: str = "onprem", gemini_api_key: str = None):
        if provider == "gemini":
            async for chunk in self._stream_chat_gemini(message, history, user, gemini_api_key):
                yield chunk
            return

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

        # Explicit, single-purpose language directive — appended last so it's
        # the freshest instruction the model sees before writing its reply.
        lang = _detect_language(message)
        messages.append({
            "role": "system",
            "content": (
                "PENTING: Tulis balasan berikut dalam Bahasa Indonesia. Jangan gunakan Bahasa Inggris."
                if lang == "id" else
                "IMPORTANT: Write the following reply in English. Do not use Indonesian."
            ),
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

    async def _stream_chat_gemini(self, message: str, history: list[dict], user, gemini_api_key: str = None):
        contents = gemini_service.to_contents(history, message)

        try:
            step1 = await gemini_service.generate_with_tools(SYSTEM_PROMPT, contents, eis_tools.EIS_TOOLS, gemini_api_key)
        except Exception as e:
            logger.error("oracle_gemini_tool_selection_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        sources = []
        if step1["function_calls"]:
            # Must echo back the exact parts (including thoughtSignature) —
            # Gemini 3.x rejects the follow-up call otherwise.
            contents.append({"role": "model", "parts": step1["model_parts"]})
            for call in step1["function_calls"]:
                tool_name = call["name"]
                arguments = call["args"]
                try:
                    data = eis_tools.execute_tool(tool_name, arguments)
                    error = None
                except Exception as e:
                    data = []
                    error = str(e)
                    logger.warning("oracle_gemini_tool_execution_error", tool=tool_name, arguments=arguments, error=error)

                sources.append({"tool": tool_name, "arguments": arguments, "row_count": len(data), "error": error})
                contents.append(gemini_service.function_response_part(tool_name, call.get("id"), data, error))

        lang = _detect_language(message)
        final_system = SYSTEM_PROMPT + "\n\n" + (
            "PENTING: Tulis balasan berikut dalam Bahasa Indonesia. Jangan gunakan Bahasa Inggris."
            if lang == "id" else
            "IMPORTANT: Write the following reply in English. Do not use Indonesian."
        )

        try:
            async for text in gemini_service.stream_generate(final_system, contents, gemini_api_key):
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
        except Exception as e:
            logger.error("oracle_gemini_final_answer_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
