"""
Production Service — Batch Status / Batch Yield / Schedule Adherence
─────────────────────────────────────────
Reads from the eis_dashboard Postgres warehouse only — no live Oracle
queries here (same rationale as ppwh_service.py / sales_marketing_service.py).
All three tabs read eis.fact_batch, populated by
app.tasks.eis_etl_tasks.etl_batches (Oracle OPM gme_batch_header +
gme_material_details's produced-item line).
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import get_settings

settings = get_settings()


class ProductionService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        conn = psycopg2.connect(settings.eis_database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params or {})
                return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    async def get_organizations(self) -> list[dict]:
        return self._query(
            "SELECT DISTINCT organization_id, organization_name "
            "FROM eis.fact_batch "
            "WHERE organization_name IS NOT NULL "
            "ORDER BY organization_name"
        )

    async def get_status_overview(self, date_from: str, date_to: str, organization_id: str = None) -> dict:
        by_status = self._query(
            """
            SELECT batch_status_name, COUNT(*) AS batch_count
            FROM eis.fact_batch
            WHERE plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
            GROUP BY batch_status_name
            ORDER BY batch_count DESC
            """,
            {"date_from": date_from, "date_to": date_to, "organization_id": organization_id},
        )
        trend = self._query(
            """
            SELECT plan_start_date::date AS txn_date, COUNT(*) AS batch_count
            FROM eis.fact_batch
            WHERE plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
            GROUP BY txn_date
            ORDER BY txn_date
            """,
            {"date_from": date_from, "date_to": date_to, "organization_id": organization_id},
        )
        rows = self._query(
            """
            SELECT batch_id, batch_no, organization_name, batch_status_name,
                   product_item_code, product_item_description,
                   plan_start_date, actual_start_date, plan_cmplt_date, actual_cmplt_date
            FROM eis.fact_batch
            WHERE plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
            ORDER BY plan_start_date DESC
            LIMIT 200
            """,
            {"date_from": date_from, "date_to": date_to, "organization_id": organization_id},
        )
        total = sum(r["batch_count"] for r in by_status)
        cancelled = next((r["batch_count"] for r in by_status if r["batch_status_name"] == "Cancelled"), 0)
        cancellation_rate = round(cancelled / total * 100, 1) if total else 0.0
        return {
            "success": True,
            "total_batches": total,
            "cancellation_rate": cancellation_rate,
            "by_status": by_status,
            "trend": trend,
            "rows": rows,
        }

    async def get_yield(self, date_from: str, date_to: str, organization_id: str = None, product_code: str = None) -> dict:
        by_product = self._query(
            """
            SELECT product_item_code, product_item_description,
                   COUNT(*) AS batch_count,
                   SUM(product_plan_qty) AS total_plan_qty,
                   SUM(product_actual_qty) AS total_actual_qty
            FROM eis.fact_batch
            WHERE batch_status IN (3, 4)
              AND plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
              AND (%(product_code)s IS NULL OR product_item_code = %(product_code)s)
              AND product_plan_qty IS NOT NULL AND product_plan_qty > 0
            GROUP BY product_item_code, product_item_description
            ORDER BY batch_count DESC
            """,
            {"date_from": date_from, "date_to": date_to, "organization_id": organization_id, "product_code": product_code},
        )
        for r in by_product:
            plan = float(r["total_plan_qty"] or 0)
            actual = float(r["total_actual_qty"] or 0)
            r["total_plan_qty"] = plan
            r["total_actual_qty"] = actual
            r["yield_pct"] = round(actual / plan * 100, 1) if plan else None

        rows = self._query(
            """
            SELECT batch_id, batch_no, organization_name, batch_status_name,
                   product_item_code, product_item_description,
                   product_plan_qty, product_actual_qty, product_uom, actual_cmplt_date
            FROM eis.fact_batch
            WHERE batch_status IN (3, 4)
              AND plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
              AND (%(product_code)s IS NULL OR product_item_code = %(product_code)s)
              AND product_plan_qty IS NOT NULL AND product_plan_qty > 0
            ORDER BY actual_cmplt_date DESC NULLS LAST
            LIMIT 200
            """,
            {"date_from": date_from, "date_to": date_to, "organization_id": organization_id, "product_code": product_code},
        )
        for r in rows:
            plan = float(r["product_plan_qty"] or 0)
            actual = float(r["product_actual_qty"] or 0)
            r["product_plan_qty"] = plan
            r["product_actual_qty"] = actual
            r["yield_pct"] = round(actual / plan * 100, 1) if plan else None

        total_plan = sum(r["total_plan_qty"] for r in by_product)
        total_actual = sum(r["total_actual_qty"] for r in by_product)
        overall_yield_pct = round(total_actual / total_plan * 100, 1) if total_plan else None

        return {
            "success": True,
            "overall_yield_pct": overall_yield_pct,
            "by_product": by_product,
            "rows": rows,
        }

    async def get_schedule_adherence(self, date_from: str, date_to: str, organization_id: str = None) -> dict:
        where = """
            actual_cmplt_date IS NOT NULL
              AND plan_cmplt_date IS NOT NULL
              AND plan_start_date >= %(date_from)s
              AND plan_start_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_id)s IS NULL OR organization_id = %(organization_id)s)
        """
        params = {"date_from": date_from, "date_to": date_to, "organization_id": organization_id}

        # KPIs over the full matching set — computed separately from the
        # bounded display rows below, since a straight len()/sum() over a
        # LIMIT-ed list would silently understate on_time_rate/avg_delay
        # once more than 200 batches finish in the selected period.
        agg = self._query(
            f"""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE actual_cmplt_date <= plan_cmplt_date) AS on_time,
                   AVG(EXTRACT(EPOCH FROM (actual_cmplt_date - plan_cmplt_date)) / 86400.0) AS avg_delay
            FROM eis.fact_batch
            WHERE {where}
            """,
            params,
        )[0]
        total = agg["total"]
        on_time_rate = round(agg["on_time"] / total * 100, 1) if total else None
        avg_delay = round(float(agg["avg_delay"]), 1) if agg["avg_delay"] is not None else None

        rows = self._query(
            f"""
            SELECT batch_id, batch_no, organization_name, batch_status_name,
                   product_item_code, product_item_description,
                   plan_cmplt_date, actual_cmplt_date,
                   EXTRACT(EPOCH FROM (actual_cmplt_date - plan_cmplt_date)) / 86400.0 AS delay_days
            FROM eis.fact_batch
            WHERE {where}
            ORDER BY delay_days DESC NULLS LAST
            LIMIT 200
            """,
            params,
        )
        for r in rows:
            r["delay_days"] = round(float(r["delay_days"]), 1) if r["delay_days"] is not None else None

        return {
            "success": True,
            "total_batches": total,
            "on_time_rate": on_time_rate,
            "avg_delay_days": avg_delay,
            "rows": rows,
        }
