"""
AI Chat Provider Service
─────────────────────────────────────────
On/off switch per chat provider (onprem/anthropic/gemini) for the AI
Chatbot's 3 modes (Policy/Oracle/General) — a usage/cost control lever for
IT/admin (e.g. turning off Claude company-wide instead of relying on every
user remembering not to pick it). Scoped to the chatbot only — see
app/models/ai_chat_provider.py for why this doesn't touch other features
that also call these providers internally.

No row for a provider = enabled (see the model's docstring for why the
default is the opposite of menu_access_service's).
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chat_provider import AiChatProviderSetting

# label — for the admin UI and for error messages when a disabled
# provider is requested anyway.
PROVIDERS: dict[str, str] = {
    "onprem": "On-Premise",
    "anthropic": "Claude",
    "gemini": "Gemini",
}


async def list_provider_status(db: AsyncSession) -> dict[str, bool]:
    result = await db.execute(select(AiChatProviderSetting))
    rows = {r.provider: r.enabled for r in result.scalars().all()}
    return {p: rows.get(p, True) for p in PROVIDERS}


async def is_provider_enabled(db: AsyncSession, provider: str) -> bool:
    if provider not in PROVIDERS:
        return True  # unknown providers aren't this service's concern
    result = await db.execute(
        select(AiChatProviderSetting).where(AiChatProviderSetting.provider == provider)
    )
    row = result.scalar_one_or_none()
    return True if row is None else row.enabled


async def set_provider_enabled(db: AsyncSession, provider: str, enabled: bool, updated_by: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    result = await db.execute(
        select(AiChatProviderSetting).where(AiChatProviderSetting.provider == provider)
    )
    row = result.scalar_one_or_none()
    if row:
        row.enabled = enabled
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
    else:
        db.add(AiChatProviderSetting(provider=provider, enabled=enabled, updated_by=updated_by))
    await db.commit()
