"""
Gemini Service — shared helper for the Google Gemini API (Google AI Studio),
the third chat provider alongside on-premise Ollama ("onprem") and, for a
couple of other AI tools in this app, Anthropic. Opt-in per request via
provider="gemini". Raw REST (httpx), same pattern as the Ollama calls
elsewhere — no SDK dependency needed for a handful of endpoints.

API shapes below were validated empirically against the live API (current
as of 2026-07): https://generativelanguage.googleapis.com/v1beta

Key quirks vs. Ollama/OpenAI-style chat APIs:
  - Roles are "user"/"model" (not "assistant"); message content is
    `parts: [{"text": ...}]`, not a plain string.
  - System prompt is a separate top-level `systemInstruction`, not a
    message in the list.
  - Tool JSON-schema types are UPPERCASE ("OBJECT"/"STRING"), not lowercase.
  - When a function-call turn is replayed back to the model, the
    `thoughtSignature` returned alongside that functionCall part MUST be
    echoed back verbatim as a sibling key in that same part, or the API
    rejects the request with 400 "Function call is missing a
    thought_signature" (Gemini 3.x requirement, see
    https://ai.google.dev/gemini-api/docs/thought-signatures).
  - Use the "-latest" model alias, not a pinned dated model — dated IDs
    get deprecated for new API keys/projects (e.g. gemini-2.5-flash -> 404).
"""
import json
import httpx
from app.config import get_settings

settings = get_settings()

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TOOL_SELECTION_TIMEOUT_SECONDS = 60.0
STREAM_TIMEOUT_SECONDS = 120.0

# Reduces (but per Gemini 3.x, cannot fully disable) reasoning-token
# overhead — matters for chat responsiveness. thinkingBudget:0 was tried
# and rejected outright (400 invalid argument) on this model generation.
_GENERATION_CONFIG = {"thinkingConfig": {"thinkingLevel": "low"}}


def to_contents(history: list[dict], message: str) -> list[dict]:
    """Ollama/OpenAI-style [{role, content}] history -> Gemini `contents`."""
    contents = []
    for m in history:
        role = "model" if m.get("role") == "assistant" else "user"
        text = m.get("content", "")
        if not text:
            continue
        contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents


def _to_gemini_schema(schema: dict) -> dict:
    out = {}
    t = schema.get("type")
    if t:
        out["type"] = t.upper()
    if "description" in schema:
        out["description"] = schema["description"]
    if "properties" in schema:
        out["properties"] = {k: _to_gemini_schema(v) for k, v in schema["properties"].items()}
    if "required" in schema:
        out["required"] = schema["required"]
    return out


def to_gemini_tools(ollama_tools: list[dict]) -> list[dict]:
    """Ollama/OpenAI-style function-tool schema (lowercase types) -> Gemini functionDeclarations (uppercase types)."""
    declarations = []
    for tool in ollama_tools:
        fn = tool["function"]
        declarations.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": _to_gemini_schema(fn.get("parameters", {"type": "object", "properties": {}})),
        })
    return [{"functionDeclarations": declarations}]


async def generate_with_tools(system_prompt: str, contents: list[dict], tools: list[dict], api_key: str = None) -> dict:
    """
    Non-streaming call with tools attached — the model decides whether to
    call a function. Returns:
      {"function_calls": [{"name", "args", "id"}], "model_parts": <raw parts
       list to replay verbatim, including thoughtSignature>, "text": str}

    api_key: caller's resolved key (per-user key if they saved one, else the
    shared company key) — defaults to the shared company key if omitted.
    """
    payload = {
        "contents": contents,
        "tools": to_gemini_tools(tools),
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": _GENERATION_CONFIG,
    }
    async with httpx.AsyncClient(timeout=TOOL_SELECTION_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{BASE_URL}/models/{settings.gemini_model}:generateContent",
            params={"key": api_key or settings.gemini_api_key},
            json=payload,
        )
        resp.raise_for_status()
        result = resp.json()

    candidates = result.get("candidates") or []
    if not candidates:
        return {"function_calls": [], "model_parts": [], "text": ""}

    parts = candidates[0].get("content", {}).get("parts", [])
    function_calls = []
    text_parts = []
    for part in parts:
        if "functionCall" in part:
            fc = part["functionCall"]
            function_calls.append({"name": fc["name"], "args": fc.get("args", {}), "id": fc.get("id")})
        elif "text" in part:
            text_parts.append(part["text"])

    return {"function_calls": function_calls, "model_parts": parts, "text": "".join(text_parts)}


def function_response_part(name: str, call_id: str | None, data: list[dict] | None, error: str | None) -> dict:
    """Builds the {"role": "user", "parts": [{"functionResponse": ...}]} turn for a tool result."""
    # eis_tools returns rows straight from psycopg2 (RealDictCursor), whose
    # numeric columns come back as Decimal — not JSON-serializable by
    # httpx's plain json.dumps. Round-trip through json with default=str
    # (same fallback the Ollama path already used for this) to sanitize
    # before it goes into the request payload.
    result = {"error": error} if error else {"data": json.loads(json.dumps(data, default=str))}
    return {
        "role": "user",
        "parts": [{
            "functionResponse": {
                "name": name,
                "id": call_id,
                "response": {"result": result},
            }
        }],
    }


async def stream_generate(system_prompt: str, contents: list[dict], api_key: str = None):
    """
    Streams plain text tokens (not SSE-envelope-wrapped) from Gemini's native
    SSE endpoint. api_key: caller's resolved key — defaults to the shared
    company key if omitted.
    """
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": _GENERATION_CONFIG,
    }
    async with httpx.AsyncClient(timeout=STREAM_TIMEOUT_SECONDS) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/models/{settings.gemini_model}:streamGenerateContent",
            params={"key": api_key or settings.gemini_api_key, "alt": "sse"},
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[len("data: "):].strip()
                if not raw:
                    continue
                chunk = json.loads(raw)
                candidates = chunk.get("candidates") or []
                if not candidates:
                    continue
                for part in candidates[0].get("content", {}).get("parts", []):
                    text = part.get("text")
                    if text:
                        yield text
