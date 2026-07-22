from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/portfolio")
async def get_portfolio(
    year: int = Query(2025),
    period: int = Query(11),
    business: str = Query("Local"),
    market: str = Query("Public"),
    product_code: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Product portfolio profitability for selected product."""
    q = text("""
        SELECT p.product_code, p.product_name,
               c.sales_amount, c.cogs_total, c.opex_amount, c.ebit_amount,
               c.cogs_material, c.cogs_labour, c.cogs_depreciation, c.cogs_foh,
               CASE WHEN c.sales_amount > 0 THEN ROUND((c.cogs_total / c.sales_amount * 100)::numeric, 2) ELSE 0 END as cogs_pct,
               CASE WHEN c.sales_amount > 0 THEN ROUND(((c.sales_amount - c.cogs_total) / c.sales_amount * 100)::numeric, 2) ELSE 0 END as gp_pct,
               CASE WHEN c.sales_amount > 0 THEN ROUND((c.ebit_amount / c.sales_amount * 100)::numeric, 2) ELSE 0 END as ebit_pct
        FROM eis.fact_cogs c
        JOIN eis.dim_period per ON c.period_id = per.id
        JOIN eis.dim_product p ON c.product_id = p.id
        WHERE per.fiscal_year = :year AND per.period_num <= :period
          AND p.business_type = :business AND p.market = :market
          AND (:product_code IS NULL OR p.product_code = :product_code)
        ORDER BY c.sales_amount DESC
        LIMIT 1
    """)
    result = await db.execute(q, {"year": year, "period": period, "business": business, "market": market, "product_code": product_code})
    row = result.mappings().first()
    return {"data": dict(row) if row else None}


@router.get("/closing-estimation")
async def get_closing_estimation(
    year: int = Query(2025),
    period: int = Query(11),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Sales closing estimation by segment."""
    q = text("""
        SELECT s.business_type,
               SUM(s.bp_amount) as bp_total,
               SUM(s.actual_amount) as actual_total,
               CASE WHEN SUM(s.bp_amount) > 0
                    THEN ROUND((SUM(s.actual_amount) / SUM(s.bp_amount) * 100)::numeric, 2)
                    ELSE 0 END as achievement_pct
        FROM eis.fact_sales s
        JOIN eis.dim_period per ON s.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num = :period
        GROUP BY s.business_type
        ORDER BY s.business_type
    """)
    result = await db.execute(q, {"year": year, "period": period})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.get("/nwc")
async def get_nwc(
    year: int = Query(2025),
    period: int = Query(11),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Net Working Capital (DSO + DIO - DPO)."""
    q = text("""
        SELECT per.period_name, fr.dso_days, fr.dio_days, fr.dpo_days,
               ROUND((fr.dso_days + fr.dio_days - fr.dpo_days)::numeric, 2) as nwc_days,
               ROUND(((fr.dso_days + fr.dio_days - fr.dpo_days) / 30)::numeric, 2) as nwc_months
        FROM eis.fact_financial_ratio fr
        JOIN eis.dim_period per ON fr.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num = :period
    """)
    result = await db.execute(q, {"year": year, "period": period})
    row = result.mappings().first()
    return {"data": dict(row) if row else None}


@router.get("/kpi-cards")
async def get_kpi_cards(
    year: int = Query(2025),
    period: int = Query(11),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """KPI summary cards for the landing page."""
    sales_q = text("""
        SELECT SUM(bp_amount) as bp_total, SUM(actual_amount) as actual_total
        FROM eis.fact_sales s
        JOIN eis.dim_period per ON s.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num <= :period
    """)
    sales = await db.execute(sales_q, {"year": year, "period": period})
    sales_row = sales.mappings().first()

    prod_q = text("""
        SELECT SUM(batch_size) as total_batch_size, SUM(yield_qty) as total_yield,
               CASE WHEN SUM(batch_size) > 0
                    THEN ROUND((SUM(yield_qty) / SUM(batch_size) * 100)::numeric, 2)
                    ELSE 0 END as yield_pct
        FROM eis.fact_production
        WHERE period_id = (SELECT id FROM eis.dim_period WHERE fiscal_year = :year AND period_num = :period)
    """)
    prod = await db.execute(prod_q, {"year": year, "period": period})
    prod_row = prod.mappings().first()

    fin_q = text("""
        SELECT net_profit_actual_cumulative, net_profit_bp_cumulative,
               cf_ending_balance_actual, cf_ending_balance_bp
        FROM eis.fact_financial
        WHERE period_id = (SELECT id FROM eis.dim_period WHERE fiscal_year = :year AND period_num = :period)
    """)
    fin = await db.execute(fin_q, {"year": year, "period": period})
    fin_row = fin.mappings().first()

    bp_total = float(sales_row["bp_total"] or 0) if sales_row else 0
    actual_total = float(sales_row["actual_total"] or 0) if sales_row else 0

    return {
        "data": {
            "sales_achievement": round(actual_total / bp_total * 100, 2) if bp_total > 0 else 0,
            "sales_bp": bp_total,
            "sales_actual": actual_total,
            "yield_pct": float(prod_row["yield_pct"] or 0) if prod_row else 0,
            "net_profit_achievement": round(
                float(fin_row["net_profit_actual_cumulative"] or 0) / float(fin_row["net_profit_bp_cumulative"] or 1) * 100, 2
            ) if fin_row and fin_row["net_profit_bp_cumulative"] else 0,
            "cashflow_achievement": round(
                float(fin_row["cf_ending_balance_actual"] or 0) / float(fin_row["cf_ending_balance_bp"] or 1) * 100, 2
            ) if fin_row and fin_row["cf_ending_balance_bp"] else 0,
        }
    }
