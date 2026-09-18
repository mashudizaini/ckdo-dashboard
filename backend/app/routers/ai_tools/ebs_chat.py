"""
EBS Chat Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/ebs-chat

Endpoints:
  POST   /query        — service-to-service: CoChat asks a question on behalf
                          of one of its own users (X-Service-Key auth, no
                          Keycloak session — see ebs_chat_service.py)
  GET    /scope         — list configured email -> department scope rows (admin)
  POST   /scope         — create/update a scope row (admin)
  DELETE /scope/{email} — remove a scope row (admin)

See app/services/ebs_chat_service.py for the full design rationale (why the
scope source is a manually-curated table here rather than synced from
Oracle, and why only 3 of the 12 eis.* tools are actually RLS-scoped).
"""
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import require_role, CurrentUser, Roles
from app.services import ebs_chat_service

router = APIRouter()
settings = get_settings()


class QueryRequest(BaseModel):
    question: str
    user_email: str


async def _require_service_key(x_service_key: str = Header(None)):
    if not settings.ebs_chat_service_key:
        raise HTTPException(503, "EBS Chat belum dikonfigurasi (EBS_CHAT_SERVICE_KEY belum diset)")
    if not x_service_key or not hmac.compare_digest(x_service_key, settings.ebs_chat_service_key):
        raise HTTPException(401, "Invalid or missing X-Service-Key")


@router.post("/query", dependencies=[Depends(_require_service_key)])
async def query(payload: QueryRequest):
    if not payload.question or not payload.question.strip():
        raise HTTPException(400, "question is required")
    if not payload.user_email or not payload.user_email.strip():
        raise HTTPException(400, "user_email is required")

    result = await ebs_chat_service.answer_question(payload.question, payload.user_email)
    if result.get("error") in ("user_not_found_in_ebs", "scope_not_configured"):
        raise HTTPException(403, {"error": result["error"]})
    return result


class ScopeUpsert(BaseModel):
    email: str
    full_access: bool = False
    departments: list[str] = []
    allowed_modules: list[str] = []
    notes: str | None = None


@router.get("/modules")
async def list_modules(user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    """The MODULE_TOOL_MAP keys, for the allowed_modules checkbox UI —
    empty selection means "no restriction", same convention as an empty
    departments list under full_access."""
    return list(ebs_chat_service.MODULE_TOOL_MAP.keys())


@router.get("/scope")
async def list_scope(user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    return ebs_chat_service.list_scopes()


@router.post("/scope")
async def upsert_scope(payload: ScopeUpsert, user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    try:
        return ebs_chat_service.upsert_scope(
            payload.email, payload.full_access, payload.departments, payload.notes,
            updated_by=user.username or "admin", allowed_modules=payload.allowed_modules,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/scope/{email}")
async def remove_scope(email: str, user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    ebs_chat_service.delete_scope(email)
    return {"message": "Deleted"}
