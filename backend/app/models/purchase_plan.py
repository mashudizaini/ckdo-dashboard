from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class PurchasePlanMaterial(Base):
    """
    Purchase Plan (Material) — modular input for purchasing planning, mirrors
    SalesPlan's shape. plan_category distinguishes the sheet the data came
    from in the "(P1-M) Purchase plan_Material.xlsx" reference template
    (Summary / Local / CMO / Export).
    """
    __tablename__ = "purchase_plan_materials"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    plan_year     = Column(Integer,     nullable=False, index=True)
    plan_category = Column(String(20),  nullable=False, default="Local")  # Summary | Local | CMO | Export
    department    = Column(String(100), nullable=False, default="")
    team_code     = Column(String(50),  nullable=False, default="")
    team_name     = Column(String(100), nullable=False, default="")
    content       = Column(JSONB,       nullable=False, default=dict)
    status        = Column(String(10),  default="draft")   # draft | final
    created_by    = Column(String(100), default="")
    created_at    = Column(DateTime,    default=datetime.utcnow)
    updated_at    = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
