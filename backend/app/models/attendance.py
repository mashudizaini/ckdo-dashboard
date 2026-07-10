from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, UniqueConstraint
from app.database import Base


class AttendanceRecord(Base):
    """Daily physical attendance — sourced from the Intercom access-control export.
    One row per employee per day."""
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_emp_date"),
    )

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    employee_id        = Column(String(20),  nullable=False, index=True)
    employee_name      = Column(String(200))
    department         = Column(String(100))
    team               = Column(String(100))
    attendance_date    = Column(Date,        nullable=False, index=True)
    week_day           = Column(String(20))
    time_period        = Column(String(50))
    scheduled_checkin  = Column(String(10))
    scheduled_checkout = Column(String(10))
    actual_checkin     = Column(String(10))
    actual_checkout    = Column(String(10))
    attendance_status  = Column(String(10))   # W=Worked, L=Late, E=Early leave, LE=Late+Early, A=Absent (Intercom's own determination)
    notes              = Column(Text)

    upload_batch_id    = Column(String(50), index=True)
    uploaded_at        = Column(DateTime, default=datetime.utcnow)


class AttendanceLeaveEvent(Base):
    """Leave / business-trip days — sourced from the Talenta export. Used to
    reclassify a day that would otherwise look "absent" in AttendanceRecord:
    approved leave (SL/AL/ML/EM/UL/...) is excluded from the attendance-rate
    denominator entirely, and Business Trip (BT) counts as present."""
    __tablename__ = "attendance_leave_events"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_leave_event_emp_date"),
    )

    id                = Column(Integer, primary_key=True, autoincrement=True)
    employee_id       = Column(String(20),  nullable=False, index=True)
    employee_name     = Column(String(200))
    department        = Column(String(100))
    attendance_date   = Column(Date,        nullable=False, index=True)
    attendance_code   = Column(String(20))
    time_off_code     = Column(String(20))

    upload_batch_id   = Column(String(50), index=True)
    uploaded_at       = Column(DateTime, default=datetime.utcnow)


class AttendanceUploadLog(Base):
    __tablename__ = "attendance_upload_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    source      = Column(String(20), default="intercom")  # intercom | talenta
    filename    = Column(String(255))
    total_rows  = Column(Integer, default=0)
    inserted    = Column(Integer, default=0)
    updated     = Column(Integer, default=0)
    skipped     = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
