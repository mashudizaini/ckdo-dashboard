from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, UniqueConstraint
from app.database import Base


class LeaveRecord(Base):
    """Legacy — superseded by AttendanceRecord.leave_code (see
    models/attendance.py). Kept only so historical rows remain queryable;
    hr_leave.py no longer reads or writes this table."""
    __tablename__ = "leave_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_date", name="uq_leave_emp_date"),
    )

    id              = Column(Integer, primary_key=True, autoincrement=True)
    employee_id     = Column(String(20),  nullable=False, index=True)
    employee_name   = Column(String(200))
    organization    = Column(String(100))
    job_position    = Column(String(200))
    leave_date      = Column(Date,        nullable=False, index=True)
    leave_code      = Column(String(10),  nullable=False, index=True)
    leave_type      = Column(String(50))

    upload_batch_id = Column(String(50), index=True)
    uploaded_at     = Column(DateTime, default=datetime.utcnow)


class LeaveUploadLog(Base):
    __tablename__ = "leave_upload_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    filename    = Column(String(255))
    total_rows  = Column(Integer, default=0)
    inserted    = Column(Integer, default=0)
    updated     = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
