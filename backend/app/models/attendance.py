from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, UniqueConstraint
from app.database import Base


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_emp_date"),
    )

    id               = Column(Integer, primary_key=True, autoincrement=True)
    employee_id      = Column(String(20),  nullable=False, index=True)
    employee_name    = Column(String(200))
    department       = Column(String(100))
    attendance_date  = Column(Date,        nullable=False, index=True)
    week_day         = Column(String(20))
    time_period      = Column(String(50))
    scheduled_checkin  = Column(String(10))
    scheduled_checkout = Column(String(10))
    actual_checkin   = Column(String(10))
    actual_checkout  = Column(String(10))
    notes            = Column(Text)

    upload_batch_id  = Column(String(50), index=True)
    uploaded_at      = Column(DateTime, default=datetime.utcnow)


class AttendanceUploadLog(Base):
    __tablename__ = "attendance_upload_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    filename    = Column(String(255))
    total_rows  = Column(Integer, default=0)
    inserted    = Column(Integer, default=0)
    updated     = Column(Integer, default=0)
    skipped     = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
