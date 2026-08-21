"""
Document Converter — Translation Service
─────────────────────────────────────────
Translates the structured block list (see document_converter_service.
extract_blocks) from Korean/English source text into English and/or
Indonesian, batched ~50 strings per call with a shared glossary injected
into every prompt so terminology stays consistent across every document
translated through this tool (see document_glossary.py) — a human
correcting one glossary row fixes it for every future translation.

Table cells are translated in place, staying at their original row/column
position in the block list — nothing is flattened through Markdown and
reflowed mid-pipeline, which is the failure mode
sumber/Panduan_Konversi_dan_Terjemahan_Dokumen_KO.md opens with.

Provider dispatch (onprem/gemini/anthropic/openai/kimi) is a copy-adapt of
meeting_notes_service.py's generate_mom() — deliberately not refactored
into a shared helper, to avoid touching that already-working code path for
an unrelated feature. Same api_key convention: the router resolves the
calling user's own saved key (user_api_key_service) and passes it in here,
falling back to the shared company key per-provider when absent.
"""
import hashlib
import json
import re

import anthropic
import httpx

from app.config import get_settings
from app.services import gemini_service

settings = get_settings()

CLOUD_TIMEOUT_SECONDS = 120.0
OLLAMA_TIMEOUT_SECONDS = 120.0
MAX_OUTPUT_TOKENS = 8192
# 40-60 per the guide's own recommendation — small enough the model doesn't
# drop items in the middle, large enough not to burn overhead on tiny calls.
BATCH_SIZE = 50

TARGET_LABEL = {"en": "English", "id": "Indonesian"}

SYSTEM_PROMPT_TEMPLATE = """You translate corporate/technical documents (Korean or English source) into {target_label}.

Rules:
- Translate each item as a standalone phrase/sentence, preserving its original meaning and register — don't summarize, explain, or add commentary.
- Use the glossary EXACTLY where a source term matches one. It overrides your own preference.
- Keep monetary amounts in their original currency (e.g. KRW, USD) — never convert currency.
- Keep numbers, codes, dates, and identifiers (invoice numbers, regulatory acronyms like SOP/GMP/QA/QC/IND/IRB/CTD/CDA/PMS/BE/CAPA) exactly as written.
- If an item is already in {target_label}, return it unchanged.
- Output ONLY a JSON object mapping each id to its translation as a plain string, e.g. {{"a1b2c3": "...", "d4e5f6": "..."}}. No preamble, no markdown fences, no explanation."""


def _key(s: str) -> str:
    return hashlib.sha256(s.strip().encode("utf-8")).hexdigest()[:16]


def _build_prompt(batch: dict, glossary: list) -> str:
    parts = []
    if glossary:
        parts.append("Glossary (source term -> preferred translation — use exactly when a source item matches one of these):")
        parts.append(json.dumps(glossary, ensure_ascii=False, indent=1))
    parts.append("Translate these items. Respond with a JSON object mapping each id below to its translation, same ids:")
    parts.append(json.dumps(batch, ensure_ascii=False, indent=1))
    return "\n\n".join(parts)


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


async def _call_llm(provider: str, system: str, prompt: str, api_key: str | None) -> str:
    """Single non-streaming call — returns raw text (may still be ```json-fenced)."""
    if provider == "anthropic":
        client = anthropic.AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-opus-5",
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    if provider == "gemini":
        return (await gemini_service.generate(
            system_prompt=system,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            api_key=api_key,
        )).strip()

    if provider == "openai":
        async with httpx.AsyncClient(timeout=CLOUD_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key or settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    if provider == "kimi":
        async with httpx.AsyncClient(timeout=CLOUD_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{settings.kimi_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key or settings.kimi_api_key}"},
                json={
                    "model": settings.kimi_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    # "onprem" (default) — local Ollama, free, no key.
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{settings.ollama_api_url.rstrip('/')}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1, "top_p": 0.9},
                "think": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


async def _translate_batch(batch: dict, target: str, provider: str, api_key: str | None, glossary: list) -> dict:
    system = SYSTEM_PROMPT_TEMPLATE.format(target_label=TARGET_LABEL[target])
    raw = await _call_llm(provider, system, _build_prompt(batch, glossary), api_key)
    result = json.loads(_strip_fences(raw))

    # Guide §5.3 — verify the batch came back whole; a partial/short response
    # from the model isn't degraded silently, the missing ids get one retry.
    missing = set(batch) - set(result)
    if missing:
        retry_batch = {k: batch[k] for k in missing}
        retry_raw = await _call_llm(provider, system, _build_prompt(retry_batch, glossary), api_key)
        result.update(json.loads(_strip_fences(retry_raw)))
    return result


_HANGUL_RE = re.compile(r"[가-힣]")
_NUM_RE = re.compile(r"[\d,]+")


def _qa_issues(source: str, translated: str) -> list:
    """Guide §5.4 — flags, doesn't reject: items land in a review list, not
    a hard failure, since these heuristics have false positives."""
    issues = []
    if _HANGUL_RE.search(translated):
        issues.append("leftover Hangul in translation")
    nums_src = set(_NUM_RE.findall(source))
    if nums_src and not nums_src <= set(_NUM_RE.findall(translated)):
        issues.append("numbers missing or changed")
    if len(translated) > len(source) * 6 + 20:
        issues.append("unusually long — may be explaining rather than translating")
    if not translated.strip():
        issues.append("empty translation")
    return issues


def _texts_in_block(block: dict) -> list:
    if block.get("type") in ("heading", "paragraph"):
        return [block["text"]] if block.get("text") else []
    if block.get("type") == "table":
        return [c for row in block.get("rows", []) for c in row if c and c.strip()]
    return []


async def translate_blocks(blocks: list, target: str, provider: str, api_key: str | None, glossary: list) -> tuple:
    """
    target: "en" | "id". glossary: rows from document_glossary_terms, each
    {"source_term", "target_en", "target_id", "notes"}.
    Returns (translated_blocks, qa_warnings) — translated_blocks is the same
    shape as `blocks` with every string replaced; qa_warnings is a flat list
    of {"source", "translated", "issues": [...]} for anything flagged.
    """
    uniq = {}
    for b in blocks:
        for s in _texts_in_block(b):
            uniq.setdefault(_key(s), s)

    if not uniq:
        return blocks, []

    glossary_for_target = [
        {"source": g["source_term"], "translation": g.get(f"target_{target}"), "notes": g.get("notes") or ""}
        for g in glossary if g.get(f"target_{target}")
    ]

    items = list(uniq.items())
    translated_map = {}
    for i in range(0, len(items), BATCH_SIZE):
        batch = dict(items[i:i + BATCH_SIZE])
        translated_map.update(await _translate_batch(batch, target, provider, api_key, glossary_for_target))

    qa_warnings = []
    for h, src in uniq.items():
        tr = translated_map.get(h, "")
        issues = _qa_issues(src, tr)
        if issues:
            qa_warnings.append({"source": src, "translated": tr, "issues": issues})

    def _tr(s: str) -> str:
        return translated_map.get(_key(s), s) if s else s

    out_blocks = []
    for b in blocks:
        if b.get("type") in ("heading", "paragraph"):
            out_blocks.append({**b, "text": _tr(b.get("text", ""))})
        elif b.get("type") == "table":
            out_blocks.append({**b, "rows": [[_tr(c) for c in row] for row in b.get("rows", [])]})
        else:
            out_blocks.append(b)

    return out_blocks, qa_warnings
