from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/headcount")
async def employee_headcount(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               e.dept_group, e.headcount, e.plan_headcount, e.resigned_cumulative,
               CASE WHEN e.plan_headcount > 0
                    THEN ROUND((e.headcount::numeric / e.plan_headcount * 100), 2)
                    ELSE 0 END as achievement_pct
        FROM eis.fact_employee e
        JOIN eis.dim_period per ON e.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num, e.dept_group
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/turnover")
async def turnover_rate(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               SUM(e.headcount) as total_headcount,
               MAX(e.resigned_cumulative) as resigned_cumulative,
               CASE WHEN SUM(e.headcount) > 0
                    THEN ROUND((MAX(e.resigned_cumulative)::numeric / SUM(e.headcount) * 100), 2)
                    ELSE 0 END as turnover_pct
        FROM eis.fact_employee e
        JOIN eis.dim_period per ON e.period_id = per.id
        WHERE per.fiscal_year = :year
        GROUP BY per.period_num, per.period_name
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


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
