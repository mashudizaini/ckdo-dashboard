from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class PACBusinessPlanSetup(Base):
    """
    Business Plan Setup module — Schedule, Guideline, Outlook.
    Stored as JSONB for flexible content.
    """
    __tablename__ = "pac_bp_setup"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    setup_module = Column(String(30),  nullable=False)   # schedule | guideline | outlook
    plan_year   = Column(Integer,     nullable=False, index=True)
    content     = Column(JSONB,       nullable=False, default=dict)
    status      = Column(String(10),  default="draft")   # draft | final
    created_at  = Column(DateTime,    default=datetime.utcnow)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by  = Column(String(100), default="")

    __table_args__ = (
        # One record per module per year
        # Uses unique_together style via a named constraint in migration, but SQLAlchemy
        # will create it automatically during create_all if we define it here:
        # However, for simplicity we rely on app-level uniqueness.
    )
