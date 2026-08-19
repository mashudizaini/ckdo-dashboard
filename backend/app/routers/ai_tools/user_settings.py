"""
AI User Settings Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/settings
Required role: any authenticated user (each user manages only their own key)

Lets each user optionally store their own API key (Gemini for the AI
Chatbot; Gemini/Claude/ChatGPT/Kimi for Meeting Notes' MOM generation) so
those features use their personal account/quota instead of the shared
company key. Keys are validated against the live provider API before
saving (see user_api_key_service.VALIDATORS) and encrypted at rest — see
user_api_key_service.py / crypto.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user, CurrentUser
from app.services import user_api_key_service as svc

router = APIRouter()


class ApiKeyRequest(BaseModel):
    api_key: str


def _check_provider(provider: str):
    if provider not in svc.ALLOWED_PROVIDERS:
        raise HTTPException(400, f"Provider tidak didukung: {provider}")


@router.get("/api-key/{provider}")
async def get_api_key_status(
    provider: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_provider(provider)
    return await svc.get_key_status(db, user.username, provider)


@router.put("/api-key/{provider}")
async def save_api_key(
    provider: str,
    request: ApiKeyRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_provider(provider)
    key = request.api_key.strip()
    if not key:
        raise HTTPException(400, "API key tidak boleh kosong")

    try:
        await svc.VALIDATORS[provider](key)
    except ValueError as e:
        raise HTTPException(400, str(e))

    hint = await svc.set_user_key(db, user.username, provider, key)
    return {"message": "API key berhasil disimpan dan tervalidasi", "key_hint": hint}


@router.delete("/api-key/{provider}")
async def remove_api_key(
    provider: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_provider(provider)
    deleted = await svc.delete_user_key(db, user.username, provider)
    if not deleted:
        raise HTTPException(404, "Belum ada API key tersimpan untuk provider ini")
    return {"message": "API key dihapus — kembali memakai key perusahaan (shared)"}
