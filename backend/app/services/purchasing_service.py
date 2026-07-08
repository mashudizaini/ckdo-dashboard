"""
Purchasing Service
─────────────────────────────────────────
Oracle EBS queries + Manufacturer Master CRUD (stored in Oracle).
"""
import asyncio
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()


class PurchasingService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _execute(self, sql: str, params: dict = None) -> int:
        """Execute DML, return rowcount."""
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            rows = cursor.rowcount
            conn.commit()
            return rows

    # ── LOV: Organizations ────────────────────────────────────────────────────

    async def get_organizations(self) -> dict:
        sql = """
            SELECT NAME, ORGANIZATION_ID
            FROM HR_ALL_ORGANIZATION_UNITS
            ORDER BY NAME
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("org_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── LOV: Items ────────────────────────────────────────────────────────────

    async def get_items(self, org_id: int, search: str = "") -> dict:
        """Search items in MTL_SYSTEM_ITEMS_B for the given org."""
        sql = """
            SELECT IB.INVENTORY_ITEM_ID AS item_id,
                   IB.SEGMENT1          AS item_code,
                   IT.DESCRIPTION       AS item_description
            FROM MTL_SYSTEM_ITEMS_B IB, MTL_SYSTEM_ITEMS_TL IT
            WHERE IB.ORGANIZATION_ID = IT.ORGANIZATION_ID
              AND IB.INVENTORY_ITEM_ID = IT.INVENTORY_ITEM_ID
              AND IB.ORGANIZATION_ID = :org_id
              AND (:search IS NULL OR UPPER(IB.SEGMENT1) LIKE UPPER(:search_like))
            ORDER BY IB.SEGMENT1
            FETCH FIRST 50 ROWS ONLY
        """
        search_like = f"%{search}%" if search else None
        try:
            rows = await asyncio.to_thread(
                self._query, sql,
                {"org_id": org_id, "search": search or None, "search_like": search_like}
            )
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("item_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Manufacturer Master ───────────────────────────────────────────────────

    async def get_manufacturer_list(self) -> dict:
        sql = """
            SELECT
                MANUFACTURER_ID,
                ITEM_ID,
                ORGANIZATION_ID,
                ITEM_CODE,
                ITEM_DESCRIPTION,
                MANUFACTURER_NAME,
                COUNTRY_OF_ORIGIN,
                CREATED_BY,
                TO_CHAR(CREATION_DATE, 'DD-MON-YYYY') AS CREATION_DATE,
                LAST_UPDATED_BY,
                TO_CHAR(LAST_UPDATE_DATE, 'DD-MON-YYYY') AS LAST_UPDATE_DATE
            FROM XXCKDO_MANUFACTURER_MASTER
            ORDER BY CREATION_DATE DESC
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("manufacturer_list_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def create_manufacturer(self, data: dict, username: str) -> dict:
        sql = """
            INSERT INTO XXCKDO_MANUFACTURER_MASTER (
                ITEM_ID, ORGANIZATION_ID, ITEM_CODE, ITEM_DESCRIPTION,
                MANUFACTURER_NAME, COUNTRY_OF_ORIGIN,
                CREATED_BY, CREATION_DATE, LAST_UPDATED_BY, LAST_UPDATE_DATE
            ) VALUES (
                :item_id, :organization_id, :item_code, :item_description,
                :manufacturer_name, :country_of_origin,
                :created_by, SYSDATE, :created_by, SYSDATE
            )
        """
        try:
            await asyncio.to_thread(self._execute, sql, {
                "item_id":          data["item_id"],
                "organization_id":  data["organization_id"],
                "item_code":        data["item_code"],
                "item_description": data.get("item_description", ""),
                "manufacturer_name": data["manufacturer_name"],
                "country_of_origin": data.get("country_of_origin", ""),
                "created_by":       username,
            })
            return {"success": True, "message": "Data berhasil disimpan"}
        except Exception as e:
            logger.error("manufacturer_create_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def delete_manufacturer(self, manufacturer_id: int) -> dict:
        sql = "DELETE FROM XXCKDO_MANUFACTURER_MASTER WHERE MANUFACTURER_ID = :id"
        try:
            rows = await asyncio.to_thread(self._execute, sql, {"id": manufacturer_id})
            if rows == 0:
                return {"success": False, "error": "Record tidak ditemukan"}
            return {"success": True, "message": "Data berhasil dihapus"}
        except Exception as e:
            logger.error("manufacturer_delete_error", error=str(e))
            return {"success": False, "error": str(e)}

    # ── LOV: Categories, Currencies & Material Types ─────────────────────────

    async def get_material_types(self) -> dict:
        """LOV: distinct material type tags from CKDO_MTRL_TYPE_DIRECT_INDIRECT lookup."""
        sql = """
            SELECT DISTINCT lv.lookup_code, lv.tag, lv.meaning
            FROM fnd_lookup_values_vl lv
            WHERE lv.view_application_id = 700
              AND lv.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
              AND lv.tag                 IS NOT NULL
            ORDER BY lv.tag
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("material_types_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_categories(self) -> dict:
        sql = """
            SELECT DISTINCT mcb.segment1 AS category
            FROM mtl_categories_b      mcb
            JOIN mtl_item_categories   mic ON mic.category_id = mcb.category_id
            WHERE mcb.segment1 IS NOT NULL
            ORDER BY mcb.segment1
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("categories_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_currencies(self) -> dict:
        sql = """
            SELECT DISTINCT currency_code
            FROM po_headers_all
            WHERE type_lookup_code   IN ('STANDARD','BLANKET','CONTRACT')
              AND authorization_status NOT IN ('INCOMPLETE')
            ORDER BY currency_code
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("currencies_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Purchase History (shared SQL fragments) ───────────────────────────────

    _PH_FROM = """
        po_headers_all poh
        JOIN po_lines_all          pol  ON pol.po_header_id     = poh.po_header_id
        JOIN po_line_locations_all poll ON poll.po_line_id      = pol.po_line_id
        LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = pol.item_id
                                       AND msi.organization_id   = poll.ship_to_organization_id
        LEFT JOIN (
            SELECT mic2.inventory_item_id, mic2.organization_id,
                   MIN(mcb2.segment1) AS segment1
            FROM mtl_item_categories mic2
            JOIN mtl_categories_b   mcb2 ON mcb2.category_id = mic2.category_id
            GROUP BY mic2.inventory_item_id, mic2.organization_id
        ) mcb ON mcb.inventory_item_id = msi.inventory_item_id
             AND mcb.organization_id   = msi.organization_id
        JOIN ap_suppliers          aps  ON aps.vendor_id         = poh.vendor_id
        LEFT JOIN xxckdo_manufacturer_master mfr
                                        ON mfr.item_id           = msi.inventory_item_id
                                       AND mfr.organization_id   = msi.organization_id
        LEFT JOIN hr_all_organization_units hou
                                        ON hou.organization_id   = msi.organization_id
        LEFT JOIN fnd_lookup_values_vl  lv_mt
                                        ON  lv_mt.lookup_code         = msi.item_type
                                        AND lv_mt.view_application_id = 700
                                        AND lv_mt.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
    """

    _PH_WHERE = """
        poh.type_lookup_code IN ('STANDARD','BLANKET','CONTRACT')
        AND poh.authorization_status NOT IN ('CANCELLED','INCOMPLETE')
        AND NVL(pol.cancel_flag,'N') = 'N'
        AND (:p_org_id       IS NULL OR NVL(msi.organization_id, poll.ship_to_organization_id) = :p_org_id)
        AND EXTRACT(YEAR FROM poh.creation_date) BETWEEN
              NVL(:p_year_from, EXTRACT(YEAR FROM poh.creation_date))
          AND NVL(:p_year_to,   EXTRACT(YEAR FROM poh.creation_date))
        AND (:p_item_code    IS NULL OR NVL(msi.segment1, TO_CHAR(pol.item_id)) = :p_item_code)
        AND (:p_item_desc    IS NULL
             OR UPPER(pol.item_description) LIKE UPPER('%'||:p_item_desc||'%')
             OR UPPER(msi.description)      LIKE UPPER('%'||:p_item_desc||'%'))
        AND (:p_vendor_name  IS NULL OR UPPER(aps.vendor_name)           LIKE UPPER('%'||:p_vendor_name||'%'))
        AND (:p_manufacturer IS NULL OR UPPER(mfr.manufacturer_name)     LIKE UPPER('%'||:p_manufacturer||'%'))
        AND (:p_country      IS NULL OR mfr.country_of_origin            = :p_country)
        AND (:p_category     IS NULL OR NVL(mcb.segment1,'—')             = :p_category)
        AND (:p_currency     IS NULL OR poh.currency_code                = :p_currency)
        AND (:p_mat_type IS NULL OR lv_mt.tag = :p_mat_type)
    """

    _RATE_CASE = """
        CASE WHEN poh.currency_code = 'IDR' THEN 1
        ELSE COALESCE((
            SELECT gdr.conversion_rate FROM gl_daily_rates gdr
            WHERE  gdr.from_currency   = poh.currency_code
              AND  gdr.to_currency     = 'IDR'
              AND  gdr.conversion_type = NVL(:p_ert,'Corporate')
              AND  gdr.conversion_date = (
                  SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                  WHERE  gdr2.from_currency   = poh.currency_code
                    AND  gdr2.to_currency     = 'IDR'
                    AND  gdr2.conversion_type = NVL(:p_ert,'Corporate')
                    AND  gdr2.conversion_date <= TRUNC(poh.creation_date)
              )
        ), 1) END
    """

    _MAT_TYPE = "lv_mt.tag"

    def _ph_params(self, f: dict) -> dict:
        return {
            "p_org_id":       f.get("org_id")             or None,
            "p_ert":          f.get("exchange_rate_type") or "Corporate",
            "p_year_from":    f.get("year_from")           or None,
            "p_year_to":      f.get("year_to")             or None,
            "p_item_code":    f.get("item_code")           or None,
            "p_item_desc":    f.get("item_desc")           or None,
            "p_vendor_name":  f.get("vendor_name")         or None,
            "p_manufacturer": f.get("manufacturer")        or None,
            "p_country":      f.get("country_of_origin")   or None,
            "p_category":     f.get("category")            or None,
            "p_currency":     f.get("currency_code")       or None,
            "p_mat_type":     f.get("material_type")       or None,
        }

    async def get_purchase_history_detail(self, filters: dict) -> dict:
        """Output 1: Individual PO line detail (like Oracle PO report)."""
        sql = f"""
            SELECT
                poh.segment1                                             AS po_number,
                pol.line_num                                             AS line_num,
                NVL(msi.segment1, TO_CHAR(pol.item_id))                  AS item_code,
                NVL(msi.description, pol.item_description)               AS item_description,
                NVL(mcb.segment1, '—')                                   AS category,
                ({self._MAT_TYPE})                                       AS material_type,
                aps.vendor_name                                          AS supplier_name,
                poh.currency_code,
                NVL(msi.primary_uom_code, pol.unit_meas_lookup_code)     AS uom,
                pol.quantity                                             AS quantity,
                pol.unit_price                                           AS unit_price,
                ROUND(pol.quantity * pol.unit_price, 2)                  AS amount_orig,
                ROUND(pol.quantity * pol.unit_price * ({self._RATE_CASE}), 2) AS amount_idr,
                NVL(poll.quantity_received, 0)                           AS received_qty,
                TO_CHAR(poh.creation_date, 'YYYY-MM-DD')                AS creation_date,
                poh.closed_code                                          AS closure_status,
                NVL(hou.name, TO_CHAR(poll.ship_to_organization_id))     AS organization_name,
                COALESCE(mfr.country_of_origin,'UNKNOWN')                AS country_of_origin
            FROM {self._PH_FROM}
            WHERE {self._PH_WHERE}
            ORDER BY poh.creation_date DESC, poh.segment1, pol.line_num
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, self._ph_params(filters))
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("ph_detail_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_purchase_history_by_item(self, filters: dict) -> dict:
        """Output 2: Per-item pivot by year — Value IDR + Qty per year."""
        year_from = int(filters.get("year_from") or 2020)
        year_to   = int(filters.get("year_to")   or 2026)
        years     = list(range(year_from, year_to + 1))
        pivot     = ",\n            ".join(
            f"SUM(CASE WHEN trx_year={y} THEN line_amount_idr ELSE 0 END) AS value_idr_{y},"
            f"\n            SUM(CASE WHEN trx_year={y} THEN line_qty ELSE 0 END) AS qty_{y}"
            for y in years
        )
        sql = f"""
            WITH base_data AS (
                SELECT
                    NVL(msi.organization_id, poll.ship_to_organization_id)   AS organization_id,
                    NVL(hou.name, TO_CHAR(poll.ship_to_organization_id))     AS organization_name,
                    NVL(msi.segment1, TO_CHAR(pol.item_id))                  AS item_code,
                    NVL(msi.description, pol.item_description)               AS item_description,
                    NVL(mcb.segment1, '—')                                   AS category,
                    ({self._MAT_TYPE})                                       AS material_type,
                    poh.currency_code,
                    NVL(msi.primary_uom_code, pol.unit_meas_lookup_code)     AS uom,
                    EXTRACT(YEAR FROM poh.creation_date)                     AS trx_year,
                    pol.quantity * pol.unit_price * ({self._RATE_CASE})       AS line_amount_idr,
                    pol.quantity                                              AS line_qty
                FROM {self._PH_FROM}
                WHERE {self._PH_WHERE}
            )
            SELECT
                organization_id, organization_name,
                item_code, item_description, category, material_type, currency_code, uom,
                {pivot},
                SUM(line_amount_idr) AS total_value_idr,
                SUM(line_qty)        AS total_qty
            FROM base_data
            GROUP BY organization_id, organization_name, item_code, item_description, category, material_type, currency_code, uom
            ORDER BY item_code
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, self._ph_params(filters))
            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("ph_by_item_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}

    async def get_purchase_history_by_supplier(self, filters: dict) -> dict:
        """Output 3: Per supplier pivot by year."""
        year_from = int(filters.get("year_from") or 2020)
        year_to   = int(filters.get("year_to")   or 2026)
        years     = list(range(year_from, year_to + 1))
        pivot     = ",\n            ".join(
            f"SUM(CASE WHEN trx_year={y} THEN line_amount_orig ELSE 0 END) AS value_orig_{y},"
            f"\n            SUM(CASE WHEN trx_year={y} THEN line_amount_idr  ELSE 0 END) AS value_idr_{y},"
            f"\n            SUM(CASE WHEN trx_year={y} THEN line_qty          ELSE 0 END) AS qty_{y}"
            for y in years
        )
        sql = f"""
            WITH base_data AS (
                SELECT
                    aps.vendor_name                                          AS supplier_name,
                    poh.currency_code,
                    EXTRACT(YEAR FROM poh.creation_date)                     AS trx_year,
                    pol.quantity * pol.unit_price                            AS line_amount_orig,
                    pol.quantity * pol.unit_price * ({self._RATE_CASE})       AS line_amount_idr,
                    pol.quantity                                              AS line_qty,
                    COUNT(DISTINCT NVL(msi.segment1, TO_CHAR(pol.item_id))) OVER (PARTITION BY aps.vendor_name)  AS item_count,
                    COUNT(DISTINCT poh.po_header_id) OVER (PARTITION BY aps.vendor_name) AS po_count
                FROM {self._PH_FROM}
                WHERE {self._PH_WHERE}
            )
            SELECT
                supplier_name, currency_code,
                MIN(item_count) AS item_count,
                MIN(po_count)   AS po_count,
                {pivot},
                SUM(line_amount_orig) AS total_value_orig,
                SUM(line_amount_idr)  AS total_value_idr,
                SUM(line_qty)         AS total_qty
            FROM base_data
            GROUP BY supplier_name, currency_code
            ORDER BY supplier_name
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, self._ph_params(filters))
            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("ph_by_supplier_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}

    # ── Active Suppliers ─────────────────────────────────────────────────────

    async def get_active_suppliers(self, filters: dict) -> dict:
        """
        Suppliers with at least one approved/closed PO in the given period.
        Returns aggregated spend (IDR) + PO count + item/category counts per supplier.
        """
        sql = f"""
            SELECT
                aps.vendor_id                                                   AS vendor_id,
                aps.vendor_name                                                 AS supplier_name,
                COUNT(DISTINCT poh.po_header_id)                               AS po_count,
                COUNT(DISTINCT msi.inventory_item_id)                          AS item_count,
                COUNT(DISTINCT NVL(mcb.segment1,'—'))                             AS category_count,
                TO_CHAR(MAX(poh.creation_date), 'YYYY-MM-DD')                  AS last_po_date,
                ROUND(SUM(
                    CASE WHEN NVL(mcb.segment1,'') IN
                        ('RAW MATERIAL','PACKAGING MATERIAL','FINISHED GOODS')
                    THEN pol.quantity * pol.unit_price * ({self._RATE_CASE})
                    ELSE 0 END
                ), 0)                                                           AS direct_idr,
                ROUND(SUM(
                    CASE WHEN NVL(mcb.segment1,'') NOT IN
                        ('RAW MATERIAL','PACKAGING MATERIAL','FINISHED GOODS')
                    THEN pol.quantity * pol.unit_price * ({self._RATE_CASE})
                    ELSE 0 END
                ), 0)                                                           AS indirect_idr,
                ROUND(SUM(pol.quantity * pol.unit_price
                          * ({self._RATE_CASE})), 0)                           AS total_idr
            FROM {self._PH_FROM}
            WHERE {self._PH_WHERE}
            GROUP BY aps.vendor_id, aps.vendor_name
            ORDER BY total_idr DESC
        """
        params = self._ph_params(filters)
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("active_suppliers_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Monthly Spend ─────────────────────────────────────────────────────────

    async def get_monthly_spend(self, filters: dict) -> dict:
        """
        Monthly PO spend from Oracle EBS grouped by year + month + material_type.
        Frontend pivots into bar chart (stacked Direct/Indirect) and year comparison line chart.
        """
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM poh.creation_date)                   AS yr,
                EXTRACT(MONTH FROM poh.creation_date)                   AS mo,
                TO_CHAR(TRUNC(poh.creation_date, 'MM'), 'Mon YYYY')     AS ym_label,
                ({self._MAT_TYPE})                                       AS material_type,
                COUNT(DISTINCT poh.po_header_id)                        AS po_count,
                ROUND(SUM(pol.quantity * pol.unit_price), 2)            AS spend_orig,
                ROUND(SUM(pol.quantity * pol.unit_price
                          * ({self._RATE_CASE})), 0)                    AS spend_idr
            FROM {self._PH_FROM}
            WHERE {self._PH_WHERE}
            GROUP BY
                EXTRACT(YEAR  FROM poh.creation_date),
                EXTRACT(MONTH FROM poh.creation_date),
                TO_CHAR(TRUNC(poh.creation_date, 'MM'), 'Mon YYYY'),
                {self._MAT_TYPE}
            ORDER BY yr, mo, material_type
        """
        params = self._ph_params(filters)
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("monthly_spend_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Open PR (Purchase Requisition Approval Status) ───────────────────────

    _PR_RATE_CASE = """
        CASE WHEN prl.currency_code = 'IDR' THEN 1
        ELSE COALESCE((
            SELECT gdr.conversion_rate FROM gl_daily_rates gdr
            WHERE  gdr.from_currency   = prl.currency_code
              AND  gdr.to_currency     = 'IDR'
              AND  gdr.conversion_type = NVL(:p_ert, 'Corporate')
              AND  gdr.conversion_date = (
                  SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                  WHERE  gdr2.from_currency   = prl.currency_code
                    AND  gdr2.to_currency     = 'IDR'
                    AND  gdr2.conversion_type = NVL(:p_ert, 'Corporate')
                    AND  gdr2.conversion_date <= TRUNC(prh.creation_date)
              )
        ), 1) END
    """

    async def get_open_pr(self, filters: dict) -> dict:
        """
        PR Approval Status report from Oracle EBS.
        Joins PO_REQUISITION_HEADERS_ALL + PO_REQUISITION_LINES_ALL.
        Returns per-line detail with aging, status, and IDR conversion.
        """
        mat_type = filters.get("material_type") or None
        pr_status = filters.get("pr_status") or None
        pr_number = filters.get("pr_number") or None
        item_code = filters.get("item_code") or None
        item_desc = filters.get("item_desc") or None
        requestor = filters.get("requestor") or None
        currency  = filters.get("currency_code") or None
        date_from = filters.get("date_from") or None
        date_to   = filters.get("date_to") or None
        ert       = filters.get("exchange_rate_type") or "Corporate"

        sql = f"""
            SELECT
                prh.segment1                                                AS pr_number,
                prl.line_num                                                AS line_num,
                NVL(msi.segment1, '—')                                     AS item_code,
                prl.item_description                                        AS item_description,
                NVL(mcb.segment1, '—')                                      AS category_code,
                NVL(mcb.description, prl.item_description)                  AS category_name,
                CASE
                    WHEN UPPER(NVL(mcb.segment1,'')) IN (
                        'RAW MATERIAL','PACKAGING MATERIAL','FINISHED GOODS',
                        'API','EXCIPIENT','PRIMARY PACKAGING','SECONDARY PACKAGING'
                    ) THEN 'Direct Material'
                    ELSE 'Indirect Material'
                END                                                         AS material_type,
                fu.user_name                                                AS requestor,
                NVL(prl.unit_meas_lookup_code, '—')                        AS uom,
                ROUND(prl.quantity, 4)                                      AS quantity,
                NVL(prl.currency_code, 'IDR')                              AS currency_code,
                ROUND(NVL(prl.unit_price, 0), 4)                           AS unit_price_orig,
                ROUND(NVL(prl.unit_price, 0) * ({self._PR_RATE_CASE}), 4)  AS unit_price_idr,
                ROUND(NVL(prl.quantity, 0) * NVL(prl.unit_price, 0), 2)    AS total_value_orig,
                ROUND(NVL(prl.quantity, 0) * NVL(prl.unit_price, 0)
                      * ({self._PR_RATE_CASE}), 2)                         AS total_value_idr,
                prh.authorization_status                                    AS pr_status,
                TO_CHAR(prh.creation_date, 'YYYY-MM-DD')                   AS creation_date,
                TRUNC(SYSDATE) - TRUNC(prh.creation_date)                  AS aging_days,
                NVL(aps.vendor_name, NVL(prl.suggested_vendor_name, '—'))  AS supplier_name
            FROM po_requisition_headers_all prh
            JOIN po_requisition_lines_all prl
                ON prl.requisition_header_id = prh.requisition_header_id
            LEFT JOIN mtl_system_items_b msi
                ON  msi.inventory_item_id = prl.item_id
                AND msi.organization_id   = prl.destination_organization_id
            LEFT JOIN mtl_categories_b mcb
                ON  mcb.category_id = prl.category_id
            LEFT JOIN fnd_user fu
                ON  fu.user_id = prh.created_by
            LEFT JOIN ap_suppliers aps
                ON  aps.vendor_id = prl.vendor_id
            WHERE NVL(prl.cancel_flag, 'N') = 'N'
              AND prh.authorization_status NOT IN ('CANCELLED')
              AND (:p_pr_status IS NULL OR prh.authorization_status = :p_pr_status)
              AND (:p_pr_number IS NULL OR UPPER(prh.segment1)
                   LIKE UPPER('%' || :p_pr_number || '%'))
              AND (:p_item_code IS NULL OR UPPER(NVL(msi.segment1,''))
                   LIKE UPPER('%' || :p_item_code || '%'))
              AND (:p_item_desc IS NULL OR UPPER(prl.item_description)
                   LIKE UPPER('%' || :p_item_desc || '%'))
              AND (:p_requestor IS NULL OR UPPER(fu.user_name)
                   LIKE UPPER('%' || :p_requestor || '%'))
              AND (:p_currency IS NULL OR prl.currency_code = :p_currency)
              AND (:p_date_from IS NULL OR prh.creation_date
                   >= TO_DATE(:p_date_from, 'YYYY-MM-DD'))
              AND (:p_date_to IS NULL OR prh.creation_date
                   < TO_DATE(:p_date_to, 'YYYY-MM-DD') + 1)
              AND (
                  :p_mat_type IS NULL
                  OR (:p_mat_type = 'Direct Material'
                      AND UPPER(NVL(mcb.segment1,'')) IN (
                          'RAW MATERIAL','PACKAGING MATERIAL','FINISHED GOODS',
                          'API','EXCIPIENT','PRIMARY PACKAGING','SECONDARY PACKAGING'
                      ))
                  OR (:p_mat_type = 'Indirect Material'
                      AND (mcb.segment1 IS NULL
                           OR UPPER(mcb.segment1) NOT IN (
                               'RAW MATERIAL','PACKAGING MATERIAL','FINISHED GOODS',
                               'API','EXCIPIENT','PRIMARY PACKAGING','SECONDARY PACKAGING'
                           )))
              )
            ORDER BY prh.creation_date DESC, prh.segment1, prl.line_num
        """
        params = {
            "p_ert":       ert,
            "p_pr_status": pr_status,
            "p_pr_number": pr_number,
            "p_item_code": item_code,
            "p_item_desc": item_desc,
            "p_requestor": requestor,
            "p_currency":  currency,
            "p_date_from": date_from,
            "p_date_to":   date_to,
            "p_mat_type":  mat_type,
        }
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            # KPIs computed server-side
            total_pr_headers = len({r["pr_number"] for r in rows})
            overdue = sum(1 for r in rows if (r.get("aging_days") or 0) > 7)
            aging_vals = [r["aging_days"] for r in rows if r.get("aging_days") is not None]
            avg_aging = round(sum(aging_vals) / len(aging_vals), 1) if aging_vals else 0
            return {
                "success": True,
                "count": len(rows),
                "data": rows,
                "kpi": {
                    "total_pr_headers": total_pr_headers,
                    "total_lines": len(rows),
                    "overdue_lines": overdue,
                    "avg_aging": avg_aging,
                },
            }
        except Exception as e:
            logger.error("open_pr_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "kpi": {}}

    # ── Price Analysis ────────────────────────────────────────────────────────

    async def get_price_analysis(self, filters: dict) -> dict:
        """
        Price trend per supplier per year for a specific item.
        Returns rows: item_code, item_desc, uom, supplier_name, currency, trx_year,
                      po_count, total_qty, avg_price_orig, avg_price_idr
        Frontend pivots this into chart data.
        """
        year_from = int(filters.get("year_from") or 2022)
        year_to   = int(filters.get("year_to")   or 2025)
        years     = list(range(year_from, year_to + 1))

        sql = f"""
            SELECT
                NVL(msi.organization_id, poll.ship_to_organization_id)       AS organization_id,
                NVL(hou.name, TO_CHAR(poll.ship_to_organization_id))         AS organization_name,
                NVL(msi.segment1, TO_CHAR(pol.item_id))                      AS item_code,
                NVL(msi.description, pol.item_description)                   AS item_desc,
                NVL(msi.primary_uom_code, pol.unit_meas_lookup_code)         AS uom,
                aps.vendor_name                                              AS supplier_name,
                COALESCE(mfr.manufacturer_name, 'UNKNOWN')                  AS manufacturer_name,
                COALESCE(mfr.country_of_origin, 'UNKNOWN')                  AS country_of_origin,
                poh.currency_code,
                EXTRACT(YEAR FROM poh.creation_date)                        AS trx_year,
                COUNT(DISTINCT poh.po_header_id)                            AS po_count,
                ROUND(SUM(pol.quantity), 2)                                 AS total_qty,
                ROUND(AVG(pol.unit_price), 4)                               AS avg_price_orig,
                ROUND(AVG(pol.unit_price * ({self._RATE_CASE})), 4)         AS avg_price_idr
            FROM {self._PH_FROM}
            WHERE {self._PH_WHERE}
            GROUP BY
                NVL(msi.organization_id, poll.ship_to_organization_id),
                NVL(hou.name, TO_CHAR(poll.ship_to_organization_id)),
                NVL(msi.segment1, TO_CHAR(pol.item_id)),
                NVL(msi.description, pol.item_description),
                NVL(msi.primary_uom_code, pol.unit_meas_lookup_code),
                aps.vendor_name, mfr.manufacturer_name, mfr.country_of_origin,
                poh.currency_code,
                EXTRACT(YEAR FROM poh.creation_date)
            ORDER BY aps.vendor_name, EXTRACT(YEAR FROM poh.creation_date)
            FETCH FIRST 10 ROWS ONLY
        """
        params = self._ph_params(filters)
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("price_analysis_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}
