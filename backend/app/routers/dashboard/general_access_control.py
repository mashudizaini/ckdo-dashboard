"""
Access Control Router
Route prefix : /api/v1/dashboard/general/access-control
Required role: it_staff OR admin — applied PER-ENDPOINT below (not at
router-mount time, unlike it_hikcentral/it_zkteco/it_etl_admin) because this
router mixes gate levels: GET /my-access must stay open to any authenticated
user (every user needs it to know which of their own Setup > General tabs
to show), while everything else here is IT-only.

Endpoints:
  GET  /menus            — the MENU_REGISTRY (for building the checkbox UI)
  GET  /users             — distinct emails with any existing override row
  GET  /users/{email}     — that email's current grant for every registry key
  PUT  /users/{email}/{menu_key} — body {granted: bool}, upsert
  GET  /my-access         — the CALLER's own granted menu_key list (no role gate)
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role, CurrentUser, Roles
from app.services import menu_access_service

router = APIRouter()


@router.get("/menus")
async def get_menus(user: CurrentUser = Depends(require_role(Roles.IT))):
    return [{"menu_key": k, **v} for k, v in menu_access_service.MENU_REGISTRY.items()]


@router.get("/users")
async def get_configured_users(
    user: CurrentUser = Depends(require_role(Roles.IT)),
    db: AsyncSession = Depends(get_db),
):
    return await menu_access_service.list_configured_emails(db)


@router.get("/users/{email}")
async def get_user_access(
    email: str,
    user: CurrentUser = Depends(require_role(Roles.IT)),
    db: AsyncSession = Depends(get_db),
):
    return {"email": email, "access": await menu_access_service.list_access_for_email(db, email)}


class SetAccessRequest(BaseModel):
    granted: bool


@router.put("/users/{email}/{menu_key}")
async def set_user_access(
    email: str, menu_key: str, body: SetAccessRequest,
    user: CurrentUser = Depends(require_role(Roles.IT)),
    db: AsyncSession = Depends(get_db),
):
    await menu_access_service.set_menu_access(db, email, menu_key, body.granted, updated_by=user.username)
    return {"success": True}


@router.get("/my-access")
async def get_my_access(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """No role gate — any authenticated user needs this to know which of
    their own Setup > General tabs to show."""
    email = menu_access_service._resolve_email(user)
    if not email:
        return {"granted": []}
    access = await menu_access_service.list_access_for_email(db, email)
    return {"granted": [k for k, v in access.items() if v]}
