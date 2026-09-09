"""
Digital Overtime Management System — employee & approver endpoints.
Route prefix: /api/v1/dashboard/hr/overtime

Access: any authenticated user whose login maps to an Employee row. This is
the one HRGA module that is NOT gated on the hr_staff Keycloak role — every
employee files their own overtime here, and their Team Head / Department
Head approve it. HRGA-only screens (calculation, monitoring, settings) live
in hr_overtime_admin.py behind require_admin.
"""
import io
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.models.overtime import (
    PLAN_APPROVED, PLAN_CANCELLED, PLAN_DRAFT, PLAN_REJECTED, PLAN_REVISION,
    PLAN_SUBMITTED, PLAN_TH_APPROVED,
    ROLE_DEPT_HEAD, ROLE_TEAM_HEAD,
    RZ_APPROVED, RZ_DH_APPROVED, RZ_DRAFT, RZ_PENDING, RZ_REJECTED, RZ_REVISION,
    RZ_SUBMITTED, RZ_TH_APPROVED,
    OvertimeApprovalLog, OvertimeApprovalMatrix, OvertimeAttachment,
    OvertimeHourDetail, OvertimeNotification, OvertimeRateConfig, OvertimeRequest,
    OvertimeRule,
)
from app.services import overtime_service as svc
from app.services.overtime_service import OvertimeActor, get_actor

router = APIRouter()

_EVIDENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "overtime_evidence"
)
os.makedirs(_EVIDENCE_DIR, exist_ok=True)

_MAX_EVIDENCE_BYTES = 15 * 1024 * 1024
_ALLOWED_EVIDENCE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt"}

# Plan states the employee may still edit. Anything else is locked because
# an approver has already acted on it.
_PLAN_EDITABLE = {PLAN_DRAFT, PLAN_REVISION}
_RZ_EDITABLE = {RZ_PENDING, RZ_DRAFT, RZ_REVISION}


# ─────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────

class HourDetailIn(BaseModel):
    hour_no: int
    detail: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None


class OrderIn(BaseModel):
    overtime_type: Optional[str] = None          # weekday | weekend — auto-detected when omitted
    work_category: str = "adhoc"                 # adhoc | routine
    task_description: str
    ot_date: str
    work_start: Optional[str] = "08:30"
    work_finish: Optional[str] = "17:30"
    plan_start: str
    plan_finish: str
    submit: bool = False                         # True = file it straight away instead of saving a draft


class RealizationIn(BaseModel):
    actual_start: Optional[str] = None
    actual_finish: Optional[str] = None
    gap_reason: Optional[str] = None
    hour_details: list[HourDetailIn] = Field(default_factory=list)
    submit: bool = False


class DecisionIn(BaseModel):
    decision: str                                 # approve | reject | revision
    note: Optional[str] = None
    payable_minutes: Optional[int] = None         # HRGA final check only — pay fewer minutes than worked


class CancelIn(BaseModel):
    reason: Optional[str] = None


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

async def _load(db: AsyncSession, request_id: int) -> OvertimeRequest:
    result = await db.execute(select(OvertimeRequest).where(OvertimeRequest.id == request_id))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Overtime request not found")
    return req


def _assert_owner(actor: OvertimeActor, req: OvertimeRequest) -> None:
    if req.employee_id != actor.employee_id:
        raise HTTPException(403, "This overtime request belongs to another employee.")


async def _hours(db: AsyncSession, request_id: int) -> list[OvertimeHourDetail]:
    result = await db.execute(
        select(OvertimeHourDetail).where(OvertimeHourDetail.request_id == request_id)
        .order_by(OvertimeHourDetail.hour_no)
    )
    return list(result.scalars().all())


async def _attachments(db: AsyncSession, request_id: int) -> list[OvertimeAttachment]:
    result = await db.execute(
        select(OvertimeAttachment).where(OvertimeAttachment.request_id == request_id)
        .order_by(OvertimeAttachment.id)
    )
    return list(result.scalars().all())


async def _logs(db: AsyncSession, request_id: int) -> list[OvertimeApprovalLog]:
    result = await db.execute(
        select(OvertimeApprovalLog).where(OvertimeApprovalLog.request_id == request_id)
        .order_by(OvertimeApprovalLog.id)
    )
    return list(result.scalars().all())


async def _resolve_rate(db: AsyncSession, employee_id: str) -> Decimal:
    """Hourly base wage for cost estimation — by the employee's grade, then
    the "DEFAULT" catch-all row, then zero (cost simply shows as 0)."""
    result = await db.execute(select(Employee).where(Employee.user_id == employee_id))
    emp = result.scalar_one_or_none()
    grades = [g for g in ((emp.employee_grade if emp else None), "DEFAULT") if g]
    for grade in grades:
        row = (await db.execute(
            select(OvertimeRateConfig).where(OvertimeRateConfig.grade.ilike(grade.strip()))
        )).scalar_one_or_none()
        if row:
            return Decimal(row.hourly_rate or 0)
    return Decimal(0)


async def _matrix_for(db: AsyncSession, employee_id: str) -> Optional[OvertimeApprovalMatrix]:
    result = await db.execute(
        select(OvertimeApprovalMatrix).where(OvertimeApprovalMatrix.employee_id == employee_id)
    )
    return result.scalar_one_or_none()


def _can_act_as(actor: OvertimeActor, approver_id: Optional[str]) -> bool:
    """The named approver acts; an HRGA admin may act in their place (every
    such override is written to the approval log with the admin's name, so
    the substitution is never invisible)."""
    if approver_id and actor.employee_id == approver_id:
        return True
    return actor.is_hrga_admin


# ─────────────────────────────────────────
# CONTEXT
# ─────────────────────────────────────────

@router.get("/me")
async def whoami(actor: OvertimeActor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    """Everything the UI needs to decide which tabs to render."""
    th_name = dh_name = ""
    if actor.matrix:
        _, th_name = await svc.email_for_employee(db, actor.matrix.team_head_id)
        _, dh_name = await svc.email_for_employee(db, actor.matrix.dept_head_id)

    unread = (await db.execute(
        select(func.count(OvertimeNotification.id)).where(
            OvertimeNotification.recipient_email == actor.email,
            OvertimeNotification.is_read.is_(False),
        )
    )).scalar() or 0

    return {
        "employee_id": actor.employee_id,
        "full_name": actor.full_name,
        "email": actor.email,
        "department": actor.employee.department if actor.employee else None,
        "division": actor.employee.division if actor.employee else None,
        "team": actor.employee.team if actor.employee else None,
        "employee_linked": actor.employee is not None,
        "role_level": actor.role_level,
        "is_hrga_admin": actor.is_hrga_admin,
        "is_team_head": actor.is_team_head,
        "is_dept_head": actor.is_dept_head,
        "matrix_configured": actor.matrix is not None,
        "team_head_id": actor.matrix.team_head_id if actor.matrix else None,
        "team_head_name": th_name,
        "dept_head_id": actor.matrix.dept_head_id if actor.matrix else None,
        "dept_head_name": dh_name,
        "unread_notifications": unread,
    }


@router.get("/rules")
async def list_rules(actor: OvertimeActor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    """Read-only for everyone — HRGA maintains these under System Setting."""
    result = await db.execute(
        select(OvertimeRule).where(OvertimeRule.is_active.is_(True))
        .order_by(OvertimeRule.seq, OvertimeRule.id)
    )
    return [
        {"id": r.id, "seq": r.seq, "title": r.title, "content": r.content}
        for r in result.scalars().all()
    ]


# ─────────────────────────────────────────
# DASHBOARD (site map A)
# ─────────────────────────────────────────

@router.get("/dashboard/summary")
async def dashboard_summary(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to the current month"),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    if month:
        try:
            year, mon = (int(x) for x in month.split("-")[:2])
        except (ValueError, IndexError):
            raise HTTPException(400, "month must be YYYY-MM")
    else:
        year, mon = today.year, today.month
    start = date(year, mon, 1)
    end = (date(year + (mon // 12), (mon % 12) + 1, 1) - timedelta(days=1))

    mine = OvertimeRequest.employee_id == actor.employee_id
    in_month = and_(OvertimeRequest.ot_date >= start, OvertimeRequest.ot_date <= end)

    async def _count(*conditions) -> int:
        return (await db.execute(select(func.count(OvertimeRequest.id)).where(mine, *conditions))).scalar() or 0

    # "This month" counts only what HRGA has finally approved — anything
    # still in the chain is reported separately as pending, never folded
    # into an hours figure the employee might read as banked.
    approved_minutes = (await db.execute(
        select(func.coalesce(func.sum(OvertimeRequest.payable_minutes), 0))
        .where(mine, in_month, OvertimeRequest.rz_status == RZ_APPROVED)
    )).scalar() or 0

    planned_minutes = (await db.execute(
        select(func.coalesce(func.sum(OvertimeRequest.planned_minutes), 0))
        .where(mine, in_month, OvertimeRequest.plan_status == PLAN_APPROVED)
    )).scalar() or 0

    pending_approvals = 0
    if actor.is_team_head or actor.is_dept_head or actor.is_hrga_admin:
        pending_approvals = len(await _pending_for_approver(db, actor))

    return {
        "period": {"month": f"{year:04d}-{mon:02d}", "start": start.isoformat(), "end": end.isoformat()},
        "this_month_hours": svc.fmt_hours(approved_minutes),
        "this_month_planned_hours": svc.fmt_hours(planned_minutes),
        "pending_orders": await _count(in_month, OvertimeRequest.plan_status.in_([PLAN_SUBMITTED, PLAN_TH_APPROVED])),
        "pending_realizations": await _count(in_month, OvertimeRequest.rz_status.in_([RZ_SUBMITTED, RZ_TH_APPROVED, RZ_DH_APPROVED])),
        "realizations": await _count(in_month, OvertimeRequest.rz_status == RZ_APPROVED),
        "approved": await _count(in_month, OvertimeRequest.plan_status == PLAN_APPROVED),
        "rejected": await _count(in_month, or_(OvertimeRequest.plan_status == PLAN_REJECTED, OvertimeRequest.rz_status == RZ_REJECTED)),
        "to_be_realized": await _count(
            OvertimeRequest.plan_status == PLAN_APPROVED,
            OvertimeRequest.rz_status.in_([RZ_PENDING, RZ_DRAFT, RZ_REVISION]),
            OvertimeRequest.ot_date <= today,
        ),
        "pending_approvals": pending_approvals,
    }


@router.get("/dashboard/upcoming")
async def upcoming_overtime(
    limit: int = Query(10, le=50),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    """Approved overtime still ahead of the employee (site map A.2)."""
    result = await db.execute(
        select(OvertimeRequest).where(
            OvertimeRequest.employee_id == actor.employee_id,
            OvertimeRequest.plan_status.in_([PLAN_APPROVED, PLAN_SUBMITTED, PLAN_TH_APPROVED]),
            OvertimeRequest.ot_date >= date.today(),
        ).order_by(OvertimeRequest.ot_date).limit(limit)
    )
    return [
        {
            "id": r.id, "request_no": r.request_no,
            "ot_date": r.ot_date.isoformat(), "overtime_type": r.overtime_type,
            "work_category": r.work_category, "task_description": r.task_description,
            "plan_start": r.plan_start, "plan_finish": r.plan_finish,
            "planned_hours": svc.fmt_hours(r.planned_minutes), "plan_status": r.plan_status,
        }
        for r in result.scalars().all()
    ]


# ─────────────────────────────────────────
# MY OVERTIME ORDER (site map B)
# ─────────────────────────────────────────

@router.get("/orders")
async def list_orders(
    status: Optional[str] = Query(None, description="Comma-separated plan_status values"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    conditions = [OvertimeRequest.employee_id == actor.employee_id]
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        if wanted:
            conditions.append(OvertimeRequest.plan_status.in_(wanted))
    if date_from:
        conditions.append(OvertimeRequest.ot_date >= date.fromisoformat(date_from))
    if date_to:
        conditions.append(OvertimeRequest.ot_date <= date.fromisoformat(date_to))

    result = await db.execute(
        select(OvertimeRequest).where(*conditions).order_by(OvertimeRequest.ot_date.desc(), OvertimeRequest.id.desc())
    )
    rows = list(result.scalars().all())

    counts = {}
    for st in (PLAN_DRAFT, PLAN_SUBMITTED, PLAN_TH_APPROVED, PLAN_REVISION, PLAN_APPROVED, PLAN_REJECTED, PLAN_CANCELLED):
        counts[st] = (await db.execute(
            select(func.count(OvertimeRequest.id)).where(
                OvertimeRequest.employee_id == actor.employee_id, OvertimeRequest.plan_status == st)
        )).scalar() or 0

    return {"orders": [svc.serialize_request(r) for r in rows], "status_counts": counts}


@router.get("/requests/{request_id}")
async def get_request(
    request_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    is_approver = actor.employee_id in {
        req.th_approver_id, req.dh_approver_id, req.rz_th_approver_id, req.rz_dh_approver_id,
    }
    if req.employee_id != actor.employee_id and not is_approver and not actor.is_hrga_admin:
        raise HTTPException(403, "You are not a party to this overtime request.")
    return svc.serialize_request(
        req,
        hours=await _hours(db, req.id),
        attachments=await _attachments(db, req.id),
        logs=await _logs(db, req.id),
    )


async def _apply_order_fields(db: AsyncSession, req: OvertimeRequest, body: OrderIn) -> None:
    """Validate + write the plan half. Shared by create and update so a
    draft edited later gets exactly the same checks as one filed directly."""
    try:
        ot_date = date.fromisoformat(body.ot_date)
    except ValueError:
        raise HTTPException(400, "ot_date must be YYYY-MM-DD")

    if not (body.task_description or "").strip():
        raise HTTPException(400, "Task / target result is required.")
    if body.work_category not in ("adhoc", "routine"):
        raise HTTPException(400, "work_category must be 'adhoc' or 'routine'")

    planned = svc.duration_minutes(body.plan_start, body.plan_finish)
    if planned <= 0:
        raise HTTPException(400, "Overtime start and finish must produce a duration greater than zero.")
    if planned > 12 * 60:
        raise HTTPException(400, "Planned overtime cannot exceed 12 hours in one day.")

    # Type is derived from the working calendar rather than trusted from the
    # client — it drives the statutory multiplier, so a mis-set weekday flag
    # on a public holiday would silently underpay.
    detected = "weekend" if await svc.is_non_working_day(db, ot_date) else "weekday"
    if body.overtime_type and body.overtime_type not in ("weekday", "weekend"):
        raise HTTPException(400, "overtime_type must be 'weekday' or 'weekend'")

    req.overtime_type = detected
    req.work_category = body.work_category
    req.task_description = body.task_description.strip()
    req.ot_date = ot_date
    req.work_start = body.work_start
    req.work_finish = body.work_finish
    req.plan_start = body.plan_start
    req.plan_finish = body.plan_finish
    req.planned_minutes = planned


async def _assign_approvers(db: AsyncSession, actor: OvertimeActor, req: OvertimeRequest) -> OvertimeApprovalMatrix:
    matrix = await _matrix_for(db, req.employee_id)
    if not matrix or not matrix.is_active:
        raise HTTPException(
            400,
            "No approval matrix is configured for you. Ask HRGA to set your Team Head and "
            "Department Head under Overtime > System Setting > Approval Matrix.",
        )
    if not matrix.team_head_id or not matrix.dept_head_id:
        raise HTTPException(400, "Your approval matrix is incomplete — both a Team Head and a Department Head are required.")
    if matrix.team_head_id == req.employee_id or matrix.dept_head_id == req.employee_id:
        raise HTTPException(400, "Your approval matrix names you as your own approver. Ask HRGA to correct it.")

    _, th_name = await svc.email_for_employee(db, matrix.team_head_id)
    _, dh_name = await svc.email_for_employee(db, matrix.dept_head_id)
    req.th_approver_id, req.th_approver_name = matrix.team_head_id, th_name
    req.dh_approver_id, req.dh_approver_name = matrix.dept_head_id, dh_name
    return matrix


async def _notify_approver(db: AsyncSession, req: OvertimeRequest, approver_id: str, what: str) -> None:
    email, _name = await svc.email_for_employee(db, approver_id)
    if what.lower().endswith("realization"):
        window = (f"actual {req.actual_start}-{req.actual_finish}, {svc.fmt_hours(req.actual_minutes)}h "
                  f"vs {svc.fmt_hours(req.planned_minutes)}h planned")
    else:
        window = f"{req.plan_start}-{req.plan_finish}, {svc.fmt_hours(req.planned_minutes)}h"
    await svc.notify(
        db, event_key="need_approval", recipient_email=email, recipient_id=approver_id,
        title=f"{what} needs your approval — {req.request_no}",
        body=f"{req.employee_name} submitted {what.lower()} for {req.ot_date:%d %b %Y} "
             f"({window}). Task: {req.task_description}",
        req=req,
    )


@router.post("/orders")
async def create_order(
    body: OrderIn,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    emp = svc.require_employee(actor)
    try:
        numbering_date = date.fromisoformat(body.ot_date)
    except (ValueError, TypeError):
        raise HTTPException(400, "ot_date must be YYYY-MM-DD")
    req = OvertimeRequest(
        request_no=await svc.next_request_no(db, numbering_date),
        employee_id=emp.user_id, employee_name=emp.full_name, employee_email=actor.email,
        department=emp.department, division=emp.division, team=emp.team,
        plan_status=PLAN_DRAFT, rz_status=RZ_PENDING, created_by=actor.email,
        task_description="", ot_date=date.today(),
    )
    await _apply_order_fields(db, req, body)
    db.add(req)
    await db.flush()
    svc.log_action(db, req, actor, "plan", "create")

    if body.submit:
        await _submit_plan(db, actor, req)
    return svc.serialize_request(req)


@router.put("/orders/{request_id}")
async def update_order(
    request_id: int,
    body: OrderIn,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    if req.plan_status not in _PLAN_EDITABLE:
        raise HTTPException(400, f"An order in status '{req.plan_status}' can no longer be edited.")

    await _apply_order_fields(db, req, body)
    svc.log_action(db, req, actor, "plan", "update")
    if body.submit:
        await _submit_plan(db, actor, req)
    await db.flush()
    return svc.serialize_request(req)


async def _submit_plan(db: AsyncSession, actor: OvertimeActor, req: OvertimeRequest) -> None:
    if req.plan_status not in _PLAN_EDITABLE:
        raise HTTPException(400, f"An order in status '{req.plan_status}' cannot be submitted.")
    await _assign_approvers(db, actor, req)
    req.plan_status = PLAN_SUBMITTED
    req.plan_submitted_at = datetime.utcnow()
    # Clear any previous rejection so a resubmitted revision doesn't keep
    # showing the old decision alongside its new pending state.
    req.th_decision = req.dh_decision = None
    req.th_decision_at = req.dh_decision_at = None
    svc.log_action(db, req, actor, "plan", "submit")
    await db.flush()
    await _notify_approver(db, req, req.th_approver_id, "Overtime order")


@router.post("/orders/{request_id}/submit")
async def submit_order(
    request_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    await _submit_plan(db, actor, req)
    return svc.serialize_request(req)


@router.post("/orders/{request_id}/cancel")
async def cancel_order(
    request_id: int,
    body: CancelIn,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    if req.rz_status in (RZ_SUBMITTED, RZ_TH_APPROVED, RZ_DH_APPROVED, RZ_APPROVED):
        raise HTTPException(400, "This overtime has already been realized — it can no longer be cancelled.")
    if req.plan_status in (PLAN_CANCELLED, PLAN_REJECTED):
        raise HTTPException(400, f"Order is already {req.plan_status}.")
    req.plan_status = PLAN_CANCELLED
    req.cancelled_at = datetime.utcnow()
    req.cancel_reason = body.reason
    svc.log_action(db, req, actor, "plan", "cancel", body.reason)
    return svc.serialize_request(req)


@router.delete("/orders/{request_id}")
async def delete_order(
    request_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    """Only an untouched draft can be deleted — anything that has ever been
    submitted is cancelled instead, so the audit trail survives."""
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    if req.plan_status != PLAN_DRAFT:
        raise HTTPException(400, "Only a draft can be deleted. Cancel the order instead.")
    await db.delete(req)
    return {"message": "Draft deleted"}


# ─────────────────────────────────────────
# REALIZATION (site map C)
# ─────────────────────────────────────────

@router.get("/realizations")
async def list_realizations(
    status: Optional[str] = Query(None, description="Comma-separated rz_status values"),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    """My realizations, plus the "To Be Realized" queue — approved orders
    whose date has arrived and that still have nothing filled in."""
    conditions = [
        OvertimeRequest.employee_id == actor.employee_id,
        OvertimeRequest.plan_status == PLAN_APPROVED,
    ]
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        if wanted:
            conditions.append(OvertimeRequest.rz_status.in_(wanted))

    result = await db.execute(
        select(OvertimeRequest).where(*conditions).order_by(OvertimeRequest.ot_date.desc(), OvertimeRequest.id.desc())
    )
    rows = list(result.scalars().all())

    counts = {}
    for st in (RZ_PENDING, RZ_DRAFT, RZ_SUBMITTED, RZ_TH_APPROVED, RZ_DH_APPROVED, RZ_REVISION, RZ_APPROVED, RZ_REJECTED):
        counts[st] = (await db.execute(
            select(func.count(OvertimeRequest.id)).where(
                OvertimeRequest.employee_id == actor.employee_id,
                OvertimeRequest.plan_status == PLAN_APPROVED,
                OvertimeRequest.rz_status == st)
        )).scalar() or 0
    counts["to_be_realized"] = (await db.execute(
        select(func.count(OvertimeRequest.id)).where(
            OvertimeRequest.employee_id == actor.employee_id,
            OvertimeRequest.plan_status == PLAN_APPROVED,
            OvertimeRequest.rz_status.in_([RZ_PENDING, RZ_DRAFT, RZ_REVISION]),
            OvertimeRequest.ot_date <= date.today())
    )).scalar() or 0

    out = []
    for r in rows:
        item = svc.serialize_request(r, hours=await _hours(db, r.id), attachments=await _attachments(db, r.id))
        item["to_be_realized"] = (
            r.rz_status in (RZ_PENDING, RZ_DRAFT, RZ_REVISION) and r.ot_date <= date.today()
        )
        out.append(item)
    return {"realizations": out, "status_counts": counts}


@router.put("/realizations/{request_id}")
async def save_realization(
    request_id: int,
    body: RealizationIn,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    if req.plan_status != PLAN_APPROVED:
        raise HTTPException(400, "Only an approved overtime order can be realized.")
    if req.rz_status not in _RZ_EDITABLE:
        raise HTTPException(400, f"A realization in status '{req.rz_status}' can no longer be edited.")
    if req.ot_date > date.today():
        raise HTTPException(400, "Overtime cannot be realized before the day it was planned for.")

    actual = svc.duration_minutes(body.actual_start, body.actual_finish)
    req.actual_start = body.actual_start
    req.actual_finish = body.actual_finish
    req.actual_minutes = actual
    req.gap_minutes = actual - (req.planned_minutes or 0)
    req.gap_reason = (body.gap_reason or "").strip() or None

    # Weekend / public-holiday overtime is justified hour by hour; weekday
    # overtime is not, so any hour rows sent for it are ignored rather than
    # stored and silently shown on a screen that never asks for them.
    await db.execute(
        OvertimeHourDetail.__table__.delete().where(OvertimeHourDetail.request_id == req.id)
    )
    if req.overtime_type == "weekend":
        for h in body.hour_details:
            if not ((h.detail or "").strip() or h.start_time or h.finish_time):
                continue
            db.add(OvertimeHourDetail(
                request_id=req.id, hour_no=h.hour_no, detail=(h.detail or "").strip() or None,
                start_time=h.start_time, finish_time=h.finish_time,
            ))

    if req.rz_status == RZ_PENDING:
        req.rz_status = RZ_DRAFT
    svc.log_action(db, req, actor, "realization", "update")
    await db.flush()

    if body.submit:
        await _submit_realization(db, actor, req)
    return svc.serialize_request(req, hours=await _hours(db, req.id), attachments=await _attachments(db, req.id))


async def _submit_realization(db: AsyncSession, actor: OvertimeActor, req: OvertimeRequest) -> None:
    if req.rz_status not in _RZ_EDITABLE:
        raise HTTPException(400, f"A realization in status '{req.rz_status}' cannot be submitted.")
    if not req.actual_start or not req.actual_finish or (req.actual_minutes or 0) <= 0:
        raise HTTPException(400, "Fill in the actual start and finish time before submitting.")
    # A gap in either direction changes what gets paid, so it always needs a
    # written explanation — that is the whole point of the gap column.
    if abs(req.gap_minutes or 0) >= 15 and not (req.gap_reason or "").strip():
        raise HTTPException(400, "Actual time differs from the plan by 15 minutes or more — a reason is required.")
    if req.overtime_type == "weekend":
        hours = await _hours(db, req.id)
        if not hours:
            raise HTTPException(400, "Weekend / public-holiday overtime requires an hour-by-hour detail before submission.")
    attachments = await _attachments(db, req.id)
    if not attachments:
        raise HTTPException(400, "Attach at least one work evidence / supporting document before submitting.")

    # The realization follows the same two heads who approved the plan.
    req.rz_th_approver_id, req.rz_th_approver_name = req.th_approver_id, req.th_approver_name
    req.rz_dh_approver_id, req.rz_dh_approver_name = req.dh_approver_id, req.dh_approver_name
    req.rz_status = RZ_SUBMITTED
    req.rz_submitted_at = datetime.utcnow()
    req.rz_th_decision = req.rz_dh_decision = req.hr_decision = None
    req.rz_th_decision_at = req.rz_dh_decision_at = req.hr_decision_at = None
    svc.log_action(db, req, actor, "realization", "submit")
    await db.flush()
    await _notify_approver(db, req, req.rz_th_approver_id, "Overtime realization")


@router.post("/realizations/{request_id}/submit")
async def submit_realization(
    request_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    await _submit_realization(db, actor, req)
    return svc.serialize_request(req)


# ─────────────────────────────────────────
# EVIDENCE / SUPPORTING DOCUMENTS (site map C.4)
# ─────────────────────────────────────────

@router.post("/requests/{request_id}/attachments")
async def upload_attachment(
    request_id: int,
    file: UploadFile = File(...),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await _load(db, request_id)
    _assert_owner(actor, req)
    if req.rz_status not in _RZ_EDITABLE:
        raise HTTPException(400, "Evidence can only be attached while the realization is still editable.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EVIDENCE_EXT:
        raise HTTPException(400, f"File type '{ext or 'unknown'}' is not allowed. Allowed: {', '.join(sorted(_ALLOWED_EVIDENCE_EXT))}")
    content = await file.read()
    if len(content) > _MAX_EVIDENCE_BYTES:
        raise HTTPException(400, f"File is larger than {_MAX_EVIDENCE_BYTES // (1024 * 1024)} MB.")
    if not content:
        raise HTTPException(400, "File is empty.")

    stored = f"{req.id}_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(_EVIDENCE_DIR, stored), "wb") as f:
        f.write(content)

    row = OvertimeAttachment(
        request_id=req.id, original_name=file.filename or stored, stored_name=stored,
        content_type=file.content_type, size_bytes=len(content), uploaded_by=actor.email,
    )
    db.add(row)
    await db.flush()
    return {"id": row.id, "original_name": row.original_name, "size_bytes": row.size_bytes}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(OvertimeAttachment).where(OvertimeAttachment.id == attachment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Attachment not found")
    req = await _load(db, row.request_id)
    is_approver = actor.employee_id in {req.th_approver_id, req.dh_approver_id, req.rz_th_approver_id, req.rz_dh_approver_id}
    if req.employee_id != actor.employee_id and not is_approver and not actor.is_hrga_admin:
        raise HTTPException(403, "You are not a party to this overtime request.")

    path = os.path.join(_EVIDENCE_DIR, row.stored_name)
    if not os.path.exists(path):
        raise HTTPException(404, "Attachment file is missing on the server.")
    with open(path, "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type=row.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.original_name}"'},
    )


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(OvertimeAttachment).where(OvertimeAttachment.id == attachment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Attachment not found")
    req = await _load(db, row.request_id)
    _assert_owner(actor, req)
    if req.rz_status not in _RZ_EDITABLE:
        raise HTTPException(400, "Evidence can only be removed while the realization is still editable.")
    path = os.path.join(_EVIDENCE_DIR, row.stored_name)
    await db.delete(row)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass  # DB row is gone; a stray file on disk is not worth failing the request
    return {"message": "Attachment removed"}


# ─────────────────────────────────────────
# APPROVAL INBOX (site map B.3/B.4, C.6/C.7/C.8)
# ─────────────────────────────────────────

async def _pending_for_approver(db: AsyncSession, actor: OvertimeActor) -> list[OvertimeRequest]:
    """Everything currently sitting on this person's desk, across both
    chains and every level they hold."""
    me = actor.employee_id
    clauses = []
    if me:
        clauses += [
            and_(OvertimeRequest.plan_status == PLAN_SUBMITTED, OvertimeRequest.th_approver_id == me),
            and_(OvertimeRequest.plan_status == PLAN_TH_APPROVED, OvertimeRequest.dh_approver_id == me),
            and_(OvertimeRequest.rz_status == RZ_SUBMITTED, OvertimeRequest.rz_th_approver_id == me),
            and_(OvertimeRequest.rz_status == RZ_TH_APPROVED, OvertimeRequest.rz_dh_approver_id == me),
        ]
    if actor.is_hrga_admin:
        clauses.append(OvertimeRequest.rz_status == RZ_DH_APPROVED)
    if not clauses:
        return []
    result = await db.execute(
        select(OvertimeRequest).where(or_(*clauses)).order_by(OvertimeRequest.ot_date, OvertimeRequest.id)
    )
    return list(result.scalars().all())


def _stage_of(req: OvertimeRequest, actor: OvertimeActor) -> tuple[str, str]:
    """(stage, level) this request is waiting on for this actor."""
    me = actor.employee_id
    if req.plan_status == PLAN_SUBMITTED and (me == req.th_approver_id or actor.is_hrga_admin):
        return "plan", ROLE_TEAM_HEAD
    if req.plan_status == PLAN_TH_APPROVED and (me == req.dh_approver_id or actor.is_hrga_admin):
        return "plan", ROLE_DEPT_HEAD
    if req.rz_status == RZ_SUBMITTED and (me == req.rz_th_approver_id or actor.is_hrga_admin):
        return "realization", ROLE_TEAM_HEAD
    if req.rz_status == RZ_TH_APPROVED and (me == req.rz_dh_approver_id or actor.is_hrga_admin):
        return "realization", ROLE_DEPT_HEAD
    if req.rz_status == RZ_DH_APPROVED and actor.is_hrga_admin:
        return "realization", "hrga"
    return "", ""


@router.get("/approvals")
async def approval_inbox(
    stage: Optional[str] = Query(None, description="plan | realization"),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    rows = await _pending_for_approver(db, actor)
    out = []
    for r in rows:
        st, level = _stage_of(r, actor)
        if not st or (stage and st != stage):
            continue
        item = svc.serialize_request(r, hours=await _hours(db, r.id), attachments=await _attachments(db, r.id))
        item["awaiting_stage"] = st
        item["awaiting_level"] = level
        out.append(item)
    return {
        "approvals": out,
        "counts": {
            "plan": sum(1 for i in out if i["awaiting_stage"] == "plan"),
            "realization": sum(1 for i in out if i["awaiting_stage"] == "realization"),
            "total": len(out),
        },
    }


@router.get("/approvals/history")
async def approval_history(
    limit: int = Query(200, le=500),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    """Requests this person has already decided on — the other half of the
    inbox, so an approver can look up what they signed off last month."""
    me = actor.employee_id
    if not me:
        return {"history": []}
    result = await db.execute(
        select(OvertimeRequest).where(or_(
            and_(OvertimeRequest.th_approver_id == me, OvertimeRequest.th_decision.is_not(None)),
            and_(OvertimeRequest.dh_approver_id == me, OvertimeRequest.dh_decision.is_not(None)),
            and_(OvertimeRequest.rz_th_approver_id == me, OvertimeRequest.rz_th_decision.is_not(None)),
            and_(OvertimeRequest.rz_dh_approver_id == me, OvertimeRequest.rz_dh_decision.is_not(None)),
        )).order_by(OvertimeRequest.updated_at.desc()).limit(limit)
    )
    return {"history": [svc.serialize_request(r) for r in result.scalars().all()]}


async def _finalize_hrga(db: AsyncSession, req: OvertimeRequest, payable_override: Optional[int]) -> None:
    """Freeze what actually gets paid. Runs once, at HRGA final approval."""
    payable = req.actual_minutes or 0
    if payable_override is not None:
        if payable_override < 0:
            raise HTTPException(400, "payable_minutes cannot be negative.")
        if payable_override > (req.actual_minutes or 0):
            raise HTTPException(400, "payable_minutes cannot exceed the actual minutes worked.")
        payable = payable_override
    req.payable_minutes = payable
    req.overtime_index = svc.overtime_index(payable, req.overtime_type == "weekend")
    rate = await _resolve_rate(db, req.employee_id)
    req.hourly_rate = rate
    req.estimated_cost = (Decimal(req.overtime_index) * rate).quantize(Decimal("0.01"))


@router.post("/approvals/{request_id}/decide")
async def decide(
    request_id: int,
    body: DecisionIn,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    """One endpoint for every approval step — which step it is comes from
    the request's own state, not from the client, so a stale browser tab can
    never push a request through a level it has already passed."""
    if body.decision not in ("approve", "reject", "revision"):
        raise HTTPException(400, "decision must be 'approve', 'reject' or 'revision'")
    if body.decision in ("reject", "revision") and not (body.note or "").strip():
        raise HTTPException(400, "A note is required when rejecting or requesting a revision.")

    req = await _load(db, request_id)
    svc.assert_not_self_approval(actor, req)
    stage, level = _stage_of(req, actor)
    if not stage:
        raise HTTPException(403, "This request is not waiting for your approval.")

    note = (body.note or "").strip() or None
    now = datetime.utcnow()
    approved = body.decision == "approve"
    next_approver_id: Optional[str] = None
    what = "Overtime order" if stage == "plan" else "Overtime realization"

    if stage == "plan":
        if not _can_act_as(actor, req.th_approver_id if level == ROLE_TEAM_HEAD else req.dh_approver_id):
            raise HTTPException(403, "You are not the assigned approver for this step.")
        if level == ROLE_TEAM_HEAD:
            req.th_approver_id = req.th_approver_id or actor.employee_id
            req.th_approver_name = req.th_approver_name or actor.full_name
            req.th_decision, req.th_decision_at, req.th_note = body.decision, now, note
            req.plan_status = PLAN_TH_APPROVED if approved else (PLAN_REVISION if body.decision == "revision" else PLAN_REJECTED)
            next_approver_id = req.dh_approver_id if approved else None
        else:
            req.dh_approver_id = req.dh_approver_id or actor.employee_id
            req.dh_approver_name = req.dh_approver_name or actor.full_name
            req.dh_decision, req.dh_decision_at, req.dh_note = body.decision, now, note
            req.plan_status = PLAN_APPROVED if approved else (PLAN_REVISION if body.decision == "revision" else PLAN_REJECTED)
    else:
        if level == ROLE_TEAM_HEAD:
            if not _can_act_as(actor, req.rz_th_approver_id):
                raise HTTPException(403, "You are not the assigned approver for this step.")
            req.rz_th_decision, req.rz_th_decision_at, req.rz_th_note = body.decision, now, note
            req.rz_status = RZ_TH_APPROVED if approved else (RZ_REVISION if body.decision == "revision" else RZ_REJECTED)
            next_approver_id = req.rz_dh_approver_id if approved else None
        elif level == ROLE_DEPT_HEAD:
            if not _can_act_as(actor, req.rz_dh_approver_id):
                raise HTTPException(403, "You are not the assigned approver for this step.")
            req.rz_dh_decision, req.rz_dh_decision_at, req.rz_dh_note = body.decision, now, note
            req.rz_status = RZ_DH_APPROVED if approved else (RZ_REVISION if body.decision == "revision" else RZ_REJECTED)
        else:  # HRGA final check
            if not actor.is_hrga_admin:
                raise HTTPException(403, "Only HRGA can perform the final check.")
            req.hr_approver_id, req.hr_approver_name = actor.employee_id, actor.full_name
            req.hr_decision, req.hr_decision_at, req.hr_note = body.decision, now, note
            if approved:
                await _finalize_hrga(db, req, body.payable_minutes)
                req.rz_status = RZ_APPROVED
            else:
                req.payable_minutes = 0
                req.overtime_index = Decimal(0)
                req.estimated_cost = Decimal(0)
                req.rz_status = RZ_REVISION if body.decision == "revision" else RZ_REJECTED

    svc.log_action(db, req, actor, stage, body.decision, note)
    await db.flush()

    if approved and next_approver_id:
        await _notify_approver(db, req, next_approver_id, what)
    else:
        event = "approval" if approved else ("adjustment" if body.decision == "revision" else "rejection")
        verb = {"approval": "approved", "adjustment": "sent back for revision", "rejection": "rejected"}[event]
        await svc.notify(
            db, event_key=event, recipient_email=req.employee_email, recipient_id=req.employee_id,
            title=f"{what} {verb} — {req.request_no}",
            body=f"{actor.full_name} {verb} your {what.lower()} for {req.ot_date:%d %b %Y}."
                 + (f" Note: {note}" if note else ""),
            req=req,
        )
    return svc.serialize_request(req)


# ─────────────────────────────────────────
# NOTIFICATIONS (site map E)
# ─────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(100, le=300),
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    conditions = [OvertimeNotification.recipient_email == actor.email]
    if unread_only:
        conditions.append(OvertimeNotification.is_read.is_(False))
    result = await db.execute(
        select(OvertimeNotification).where(*conditions)
        .order_by(OvertimeNotification.created_at.desc(), OvertimeNotification.id.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    unread = (await db.execute(
        select(func.count(OvertimeNotification.id)).where(
            OvertimeNotification.recipient_email == actor.email, OvertimeNotification.is_read.is_(False))
    )).scalar() or 0
    return {
        "unread": unread,
        "notifications": [
            {"id": n.id, "event_key": n.event_key, "title": n.title, "body": n.body,
             "request_id": n.request_id, "request_no": n.request_no, "is_read": n.is_read,
             "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in rows
        ],
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(OvertimeNotification).where(
        OvertimeNotification.id == notification_id,
        OvertimeNotification.recipient_email == actor.email,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Notification not found")
    row.is_read = True
    return {"message": "Marked as read"}


@router.post("/notifications/read-all")
async def mark_all_read(
    actor: OvertimeActor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OvertimeNotification).where(
        OvertimeNotification.recipient_email == actor.email, OvertimeNotification.is_read.is_(False)))
    rows = list(result.scalars().all())
    for r in rows:
        r.is_read = True
    return {"message": f"{len(rows)} notification(s) marked as read"}
