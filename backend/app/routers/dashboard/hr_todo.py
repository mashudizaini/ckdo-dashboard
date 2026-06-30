"""
HRGA To Do List Router
Route prefix: /api/v1/dashboard/hr/todo

Implements 3 features from the HRGA To Do List request form:
  1. HRGA To Do List (Manager / Supervisor / Officer)
  2. HRGA e-Calendar — same tasks, viewed by due date in the frontend
  3. HRGA TOP Vendor Alert — flag vendor-related tasks due within 7 days, not completed
"""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.hrga_task import HrgaTask

router = APIRouter()

VENDOR_ALERT_DAYS = 7


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_vendor: bool = False
    assigned_to: Optional[str] = None
    role: Optional[str] = None
    status: str = "Not Started"
    due_date: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_vendor: Optional[bool] = None
    assigned_to: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")


def _vendor_alert_days_left(t: HrgaTask) -> Optional[int]:
    if not t.is_vendor or not t.due_date or t.status == "Completed":
        return None
    return (t.due_date - date.today()).days


def _to_dict(t: HrgaTask) -> dict:
    days_left = _vendor_alert_days_left(t)
    is_overdue = t.due_date is not None and t.due_date < date.today() and t.status != "Completed"
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "is_vendor": t.is_vendor,
        "assigned_to": t.assigned_to,
        "role": t.role,
        "status": t.status,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "is_overdue": is_overdue,
        "vendor_alert": days_left is not None and 0 <= days_left <= VENDOR_ALERT_DAYS,
        "vendor_days_left": days_left,
    }


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    vendor_only: bool = Query(False),
    search: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    conditions = []
    if status:
        conditions.append(HrgaTask.status == status)
    if role:
        conditions.append(HrgaTask.role == role)
    if category:
        conditions.append(HrgaTask.category == category)
    if vendor_only:
        conditions.append(HrgaTask.is_vendor.is_(True))
    if search:
        pat = f"%{search}%"
        conditions.append(HrgaTask.title.ilike(pat) | HrgaTask.assigned_to.ilike(pat))
    if year:
        conditions.append(extract("year", HrgaTask.due_date) == year)
    if month:
        conditions.append(extract("month", HrgaTask.due_date) == month)

    where = and_(*conditions) if conditions else True
    result = await db.execute(
        select(HrgaTask).where(where).order_by(HrgaTask.due_date.asc().nulls_last(), HrgaTask.id.desc())
    )
    tasks = result.scalars().all()
    return [_to_dict(t) for t in tasks]


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(HrgaTask))
    tasks = result.scalars().all()

    total = len(tasks)
    not_started = sum(1 for t in tasks if t.status == "Not Started")
    in_progress = sum(1 for t in tasks if t.status == "In Progress")
    completed = sum(1 for t in tasks if t.status == "Completed")
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < date.today() and t.status != "Completed")
    vendor_alerts = sum(1 for t in tasks if _vendor_alert_days_left(t) is not None and 0 <= _vendor_alert_days_left(t) <= VENDOR_ALERT_DAYS)

    return {
        "total": total,
        "not_started": not_started,
        "in_progress": in_progress,
        "completed": completed,
        "overdue": overdue,
        "vendor_alerts": vendor_alerts,
    }


@router.post("/tasks")
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    if not body.title.strip():
        raise HTTPException(400, "Title is required")

    t = HrgaTask(
        title=body.title.strip(),
        description=body.description,
        category=body.category,
        is_vendor=body.is_vendor,
        assigned_to=body.assigned_to,
        role=body.role,
        status=body.status or "Not Started",
        due_date=_parse_date(body.due_date),
        created_by=user.username,
    )
    db.add(t)
    await db.flush()
    return _to_dict(t)


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(HrgaTask).where(HrgaTask.id == task_id))
    t = result.scalars().first()
    if not t:
        raise HTTPException(404, "Task not found")

    data = body.model_dump(exclude_unset=True)
    if "due_date" in data:
        data["due_date"] = _parse_date(data["due_date"])

    was_completed = t.status == "Completed"
    for k, v in data.items():
        setattr(t, k, v)

    if t.status == "Completed" and not was_completed:
        t.completed_at = datetime.utcnow()
    elif t.status != "Completed":
        t.completed_at = None

    t.updated_at = datetime.utcnow()
    await db.flush()
    return _to_dict(t)


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(HrgaTask).where(HrgaTask.id == task_id))
    t = result.scalars().first()
    if not t:
        raise HTTPException(404, "Task not found")
    await db.delete(t)
    return {"message": "Deleted"}
