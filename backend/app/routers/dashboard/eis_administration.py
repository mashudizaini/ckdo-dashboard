from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db as get_main_db
from app.dependencies import get_current_user
from app.eis_database import get_eis_db as get_db
from app.models.employee import Employee
from app.services.department_taxonomy import CANONICAL_DEPARTMENTS, normalize_department

router = APIRouter()

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


@router.get("/headcount")
async def employee_headcount(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_main_db), user = Depends(get_current_user),
):
    """Sourced from HRGA's Employee master (app.models.employee.Employee),
    not the separate EIS ETL schema — same month-end "active as of" window
    (join date <= month end, resign date null or >= month start) and the
    same 4 canonical department groups as HRGA Employee Data, so this chart
    never disagrees with what HR sees."""
    rows = (await db.execute(
        select(Employee.department, Employee.date_of_joining, Employee.resign_date)
        .where(Employee.date_of_joining.isnot(None))
    )).all()

    data = []
    for m in range(1, 13):
        first_day = date(year, m, 1)
        last_day = date(year, m, monthrange(year, m)[1])
        counts = {g: 0 for g in CANONICAL_DEPARTMENTS}
        for dept, join, resign in rows:
            if join <= last_day and (resign is None or resign >= first_day):
                group = normalize_department(dept)
                if group:
                    counts[group] += 1
        for group, headcount in counts.items():
            data.append({
                "period_num": m, "period_name": _MONTH_NAMES[m - 1],
                "dept_group": group, "headcount": headcount,
            })
    return {"data": data}


@router.get("/turnover")
async def turnover_rate(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_main_db), user = Depends(get_current_user),
):
    """Sourced from HRGA's Employee master — same monthly turnover-rate
    formula (resigns-in-month / average of month-start and month-end
    headcount) as HR Employee Data's /employees/turnover-summary, so the
    two dashboards always agree."""
    rows = (await db.execute(
        select(Employee.date_of_joining, Employee.resign_date)
        .where(Employee.date_of_joining.isnot(None))
    )).all()

    data = []
    for m in range(1, 13):
        first_day = date(year, m, 1)
        last_day = date(year, m, monthrange(year, m)[1])
        resigns_in_month = sum(
            1 for join, resign in rows if resign is not None and first_day <= resign <= last_day
        )
        headcount_start = sum(
            1 for join, resign in rows if join < first_day and (resign is None or resign >= first_day)
        )
        headcount_end = sum(
            1 for join, resign in rows if join <= last_day and (resign is None or resign >= first_day)
        )
        avg_headcount = (headcount_start + headcount_end) / 2 if (headcount_start + headcount_end) > 0 else 0
        turnover_pct = round((resigns_in_month / avg_headcount) * 100, 2) if avg_headcount > 0 else 0
        data.append({
            "period_num": m, "period_name": _MONTH_NAMES[m - 1],
            "total_headcount": headcount_end, "resigned_cumulative": resigns_in_month,
            "turnover_pct": turnover_pct,
        })
    return {"data": data}


@router.get("/profit")
async def net_profit(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               f.net_profit_bp, f.net_profit_actual,
               f.net_profit_bp_cumulative, f.net_profit_actual_cumulative,
               CASE WHEN f.net_profit_bp_cumulative != 0
                    THEN ROUND((f.net_profit_actual_cumulative / f.net_profit_bp_cumulative * 100)::numeric, 2)
                    ELSE 0 END as achievement_pct
        FROM eis.fact_financial f
        JOIN eis.dim_period per ON f.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/cashflow")
async def cashflow(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               f.cf_ending_balance_bp, f.cf_ending_balance_actual,
               CASE WHEN f.cf_ending_balance_bp > 0
                    THEN ROUND((f.cf_ending_balance_actual / f.cf_ending_balance_bp * 100)::numeric, 2)
                    ELSE 0 END as achievement_pct
        FROM eis.fact_financial f
        JOIN eis.dim_period per ON f.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/ratios")
async def financial_ratios(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               fr.dso_days, fr.dpo_days, fr.dio_days,
               ROUND((fr.dso_days + fr.dio_days - fr.dpo_days)::numeric, 2) as nwc_days
        FROM eis.fact_financial_ratio fr
        JOIN eis.dim_period per ON fr.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/budget")
async def budget_utilization(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               b.dept_group, b.bp_amount, b.actual_amount,
               CASE WHEN b.bp_amount > 0
                    THEN ROUND((b.actual_amount / b.bp_amount * 100)::numeric, 2)
                    ELSE 0 END as utilization_pct
        FROM eis.fact_budget b
        JOIN eis.dim_period per ON b.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num, b.dept_group
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}
