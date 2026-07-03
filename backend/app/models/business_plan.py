from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class PACBusinessPlan(Base):
    """
    Business Plan document — stored as JSONB for flexible hierarchical content.
    doc_type: 'managerial_obj' | 'strategy_plan'
    """
    __tablename__ = "pac_business_plans"
    __table_args__ = (
        UniqueConstraint("doc_type", "plan_year", "department", "team_code",
                         name="uq_pac_bp_doc"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    doc_type    = Column(String(20),  nullable=False)   # managerial_obj | strategy_plan
    plan_year   = Column(Integer,     nullable=False, index=True)
    department  = Column(String(100), nullable=False, default="ALL")
    team_code   = Column(String(20),  nullable=False, default="")
    team_name   = Column(String(100), nullable=False, default="")
    plan_role   = Column(String(100), nullable=False, default="")
    content     = Column(JSONB,       nullable=False, default=dict)
    status      = Column(String(10),  default="draft")   # draft | final
    created_at  = Column(DateTime,    default=datetime.utcnow)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by  = Column(String(100), default="")
