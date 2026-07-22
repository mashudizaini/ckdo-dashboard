from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/sales-achievement")
async def sales_achievement(
    year: int = Query(2025), segment: str = Query("all"),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Yearly cumulative sales achievement by segment."""
    seg_filter = "" if segment == "all" else "AND s.business_type = :segment"
    q = text(f"""
        SELECT per.period_num, per.period_name,
               SUM(s.bp_amount) as bp_cumulative,
               SUM(s.actual_amount) as actual_cumulative,
               CASE WHEN SUM(s.bp_amount) > 0
                    THEN ROUND((SUM(s.actual_amount) / SUM(s.bp_amount) * 100)::numeric, 2)
                    ELSE 0 END as achievement_pct
        FROM eis.fact_sales s
        JOIN eis.dim_period per ON s.period_id = per.id
        WHERE per.fiscal_year = :year {seg_filter}
        GROUP BY per.period_num, per.period_name
        ORDER BY per.period_num
    """)
    params = {"year": year}
    if segment != "all":
        params["segment"] = segment
    result = await db.execute(q, params)
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/monthly-sales")
async def monthly_sales(
    year: int = Query(2025), segment: str = Query("all"),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Monthly BP vs Actual sales."""
    seg_filter = "" if segment == "all" else "AND s.business_type = :segment"
    q = text(f"""
        SELECT per.period_num, per.period_name,
               SUM(s.bp_amount) as bp_amount,
               SUM(s.actual_amount) as actual_amount
        FROM eis.fact_sales s
        JOIN eis.dim_period per ON s.period_id = per.id
        WHERE per.fiscal_year = :year {seg_filter}
        GROUP BY per.period_num, per.period_name
        ORDER BY per.period_num
    """)
    params = {"year": year}
    if segment != "all":
        params["segment"] = segment
    result = await db.execute(q, params)
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/growth")
async def sales_growth(
    year: int = Query(2025), segment: str = Query("all"),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Year-over-year growth comparison."""
    seg_filter = "" if segment == "all" else "AND s.business_type = :segment"
    q = text(f"""
        WITH yearly AS (
            SELECT per.fiscal_year, SUM(s.bp_amount) as bp_total, SUM(s.actual_amount) as actual_total
            FROM eis.fact_sales s
            JOIN eis.dim_period per ON s.period_id = per.id
            WHERE per.fiscal_year IN (:year, :prev_year) {seg_filter}
            GROUP BY per.fiscal_year
        )
        SELECT * FROM yearly ORDER BY fiscal_year
    """)
    params = {"year": year, "prev_year": year - 1}
    if segment != "all":
        params["segment"] = segment
    result = await db.execute(q, params)
    rows = [dict(r) for r in result.mappings().all()]
    growth = None
    if len(rows) == 2 and rows[0]["actual_total"] and float(rows[0]["actual_total"]) > 0:
        prev = float(rows[0]["actual_total"])
        curr = float(rows[1]["actual_total"])
        growth = round((curr / prev - 1) * 100, 2)
    return {"data": rows, "growth_pct": growth}


@router.get("/ebit-product")
async def ebit_by_product(
    year: int = Query(2025), period: int = Query(11),
    limit: int = Query(5),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Top N products by sales with their EBIT %."""
    q = text("""
        SELECT p.product_name, p.business_type, p.market,
               SUM(c.sales_amount) as sales,
               SUM(c.ebit_amount) as ebit,
               CASE WHEN SUM(c.sales_amount) > 0
                    THEN ROUND((SUM(c.ebit_amount) / SUM(c.sales_amount) * 100)::numeric, 2)
                    ELSE 0 END as ebit_pct
        FROM eis.fact_cogs c
        JOIN eis.dim_period per ON c.period_id = per.id
        JOIN eis.dim_product p ON c.product_id = p.id
        WHERE per.fiscal_year = :year AND per.period_num <= :period
        GROUP BY p.product_name, p.business_type, p.market
        HAVING SUM(c.sales_amount) > 0
        ORDER BY sales DESC
        LIMIT :limit
    """)
    result = await db.execute(q, {"year": year, "period": period, "limit": limit})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/area-sales")
async def area_sales(
    year: int = Query(2025), period: int = Query(11),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Area sales force performance."""
    q = text("""
        SELECT a.area_name, a.region,
               fas.cumulative_amount, fas.monthly_amount,
               CASE WHEN t.total > 0
                    THEN ROUND((fas.cumulative_amount / t.total * 100)::numeric, 2)
                    ELSE 0 END as portion_pct
        FROM eis.fact_area_sales fas
        JOIN eis.dim_area a ON fas.area_id = a.id
        JOIN eis.dim_period per ON fas.period_id = per.id
        CROSS JOIN (
            SELECT SUM(cumulative_amount) as total
            FROM eis.fact_area_sales
            WHERE period_id = (SELECT id FROM eis.dim_period WHERE fiscal_year = :year AND period_num = :period)
        ) t
        WHERE per.fiscal_year = :year AND per.period_num = :period
        ORDER BY a.sort_order
    """)
    result = await db.execute(q, {"year": year, "period": period})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/marketing")
async def marketing_activities(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Marketing activities (seminars/events + RTD)."""
    q = text("""
        SELECT m.event_type, m.event_name, per.period_num, per.period_name,
               m.plan_amount, m.actual_amount, m.plan_qty, m.actual_qty
        FROM eis.fact_marketing m
        JOIN eis.dim_period per ON m.period_id = per.id
        WHERE per.fiscal_year = :year
        ORDER BY m.event_type, per.period_num
    """)
    result = await db.execute(q, {"year": year})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/forecast")
async def sales_forecast(
    year: int = Query(2025), period: int = Query(12), segment: str = Query("Local"),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Daily sales data for closing estimation."""
    q = text("""
        SELECT d.day_num, d.daily_amount,
               SUM(d.daily_amount) OVER (ORDER BY d.day_num) as cumulative_amount
        FROM eis.fact_sales_daily d
        JOIN eis.dim_period per ON d.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num = :period
          AND d.business_type = :segment
        ORDER BY d.day_num
    """)
    result = await db.execute(q, {"year": year, "period": period, "segment": segment})
    return {"data": [dict(r) for r in result.mappings().all()]}
