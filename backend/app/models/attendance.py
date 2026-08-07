from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean, UniqueConstraint
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
    # True for a day the employee's own shift schedule marks as a rest day
    # (Plant source: ON DUTY column literally says "OFF") — distinct from a
    # calendar weekend, since Plant shift rotations can put a rest day on
    # any weekday. Excluded from the attendance-rate plan/actual the same
    # way a weekend is. Always False for Intercom/Talenta-sourced rows.
    is_day_off         = Column(Boolean, default=False, nullable=False)
    # Single leave/BT code for this day (SL/AL/ALAB/ML/EM/UL/ULBB/H/EL/HD/BT).
    # The master field for attendance-rate scoring AND the leave-quota
    # reports — both read this column, there is no separate leave table.
    leave_code         = Column(String(20))
    # Who/what last wrote this row: intercom | talenta | talenta-leave |
    # plant | manual. Purely informational (e.g. a "manually edited" badge
    # in the UI) — a later upload is always free to overwrite a manual edit,
    # there's no lock.
    source             = Column(String(20))

    upload_batch_id    = Column(String(50), index=True)
    uploaded_at        = Column(DateTime, default=datetime.utcnow)


class AttendanceRecordAuditLog(Base):
    """Field-level change log for manual edits to AttendanceRecord — lets HR
    trace who corrected what and why. Only written by the manual-edit
    endpoint, not by bulk Excel uploads (those already have upload_batch_id
    + AttendanceUploadLog for traceability)."""
    __tablename__ = "attendance_record_audit_log"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    employee_id     = Column(String(20), index=True, nullable=False)
    attendance_date = Column(Date, index=True, nullable=False)
    field           = Column(String(50), nullable=False)
    old_value       = Column(String(300))
    new_value       = Column(String(300))
    changed_by      = Column(String(100))
    changed_at      = Column(DateTime, default=datetime.utcnow)
    reason          = Column(Text)


class AttendanceLeaveEvent(Base):
    """Legacy — superseded by AttendanceRecord.leave_code. Kept only so
    historical rows remain queryable; no longer written to."""
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
