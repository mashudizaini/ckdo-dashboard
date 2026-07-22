from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/batch")
async def batch_production(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name, p.segment,
               p.bp_qty, p.actual_qty,
               CASE WHEN p.bp_qty > 0 THEN ROUND((p.actual_qty / p.bp_qty * 100)::numeric, 2) ELSE 0 END as achievement_pct
        FROM eis.fact_production p
        JOIN eis.dim_period per ON p.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num, p.segment
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/yield")
async def yield_production(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               SUM(p.batch_size) as batch_size, SUM(p.yield_qty) as yield_qty,
               CASE WHEN SUM(p.batch_size) > 0
                    THEN ROUND((SUM(p.yield_qty) / SUM(p.batch_size) * 100)::numeric, 2)
                    ELSE 0 END as yield_pct
        FROM eis.fact_production p
        JOIN eis.dim_period per ON p.period_id = per.id
        WHERE per.fiscal_year = :year
        GROUP BY per.period_num, per.period_name
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/dio")
async def days_inventory_outstanding(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               fr.dio_cogs, fr.dio_inv_avg, fr.dio_days
        FROM eis.fact_financial_ratio fr
        JOIN eis.dim_period per ON fr.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/cogs-ratio")
async def cogs_ratio(
    year: int = Query(2025), period: int = Query(11),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT p.product_name,
               SUM(c.sales_amount) as net_sales, SUM(c.cogs_total) as cogs,
               CASE WHEN SUM(c.sales_amount) > 0
                    THEN ROUND((SUM(c.cogs_total) / SUM(c.sales_amount))::numeric, 4)
                    ELSE 0 END as cogs_rate
        FROM eis.fact_cogs c
        JOIN eis.dim_product p ON c.product_id = p.id
        JOIN eis.dim_period per ON c.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num <= :period
        GROUP BY p.product_name
        HAVING SUM(c.sales_amount) > 0
        ORDER BY cogs_rate DESC
    """)
    result = await db.execute(q, {"year": year, "period": period})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/overtime")
async def overtime_ratio(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               o.overtime_hours, o.working_hours,
               CASE WHEN (o.working_hours + o.overtime_hours) > 0
                    THEN ROUND((o.overtime_hours / (o.working_hours + o.overtime_hours) * 100)::numeric, 2)
                    ELSE 0 END as ratio_pct
        FROM eis.fact_overtime o
        JOIN eis.dim_period per ON o.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/release-time")
async def product_release_time(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT per.period_num, per.period_name,
               pr.target_days, pr.actual_days
        FROM eis.fact_product_release pr
        JOIN eis.dim_period per ON pr.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}
