"""
Purchasing Service
─────────────────────────────────────────
Oracle EBS queries + Manufacturer Master CRUD (stored in Oracle).
"""
import asyncio
from datetime import date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
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

    def _query_eis(self, sql: str, params: dict = None) -> list[dict]:
        """Same shape as _query() but against the eis_dashboard Postgres
        warehouse (read-only role) instead of live Oracle — used by the
        methods below that were migrated off Oracle to eliminate the
        chatbot/dashboard drift risk (see eis_etl_tasks.py's etl_po_lines/
        etl_open_pr, which populate the tables these read from)."""
        conn = psycopg2.connect(settings.eis_database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params or {})
                return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

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

    async def get_items(self, search: str = "") -> dict:
        """Search items in MTL_SYSTEM_ITEMS_B across ALL orgs (not scoped to
        one organization_id). Used to be org-scoped — real bug: the same
        inventory_item_id an item shares across orgs in Oracle's multi-org
        item master isn't enabled in EVERY org, so a search limited to one
        org came back empty for an item that only exists in others, and the
        Manufacturer Master form let the user type the code anyway, saving
        item_id=0 (never matches anything real) instead of failing loudly.
        Deduplicated to one row per inventory_item_id since the same item
        can otherwise appear once per org it's enabled in."""
        sql = """
            SELECT item_id, item_code, MIN(item_description) AS item_description
            FROM (
                SELECT IB.INVENTORY_ITEM_ID AS item_id,
                       IB.SEGMENT1          AS item_code,
                       IT.DESCRIPTION       AS item_description
                FROM MTL_SYSTEM_ITEMS_B IB, MTL_SYSTEM_ITEMS_TL IT
                WHERE IB.ORGANIZATION_ID = IT.ORGANIZATION_ID
                  AND IB.INVENTORY_ITEM_ID = IT.INVENTORY_ITEM_ID
                  AND (:search IS NULL OR UPPER(IB.SEGMENT1) LIKE UPPER(:search_like))
            )
            GROUP BY item_id, item_code
            ORDER BY item_code
            FETCH FIRST 50 ROWS ONLY
        """
        search_like = f"%{search}%" if search else None
        try:
            rows = await asyncio.to_thread(
                self._query, sql,
                {"search": search or None, "search_like": search_like}
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
        # One manufacturer record per item (item_code is org-agnostic here
        # now — see the join fix in _PH_FROM) — without this check the form
        # let the same item be added repeatedly with no warning, which is
        # exactly how it went "dobel" (duplicated).
        dupe_check_sql = "SELECT COUNT(*) AS c FROM XXCKDO_MANUFACTURER_MASTER WHERE UPPER(ITEM_CODE) = UPPER(:item_code)"
        try:
            existing = await asyncio.to_thread(self._query, dupe_check_sql, {"item_code": data["item_code"]})
            if existing and existing[0]["c"] > 0:
                return {"success": False, "error": f"\"{data['item_code']}\" already exists in Manufacturer Master — edit the existing record instead of adding a new one."}
        except Exception as e:
            logger.error("manufacturer_dupe_check_error", error=str(e))

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
            return {"success": True, "message": "Data saved successfully"}
        except Exception as e:
            logger.error("manufacturer_create_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def update_manufacturer(self, manufacturer_id: int, data: dict, username: str) -> dict:
        dupe_check_sql = (
            "SELECT COUNT(*) AS c FROM XXCKDO_MANUFACTURER_MASTER "
            "WHERE UPPER(ITEM_CODE) = UPPER(:item_code) AND MANUFACTURER_ID != :id"
        )
        try:
            existing = await asyncio.to_thread(self._query, dupe_check_sql, {"item_code": data["item_code"], "id": manufacturer_id})
            if existing and existing[0]["c"] > 0:
                return {"success": False, "error": f"\"{data['item_code']}\" already exists in another Manufacturer Master record."}
        except Exception as e:
            logger.error("manufacturer_dupe_check_error", error=str(e))

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
                return {"success": False, "error": "Record not found"}
            return {"success": True, "message": "Data updated successfully"}
        except Exception as e:
            logger.error("manufacturer_update_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def delete_manufacturer(self, manufacturer_id: int) -> dict:
        sql = "DELETE FROM XXCKDO_MANUFACTURER_MASTER WHERE MANUFACTURER_ID = :id"
        try:
            rows = await asyncio.to_thread(self._execute, sql, {"id": manufacturer_id})
            if rows == 0:
                return {"success": False, "error": "Record not found"}
            return {"success": True, "message": "Data deleted successfully"}
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
        -- Manufacturer/country-of-origin is a property of the ITEM, not of
        -- which org a given PO happened to be raised in — matching on
        -- organization_id too (as this used to) meant a Manufacturer
        -- Master row entered under one org silently failed to link to
        -- Purchase History rows for the same item under a different org,
        -- which is exactly why newly-added data "didn't show up." Joins by
        -- item_id alone now. Deduplicated to one row per item_id (most
        -- recently updated wins) so a leftover pre-existing org-scoped
        -- duplicate for the same item can't fan out a PO line into
        -- multiple result rows.
        LEFT JOIN (
            SELECT item_id, manufacturer_name, country_of_origin
            FROM (
                SELECT item_id, manufacturer_name, country_of_origin,
                       ROW_NUMBER() OVER (
                           PARTITION BY item_id
                           ORDER BY NVL(last_update_date, creation_date) DESC
                       ) AS rn
                FROM xxckdo_manufacturer_master
            )
            WHERE rn = 1
        ) mfr ON mfr.item_id = msi.inventory_item_id
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

    # ── Purchase History / Price Analysis (Postgres — migrated 2026-09-03) ────
    # eis.fact_po_line (etl_po_lines) replaces live Oracle for these 4
    # reports — see the architecture note on eliminating dashboard/chatbot
    # ETL drift. Filters below are the Postgres translation of _ph_where/
    # _ph_params above (ILIKE for substring search, ~* for the buyer
    # regex, = ANY(array) for multi-select category) — amount_idr/
    # unit_price_idr are already converted at ETL time, so no rate-lookup
    # subquery is needed here anymore.

    def _pg_ph_where(self) -> str:
        return """
            (%(p_org_id)s      IS NULL OR organization_id = %(p_org_id)s)
            AND (%(p_date_from)s   IS NULL OR creation_date >= %(p_date_from)s)
            AND (%(p_date_to)s     IS NULL OR creation_date <= %(p_date_to)s)
            AND (%(p_item_code)s   IS NULL OR item_code = %(p_item_code)s)
            AND (%(p_item_desc)s   IS NULL OR item_description ILIKE %(p_item_desc_like)s)
            AND (%(p_vendor_name)s IS NULL OR supplier_name ILIKE %(p_vendor_name_like)s)
            AND (%(p_manufacturer)s IS NULL OR manufacturer_name ILIKE %(p_manufacturer_like)s)
            AND (%(p_country)s     IS NULL OR country_of_origin = %(p_country)s)
            AND (%(p_category)s::text[] IS NULL OR category = ANY(%(p_category)s))
            AND (%(p_currency)s    IS NULL OR currency_code = %(p_currency)s)
            AND (%(p_mat_type)s    IS NULL OR material_type = %(p_mat_type)s)
            AND (%(p_po_number)s   IS NULL OR po_number ILIKE %(p_po_number_like)s)
            AND (%(p_buyer)s       IS NULL OR buyer_name ~* %(p_buyer)s)
        """

    def _pg_ph_params(self, f: dict) -> dict:
        date_from = f.get("date_from") or None
        date_to   = f.get("date_to") or None
        if not date_from and f.get("year_from"):
            date_from = f"{int(f['year_from'])}-01-01"
        if not date_to and f.get("year_to"):
            date_to = f"{int(f['year_to'])}-12-31"

        def _like(v):
            return f"%{v}%" if v else None

        category_list = [c.strip() for c in (f.get("category") or "").split(",") if c.strip()] or None
        item_desc, vendor_name, manufacturer, po_number = (
            f.get("item_desc") or None, f.get("vendor_name") or None,
            f.get("manufacturer") or None, f.get("po_number") or None,
        )
        return {
            "p_org_id":            f.get("org_id") or None,
            "p_date_from":         date_from,
            "p_date_to":           date_to,
            "p_item_code":         f.get("item_code") or None,
            "p_item_desc":         item_desc,
            "p_item_desc_like":    _like(item_desc),
            "p_vendor_name":       vendor_name,
            "p_vendor_name_like":  _like(vendor_name),
            "p_manufacturer":      manufacturer,
            "p_manufacturer_like": _like(manufacturer),
            "p_country":           f.get("country_of_origin") or None,
            "p_category":          category_list,
            "p_currency":          f.get("currency_code") or None,
            "p_mat_type":          f.get("material_type") or None,
            "p_po_number":         po_number,
            "p_po_number_like":    _like(po_number),
            "p_buyer":             f.get("buyer") or None,
        }

    async def get_purchase_history_detail(self, filters: dict) -> dict:
        """Output 1: Individual PO line detail (like Oracle PO report).
        Reads eis.fact_po_line (Postgres) — see _pg_ph_where's docstring."""
        params = self._pg_ph_params(filters)
        sql = f"""
            SELECT po_number, line_num, item_code, item_description, category, item_type,
                   material_type, supplier_name, currency_code, uom, quantity, unit_price,
                   amount_orig, amount_idr, received_qty,
                   TO_CHAR(creation_date, 'YYYY-MM-DD') AS creation_date,
                   closure_status, organization_name, country_of_origin
            FROM eis.fact_po_line
            WHERE {self._pg_ph_where()}
            ORDER BY creation_date DESC, po_number, line_num
        """
        try:
            rows = await asyncio.to_thread(self._query_eis, sql, params)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("ph_detail_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_purchase_history_by_item(self, filters: dict) -> dict:
        """Output 2: Per-item pivot by year — Value IDR + Qty per year."""
        year_from, year_to = self._ph_year_range(filters)
        years  = list(range(year_from, year_to + 1))
        params = self._pg_ph_params(filters)
        pivot  = ",\n            ".join(
            f"SUM(CASE WHEN EXTRACT(YEAR FROM creation_date)={y} THEN amount_idr ELSE 0 END) AS value_idr_{y},"
            f"\n            SUM(CASE WHEN EXTRACT(YEAR FROM creation_date)={y} THEN quantity ELSE 0 END) AS qty_{y}"
            for y in years
        )
        sql = f"""
            SELECT
                organization_id, organization_name,
                item_code, item_description, category, material_type, country_of_origin, currency_code, uom,
                {pivot},
                SUM(amount_idr) AS total_value_idr,
                SUM(quantity)   AS total_qty
            FROM eis.fact_po_line
            WHERE {self._pg_ph_where()}
            GROUP BY organization_id, organization_name, item_code, item_description, category, material_type, country_of_origin, currency_code, uom
            ORDER BY item_code
        """
        try:
            rows = await asyncio.to_thread(self._query_eis, sql, params)
            return {"success": True, "count": len(rows), "data": rows, "years": years}
        except Exception as e:
            logger.error("ph_by_item_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "years": years}

    async def get_purchase_history_by_supplier(self, filters: dict) -> dict:
        """Output 3: Per supplier pivot by year."""
        year_from, year_to = self._ph_year_range(filters)
        years  = list(range(year_from, year_to + 1))
        params = self._pg_ph_params(filters)
        pivot  = ",\n            ".join(
            f"SUM(CASE WHEN trx_year={y} THEN line_amount_orig ELSE 0 END) AS value_orig_{y},"
            f"\n            SUM(CASE WHEN trx_year={y} THEN line_amount_idr  ELSE 0 END) AS value_idr_{y},"
            f"\n            SUM(CASE WHEN trx_year={y} THEN line_qty          ELSE 0 END) AS qty_{y}"
            for y in years
        )
        sql = f"""
            WITH base_data AS (
                SELECT
                    supplier_name, currency_code,
                    EXTRACT(YEAR FROM creation_date)                          AS trx_year,
                    amount_orig                                               AS line_amount_orig,
                    amount_idr                                                AS line_amount_idr,
                    quantity                                                  AS line_qty,
                    COUNT(DISTINCT item_code) OVER (PARTITION BY supplier_name) AS item_count,
                    COUNT(DISTINCT po_number) OVER (PARTITION BY supplier_name) AS po_count
                FROM eis.fact_po_line
                WHERE {self._pg_ph_where()}
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
            rows = await asyncio.to_thread(self._query_eis, sql, params)
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
        PR Approval Status report — reads eis.fact_open_pr (Postgres),
        populated every 15 min by etl_open_pr (see its docstring in
        eis_etl_tasks.py for why this one job runs far more often than
        every other ETL job: "open" status is inherently live). All the
        structural exclusions (cancelled/split/dummy-data rows) are
        already applied at ETL time — only the user-adjustable filters
        below run here. Surfaces "data_as_of" (the ETL's last run time)
        so staleness between runs is visible rather than silent.
        """
        mat_type  = filters.get("material_type") or None
        pr_status = filters.get("pr_status") or None
        pr_number = filters.get("pr_number") or None
        item_code = filters.get("item_code") or None
        item_desc = filters.get("item_desc") or None
        currency  = filters.get("currency_code") or None
        date_from = filters.get("date_from") or None
        date_to   = filters.get("date_to") or None

        requestor_list = [r.strip() for r in (filters.get("requestor") or "").split(",") if r.strip()] or None

        sql = """
            SELECT pr_number, po_number, line_num, item_code, item_description,
                   category_code, category_name, material_type, requestor, uom, quantity,
                   currency_code, unit_price_orig, unit_price_idr, total_value_orig, total_value_idr,
                   pr_status, creation_date, due_date, aging_basis_date, supplier_name,
                   payment_terms, last_purchase_price, last_purchase_currency
            FROM eis.fact_open_pr
            WHERE (%(p_pr_status)s IS NULL OR pr_status = %(p_pr_status)s)
              AND (%(p_pr_number)s IS NULL OR pr_number ILIKE %(p_pr_number_like)s)
              AND (%(p_item_code)s IS NULL OR item_code ILIKE %(p_item_code_like)s)
              AND (%(p_item_desc)s IS NULL OR item_description ILIKE %(p_item_desc_like)s)
              AND (%(p_requestor)s::text[] IS NULL OR requestor = ANY(%(p_requestor)s))
              AND (%(p_currency)s IS NULL OR currency_code = %(p_currency)s)
              AND (%(p_date_from)s IS NULL OR creation_date >= %(p_date_from)s)
              AND (%(p_date_to)s   IS NULL OR creation_date <= %(p_date_to)s)
              AND (%(p_mat_type)s  IS NULL OR material_type = %(p_mat_type)s)
            ORDER BY due_date ASC NULLS LAST, pr_number, line_num
        """
        params = {
            "p_pr_status": pr_status,
            "p_pr_number": pr_number, "p_pr_number_like": f"%{pr_number}%" if pr_number else None,
            "p_item_code": item_code, "p_item_code_like": f"%{item_code}%" if item_code else None,
            "p_item_desc": item_desc, "p_item_desc_like": f"%{item_desc}%" if item_desc else None,
            "p_requestor": requestor_list,
            "p_currency": currency,
            "p_date_from": date_from,
            "p_date_to": date_to,
            "p_mat_type": mat_type,
        }
        try:
            rows = await asyncio.to_thread(self._query_eis, sql, params)
            holidays = await asyncio.to_thread(self._fetch_holidays)
            data_as_of = await asyncio.to_thread(self._fetch_open_pr_data_as_of)

            today = date.today()
            for r in rows:
                basis_date = r.pop("aging_basis_date", None)
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
                "data_as_of": data_as_of,
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

    def _fetch_open_pr_data_as_of(self) -> str | None:
        """Last successful etl_open_pr run's finish time — see get_open_pr's
        docstring for why this needs to be visible to the user."""
        conn = psycopg2.connect(settings.eis_database_url)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT finished_at FROM eis.etl_job_log "
                "WHERE job_name = 'etl_open_pr' AND status = 'success' "
                "ORDER BY finished_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0].isoformat() if row and row[0] else None
        finally:
            conn.close()

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
        params    = self._pg_ph_params(filters)

        sql = f"""
            SELECT
                organization_id, organization_name, item_code,
                item_description AS item_desc, uom, supplier_name,
                COALESCE(manufacturer_name, 'UNKNOWN')  AS manufacturer_name,
                COALESCE(country_of_origin, 'UNKNOWN')  AS country_of_origin,
                currency_code,
                EXTRACT(YEAR FROM creation_date)        AS trx_year,
                COUNT(DISTINCT po_number)               AS po_count,
                ROUND(SUM(quantity)::numeric, 2)        AS total_qty,
                ROUND(MIN(unit_price)::numeric, 4)      AS min_price_orig,
                ROUND(MAX(unit_price)::numeric, 4)      AS max_price_orig,
                ROUND(MIN(unit_price_idr)::numeric, 4)  AS min_price_idr,
                ROUND(MAX(unit_price_idr)::numeric, 4)  AS max_price_idr,
                ROUND(AVG(unit_price)::numeric, 4)      AS avg_price_orig,
                ROUND(AVG(unit_price_idr)::numeric, 4)  AS avg_price_idr
            FROM eis.fact_po_line
            WHERE {self._pg_ph_where()}
            GROUP BY
                organization_id, organization_name, item_code, item_description, uom,
                supplier_name, manufacturer_name, country_of_origin, currency_code,
                EXTRACT(YEAR FROM creation_date)
            ORDER BY supplier_name, EXTRACT(YEAR FROM creation_date)
        """
        try:
            rows = await asyncio.to_thread(self._query_eis, sql, params)

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
