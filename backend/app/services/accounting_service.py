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

    # ── Inventory RM PM ──────────────────────────────────────────────────────

    async def get_inventory_rm_pm(self, period: str, include_begin: bool = True) -> dict:
        """
        Inventory RM PM monthly report matching Template_Dashboard_Inventory-monthly.xlsx.
        - Movements for the period from MTL_MATERIAL_TRANSACTIONS (org 121)
        - Price from CKDO_GET_ITEM_COST
        - Beginning balance: sum of 5-year lookback (skippable for speed)
        """
        from calendar import monthrange

        MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        try:
            mon_str, yr_str = period.upper().split("-")
            month = MONTHS[mon_str]
            year  = 2000 + int(yr_str)
        except Exception:
            return {"success": False, "error": f"Invalid period: {period}. Use e.g. JAN-26", "data": []}

        _, last_day = monthrange(year, month)
        date_from = f"{year}-{month:02d}-01"
        date_to   = f"{year}-{month:02d}-{last_day:02d}"

        mvt_sql = """
            SELECT
                msib.segment1                                                     AS item_code,
                SUBSTR(NVL(msib.description, '-'), 1, 80)                        AS item_name,
                msib.primary_uom_code                                            AS uom,
                CASE
                    WHEN UPPER(msib.segment1) LIKE '02A%' THEN 'API'
                    WHEN UPPER(msib.segment1) LIKE '02B%' THEN 'EXCIPIENT'
                    WHEN UPPER(msib.segment1) LIKE '02%'  THEN 'API & EXCIPIENT'
                    WHEN UPPER(msib.segment1) LIKE '01P%' THEN 'PRIMARY PACKAGING'
                    WHEN UPPER(msib.segment1) LIKE '01S%' THEN 'SECONDARY PACKAGING'
                    WHEN UPPER(msib.segment1) LIKE '01%'  THEN 'PACKAGING'
                    ELSE NVL(msib.item_type, 'OTHER')
                END                                                              AS material_type,
                ROUND(NVL(CKDO_GET_ITEM_COST(:period, msib.inventory_item_id), 0), 4) AS unit_price,
                mtt.transaction_type_name                                        AS trx_type,
                SUM(mmt.primary_quantity)                                        AS qty,
                msib.inventory_item_id                                           AS item_id
            FROM apps.mtl_material_transactions mmt
            JOIN apps.mtl_system_items_b msib
                ON  msib.inventory_item_id = mmt.inventory_item_id
                AND msib.organization_id   = mmt.organization_id
            JOIN apps.mtl_transaction_types mtt
                ON  mtt.transaction_type_id = mmt.transaction_type_id
            WHERE mmt.organization_id = 121
              AND mmt.transaction_date >= TO_DATE(:date_from, 'YYYY-MM-DD')
              AND mmt.transaction_date <  TO_DATE(:date_to,   'YYYY-MM-DD') + 1
            GROUP BY
                msib.segment1, msib.description, msib.primary_uom_code,
                msib.item_type, mtt.transaction_type_name, msib.inventory_item_id
            ORDER BY msib.segment1, mtt.transaction_type_name
        """

        beg_sql = """
            SELECT mmt.inventory_item_id AS item_id,
                   SUM(mmt.primary_quantity) AS begin_qty
            FROM apps.mtl_material_transactions mmt
            WHERE mmt.organization_id = 121
              AND mmt.transaction_date >= ADD_MONTHS(TO_DATE(:date_from, 'YYYY-MM-DD'), -60)
              AND mmt.transaction_date <  TO_DATE(:date_from, 'YYYY-MM-DD')
            GROUP BY mmt.inventory_item_id
        """

        try:
            mvt_rows = await asyncio.to_thread(
                self._query, mvt_sql,
                {"period": period.upper(), "date_from": date_from, "date_to": date_to}
            )
            beg_rows = await asyncio.to_thread(self._query, beg_sql, {"date_from": date_from}) \
                       if include_begin else []
        except Exception as e:
            logger.error("inventory_rm_pm_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

        begin_map = {r["item_id"]: float(r["begin_qty"] or 0) for r in beg_rows}

        def categorize(name: str) -> str:
            n = name.lower()
            if any(k in n for k in ["receipt", "purchase", "receiving"]) \
               and "return" not in n: return "purchase"
            if any(k in n for k in ["return to vendor", "return to receiving",
                                     "return to supplier"]): return "return_vendor"
            if "wip" in n and "return" in n:  return "wip_return"
            if "wip" in n and "issue" in n:   return "wip_issue"
            if "wip" in n:                    return "wip_issue"
            if any(k in n for k in ["sample", "qc", "quality"]): return "sample"
            if any(k in n for k in ["trial", "media fill", "project"]): return "misc"
            if any(k in n for k in ["disposal", "scrap", "written off"]): return "disposal"
            if any(k in n for k in ["adjustment", "cycle count",
                                     "physical inventory"]): return "adjustment"
            return "other"

        CATS = ["purchase", "return_vendor", "sample", "wip_issue",
                "wip_return", "misc", "disposal", "adjustment", "other"]

        items: dict = {}
        for r in mvt_rows:
            iid = r["item_id"]
            if iid not in items:
                items[iid] = {
                    "item_code":     r["item_code"],
                    "item_name":     r["item_name"],
                    "uom":           r["uom"],
                    "material_type": r["material_type"],
                    "unit_price":    float(r["unit_price"] or 0),
                    "movements":     [],
                    **{c: 0.0 for c in CATS},
                }
            cat = categorize(r["trx_type"])
            qty = float(r["qty"] or 0)
            items[iid][cat] = round(items[iid][cat] + qty, 6)
            items[iid]["movements"].append({"trx_type": r["trx_type"], "qty": round(qty, 6)})

        result = []
        for iid, d in sorted(items.items(), key=lambda x: x[1]["item_code"]):
            begin_qty  = round(begin_map.get(iid, 0), 6)
            net_mvt    = sum(d[c] for c in CATS)
            end_qty    = round(begin_qty + net_mvt, 6)
            price      = d["unit_price"]
            result.append({
                "item_code":      d["item_code"],
                "item_name":      d["item_name"],
                "uom":            d["uom"],
                "material_type":  d["material_type"],
                "unit_price":     price,
                "begin_qty":      begin_qty,
                "begin_amount":   round(begin_qty * price, 2),
                "purchase":       d["purchase"],
                "return_vendor":  d["return_vendor"],
                "sample":         d["sample"],
                "wip_issue":      d["wip_issue"],
                "wip_return":     d["wip_return"],
                "misc":           d["misc"],
                "disposal":       d["disposal"],
                "adjustment":     d["adjustment"],
                "other":          d["other"],
                "end_qty":        end_qty,
                "end_amount":     round(end_qty * price, 2),
                "movements":      d["movements"],
            })

        return {
            "success":   True,
            "count":     len(result),
            "period":    period.upper(),
            "date_from": date_from,
            "date_to":   date_to,
            "data":      result,
        }

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
                msib.primary_uom_code                            AS primary_uom,
                ROUND(NVL(mmt.actual_cost, 0), 4)               AS unit_cost,
                ROUND(NVL(mmt.actual_cost, 0)
                      * ABS(mmt.transaction_quantity), 2)        AS trx_value,
                NVL(mmt.subinventory_code, '-')                  AS subinventory,
                NVL(mmt.transfer_subinventory, '-')              AS transfer_subinv,
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
