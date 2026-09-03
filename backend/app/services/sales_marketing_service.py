"""
Sales & Marketing Service
─────────────────────────────────────────
Reads from the eis_dashboard Postgres warehouse only — no live Oracle
queries here, deliberately. Sales Trend / Sales vs Budget read the
existing eis.fact_sales (populated by etl_sales); Open Sales Order reads
eis.fact_sales_order (populated by etl_sales_orders) — see the "Blueprint
Sales & Marketing" plan for why building straight on the warehouse from
day one avoids the dashboard/chatbot drift this session spent a lot of
time fixing elsewhere (Purchasing, Budget, Financial).
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import get_settings

settings = get_settings()


class SalesMarketingService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        conn = psycopg2.connect(settings.eis_database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params or {})
                return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    async def get_years(self) -> list[int]:
        rows = self._query(
            "SELECT DISTINCT per.fiscal_year FROM eis.fact_sales fs "
            "JOIN eis.dim_period per ON per.id = fs.period_id "
            "ORDER BY per.fiscal_year DESC"
        )
        return [r["fiscal_year"] for r in rows]

    async def get_trend(self, year: int, business_type: str = None) -> list[dict]:
        """Serves both Sales Trend and Sales vs Budget — same underlying
        rows (bp_amount/actual_amount/prior_year_actual per period +
        business_type), just charted differently on the frontend.
        WHERE product_id IS NULL is critical: fact_sales also carries a
        per-product breakdown (added earlier this session) — without this
        filter, summing would double the real total.

        fact_sales stores amounts in MILLIONS IDR (established convention
        across fact_sales/fact_cogs/fact_purchasing — unlike fact_po_line/
        fact_sales_order, which store raw IDR). Multiplied by 1,000,000
        here so the frontend's plain fmtRp()/chart formatting — already
        correct for the raw-IDR tables — doesn't need a special case, and
        doesn't understate these figures by 1,000,000x."""
        rows = self._query(
            """
            SELECT per.period_num, per.period_name, fs.business_type,
                   fs.bp_amount, fs.actual_amount, fs.prior_year_actual
            FROM eis.fact_sales fs
            JOIN eis.dim_period per ON per.id = fs.period_id
            WHERE fs.product_id IS NULL
              AND per.fiscal_year = %(year)s
              AND (%(business_type)s IS NULL OR fs.business_type = %(business_type)s)
            ORDER BY per.period_num, fs.business_type
            """,
            {"year": year, "business_type": business_type},
        )
        for r in rows:
            for k in ("bp_amount", "actual_amount", "prior_year_actual"):
                r[k] = float(r[k] or 0) * 1_000_000
        return rows

    async def get_order_detail(self, year: int, month: int, business_type: str = None) -> list[dict]:
        """Drill-down for a clicked Sales Trend bar (one period + business
        type) — every order line for that month, ANY status (unlike
        get_open_orders, which is deliberately scoped to backlog only;
        a Sales Trend bar represents total sales for the month, so its
        drill-down needs to include CLOSED lines too, not just open
        ones — see the CMO 2022 case that surfaced this exact
        open-vs-total distinction)."""
        return self._query(
            """
            SELECT order_number, line_num, item_code, item_description, business_type,
                   customer_name, currency_code, quantity, unit_selling_price,
                   amount_orig, amount_idr, flow_status_code, ordered_date
            FROM eis.fact_sales_order
            WHERE EXTRACT(YEAR FROM ordered_date) = %(year)s
              AND EXTRACT(MONTH FROM ordered_date) = %(month)s
              AND (%(business_type)s IS NULL OR business_type = %(business_type)s)
            ORDER BY amount_idr DESC
            """,
            {"year": year, "month": month, "business_type": business_type},
        )

    async def get_open_orders(
        self, customer_name: str = None, business_type: str = None, item_code: str = None,
    ) -> dict:
        rows = self._query(
            """
            SELECT order_number, line_num, item_code, item_description, business_type,
                   customer_name, currency_code, quantity, unit_selling_price,
                   amount_orig, amount_idr, schedule_ship_date, flow_status_code, ordered_date
            FROM eis.fact_sales_order
            WHERE flow_status_code NOT IN ('CLOSED', 'CANCELLED')
              AND (%(customer_name)s IS NULL OR customer_name ILIKE %(customer_like)s)
              AND (%(business_type)s IS NULL OR business_type = %(business_type)s)
              AND (%(item_code)s IS NULL OR item_code = %(item_code)s)
            ORDER BY schedule_ship_date ASC NULLS LAST
            LIMIT 200
            """,
            {
                "customer_name": customer_name, "customer_like": f"%{customer_name}%" if customer_name else None,
                "business_type": business_type,
                "item_code": item_code,
            },
        )
        order_numbers = {r["order_number"] for r in rows}
        total_backlog_idr = sum(float(r["amount_idr"] or 0) for r in rows)
        oldest_days = None
        today_rows = [r for r in rows if r.get("ordered_date")]
        if today_rows:
            from datetime import date
            oldest_days = max((date.today() - r["ordered_date"]).days for r in today_rows)
        return {
            "success": True,
            "count": len(rows),
            "data": rows,
            "kpi": {
                "open_order_count": len(order_numbers),
                "open_line_count": len(rows),
                "total_backlog_idr": round(total_backlog_idr, 2),
                "oldest_order_days": oldest_days,
            },
        }
