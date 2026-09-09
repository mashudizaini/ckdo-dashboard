"""
Digital Overtime Management System — shared domain logic.

Everything here is deliberately router-agnostic so the employee-facing
router (hr_overtime.py) and the HRGA admin router (hr_overtime_admin.py)
compute duration, approval rights, cut-off windows and overtime index
*identically* — the two most expensive bugs in an overtime system are
"the approver saw different hours than payroll did" and "someone approved
their own request".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.employee import Employee
from app.models.overtime import (
    ROLE_DEPT_HEAD, ROLE_HRGA_ADMIN, ROLE_MEMBER, ROLE_TEAM_HEAD,
    OvertimeApprovalLog, OvertimeApprovalMatrix, OvertimeCutoffConfig,
    OvertimeNotification, OvertimeNotificationSetting, OvertimeRequest,
)
from app.models.working_calendar import WorkingCalendarHoliday

# ─────────────────────────────────────────
# TIME HELPERS
# ─────────────────────────────────────────

def parse_hhmm(value: Optional[str]) -> Optional[int]:
    """"HH:MM" -> minutes since midnight. Returns None for blank input."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        hh, mm = text.split(":")[:2]
        h, m = int(hh), int(mm)
    except (ValueError, IndexError):
        raise HTTPException(400, f"Invalid time format '{value}' — expected HH:MM")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise HTTPException(400, f"Invalid time '{value}' — expected HH:MM within 00:00-23:59")
    return h * 60 + m


def duration_minutes(start: Optional[str], finish: Optional[str]) -> int:
    """Minutes between two "HH:MM" clock times.

    A finish at or before the start is read as crossing midnight (22:00 ->
    01:00 = 180 min), which is the normal case for evening overtime — not as
    an input error. An identical start and finish is 0, not 24 hours.
    """
    s, f = parse_hhmm(start), parse_hhmm(finish)
    if s is None or f is None:
        return 0
    if f == s:
        return 0
    if f < s:
        f += 24 * 60
    return f - s


def fmt_hours(minutes: Optional[int]) -> float:
    """Minutes -> hours rounded to 2dp, for display and totals."""
    return round((minutes or 0) / 60.0, 2)


# ─────────────────────────────────────────
# OVERTIME INDEX (Kepmenaker No. 102/MEN/VI/2004)
# ─────────────────────────────────────────
# The statutory Indonesian multipliers. Returned as "index hours": the
# number of hourly-wage units owed, so cost = index * hourly_rate and the
# multiplier rules live in exactly one place.

def overtime_index(minutes: int, is_weekend: bool) -> Decimal:
    hours = Decimal(minutes or 0) / Decimal(60)
    if hours <= 0:
        return Decimal("0.00")

    if not is_weekend:
        # Weekday: 1.5x for the first hour, 2x for every hour after it.
        first = min(hours, Decimal(1))
        rest = max(hours - Decimal(1), Decimal(0))
        idx = first * Decimal("1.5") + rest * Decimal(2)
    else:
        # Rest day / public holiday on a 5-working-day week: 2x for the
        # first 8 hours, 3x for the 9th, 4x for the 10th and 11th. Anything
        # beyond 11h stays at 4x rather than falling off a cliff.
        idx = Decimal(0)
        remaining = hours
        for cap, mult in ((Decimal(8), Decimal(2)), (Decimal(1), Decimal(3)), (Decimal(2), Decimal(4))):
            take = min(remaining, cap)
            idx += take * mult
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            idx += remaining * Decimal(4)

    return idx.quantize(Decimal("0.01"))


# ─────────────────────────────────────────
# CUT-OFF PERIOD
# ─────────────────────────────────────────

@dataclass
class CutoffPeriod:
    label: str          # "11 Aug 2026 - 10 Sep 2026"
    key: str            # "2026-09" — the month the period *closes* in, i.e. the payroll month
    start: date
    end: date


def add_months(d: date, n: int) -> date:
    """Shift a date by n months, clamping the day to the target month's length."""
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    month += 1
    # Day 31 in a 30-day month clamps down rather than overflowing.
    last_day = (date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def cutoff_period_for_key(key: str, start_day: int, end_day: int) -> CutoffPeriod:
    """`key` is "YYYY-MM" of the month the period CLOSES in — the payroll
    month people actually name ("September payroll" = 11 Aug to 10 Sep)."""
    try:
        year, month = (int(x) for x in key.split("-")[:2])
        end_anchor = date(year, month, 1)
    except (ValueError, IndexError):
        raise HTTPException(400, f"Invalid period '{key}' — expected YYYY-MM")

    end_month_last = (add_months(end_anchor, 1) - timedelta(days=1)).day
    end = date(year, month, min(end_day, end_month_last))
    start_anchor = add_months(end_anchor, -1)
    start_month_last = (add_months(start_anchor, 1) - timedelta(days=1)).day
    start = date(start_anchor.year, start_anchor.month, min(start_day, start_month_last))

    fmt = "%d %b %Y"
    return CutoffPeriod(label=f"{start.strftime(fmt)} - {end.strftime(fmt)}", key=key, start=start, end=end)


async def get_active_cutoff(db: AsyncSession) -> OvertimeCutoffConfig:
    result = await db.execute(
        select(OvertimeCutoffConfig).where(OvertimeCutoffConfig.is_active.is_(True))
        .order_by(OvertimeCutoffConfig.id.desc())
    )
    row = result.scalars().first()
    if row:
        return row
    # Seed the documented default (11th -> 10th) on first use rather than
    # making the Calculation tab unusable until someone visits Settings.
    row = OvertimeCutoffConfig(name="Default", start_day=11, end_day=10, is_active=True, updated_by="system")
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────
# WORKING CALENDAR
# ─────────────────────────────────────────

async def is_non_working_day(db: AsyncSession, day: date) -> bool:
    """Weekend or a holiday on the HRGA working calendar — the two cases the
    site map lumps together as "Weekend / Public Holiday" overtime."""
    if day.weekday() >= 5:
        return True
    result = await db.execute(
        select(WorkingCalendarHoliday).where(WorkingCalendarHoliday.holiday_date == day)
    )
    return result.scalars().first() is not None


# ─────────────────────────────────────────
# ACTOR RESOLUTION
# ─────────────────────────────────────────

@dataclass
class OvertimeActor:
    """The logged-in user, resolved into overtime terms."""
    user: CurrentUser
    employee: Optional[Employee]
    matrix: Optional[OvertimeApprovalMatrix]

    @property
    def employee_id(self) -> str:
        return self.employee.user_id if self.employee else ""

    @property
    def full_name(self) -> str:
        if self.employee and self.employee.full_name:
            return self.employee.full_name
        return self.user.full_name or self.user.username

    @property
    def email(self) -> str:
        return (self.user.email or self.user.username or "").strip().lower()

    @property
    def role_level(self) -> str:
        if self.is_hrga_admin:
            return ROLE_HRGA_ADMIN
        return self.matrix.role_level if self.matrix else ROLE_MEMBER

    @property
    def is_hrga_admin(self) -> bool:
        """HRGA administrators of the module: the Keycloak hr_staff/admin
        roles, plus anyone HRGA explicitly marks hrga_admin in the approval
        matrix (so a GA officer without the hr_staff realm role can still run
        the final check without an IT round-trip)."""
        if self.user.has_any_role("admin", "hr_staff"):
            return True
        return bool(self.matrix and self.matrix.role_level == ROLE_HRGA_ADMIN)

    @property
    def is_team_head(self) -> bool:
        return bool(self.matrix and self.matrix.role_level in (ROLE_TEAM_HEAD, ROLE_DEPT_HEAD))

    @property
    def is_dept_head(self) -> bool:
        return bool(self.matrix and self.matrix.role_level == ROLE_DEPT_HEAD)


async def _find_employee(user: CurrentUser, db: AsyncSession) -> Optional[Employee]:
    """Same match as budget_access_service._find_employee — company_email is
    the only field on Employee that corresponds to a login identity."""
    for candidate in (user.email, user.username):
        if not candidate:
            continue
        result = await db.execute(select(Employee).where(Employee.company_email.ilike(candidate.strip())))
        employee = result.scalar_one_or_none()
        if employee:
            return employee
    return None


async def get_actor(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OvertimeActor:
    """FastAPI dependency — every overtime endpoint runs as an actor.

    Note this does NOT require an Employee row: an HRGA/admin account that
    isn't itself in the employee master must still be able to administer the
    module. Endpoints that genuinely need a requester identity call
    `require_employee()` on the actor instead.
    """
    employee = await _find_employee(user, db)
    matrix = None
    if employee:
        result = await db.execute(
            select(OvertimeApprovalMatrix).where(OvertimeApprovalMatrix.employee_id == employee.user_id)
        )
        matrix = result.scalar_one_or_none()
    return OvertimeActor(user=user, employee=employee, matrix=matrix)


def require_employee(actor: OvertimeActor) -> Employee:
    if not actor.employee:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your login is not linked to an employee record. Ask HRGA to set your company email "
            "on the Employee master before filing overtime.",
        )
    return actor.employee


async def require_admin(actor: OvertimeActor = Depends(get_actor)) -> OvertimeActor:
    if not actor.is_hrga_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied — HRGA administrators only.")
    return actor


# ─────────────────────────────────────────
# APPROVAL RIGHTS
# ─────────────────────────────────────────

async def subordinate_ids(db: AsyncSession, approver_id: str, level: str) -> list[str]:
    """Employee IDs whose overtime this approver is named on, at `level`
    ("team_head" or "dept_head") in the approval matrix."""
    column = OvertimeApprovalMatrix.team_head_id if level == ROLE_TEAM_HEAD else OvertimeApprovalMatrix.dept_head_id
    result = await db.execute(
        select(OvertimeApprovalMatrix.employee_id).where(column == approver_id, OvertimeApprovalMatrix.is_active.is_(True))
    )
    return [r[0] for r in result.all()]


def assert_not_self_approval(actor: OvertimeActor, req: OvertimeRequest) -> None:
    """A head still files their own overtime, but must never sign it off —
    it goes to the level above them, which is why the matrix lets a Team
    Head have their own team_head_id pointing at someone else."""
    if actor.employee_id and actor.employee_id == req.employee_id:
        raise HTTPException(403, "You cannot approve your own overtime request.")


# ─────────────────────────────────────────
# AUDIT TRAIL + NOTIFICATIONS
# ─────────────────────────────────────────

def log_action(
    db: AsyncSession, req: OvertimeRequest, actor: OvertimeActor,
    stage: str, action: str, note: str | None = None,
) -> None:
    db.add(OvertimeApprovalLog(
        request_id=req.id, stage=stage, action=action,
        actor_id=actor.employee_id, actor_name=actor.full_name,
        actor_email=actor.email, actor_role=actor.role_level, note=note,
    ))


DEFAULT_NOTIFICATION_EVENTS = [
    ("need_approval", "Need Approval Notification"),
    ("approval",      "Approval Notification"),
    ("rejection",     "Rejection Notification"),
    ("adjustment",    "Adjustment Permission Notification"),
]


async def ensure_notification_settings(db: AsyncSession) -> list[OvertimeNotificationSetting]:
    result = await db.execute(select(OvertimeNotificationSetting))
    rows = {r.event_key: r for r in result.scalars().all()}
    created = False
    for key, label in DEFAULT_NOTIFICATION_EVENTS:
        if key not in rows:
            row = OvertimeNotificationSetting(event_key=key, label=label, in_app=True, email=False, is_active=True)
            db.add(row)
            rows[key] = row
            created = True
    if created:
        await db.flush()
    return [rows[key] for key, _ in DEFAULT_NOTIFICATION_EVENTS]


async def notify(
    db: AsyncSession, *, event_key: str, recipient_email: str, recipient_id: str | None,
    title: str, body: str, req: OvertimeRequest | None = None,
) -> None:
    """Drop one in-app notification, honouring the HRGA on/off switch for
    that event type. Silently no-ops when there is no recipient — an
    unroutable notification must never block the approval it accompanies."""
    email = (recipient_email or "").strip().lower()
    if not email:
        return
    settings = {s.event_key: s for s in await ensure_notification_settings(db)}
    cfg = settings.get(event_key)
    if cfg and (not cfg.is_active or not cfg.in_app):
        return
    db.add(OvertimeNotification(
        recipient_email=email, recipient_id=recipient_id, event_key=event_key,
        title=title, body=body,
        request_id=req.id if req else None, request_no=req.request_no if req else None,
    ))


async def email_for_employee(db: AsyncSession, employee_id: str | None) -> tuple[str, str]:
    """(company_email, full_name) for a NIK — ("", "") when unknown."""
    if not employee_id:
        return "", ""
    result = await db.execute(select(Employee).where(Employee.user_id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        return "", ""
    return (emp.company_email or "").strip().lower(), emp.full_name or employee_id


# ─────────────────────────────────────────
# DOCUMENT NUMBERING
# ─────────────────────────────────────────

async def next_request_no(db: AsyncSession, when: date) -> str:
    """OT-YYYY-NNNNNN, restarting each year. Derived from the highest
    existing number in that year rather than a counter table — a gap from a
    deleted draft is harmless, a duplicate number would not be."""
    prefix = f"OT-{when.year}-"
    result = await db.execute(
        select(OvertimeRequest.request_no)
        .where(OvertimeRequest.request_no.like(f"{prefix}%"))
        .order_by(OvertimeRequest.request_no.desc()).limit(1)
    )
    last = result.scalars().first()
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:06d}"


# ─────────────────────────────────────────
# SERIALIZATION
# ─────────────────────────────────────────

def serialize_request(req: OvertimeRequest, *, hours: list | None = None, attachments: list | None = None,
                      logs: list | None = None) -> dict:
    data = {
        "id": req.id,
        "request_no": req.request_no,
        "employee_id": req.employee_id,
        "employee_name": req.employee_name,
        "employee_email": req.employee_email,
        "department": req.department,
        "division": req.division,
        "team": req.team,
        "overtime_type": req.overtime_type,
        "work_category": req.work_category,
        "task_description": req.task_description,
        "ot_date": req.ot_date.isoformat() if req.ot_date else None,
        "work_start": req.work_start,
        "work_finish": req.work_finish,
        "plan_start": req.plan_start,
        "plan_finish": req.plan_finish,
        "planned_minutes": req.planned_minutes or 0,
        "planned_hours": fmt_hours(req.planned_minutes),
        "plan_status": req.plan_status,
        "plan_submitted_at": req.plan_submitted_at.isoformat() if req.plan_submitted_at else None,
        "th_approver_id": req.th_approver_id,
        "th_approver_name": req.th_approver_name,
        "th_decision": req.th_decision,
        "th_decision_at": req.th_decision_at.isoformat() if req.th_decision_at else None,
        "th_note": req.th_note,
        "dh_approver_id": req.dh_approver_id,
        "dh_approver_name": req.dh_approver_name,
        "dh_decision": req.dh_decision,
        "dh_decision_at": req.dh_decision_at.isoformat() if req.dh_decision_at else None,
        "dh_note": req.dh_note,
        "rz_status": req.rz_status,
        "actual_start": req.actual_start,
        "actual_finish": req.actual_finish,
        "actual_minutes": req.actual_minutes or 0,
        "actual_hours": fmt_hours(req.actual_minutes),
        "gap_minutes": req.gap_minutes or 0,
        "gap_hours": fmt_hours(req.gap_minutes),
        "gap_reason": req.gap_reason,
        "rz_submitted_at": req.rz_submitted_at.isoformat() if req.rz_submitted_at else None,
        "rz_th_approver_name": req.rz_th_approver_name,
        "rz_th_decision": req.rz_th_decision,
        "rz_th_decision_at": req.rz_th_decision_at.isoformat() if req.rz_th_decision_at else None,
        "rz_th_note": req.rz_th_note,
        "rz_dh_approver_name": req.rz_dh_approver_name,
        "rz_dh_decision": req.rz_dh_decision,
        "rz_dh_decision_at": req.rz_dh_decision_at.isoformat() if req.rz_dh_decision_at else None,
        "rz_dh_note": req.rz_dh_note,
        "hr_approver_name": req.hr_approver_name,
        "hr_decision": req.hr_decision,
        "hr_decision_at": req.hr_decision_at.isoformat() if req.hr_decision_at else None,
        "hr_note": req.hr_note,
        "payable_minutes": req.payable_minutes or 0,
        "payable_hours": fmt_hours(req.payable_minutes),
        "overtime_index": float(req.overtime_index or 0),
        "hourly_rate": float(req.hourly_rate or 0),
        "estimated_cost": float(req.estimated_cost or 0),
        "cancel_reason": req.cancel_reason,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }
    if hours is not None:
        data["hour_details"] = [
            {"hour_no": h.hour_no, "detail": h.detail, "start_time": h.start_time, "finish_time": h.finish_time}
            for h in hours
        ]
    if attachments is not None:
        data["attachments"] = [
            {"id": a.id, "original_name": a.original_name, "content_type": a.content_type,
             "size_bytes": a.size_bytes, "uploaded_by": a.uploaded_by,
             "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None}
            for a in attachments
        ]
    if logs is not None:
        data["timeline"] = [
            {"stage": l.stage, "action": l.action, "actor_name": l.actor_name, "actor_role": l.actor_role,
             "note": l.note, "created_at": l.created_at.isoformat() if l.created_at else None}
            for l in logs
        ]
    return data
