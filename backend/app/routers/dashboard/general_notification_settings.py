"""
Announcement & Notification Settings Router
Route prefix : /api/v1/dashboard/general/notification-settings
Required role: admin — applied PER-ENDPOINT below, same mixed-gate reason
as general_access_control.py: GET /types and GET /announcements/active
must stay open to any authenticated user (AppLauncher.jsx calls them for
every user on every page load), while the rest (toggling a type, and all
Announcement CRUD) is admin-only.

Endpoints:
  GET    /types                    — the 3 system-derived types + enabled state (any user)
  PUT    /types/{key}               — body {is_enabled: bool} (admin)
  GET    /announcements/active     — enabled rows within their date window (any user)
  GET    /announcements            — all rows, for the admin list (admin)
  POST   /announcements            — create (admin)
  PUT    /announcements/{id}       — update (admin)
  DELETE /announcements/{id}       — delete (admin)
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, Roles, get_current_user, require_role
from app.services import notification_settings_service as svc

router = APIRouter()


@router.get("/types")
async def get_types(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_notification_settings(db)


class SetTypeRequest(BaseModel):
    is_enabled: bool


@router.put("/types/{key}")
async def set_type(
    key: str, body: SetTypeRequest,
    user: CurrentUser = Depends(require_role(Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.set_notification_setting(db, key, body.is_enabled, updated_by=user.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True}


@router.get("/announcements/active")
async def get_active_announcements(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_active_announcements(db)


@router.get("/announcements")
async def get_announcements(
    user: CurrentUser = Depends(require_role(Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_announcements(db)


class AnnouncementRequest(BaseModel):
    title: str
    message: str
    is_enabled: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@router.post("/announcements")
async def create_announcement(
    body: AnnouncementRequest,
    user: CurrentUser = Depends(require_role(Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if not body.title.strip() or not body.message.strip():
        raise HTTPException(400, "title and message are required")
    return await svc.create_announcement(
        db, body.title.strip(), body.message.strip(), body.is_enabled,
        body.start_date, body.end_date, created_by=user.username,
    )


@router.put("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: int, body: AnnouncementRequest,
    user: CurrentUser = Depends(require_role(Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if not body.title.strip() or not body.message.strip():
        raise HTTPException(400, "title and message are required")
    result = await svc.update_announcement(
        db, announcement_id, body.title.strip(), body.message.strip(), body.is_enabled,
        body.start_date, body.end_date,
    )
    if not result:
        raise HTTPException(404, "Announcement not found")
    return result


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    user: CurrentUser = Depends(require_role(Roles.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    ok = await svc.delete_announcement(db, announcement_id)
    if not ok:
        raise HTTPException(404, "Announcement not found")
    return {"success": True}
