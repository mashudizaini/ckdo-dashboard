"""
Per-user API key storage — lets each user opt into using their own Gemini
account/quota for the AI Chatbot instead of the shared company key. Keys are
encrypted at rest (see crypto.py) and validated against the live provider
API before being saved, so a typo/invalid key fails fast at save time
instead of silently breaking every future chat request.
"""
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_api_key import UserApiKey
from app.services import crypto
from app.services import gemini_service

ALLOWED_PROVIDERS = {"gemini"}


async def _get_row(db: AsyncSession, username: str, provider: str) -> UserApiKey | None:
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.username == username, UserApiKey.provider == provider)
    )
    return result.scalar_one_or_none()


async def get_key_status(db: AsyncSession, username: str, provider: str) -> dict:
    row = await _get_row(db, username, provider)
    return {"has_key": row is not None, "key_hint": row.key_hint if row else None}


async def get_user_key(db: AsyncSession, username: str, provider: str) -> str | None:
    row = await _get_row(db, username, provider)
    return crypto.decrypt(row.encrypted_key) if row else None


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


async def set_user_key(db: AsyncSession, username: str, provider: str, plaintext: str) -> str:
    encrypted = crypto.encrypt(plaintext)
    hint = f"••••{plaintext[-4:]}" if len(plaintext) >= 4 else "••••"

    row = await _get_row(db, username, provider)
    if row:
        row.encrypted_key = encrypted
        row.key_hint = hint
    else:
        row = UserApiKey(username=username, provider=provider, encrypted_key=encrypted, key_hint=hint)
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
