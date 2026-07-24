from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class ManufacturePlan(Base):
    """
    Manufacture Plan ("Manufacture Plan Data" tab) — production planning by
    product/customer, mirrors SalesPlan's shape (flat headers+rows).
    """
    __tablename__ = "manufacture_plans"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    plan_year   = Column(Integer,     nullable=False, index=True)
    department  = Column(String(100), nullable=False, default="")
    team_code   = Column(String(50),  nullable=False, default="")
    team_name   = Column(String(100), nullable=False, default="")
    content     = Column(JSONB,       nullable=False, default=dict)
    status      = Column(String(10),  default="draft")   # draft | final
    created_by  = Column(String(100), default="")
    created_at  = Column(DateTime,    default=datetime.utcnow)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
