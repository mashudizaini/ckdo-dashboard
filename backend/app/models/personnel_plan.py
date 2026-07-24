from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class PersonnelPlan(Base):
    """
    Personnel Plan ("Personal Plan Data" tab) — headcount plan + recruitment
    schedules, mirrors SalesPlan/PurchasePlanMaterial's shape. Content holds
    all three blocks from the reference template in one record: headcount
    (by level, prev/curr year Permanent/Temporary/Total + Increasing),
    recruitment_permanent and recruitment_temporary (by level, monthly plan).
    """
    __tablename__ = "personnel_plans"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    plan_year   = Column(Integer,     nullable=False, index=True)
    department  = Column(String(100), nullable=False, default="")
    content     = Column(JSONB,       nullable=False, default=dict)
    status      = Column(String(10),  default="draft")   # draft | final
    created_by  = Column(String(100), default="")
    created_at  = Column(DateTime,    default=datetime.utcnow)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
