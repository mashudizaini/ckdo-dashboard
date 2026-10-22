import asyncio
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.database import get_db as get_main_db
from app.dependencies import get_current_user

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


# ══════════════════════════════════════════════════════════════
# Summary dashboard — the template's Summary sheet, built from the same
# numbers the Performance / Production / Administration pages show (their
# own /dashboard functions are called, so the pages can never disagree):
#   (The four KPI cards were removed from the page on 2026-10-22.)
#   Portfolio    one product's Sales / COGS / GP / OPEX / EBIT from the latest
#                Sales_Ledger snapshot (eis.perf_sales_ledger), and its COGS
#                split into Material / Labour / Depreciation / FOH with the
#                ratios of the item's Oracle OPM actual cost (CM_CMPT_DTL)
#   Closing      the selected month (user, 2026-10-22 — Jul 2026 = "Closing
#                July 2026", not the month after):
#                plan from SalesSummary_Monthly only (user, 2026-10-22: not
#                the PAC Sales Plan / Business Plan, which it used to fall
#                back to for months the sheet lacked); Local
#                estimation = Daily Sales run-rate projection (its upload is
#                Local sales), CMO & Others / Export = that month's actual
#                when SalesSummary_Monthly has one (no daily source for them)
#   NWC          DSO + DIO − DPO: DSO = Average AR ÷ Sales × 365 and DPO =
#                Average AP ÷ COGS × 365 from the Administration_Ratios
#                sheet — eis_administration.ratios_for_month, shared with the
#                Administration page — DIO from Production
# ══════════════════════════════════════════════════════════════

_SEGMENTS = [("local", "Local"), ("cmo_other", "CMO & Others"), ("export", "Export")]

# Sales_Ledger market -> business line (the template's Business column)
from app.routers.dashboard.eis_performance import ledger_business, market_business_map


# OPM cost component class -> the template's four COGS buckets. 2025 costing
# only carries material classes + one GLA overhead lump; the detailed salary /
# depreciation classes start in 2026.
_CMPNT_BUCKET = {
    "RMA": "material", "RME": "material", "PMP": "material", "PMS": "material", "UNK": "material",
    "DISL": "labour", "INSL": "labour", "DIOA": "labour", "INOA": "labour", "RSD": "labour",
    "DEPR": "depreciation",
}


def _opm_cost_split(product_name: str, year: int, month: int) -> Optional[dict]:
    """Cost-component shares of the FG item matching product_name, Oracle
    OPM actual cost (org 121, cost type 1000) for that month. The ledger
    names products like "Docetaxel 20 mg"; OPM item descriptions start the
    same way ("DOCETAXEL 20 MG INJECTION"), compared without spaces. Own
    CKD items are preferred over toll/brand variants of the same product."""
    from app.database import get_oracle_connection
    key = re.sub(r"\s+", "", product_name or "").upper()
    if not key:
        return None
    period_code = f"{_MONTH_ABBR[month - 1]}-{str(year)[2:]}"
    sql = """
        SELECT MSIB.SEGMENT1, MSIB.DESCRIPTION, CCMV.COST_CMPNTCLS_CODE, SUM(CDT.CMPNT_COST)
        FROM apps.CM_CMPT_DTL CDT
        JOIN apps.MTL_SYSTEM_ITEMS_B MSIB ON MSIB.INVENTORY_ITEM_ID = CDT.INVENTORY_ITEM_ID
                                         AND MSIB.ORGANIZATION_ID = CDT.ORGANIZATION_ID
        JOIN apps.GMF_PERIOD_STATUSES GPS ON GPS.PERIOD_ID = CDT.PERIOD_ID
        JOIN apps.CM_CMPT_MST_VL CCMV ON CCMV.COST_CMPNTCLS_ID = CDT.COST_CMPNTCLS_ID
        WHERE CDT.ORGANIZATION_ID = 121 AND CDT.COST_TYPE_ID = 1000
          AND GPS.PERIOD_CODE = :per AND MSIB.ITEM_TYPE LIKE 'FG%'
          AND REPLACE(UPPER(MSIB.DESCRIPTION), ' ', '') LIKE :key || '%'
        GROUP BY MSIB.SEGMENT1, MSIB.DESCRIPTION, CCMV.COST_CMPNTCLS_CODE
    """
    items = {}
    with get_oracle_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, {"per": period_code, "key": key})
        for code, desc, cls, cost in cur.fetchall():
            items.setdefault((code, desc), {})[cls] = float(cost or 0)
    items = {k: v for k, v in items.items() if sum(v.values()) > 0}
    if not items:
        return None
    (code, desc), comps = sorted(items.items(), key=lambda kv: (not kv[0][0].startswith("CKD"), kv[0][0]))[0]
    total = sum(comps.values())
    buckets = {"material": 0.0, "labour": 0.0, "depreciation": 0.0, "foh": 0.0}
    for cls, cost in comps.items():
        buckets[_CMPNT_BUCKET.get(cls, "foh")] += cost
    return {
        "item_code": code, "item_desc": desc, "period": period_code, "unit_cost": round(total, 2),
        "shares": {k: v / total for k, v in buckets.items()},
        # 2025 costing has no salary/depreciation classes with value — those
        # costs sit inside the GLA overhead lump, i.e. in FOH here.
        "detailed": buckets["labour"] + buckets["depreciation"] > 0,
    }


async def _portfolio(eis_db, main_db, year: int, period: int, market: Optional[str], product: Optional[str]):
    at = (await eis_db.execute(text("""
        SELECT fiscal_year, month_num FROM eis.perf_sales_ledger
        WHERE scenario = 'Actual' AND sales_amount IS NOT NULL
        GROUP BY fiscal_year, month_num
        ORDER BY (fiscal_year * 100 + month_num) <= (:y * 100 + :p) DESC, fiscal_year DESC, month_num DESC
        LIMIT 1
    """), {"y": year, "p": period})).first()
    if not at:
        return None
    rows = (await eis_db.execute(text("""
        SELECT market, product_name, SUM(sales_amount) AS sales, SUM(cogs_amount) AS cogs,
               SUM(opex_amount) AS opex, SUM(ebit_amount) AS ebit
        FROM eis.perf_sales_ledger
        WHERE scenario = 'Actual' AND fiscal_year = :fy AND month_num = :fm
        GROUP BY market, product_name
        HAVING SUM(sales_amount) > 0
        ORDER BY SUM(sales_amount) DESC
    """), {"fy": at[0], "fm": at[1]})).mappings().all()
    if not rows:
        return None

    options = {}
    for r in rows:
        options.setdefault(r["market"], []).append(r["product_name"])
    mapping = await market_business_map(main_db)
    biz_of = lambda m: ledger_business(m, mapping)[0]
    markets = [{"market": m, "business": biz_of(m), "products": ps} for m, ps in options.items()]

    pick = next((r for r in rows if r["market"] == market and r["product_name"] == product), None) \
        or next((r for r in rows if r["market"] == market), None) \
        or next((r for r in rows if r["market"] == "Public"), rows[0])
    f = lambda k: float(pick[k]) if pick[k] is not None else None
    sales, cogs, opex, ebit = f("sales"), f("cogs"), f("opex"), f("ebit")
    gp = sales - cogs if cogs is not None else None
    pct = lambda v: round(v / sales * 100, 1) if v is not None and sales else None

    cost = None
    try:
        split = await asyncio.to_thread(_opm_cost_split, pick["product_name"], at[0], at[1])
    except Exception as e:
        split = {"error": str(e)}
    if split and "error" not in split and cogs is not None:
        cost = {
            "item_code": split["item_code"], "item_desc": split["item_desc"], "period": split["period"],
            "detailed": split["detailed"],
            **{k: {"amount": round(cogs * share, 1), "pct": round(share * 100, 1)} for k, share in split["shares"].items()},
        }
    elif split and "error" in split:
        cost = {"error": split["error"]}

    return {
        "as_of": {"year": at[0], "month": at[1]},
        "markets": markets,
        "selected": {
            "business": biz_of(pick["market"]), "market": pick["market"], "product": pick["product_name"],
            "sales": sales, "cogs": cogs, "cogs_pct": pct(cogs), "gross_profit": gp, "gp_pct": pct(gp),
            "opex": opex, "opex_pct": pct(opex), "ebit": ebit, "ebit_pct": pct(ebit),
        },
        "cost": cost,
    }


async def _closing(eis_db, main_db, year: int, period: int):
    from app.routers.dashboard import eis_daily_sales as ds
    cy, cm = year, period

    tpl = (await eis_db.execute(text("""
        SELECT business_type, plan_amount, actual_amount FROM eis.perf_sales_summary
        WHERE fiscal_year = :y AND month_num = :m
    """), {"y": cy, "m": cm})).mappings().all()
    tpl = {r["business_type"]: r for r in tpl}

    daily = None
    blob = ds._load_store().get(str(cy))
    if blob:
        info = ds._daily_sales_kpi_by_month(blob.get("rows") or []).get(ds.MONTHS[cm - 1])
        if info and info["status"] in ("actual", "projected"):
            daily = info

    segs = {}
    for key, label in _SEGMENTS:
        row = tpl.get(label)
        plan = float(row["plan_amount"]) if row and row["plan_amount"] is not None else None
        plan_src = "template" if plan is not None else None
        if key == "local" and daily:
            est, est_src = round(daily["expectation_closing"], 1), daily["status"]
        elif row and row["actual_amount"] is not None:
            est, est_src = float(row["actual_amount"]), "actual"
        else:
            est, est_src = None, None
        segs[key] = {"plan": plan, "plan_source": plan_src, "est": est, "est_source": est_src,
                     "pct": round(est / plan * 100, 1) if est is not None and plan else None}
    plans = [s["plan"] for s in segs.values() if s["plan"] is not None]
    ests = [s["est"] for s in segs.values() if s["est"] is not None]
    total_plan = sum(plans) if plans else None
    total_est = sum(ests) if ests else None
    segs["sales"] = {"plan": total_plan, "est": total_est,
                     "pct": round(total_est / total_plan * 100, 1) if total_est is not None and total_plan else None}
    return {"year": cy, "month": cm, **segs,
            "daily_sales": {"wd_actual": daily["wd_actual"], "wd_total": daily["wd_total"]} if daily else None}


@router.get("/dashboard")
async def summary_dashboard(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    market: Optional[str] = Query(None), product: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db), main_db: AsyncSession = Depends(get_main_db),
    user = Depends(get_current_user),
):
    from app.routers.dashboard.eis_production import production_dashboard
    from app.routers.dashboard.eis_administration import load_admin_plans, financial_and_ratios, ratios_for_month

    prod = await production_dashboard(year=year, period=period, db=db, user=user)

    dio = prod["dio"]
    rt = await ratios_for_month(db, year, period, None)
    if rt["dso_days"] is None or rt["dpo_days"] is None:
        # The Oracle P&L/BS queries are slow — only run them when the
        # Administration_Ratios sheet doesn't cover this month.
        _, plan, _ = await load_admin_plans(db, year, period)
        _, ratios = await financial_and_ratios(year, period, plan)
        rt = await ratios_for_month(db, year, period, ratios)
    dso, dpo = rt["dso_days"], rt["dpo_days"]
    dio_days = dio["days"] if dio else None
    nwc_days = dso + dio_days - dpo if None not in (dso, dio_days, dpo) else None
    to_month = lambda d: round(d / 30, 1) if d is not None else None
    nwc = {
        "dso_days": dso, "dio_days": dio_days, "dpo_days": dpo, "nwc_days": round(nwc_days, 1) if nwc_days is not None else None,
        "dso_months": to_month(dso), "dio_months": to_month(dio_days), "dpo_months": to_month(dpo),
        "dio_month": dio["month"] if dio else None,
        "dso_source": rt["dso_source"], "dso_month": rt["dso_month"],
        "dpo_source": rt["dpo_source"], "dpo_month": rt["dpo_month"],
        "error": rt["error"],
    }

    return {
        "year": year, "period": period,
        "portfolio": await _portfolio(db, main_db, year, period, market, product),
        "closing": await _closing(db, main_db, year, period),
        "nwc": nwc,
    }


@router.get("/dashboard/portfolio")
async def summary_portfolio(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    market: Optional[str] = Query(None), product: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db), main_db: AsyncSession = Depends(get_main_db),
    user = Depends(get_current_user),
):
    """Product Portfolio block alone — for the Summary page's product
    selector, without re-running the Oracle financial queries."""
    return await _portfolio(db, main_db, year, period, market, product)
