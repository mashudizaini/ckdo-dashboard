from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class SalesPlan(Base):
    """
    Sales Plan — modular input for sales planning (value and unit).
    """
    __tablename__ = "sales_plans"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    plan_year    = Column(Integer,     nullable=False, index=True)
    department   = Column(String(100), nullable=False, default="")
    team_code    = Column(String(50),  nullable=False, default="")
    team_name    = Column(String(100), nullable=False, default="")
    plan_type    = Column(String(10),  nullable=False, default="value")  # value | unit
    content      = Column(JSONB,       nullable=False, default=dict)
    status       = Column(String(10),  default="draft")   # draft | final
    created_by   = Column(String(100), default="")
    created_at   = Column(DateTime,    default=datetime.utcnow)
    updated_at   = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)


class SalesPlanHistory(Base):
    """
    Sales Plan History — untuk menyimpan snapshot export ke Excel.
    """
    __tablename__ = "sales_plan_history"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    sales_plan_id = Column(Integer, ForeignKey("sales_plans.id", ondelete="CASCADE"), nullable=False)
    plan_type    = Column(String(10),  nullable=False)  # value | unit
    filename     = Column(String(255), nullable=False)
    file_path    = Column(String(500), nullable=False)
    generated_by = Column(String(100), default="")
    generated_at = Column(DateTime,    default=datetime.utcnow)
