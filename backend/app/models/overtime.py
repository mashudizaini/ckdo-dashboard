"""
Digital Overtime Management System — data model.

One `OvertimeRequest` row is the whole overtime document: the *plan* (the
"Overtime Order" the employee files before working) AND the *realization*
(what actually happened afterwards). They are deliberately not two tables —
a realization only ever exists against an approved plan, and every screen in
the site map (Dashboard summary, My Order, My Realization, Calculation,
Exception Report "plan vs realization") needs both halves side by side. Two
tables would mean a join on every one of those.

Each half carries its own independent approval chain, because that is how
the process actually runs:

    plan          employee -> team head -> dept head -> (approved)
    realization   employee -> team head -> dept head -> HRGA -> (final)

Column prefixes: `plan_*`/`th_*`/`dh_*` for the plan chain, `rz_*` for the
realization and its own `rz_th_*`/`rz_dh_*`/`hr_*` approvals.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint,
)

from app.database import Base

# ── Status vocabularies (kept as plain strings, not DB enums, so adding a
# state later is a code change and not a migration) ───────────────────────
PLAN_DRAFT       = "draft"
PLAN_SUBMITTED   = "submitted"      # waiting Team Head
PLAN_TH_APPROVED = "th_approved"    # waiting Department Head
PLAN_APPROVED    = "approved"       # final — employee may now realize it
PLAN_REVISION    = "revision"       # sent back, employee edits and resubmits
PLAN_REJECTED    = "rejected"
PLAN_CANCELLED   = "cancelled"

RZ_PENDING     = "pending"       # approved plan, nothing filled in yet
RZ_DRAFT       = "draft"
RZ_SUBMITTED   = "submitted"     # waiting Team Head
RZ_TH_APPROVED = "th_approved"   # waiting Department Head
RZ_DH_APPROVED = "dh_approved"   # waiting HRGA final check
RZ_APPROVED    = "approved"      # final — counts toward payable overtime
RZ_REVISION    = "revision"
RZ_REJECTED    = "rejected"

# role_level values on OvertimeApprovalMatrix
ROLE_MEMBER     = "member"
ROLE_TEAM_HEAD  = "team_head"
ROLE_DEPT_HEAD  = "dept_head"
ROLE_HRGA_ADMIN = "hrga_admin"


class OvertimeRequest(Base):
    __tablename__ = "overtime_requests"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    # Human-readable document number, e.g. OT-2026-000137 — what people
    # quote to each other; the surrogate id never leaves the system.
    request_no    = Column(String(30), unique=True, nullable=False, index=True)

    # ── Requester (denormalized from Employee at creation time so a later
    # transfer/resign doesn't rewrite history on already-approved rows) ──
    employee_id    = Column(String(20),  nullable=False, index=True)   # NIK
    employee_name  = Column(String(200))
    employee_email = Column(String(200), index=True)
    department     = Column(String(100), index=True)
    division       = Column(String(100))
    team           = Column(String(100), index=True)

    # ── The order itself ──
    overtime_type    = Column(String(20), nullable=False, index=True)  # weekday | weekend
    work_category    = Column(String(20), default="adhoc")             # adhoc | routine
    task_description = Column(Text, nullable=False)                    # Task / Target Result
    ot_date          = Column(Date, nullable=False, index=True)

    # Normal working time that day, "HH:MM" — context for the approver, and
    # what the overtime window is validated against (must sit outside it).
    work_start   = Column(String(5))
    work_finish  = Column(String(5))

    plan_start      = Column(String(5))
    plan_finish     = Column(String(5))
    planned_minutes = Column(Integer, default=0)

    # ── Plan approval chain ──
    plan_status       = Column(String(20), nullable=False, default=PLAN_DRAFT, index=True)
    plan_submitted_at = Column(DateTime)

    th_approver_id   = Column(String(20))
    th_approver_name = Column(String(200))
    th_decision      = Column(String(20))    # approved | rejected | revision
    th_decision_at   = Column(DateTime)
    th_note          = Column(Text)

    dh_approver_id   = Column(String(20))
    dh_approver_name = Column(String(200))
    dh_decision      = Column(String(20))
    dh_decision_at   = Column(DateTime)
    dh_note          = Column(Text)

    # ── Realization ──
    rz_status       = Column(String(20), nullable=False, default=RZ_PENDING, index=True)
    actual_start    = Column(String(5))
    actual_finish   = Column(String(5))
    actual_minutes  = Column(Integer, default=0)
    # actual_minutes - planned_minutes. Negative = worked less than planned.
    gap_minutes     = Column(Integer, default=0)
    gap_reason      = Column(Text)
    rz_submitted_at = Column(DateTime)

    rz_th_approver_id   = Column(String(20))
    rz_th_approver_name = Column(String(200))
    rz_th_decision      = Column(String(20))
    rz_th_decision_at   = Column(DateTime)
    rz_th_note          = Column(Text)

    rz_dh_approver_id   = Column(String(20))
    rz_dh_approver_name = Column(String(200))
    rz_dh_decision      = Column(String(20))
    rz_dh_decision_at   = Column(DateTime)
    rz_dh_note          = Column(Text)

    hr_approver_id   = Column(String(20))
    hr_approver_name = Column(String(200))
    hr_decision      = Column(String(20))
    hr_decision_at   = Column(DateTime)
    hr_note          = Column(Text)

    # ── Payable result, frozen at HRGA final approval ──
    # HRGA may pay fewer minutes than were actually worked (e.g. the gap is
    # unjustified) — this, not actual_minutes, is what Calculation totals.
    payable_minutes = Column(Integer, default=0)
    # Multiplier-hours per Kepmenaker 102/2004 (weekday 1.5x first hour then
    # 2x; weekend/holiday on a 5-day week 2x up to 8h, then 3x, then 4x).
    overtime_index  = Column(Numeric(10, 2), default=0)
    hourly_rate     = Column(Numeric(14, 2), default=0)   # rate applied, snapshotted
    estimated_cost  = Column(Numeric(16, 2), default=0)   # overtime_index * hourly_rate

    cancelled_at  = Column(DateTime)
    cancel_reason = Column(Text)

    created_by = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeHourDetail(Base):
    """Hour-by-hour breakdown required for weekend / public-holiday overtime
    only (site map C.3) — weekday overtime is short enough that a single
    task description covers it, weekend overtime has to be justified hour by
    hour before HRGA will pay it."""
    __tablename__ = "overtime_hour_details"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    request_id  = Column(Integer, ForeignKey("overtime_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    hour_no     = Column(Integer, nullable=False)     # 1, 2, 3, ...
    detail      = Column(Text)                        # task / result for that hour
    start_time  = Column(String(5))
    finish_time = Column(String(5))

    __table_args__ = (UniqueConstraint("request_id", "hour_no", name="uq_ot_hour_detail"),)


class OvertimeAttachment(Base):
    """Work evidence / supporting document for a realization (site map C.4)."""
    __tablename__ = "overtime_attachments"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    request_id    = Column(Integer, ForeignKey("overtime_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name = Column(String(300), nullable=False)
    stored_name   = Column(String(300), nullable=False)   # on disk under uploads/overtime_evidence/
    content_type  = Column(String(120))
    size_bytes    = Column(Integer, default=0)
    uploaded_by   = Column(String(200))
    uploaded_at   = Column(DateTime, default=datetime.utcnow)


class OvertimeApprovalLog(Base):
    """Append-only trail of every state change on a request — the answer to
    "who approved this, when, and what did they write". Never updated."""
    __tablename__ = "overtime_approval_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    request_id  = Column(Integer, ForeignKey("overtime_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    stage       = Column(String(20), nullable=False)   # plan | realization
    action      = Column(String(30), nullable=False)   # create/update/submit/approve/reject/revision/cancel/adjust
    actor_id    = Column(String(20))
    actor_name  = Column(String(200))
    actor_email = Column(String(200))
    actor_role  = Column(String(20))                   # member/team_head/dept_head/hrga_admin
    note        = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)


class OvertimeApprovalMatrix(Base):
    """Who a given employee's approvers are, and what they themselves may
    approve (site map D.1).

    Deliberately its own table rather than reusing Employee.supervisor_id:
    the overtime chain is two fixed levels (Team Head then Dept Head), which
    is not the same shape as the free-form supervisor tree — an employee's
    direct supervisor is often already the Dept Head, and some teams route
    overtime to someone other than the line manager. HRGA maintains this
    explicitly. No row for an employee = they can file overtime but it has
    nowhere to go, so the API refuses the submit with a clear message.
    """
    __tablename__ = "overtime_approval_matrix"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    employee_id   = Column(String(20), nullable=False, unique=True, index=True)
    employee_name = Column(String(200))
    department    = Column(String(100), index=True)
    team          = Column(String(100), index=True)
    role_level    = Column(String(20), nullable=False, default=ROLE_MEMBER, index=True)
    team_head_id  = Column(String(20), index=True)
    dept_head_id  = Column(String(20), index=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    updated_by    = Column(String(200))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeRule(Base):
    """Company overtime rules shown read-only on every employee's dashboard
    (site map A.3), maintained by HRGA (site map D.3)."""
    __tablename__ = "overtime_rules"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    seq        = Column(Integer, default=0)
    title      = Column(String(300), nullable=False)
    content    = Column(Text)
    is_active  = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeCutoffConfig(Base):
    """Payroll cut-off window (site map D.4) — e.g. the 11th of one month to
    the 10th of the next. Exactly one row is active at a time; older rows are
    kept so a historical calculation can be reproduced with the window that
    was in force then."""
    __tablename__ = "overtime_cutoff_config"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), default="Default")
    start_day  = Column(Integer, nullable=False, default=11)   # day-of-month the period opens
    end_day    = Column(Integer, nullable=False, default=10)    # day-of-month it closes (next month)
    is_active  = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeRateConfig(Base):
    """Base hourly wage per employee grade, used only to estimate overtime
    cost on the Monitoring tab. Salary is not held anywhere in this system —
    HRGA enters a representative hourly figure per grade instead, so the cost
    chart is indicative rather than payroll-accurate."""
    __tablename__ = "overtime_rate_config"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    grade       = Column(String(50), nullable=False, unique=True, index=True)
    hourly_rate = Column(Numeric(14, 2), nullable=False, default=0)
    updated_by  = Column(String(200))
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeNotificationSetting(Base):
    """Per-event delivery toggles (site map D.5). Email delivery is stored
    here but not yet wired to an SMTP sender — the in-app inbox is the live
    channel; the flag is respected the moment a sender is added."""
    __tablename__ = "overtime_notification_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    event_key  = Column(String(50), nullable=False, unique=True, index=True)  # need_approval | rejection | adjustment
    label      = Column(String(200))
    in_app     = Column(Boolean, nullable=False, default=True)
    email      = Column(Boolean, nullable=False, default=False)
    is_active  = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(200))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeNotification(Base):
    """In-app notification inbox (site map E)."""
    __tablename__ = "overtime_notifications"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    recipient_email = Column(String(200), nullable=False, index=True)
    recipient_id    = Column(String(20), index=True)
    event_key       = Column(String(50), index=True)   # need_approval | rejection | adjustment | approval
    title           = Column(String(300), nullable=False)
    body            = Column(Text)
    request_id      = Column(Integer, index=True)
    request_no      = Column(String(30))
    is_read         = Column(Boolean, nullable=False, default=False, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)
