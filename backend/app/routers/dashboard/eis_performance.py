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


# ══════════════════════════════════════════════════════════════
# Performance dashboard — reads the eis.perf_* tables filled by the EIS
# template upload (eis_data_upload: /eis-template/upload), not fact_sales
# above (that one is rewritten by the Oracle ETL). One call returns every
# block of the page, with the formulas of the template's own Performance
# sheet (verified against its Nov 2025 figures):
#   Yearly       YTD actual ÷ YTD business plan, Jan..selected month
#   Growth       YTD actual vs the same months of the previous year
#   Monthly      business plan vs actual per month (SalesSummary_Monthly)
#   Company      Local + CMO & Others + Export
#   Area         YTD sum per region; West / East per the sheet's grouping
#   Marketing    latest month's plan (annual target) vs actual (YTD)
#   EBIT-Product latest Sales_Ledger snapshot (quarterly) for one market:
#                the 5 largest products by sales with positive EBIT,
#                ranked by EBIT ÷ sales. A ratio, so it is unaffected by
#                the ledger's mixed scale between quarters.
# ══════════════════════════════════════════════════════════════

SALES_SEGMENTS = ["Local", "CMO & Others", "Export"]
# The sheet's sales-force split: West 65,350 = Java + Sumatera + Sulawesi,
# East 11,418 = Bali + Kalimantan (Nov 2025 YTD).
AREA_GROUPS = {"West": ("Java", "Sumatera", "Sulawesi"), "East": ("Bali", "Kalimantan")}
EBIT_TOP_N = 5


def _sum(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _pct(num, den):
    return round(num / den * 100, 1) if num is not None and den else None


@router.get("/dashboard")
async def performance_dashboard(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    ebit_market: str = Query("Public"),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    # ── Sales summary: this year + previous year, Jan..period ─────
    ss = (await db.execute(text("""
        SELECT business_type, fiscal_year, month_num, plan_amount, actual_amount
        FROM eis.perf_sales_summary
        WHERE fiscal_year IN (:y, :py) AND month_num <= :p
    """), {"y": year, "py": year - 1, "p": period})).mappings().all()
    cell = {(r["business_type"], r["fiscal_year"], r["month_num"]):
            (float(r["plan_amount"]) if r["plan_amount"] is not None else None,
             float(r["actual_amount"]) if r["actual_amount"] is not None else None)
            for r in ss}

    def segment_block(types):
        monthly = []
        for m in range(1, period + 1):
            vals = [cell.get((t, year, m), (None, None)) for t in types]
            monthly.append({"month": m, "plan": _sum(v[0] for v in vals), "actual": _sum(v[1] for v in vals)})
        ytd_plan = _sum(r["plan"] for r in monthly)
        ytd_actual = _sum(r["actual"] for r in monthly)
        prev = _sum(cell.get((t, year - 1, m), (None, None))[1] for t in types for m in range(1, period + 1))
        return {
            "monthly": monthly,
            "ytd_plan": ytd_plan, "ytd_actual": ytd_actual,
            "achievement_pct": _pct(ytd_actual, ytd_plan),
            "prev_ytd_actual": prev,
            "growth_pct": round((ytd_actual / prev - 1) * 100, 1) if ytd_actual is not None and prev else None,
        }

    segments = {"Company": segment_block(SALES_SEGMENTS)}
    for t in SALES_SEGMENTS:
        segments[t] = segment_block([t])

    # ── Area sales (YTD) ─────────────────────────────────────────
    area_rows = (await db.execute(text("""
        SELECT region, SUM(sales_amount) AS amount
        FROM eis.perf_area_sales
        WHERE fiscal_year = :y AND month_num <= :p
        GROUP BY region
        ORDER BY MIN(id)
    """), {"y": year, "p": period})).mappings().all()
    area_total = _sum(float(r["amount"]) if r["amount"] is not None else None for r in area_rows)
    area = None
    if area_rows:
        amounts = {r["region"]: float(r["amount"]) if r["amount"] is not None else None for r in area_rows}
        area = {
            "regions": [{"region": k, "amount": v, "portion_pct": _pct(v, area_total)} for k, v in amounts.items()],
            "total": area_total,
            "groups": [],
        }
        for g, regs in AREA_GROUPS.items():
            amt = _sum(amounts.get(rg) for rg in regs)
            area["groups"].append({"name": g, "amount": amt, "portion_pct": _pct(amt, area_total)})

    # ── Marketing activity: latest month <= period per event ─────
    mk = (await db.execute(text("""
        SELECT DISTINCT ON (event_name) event_name, month_num, plan_event_count, actual_event_count
        FROM eis.perf_marketing
        WHERE fiscal_year = :y AND month_num <= :p
          AND (plan_event_count IS NOT NULL OR actual_event_count IS NOT NULL)
        ORDER BY event_name, month_num DESC
    """), {"y": year, "p": period})).mappings().all()
    marketing = []
    for r in mk:
        plan = float(r["plan_event_count"]) if r["plan_event_count"] is not None else None
        act = float(r["actual_event_count"]) if r["actual_event_count"] is not None else None
        marketing.append({
            "event": r["event_name"].replace("(total tahun berjalan)", "").strip(),
            "month": r["month_num"], "plan": plan, "actual": act, "achievement_pct": _pct(act, plan),
        })
    marketing.sort(key=lambda e: (not e["event"].lower().startswith("event"), e["event"]))

    # ── EBIT per product: latest Actual snapshot for the market ───
    mkt_cond = "(market = :mkt OR (:mkt = 'Export' AND market LIKE 'Export%'))"
    at = (await db.execute(text(f"""
        SELECT fiscal_year, month_num FROM eis.perf_sales_ledger
        WHERE scenario = 'Actual' AND sales_amount IS NOT NULL AND {mkt_cond}
        GROUP BY fiscal_year, month_num
        ORDER BY (fiscal_year * 100 + month_num) <= (:y * 100 + :p) DESC,
                 fiscal_year DESC, month_num DESC
        LIMIT 1
    """), {"y": year, "p": period, "mkt": ebit_market})).first()
    ebit = None
    if at:
        prods = (await db.execute(text(f"""
            SELECT product_name, SUM(sales_amount) AS sales, SUM(ebit_amount) AS ebit
            FROM eis.perf_sales_ledger
            WHERE scenario = 'Actual' AND fiscal_year = :fy AND month_num = :fm AND {mkt_cond}
            GROUP BY product_name
        """), {"fy": at[0], "fm": at[1], "mkt": ebit_market})).mappings().all()
        ranked = sorted(
            (p for p in prods if p["sales"] and p["sales"] > 0 and p["ebit"] is not None and p["ebit"] > 0),
            key=lambda p: p["sales"], reverse=True,
        )[:EBIT_TOP_N]
        ebit = {
            "market": ebit_market, "year": at[0], "month": at[1],
            "items": sorted(
                ({"product": p["product_name"], "ebit_pct": round(float(p["ebit"]) / float(p["sales"]) * 100, 1)}
                 for p in ranked),
                key=lambda x: x["ebit_pct"], reverse=True,
            ),
        }

    return {
        "year": year, "period": period,
        "has_data": bool(ss or area_rows or mk or at),
        "segments": segments,
        "area": area,
        "marketing": marketing,
        "ebit": ebit,
    }
