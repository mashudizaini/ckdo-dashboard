"""
HR Department Initiatives Router
Route prefix : /api/v1/dashboard/hr/budget/initiatives

Tracks named HR department initiatives/projects against a monthly budget
vs actual spend and a manually-set completion status — feeds the
"Department Initiatives" sub-tab under Budget Monitoring (status donut,
monthly budget vs actual bar chart, initiatives table). Independent of the
Oracle-synced GL Budget Monitoring section (hr_budget.py) — this is
user-entered data, not pulled from GL_BALANCES.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.hr_initiative import HRInitiative

router = APIRouter()

STATUSES = ("on_track", "behind_schedule", "revised_schedule")
MONTHS = 12


class InitiativePayload(BaseModel):
    year: int
    name: str
    status: str = "on_track"
    percent_complete: int = Field(0, ge=0, le=100)
    monthly_budget: list[float] = Field(default_factory=lambda: [0.0] * MONTHS)
    monthly_actual: list[float] = Field(default_factory=lambda: [0.0] * MONTHS)
    notes: str = ""


def _validate_status(status: str):
    if status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {STATUSES}")


def _validate_months(values: list[float], field: str):
    if len(values) != MONTHS:
        raise HTTPException(status_code=422, detail=f"{field} must have exactly {MONTHS} values (Jan-Dec)")


def _to_dict(row: HRInitiative) -> dict:
    monthly_budget = row.monthly_budget or [0.0] * MONTHS
    monthly_actual = row.monthly_actual or [0.0] * MONTHS
    return {
        "id":                row.id,
        "year":              row.year,
        "name":              row.name,
        "status":            row.status,
        "percent_complete":  row.percent_complete,
        "monthly_budget":    monthly_budget,
        "monthly_actual":    monthly_actual,
        "budget":            round(sum(monthly_budget), 2),
        "actual":            round(sum(monthly_actual), 2),
        "notes":             row.notes or "",
        "created_by":        row.created_by,
        "created_at":        row.created_at.isoformat() if row.created_at else None,
        "updated_at":        row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/years")
async def get_initiative_years(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(HRInitiative.year).distinct())
    years = sorted({r[0] for r in result.fetchall()}, reverse=True)
    return years or [datetime.now().year]


@router.get("")
async def list_initiatives(
    year: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(
        select(HRInitiative).where(HRInitiative.year == year).order_by(HRInitiative.id)
    )
    rows = result.scalars().all()
    initiatives = [_to_dict(r) for r in rows]

    status_summary = {s: 0 for s in STATUSES}
    monthly_totals = {"budget": [0.0] * MONTHS, "actual": [0.0] * MONTHS}
    for it in initiatives:
        status_summary[it["status"]] = status_summary.get(it["status"], 0) + 1
        for i in range(MONTHS):
            monthly_totals["budget"][i] += it["monthly_budget"][i] or 0
            monthly_totals["actual"][i] += it["monthly_actual"][i] or 0
    monthly_totals["budget"] = [round(v, 2) for v in monthly_totals["budget"]]
    monthly_totals["actual"] = [round(v, 2) for v in monthly_totals["actual"]]

    return {
        "year": year,
        "initiatives": initiatives,
        "status_summary": status_summary,
        "monthly_totals": monthly_totals,
    }


@router.post("")
async def create_initiative(
    body: InitiativePayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    _validate_status(body.status)
    _validate_months(body.monthly_budget, "monthly_budget")
    _validate_months(body.monthly_actual, "monthly_actual")
    row = HRInitiative(
        year=body.year,
        name=body.name.strip(),
        status=body.status,
        percent_complete=body.percent_complete,
        monthly_budget=body.monthly_budget,
        monthly_actual=body.monthly_actual,
        notes=body.notes,
        created_by=user.username or "unknown",
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _to_dict(row)


@router.put("/{initiative_id}")
async def update_initiative(
    initiative_id: int,
    body: InitiativePayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    _validate_status(body.status)
    _validate_months(body.monthly_budget, "monthly_budget")
    _validate_months(body.monthly_actual, "monthly_actual")
    row = await db.get(HRInitiative, initiative_id)
    if not row:
        raise HTTPException(status_code=404, detail="Initiative not found")
    row.year = body.year
    row.name = body.name.strip()
    row.status = body.status
    row.percent_complete = body.percent_complete
    row.monthly_budget = body.monthly_budget
    row.monthly_actual = body.monthly_actual
    row.notes = body.notes
    row.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(row)
    return _to_dict(row)


@router.delete("/{initiative_id}")
async def delete_initiative(
    initiative_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    row = await db.get(HRInitiative, initiative_id)
    if not row:
        raise HTTPException(status_code=404, detail="Initiative not found")
    await db.delete(row)
    return {"message": "Deleted"}
