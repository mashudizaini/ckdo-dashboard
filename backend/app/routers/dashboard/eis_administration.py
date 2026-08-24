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
from app.services.financial_statement_upload_service import FinancialStatementUploadService

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
    db: AsyncSession = Depends(get_main_db), user = Depends(get_current_user),
):
    """Actual net profit sourced from Accounting & Tax's Financial Statement
    module (PL_monthly Excel uploads — one snapshot per calendar month,
    each holding a "MTD This Year" net-profit figure keyed by the month it
    represents), instead of the disconnected EIS ETL schema, so this chart
    always agrees with what Accounting sees under Profit or Loss. A month
    nobody has uploaded a PL_monthly snapshot for comes back with a null
    value (no bar), never an estimate."""
    svc = FinancialStatementUploadService()
    snapshots = await svc.list_snapshots(db, "profit_loss_monthly")
    months_in_year = {s["month"] for s in snapshots if s["year"] == year}

    data = []
    for m in range(1, 13):
        net_profit_actual = None
        if m in months_in_year:
            upload = await svc.get_upload(db, "profit_loss_monthly", m, year)
            pat = (upload or {}).get("content", {}).get("profit_after_tax") or []
            # columns = ["MTD Last Year", "YTD Last Year", "MTD This Year", "YTD This Year"]
            net_profit_actual = pat[2] if len(pat) > 2 else None
        data.append({
            "period_num": m, "period_name": _MONTH_NAMES[m - 1],
            "net_profit_actual": net_profit_actual,
        })
    return {"data": data}


@router.get("/cashflow")
async def cashflow(
    year: int = Query(2025),
    eis_db: AsyncSession = Depends(get_db), db: AsyncSession = Depends(get_main_db),
    user = Depends(get_current_user),
):
    """Plan stays sourced from the EIS ETL schema (eis.fact_financial) —
    Accounting & Tax's Financial Statement module has no Plan/Budget figure
    anywhere. Actual is sourced from Financial Statement's Cashflow upload
    (Ending Balance, month-by-month for whichever year is currently
    "in progress" in that sheet — see parse_cash_flow_excel's
    monthly_ending_balance). Re-upload the Cashflow Excel once after this
    ships for the monthly Actual series to populate — earlier uploads were
    parsed before this breakdown was captured."""
    plan_q = text("""
        SELECT per.period_num, per.period_name, f.cf_ending_balance_bp
        FROM eis.fact_financial f
        JOIN eis.dim_period per ON f.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    plan_by_month = {
        r["period_num"]: r for r in (await eis_db.execute(plan_q, {"year": year})).mappings().all()
    }

    upload = await FinancialStatementUploadService().get_upload(db, "cash_flow")
    content = (upload or {}).get("content") or {}
    actual_by_month = {}
    if content.get("partial_year") == year:
        actual_by_month = {item["month"]: item["value"] for item in content.get("monthly_ending_balance", [])}

    data = []
    for m in range(1, 13):
        plan_row = plan_by_month.get(m)
        data.append({
            "period_num": m,
            "period_name": plan_row["period_name"] if plan_row else _MONTH_NAMES[m - 1],
            "cf_ending_balance_bp": float(plan_row["cf_ending_balance_bp"]) if plan_row and plan_row["cf_ending_balance_bp"] is not None else None,
            "cf_ending_balance_actual": actual_by_month.get(m),
        })
    return {"data": data}


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
