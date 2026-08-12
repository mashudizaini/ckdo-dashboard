"""
Shared helper for pulling PAC's Sales Plan (Business Plan) figures into
other dashboards — EIS Daily Sales' BP card and EIS Summary's Sales
Achievement KPI both used to source Business Plan from their own module's
data instead (a Daily Sales Excel cell that's usually blank, and
eis.fact_sales.bp_amount which turned out to be 0 for every 2026 period)
while PAC's Sales Plan already had the real figures.
See app/services/sales_plan_service.py for the row/meta shape this reads.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sales_plan import SalesPlan


async def pac_monthly_business_plan(db: AsyncSession, year: int) -> tuple[list[float], bool]:
    """Company-wide Sales Business Plan per month (Jan-Dec, in Million IDR).
    Each PAC team stores its plan as one pre-aggregated "Total" document
    (content.meta.area == "Total", meta.type blank) plus one document per
    market/customer segment that sums up to that Total — group by
    (department, team_code) and prefer each team's own Total doc so a team
    is counted exactly once; fall back to summing its segment docs only if
    it never submitted a Total rollup, so that team isn't dropped entirely.

    Only the Total doc is trustworthy for a company-wide figure: segment
    docs can themselves be hierarchical (e.g. team 21's "National" area
    turned out to equal its own "West" + "East" segments combined — a
    sub-rollup, not an independent leaf), so blindly summing every segment
    document overcounts. There's currently no reliable way to tell a leaf
    segment from a sub-rollup from the data alone, so a business-unit
    breakdown (Local/CMO/Export/...) isn't implemented here — only the
    Total-preferring company-wide total, which is confirmed correct against
    the Daily Sales sheet's own Target figures."""
    result = await db.execute(
        select(SalesPlan).where(SalesPlan.plan_year == year, SalesPlan.plan_type == "value")
    )
    groups: dict = {}
    for plan in result.scalars().all():
        content = plan.content or {}
        meta = content.get("meta", {})
        is_total = meta.get("area") == "Total" and not meta.get("type")
        key = (plan.department, plan.team_code)
        bucket = groups.setdefault(key, {"total": None, "segments": []})
        rows = content.get("rows", [])
        if is_total:
            bucket["total"] = rows
        else:
            bucket["segments"].append(rows)

    monthly = [0.0] * 12
    has_data = False
    for bucket in groups.values():
        rows = bucket["total"] if bucket["total"] is not None else [r for seg in bucket["segments"] for r in seg]
        for row in rows:
            # Row shape: [no, country, customer, product, jan..dec, total_value,
            # total_unit, price_usd, price_idr] (20 items) — months start at index 4.
            if len(row) < 16:
                continue
            has_data = True
            for i in range(12):
                v = row[4 + i]
                if isinstance(v, (int, float)):
                    monthly[i] += v
    return [round(v / 1_000_000, 3) for v in monthly], has_data
