"""
Menu Access Service
─────────────────────────────────────────
Per-user, per-menu-item access control — a second, finer-grained layer
underneath Keycloak's realm roles. Keycloak still decides whether someone
can reach a whole team's section at all (it_staff, hr_staff, ...); this
service decides, for the specific menu_keys in MENU_REGISTRY, which
individual users (by login email) can actually use that particular module.

Deliberately NOT trying to look up a user's Keycloak role assignments live —
that needs Keycloak Admin API credentials this backend doesn't have
configured (a separate integration, not built here). Instead: a plain
explicit allow-list in the user_menu_access table (see
app/models/menu_access.py). No row = not granted. Simple to audit, no
hidden "inherited from role" behavior to reason about.

MENU_REGISTRY currently only covers the 3 modules relocated from
Setup > IT to Setup > General (2026-09-01) — HikCentral Integration, ZKTeco
Integration, ETL Admin. Extending this to other modules later just means
adding more entries here and wiring require_menu_access() onto their
routers, same as done for these three.
"""
from datetime import datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, CurrentUser
from app.models.menu_access import UserMenuAccess

MENU_REGISTRY: dict[str, dict] = {
    "general.hikcentral": {"label": "HikCentral Integration", "section": "Setup > General"},
    "general.zkteco":     {"label": "ZKTeco Integration",     "section": "Setup > General"},
    "general.etl-admin":  {"label": "ETL Admin",               "section": "Setup > General"},
}


def _resolve_email(user: CurrentUser) -> str:
    """Same candidate order as budget_access_service._find_employee — email
    first, falling back to username (preferred_username is also an email
    address in this Keycloak realm)."""
    return (user.email or user.username or "").strip().lower()


async def has_menu_access(db: AsyncSession, email: str, menu_key: str) -> bool:
    result = await db.execute(
        select(UserMenuAccess).where(
            UserMenuAccess.user_email.ilike(email.strip()),
            UserMenuAccess.menu_key == menu_key,
        )
    )
    row = result.scalar_one_or_none()
    return bool(row and row.granted)


def require_menu_access(menu_key: str):
    """FastAPI dependency factory — same shape as require_role(), for
    routers gated by a MENU_REGISTRY key instead of a Keycloak role.
    "admin" bypasses this check, matching require_role()'s own escape hatch."""
    async def checker(
        user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        if user.has_role("admin"):
            return user
        email = _resolve_email(user)
        if not email or not await has_menu_access(db, email, menu_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Ask IT to grant access to '{MENU_REGISTRY.get(menu_key, {}).get('label', menu_key)}'.",
            )
        return user
    return checker


async def list_access_for_email(db: AsyncSession, email: str) -> dict[str, bool]:
    result = await db.execute(select(UserMenuAccess).where(UserMenuAccess.user_email.ilike(email.strip())))
    granted = {r.menu_key: r.granted for r in result.scalars().all()}
    return {key: granted.get(key, False) for key in MENU_REGISTRY}


async def list_configured_emails(db: AsyncSession) -> list[str]:
    result = await db.execute(select(UserMenuAccess.user_email).distinct())
    return sorted({row[0] for row in result.all()})


async def set_menu_access(db: AsyncSession, email: str, menu_key: str, granted: bool, updated_by: str) -> None:
    if menu_key not in MENU_REGISTRY:
        raise HTTPException(400, f"Unknown menu_key: {menu_key}")
    email = email.strip().lower()
    result = await db.execute(
        select(UserMenuAccess).where(
            UserMenuAccess.user_email.ilike(email),
            UserMenuAccess.menu_key == menu_key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.granted = granted
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
    else:
        db.add(UserMenuAccess(user_email=email, menu_key=menu_key, granted=granted, updated_by=updated_by))
    await db.commit()
