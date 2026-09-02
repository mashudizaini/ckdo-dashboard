"""
Per-user API key storage — lets each user opt into using their own AI
provider account/quota (originally just Gemini for the AI Chatbot, now also
Claude/ChatGPT/Kimi for Meeting Notes' MOM generation) instead of the
shared company key. Keys are encrypted at rest (see crypto.py) and
validated against the live provider API before being saved, so a typo/
invalid key fails fast at save time instead of silently breaking every
future request.
"""
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.user_api_key import UserApiKey
from app.services import crypto
from app.services import gemini_service

settings = get_settings()

ALLOWED_PROVIDERS = {"gemini", "anthropic", "openai", "kimi"}

# Selectable models per provider — only providers listed here show a model
# picker in the API key setup UI; the first entry is the recommended
# default used when a user saves a key without picking a model.
ALLOWED_MODELS = {
    "anthropic": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
}


async def _get_row(db: AsyncSession, username: str, provider: str) -> UserApiKey | None:
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.username == username, UserApiKey.provider == provider)
    )
    return result.scalar_one_or_none()


async def get_key_status(db: AsyncSession, username: str, provider: str) -> dict:
    row = await _get_row(db, username, provider)
    return {
        "has_key": row is not None,
        "key_hint": row.key_hint if row else None,
        "model": row.model if row else None,
    }


async def get_user_key(db: AsyncSession, username: str, provider: str) -> str | None:
    row = await _get_row(db, username, provider)
    return crypto.decrypt(row.encrypted_key) if row else None


async def get_user_model(db: AsyncSession, username: str, provider: str) -> str | None:
    row = await _get_row(db, username, provider)
    return row.model if row else None


async def validate_gemini_key(api_key: str) -> None:
    """Raises ValueError with a user-facing message if the key doesn't work."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{gemini_service.BASE_URL}/models", params={"key": api_key})
    except httpx.HTTPError as e:
        raise ValueError(f"Tidak bisa menghubungi Gemini API: {e}")

    if resp.status_code == 200:
        return
    try:
        detail = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
    except Exception:
        detail = f"HTTP {resp.status_code}"
    raise ValueError(f"API key tidak valid: {detail}")


async def validate_anthropic_key(api_key: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
    except httpx.HTTPError as e:
        raise ValueError(f"Tidak bisa menghubungi Anthropic API: {e}")
    if resp.status_code == 200:
        return
    try:
        detail = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
    except Exception:
        detail = f"HTTP {resp.status_code}"
    raise ValueError(f"API key tidak valid: {detail}")


async def validate_openai_key(api_key: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        raise ValueError(f"Tidak bisa menghubungi OpenAI API: {e}")
    if resp.status_code == 200:
        return
    try:
        detail = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
    except Exception:
        detail = f"HTTP {resp.status_code}"
    raise ValueError(f"API key tidak valid: {detail}")


async def validate_kimi_key(api_key: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.kimi_api_base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        raise ValueError(f"Tidak bisa menghubungi Kimi (Moonshot) API: {e}")
    if resp.status_code == 200:
        return
    try:
        detail = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
    except Exception:
        detail = f"HTTP {resp.status_code}"
    raise ValueError(f"API key tidak valid: {detail}")


# Provider -> validator dispatch, shared by user_settings.py so adding a new
# provider only means adding a validate_<provider>_key function + one entry
# here + the provider name in ALLOWED_PROVIDERS above.
VALIDATORS = {
    "gemini": validate_gemini_key,
    "anthropic": validate_anthropic_key,
    "openai": validate_openai_key,
    "kimi": validate_kimi_key,
}


async def set_user_key(db: AsyncSession, username: str, provider: str, plaintext: str, model: str | None = None) -> str:
    encrypted = crypto.encrypt(plaintext)
    hint = f"••••{plaintext[-4:]}" if len(plaintext) >= 4 else "••••"
    if model and provider in ALLOWED_MODELS and model not in ALLOWED_MODELS[provider]:
        raise ValueError(f"Model tidak dikenali untuk {provider}: {model}")

    row = await _get_row(db, username, provider)
    if row:
        row.encrypted_key = encrypted
        row.key_hint = hint
        row.model = model
    else:
        row = UserApiKey(username=username, provider=provider, encrypted_key=encrypted, key_hint=hint, model=model)
        db.add(row)
    await db.commit()
    return hint


async def delete_user_key(db: AsyncSession, username: str, provider: str) -> bool:
    row = await _get_row(db, username, provider)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
