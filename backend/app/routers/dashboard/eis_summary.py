from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.eis_database import get_eis_db as get_db
from app.database import get_db as get_main_db
from app.dependencies import get_current_user
from app.services.financial_statement_service import FinancialStatementService
from app.services.pac_sales_plan_bp import pac_monthly_business_plan

router = APIRouter()

_MONTH_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
               "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


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


_CLOSING_SHEET_GROUPS = {
    "local":     {"national public", "national private"},
    "export":    {"export"},
    "cmo_other": {"cmo", "agreement"},
}


@router.get("/closing-estimation")
async def get_closing_estimation(
    year: int = Query(2025),
    month: int = Query(12, ge=1, le=12),
    db: AsyncSession = Depends(get_main_db),
    user = Depends(get_current_user),
):
    """Sales Closing Estimation — sourced from PAC's Sales Plan (Simulation
    Data), not the disconnected EIS ETL schema. Business Plan per segment
    is that segment's Sales Plan sheets' Jan..`month` monthly cells (row
    indices 4..4+month, NOT the row's own "Total Value" column, which is
    always the full Jan-Dec year regardless of `month`), summed across
    every product — e.g. month=7 totals January through July only.
    month=12 (default) sums the whole year, same total the row's own
    "Total Value" column already holds. Segments are grouped by which
    Excel tab a plan came from (content.meta.sheet_name, set at import
    time by sales_plan_service.py — matched as a case-insensitive
    substring, so "National Public FY26" still matches "national public"):
      Local       = sheet name contains "national public" or "national private"
      Export      = sheet name contains "export"
      CMO & Other = sheet name contains "cmo" or "agreement"
    Sales' own Business Plan is Local + CMO & Other + Export.
    Estimation has no data source yet anywhere in the app — always 0 until
    one exists; % is Estimation / Business Plan so it lights up on its own
    once a real estimation source is wired in, rather than needing a second
    change here.

    `unmatched_sheets` in the response lists every sheet_name found on a
    Sales Plan row for `year` that didn't match any of the 3 groups above
    (including blank, for rows uploaded before sheet_name existed) — a
    quick way to tell "no data uploaded yet" apart from "uploaded but the
    sheet naming doesn't match what this endpoint expects" without needing
    direct DB access."""
    from app.models.sales_plan import SalesPlan

    rows = (await db.execute(
        select(SalesPlan.content).where(SalesPlan.plan_year == year, SalesPlan.plan_type == "value")
    )).scalars().all()

    totals = {"local": 0.0, "export": 0.0, "cmo_other": 0.0}
    unmatched_sheets = set()
    for content in rows:
        sheet_raw = (content or {}).get("meta", {}).get("sheet_name") or ""
        sheet = str(sheet_raw).strip().lower()
        group = next((g for g, keywords in _CLOSING_SHEET_GROUPS.items() if any(k in sheet for k in keywords)), None)
        if not group:
            unmatched_sheets.add(sheet_raw if sheet_raw else "(no sheet_name — uploaded before this feature; re-upload the file)")
            continue
        for r in (content.get("rows") or []):
            if len(r) > 15:
                totals[group] += sum(float(v or 0) for v in r[4:4 + month])

    def _segment(plan_total: float) -> dict:
        est = 0.0
        return {
            "plan": round(plan_total, 2),
            "est":  est,
            "pct":  round(est / plan_total * 100, 2) if plan_total else 0,
        }

    local, export, cmo_other = totals["local"], totals["export"], totals["cmo_other"]
    return {"data": {
        "sales":     _segment(local + export + cmo_other),
        "local":     _segment(local),
        "cmo_other": _segment(cmo_other),
        "export":    _segment(export),
    }, "unmatched_sheets": sorted(unmatched_sheets)}


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
    main_db: AsyncSession = Depends(get_main_db),
    user = Depends(get_current_user),
):
    """KPI summary cards for the landing page. Sales Achievement's Business
    Plan prefers PAC's Sales Plan (Simulation Data) when it has data for
    the requested year — eis.fact_sales.bp_amount is 0 for every 2026
    period (whatever normally populates it hasn't run for 2026 yet) while
    PAC already has real 2026 figures; falls back to eis.fact_sales.bp_amount
    for years PAC has no Sales Plan for yet (e.g. 2025), so this doesn't
    regress years that already worked. Actual always comes from
    eis.fact_sales — PAC's Sales Plan is a plan, it has no actuals."""
    sales_q = text("""
        SELECT SUM(bp_amount) as bp_total, SUM(actual_amount) as actual_total
        FROM eis.fact_sales s
        JOIN eis.dim_period per ON s.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num <= :period
    """)
    sales = await db.execute(sales_q, {"year": year, "period": period})
    sales_row = sales.mappings().first()

    pac_bp_monthly, has_pac_data = await pac_monthly_business_plan(main_db, year)

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

    # Plan stays sourced from the EIS ETL schema (eis.fact_financial) —
    # Accounting & Tax's Financial Statement module has no Plan/Budget
    # figure anywhere. Actual is queried live from Oracle EBS GL_BALANCES
    # via FinancialStatementService — the same data Financial Statement >
    # Profit or Loss / Balance Sheet use — instead of eis.fact_financial's
    # actual columns, which were never populated (hence these cards coming
    # back empty). Net profit actual = YTD (Jan through `period`) net
    # profit; cashflow actual = the Cash & Cash Equivalents balance at
    # `period`'s month-end (a point-in-time snapshot, same as an
    # "Ending Balance").
    fin_q = text("""
        SELECT net_profit_bp_cumulative, cf_ending_balance_bp
        FROM eis.fact_financial
        WHERE period_id = (SELECT id FROM eis.dim_period WHERE fiscal_year = :year AND period_num = :period)
    """)
    fin = await db.execute(fin_q, {"year": year, "period": period})
    fin_row = fin.mappings().first()

    yy = str(year)[2:].zfill(2)
    ytd_periods = [f"{_MONTH_ABBR[m - 1]}-{yy}" for m in range(1, period + 1)]
    period_name = f"{_MONTH_ABBR[period - 1]}-{yy}"

    fs = FinancialStatementService()
    pl_result = await fs.get_profit_and_loss([{"label": "YTD", "periods": ytd_periods}])
    net_profit_actual_ytd = (pl_result.get("profit_after_tax") or [0])[0]

    bs_result = await fs.get_balance_sheet([period_name], "ASSETS")
    cash_row = next((r for r in bs_result.get("current_assets", []) if r["label"] == "CASH & CASH EQUIVALENTS"), None)
    cf_ending_balance_actual = cash_row["values"][0] if cash_row else 0

    net_profit_bp_cumulative = float(fin_row["net_profit_bp_cumulative"] or 0) if fin_row else 0
    cf_ending_balance_bp = float(fin_row["cf_ending_balance_bp"] or 0) if fin_row else 0

    actual_total = float(sales_row["actual_total"] or 0) if sales_row else 0
    if has_pac_data:
        bp_total = sum(pac_bp_monthly[:period])
    else:
        bp_total = float(sales_row["bp_total"] or 0) if sales_row else 0

    return {
        "data": {
            "sales_achievement": round(actual_total / bp_total * 100, 2) if bp_total > 0 else 0,
            "sales_bp": bp_total,
            "sales_actual": actual_total,
            "yield_pct": float(prod_row["yield_pct"] or 0) if prod_row else 0,
            "net_profit_achievement": round(
                net_profit_actual_ytd / net_profit_bp_cumulative * 100, 2
            ) if net_profit_bp_cumulative else 0,
            "cashflow_achievement": round(
                cf_ending_balance_actual / cf_ending_balance_bp * 100, 2
            ) if cf_ending_balance_bp else 0,
        }
    }
