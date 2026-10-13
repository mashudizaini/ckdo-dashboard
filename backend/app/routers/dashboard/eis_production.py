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


# ══════════════════════════════════════════════════════════════
# Production dashboard — reads the eis.prod_* tables filled by the EIS
# template upload (eis_data_upload: /production-template/upload), not the
# ETL fact_* tables above. One call returns every block of the page, with
# the formulas of the template's own Production_Dashboard sheet:
#   Batch production  cumulative Σ plan / Σ actual of Local+CMO+Export
#   Yield             (Total Company) actual ÷ batch size, per month
#   DIO               average inventory ÷ COGS (12-month rolling) × 365
#   Overtime ratio    overtime hour ÷ working hour
#   OEE               availability × performance × quality
# Point-in-time blocks (yield, DIO, release) use the selected month, or the
# latest earlier month of that year that has data; snapshot blocks (GPM,
# machine utilization — the template has one period each) use the latest
# snapshot at or before the selected month, else the latest one there is.
# Each carries its as-of month so the page can say which month it shows.
# ══════════════════════════════════════════════════════════════

TOTAL_SEGMENT = "(Total Company)"
YIELD_TARGET_PCT = 95.0


def _f(v):
    return float(v) if v is not None else None


def _latest(rows: dict, period: int, has_data):
    """Latest month <= period whose row satisfies has_data -> (month, row)."""
    for m in range(period, 0, -1):
        if m in rows and has_data(rows[m]):
            return m, rows[m]
    return None, None


async def _snapshot(db, table: str, cols: str, year: int, period: int):
    """Rows of the latest (year, month) snapshot <= (year, period), falling
    back to the latest snapshot overall."""
    at = (await db.execute(text(f"""
        SELECT fiscal_year, month_num FROM eis.{table}
        GROUP BY fiscal_year, month_num
        ORDER BY (fiscal_year * 100 + month_num) <= (:y * 100 + :p) DESC,
                 fiscal_year DESC, month_num DESC
        LIMIT 1
    """), {"y": year, "p": period})).first()
    if not at:
        return None, []
    rows = (await db.execute(
        text(f"SELECT {cols} FROM eis.{table} WHERE fiscal_year = :y AND month_num = :m"),
        {"y": at[0], "m": at[1]},
    )).mappings().all()
    return {"year": at[0], "month": at[1]}, rows


@router.get("/dashboard")
async def production_dashboard(
    year: int = Query(...), period: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    # ── Batch & yield ────────────────────────────────────────────
    by = (await db.execute(text("""
        SELECT month_num, segment, plan_qty, batch_size_qty, actual_qty
        FROM eis.prod_batch_yield
        WHERE fiscal_year = :y AND month_num <= :p
    """), {"y": year, "p": period})).mappings().all()

    seg = {}    # month -> {"plan": x|None, "actual": x|None}, Local+CMO+Export
    total = {}  # month -> (Total Company) {"batch_size": x, "actual": x}
    for r in by:
        m = r["month_num"]
        if r["segment"] == TOTAL_SEGMENT:
            total[m] = {"batch_size": _f(r["batch_size_qty"]), "actual": _f(r["actual_qty"])}
            continue
        s = seg.setdefault(m, {"plan": None, "actual": None})
        for k, col in (("plan", "plan_qty"), ("actual", "actual_qty")):
            if r[col] is not None:
                s[k] = (s[k] or 0) + float(r[col])

    batch, plan_cum, actual_cum = [], 0.0, 0.0
    for m in range(1, period + 1):
        s = seg.get(m, {})
        plan = s.get("plan")
        actual = s.get("actual")
        if actual is None:
            actual = (total.get(m) or {}).get("actual")
        if plan is not None:
            plan_cum += plan
        if actual is not None:
            actual_cum += actual
        batch.append({
            "month": m, "plan": plan, "actual": actual,
            "plan_cum": round(plan_cum) if plan is not None else None,
            "actual_cum": round(actual_cum) if actual is not None else None,
        })

    yield_monthly = []
    for m in range(1, period + 1):
        t = total.get(m) or {}
        bs, act = t.get("batch_size"), t.get("actual")
        pct = round(act / bs * 100, 2) if bs and act is not None else None
        yield_monthly.append({"month": m, "batch_size": bs, "actual": act, "yield_pct": pct})
    ym, yr = _latest({r["month"]: r for r in yield_monthly}, period, lambda r: r["yield_pct"] is not None)

    # ── Ratios: DIO + overtime ───────────────────────────────────
    ratios = (await db.execute(text("""
        SELECT metric, month_num, lower(value_type) AS value_type, value
        FROM eis.prod_ratio
        WHERE fiscal_year = :y AND month_num <= :p
    """), {"y": year, "p": period})).mappings().all()
    dio_raw, ot_raw = {}, {}
    for r in ratios:
        bucket = {"DIO": dio_raw, "Overtime Ratio": ot_raw}.get(r["metric"])
        if bucket is not None:
            bucket.setdefault(r["month_num"], {})[r["value_type"]] = _f(r["value"])

    dio_monthly = {}
    for m, v in dio_raw.items():
        cogs, inv = v.get("cogs"), v.get("average inventory")
        dio_monthly[m] = {
            "cogs": cogs, "avg_inventory": inv,
            "days": round(inv / cogs * 365, 1) if cogs and inv is not None else None,
        }
    dm, dr = _latest(dio_monthly, period, lambda r: r["days"] is not None)

    overtime = []
    for m in range(1, period + 1):
        v = ot_raw.get(m, {})
        ot, wh = v.get("overtime hour"), v.get("working hour")
        overtime.append({
            "month": m, "overtime_hours": ot, "working_hours": wh,
            "ratio_pct": round(ot / wh * 100, 2) if wh and ot is not None else None,
        })

    # ── Quality release ──────────────────────────────────────────
    rel = (await db.execute(text("""
        SELECT month_num, AVG(plan_days) AS plan_days, AVG(actual_days) AS actual_days
        FROM eis.prod_release
        WHERE fiscal_year = :y AND month_num <= :p
        GROUP BY month_num
    """), {"y": year, "p": period})).mappings().all()
    rel_by_m = {r["month_num"]: {"plan_days": _f(r["plan_days"]), "actual_days": _f(r["actual_days"])} for r in rel}
    rm, rr = _latest(rel_by_m, period, lambda r: r["plan_days"] is not None or r["actual_days"] is not None)

    # ── Snapshots: GPM + machine utilization ─────────────────────
    gpm_at, gpm_rows = await _snapshot(db, "prod_gpm", "product_name, gpm_ratio", year, period)
    gpm_items = sorted(
        ({"product": r["product_name"], "gpm_pct": round(float(r["gpm_ratio"]) * 100, 1)}
         for r in gpm_rows if r["gpm_ratio"] is not None),
        key=lambda x: x["gpm_pct"],
    )

    mu_at, mu_rows = await _snapshot(
        db, "prod_machine_utilization", "availability_pct, performance_pct, quality_pct", year, period)
    machine = None
    if mu_rows:
        r = mu_rows[0]
        a, p, q = _f(r["availability_pct"]), _f(r["performance_pct"]), _f(r["quality_pct"])
        pct = lambda v: round(v * 100, 1) if v is not None else None
        machine = {
            **mu_at,
            "availability_pct": pct(a), "performance_pct": pct(p), "quality_pct": pct(q),
            "oee_pct": pct(a * p * q) if None not in (a, p, q) else None,
        }

    return {
        "year": year, "period": period,
        "has_data": bool(by or ratios or rel or gpm_rows or mu_rows),
        "batch": batch,
        "yield": {
            "monthly": yield_monthly,
            "current": {"month": ym, "yield_pct": yr["yield_pct"]} if yr else None,
            "target_pct": YIELD_TARGET_PCT,
        },
        "dio": {"month": dm, **dr} if dr else None,
        "release": {"month": rm, **rr} if rr else None,
        "gpm": {**gpm_at, "items": gpm_items} if gpm_at else None,
        "machine": machine,
        "overtime": overtime,
    }
