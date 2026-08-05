"""
Purchasing Service
─────────────────────────────────────────
Oracle EBS queries + Manufacturer Master CRUD (stored in Oracle).
"""
import asyncio
from datetime import date, datetime, timedelta
import psycopg2
from app.database import get_oracle_connection
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()


class PurchasingService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _fetch_holidays(self) -> set:
        """Company holiday calendar lives in this app's own Postgres DB (HR >
        Working Calendar), not Oracle — so Open PR aging (Oracle-sourced) is
        computed in Python after the query, not in Oracle SQL, to cross this
        DB boundary."""
        conn = psycopg2.connect(settings.database_url)
        try:
            cur = conn.cursor()
            cur.execute("SELECT holiday_date FROM working_calendar_holidays")
            return {row[0] for row in cur.fetchall()}
        finally:
            conn.close()

    @staticmethod
    def _working_days_between(start: date, end: date, holidays: set) -> int | None:
        """Working days elapsed from start to end, excluding weekends and
        company holidays. Returns None if either date is missing, 0 if
        start >= end (same day or a future-dated basis)."""
        if not start or not end:
            return None
        if start >= end:
            return 0
        days = 0
        d = start
        while d < end:
            d += timedelta(days=1)
            if d.weekday() < 5 and d not in holidays:
                days += 1
        return days

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
        """Inventory Organizations only (IO) — excludes Operating Units, Legal
        Entities, HR Orgs, etc. that HR_ALL_ORGANIZATION_UNITS also returns."""
        sql = """
            SELECT ood.organization_name AS name, ood.organization_id
            FROM org_organization_definitions ood
            ORDER BY ood.organization_name
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

    async def get_manufacturer_list(self, filters: dict = None) -> dict:
        filters = filters or {}
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
            WHERE (:p_org_id      IS NULL OR ORGANIZATION_ID = :p_org_id)
              AND (:p_item_code   IS NULL OR UPPER(ITEM_CODE)         LIKE UPPER('%'||:p_item_code||'%'))
              AND (:p_item_desc   IS NULL OR UPPER(ITEM_DESCRIPTION)  LIKE UPPER('%'||:p_item_desc||'%'))
              AND (:p_mfr_name    IS NULL OR UPPER(MANUFACTURER_NAME) LIKE UPPER('%'||:p_mfr_name||'%'))
              AND (:p_country     IS NULL OR UPPER(COUNTRY_OF_ORIGIN) LIKE UPPER('%'||:p_country||'%'))
            ORDER BY CREATION_DATE DESC
        """
        params = {
            "p_org_id":    filters.get("org_id") or None,
            "p_item_code": filters.get("item_code") or None,
            "p_item_desc": filters.get("item_desc") or None,
            "p_mfr_name":  filters.get("manufacturer_name") or None,
            "p_country":   filters.get("country_of_origin") or None,
        }
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
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

    async def update_manufacturer(self, manufacturer_id: int, data: dict, username: str) -> dict:
        sql = """
            UPDATE XXCKDO_MANUFACTURER_MASTER
               SET ITEM_ID           = :item_id,
                   ORGANIZATION_ID   = :organization_id,
                   ITEM_CODE         = :item_code,
                   ITEM_DESCRIPTION  = :item_description,
                   MANUFACTURER_NAME = :manufacturer_name,
                   COUNTRY_OF_ORIGIN = :country_of_origin,
                   LAST_UPDATED_BY   = :updated_by,
                   LAST_UPDATE_DATE  = SYSDATE
             WHERE MANUFACTURER_ID   = :id
        """
        try:
            rows = await asyncio.to_thread(self._execute, sql, {
                "item_id":          data["item_id"],
                "organization_id":  data["organization_id"],
                "item_code":        data["item_code"],
                "item_description": data.get("item_description", ""),
                "manufacturer_name": data["manufacturer_name"],
                "country_of_origin": data.get("country_of_origin", ""),
                "updated_by":       username,
                "id":               manufacturer_id,
            })
            if rows == 0:
                return {"success": False, "error": "Record tidak ditemukan"}
            return {"success": True, "message": "Data berhasil diperbarui"}
        except Exception as e:
            logger.error("manufacturer_update_error", error=str(e))
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
        """LOV: distinct material type tags from CKDO_MTRL_TYPE_DIRECT_INDIRECT lookup.

        fnd_lookup_values_vl returns one row per SECURITY_GROUP_ID for lookup
        types that aren't security-group-enabled (a well-known Oracle EBS
        quirk) — lookup_code differs between those duplicate rows, so
        selecting it alongside tag defeats DISTINCT and doubles every option.
        Only select tag, which is the only column actually used (both for
        display and as the filter value in _MAT_TYPE / p_mat_type).
        """
        sql = """
            SELECT DISTINCT lv.tag
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
            FROM mtl_item_categories_v miv
            JOIN mtl_categories_b      mcb ON mcb.category_id = miv.category_id
            WHERE miv.category_set_name = 'CKDO Inventory'
              AND mcb.segment1 IS NOT NULL
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
            SELECT miv2.inventory_item_id, miv2.organization_id,
                   MIN(mcb2.segment1) AS segment1
            FROM mtl_item_categories_v miv2
            JOIN mtl_categories_b      mcb2 ON mcb2.category_id = miv2.category_id
            WHERE miv2.category_set_name = 'CKDO Inventory'
            GROUP BY miv2.inventory_item_id, miv2.organization_id
        ) mcb ON mcb.inventory_item_id = msi.inventory_item_id
             AND mcb.organization_id   = msi.organization_id
        JOIN ap_suppliers          aps  ON aps.vendor_id         = poh.vendor_id
        LEFT JOIN per_all_people_f buyer_p
                                        ON buyer_p.person_id     = poh.agent_id
                                       AND SYSDATE BETWEEN buyer_p.effective_start_date
                                                        AND buyer_p.effective_end_date
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

    def _ph_where(self, category_clause: str = "1=1") -> str:
        """Shared WHERE clause for all Purchase History-family queries
        (detail/by-item/by-supplier/active-suppliers/monthly-spend).
        category_clause is injected dynamically (see _category_filter) since
        it's now a multi-select IN(...) instead of a single '=' comparison —
        an f-string constant can't hold a per-call bind list, so this became
        a method instead of the plain string constant it used to be."""
        return f"""
        poh.type_lookup_code IN ('STANDARD','BLANKET','CONTRACT')
        AND poh.authorization_status NOT IN ('CANCELLED','INCOMPLETE')
        AND NVL(pol.cancel_flag,'N') = 'N'
        AND (:p_org_id       IS NULL OR NVL(msi.organization_id, poll.ship_to_organization_id) = :p_org_id)
        -- Date range based on PO Date (poh.creation_date) — was a
        -- year_from/year_to whole-year filter; still accepts year_from/
        -- year_to too (converted to a date range in _ph_params) so
        -- Active Suppliers / Monthly Spend, which weren't asked to change
        -- their own filter UI, keep working unmodified.
        AND (:p_date_from IS NULL OR poh.creation_date >= TO_DATE(:p_date_from, 'YYYY-MM-DD'))
        AND (:p_date_to   IS NULL OR poh.creation_date <  TO_DATE(:p_date_to,   'YYYY-MM-DD') + 1)
        AND (:p_item_code    IS NULL OR NVL(msi.segment1, TO_CHAR(pol.item_id)) = :p_item_code)
        AND (:p_item_desc    IS NULL
             OR UPPER(pol.item_description) LIKE UPPER('%'||:p_item_desc||'%')
             OR UPPER(msi.description)      LIKE UPPER('%'||:p_item_desc||'%'))
        AND (:p_vendor_name  IS NULL OR UPPER(aps.vendor_name)           LIKE UPPER('%'||:p_vendor_name||'%'))
        AND (:p_manufacturer IS NULL OR UPPER(mfr.manufacturer_name)     LIKE UPPER('%'||:p_manufacturer||'%'))
        AND (:p_country      IS NULL OR mfr.country_of_origin            = :p_country)
        AND ({category_clause})
        AND (:p_currency     IS NULL OR poh.currency_code                = :p_currency)
        AND (:p_mat_type IS NULL OR lv_mt.tag = :p_mat_type)
        AND (:p_po_number    IS NULL OR UPPER(poh.segment1)               LIKE UPPER('%'||:p_po_number||'%'))
        AND (:p_buyer        IS NULL OR REGEXP_LIKE(UPPER(buyer_p.full_name), UPPER(:p_buyer)))
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
        # Purchase History's own filter form now sends date_from/date_to
        # directly (based on PO Date); Active Suppliers / Monthly Spend
        # still send year_from/year_to, converted here to the same
        # first-day/last-day-of-year date range so _ph_where's single
        # date-range comparison covers both without branching in SQL.
        date_from = f.get("date_from") or None
        date_to   = f.get("date_to") or None
        if not date_from and f.get("year_from"):
            date_from = f"{int(f['year_from'])}-01-01"
        if not date_to and f.get("year_to"):
            date_to = f"{int(f['year_to'])}-12-31"
        return {
            "p_org_id":       f.get("org_id")             or None,
            "p_ert":          f.get("exchange_rate_type") or "Corporate",
            "p_date_from":    date_from,
            "p_date_to":      date_to,
            "p_item_code":    f.get("item_code")           or None,
            "p_item_desc":    f.get("item_desc")           or None,
            "p_vendor_name":  f.get("vendor_name")         or None,
            "p_manufacturer": f.get("manufacturer")        or None,
            "p_country":      f.get("country_of_origin")   or None,
            "p_currency":     f.get("currency_code")       or None,
            "p_mat_type":     f.get("material_type")       or None,
            "p_po_number":    f.get("po_number")           or None,
            "p_buyer":        f.get("buyer")                or None,
        }

    def _ph_year_range(self, f: dict) -> tuple[int, int]:
        """Year span for the by-item/by-supplier pivot columns — derived
        from date_from/date_to when present (Purchase History's own filter,
        now a date range rather than year_from/year_to), else from
        year_from/year_to directly (Active Suppliers / Monthly Spend)."""
        date_from = f.get("date_from")
        date_to   = f.get("date_to")
        if date_from and date_to:
            return int(str(date_from)[:4]), int(str(date_to)[:4])
        return int(f.get("year_from") or 2020), int(f.get("year_to") or 2026)

    def _category_filter(self, f: dict) -> tuple[str, dict]:
        """Category is now a multi-select checkbox list on the Purchase
        History frontend (was single-select) — arrives here as a
        comma-joined string, matched exactly against each selected value."""
        category_list = [c.strip() for c in (f.get("category") or "").split(",") if c.strip()]
        if not category_list:
            return "1=1", {}
        binds = {}
        placeholders = []
        for i, val in enumerate(category_list):
            key = f"p_cat_{i}"
            placeholders.append(f":{key}")
            binds[key] = val
        return f"NVL(mcb.segment1,'-') IN ({','.join(placeholders)})", binds

    async def get_purchase_history_detail(self, filters: dict) -> dict:
        """Output 1: Individual PO line detail (like Oracle PO report)."""
        category_clause, category_binds = self._category_filter(filters)
        sql = f"""
            SELECT
                poh.segment1                                             AS po_number,
                pol.line_num                                             AS line_num,
                NVL(msi.segment1, TO_CHAR(pol.item_id))                  AS item_code,
                NVL(pol.item_description, msi.description)               AS item_description,
                NVL(mcb.segment1, '-')                                   AS category,
                NVL(msi.item_type, '—')                                  AS item_type,
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
            WHERE {self._ph_where(category_clause)}
            ORDER BY poh.creation_date DESC, poh.segment1, pol.line_num
        """
        try:
            params = {**self._ph_params(filters), **category_binds}
            rows = await asyncio.to_thread(self._query, sql, params)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("ph_detail_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_purchase_history_by_item(self, filters: dict) -> dict:
        """Output 2: Per-item pivot by year — Value IDR + Qty per year."""
        year_from, year_to = self._ph_year_range(filters)
        years     = list(range(year_from, year_to + 1))
        category_clause, category_binds = self._category_filter(filters)
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
                    NVL(pol.item_description, msi.description)               AS item_description,
                    NVL(mcb.segment1, '-')                                   AS category,
                    ({self._MAT_TYPE})                                       AS material_type,
                    COALESCE(mfr.country_of_origin,'UNKNOWN')                AS country_of_origin,
                    poh.currency_code,
                    NVL(msi.primary_uom_code, pol.unit_meas_lookup_code)     AS uom,
                    EXTRACT(YEAR FROM poh.creation_date)                     AS trx_year,
                    pol.quantity * pol.unit_price * ({self._RATE_CASE})       AS line_amount_idr,
                    pol.quantity                                              AS line_qty
                FROM {self._PH_FROM}
                WHERE {self._ph_where(category_clause)}
            )
            SELECT
                organization_id, organization_name,
                item_code, item_description, category, material_type, country_of_origin, currency_code, uom,
                {pivot},
                SUM(line_amount_idr) AS total_value_idr,
                SUM(line_qty)        AS total_qty
            FROM base_data
            GROUP BY organization_id, organization_name, item_code, item_description, category, material_type, country_of_origin, currency_code, uom
            ORDER BY item_code
        """
        try:
            params = {**self._ph_params(filters), **category_binds}
            rows = await asyncio.to_thread(self._query, sql, params)
            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("ph_by_item_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}

    async def get_purchase_history_by_supplier(self, filters: dict) -> dict:
        """Output 3: Per supplier pivot by year."""
        year_from, year_to = self._ph_year_range(filters)
        years     = list(range(year_from, year_to + 1))
        category_clause, category_binds = self._category_filter(filters)
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
                WHERE {self._ph_where(category_clause)}
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
            params = {**self._ph_params(filters), **category_binds}
            rows = await asyncio.to_thread(self._query, sql, params)
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
                COUNT(DISTINCT NVL(mcb.segment1,'-'))                             AS category_count,
                TO_CHAR(MAX(poh.creation_date), 'YYYY-MM-DD')                  AS last_po_date,
                ROUND(SUM(
                    CASE WHEN ({self._MAT_TYPE}) = 'Direct Material'
                    THEN pol.quantity * pol.unit_price * ({self._RATE_CASE})
                    ELSE 0 END
                ), 0)                                                           AS direct_idr,
                ROUND(SUM(
                    CASE WHEN ({self._MAT_TYPE}) = 'Indirect Material'
                    THEN pol.quantity * pol.unit_price * ({self._RATE_CASE})
                    ELSE 0 END
                ), 0)                                                           AS indirect_idr,
                ROUND(SUM(pol.quantity * pol.unit_price
                          * ({self._RATE_CASE})), 0)                           AS total_idr
            FROM {self._PH_FROM}
            WHERE {self._ph_where()}
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
            WHERE {self._ph_where()}
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

    async def get_requestors(self) -> dict:
        """LOV: distinct PR requestors, for the Open PR multi-select checkbox
        filter — same not-cancelled/not-superseded scoping as the main Open
        PR query, and excludes the two fully-scrubbed names (ELLVIN, AFNI)
        outright so they can't even be selected; SHERLIN stays since only
        her rows paired with supplier ELLVIN are excluded, not all of hers."""
        sql = """
            SELECT DISTINCT fu.user_name AS name
            FROM po_requisition_headers_all prh
            JOIN po_requisition_lines_all prl
                ON prl.requisition_header_id = prh.requisition_header_id
            LEFT JOIN fnd_user fu ON fu.user_id = prh.created_by
            WHERE NVL(prl.cancel_flag, 'N') = 'N'
              AND prh.authorization_status NOT IN ('CANCELLED')
              AND NVL(prl.modified_by_agent_flag, 'N') = 'N'
              AND fu.user_name IS NOT NULL
              AND UPPER(fu.user_name) NOT IN ('ELLVIN', 'AFNI')
            ORDER BY fu.user_name
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("requestors_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

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
        currency  = filters.get("currency_code") or None
        date_from = filters.get("date_from") or None
        date_to   = filters.get("date_to") or None
        ert       = filters.get("exchange_rate_type") or "Corporate"

        # Requestor is now a multi-select checkbox list on the frontend
        # (was free-text substring search) — arrives here as a
        # comma-joined string, matched exactly (not LIKE) against each
        # selected name.
        requestor_list = [r.strip() for r in (filters.get("requestor") or "").split(",") if r.strip()]
        requestor_binds: dict = {}
        if requestor_list:
            placeholders = []
            for i, val in enumerate(requestor_list):
                key = f"p_req_{i}"
                placeholders.append(f":{key}")
                requestor_binds[key] = val.upper()
            requestor_clause = f"UPPER(fu.user_name) IN ({','.join(placeholders)})"
        else:
            requestor_clause = "1=1"

        sql = f"""
            SELECT
                prh.segment1                                                AS pr_number,
                po_link.po_number                                          AS po_number,
                prl.line_num                                                AS line_num,
                NVL(msi.segment1, '—')                                     AS item_code,
                prl.item_description                                        AS item_description,
                NVL(mcb.segment1, '—')                                      AS category_code,
                NVL(mcb.description, prl.item_description)                  AS category_name,
                ({self._MAT_TYPE})                                          AS material_type,
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
                TO_CHAR(prl.need_by_date, 'YYYY-MM-DD')                    AS due_date,
                -- Aging basis: once a PO exists, age from when the PO was
                -- approved (how long it's been open at the PO stage);
                -- before that, fall back to when the PR itself was
                -- approved, or its creation date if never separately
                -- approved. Actual working-day count (excluding weekends
                -- + company holidays) is computed in Python below — Oracle
                -- doesn't have the holiday calendar, that lives in this
                -- app's own Postgres DB (HR > Working Calendar).
                TO_CHAR(NVL(po_appr.approved_date,
                            NVL(appr.approved_date, prh.creation_date)),
                        'YYYY-MM-DD')                                       AS aging_basis_date,
                NVL(aps.vendor_name,
                    NVL(lastpo.last_supplier_name,
                        NVL(prl.suggested_vendor_name, '-')))              AS supplier_name,
                NVL(trm.name, '-')                                         AS payment_terms,
                lastpo.last_price                                          AS last_purchase_price,
                lastpo.last_currency                                       AS last_purchase_currency
            FROM po_requisition_headers_all prh
            JOIN po_requisition_lines_all prl
                ON prl.requisition_header_id = prh.requisition_header_id
            LEFT JOIN mtl_system_items_b msi
                ON  msi.inventory_item_id = prl.item_id
                AND msi.organization_id   = prl.destination_organization_id
            LEFT JOIN mtl_categories_b mcb
                ON  mcb.category_id = prl.category_id
            LEFT JOIN fnd_lookup_values_vl lv_mt
                ON  lv_mt.lookup_code         = msi.item_type
                AND lv_mt.view_application_id = 700
                AND lv_mt.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
            LEFT JOIN fnd_user fu
                ON  fu.user_id = prh.created_by
            LEFT JOIN ap_suppliers aps
                ON  aps.vendor_id = prl.vendor_id
            LEFT JOIN ap_terms_tl trm
                ON  trm.term_id  = aps.terms_id
                AND trm.language = USERENV('LANG')
            LEFT JOIN (
                SELECT pah.object_id, MAX(pah.action_date) AS approved_date
                FROM po_action_history pah
                WHERE pah.action_code      = 'APPROVE'
                  AND pah.object_type_code = 'REQUISITION'
                GROUP BY pah.object_id
            ) appr ON appr.object_id = prh.requisition_header_id
            LEFT JOIN (
                -- Requisition line -> PO, via the real distribution linkage
                -- (not the fuzzy item-description match "lastpo" below uses).
                -- Picks the most recently created PO if a line was split
                -- across more than one.
                SELECT requisition_line_id, po_number, po_header_id
                FROM (
                    SELECT prd.requisition_line_id,
                           poh2.segment1 AS po_number,
                           poh2.po_header_id AS po_header_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY prd.requisition_line_id
                               ORDER BY poh2.creation_date DESC
                           ) AS rn
                    FROM po_req_distributions_all prd
                    JOIN po_distributions_all pd   ON pd.req_distribution_id = prd.distribution_id
                    JOIN po_headers_all        poh2 ON poh2.po_header_id     = pd.po_header_id
                    WHERE poh2.authorization_status NOT IN ('CANCELLED')
                )
                WHERE rn = 1
            ) po_link ON po_link.requisition_line_id = prl.requisition_line_id
            LEFT JOIN (
                -- PO header approval date — object_type_code = 'PO' is the
                -- standard EBS lookup for standard/blanket PO approvals in
                -- PO_ACTION_HISTORY (mirrors the 'REQUISITION' one above).
                -- Worst case if this code is off for this instance: aging
                -- silently falls back to the PR-approved/creation date for
                -- PO'd lines too (NULL join, not a wrong value) — flagged
                -- for verification against a real approved PO.
                SELECT pah.object_id, MAX(pah.action_date) AS approved_date
                FROM po_action_history pah
                WHERE pah.action_code      = 'APPROVE'
                  AND pah.object_type_code = 'PO'
                GROUP BY pah.object_id
            ) po_appr ON po_appr.object_id = po_link.po_header_id
            LEFT JOIN (
                SELECT item_desc_key, unit_price AS last_price,
                       currency_code AS last_currency, vendor_name AS last_supplier_name
                FROM (
                    SELECT UPPER(plx.item_description)                     AS item_desc_key,
                           plx.unit_price, phx.currency_code, apsx.vendor_name,
                           ROW_NUMBER() OVER (
                               PARTITION BY UPPER(plx.item_description)
                               ORDER BY phx.creation_date DESC
                           )                                               AS rn
                    FROM po_lines_all plx
                    JOIN po_headers_all phx  ON phx.po_header_id = plx.po_header_id
                    JOIN ap_suppliers   apsx ON apsx.vendor_id   = phx.vendor_id
                    WHERE phx.type_lookup_code      IN ('STANDARD','BLANKET','CONTRACT')
                      AND phx.authorization_status  NOT IN ('CANCELLED','INCOMPLETE')
                )
                WHERE rn = 1
            ) lastpo ON lastpo.item_desc_key = UPPER(prl.item_description)
            WHERE NVL(prl.cancel_flag, 'N') = 'N'
              AND prh.authorization_status NOT IN ('CANCELLED')
              -- Excludes requisition lines superseded by a Split PO/Split
              -- Requisition Line action. When a buyer splits a line during
              -- AutoCreate, Oracle sets MODIFIED_BY_AGENT_FLAG='Y' on the
              -- ORIGINAL line but leaves its full original QUANTITY intact
              -- (no reduction, no cancel_flag) — the new split-child lines
              -- carry the real remaining demand instead. Without this
              -- filter, the original line's full quantity kept showing as
              -- still-open (with no PO and full aging) even though it had
              -- already been fully replaced by its split children —
              -- verified directly against PO_REQUISITION_LINES_ALL for a
              -- real split PR (25100080): original line qty 8000,
              -- MODIFIED_BY_AGENT_FLAG='Y', vs. its 3 split children
              -- (qty 2892.1 + 2886 + 2221.9 = 8000 exactly) each with
              -- MODIFIED_BY_AGENT_FLAG NULL.
              AND NVL(prl.modified_by_agent_flag, 'N') = 'N'
              -- Known dummy/test data scrubbed from the report — not
              -- user-adjustable filters, always excluded:
              --   i.  Requestor SHERLIN + Supplier ELLVIN together
              --   ii. Requestor ELLVIN (any supplier)
              --   iii. Requestor AFNI (any supplier)
              AND NOT (
                  UPPER(fu.user_name) IN ('ELLVIN', 'AFNI')
                  OR (
                      UPPER(fu.user_name) = 'SHERLIN'
                      AND UPPER(NVL(aps.vendor_name,
                              NVL(lastpo.last_supplier_name,
                                  NVL(prl.suggested_vendor_name, '-')))) = 'ELLVIN'
                  )
              )
              AND (:p_pr_status IS NULL OR prh.authorization_status = :p_pr_status)
              AND (:p_pr_number IS NULL OR UPPER(prh.segment1)
                   LIKE UPPER('%' || :p_pr_number || '%'))
              AND (:p_item_code IS NULL OR UPPER(NVL(msi.segment1,''))
                   LIKE UPPER('%' || :p_item_code || '%'))
              AND (:p_item_desc IS NULL OR UPPER(prl.item_description)
                   LIKE UPPER('%' || :p_item_desc || '%'))
              AND ({requestor_clause})
              AND (:p_currency IS NULL OR prl.currency_code = :p_currency)
              AND (:p_date_from IS NULL OR prh.creation_date
                   >= TO_DATE(:p_date_from, 'YYYY-MM-DD'))
              AND (:p_date_to IS NULL OR prh.creation_date
                   < TO_DATE(:p_date_to, 'YYYY-MM-DD') + 1)
              AND (:p_mat_type IS NULL OR ({self._MAT_TYPE}) = :p_mat_type)
            ORDER BY prl.need_by_date ASC NULLS LAST, prh.segment1, prl.line_num
        """
        params = {
            "p_ert":       ert,
            "p_pr_status": pr_status,
            "p_pr_number": pr_number,
            "p_item_code": item_code,
            "p_item_desc": item_desc,
            "p_currency":  currency,
            "p_date_from": date_from,
            "p_date_to":   date_to,
            "p_mat_type":  mat_type,
            **requestor_binds,
        }
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            holidays = await asyncio.to_thread(self._fetch_holidays)

            today = date.today()
            for r in rows:
                basis_str = r.pop("aging_basis_date", None)
                basis_date = datetime.strptime(basis_str, "%Y-%m-%d").date() if basis_str else None
                r["aging_days"] = self._working_days_between(basis_date, today, holidays)

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
        category_clause, category_binds = self._category_filter(filters)

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
                ROUND(MIN(pol.unit_price), 4)                               AS min_price_orig,
                ROUND(MAX(pol.unit_price), 4)                               AS max_price_orig,
                ROUND(MIN(pol.unit_price * ({self._RATE_CASE})), 4)         AS min_price_idr,
                ROUND(MAX(pol.unit_price * ({self._RATE_CASE})), 4)         AS max_price_idr,
                ROUND(AVG(pol.unit_price), 4)                               AS avg_price_orig,
                ROUND(AVG(pol.unit_price * ({self._RATE_CASE})), 4)         AS avg_price_idr
            FROM {self._PH_FROM}
            WHERE {self._ph_where(category_clause)}
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
        """
        params = {**self._ph_params(filters), **category_binds}
        try:
            rows = await asyncio.to_thread(self._query, sql, params)

            # Cap to the top N item+supplier combos by total spend (IDR) so the
            # trend chart stays readable — keeps every year for each combo kept,
            # rather than truncating the raw row list mid-sequence.
            max_rows = int(filters.get("max_rows") or 10)
            if max_rows and len(rows) > 0:
                group_spend = {}
                for r in rows:
                    key = (r["item_code"], r["supplier_name"])
                    spend = (r.get("avg_price_idr") or 0) * (r.get("total_qty") or 0)
                    group_spend[key] = group_spend.get(key, 0) + spend
                top_keys = set(sorted(group_spend, key=lambda k: group_spend[k], reverse=True)[:max_rows])
                rows = [r for r in rows if (r["item_code"], r["supplier_name"]) in top_keys]

            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("price_analysis_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}
