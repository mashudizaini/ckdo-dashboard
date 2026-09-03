"""
Oracle EBS Data Chat — tool-calling over Postgres EIS

Same two-step flow for all 3 providers (onprem/Ollama, Gemini, Claude):
  1. Send the question + tool definitions (no tools executed yet) — the model
     decides which tool(s), if any, answer the question and with what
     arguments.
  2. Execute the chosen tool(s) against Postgres EIS (parameterized, via a
     read-only DB role — see eis_tools.py) and send the results back to the
     model for a final natural-language answer, which is streamed to the
     client exactly like the Policy Chat.

Each provider's tool-calling API has its own shape (Ollama/OpenAI-style for
onprem, Gemini's functionDeclarations, Anthropic's tool_use/tool_result
content blocks), so each gets its own _stream_chat_* method below rather
than a shared abstraction — the two steps above are the only thing they
share.

See sumber/AI_Chat_Implementation_Guide.md section 5.
"""
import json
import httpx
import anthropic
from app.config import get_settings
from app.services import eis_tools
from app.services import gemini_service
from app.services.ai_service import ANTHROPIC_CHAT_DEFAULT_MODEL
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


def _to_anthropic_tools(ollama_tools: list[dict]) -> list[dict]:
    """EIS_TOOLS' Ollama/OpenAI-style {"type":"function","function":{"name",
    "description","parameters"}} -> Anthropic's {"name","description",
    "input_schema"} — a straight field rename, no case conversion needed
    (unlike gemini_service.to_gemini_tools(), Claude uses the same
    lowercase JSON-schema types already in EIS_TOOLS)."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
        }
        for t in ollama_tools
    ]

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
    "- PENTING soal satuan nilai uang dari tools — DUA konvensi berbeda, jangan tertukar: "
    "get_sales_order_detail dan get_purchase_order_detail (amount_idr/unit_price_idr) sudah dalam "
    "RUPIAH PENUH (raw IDR) — JANGAN dikalikan atau dianggap 'juta'. Semua tool LAINNYA "
    "(get_sales_performance, get_purchasing_performance, get_cogs_performance, get_budget_vs_actual, "
    "get_financial_summary, get_ar_ap_summary, get_inventory_summary) mengembalikan nilai dalam JUTA "
    "IDR. Kalau ragu tool mana yang dipakai, cek nama tool di hasil sebelumnya.\n"
    "- Pilih SATU satuan yang paling jelas dan sebutkan sekali saja — JANGAN tulis dua satuan "
    "berdampingan untuk angka yang sama (mis. '92.804,82 juta atau sekitar Rp 92,8 miliar' "
    "membingungkan karena format ribuan Indonesia '92.804' terlihat seperti angka lain, padahal itu "
    "92 ribu lebih). Untuk tool yang mengembalikan JUTA IDR: kalau nilainya ≥ 1.000 juta, konversi "
    "ke miliar dan tulis HANYA itu (mis. 'Rp 92,8 miliar'); kalau < 1.000 juta, tulis dalam juta "
    "(mis. 'Rp 691,9 juta'). Untuk tool yang mengembalikan RUPIAH PENUH: konversi sendiri ke juta/"
    "miliar untuk keterbacaan (mis. 12.798.771.975 ditulis 'Rp 12,8 miliar'), jangan tampilkan digit "
    "penuh mentah-mentah kecuali diminta persis.\n"
    "- Jika data yang diminta tidak ditemukan (list kosong), katakan terus terang tidak ada data "
    "untuk periode/filter tersebut — jangan mengarang.\n"
)


class OracleChatService:
    def __init__(self):
        self.base_url = settings.ollama_api_url.rstrip("/")
        self.model = settings.ollama_tool_model

    async def stream_chat(
        self, message: str, history: list[dict], user, provider: str = "onprem",
        gemini_api_key: str = None, anthropic_api_key: str = None, anthropic_model: str = None,
    ):
        if provider == "gemini":
            async for chunk in self._stream_chat_gemini(message, history, user, gemini_api_key):
                yield chunk
            return
        if provider == "anthropic":
            async for chunk in self._stream_chat_anthropic(message, history, user, anthropic_api_key, anthropic_model):
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
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
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
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
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
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
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
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"

    async def _stream_chat_anthropic(
        self, message: str, history: list[dict], user,
        anthropic_api_key: str = None, anthropic_model: str = None,
    ):
        client = anthropic.AsyncAnthropic(api_key=anthropic_api_key or settings.anthropic_api_key)
        model = anthropic_model or ANTHROPIC_CHAT_DEFAULT_MODEL
        messages = [
            {"role": m.get("role") if m.get("role") in ("user", "assistant") else "user", "content": m.get("content", "")}
            for m in history if m.get("content")
        ] + [{"role": "user", "content": message}]

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=_to_anthropic_tools(eis_tools.EIS_TOOLS),
            )
        except Exception as e:
            logger.error("oracle_anthropic_tool_selection_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
            yield "data: [DONE]\n\n"
            return

        sources = []
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if tool_use_blocks:
            # Echo the assistant turn back verbatim (text + tool_use blocks) —
            # same pattern ai_service.py's web-search pause/resume loop already
            # relies on for replaying response.content into the next turn.
            messages.append({"role": "assistant", "content": response.content})
            tool_result_blocks = []
            for block in tool_use_blocks:
                tool_name = block.name
                arguments = block.input
                try:
                    data = eis_tools.execute_tool(tool_name, arguments)
                    error = None
                except Exception as e:
                    data = []
                    error = str(e)
                    logger.warning("oracle_anthropic_tool_execution_error", tool=tool_name, arguments=arguments, error=error)

                sources.append({"tool": tool_name, "arguments": arguments, "row_count": len(data), "error": error})
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"error": error} if error else {"data": data}, default=str),
                })
            messages.append({"role": "user", "content": tool_result_blocks})

        lang = _detect_language(message)
        final_system = SYSTEM_PROMPT + "\n\n" + (
            "PENTING: Tulis balasan berikut dalam Bahasa Indonesia. Jangan gunakan Bahasa Inggris."
            if lang == "id" else
            "IMPORTANT: Write the following reply in English. Do not use Indonesian."
        )

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=final_system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
        except Exception as e:
            logger.error("oracle_anthropic_final_answer_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
