from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from app.database import Base


class UserMenuAccess(Base):
    """
    Per-user, per-menu-item access override — explicit allow-list, keyed by
    login email rather than Keycloak role. No row for (user_email, menu_key)
    means NOT granted; there is no implicit "granted by role" fallback here
    (the backend has no Keycloak Admin API integration to look up an
    arbitrary user's role assignments, so this table is the sole source of
    truth for whichever menu_keys it covers — see menu_access_service.py's
    MENU_REGISTRY for which ones that currently is).
    """
    __tablename__ = "user_menu_access"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(200), nullable=False, index=True)
    menu_key   = Column(String(100), nullable=False)
    granted    = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_email", "menu_key", name="uq_user_menu_access"),)
