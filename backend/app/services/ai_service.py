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
import anthropic
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

    def _anthropic_complete(self, system: str, message: str) -> str:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text.strip()

    def _anthropic_complete_with_search(self, system: str, message: str, max_tokens: int = 8192) -> str:
        """Same as _anthropic_complete but with the web_search server-side
        tool enabled, on the current flagship model — for grounding a
        response in current information instead of training-data-only
        knowledge. Web search runs entirely server-side (Claude decides
        when to search and reads the results itself), so this is still a
        single request/response, not a client-side tool loop — except for
        the rare case where Claude's internal search loop pauses mid-turn
        (stop_reason "pause_turn"), which we resume automatically.
        Response content interleaves a pre-search narration text block
        ("I'll search for that."), server_tool_use/tool_result blocks, and
        THEN the actual answer — itself possibly split across several
        trailing text blocks (empirically confirmed against the live API,
        not assumed). So: find the last non-text block and join every text
        block after it — that's the answer with the narration excluded,
        without assuming it's a single block."""
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages = [{"role": "user", "content": message}]
        # Unbounded, a "ground everything" prompt drove Claude to 35 searches
        # and 5.5 minutes on one measured run — way past any reasonable HTTP
        # request lifetime. Capping max_uses bounds worst-case latency while
        # still allowing solid grounding across a handful of key figures.
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
        response = None
        for _ in range(3):
            response = client.messages.create(
                model="claude-opus-5",
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
            if response.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": response.content}]
        last_tool_idx = -1
        for i, block in enumerate(response.content):
            if block.type != "text":
                last_tool_idx = i
        answer_blocks = [b.text for b in response.content[last_tool_idx + 1:] if b.type == "text"]
        return "".join(answer_blocks).strip()

    def _anthropic_complete_with_search_history(self, system: str, history: list[dict], message: str, max_tokens: int = 8192) -> str:
        """Same web-search grounding as _anthropic_complete_with_search, but
        carries prior conversation turns too — General Chat's Claude option
        needs history the same way the other 2 providers there already get
        it, unlike the single-shot batch-report caller
        _anthropic_complete_with_search was built for. Deliberately a
        separate method rather than adding a history param to that one, to
        avoid touching the already-working PAC Business Plan Outlook path
        that calls it today."""
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages = [
            {"role": m.get("role") if m.get("role") in ("user", "assistant") else "user", "content": m.get("content", "")}
            for m in history if m.get("content")
        ] + [{"role": "user", "content": message}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
        response = None
        for _ in range(3):
            response = client.messages.create(
                model="claude-opus-5", max_tokens=max_tokens, system=system, messages=messages, tools=tools,
            )
            if response.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": response.content}]
        last_tool_idx = -1
        for i, block in enumerate(response.content):
            if block.type != "text":
                last_tool_idx = i
        answer_blocks = [b.text for b in response.content[last_tool_idx + 1:] if b.type == "text"]
        return "".join(answer_blocks).strip()

    async def complete(self, system: str, message: str, num_ctx: int = 8192, provider: str = "onprem", gemini_api_key: str = None, web_search: bool = False) -> str:
        """One-shot, non-streaming completion — for batch/background tasks
        (e.g. summarizing an uploaded reference file into a structured
        brief, or generating the Outlook write-up) that just need the final
        text, not token-by-token SSE. provider: "onprem" (local Ollama,
        default), "gemini", or "anthropic" (Claude — shared company key
        only, same as the other Claude-backed tools in this app).
        web_search: only meaningful with provider="anthropic" — grounds the
        response in live web search results via Claude's server-side tool."""
        if provider == "gemini":
            contents = [{"role": "user", "parts": [{"text": message}]}]
            return await gemini_service.generate(system, contents, gemini_api_key)

        if provider == "anthropic":
            # anthropic's SDK is sync-only; run off the event loop thread
            # like meeting_notes_service's Claude path does.
            if web_search:
                return await asyncio.to_thread(self._anthropic_complete_with_search, system, message)
            return await asyncio.to_thread(self._anthropic_complete, system, message)

        messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
        async with httpx.AsyncClient(timeout=OLLAMA_CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False, "options": {"num_ctx": num_ctx}},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            return data.get("message", {}).get("content", "")

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

            "Fokus topik: Oracle EBS, produksi farmasi, HR (termasuk training, benefit, cuti, "
            "perjalanan dinas), keuangan, purchasing, dan IT perusahaan.\n"
        )
        if department_filter is not None:
            base_system += (
                f"\nAkses dokumen user dibatasi pada departemen: **{', '.join(department_filter)}**. "
                "Jangan bocorkan isi dokumen departemen lain."
            )

        if context:
            # This whole "reason from documents, don't say unavailable"
            # block only makes sense when there IS retrieved context to
            # reason from — it used to be part of base_system unconditionally,
            # which meant an empty-KB query still got told "never say info
            # isn't available, reason your way to a conclusion" with nothing
            # to reason from, inviting exactly the kind of confident,
            # specific-sounding hallucination (a fabricated allowance amount)
            # that made this worth fixing.
            system = (
                f"{base_system}\n\n"
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
                "## Dokumen Internal yang Tersedia\n"
                "Gunakan dokumen berikut sebagai sumber utama. "
                "Nalar dari seluruh konteks yang ada — "
                "meski kata-katanya berbeda dari pertanyaan, cari hubungan semantiknya.\n\n"
                f"{context}"
            )
        else:
            # No relevant document was retrieved (empty/irrelevant Knowledge
            # Base, or the search simply found nothing above the similarity
            # threshold for this query). The opposite instruction from
            # above: be explicit that fabricating a specific-sounding
            # company fact (an amount, a policy detail) here would be a
            # hallucination, not a confident answer.
            system = (
                f"{base_system}\n\n"
                "## Tidak Ada Dokumen Relevan Ditemukan\n"
                "Pencarian di Knowledge Base tidak menemukan dokumen internal yang relevan dengan "
                "pertanyaan ini. JANGAN mengarang atau menebak angka, kebijakan, atau fakta spesifik "
                "perusahaan (nominal tunjangan, cuti, budget, prosedur, dll) — itu bisa salah dan "
                "menyesatkan pengguna. Katakan dengan jujur bahwa informasi ini belum tersedia di "
                "Knowledge Base internal, dan sarankan user menghubungi departemen terkait atau "
                "mengunggah dokumen yang relevan. Kamu tetap boleh membantu untuk pertanyaan umum di "
                "luar data spesifik perusahaan (mis. penjelasan konsep umum, cara pakai sistem)."
            )

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
        elif provider == "anthropic":
            # Shared company key only (no per-user override) — matches the
            # convention already established by _anthropic_complete/
            # _anthropic_complete_with_search above, not something new
            # introduced here.
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            anthropic_history = [
                {"role": m.get("role") if m.get("role") in ("user", "assistant") else "user", "content": m.get("content", "")}
                for m in history if m.get("content")
            ]
            try:
                async with client.messages.stream(
                    model="claude-opus-5",
                    max_tokens=4096,
                    system=system,
                    messages=anthropic_history + [{"role": "user", "content": message}],
                ) as stream:
                    async for text in stream.text_stream:
                        yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
            except Exception as e:
                logger.error("anthropic_stream_error", error=str(e))
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
        elif provider == "anthropic":
            # Unlike Policy/Oracle Chat, General Chat's Claude option grounds
            # every answer in live web search (Claude's server-side
            # web_search tool — same mechanism PAC's Business Plan Outlook
            # already uses) instead of plain model knowledge, since General
            # Chat has no other grounding (no RAG/tools) and this is the one
            # mode in this app's interactive chatbot that can answer with
            # genuinely current information rather than being capped at
            # training-data knowledge. Not true token-by-token streaming —
            # web search is a multi-step server-side process (Claude decides
            # what to search, reads results, then answers), so the full
            # answer arrives as one chunk once it's ready rather than
            # progressively like the other 2 providers.
            try:
                text = await asyncio.to_thread(
                    self._anthropic_complete_with_search_history, GENERAL_CHAT_SYSTEM_PROMPT, history, message
                )
                yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
            except Exception as e:
                logger.error("anthropic_general_chat_error", error=str(e))
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
