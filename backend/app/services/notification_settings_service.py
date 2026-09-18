"""
Announcement & Notification Settings Service
─────────────────────────────────────────
Backs Setup > General > Announcement & Notification, and is read by
AppLauncher.jsx (the Application Center home screen) to decide which of
the 3 system-derived notification types to fetch/show, plus which custom
Announcement rows are currently active.

Two independent concepts, both surfaced from this one service:
  - NOTIFICATION_REGISTRY: a fixed, code-defined list of system-derived
    notification types (birthday, late attendance, task alert — each
    backed by its own existing HR endpoint), each with a simple on/off
    switch stored in `notification_settings`. Same registry-plus-override
    shape as menu_access_service.MENU_REGISTRY, except the default when
    no row exists is "enabled" (these were always-on before this feature
    existed, so leaving one unconfigured must not silently hide it).
  - Announcement rows: free-form admin-authored messages, fully CRUD'd
    (not a fixed registry) — this is the "add a new notification" half of
    the feature, since adding a new *system-derived* type would require
    a new backend query/endpoint, not just a config change.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import Announcement
from app.models.notification_settings import NotificationSetting

NOTIFICATION_REGISTRY: dict[str, dict] = {
    "birthday":         {"label": "Birthday",         "description": "Karyawan yang berulang tahun bulan ini", "icon": "🎂"},
    "late_attendance":  {"label": "Late Attendance",   "description": "Karyawan yang terlambat bulan ini",      "icon": "⏰"},
    "task_alert":       {"label": "Task Alert",        "description": "Tugas HRGA yang mendekati/lewat deadline", "icon": "📋"},
}


# ── Notification type toggles ───────────────────────────────────────────

async def list_notification_settings(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(NotificationSetting))
    overrides = {r.key: r.is_enabled for r in result.scalars().all()}
    return [
        {"key": key, **meta, "is_enabled": overrides.get(key, True)}
        for key, meta in NOTIFICATION_REGISTRY.items()
    ]


async def set_notification_setting(db: AsyncSession, key: str, is_enabled: bool, updated_by: str) -> None:
    if key not in NOTIFICATION_REGISTRY:
        raise ValueError(f"Unknown notification key: {key}")
    result = await db.execute(select(NotificationSetting).where(NotificationSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.is_enabled = is_enabled
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
    else:
        db.add(NotificationSetting(key=key, is_enabled=is_enabled, updated_by=updated_by))
    await db.commit()


# ── Announcements (custom messages) ─────────────────────────────────────

def _announcement_dict(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "is_enabled": a.is_enabled,
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "end_date": a.end_date.isoformat() if a.end_date else None,
        "created_by": a.created_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


async def list_announcements(db: AsyncSession) -> list[dict]:
    """All rows, enabled or not — for the Setup > General admin list."""
    result = await db.execute(select(Announcement).order_by(Announcement.created_at.desc()))
    return [_announcement_dict(a) for a in result.scalars().all()]


async def list_active_announcements(db: AsyncSession) -> list[dict]:
    """Enabled rows whose optional date window covers today — for
    AppLauncher.jsx, which any authenticated user can call."""
    today = date.today()
    result = await db.execute(select(Announcement).where(Announcement.is_enabled.is_(True)))
    rows = result.scalars().all()
    active = [
        a for a in rows
        if (a.start_date is None or a.start_date <= today)
        and (a.end_date is None or a.end_date >= today)
    ]
    return [_announcement_dict(a) for a in active]


async def create_announcement(
    db: AsyncSession, title: str, message: str, is_enabled: bool,
    start_date: Optional[date], end_date: Optional[date], created_by: str,
) -> dict:
    a = Announcement(
        title=title, message=message, is_enabled=is_enabled,
        start_date=start_date, end_date=end_date, created_by=created_by,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _announcement_dict(a)


async def update_announcement(
    db: AsyncSession, announcement_id: int, title: str, message: str, is_enabled: bool,
    start_date: Optional[date], end_date: Optional[date],
) -> Optional[dict]:
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    a = result.scalar_one_or_none()
    if not a:
        return None
    a.title, a.message, a.is_enabled = title, message, is_enabled
    a.start_date, a.end_date = start_date, end_date
    a.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(a)
    return _announcement_dict(a)


async def delete_announcement(db: AsyncSession, announcement_id: int) -> bool:
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    a = result.scalar_one_or_none()
    if not a:
        return False
    await db.delete(a)
    await db.commit()
    return True
