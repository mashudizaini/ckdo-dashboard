"""
Accounting Service
─────────────────────────────────────────
Business logic for Accounting Dashboard.
"""
import asyncio
from datetime import date
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

    # Excel template column order — see sumber/ouput-inventory RMPM.xlsx.
    # Amount side is coarser than qty side (10 vs 14 cols); WIP Return nets
    # into WIP Issue amount, Manual addition nets into Purchase amount, and
    # the 3 sample sub-types net into a single Sample amount column.
    QTY_COLS = [
        ("q_purchase",          "Purchase"),
        ("q_return_vendor",     "Return to vendor"),
        ("q_sample_qc",         "QTY Sample /Deduct Sample Qty +Issue RM Sample QC"),
        ("q_sample_stability",  "Sample for Stability Test"),
        ("q_sample_marketing",  "Sample marketing"),
        ("q_manual_addition",   "Manual addition project algeria"),
        ("q_wip_issue",         "WIP Issue"),
        ("q_wip_return",        "WIP Return"),
        ("q_repacking",         "Repacking"),
        ("q_rusak",             "Issue RM Rusak"),
        ("q_investigation_adj", "stock Investigation adjustment"),
        ("q_trial_production",  "Trial production"),
        ("q_mediafill_wo",      "Media fill written off"),
        ("q_adj_written_off",   "QTY Adjustment Written off from Plant"),
    ]
    AMT_COLS = [
        ("a_purchase",          "Purchase"),
        ("a_return_supplier",   "Return to supplier"),
        ("a_sample",            "Sample"),
        ("a_wip_issue",         "WIP Issue"),
        ("a_repacking",         "Repacking"),
        ("a_rusak",             "Issue RM PM Rusak"),
        ("a_investigation_adj", "stock Investigation adjustment"),
        ("a_trial_production",  "Amount trial production"),
        ("a_mediafill",         "Adjustment mediafill"),
        ("a_written_off",       "Amount written off"),
    ]
    # Oracle mtl_transaction_types.transaction_type_name → qty column.
    # Confirmed against a live 12-month distinct-value pull from org 121
    # (Subinventory Transfer / Sales Order* / WIP Completion* / RMA Receipt /
    # Issue FG* / Issue Ruah* are FG/bulk-item or net-zero-at-org-level
    # transactions and are intentionally left unmapped — they don't appear
    # on RM/PM items once the item-type filter below is applied).
    TRX_TYPE_MAP = {
        "PO Receipt":                       "q_purchase",
        "Return to Vendor":                 "q_return_vendor",
        "Issue RM/PM Sample QC":            "q_sample_qc",
        "Deduct Sample Qty":                "q_sample_qc",
        "Issue RM/PM Additional Material":  "q_manual_addition",
        "WIP Issue":                        "q_wip_issue",
        "WIP Return":                       "q_wip_return",
        "Residual Mat Prod to RM/PM":       "q_repacking",
        "Issue RM/PM Rusak":                "q_rusak",
        "Stock Adjustment RM/PM +":         "q_investigation_adj",
        "Issue RM/PM Trial Production":     "q_trial_production",
        "Issue RM/PM Expired":              "q_adj_written_off",
    }
    # qty column → amount column it nets into
    QTY_TO_AMT = {
        "q_purchase": "a_purchase", "q_manual_addition": "a_purchase",
        "q_return_vendor": "a_return_supplier",
        "q_sample_qc": "a_sample", "q_sample_stability": "a_sample", "q_sample_marketing": "a_sample",
        "q_wip_issue": "a_wip_issue", "q_wip_return": "a_wip_issue",
        "q_repacking": "a_repacking",
        "q_rusak": "a_rusak",
        "q_investigation_adj": "a_investigation_adj",
        "q_trial_production": "a_trial_production",
        "q_mediafill_wo": "a_mediafill",
        "q_adj_written_off": "a_written_off",
    }

    async def get_inventory_rm_pm(self, period: str, include_begin: bool = True) -> dict:
        """
        Inventory RM PM monthly report matching sumber/ouput-inventory RMPM.xlsx.
        - Movements for the period from MTL_MATERIAL_TRANSACTIONS (org 121),
          restricted to true RM/PM items (excludes FG MAKE/RUAHAN/FG BUY/TOLL IN)
        - Price from CKDO_GET_ITEM_COST
        - Beginning balance: sum of 5-year lookback (skippable for speed)
        - 14 qty movement columns + 10 netted amount movement columns, see
          QTY_COLS/AMT_COLS/TRX_TYPE_MAP/QTY_TO_AMT above.
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
              AND (
                    UPPER(msib.segment1) LIKE '02A%' OR UPPER(msib.segment1) LIKE '02B%'
                 OR UPPER(msib.segment1) LIKE '02%'  OR UPPER(msib.segment1) LIKE '01P%'
                 OR UPPER(msib.segment1) LIKE '01S%' OR UPPER(msib.segment1) LIKE '01%'
                 OR msib.item_type = 'RM'
              )
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

        QTY_KEYS = [k for k, _ in self.QTY_COLS]
        AMT_KEYS = [k for k, _ in self.AMT_COLS]

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
                    **{c: 0.0 for c in QTY_KEYS},
                }
            qty = float(r["qty"] or 0)
            items[iid]["movements"].append({"trx_type": r["trx_type"], "qty": round(qty, 6)})
            cat = self.TRX_TYPE_MAP.get(r["trx_type"])
            if cat:
                items[iid][cat] = round(items[iid][cat] + qty, 6)

        result = []
        for iid, d in sorted(items.items(), key=lambda x: x[1]["item_code"]):
            begin_qty  = round(begin_map.get(iid, 0), 6)
            net_mvt    = sum(d[c] for c in QTY_KEYS)
            end_qty    = round(begin_qty + net_mvt, 6)
            price      = d["unit_price"]

            amounts = {a: 0.0 for a in AMT_KEYS}
            for qk, ak in self.QTY_TO_AMT.items():
                amounts[ak] = round(amounts[ak] + d[qk] * price, 2)

            row = {
                "item_code":      d["item_code"],
                "item_name":      d["item_name"],
                "uom":            d["uom"],
                "material_type":  d["material_type"],
                "unit_price":     price,
                "begin_qty":      begin_qty,
                "begin_amount":   round(begin_qty * price, 2),
                **{k: d[k] for k in QTY_KEYS},
                "end_qty":        end_qty,
                **amounts,
                "end_amount":     round(begin_qty * price + sum(amounts.values()), 2),
                "movements":      d["movements"],
            }
            result.append(row)

        return {
            "success":   True,
            "count":     len(result),
            "period":    period.upper(),
            "date_from": date_from,
            "date_to":   date_to,
            "data":      result,
        }

    # ── AP Outstanding ───────────────────────────────────────────────────────

    async def get_ap_outstanding(
        self,
        as_of_date: str = None,
        supplier_name: str = None,
        operating_unit: str = None,
        payment_status: str = None,
        limit: int = 500,
        usd_rate: float = None,
        eur_rate: float = None,
    ) -> dict:
        """
        AP Outstanding from Oracle EBS — AP_INVOICES_ALL + AP_PAYMENT_SCHEDULES_ALL.
        Mirrors the AP Outstanding report; excludes fully Paid invoices.
        as_of_date defaults to SYSDATE when not provided.

        usd_rate/eur_rate (typically Bank Indonesia's Kurs Tengah as of
        as_of_date) drive the "Total After Revaluation" summary figure —
        SUM over Not Paid invoices of original_amount_orig * the matching
        override rate for USD/EUR rows, falling back to the existing
        base_amount-derived original_amount_idr for every other currency
        (including IDR itself, and USD/EUR when no override was given).
        This only affects that one summary number — the per-row
        original_amount_idr/remaining_amount_idr columns are untouched.
        """
        limit = min(max(limit, 1), 2000)

        date_expr = "TO_DATE(:as_of_date, 'YYYY-MM-DD')" if as_of_date else "TRUNC(SYSDATE)"
        params: dict = {}
        if as_of_date:
            params["as_of_date"] = as_of_date

        extra_where = ""
        if supplier_name:
            extra_where += " AND UPPER(pv.vendor_name) LIKE UPPER(:supplier_name)"
            params["supplier_name"] = f"%{supplier_name}%"
        if operating_unit:
            extra_where += " AND UPPER(hou.name) LIKE UPPER(:operating_unit)"
            params["operating_unit"] = f"%{operating_unit}%"
        if payment_status and payment_status != "ALL":
            # Will be applied as HAVING-equivalent via subquery wrapping
            # We include it in the outer filter using CASE expression
            extra_where += (
                " AND CASE"
                "   WHEN NVL(sched_summary.total_remaining, 0) = 0 THEN 'Paid'"
                "   WHEN NVL(sched_summary.total_remaining, 0) < NVL(sched_summary.total_gross, 0) THEN 'Partially Paid'"
                "   ELSE 'Not Paid'"
                " END = :pay_status"
            )
            params["pay_status"] = payment_status

        sql = f"""
            SELECT *
            FROM (
                SELECT
                    hou.name                                                       AS operating_unit,
                    ai.org_id,
                    pv.vendor_name                                                 AS supplier_name,
                    SUBSTR(NVL(ai.description, '-'), 1, 100)                       AS description,
                    gcc.segment1||'.'||gcc.segment2||'.'||gcc.segment3||'.'||
                    gcc.segment4||'.'||gcc.segment5||'.'||gcc.segment6             AS coa,
                    gcc.segment4                                                   AS coa_number,
                    SUBSTR(NVL(ffvl.description, '-'), 1, 80)                      AS coa_descpt,
                    ai.invoice_type_lookup_code                                    AS transaction_type,
                    ai.invoice_num                                                 AS transaction_number,
                    ai.invoice_id,
                    TO_CHAR(ai.invoice_date, 'YYYY-MM-DD')                         AS invoice_date,
                    TO_CHAR(ai.gl_date,      'YYYY-MM-DD')                         AS gl_date,
                    ai.invoice_currency_code                                       AS currency,
                    CASE
                        WHEN NVL(sched_summary.total_remaining, 0) = 0
                             THEN 'Paid'
                        WHEN NVL(sched_summary.total_remaining, 0) <
                             NVL(sched_summary.total_gross, 0)
                             THEN 'Partially Paid'
                        ELSE 'Not Paid'
                    END                                                            AS payment_status,
                    CASE WHEN ai.invoice_currency_code <> 'IDR'
                         THEN ai.invoice_amount        END                         AS original_amount_orig,
                    CASE WHEN ai.invoice_currency_code <> 'IDR'
                         THEN sched_summary.total_remaining_orig END               AS remaining_amount_orig,
                    NVL(ai.base_amount, ai.invoice_amount)                         AS original_amount_idr,
                    sched_summary.total_remaining                                  AS remaining_amount_idr
                FROM apps.ap_invoices_all              ai
                   , apps.ap_suppliers                 pv
                   , apps.gl_code_combinations         gcc
                   , apps.fnd_flex_values_vl           ffvl
                   , apps.fnd_flex_value_sets          ffvs
                   , apps.hr_operating_units           hou
                   , ( SELECT aps.invoice_id
                            , SUM(aps.gross_amount)                                AS total_gross
                            , SUM(aps.amount_remaining)                            AS total_remaining_orig
                            , SUM( aps.amount_remaining *
                                   NVL(ai2.base_amount, ai2.invoice_amount) /
                                   DECODE(ai2.invoice_amount, 0, 1, ai2.invoice_amount) )
                                                                                   AS total_remaining
                         FROM apps.ap_payment_schedules_all aps
                            , apps.ap_invoices_all          ai2
                        WHERE aps.invoice_id            = ai2.invoice_id
                          AND aps.payment_status_flag  IN ('N', 'P')
                          AND ai2.gl_date              <= {date_expr}
                        GROUP BY aps.invoice_id
                     ) sched_summary
                WHERE ai.invoice_id                       = sched_summary.invoice_id
                  AND ai.vendor_id                        = pv.vendor_id
                  AND ai.accts_pay_code_combination_id    = gcc.code_combination_id
                  AND ai.org_id                           = hou.organization_id
                  AND ai.gl_date                         <= {date_expr}
                  AND ffvl.flex_value_set_id              = ffvs.flex_value_set_id
                  AND ffvl.flex_value                     = gcc.segment4
                  AND CASE
                          WHEN NVL(sched_summary.total_remaining, 0) = 0
                               THEN 'Paid'
                          WHEN NVL(sched_summary.total_remaining, 0) <
                               NVL(sched_summary.total_gross, 0)
                               THEN 'Partially Paid'
                          ELSE 'Not Paid'
                      END != 'Paid'
                  {extra_where}
                ORDER BY hou.name, pv.vendor_name, ai.invoice_date, ai.invoice_num
            )
            WHERE ROWNUM <= {limit}
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            not_paid     = [r for r in clean if r.get("payment_status") == "Not Paid"]
            partial_paid = [r for r in clean if r.get("payment_status") == "Partially Paid"]
            total_idr    = sum(r.get("remaining_amount_idr") or 0 for r in clean)

            reval_override = {}
            if usd_rate:
                reval_override["USD"] = usd_rate
            if eur_rate:
                reval_override["EUR"] = eur_rate

            def _revalued(r):
                ccy = r.get("currency")
                orig_fc = r.get("original_amount_orig")
                if ccy in reval_override and orig_fc is not None:
                    return orig_fc * reval_override[ccy]
                return r.get("original_amount_idr") or 0

            total_after_revaluation_idr = sum(_revalued(r) for r in not_paid)

            return {
                "success":       True,
                "count":         len(clean),
                "as_of_date":    as_of_date or "today",
                "usd_rate":      usd_rate,
                "eur_rate":      eur_rate,
                "summary": {
                    "not_paid_count":    len(not_paid),
                    "partial_paid_count": len(partial_paid),
                    "total_outstanding_idr": round(total_idr, 2),
                    "not_paid_idr":      round(sum(r.get("remaining_amount_idr") or 0 for r in not_paid), 2),
                    "partial_paid_idr":  round(sum(r.get("remaining_amount_idr") or 0 for r in partial_paid), 2),
                    "total_after_revaluation_idr": round(total_after_revaluation_idr, 2),
                },
                "data": clean,
            }
        except Exception as e:
            logger.error("ap_outstanding_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_ap_aging(self, supplier_name: str = None, base_date: str = None, limit: int = 500) -> dict:
        """
        AP Aging — open items grouped by supplier into 5 buckets (Current,
        1-30, 31-60, 61-90, >90 days overdue), IDR converted (same
        base_amount/invoice_amount ratio used by get_ap_outstanding) and
        summed. Mirrors get_ar_aging's shape/behavior on the AP side.

        base_date anchors what "today" means for both the days-overdue
        bucketing and which invoices are in scope (ai.gl_date <= base_date)
        — defaults to the actual current date but can be overridden by the
        user to reprice/re-bucket the report as of any past date.
        """
        limit = min(max(limit, 1), 2000)
        where_extra = ""
        params: dict = {}
        if supplier_name:
            where_extra += " AND UPPER(pv.vendor_name) LIKE UPPER(:supplier_name)"
            params["supplier_name"] = f"%{supplier_name}%"

        base_date = base_date or date.today().isoformat()
        params["base_date"] = base_date
        base_date_expr = "TRUNC(TO_DATE(:base_date, 'YYYY-MM-DD'))"

        sql = f"""
            SELECT
                supplier_name, operating_unit,
                ROUND(SUM(CASE WHEN days_overdue <= 0                THEN remaining_idr ELSE 0 END), 2) AS current_amt,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 1  AND 30   THEN remaining_idr ELSE 0 END), 2) AS d1_30,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 31 AND 60   THEN remaining_idr ELSE 0 END), 2) AS d31_60,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 61 AND 90   THEN remaining_idr ELSE 0 END), 2) AS d61_90,
                ROUND(SUM(CASE WHEN days_overdue > 90                THEN remaining_idr ELSE 0 END), 2) AS over_90,
                ROUND(SUM(remaining_idr), 2)                                                             AS total_idr,
                COUNT(*)                                                                                 AS item_count
            FROM (
                SELECT
                    pv.vendor_name                                   AS supplier_name,
                    hou.name                                         AS operating_unit,
                    ({base_date_expr} - aps.due_date)                AS days_overdue,
                    aps.amount_remaining *
                        ( NVL(ai.base_amount, ai.invoice_amount) /
                          DECODE(ai.invoice_amount, 0, 1, ai.invoice_amount) )
                                                                      AS remaining_idr
                FROM apps.ap_payment_schedules_all aps
                JOIN apps.ap_invoices_all           ai
                    ON  ai.invoice_id       = aps.invoice_id
                JOIN apps.ap_suppliers               pv
                    ON  pv.vendor_id        = ai.vendor_id
                JOIN apps.hr_operating_units         hou
                    ON  hou.organization_id = ai.org_id
                WHERE aps.payment_status_flag IN ('N', 'P')
                  AND ai.gl_date <= {base_date_expr}
                  {where_extra}
            )
            GROUP BY supplier_name, operating_unit
            ORDER BY total_idr DESC
            FETCH FIRST {limit} ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            totals = {
                "current_amt": round(sum(r.get("current_amt", 0) for r in clean), 2),
                "d1_30":       round(sum(r.get("d1_30", 0) for r in clean), 2),
                "d31_60":      round(sum(r.get("d31_60", 0) for r in clean), 2),
                "d61_90":      round(sum(r.get("d61_90", 0) for r in clean), 2),
                "over_90":     round(sum(r.get("over_90", 0) for r in clean), 2),
                "total_idr":   round(sum(r.get("total_idr", 0) for r in clean), 2),
                "item_count":  sum(r.get("item_count", 0) for r in clean),
            }
            return {"success": True, "count": len(clean), "base_date": base_date, "data": clean, "totals": totals}
        except Exception as e:
            logger.error("ap_aging_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── AR Outstanding ───────────────────────────────────────────────────────

    async def get_ar_outstanding(
        self,
        customer_name: str = None,
        invoice_number: str = None,
        date_from: str = None,
        date_to: str = None,
        status: str = "OP",
        limit: int = 500,
        usd_rate: float = None,
        as_of_date: str = None,
    ) -> dict:
        """
        AR Outstanding from Oracle EBS Invoice Receivable.
        Sources: AR_PAYMENT_SCHEDULES_ALL + RA_CUSTOMER_TRX_ALL + HZ_PARTIES.

        usd_rate, when provided, overrides the Oracle Corporate rate for
        USD-denominated rows only (USD is the only material FX exposure in
        this AR portfolio — see get_ar_outstanding investigation notes).
        Lets the user substitute Bank Indonesia's Kurs Tengah (or any other
        value) when the Corporate rate in EBS looks stale/off. Other
        currencies keep using the Oracle Corporate rate lookup.

        as_of_date, when provided, reconstructs each row's Status and
        Remaining Amount as they stood on that date instead of showing
        today's live values — found necessary after a real case (MENSA
        invoice 26110012) where a receipt applied after the user's chosen
        date had already closed the invoice by the time they looked, even
        though it was genuinely still open as of that date. Remaining is
        recomputed as amount_due_original minus every receivable
        application with apply_date <= as_of_date (AR_RECEIVABLE_
        APPLICATIONS_ALL, status='APP'); Status is derived from that
        reconstructed remaining (<=0 => CL, else OP). Only cash/credit-memo
        applications are replayed — manual adjustments/write-offs
        (AR_ADJUSTMENTS_ALL) are not, so a balance closed purely via
        write-off may still show as marginally open as of a past date.
        Invoices dated after as_of_date are excluded (they didn't exist
        yet), the days-overdue and Corporate-rate lookup are anchored to
        as_of_date too, and the `status` filter is evaluated against the
        reconstructed status rather than the live one. Without as_of_date,
        behavior is unchanged from before (today's live status/remaining).
        """
        limit = min(max(limit, 1), 2000)
        where_extra = ""
        params: dict = {}

        # Point-in-time reconstruction (see docstring). remaining_expr/
        # status_expr fall back to the plain live columns when no
        # as_of_date is given, so every downstream usage stays identical
        # to the pre-existing behavior in that case.
        if as_of_date:
            params["as_of_date"] = as_of_date
            today_expr = "TO_DATE(:as_of_date, 'YYYY-MM-DD')"
            applied_asof_expr = """
                NVL((
                    SELECT SUM(araa.amount_applied)
                    FROM apps.ar_receivable_applications_all araa
                    WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                      AND araa.status = 'APP'
                      AND araa.apply_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                ), 0)
            """
            remaining_expr = f"ROUND(NVL(aps.amount_due_original, 0) - ({applied_asof_expr}), 2)"
            status_expr = f"CASE WHEN ({remaining_expr}) <= 0 THEN 'CL' ELSE 'OP' END"
            where_extra += " AND rct.trx_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')"
        else:
            today_expr = "TRUNC(SYSDATE)"
            remaining_expr = "ROUND(NVL(aps.amount_due_remaining, 0), 2)"
            status_expr = "aps.status"

        if status and status != "ALL":
            where_extra += f" AND ({status_expr}) = :status"
            params["status"] = status.upper()

        if customer_name:
            where_extra += " AND UPPER(hp.party_name) LIKE UPPER(:cust)"
            params["cust"] = f"%{customer_name}%"

        if invoice_number:
            where_extra += " AND UPPER(rct.trx_number) LIKE UPPER(:inv_num)"
            params["inv_num"] = f"%{invoice_number}%"

        if date_from:
            where_extra += " AND rct.trx_date >= TO_DATE(:date_from, 'YYYY-MM-DD')"
            params["date_from"] = date_from

        if date_to:
            where_extra += " AND rct.trx_date <= TO_DATE(:date_to, 'YYYY-MM-DD')"
            params["date_to"] = date_to

        # Corporate-rate IDR conversion — anchored to as_of_date when given,
        # otherwise standardized on today's rate for every row (same as
        # get_ar_aging). usd_rate, when given, substitutes this lookup for
        # USD rows only, regardless of the anchor date.
        usd_override = ""
        if usd_rate:
            usd_override = "WHEN rct.invoice_currency_code = 'USD' THEN :usd_rate\n            "
            params["usd_rate"] = usd_rate
        rate_case = f"""
            CASE WHEN rct.invoice_currency_code = 'IDR' THEN 1
            {usd_override}ELSE COALESCE((
                SELECT gdr.conversion_rate FROM apps.gl_daily_rates gdr
                WHERE  gdr.from_currency   = rct.invoice_currency_code
                  AND  gdr.to_currency     = 'IDR'
                  AND  gdr.conversion_type = 'Corporate'
                  AND  gdr.conversion_date = (
                      SELECT MAX(gdr2.conversion_date) FROM apps.gl_daily_rates gdr2
                      WHERE  gdr2.from_currency   = rct.invoice_currency_code
                        AND  gdr2.to_currency     = 'IDR'
                        AND  gdr2.conversion_type = 'Corporate'
                        AND  gdr2.conversion_date <= {today_expr}
                  )
            ), 1) END
        """

        sql = f"""
            SELECT
                hp.party_name                                        AS customer_name,
                hca.account_number,
                rct.trx_number                                       AS invoice_number,
                TO_CHAR(rct.trx_date,  'YYYY-MM-DD')                AS invoice_date,
                TO_CHAR(aps.due_date,  'YYYY-MM-DD')                AS due_date,
                ROUND(NVL(aps.amount_due_original,  0), 2)          AS original_amount,
                ({remaining_expr})                                   AS remaining_amount,
                rct.invoice_currency_code                            AS currency,
                ({rate_case})                                        AS conversion_rate,
                ROUND(NVL(aps.amount_due_original,  0) * ({rate_case}), 2) AS original_amount_idr,
                ROUND(({remaining_expr}) * ({rate_case}), 2)         AS remaining_amount_idr,
                ROUND({today_expr} - aps.due_date, 0)                AS days_overdue,
                rcttt.name                                           AS transaction_type,
                ({status_expr})                                      AS status,
                aps.class,
                SUBSTR(NVL(rct.comments, '-'), 1, 100)               AS tax_invoice_number,
                hou.name                                             AS operating_unit
            FROM apps.ar_payment_schedules_all  aps
            JOIN apps.ra_customer_trx_all        rct
                ON  rct.customer_trx_id  = aps.customer_trx_id
            JOIN apps.ra_cust_trx_types_all      rcttt
                ON  rcttt.cust_trx_type_id = rct.cust_trx_type_id
                AND rcttt.org_id           = rct.org_id
            JOIN apps.hz_cust_accounts           hca
                ON  hca.cust_account_id  = rct.bill_to_customer_id
            JOIN apps.hz_parties                 hp
                ON  hp.party_id          = hca.party_id
            JOIN apps.hr_operating_units         hou
                ON  hou.organization_id  = rct.org_id
            WHERE aps.class IN ('INV', 'DM', 'CM')
              {where_extra}
            ORDER BY
                CASE WHEN ({status_expr}) = 'OP' THEN 0 ELSE 1 END,
                aps.due_date ASC,
                hp.party_name
            FETCH FIRST {limit} ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            # Summary aggregates — now IDR-converted (total_remaining_idr /
            # total_overdue_idr) since class='CM' (credit memos / sales
            # returns) are included alongside INV/DM and some of those, plus
            # a handful of invoices, aren't IDR — summing the native-
            # currency remaining_amount as-is across mixed currencies (the
            # old behavior) understated/overstated the total depending on
            # which currencies happened to be outstanding. total_remaining/
            # total_overdue (native-currency sum) are kept too, for
            # backward compatibility with anything reading the old shape.
            open_rows   = [r for r in clean if r.get("status") == "OP"]
            overdue     = [r for r in open_rows if (r.get("days_overdue") or 0) > 0]
            total_remaining     = sum(r.get("remaining_amount", 0) for r in open_rows)
            total_overdue       = sum(r.get("remaining_amount", 0) for r in overdue)
            total_remaining_idr = sum(r.get("remaining_amount_idr", 0) for r in open_rows)
            total_overdue_idr   = sum(r.get("remaining_amount_idr", 0) for r in overdue)
            returns_rows = [r for r in open_rows if r.get("class") == "CM"]
            return {
                "success":    True,
                "count":      len(clean),
                "limit":      limit,
                "usd_rate":   usd_rate,
                "as_of_date": as_of_date,
                "summary": {
                    "open_invoice_count":    len(open_rows),
                    "overdue_count":         len(overdue),
                    "total_remaining":       round(total_remaining, 2),
                    "total_overdue":         round(total_overdue, 2),
                    "total_remaining_idr":   round(total_remaining_idr, 2),
                    "total_overdue_idr":     round(total_overdue_idr, 2),
                    "returns_count":         len(returns_rows),
                    "returns_remaining_idr": round(sum(r.get("remaining_amount_idr", 0) for r in returns_rows), 2),
                },
                "data": clean,
            }
        except Exception as e:
            logger.error("ar_outstanding_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_ar_aging(self, customer_name: str = None, as_of_date: str = None, limit: int = 500) -> dict:
        """
        AR Aging — items grouped by customer into 5 buckets (Current, 1-30,
        31-60, 61-90, >90 days overdue), Corporate-rate IDR converted and
        summed. class='CM' (credit memos / returns) is included in the
        same grouping, so a return nets against whichever bucket its own
        due_date falls into instead of being excluded — "dikurangin sales
        return" per request, same reasoning as get_ar_outstanding.

        as_of_date anchors what "today" means for the whole report — no
        separate invoice-date-range filter exists (or is needed) here,
        since as_of_date alone both scopes which invoices are in play
        (trx_date <= as_of_date) and reconstructs each one's remaining
        balance as of that date. Defaults to the actual current date but
        can be overridden by the user to re-bucket the report as of any
        past date.

        Like get_ar_outstanding's as_of_date, remaining balance is
        reconstructed by replaying AR_RECEIVABLE_APPLICATIONS_ALL
        (status='APP', apply_date <= as_of_date) against
        amount_due_original — NOT by reading today's live
        aps.status/amount_due_remaining — so a since-closed invoice that
        was still genuinely open as of the chosen date is correctly
        bucketed (see the MENSA 26110012 case that prompted this). Only
        cash/credit-memo applications are replayed; manual write-offs/
        adjustments (AR_ADJUSTMENTS_ALL) are not. due_date remains the
        reference column for every bucket (days_overdue = as_of_date -
        due_date), unchanged from before.
        """
        limit = min(max(limit, 1), 2000)
        where_extra = ""
        params: dict = {}
        if customer_name:
            where_extra += " AND UPPER(hp.party_name) LIKE UPPER(:cust)"
            params["cust"] = f"%{customer_name}%"

        as_of_date = as_of_date or date.today().isoformat()
        params["as_of_date"] = as_of_date
        asof_expr = "TRUNC(TO_DATE(:as_of_date, 'YYYY-MM-DD'))"

        applied_asof_expr = """
            NVL((
                SELECT SUM(araa.amount_applied)
                FROM apps.ar_receivable_applications_all araa
                WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                  AND araa.status = 'APP'
                  AND araa.apply_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
            ), 0)
        """
        remaining_asof_expr = f"(NVL(aps.amount_due_original, 0) - ({applied_asof_expr}))"

        rate_case = f"""
            CASE WHEN rct.invoice_currency_code = 'IDR' THEN 1
            ELSE COALESCE((
                SELECT gdr.conversion_rate FROM apps.gl_daily_rates gdr
                WHERE  gdr.from_currency   = rct.invoice_currency_code
                  AND  gdr.to_currency     = 'IDR'
                  AND  gdr.conversion_type = 'Corporate'
                  AND  gdr.conversion_date = (
                      SELECT MAX(gdr2.conversion_date) FROM apps.gl_daily_rates gdr2
                      WHERE  gdr2.from_currency   = rct.invoice_currency_code
                        AND  gdr2.to_currency     = 'IDR'
                        AND  gdr2.conversion_type = 'Corporate'
                        AND  gdr2.conversion_date <= {asof_expr}
                  )
            ), 1) END
        """

        sql = f"""
            SELECT
                customer_name, account_number,
                ROUND(SUM(CASE WHEN days_overdue <= 0                THEN remaining_idr ELSE 0 END), 2) AS current_amt,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 1  AND 30   THEN remaining_idr ELSE 0 END), 2) AS d1_30,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 31 AND 60   THEN remaining_idr ELSE 0 END), 2) AS d31_60,
                ROUND(SUM(CASE WHEN days_overdue BETWEEN 61 AND 90   THEN remaining_idr ELSE 0 END), 2) AS d61_90,
                ROUND(SUM(CASE WHEN days_overdue > 90                THEN remaining_idr ELSE 0 END), 2) AS over_90,
                ROUND(SUM(remaining_idr), 2)                                                             AS total_idr,
                COUNT(*)                                                                                 AS item_count
            FROM (
                SELECT
                    hp.party_name                                    AS customer_name,
                    hca.account_number,
                    ({asof_expr} - aps.due_date)                     AS days_overdue,
                    ({remaining_asof_expr}) * ({rate_case})          AS remaining_idr
                FROM apps.ar_payment_schedules_all  aps
                JOIN apps.ra_customer_trx_all        rct
                    ON  rct.customer_trx_id  = aps.customer_trx_id
                JOIN apps.hz_cust_accounts           hca
                    ON  hca.cust_account_id  = rct.bill_to_customer_id
                JOIN apps.hz_parties                 hp
                    ON  hp.party_id          = hca.party_id
                WHERE aps.class IN ('INV', 'DM', 'CM')
                  AND rct.trx_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                  AND ROUND({remaining_asof_expr}, 2) != 0
                  {where_extra}
            )
            GROUP BY customer_name, account_number
            ORDER BY total_idr DESC
            FETCH FIRST {limit} ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            totals = {
                "current_amt": round(sum(r.get("current_amt", 0) for r in clean), 2),
                "d1_30":       round(sum(r.get("d1_30", 0) for r in clean), 2),
                "d31_60":      round(sum(r.get("d31_60", 0) for r in clean), 2),
                "d61_90":      round(sum(r.get("d61_90", 0) for r in clean), 2),
                "over_90":     round(sum(r.get("over_90", 0) for r in clean), 2),
                "total_idr":   round(sum(r.get("total_idr", 0) for r in clean), 2),
                "item_count":  sum(r.get("item_count", 0) for r in clean),
            }
            return {"success": True, "count": len(clean), "as_of_date": as_of_date, "data": clean, "totals": totals}
        except Exception as e:
            logger.error("ar_aging_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

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
