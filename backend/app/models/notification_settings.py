from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class NotificationSetting(Base):
    """
    Global on/off switch for one system-derived notification type shown on
    the Application Center's Announcement & Notification panel (birthday,
    late attendance, task alert — see NOTIFICATION_REGISTRY in
    notification_settings_service.py for the full list). One row per
    registry key; no row means "enabled" (registry default), matching how
    UserMenuAccess treats a missing row — except inverted, since these
    default to visible rather than hidden.
    """
    __tablename__ = "notification_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    key        = Column(String(50), unique=True, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
