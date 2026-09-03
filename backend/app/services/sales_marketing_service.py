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

        actual_amount is derived from SUM(fact_sales_order.amount_idr) —
        the same table the chart's click-through drill-down (get_order_
        detail) reads from — rather than fact_sales.actual_amount, which
        is computed independently by a separate ETL job (etl_sales) and
        was found live to drift from the true per-line sum by a small
        rounding amount (fact_sales rounds at million-scale; a real April
        2026 Export case: chart showed Rp 18.529.730.000, the single
        underlying order line summed to Rp 18.529.733.664 — same order,
        just two independently-rounded aggregates). Deriving the chart
        from the exact same rows the drill-down shows makes them agree by
        construction, not by coincidence. Falls back to fact_sales.
        actual_amount (×1,000,000 — that table's own millions-IDR
        convention) only for a period/business_type fact_sales_order has
        no rows for yet (e.g. before its backfill's effective range).
        bp_amount/prior_year_actual still come from fact_sales — no
        order-line equivalent exists for budget plan or last year's
        closing figures."""
        rows = self._query(
            """
            SELECT per.period_num, per.period_name, fs.business_type,
                   fs.bp_amount, fs.actual_amount AS fallback_actual, fs.prior_year_actual,
                   so.actual_from_orders
            FROM eis.fact_sales fs
            JOIN eis.dim_period per ON per.id = fs.period_id
            LEFT JOIN (
                SELECT EXTRACT(YEAR FROM ordered_date)::int AS fiscal_year,
                       EXTRACT(MONTH FROM ordered_date)::int AS period_num,
                       business_type, SUM(amount_idr) AS actual_from_orders
                FROM eis.fact_sales_order
                GROUP BY 1, 2, 3
            ) so ON so.fiscal_year = per.fiscal_year AND so.period_num = per.period_num
                AND so.business_type = fs.business_type
            WHERE fs.product_id IS NULL
              AND per.fiscal_year = %(year)s
              AND (%(business_type)s IS NULL OR fs.business_type = %(business_type)s)
            ORDER BY per.period_num, fs.business_type
            """,
            {"year": year, "business_type": business_type},
        )
        for r in rows:
            actual_from_orders = r.pop("actual_from_orders")
            fallback_actual = r.pop("fallback_actual")
            r["actual_amount"] = (
                float(actual_from_orders) if actual_from_orders is not None
                else float(fallback_actual or 0) * 1_000_000
            )
            for k in ("bp_amount", "prior_year_actual"):
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
