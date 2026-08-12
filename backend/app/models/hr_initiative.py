from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class HRInitiative(Base):
    """
    HR Department Initiative — a named project/initiative tracked against a
    monthly budget vs actual spend, plus a manually-set completion status.
    Independent of the Oracle-synced GL Budget Monitoring section (this is
    user-entered, not pulled from GL_BALANCES) — feeds the "Department
    Initiatives" sub-tab dashboard (status donut, monthly budget vs actual
    bar chart, initiatives table).
    """
    __tablename__ = "hr_initiatives"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    year              = Column(Integer, nullable=False, index=True)
    name              = Column(String(255), nullable=False)
    status            = Column(String(20), nullable=False, default="on_track")  # on_track | behind_schedule | revised_schedule
    percent_complete  = Column(Integer, nullable=False, default=0)
    monthly_budget    = Column(JSONB, nullable=False, default=list)  # 12 floats, Jan-Dec
    monthly_actual    = Column(JSONB, nullable=False, default=list)  # 12 floats, Jan-Dec
    notes             = Column(Text, nullable=False, default="")
    created_by        = Column(String(100), default="")
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
