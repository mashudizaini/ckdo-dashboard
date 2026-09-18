from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text

from app.database import Base


class Announcement(Base):
    """
    Admin-authored message shown alongside the system-derived birthday/
    late-attendance/task-alert notifications on the Application Center's
    Announcement & Notification panel (see AppLauncher.jsx). Unlike those
    three, this is manually created content, not derived from another
    table — the "add a new notification" half of Setup > General >
    Announcement & Notification.

    start_date/end_date are both optional: a null start_date means visible
    immediately, a null end_date means visible indefinitely (until manually
    disabled or deleted). is_enabled is a manual kill switch independent of
    the date window, so an admin can hide something without losing its
    dates/content.
    """
    __tablename__ = "announcements"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    title      = Column(String(200), nullable=False)
    message    = Column(Text, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    start_date = Column(Date, nullable=True)
    end_date   = Column(Date, nullable=True)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
