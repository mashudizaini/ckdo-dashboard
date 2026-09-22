from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class PurchasePlanFinishedGood(Base):
    """
    Purchase Plan (Finished Good) — parallel to PurchasePlanMaterial
    (purchase_plan.py), but for a genuinely different Excel template
    ("Purchase Plan FG - 2026.xlsx"): different meta cell positions,
    different month columns, and an "Usage"/"Order" two-row-per-item
    pairing instead of Material's "Order"/"Received". Kept in its own
    table (not merged into purchase_plan_materials) so an FG plan and a
    Material plan sharing the same (plan_year, plan_category, department,
    team_code) — e.g. both categorized "Export" — can never collide and
    silently overwrite each other.
    """
    __tablename__ = "purchase_plan_finished_goods"

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
