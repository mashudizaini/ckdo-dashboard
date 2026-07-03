"""
Accounting Service
─────────────────────────────────────────
Business logic for Accounting Dashboard.
"""
import asyncio
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()


class AccountingService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(columns, row)))
            return rows

    # ── Item Cost Components ─────────────────────────────────────────────────

    async def get_item_cost_components(self, period: str) -> dict:
        """
        Item cost breakdown per cost component class for a given OPM period.
        Mirrors Oracle EBS OPM Cost Management — Item Cost Component report.
        Fixed: ORGANIZATION_ID=121, COST_TYPE_ID=1000 (Actual Cost).
        """
        sql = """
            SELECT
                MSIB.SEGMENT1                                                   AS segment1,
                SUBSTR(NVL(MSIB.DESCRIPTION, '-'), 1, 60)                      AS description,
                NVL(MSIB.ITEM_TYPE, '-')                                        AS item_type,
                CCT.COST_TYPE                                                   AS cost_type,
                CKDO_GET_ITEM_COST(GPS.PERIOD_CODE, MSIB.INVENTORY_ITEM_ID)    AS total_cost,
                CCMV.COST_CMPNTCLS_ID                                           AS cost_cmpntcls_id,
                CCMV.COST_CMPNTCLS_CODE                                         AS cost_cmpntcls_code,
                NVL(CDT.COST_ANALYSIS_CODE, '-')                                AS cost_analysis_code,
                CDT.CMPNT_COST                                                  AS cmpnt_cost,
                GPS.PERIOD_CODE                                                 AS period_code
            FROM apps.CM_CMPT_DTL       CDT
            JOIN apps.CST_COST_TYPES    CCT  ON CCT.COST_TYPE_ID     = CDT.COST_TYPE_ID
            JOIN apps.MTL_SYSTEM_ITEMS_B MSIB
                                         ON  MSIB.INVENTORY_ITEM_ID  = CDT.INVENTORY_ITEM_ID
                                         AND MSIB.ORGANIZATION_ID    = CDT.ORGANIZATION_ID
            JOIN apps.GMF_PERIOD_STATUSES GPS ON GPS.PERIOD_ID        = CDT.PERIOD_ID
            JOIN apps.CM_CMPT_MST_VL    CCMV ON CCMV.COST_CMPNTCLS_ID = CDT.COST_CMPNTCLS_ID
            WHERE CDT.ORGANIZATION_ID  = 121
              AND CDT.COST_TYPE_ID     = 1000
              AND GPS.PERIOD_CODE      = :p_period
            ORDER BY GPS.PERIOD_CODE, MSIB.SEGMENT1, CDT.COST_CMPNTCLS_ID
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, {"p_period": period.upper()})
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            return {"success": True, "count": len(clean), "period": period.upper(), "data": clean}
        except Exception as e:
            logger.error("item_cost_components_error", error=str(e), period=period)
            return {"success": False, "error": str(e), "data": []}

    # ── Material Transactions ────────────────────────────────────────────────

    async def get_material_transactions(
        self,
        date_from: str,
        date_to: str,
        org_code: str = None,
        item_number: str = None,
        trx_type: str = None,
        limit: int = 1000,
    ) -> dict:
        """
        Query MTL_MATERIAL_TRANSACTIONS — same data as Oracle EBS
        Inventory > Material Transactions > Export to Excel.
        """
        limit = min(max(limit, 1), 5000)

        where_extra = ""
        params = {
            "date_from": date_from,
            "date_to":   date_to,
        }
        if org_code:
            where_extra += " AND UPPER(ood.organization_code) = UPPER(:org_code)"
            params["org_code"] = org_code
        if item_number:
            where_extra += " AND UPPER(msib.segment1) LIKE UPPER(:item_number)"
            params["item_number"] = f"%{item_number}%"
        if trx_type:
            where_extra += " AND UPPER(mtt.transaction_type_name) LIKE UPPER(:trx_type)"
            params["trx_type"] = f"%{trx_type}%"

        sql = f"""
            SELECT
                TO_CHAR(mmt.transaction_date, 'DD-MON-YYYY')   AS trx_date,
                TO_CHAR(mmt.transaction_date, 'HH24:MI:SS')    AS trx_time,
                ood.organization_code,
                msib.segment1                                    AS item_number,
                SUBSTR(NVL(msib.description, '-'), 1, 60)        AS item_description,
                mtt.transaction_type_name                        AS trx_type,
                mmt.transaction_quantity                         AS quantity,
                mmt.transaction_uom                              AS uom,
                mmt.primary_quantity                             AS primary_qty,
                mmt.primary_uom_code                             AS primary_uom,
                ROUND(NVL(mmt.actual_cost, 0), 4)               AS unit_cost,
                ROUND(NVL(mmt.actual_cost, 0)
                      * ABS(mmt.transaction_quantity), 2)        AS trx_value,
                NVL(mmt.subinventory_code, '-')                  AS subinventory,
                NVL(mmt.transfer_subinventory, '-')              AS transfer_subinv,
                NVL(mmt.lot_number, '-')                         AS lot_number,
                NVL(mmt.transaction_reference, '-')              AS reference,
                NVL(mmt.source_code, '-')                        AS source_code,
                mmt.transaction_id
            FROM apps.mtl_material_transactions mmt
            JOIN apps.mtl_system_items_b msib
                ON  mmt.inventory_item_id = msib.inventory_item_id
                AND mmt.organization_id   = msib.organization_id
            JOIN apps.mtl_transaction_types mtt
                ON  mmt.transaction_type_id = mtt.transaction_type_id
            JOIN apps.org_organization_definitions ood
                ON  mmt.organization_id = ood.organization_id
            WHERE mmt.transaction_date
                      >= TO_DATE(:date_from, 'YYYY-MM-DD')
              AND mmt.transaction_date
                      <  TO_DATE(:date_to,   'YYYY-MM-DD') + 1
              {where_extra}
            ORDER BY mmt.transaction_date DESC, mmt.transaction_id DESC
            FETCH FIRST {limit} ROWS ONLY
        """

        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            # Convert Decimal / cx_Oracle types to plain Python
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            return {
                "success": True,
                "count":   len(clean),
                "limit":   limit,
                "data":    clean,
            }
        except Exception as e:
            logger.error("material_transactions_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}
