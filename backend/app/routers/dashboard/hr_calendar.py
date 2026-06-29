"""
HR Working Calendar Router
Route prefix: /api/v1/dashboard/hr/calendar
Manage holidays (national, collective, company) and compute working days.
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, extract, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.working_calendar import WorkingCalendarHoliday

router = APIRouter()


class HolidayCreate(BaseModel):
    holiday_date: str
    name: str
    holiday_type: str


@router.get("/holidays")
async def get_holidays(
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(
        select(WorkingCalendarHoliday)
        .where(extract("year", WorkingCalendarHoliday.holiday_date) == year)
        .order_by(WorkingCalendarHoliday.holiday_date)
    )
    rows = result.scalars().all()
    return [
        {"id": r.id, "holiday_date": r.holiday_date.isoformat(), "name": r.name, "holiday_type": r.holiday_type}
        for r in rows
    ]


@router.post("/holidays")
async def add_holiday(
    body: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    from datetime import datetime
    try:
        dt = datetime.strptime(body.holiday_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")

    if body.holiday_type not in ("national", "collective", "company"):
        raise HTTPException(400, "Type must be national, collective, or company")

    existing = await db.execute(
        select(WorkingCalendarHoliday).where(WorkingCalendarHoliday.holiday_date == dt)
    )
    if existing.scalars().first():
        raise HTTPException(409, f"Holiday on {body.holiday_date} already exists")

    h = WorkingCalendarHoliday(holiday_date=dt, name=body.name, holiday_type=body.holiday_type)
    db.add(h)
    await db.flush()
    return {"id": h.id, "holiday_date": h.holiday_date.isoformat(), "name": h.name, "holiday_type": h.holiday_type}


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(WorkingCalendarHoliday).where(WorkingCalendarHoliday.id == holiday_id))
    row = result.scalars().first()
    if not row:
        raise HTTPException(404, "Holiday not found")
    await db.delete(row)
    return {"message": "Deleted"}


@router.get("/summary")
async def get_calendar_summary(
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(
        select(WorkingCalendarHoliday)
        .where(extract("year", WorkingCalendarHoliday.holiday_date) == year)
    )
    holidays = result.scalars().all()

    holiday_map = {}
    for h in holidays:
        holiday_map[h.holiday_date] = h.holiday_type

    months = []
    for m in range(1, 13):
        first = date(year, m, 1)
        if m == 12:
            last = date(year, 12, 31)
        else:
            last = date(year, m + 1, 1) - timedelta(days=1)

        cal_days = (last - first).days + 1
        weekends = 0
        national = 0
        collective = 0
        company = 0

        d = first
        while d <= last:
            wd = d.weekday()
            if wd >= 5:
                weekends += 1
            elif d in holiday_map:
                t = holiday_map[d]
                if t == "national":
                    national += 1
                elif t == "collective":
                    collective += 1
                elif t == "company":
                    company += 1
            d += timedelta(days=1)

        working = cal_days - weekends - national - collective - company
        months.append({
            "month": m,
            "calendar_days": cal_days,
            "weekends": weekends,
            "national": national,
            "collective": collective,
            "company": company,
            "working_days": working,
        })

    totals = {k: sum(m[k] for m in months) for k in ["calendar_days", "weekends", "national", "collective", "company", "working_days"]}

    return {"year": year, "months": months, "totals": totals}
