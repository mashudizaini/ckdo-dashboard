from calendar import monthrange
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db as get_main_db
from app.dependencies import get_current_user
from app.eis_database import get_eis_db as get_db
from app.models.employee import Employee
from app.services.department_taxonomy import CANONICAL_DEPARTMENTS, normalize_department
from app.services.financial_statement_service import FinancialStatementService

router = APIRouter()

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]
_MONTH_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
               "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


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
    user = Depends(get_current_user),
):
    """Actual net profit queried live from Oracle EBS GL_BALANCES — the
    same table Accounting & Tax's Financial Statement > Profit or Loss
    reads — instead of the EIS ETL schema or a manually-uploaded Excel
    snapshot (both of which required someone to keep re-uploading a file
    and were coming back empty). One column per calendar month, each a
    single GL period (not a YTD range), so the value is that month's own
    net profit; a month with nothing posted in Oracle yet comes back 0."""
    yy = str(year)[2:].zfill(2)
    columns = [
        {"label": _MONTH_NAMES[m - 1], "periods": [f"{_MONTH_ABBR[m - 1]}-{yy}"]}
        for m in range(1, 13)
    ]
    result = await FinancialStatementService().get_profit_and_loss(columns)
    pat = result.get("profit_after_tax") or []
    data = [
        {
            "period_num": m, "period_name": _MONTH_NAMES[m - 1],
            "net_profit_actual": pat[m - 1] if m - 1 < len(pat) else None,
        }
        for m in range(1, 13)
    ]
    return {"data": data}


@router.get("/cashflow")
async def cashflow(
    year: int = Query(2025),
    eis_db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    """Plan stays sourced from the EIS ETL schema (eis.fact_financial) —
    Accounting & Tax has no Plan/Budget figure anywhere. Actual is now the
    live Oracle EBS "CASH & CASH EQUIVALENTS" balance at each month's end
    (same GL_BALANCES data behind Accounting & Tax's Balance Sheet) instead
    of a manually re-uploaded Cashflow Excel — there's no live Oracle
    equivalent of a full statutory cash-flow statement, but the ending cash
    balance is exactly what a Cashflow chart's "Ending Balance" tracks."""
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

    yy = str(year)[2:].zfill(2)
    period_names = [f"{_MONTH_ABBR[m - 1]}-{yy}" for m in range(1, 13)]
    bs = await FinancialStatementService().get_balance_sheet(period_names, "ASSETS")
    cash_row = next((r for r in bs.get("current_assets", []) if r["label"] == "CASH & CASH EQUIVALENTS"), None)
    cash_values = cash_row["values"] if cash_row else [None] * 12

    data = []
    for m in range(1, 13):
        plan_row = plan_by_month.get(m)
        data.append({
            "period_num": m,
            "period_name": plan_row["period_name"] if plan_row else _MONTH_NAMES[m - 1],
            "cf_ending_balance_bp": float(plan_row["cf_ending_balance_bp"]) if plan_row and plan_row["cf_ending_balance_bp"] is not None else None,
            "cf_ending_balance_actual": cash_values[m - 1] if m - 1 < len(cash_values) else None,
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


# ══════════════════════════════════════════════════════════════
# Administration dashboard — laid out after the EIS template's
# Administration sheet. One call returns every block; actuals are live,
# only the plans come from the EIS template upload (eis.adm_*), because
# neither HRGA nor Accounting carries a plan figure:
#   Personnel   HRGA employees, active as of the selected month's end (same
#               _is_active rule as HRGA Employee Data). Groups = the 4
#               canonical departments; Plant split Direct (team Production
#               or PPWH) / Indirect. Turnover = HRGA's YTD formula (resigns
#               Jan..month ÷ mean of each month's avg headcount). Plan =
#               Administration_Headcount (company row).
#   Financial   Oracle GL through Accounting's FinancialStatementService
#               (same numbers as Financial Statement): net profit per month
#               vs Administration_Financial "Net Profit" plan (progress =
#               YTD actual ÷ YTD plan); cash & cash equivalents at month end
#               vs "Cashflow Ending Balance" plan.
#   Ratios      from the Administration_Ratios sheet: DSO = Average AR ÷
#               Sales × 365, DPO = Average AP ÷ COGS × 365 (ratios_for_month);
#               Oracle only for a month the sheet lacks — there avg AR/AP =
#               (this month + same month last year) ÷ 2 over the last 12
#               months' net sales / COGS.
#   Budget      actual = Oracle GL expense postings (actual_flag 'A') per
#               department via segment3 (CKDO_GL_COA_DEPARTMENT, as Budget
#               Monitoring); codes outside the department ranges (0xx/9xx:
#               non-departmental, eliminations) are left out. Plan =
#               Administration_Financial "Budget Usage" (monthly) and
#               "Budget Allocation" (YTD per department).
# Amounts are returned in IDR million, as the template shows them.
# ══════════════════════════════════════════════════════════════

ADM_GROUPS = ["Sales & Marketing", "Strategy & Development", "Plant", "Administration"]
PLANT_DIRECT_TEAMS = {"PRODUCTION", "PPWH"}
# segment3 first digit -> department group (codes per budget_access_service)
BUDGET_DEPT_GROUP = {"1": "Administration", "4": "Administration", "2": "Sales & Marketing",
                     "3": "Plant", "6": "Strategy & Development"}
# Administration_Financial "Budget Allocation" department labels -> groups
_TPL_DEPT = {"Sales & Marketing": "Sales & Marketing", "Strategy & Development": "Strategy & Development",
             "Plant": "Plant", "Admin": "Administration", "Administration": "Administration"}


def _mio(v):
    return round(float(v) / 1e6, 1) if v is not None else None


def _ratio_pct(num, den):
    return round(num / den * 100, 1) if num is not None and den else None


def _personnel(rows, year: int, period: int):
    from app.routers.dashboard.hr_employees import _is_active

    def snapshot(d):
        return [r for r in rows if _is_active(r.date_of_joining, r.resign_date, r.employment_status, d)]

    month_end = date(year, period, monthrange(year, period)[1])
    active = snapshot(month_end)
    groups = {g: 0 for g in ADM_GROUPS}
    unassigned = plant_direct = 0
    for r in active:
        g = normalize_department(r.department)
        if g is None:
            unassigned += 1
            continue
        groups[g] += 1
        if g == "Plant" and (r.team or "").strip().upper() in PLANT_DIRECT_TEAMS:
            plant_direct += 1

    monthly, resigns, avg_hcs = [], 0, []
    for m in range(1, period + 1):
        first = date(year, m, 1)
        last = date(year, m, monthrange(year, m)[1])
        monthly.append({"month": m, "headcount": len(snapshot(last))})
        # HRGA /turnover-summary's month window, kept identical on purpose
        start = sum(1 for r in rows if r.date_of_joining < first and
                    (r.resign_date >= first if r.resign_date else r.employment_status != "Resign"))
        end = sum(1 for r in rows if r.date_of_joining <= last and
                  (r.resign_date >= first if r.resign_date else r.employment_status != "Resign"))
        avg_hcs.append((start + end) / 2)
        resigns += sum(1 for r in rows if r.resign_date and first <= r.resign_date <= last)
    avg_hc = sum(avg_hcs) / len(avg_hcs) if avg_hcs else 0

    return {
        "total": len(active),
        "groups": groups,
        "plant_direct": plant_direct,
        "plant_indirect": groups["Plant"] - plant_direct,
        "unassigned": unassigned,
        "monthly": monthly,
        "resigns_ytd": resigns,
        "turnover_pct": round(resigns / avg_hc * 100, 1) if avg_hc else None,
    }


def _budget_actuals(year: int, period: int) -> dict:
    """(month, group) -> Oracle expense actual in rupiah."""
    from app.database import get_oracle_connection
    sql = """
        SELECT gb.period_num, SUBSTR(gcc.segment3, 1, 1) AS dept_digit,
               SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) AS amount
        FROM gl_balances gb
        JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id
        WHERE gb.actual_flag = 'A' AND gcc.account_type = 'E' AND gb.currency_code = 'IDR'
          AND gcc.summary_flag = 'N' AND gb.period_year = :y AND gb.period_num <= :p
        GROUP BY gb.period_num, SUBSTR(gcc.segment3, 1, 1)
    """
    out = {}
    with get_oracle_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, {"y": year, "p": period})
        for m, digit, amount in cur.fetchall():
            g = BUDGET_DEPT_GROUP.get(str(digit))
            if g:
                out[(int(m), g)] = out.get((int(m), g), 0.0) + float(amount or 0)
    return out


async def load_admin_plans(eis_db: AsyncSession, year: int, period: int):
    """Plans from the EIS template (eis.adm_*): the company headcount plan
    row (latest month <= period) and {(metric, department, month): plan}."""
    hc_plan_row = (await eis_db.execute(text("""
        SELECT month_num, plan_count FROM eis.adm_headcount
        WHERE department = '' AND fiscal_year = :y AND month_num <= :p AND plan_count IS NOT NULL
        ORDER BY month_num DESC LIMIT 1
    """), {"y": year, "p": period})).first()
    fin_rows = (await eis_db.execute(text("""
        SELECT metric, department, month_num, plan_amount
        FROM eis.adm_financial
        WHERE fiscal_year = :y AND month_num <= :p
    """), {"y": year, "p": period})).mappings().all()
    plan = {}
    for r in fin_rows:
        plan[(r["metric"], r["department"], r["month_num"])] = float(r["plan_amount"]) if r["plan_amount"] is not None else None

    return hc_plan_row, plan, bool(hc_plan_row or fin_rows)


async def financial_and_ratios(year: int, period: int, plan: dict):
    """(financial, ratios) blocks from Oracle GL via Accounting's
    FinancialStatementService — shared by this page and the EIS Summary
    (net profit / cashflow achievement, DSO / DPO for NWC). Each comes
    back as {"error": ...} instead of raising when Oracle can't be read."""
    yy = lambda y: str(y)[2:].zfill(2)
    pname = lambda y, m: f"{_MONTH_ABBR[m - 1]}-{yy(y)}"
    # 24 months: Jan of last year .. selected month (12-month windows + YTD)
    months = [(year - 1, m) for m in range(1, 13)] + [(year, m) for m in range(1, period + 1)]
    import logging
    financial = ratios = None
    try:
        fs = FinancialStatementService()
        pl = await fs.get_profit_and_loss([{"label": pname(*k), "periods": [pname(*k)]} for k in months])
        bs_periods = [pname(year, m) for m in range(1, period + 1)] + [pname(year - 1, period)]
        bs = await fs.get_balance_sheet(bs_periods)

        def bs_row(section, label):
            r = next((x for x in bs.get(section, []) if x["label"] == label), None)
            return r["values"] if r else [None] * len(bs_periods)

        cash = bs_row("current_assets", "CASH & CASH EQUIVALENTS")
        ar = bs_row("current_assets", "ACCOUNT RECEIVABLES")
        ap = bs_row("current_liabilities", "ACCOUNT PAYABLES")
        this_year = slice(12, 12 + period)
        pat = pl["profit_after_tax"][this_year]

        np_plan = [plan.get(("Net Profit", "", m)) for m in range(1, period + 1)]
        ytd_np = sum(v for v in pat if v is not None) / 1e6
        ytd_np_plan = sum(v for v in np_plan if v is not None) if any(v is not None for v in np_plan) else None
        cf_plan = plan.get(("Cashflow Ending Balance", "", period))
        financial = {
            "net_profit": [{"month": m, "actual": _mio(pat[m - 1]), "plan": np_plan[m - 1]} for m in range(1, period + 1)],
            "net_profit_ytd": round(ytd_np, 1),
            "net_profit_ytd_plan": ytd_np_plan,
            # A progress ratio only means something against a positive plan.
            "net_profit_progress_pct": _ratio_pct(ytd_np, ytd_np_plan) if ytd_np_plan and ytd_np_plan > 0 else None,
            "cash": [{"month": m, "actual": _mio(cash[m - 1]), "plan": plan.get(("Cashflow Ending Balance", "", m))}
                     for m in range(1, period + 1)],
            "cash_plan": cf_plan,
            "cash_achievement_pct": _ratio_pct(_mio(cash[period - 1]), cf_plan),
        }

        window = slice(period, 12 + period)   # the 12 months ending at the selected one
        sales12 = sum(v or 0 for v in pl["total_net_sales"][window])
        cogs12 = sum(v or 0 for v in pl["total_cogs"][window])
        avg = lambda a: (a[period - 1] + a[-1]) / 2 if a[period - 1] is not None and a[-1] is not None else None
        avg_ar, avg_ap = avg(ar), avg(ap)
        ratios = {
            "dso_days": round(avg_ar / sales12 * 365, 1) if avg_ar is not None and sales12 else None,
            "dpo_days": round(avg_ap / cogs12 * 365, 1) if avg_ap is not None and cogs12 else None,
            "sales_12m": _mio(sales12), "cogs_12m": _mio(cogs12),
            "avg_ar": _mio(avg_ar), "avg_ap": _mio(avg_ap),
        }
    except Exception as e:  # Oracle down must not blank the HR half of the page
        logging.getLogger(__name__).exception("[eis admin] Oracle financial figures failed")
        financial = {"error": str(e)}
        ratios = {"error": str(e)}

    return financial, ratios


async def ratios_for_month(eis_db, year: int, period: int, oracle: Optional[dict]) -> dict:
    """DSO / DPO for the Administration page and the EIS Summary's NWC.
    Primary source is the Administration_Ratios sheet (eis.adm_ratio, from
    the EIS Template upload) — user's rule, 2026-10-22: DSO = Average AR ÷
    Sales × 365, DPO = Average AP ÷ COGS × 365 — for the selected month or
    the latest earlier month of that year holding both components (Jul
    2026: DSO 91.65, DPO 90.05). `oracle` (the ratios block from
    financial_and_ratios) is used per metric only when the sheet has no
    such month. Each metric records its source and month."""
    rows = (await eis_db.execute(text("""
        SELECT metric, month_num, lower(value_type) AS value_type, value
        FROM eis.adm_ratio
        WHERE fiscal_year = :y AND month_num <= :p AND metric IN ('DSO', 'DPO')
    """), {"y": year, "p": period})).mappings().all()
    parts = {}
    for r in rows:
        if r["value"] is not None:
            parts.setdefault((r["metric"], r["month_num"]), {})[r["value_type"]] = float(r["value"])

    oracle_ok = bool(oracle) and "error" not in oracle
    out = {"error": None}
    for key, metric, num_t, den_t, num_k, den_k, o_num, o_den in (
        ("dso", "DSO", "average ar", "sales", "avg_ar", "sales", "avg_ar", "sales_12m"),
        ("dpo", "DPO", "average ap", "cogs", "avg_ap", "cogs", "avg_ap", "cogs_12m"),
    ):
        hit = None
        for m in range(period, 0, -1):
            v = parts.get((metric, m), {})
            if v.get(num_t) is not None and v.get(den_t):
                hit = (m, v[num_t], v[den_t])
                break
        if hit:
            m, num, den = hit
            out.update({f"{key}_days": round(num / den * 365, 1), f"{key}_source": "template",
                        f"{key}_month": m, num_k: round(num, 1), den_k: round(den, 1)})
        elif oracle_ok and oracle.get(f"{key}_days") is not None:
            out.update({f"{key}_days": oracle[f"{key}_days"], f"{key}_source": "oracle", f"{key}_month": period,
                        num_k: oracle.get(o_num), den_k: oracle.get(o_den)})
        else:
            out.update({f"{key}_days": None, f"{key}_source": None, f"{key}_month": None, num_k: None, den_k: None})
    if out["dso_days"] is None and out["dpo_days"] is None and not oracle_ok:
        out["error"] = (oracle or {}).get("error")
    return out


@router.get("/dashboard")
async def administration_dashboard(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    main_db: AsyncSession = Depends(get_main_db), eis_db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    import asyncio
    import logging
    log = logging.getLogger(__name__)

    hc_plan_row, plan, has_plan = await load_admin_plans(eis_db, year, period)

    def plan_series(metric):
        return [plan.get((metric, "", m)) for m in range(1, period + 1)]

    # ── Personnel (HRGA) ─────────────────────────────────────────
    emp_rows = (await main_db.execute(
        select(Employee.department, Employee.team, Employee.date_of_joining,
               Employee.resign_date, Employee.employment_status)
        .where(Employee.date_of_joining.isnot(None))
    )).all()
    personnel = _personnel(emp_rows, year, period)
    personnel["plan"] = float(hc_plan_row[1]) if hc_plan_row else None
    personnel["plan_month"] = hc_plan_row[0] if hc_plan_row else None
    personnel["achievement_pct"] = _ratio_pct(personnel["total"], personnel["plan"])

    financial, oracle_ratios = await financial_and_ratios(year, period, plan)
    ratios = await ratios_for_month(eis_db, year, period, oracle_ratios)

    # ── Budget (Oracle actual, template plan) ─────────────────────
    budget = None
    try:
        actuals = await asyncio.to_thread(_budget_actuals, year, period)
        bu_plan = plan_series("Budget Usage")
        monthly = []
        for m in range(1, period + 1):
            vals = [actuals.get((m, g)) for g in ADM_GROUPS]
            act = sum(v for v in vals if v is not None) / 1e6 if any(v is not None for v in vals) else None
            monthly.append({"month": m, "actual": round(act, 1) if act is not None else None, "plan": bu_plan[m - 1]})
        ytd_actual = sum(r["actual"] for r in monthly if r["actual"] is not None)
        ytd_plan = sum(v for v in bu_plan if v is not None) if any(v is not None for v in bu_plan) else None
        # Budget Allocation plan is YTD-cumulative in the template: latest month <= period
        alloc_plan = {}
        for (metric, dept, m), v in plan.items():
            g = _TPL_DEPT.get(dept)
            if metric == "Budget Allocation" and g and v is not None and m >= alloc_plan.get(g, (0, None))[0]:
                alloc_plan[g] = (m, v)
        dept_ytd = {g: sum(actuals.get((m, g), 0.0) for m in range(1, period + 1)) / 1e6 for g in ADM_GROUPS}
        dept_total = sum(v for v in dept_ytd.values() if v > 0)
        budget = {
            "monthly": monthly,
            "ytd_actual": round(ytd_actual, 1),
            "ytd_plan": ytd_plan,
            "achievement_pct": _ratio_pct(ytd_actual, ytd_plan),
            "departments": [
                {"group": g, "actual": round(dept_ytd[g], 1),
                 "share_pct": _ratio_pct(dept_ytd[g], dept_total) if dept_ytd[g] > 0 else 0,
                 "plan": alloc_plan[g][1] if g in alloc_plan else None}
                for g in ADM_GROUPS
            ],
        }
    except Exception as e:
        log.exception("[eis admin] Oracle budget actuals failed")
        budget = {"error": str(e)}

    return {
        "year": year, "period": period,
        "personnel": personnel, "financial": financial, "ratios": ratios, "budget": budget,
        "has_plan": has_plan,
    }
