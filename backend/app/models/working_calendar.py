from datetime import date
from sqlalchemy import Column, Integer, String, Date, UniqueConstraint
from app.database import Base


class WorkingCalendarHoliday(Base):
    __tablename__ = "working_calendar_holidays"
    __table_args__ = (
        UniqueConstraint("holiday_date", name="uq_holiday_date"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    holiday_date = Column(Date, nullable=False, index=True)
    name         = Column(String(200), nullable=False)
    holiday_type = Column(String(20), nullable=False)  # national, collective, company
