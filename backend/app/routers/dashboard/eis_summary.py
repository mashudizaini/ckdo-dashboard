import asyncio
import re
from typing import Optional

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
        # Real tab names use underscores as word separators (e.g.
        # "Sales plan_V_National_Public"), not spaces — normalize both so
        # "national public" still matches "national_public".
        sheet = str(sheet_raw).strip().lower().replace("_", " ")
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


# ══════════════════════════════════════════════════════════════
# Summary dashboard — the template's Summary sheet, built from the same
# numbers the Performance / Production / Administration pages show (their
# own /dashboard functions are called, so the pages can never disagree):
#   KPI cards    Sales achievement (Performance, Company YTD), production
#                yield (Production, selected month), net profit progress and
#                cashflow achievement (Administration, Oracle + template plan)
#   Portfolio    one product's Sales / COGS / GP / OPEX / EBIT from the latest
#                Sales_Ledger snapshot (eis.perf_sales_ledger), and its COGS
#                split into Material / Labour / Depreciation / FOH with the
#                ratios of the item's Oracle OPM actual cost (CM_CMPT_DTL)
#   Closing      the month being closed = the one after the selected month:
#                plan from SalesSummary_Monthly (as Performance), else PAC
#                Sales Plan for months the template doesn't cover; Local
#                estimation = Daily Sales run-rate projection (its upload is
#                Local sales), CMO & Others / Export = that month's actual
#                when SalesSummary_Monthly has one (no daily source for them)
#   NWC          DSO + DIO − DPO: DSO/DPO from Administration, DIO from
#                Production
# ══════════════════════════════════════════════════════════════

_SEGMENTS = [("local", "Local"), ("cmo_other", "CMO & Others"), ("export", "Export")]

# Sales_Ledger market -> business line (the template's Business column)
from app.routers.dashboard.eis_performance import ledger_business as _business_of


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


async def _portfolio(eis_db, year: int, period: int, market: Optional[str], product: Optional[str]):
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
    markets = [{"market": m, "business": _business_of(m), "products": ps} for m, ps in options.items()]

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
            "business": _business_of(pick["market"]), "market": pick["market"], "product": pick["product_name"],
            "sales": sales, "cogs": cogs, "cogs_pct": pct(cogs), "gross_profit": gp, "gp_pct": pct(gp),
            "opex": opex, "opex_pct": pct(opex), "ebit": ebit, "ebit_pct": pct(ebit),
        },
        "cost": cost,
    }


async def _closing(eis_db, main_db, year: int, period: int):
    from app.routers.dashboard import eis_daily_sales as ds
    cy, cm = (year, period + 1) if period < 12 else (year + 1, 1)

    tpl = (await eis_db.execute(text("""
        SELECT business_type, plan_amount, actual_amount FROM eis.perf_sales_summary
        WHERE fiscal_year = :y AND month_num = :m
    """), {"y": cy, "m": cm})).mappings().all()
    tpl = {r["business_type"]: r for r in tpl}

    pac = None  # lazily: PAC Sales Plan for the closing month, per segment (IDR -> million)
    async def pac_plan(key):
        nonlocal pac
        if pac is None:
            pac = {}
            from app.models.sales_plan import SalesPlan
            contents = (await main_db.execute(
                select(SalesPlan.content).where(SalesPlan.plan_year == cy, SalesPlan.plan_type == "value")
            )).scalars().all()
            for content in contents:
                sheet = str((content or {}).get("meta", {}).get("sheet_name") or "").strip().lower().replace("_", " ")
                group = next((g for g, kws in _CLOSING_SHEET_GROUPS.items() if any(k in sheet for k in kws)), None)
                if group:
                    for r in content.get("rows") or []:
                        if len(r) > 15:
                            pac[group] = pac.get(group, 0.0) + float(r[3 + cm] or 0)
        v = pac.get(key)
        return round(v / 1e6, 1) if v else None

    daily = None
    blob = ds._load_store().get(str(cy))
    if blob:
        info = ds._daily_sales_kpi_by_month(blob.get("rows") or []).get(ds.MONTHS[cm - 1])
        if info and info["status"] in ("actual", "projected"):
            daily = info

    segs = {}
    for key, label in _SEGMENTS:
        row = tpl.get(label)
        plan, plan_src = (float(row["plan_amount"]), "template") if row and row["plan_amount"] is not None else (await pac_plan(key), "pac")
        if plan is None:
            plan_src = None
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
    from app.routers.dashboard.eis_performance import performance_dashboard
    from app.routers.dashboard.eis_production import production_dashboard
    from app.routers.dashboard.eis_administration import load_admin_plans, financial_and_ratios

    perf = await performance_dashboard(year=year, period=period, ebit_market="Public", db=db, user=user)
    prod = await production_dashboard(year=year, period=period, db=db, user=user)
    _, plan, _ = await load_admin_plans(db, year, period)
    financial, ratios = await financial_and_ratios(year, period, plan)

    company = perf["segments"]["Company"]
    yield_cur = prod["yield"]["current"]
    fin_ok = financial and "error" not in financial
    kpi = {
        "sales_achievement_pct": company["achievement_pct"],
        "sales_ytd_actual": company["ytd_actual"], "sales_ytd_plan": company["ytd_plan"],
        "yield_pct": yield_cur["yield_pct"] if yield_cur else None,
        "yield_month": yield_cur["month"] if yield_cur else None,
        "yield_target_pct": prod["yield"]["target_pct"],
        "net_profit_progress_pct": financial.get("net_profit_progress_pct") if fin_ok else None,
        "cash_achievement_pct": financial.get("cash_achievement_pct") if fin_ok else None,
        "financial_error": None if fin_ok else (financial or {}).get("error"),
    }

    dio = prod["dio"]
    ratios_ok = ratios and "error" not in ratios
    dso = ratios.get("dso_days") if ratios_ok else None
    dpo = ratios.get("dpo_days") if ratios_ok else None
    dio_days = dio["days"] if dio else None
    nwc_days = dso + dio_days - dpo if None not in (dso, dio_days, dpo) else None
    to_month = lambda d: round(d / 30, 1) if d is not None else None
    nwc = {
        "dso_days": dso, "dio_days": dio_days, "dpo_days": dpo, "nwc_days": round(nwc_days, 1) if nwc_days is not None else None,
        "dso_months": to_month(dso), "dio_months": to_month(dio_days), "dpo_months": to_month(dpo),
        "nwc_months": to_month(nwc_days), "dio_month": dio["month"] if dio else None,
        "error": None if ratios_ok else (ratios or {}).get("error"),
    }

    return {
        "year": year, "period": period, "kpi": kpi,
        "portfolio": await _portfolio(db, year, period, market, product),
        "closing": await _closing(db, main_db, year, period),
        "nwc": nwc,
    }


@router.get("/dashboard/portfolio")
async def summary_portfolio(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    market: Optional[str] = Query(None), product: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Product Portfolio block alone — for the Summary page's product
    selector, without re-running the Oracle financial queries."""
    return await _portfolio(db, year, period, market, product)
