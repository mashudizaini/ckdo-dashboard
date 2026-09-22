"""
PPWH Service — Inventory In / Inventory Out / Kartu Stok
─────────────────────────────────────────
Reads from the eis_dashboard Postgres warehouse only — no live Oracle
queries here, deliberately (see sales_marketing_service.py's docstring
for why: this session spent a lot of time fixing dashboard/chatbot drift
caused by independent live-Oracle queries elsewhere). All three tabs read
eis.fact_inventory_txn, populated by app.tasks.eis_etl_tasks.etl_inventory_txn.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import get_settings

settings = get_settings()


class PPWHService:

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
            "SELECT DISTINCT organization_code, organization_name "
            "FROM eis.fact_inventory_txn "
            "WHERE organization_code IS NOT NULL "
            "ORDER BY organization_code"
        )

    async def _direction_summary(self, direction: str, date_from: str, date_to: str, organization_code: str = None) -> dict:
        trend = self._query(
            """
            SELECT transaction_date::date AS txn_date, SUM(quantity) AS qty
            FROM eis.fact_inventory_txn
            WHERE direction = %(direction)s
              AND transaction_date >= %(date_from)s
              AND transaction_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_code)s IS NULL OR organization_code = %(organization_code)s)
            GROUP BY txn_date
            ORDER BY txn_date
            """,
            {"direction": direction, "date_from": date_from, "date_to": date_to, "organization_code": organization_code},
        )
        by_type = self._query(
            """
            SELECT transaction_type_name, COUNT(*) AS txn_count, SUM(quantity) AS qty
            FROM eis.fact_inventory_txn
            WHERE direction = %(direction)s
              AND transaction_date >= %(date_from)s
              AND transaction_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_code)s IS NULL OR organization_code = %(organization_code)s)
            GROUP BY transaction_type_name
            ORDER BY txn_count DESC
            """,
            {"direction": direction, "date_from": date_from, "date_to": date_to, "organization_code": organization_code},
        )
        for r in trend:
            r["qty"] = abs(float(r["qty"] or 0))
        for r in by_type:
            r["qty"] = abs(float(r["qty"] or 0))
        return {
            "success": True,
            "trend": trend,
            "by_type": by_type,
            "total_qty": sum(r["qty"] for r in by_type),
            "total_txn_count": sum(r["txn_count"] for r in by_type),
        }

    async def get_inbound(self, date_from: str, date_to: str, organization_code: str = None) -> dict:
        return await self._direction_summary("IN", date_from, date_to, organization_code)

    async def get_outbound(self, date_from: str, date_to: str, organization_code: str = None) -> dict:
        return await self._direction_summary("OUT", date_from, date_to, organization_code)

    async def search_items(self, q: str) -> list[dict]:
        return self._query(
            """
            SELECT item_code, MAX(item_description) AS item_description
            FROM eis.fact_inventory_txn
            WHERE item_code ILIKE %(q)s OR item_description ILIKE %(q)s
            GROUP BY item_code
            ORDER BY item_code
            LIMIT 20
            """,
            {"q": f"%{q}%"},
        )

    async def get_stock_card(self, item_code: str, date_from: str, date_to: str, organization_code: str = None) -> dict:
        saldo_awal_rows = self._query(
            """
            SELECT COALESCE(SUM(quantity), 0) AS saldo
            FROM eis.fact_inventory_txn
            WHERE item_code = %(item_code)s
              AND transaction_date < %(date_from)s
              AND (%(organization_code)s IS NULL OR organization_code = %(organization_code)s)
            """,
            {"item_code": item_code, "date_from": date_from, "organization_code": organization_code},
        )
        saldo_awal = float(saldo_awal_rows[0]["saldo"] or 0)

        rows = self._query(
            """
            SELECT transaction_id, transaction_date, direction, transaction_type_name,
                   organization_code, organization_name, subinventory_code, subinventory_name,
                   quantity, uom, transaction_reference
            FROM eis.fact_inventory_txn
            WHERE item_code = %(item_code)s
              AND transaction_date >= %(date_from)s
              AND transaction_date < (%(date_to)s::date + INTERVAL '1 day')
              AND (%(organization_code)s IS NULL OR organization_code = %(organization_code)s)
            ORDER BY transaction_date ASC, transaction_id ASC
            """,
            {"item_code": item_code, "date_from": date_from, "date_to": date_to, "organization_code": organization_code},
        )

        running = saldo_awal
        for r in rows:
            qty = float(r["quantity"] or 0)
            running += qty
            r["quantity"] = qty
            r["running_balance"] = running

        item_desc_rows = self._query(
            "SELECT item_description FROM eis.fact_inventory_txn "
            "WHERE item_code = %(item_code)s AND item_description IS NOT NULL LIMIT 1",
            {"item_code": item_code},
        )
        item_description = item_desc_rows[0]["item_description"] if item_desc_rows else None

        return {
            "success": True,
            "item_code": item_code,
            "item_description": item_description,
            "saldo_awal": saldo_awal,
            "rows": rows,
            "saldo_akhir": running,
        }
