from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean
from app.database import Base


class HrgaTask(Base):
    """HRGA To Do List — task tracking integrated with HRGA e-Calendar."""
    __tablename__ = "hrga_tasks"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    title        = Column(String(300), nullable=False)
    description  = Column(Text)
    category     = Column(String(100))                          # Event, Project, Vendor Invoice, Admin, Other
    is_vendor    = Column(Boolean, default=False)                # eligible for TOP vendor 7-day alert
    assigned_to  = Column(String(200))
    role         = Column(String(50))                            # Manager / Supervisor / Officer
    status       = Column(String(20), default="Not Started", index=True)  # Not Started / In Progress / Completed
    due_date     = Column(Date, index=True)
    completed_at = Column(DateTime)
    created_by   = Column(String(100))
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
