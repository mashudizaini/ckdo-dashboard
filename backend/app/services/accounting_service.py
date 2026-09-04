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

    # Chart of Accounts whitelist for AP Outstanding — only the AP control
    # accounts listed in sumber/list_COA.png (Trade/Non-Trade Accounts
    # Payable to Related/Third Parties, Local/Import).
    AP_COA_WHITELIST = (
        "212111", "212112", "212121", "212122",
        "212211", "212212", "212221", "212222",
    )

    # Shared AP/AR legacy data-quality cutoff (see get_ap_outstanding /
    # get_ar_outstanding docstrings): transactions dated on/before this are
    # always shown Paid/remaining=0 in these dashboard reports, regardless
    # of Oracle's live status/remaining figures.
    LEGACY_PAID_CUTOFF = "2021-12-31"

    # GL account (segment4) for "VAT-INPUT" — used by get_ap_list. Some AP
    # invoices (confirmed live: Rentokil's EXPENSE REPORT-type invoices)
    # never get Oracle's native REC_TAX/NONREC_TAX line_type_lookup_code at
    # all — whoever enters the invoice instead adds a plain manual line
    # (line_type_lookup_code='ITEM', description literally "VAT") coded
    # straight to this GL account. Oracle's own invoice-summary Tax field
    # shows 0.00 for these (since REC_TAX/NONREC_TAX is what that field
    # reads), even though a real VAT amount was posted. get_ap_list treats
    # a distribution against this account as real VAT too.
    AP_VAT_INPUT_COA_SEGMENT4 = "114207"

    async def get_ap_outstanding(
        self,
        as_of_date: str = None,
        date_from: str = None,
        date_to: str = None,
        supplier_name: str = None,
        payment_status: str = None,
        limit: int = 500,
        usd_rate: float = None,
        eur_rate: float = None,
    ) -> dict:
        """
        AP Outstanding from Oracle EBS — AP_INVOICES_ALL + AP_PAYMENT_SCHEDULES_ALL.
        Mirrors the AP Outstanding report; excludes fully Paid invoices.
        as_of_date defaults to SYSDATE when not provided. Restricted to the
        AP_COA_WHITELIST chart-of-account codes (segment4).

        date_from/date_to filter which invoices are in play by
        ai.invoice_date (Period From/To) — same role as get_ar_outstanding's
        date_from/date_to, independent of as_of_date (which anchors the
        remaining/status calculation, not which invoices are considered).

        usd_rate/eur_rate (typically Bank Indonesia's Kurs Tengah as of
        as_of_date) drive the "Total After Revaluation" summary figure —
        SUM over Not Paid invoices of remaining_amount_orig (the OUTSTANDING
        balance in foreign currency, not the original invoice amount — a
        partially-paid invoice's revaluation should reflect what's still
        owed) * the matching override rate for USD/EUR rows, falling back to
        the existing remaining_amount_idr for every other currency
        (including IDR itself, and USD/EUR when no override was given).
        This only affects that one summary number — the per-row
        original_amount_idr/remaining_amount_idr columns are untouched.

        LEGACY_PAID_CUTOFF (see get_ar_outstanding) applies here too:
        invoices dated on/before it always have their remaining forced to
        0 (both IDR and original-currency), which makes them classify as
        Paid below and drop out of this report by construction (the
        payment_status != 'Paid' filter already always applies) — same
        dashboard-only exception, same reasoning (legacy-era invoices
        genuinely collected but missing/incomplete payment-application
        records in Oracle), Oracle itself untouched.
        """
        limit = min(max(limit, 1), 20000)

        date_expr = "TO_DATE(:as_of_date, 'YYYY-MM-DD')" if as_of_date else "TRUNC(SYSDATE)"
        params: dict = {}
        if as_of_date:
            params["as_of_date"] = as_of_date

        params["legacy_paid_cutoff"] = self.LEGACY_PAID_CUTOFF
        legacy_cond = "ai2.invoice_date <= TO_DATE(:legacy_paid_cutoff, 'YYYY-MM-DD')"

        coa_binds = {f"coa{i}": code for i, code in enumerate(self.AP_COA_WHITELIST)}
        params.update(coa_binds)
        coa_filter = "gcc.segment4 IN (" + ", ".join(f":{k}" for k in coa_binds) + ")"

        extra_where = ""
        if supplier_name:
            extra_where += " AND UPPER(pv.vendor_name) LIKE UPPER(:supplier_name)"
            params["supplier_name"] = f"%{supplier_name}%"
        if date_from:
            extra_where += " AND ai.invoice_date >= TO_DATE(:date_from, 'YYYY-MM-DD')"
            params["date_from"] = date_from
        if date_to:
            extra_where += " AND ai.invoice_date <= TO_DATE(:date_to, 'YYYY-MM-DD')"
            params["date_to"] = date_to
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
                   , ( SELECT aps.invoice_id
                            , SUM(aps.gross_amount)                                AS total_gross
                            , SUM(CASE WHEN {legacy_cond} THEN 0 ELSE aps.amount_remaining END)
                                                                                   AS total_remaining_orig
                            , SUM(CASE WHEN {legacy_cond} THEN 0 ELSE
                                   aps.amount_remaining *
                                   NVL(ai2.base_amount, ai2.invoice_amount) /
                                   DECODE(ai2.invoice_amount, 0, 1, ai2.invoice_amount)
                              END)
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
                  AND ai.gl_date                         <= {date_expr}
                  AND ffvl.flex_value_set_id              = ffvs.flex_value_set_id
                  AND ffvl.flex_value                     = gcc.segment4
                  AND {coa_filter}
                  AND CASE
                          WHEN NVL(sched_summary.total_remaining, 0) = 0
                               THEN 'Paid'
                          WHEN NVL(sched_summary.total_remaining, 0) <
                               NVL(sched_summary.total_gross, 0)
                               THEN 'Partially Paid'
                          ELSE 'Not Paid'
                      END != 'Paid'
                  {extra_where}
                ORDER BY pv.vendor_name, ai.invoice_date, ai.invoice_num
            )
            WHERE ROWNUM <= {limit}
        """
        reval_override = {}
        if usd_rate:
            reval_override["USD"] = usd_rate
        if eur_rate:
            reval_override["EUR"] = eur_rate

        def _revalued(r):
            ccy = r.get("currency")
            remaining_fc = r.get("remaining_amount_orig")
            if ccy in reval_override and remaining_fc is not None:
                return remaining_fc * reval_override[ccy]
            return r.get("remaining_amount_idr") or 0

        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = []
            for r in rows:
                row = {
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                }
                # Original amount revalued at the USD/EUR override rate
                # (falls back to the existing base_amount-derived
                # original_amount_idr for any other currency, or when no
                # override was given) — same formula the summary total
                # below sums, exposed per-row so the table shows exactly
                # what's being added up.
                row["after_revaluation_idr"] = round(_revalued(row), 2)
                clean.append(row)
            not_paid     = [r for r in clean if r.get("payment_status") == "Not Paid"]
            partial_paid = [r for r in clean if r.get("payment_status") == "Partially Paid"]
            total_idr    = sum(r.get("remaining_amount_idr") or 0 for r in clean)
            total_after_revaluation_idr = sum(r.get("after_revaluation_idr") or 0 for r in clean)

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

    async def get_ap_outstanding_with_payment(
        self,
        as_of_date: str = None,
        date_from: str = None,
        date_to: str = None,
        supplier_name: str = None,
        payment_status: str = None,
        limit: int = 500,
    ) -> dict:
        """
        AP Outstanding + payment application history — same scope/filters as
        get_ap_outstanding above (NOT a refactor of it — the base query is
        deliberately duplicated rather than shared, so a change to one
        report can never silently break the other), extended with one row
        per (invoice, payment applied against it) via
        AP_INVOICE_PAYMENTS_ALL + AP_CHECKS_ALL (LEFT JOIN, so a "Not Paid"
        invoice with nothing applied yet still appears — once, with
        payment_number/payment_date/payment_amount all NULL — instead of
        being dropped). An invoice with 3 partial payments applied appears
        as 3 rows here, sharing the same AP Outstanding columns and
        differing only in the payment_* columns.

        NOTE: AP_INVOICE_PAYMENTS_ALL / AP_CHECKS_ALL column names follow
        the standard Oracle EBS R12 AP schema — this has NOT been validated
        against this specific instance's live data (no direct Oracle access
        from where this was written). If it errors, the fix is almost
        certainly a column/table name mismatch here, not the surrounding logic.
        """
        limit = min(max(limit, 1), 20000)

        date_expr = "TO_DATE(:as_of_date, 'YYYY-MM-DD')" if as_of_date else "TRUNC(SYSDATE)"
        params: dict = {}
        if as_of_date:
            params["as_of_date"] = as_of_date

        params["legacy_paid_cutoff"] = self.LEGACY_PAID_CUTOFF
        legacy_cond = "ai2.invoice_date <= TO_DATE(:legacy_paid_cutoff, 'YYYY-MM-DD')"

        coa_binds = {f"coa{i}": code for i, code in enumerate(self.AP_COA_WHITELIST)}
        params.update(coa_binds)
        coa_filter = "gcc.segment4 IN (" + ", ".join(f":{k}" for k in coa_binds) + ")"

        extra_where = ""
        if supplier_name:
            extra_where += " AND UPPER(pv.vendor_name) LIKE UPPER(:supplier_name)"
            params["supplier_name"] = f"%{supplier_name}%"
        if date_from:
            extra_where += " AND ai.invoice_date >= TO_DATE(:date_from, 'YYYY-MM-DD')"
            params["date_from"] = date_from
        if date_to:
            extra_where += " AND ai.invoice_date <= TO_DATE(:date_to, 'YYYY-MM-DD')"
            params["date_to"] = date_to
        if payment_status and payment_status != "ALL":
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
                    sched_summary.total_remaining                                  AS remaining_amount_idr,
                    cks.check_number                                               AS payment_number,
                    TO_CHAR(NVL(apn.accounting_date, cks.check_date), 'YYYY-MM-DD') AS payment_date,
                    apn.amount                                                     AS payment_amount,
                    cks.payment_method_code                                        AS payment_method
                FROM apps.ap_invoices_all              ai
                   , apps.ap_suppliers                 pv
                   , apps.gl_code_combinations         gcc
                   , apps.fnd_flex_values_vl           ffvl
                   , apps.fnd_flex_value_sets          ffvs
                   , ( SELECT aps.invoice_id
                            , SUM(aps.gross_amount)                                AS total_gross
                            , SUM(CASE WHEN {legacy_cond} THEN 0 ELSE aps.amount_remaining END)
                                                                                   AS total_remaining_orig
                            , SUM(CASE WHEN {legacy_cond} THEN 0 ELSE
                                   aps.amount_remaining *
                                   NVL(ai2.base_amount, ai2.invoice_amount) /
                                   DECODE(ai2.invoice_amount, 0, 1, ai2.invoice_amount)
                              END)
                                                                                   AS total_remaining
                         FROM apps.ap_payment_schedules_all aps
                            , apps.ap_invoices_all          ai2
                        WHERE aps.invoice_id            = ai2.invoice_id
                          AND aps.payment_status_flag  IN ('N', 'P')
                          AND ai2.gl_date              <= {date_expr}
                        GROUP BY aps.invoice_id
                     ) sched_summary
                   , apps.ap_invoice_payments_all apn
                   , apps.ap_checks_all           cks
                WHERE ai.invoice_id                       = sched_summary.invoice_id
                  AND ai.vendor_id                        = pv.vendor_id
                  AND ai.accts_pay_code_combination_id    = gcc.code_combination_id
                  AND ai.gl_date                         <= {date_expr}
                  AND ffvl.flex_value_set_id              = ffvs.flex_value_set_id
                  AND ffvl.flex_value                     = gcc.segment4
                  AND {coa_filter}
                  AND apn.invoice_id (+)                  = ai.invoice_id
                  AND cks.check_id (+)                    = apn.check_id
                  AND CASE
                          WHEN NVL(sched_summary.total_remaining, 0) = 0
                               THEN 'Paid'
                          WHEN NVL(sched_summary.total_remaining, 0) <
                               NVL(sched_summary.total_gross, 0)
                               THEN 'Partially Paid'
                          ELSE 'Not Paid'
                      END != 'Paid'
                  {extra_where}
                ORDER BY pv.vendor_name, ai.invoice_date, ai.invoice_num, payment_date
            )
            WHERE ROWNUM <= {limit}
        """

        try:
            rows = await asyncio.to_thread(self._query, sql, params)
            clean = [
                {
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                }
                for r in rows
            ]
            not_paid_ids     = {r.get("invoice_id") for r in clean if r.get("payment_status") == "Not Paid"}
            partial_paid_ids = {r.get("invoice_id") for r in clean if r.get("payment_status") == "Partially Paid"}
            total_payment_applied = sum(r.get("payment_amount") or 0 for r in clean)

            return {
                "success":       True,
                "count":         len(clean),
                "invoice_count": len({r.get("invoice_id") for r in clean}),
                "as_of_date":    as_of_date or "today",
                "summary": {
                    "not_paid_count":            len(not_paid_ids),
                    "partial_paid_count":        len(partial_paid_ids),
                    "total_payment_applied_idr": round(total_payment_applied, 2),
                },
                "data": clean,
            }
        except Exception as e:
            logger.error("ap_outstanding_with_payment_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def get_ap_list(
        self,
        gl_date_from: str = None,
        gl_date_to: str = None,
        payment_date_cutoff: str = None,
        supplier_name: str = None,
        payment_status: str = None,
        limit: int = 500,
    ) -> dict:
        """
        AP List — every AP transaction by GL Date, Paid and unpaid alike
        (deliberately NOT excluding Paid, unlike get_ap_outstanding/
        get_ap_outstanding_with_payment above — this report's whole point).
        One row per invoice (payments aggregated into a single Payment
        total), not one row per payment application. Format follows
        "FORMAT LIST AP 2025.xlsx" (see the AP List plan for the full
        verification trail behind each column below).

        DPP/VAT/WHT/Total are a REPORT-LEVEL calculation, confirmed against
        the reference file and the user — NOT Oracle's real tax posting:
          dpp   = NVL(ai.base_amount, ai.invoice_amount)  — same expression
                  get_ap_outstanding already uses for original_amount_idr
          vat   = one of three cases, in priority order (see vat_expr in
                  the code below):
                  1. Oracle-native REC_TAX/NONREC_TAX distribution present
                     -> ROUND(dpp * 0.11, 2), computed fresh (NOT Oracle's
                     exact REC_TAX/NONREC_TAX amount; verified live those
                     two numbers differ, e.g. dpp 23,088,000 * 11% =
                     2,539,680 matches the reference file exactly).
                  2. No REC_TAX/NONREC_TAX, but a manual distribution line
                     was posted straight to the VAT-INPUT GL account
                     (AP_VAT_INPUT_COA_SEGMENT4) -> use that line's REAL
                     posted amount as-is. Confirmed live for Rentokil's
                     EXPENSE REPORT invoices: a line_type_lookup_code=
                     'ITEM' row, description literally "VAT", coded to
                     that account — Oracle's own invoice Tax field shows
                     0.00 for these (it only reads REC_TAX/NONREC_TAX),
                     but the VAT is real and posted, just not tagged the
                     way Oracle usually tags tax. Per the user: "walaupun
                     ini sebagai LINE tapi tetap di hitung sebagai VAT."
                  3. Neither -> 0. Confirmed live for Agus Suprianto/
                     Jiangsu: only ACCRUAL/AWT distributions, no tax
                     anywhere on the invoice, matching Oracle's own Tax
                     field being 0.00 (user-reported, with a screenshot)
                     and the reference file's row 8 (Agus Suprianto)
                     showing VAT = 0.
          wht   = SUM(AP_INVOICE_DISTRIBUTIONS_ALL.amount WHERE
                  line_type_lookup_code = 'AWT') — this one IS real Oracle
                  data, already negative in Oracle so no sign-flip needed
          total = dpp + vat + NVL(wht, 0)
          remaining_ap = 0 when payment_status = 'Paid' (see below), else
                  (total - NVL(payment, 0)) — verified live that Oracle's
                  actual AP_INVOICE_PAYMENTS_ALL.amount reflects the real
                  cash paid (~= dpp, not dpp+vat, since the 11% gross-up
                  above was never a real separately-paid amount), so the
                  naive subtraction alone would show a nonzero "remaining"
                  on invoices that are actually fully paid. Confirmed with
                  the user: force 0 in that case rather than show a
                  misleading residual.

        payment (and therefore payment_status/remaining_ap/payment_rate)
        respects `payment_date_cutoff` (default: today) — a payment applied
        AFTER the cutoff does not count. Requested by the user: "jika
        tanggal parameter Jan 1 - Dec 31 2025 dan payment date diisi 31 Dec
        2025, maka data yang diambil adalah yang pembayarannya maksimal 31
        Dec 2025" — an invoice genuinely paid in, say, January 2026 must
        still show as outstanding when the cutoff is Dec 31 2025, i.e. this
        report can answer "what did AP look like as of a past payment
        cutoff," not just "what does it look like today."

        This is why payment_status here is NOT the same
        AP_PAYMENT_SCHEDULES_ALL.amount_remaining-based CASE logic
        get_ap_outstanding/get_ap_outstanding_with_payment use above —
        amount_remaining is a live/current-only Oracle field with no
        historical snapshot, so it can't answer "was this Paid as of a past
        cutoff." Instead: payment_status = 'Paid' when the cutoff-filtered
        payment sum >= the invoice's total scheduled amount
        (AP_PAYMENT_SCHEDULES_ALL.gross_amount, summed per invoice — an
        immutable figure set when the schedule is created, unlike
        amount_remaining which mutates as payments post — so comparing
        against it works for any cutoff date, not just "now"),
        'Partially Paid' when partially covered, else 'Not Paid'. (Also
        incidentally fixes the reference file's own internal
        inconsistency noted in an earlier version of this docstring — a
        row with Payment == Total and Remaining == 0 still labeled "Not
        Paid" — since status is now derived from the same Payment figure
        shown in the report, not a separate live Oracle flag.)

        payment_rate is AP_INVOICE_PAYMENTS_ALL.EXCHANGE_RATE from the most
        recent payment applied ON OR BEFORE the cutoff (NULL/blank for
        invoices unpaid as of the cutoff, or IDR payments where Oracle
        doesn't populate it — confirmed live this is sparse-but-real, ~23%
        of payments, exactly matching the reference file's own
        blank-for-IDR pattern).

        gl_date_from/gl_date_to scope WHICH invoices appear (by GL Date);
        payment_date_cutoff separately scopes which of THOSE invoices'
        payments count — the two are independent, per the user's example
        (a full-year GL Date range with a Dec 31 payment cutoff).

        Response carries `count` (rows actually in `data`, capped by
        `limit`) separately from `total_count` (the true unbounded row
        count for the filter) and `monthly` (a YYYY-MM breakdown, also
        unbounded) — a user hitting `limit` should still see accurate
        totals/chart, not a silently truncated sum. Found live: a full
        year (2025) has 4,418 matching rows, well past the old 2000 cap,
        and the summary cards were being computed from the capped `data`
        list until this fix.
        """
        limit = min(max(limit, 1), 20000)

        params: dict = {}
        params["payment_date_cutoff"] = payment_date_cutoff or date.today().isoformat()
        cutoff_expr = "TO_DATE(:payment_date_cutoff, 'YYYY-MM-DD')"

        coa_binds = {f"coa{i}": code for i, code in enumerate(self.AP_COA_WHITELIST)}
        params.update(coa_binds)
        coa_filter = "gcc.segment4 IN (" + ", ".join(f":{k}" for k in coa_binds) + ")"

        params["vat_input_coa"] = self.AP_VAT_INPUT_COA_SEGMENT4

        # 'Paid'/'Partially Paid'/'Not Paid' derived from the SAME
        # cutoff-filtered payment_summary.total_payment shown as the
        # report's own Payment column, compared against
        # sched_summary.total_gross (the invoice's immutable total
        # scheduled amount) — NOT Oracle's live amount_remaining, which has
        # no historical snapshot and can't answer "as of a past cutoff."
        # See the docstring for the full reasoning.
        payment_status_expr = """CASE
                                      WHEN NVL(sched_summary.total_gross, 0) <> 0
                                           AND NVL(payment_summary.total_payment, 0) >= sched_summary.total_gross
                                           THEN 'Paid'
                                      WHEN NVL(payment_summary.total_payment, 0) > 0
                                           THEN 'Partially Paid'
                                      ELSE 'Not Paid'
                                  END"""

        # Two distinct real-tax signals, in priority order:
        #  1. Oracle-native REC_TAX/NONREC_TAX distribution present -> VAT
        #     is computed fresh as 11% of DPP (confirmed formula, see
        #     docstring — Oracle's own REC_TAX amount is NOT used directly).
        #  2. No REC_TAX/NONREC_TAX, but a manual line was posted straight
        #     to the VAT-INPUT GL account (confirmed live for Rentokil's
        #     EXPENSE REPORT invoices: line_type_lookup_code='ITEM',
        #     description "VAT", coded to AP_VAT_INPUT_COA_SEGMENT4) -> use
        #     that line's REAL posted amount as-is, not a recomputed 11% —
        #     it's an actual figure someone entered, not a reporting
        #     gross-up. Per the user: "walaupun ini sebagai LINE tapi tetap
        #     di hitung sebagai VAT."
        #  3. Neither -> VAT = 0 (e.g. Agus Suprianto/Jiangsu, no tax at
        #     all posted anywhere on the invoice).
        vat_expr = """CASE
                          WHEN NVL(tax_summary.rec_tax_amount, 0) <> 0
                               THEN ROUND(NVL(ai.base_amount, ai.invoice_amount) * 0.11, 2)
                          WHEN NVL(tax_summary.manual_vat_amount, 0) <> 0
                               THEN tax_summary.manual_vat_amount
                          ELSE 0
                      END"""

        extra_where = ""
        if supplier_name:
            extra_where += " AND UPPER(pv.vendor_name) LIKE UPPER(:supplier_name)"
            params["supplier_name"] = f"%{supplier_name}%"
        if gl_date_from:
            extra_where += " AND ai.gl_date >= TO_DATE(:gl_date_from, 'YYYY-MM-DD')"
            params["gl_date_from"] = gl_date_from
        if gl_date_to:
            extra_where += " AND ai.gl_date <= TO_DATE(:gl_date_to, 'YYYY-MM-DD')"
            params["gl_date_to"] = gl_date_to
        if payment_status and payment_status != "ALL":
            extra_where += f" AND {payment_status_expr} = :pay_status"
            params["pay_status"] = payment_status

        inner_sql = f"""
                SELECT
                    ai.org_id,
                    pv.vendor_name                                                 AS supplier_name,
                    hp.tax_reference                                               AS npwp,
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
                    {payment_status_expr}                                         AS payment_status,
                    CASE WHEN ai.invoice_currency_code <> 'IDR'
                         THEN ai.invoice_amount        END                         AS original_amount_orig,
                    NVL(ai.base_amount, ai.invoice_amount)                         AS dpp,
                    {vat_expr}                                                     AS vat,
                    NVL(wht_summary.wht_amount, 0)                                 AS wht,
                    NVL(ai.base_amount, ai.invoice_amount)
                        + {vat_expr}
                        + NVL(wht_summary.wht_amount, 0)                          AS total_ap,
                    NVL(payment_summary.total_payment, 0)                         AS payment,
                    payment_summary.latest_rate                                   AS payment_rate,
                    -- Forced to 0 when payment_status_expr says Paid, even
                    -- though (total_ap - payment) alone would rarely land
                    -- exactly on 0: the computed 11% VAT gross-up above is
                    -- a reporting figure, not a real amount anyone actually
                    -- paid separately, so the naive subtraction leaves a
                    -- residual ~= vat on fully-paid invoices. Confirmed
                    -- with the user before applying this guard.
                    CASE WHEN {payment_status_expr} = 'Paid' THEN 0
                         ELSE (NVL(ai.base_amount, ai.invoice_amount)
                                 + {vat_expr}
                                 + NVL(wht_summary.wht_amount, 0))
                               - NVL(payment_summary.total_payment, 0)
                    END                                                          AS remaining_ap
                FROM apps.ap_invoices_all              ai
                   , apps.ap_suppliers                 pv
                   , apps.hz_parties                   hp
                   , apps.gl_code_combinations         gcc
                   , apps.fnd_flex_values_vl           ffvl
                   , apps.fnd_flex_value_sets          ffvs
                   , ( SELECT aps.invoice_id
                            , SUM(aps.gross_amount)                                AS total_gross
                         FROM apps.ap_payment_schedules_all aps
                        GROUP BY aps.invoice_id
                     ) sched_summary
                   , ( SELECT aid.invoice_id
                            , SUM(aid.amount)                                     AS wht_amount
                         FROM apps.ap_invoice_distributions_all aid
                        WHERE aid.line_type_lookup_code = 'AWT'
                        GROUP BY aid.invoice_id
                     ) wht_summary
                   , ( SELECT aid.invoice_id
                            , SUM(CASE WHEN aid.line_type_lookup_code IN ('REC_TAX', 'NONREC_TAX')
                                       THEN aid.amount ELSE 0 END)                    AS rec_tax_amount
                            , SUM(CASE WHEN aid.line_type_lookup_code NOT IN ('REC_TAX', 'NONREC_TAX')
                                            AND aid_gcc.segment4 = :vat_input_coa
                                       THEN aid.amount ELSE 0 END)                    AS manual_vat_amount
                         FROM apps.ap_invoice_distributions_all aid
                            , apps.gl_code_combinations         aid_gcc
                        WHERE aid.dist_code_combination_id     = aid_gcc.code_combination_id (+)
                        GROUP BY aid.invoice_id
                     ) tax_summary
                   , ( SELECT apn.invoice_id
                            , SUM(apn.amount)                                     AS total_payment
                            , MAX(apn.exchange_rate) KEEP (
                                  DENSE_RANK LAST ORDER BY NVL(apn.accounting_date, cks.check_date)
                              )                                                   AS latest_rate
                         FROM apps.ap_invoice_payments_all apn
                            , apps.ap_checks_all           cks
                        WHERE cks.check_id (+)            = apn.check_id
                          AND NVL(apn.accounting_date, cks.check_date) <= {cutoff_expr}
                        GROUP BY apn.invoice_id
                     ) payment_summary
                WHERE ai.invoice_id                       = sched_summary.invoice_id (+)
                  AND ai.invoice_id                       = wht_summary.invoice_id (+)
                  AND ai.invoice_id                       = tax_summary.invoice_id (+)
                  AND ai.invoice_id                       = payment_summary.invoice_id (+)
                  AND ai.vendor_id                        = pv.vendor_id
                  AND pv.party_id                         = hp.party_id (+)
                  AND ai.accts_pay_code_combination_id    = gcc.code_combination_id
                  AND ffvl.flex_value_set_id              = ffvs.flex_value_set_id
                  AND ffvl.flex_value                     = gcc.segment4
                  AND {coa_filter}
                  {extra_where}
                ORDER BY ai.gl_date, pv.vendor_name, ai.invoice_num
        """

        detail_sql = f"SELECT * FROM ( {inner_sql} ) WHERE ROWNUM <= {limit}"

        # Monthly totals — a SEPARATE, unbounded aggregate over the exact
        # same filtered row set (same inner_sql, no ROWNUM cap), so the
        # chart above the table always reflects the true per-month totals
        # even when `limit` caps how many detail rows are actually
        # returned/displayed. Grouped by YYYY-MM (not just month-of-year)
        # so a multi-year gl_date range never conflates e.g. Jan-2024 with
        # Jan-2025.
        monthly_sql = f"""
            SELECT TO_CHAR(TO_DATE(t.gl_date, 'YYYY-MM-DD'), 'YYYY-MM') AS period,
                   COUNT(*)              AS cnt,
                   SUM(t.dpp)            AS total_dpp,
                   SUM(t.vat)            AS total_vat,
                   SUM(t.wht)            AS total_wht,
                   SUM(t.total_ap)       AS total_ap,
                   SUM(t.payment)        AS total_payment,
                   SUM(t.remaining_ap)   AS total_remaining_ap
            FROM ( {inner_sql} ) t
            GROUP BY TO_CHAR(TO_DATE(t.gl_date, 'YYYY-MM-DD'), 'YYYY-MM')
            ORDER BY period
        """

        # Payment-status counts, same unbounded-over-inner_sql idea as
        # monthly_sql above — kept as their own tiny query rather than
        # folded into monthly_sql, since a status breakdown grouped ALSO by
        # month isn't needed anywhere yet and would just add columns unused
        # by the current UI.
        status_sql = f"""
            SELECT t.payment_status, COUNT(*) AS cnt
            FROM ( {inner_sql} ) t
            GROUP BY t.payment_status
        """

        try:
            rows, monthly_rows, status_rows = await asyncio.gather(
                asyncio.to_thread(self._query, detail_sql, params),
                asyncio.to_thread(self._query, monthly_sql, params),
                asyncio.to_thread(self._query, status_sql, params),
            )
            clean = [
                {
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                }
                for r in rows
            ]
            for i, r in enumerate(clean, start=1):
                r["row_no"] = i

            # monthly/status figures come from monthly_sql/status_sql, NOT
            # from summing `clean` — `clean` is capped at `limit`, so an
            # AP List spanning more rows than `limit` (confirmed live: a
            # full 2025 has 4,418 rows, well past the old 2000 cap) would
            # otherwise silently understate every summary card, not just
            # the detail table below it.
            monthly = [
                {
                    "period": r.get("period"),
                    "count": int(r.get("cnt") or 0),
                    "total_dpp": round(float(r.get("total_dpp") or 0), 2),
                    "total_vat": round(float(r.get("total_vat") or 0), 2),
                    "total_wht": round(float(r.get("total_wht") or 0), 2),
                    "total_ap": round(float(r.get("total_ap") or 0), 2),
                    "total_payment": round(float(r.get("total_payment") or 0), 2),
                    "total_remaining_ap": round(float(r.get("total_remaining_ap") or 0), 2),
                }
                for r in monthly_rows
            ]
            status_counts = {r.get("payment_status"): int(r.get("cnt") or 0) for r in status_rows}
            true_count = sum(m["count"] for m in monthly)

            def _msum(key):
                return round(sum(m.get(key) or 0 for m in monthly), 2)

            return {
                "success": True,
                "count": len(clean),
                "total_count": true_count,
                "gl_date_from": gl_date_from,
                "gl_date_to": gl_date_to,
                "monthly": monthly,
                "summary": {
                    "not_paid_count": status_counts.get("Not Paid", 0),
                    "partial_paid_count": status_counts.get("Partially Paid", 0),
                    "paid_count": status_counts.get("Paid", 0),
                    "total_dpp": _msum("total_dpp"),
                    "total_vat": _msum("total_vat"),
                    "total_wht": _msum("total_wht"),
                    "total_ap": _msum("total_ap"),
                    "total_payment": _msum("total_payment"),
                    "total_remaining_ap": _msum("total_remaining_ap"),
                },
                "data": clean,
            }
        except Exception as e:
            logger.error("ap_list_error", error=str(e))
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
        application with gl_date <= as_of_date (AR_RECEIVABLE_
        APPLICATIONS_ALL, status='APP'); Status is derived from that
        reconstructed remaining (<=0 => CL, else OP). Only cash/credit-memo
        applications are replayed — manual adjustments/write-offs
        (AR_ADJUSTMENTS_ALL) are not, so a balance closed purely via
        write-off may still show as marginally open as of a past date.

        Anchored on gl_date rather than apply_date deliberately (changed
        2026-09-01) — apply_date is a free-text-entered business date and
        confirmed live to contain outright data-entry typos (invoice
        24110047 had a Rp 800,000,000 application entered with apply_date
        year 2525 instead of 2025), which silently excluded that payment
        from every as_of_date reconstruction from now until the year 2525.
        gl_date is the GL-posting date and doesn't carry that risk.

        Invoices dated after as_of_date are excluded (they didn't exist
        yet), the days-overdue and Corporate-rate lookup are anchored to
        as_of_date too, and the `status` filter is evaluated against the
        reconstructed status rather than the live one. Without as_of_date,
        behavior is unchanged from before (today's live status/remaining).

        Once a row is Closed, payment_date (the last receivable
        application's gl_date — capped at as_of_date when given) is
        surfaced and days_overdue freezes as of that date instead of
        continuing to count against today/as_of_date, so a paid invoice
        stops accumulating overdue days the moment it was actually paid.
        Still-open rows keep counting normally (payment_date is blank).

        LEGACY_PAID_CUTOFF (shared with get_ap_outstanding): invoices dated
        on/before this are always forced Status='CL'/remaining=0 here,
        regardless of what Oracle's
        aps.status/amount_due_remaining say. Found via a MENSA case where
        many pre-2022 invoices sit open in Oracle despite being genuinely
        collected — that generation of records is missing/incomplete
        AR_RECEIVABLE_APPLICATIONS_ALL rows for their receipts, and
        reconciling that in Oracle would mean replaying years of old
        receipts for no operational benefit. This is a dashboard-only
        display exception (Oracle itself is untouched) and applies
        globally across all customers, not just MENSA, since the gap is a
        legacy-data-era issue rather than a customer-specific one.

        class='CM' (credit memos / sales returns) rows are queried and
        still netted into every summary total exactly as before, but are
        no longer returned in `data` — "credit memo tidak ditampilkan
        tapi langsung mengurangi" (not shown as a line, but still directly
        reduces the totals). The Returns (CM) summary card is the only
        remaining visibility into them.

        Summary totals are computed via a SEPARATE unlimited aggregate query
        (see agg_sql below), not by summing the `limit`-capped display rows —
        summing the capped rows understated the total whenever more than
        `limit` invoices matched the filters (confirmed live: the card
        stopped changing when narrowing filters that still left more than
        `limit` matches, since it was really just re-summing whatever
        happened to fall in the top-`limit` slice each time).

        usd_rate no longer affects conversion_rate/original_amount_idr/
        remaining_amount_idr at all — those three are now always Oracle's
        own Corporate-rate lookup (unaffected by anything the user types),
        matching how AP Outstanding's original_amount_idr/remaining_amount_idr
        are untouched by its usd_rate/eur_rate override too. usd_rate now
        drives ONLY the new after_revaluation_idr column below — a clean,
        exclusively user-driven "what would this be worth at my rate"
        figure, separate from Oracle's system rate rather than silently
        blended into it.
        """
        limit = min(max(limit, 1), 20000)
        where_extra = ""
        params: dict = {}

        # Point-in-time reconstruction (see docstring). remaining_expr/
        # status_expr fall back to the plain live columns when no
        # as_of_date is given, so every downstream usage stays identical
        # to the pre-existing behavior in that case.
        if as_of_date:
            params["as_of_date"] = as_of_date
            today_expr = "TO_DATE(:as_of_date, 'YYYY-MM-DD')"
            # amount "settled" as of the date = cash/credit-memo applications
            # MINUS approved adjustments (AR_ADJUSTMENTS_ALL.amount is signed
            # negative for a write-down that reduces the receivable — e.g. a
            # PPh/withholding-tax adjustment — so subtracting it increases
            # the settled total, same direction as an application would).
            # Confirmed live (invoice 26130003): 3 applications summing
            # 1,771,369,105 + one -32,502,185 PPh adjustment = exactly the
            # 1,803,871,290 original amount, Oracle status already CL — but
            # this reconstruction used to only replay applications, leaving
            # the PPh portion looking permanently "still open" under any
            # As of Date. AR_ADJUSTMENTS_ALL.status = 'A' is Approved
            # (mirrors the 'APP' filter on applications — only count
            # finalized adjustments, not pending/rejected ones).
            applied_asof_expr = """
                NVL((
                    SELECT SUM(araa.amount_applied)
                    FROM apps.ar_receivable_applications_all araa
                    WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                      AND araa.status = 'APP'
                      AND araa.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                ), 0)
                -
                NVL((
                    SELECT SUM(adj.amount)
                    FROM apps.ar_adjustments_all adj
                    WHERE adj.payment_schedule_id = aps.payment_schedule_id
                      AND adj.status = 'A'
                      AND adj.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                ), 0)
            """
            remaining_expr = f"ROUND(NVL(aps.amount_due_original, 0) - ({applied_asof_expr}), 2)"
            status_expr = f"CASE WHEN ({remaining_expr}) <= 0 THEN 'CL' ELSE 'OP' END"
            where_extra += " AND rct.trx_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')"
            # Oracle's GREATEST returns NULL if EITHER argument is NULL (it
            # doesn't skip nulls like some other databases), so a plain
            # GREATEST(app_max, adj_max) would wrongly go blank whenever an
            # invoice closed via only ONE of the two mechanisms — this CASE
            # picks whichever side(s) actually has a value instead.
            payment_date_expr = """
                (SELECT CASE
                    WHEN app_max IS NULL THEN adj_max
                    WHEN adj_max IS NULL THEN app_max
                    ELSE GREATEST(app_max, adj_max)
                 END
                 FROM (
                    SELECT
                        (SELECT MAX(araa.gl_date) FROM apps.ar_receivable_applications_all araa
                         WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                           AND araa.status = 'APP'
                           AND araa.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')) AS app_max,
                        (SELECT MAX(adj.gl_date) FROM apps.ar_adjustments_all adj
                         WHERE adj.payment_schedule_id = aps.payment_schedule_id
                           AND adj.status = 'A'
                           AND adj.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')) AS adj_max
                    FROM dual
                 ))
            """
        else:
            today_expr = "TRUNC(SYSDATE)"
            remaining_expr = "ROUND(NVL(aps.amount_due_remaining, 0), 2)"
            status_expr = "aps.status"
            payment_date_expr = """
                (SELECT CASE
                    WHEN app_max IS NULL THEN adj_max
                    WHEN adj_max IS NULL THEN app_max
                    ELSE GREATEST(app_max, adj_max)
                 END
                 FROM (
                    SELECT
                        (SELECT MAX(araa.gl_date) FROM apps.ar_receivable_applications_all araa
                         WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                           AND araa.status = 'APP') AS app_max,
                        (SELECT MAX(adj.gl_date) FROM apps.ar_adjustments_all adj
                         WHERE adj.payment_schedule_id = aps.payment_schedule_id
                           AND adj.status = 'A') AS adj_max
                    FROM dual
                 ))
            """

        # LEGACY_PAID_CUTOFF override (see docstring) — forces old
        # invoices Closed/remaining=0 in the dashboard regardless of
        # Oracle's live aps.status/amount_due_remaining.
        params["legacy_paid_cutoff"] = self.LEGACY_PAID_CUTOFF
        legacy_cond = "rct.trx_date <= TO_DATE(:legacy_paid_cutoff, 'YYYY-MM-DD')"
        remaining_expr = f"CASE WHEN {legacy_cond} THEN 0 ELSE ({remaining_expr}) END"
        status_expr    = f"CASE WHEN {legacy_cond} THEN 'CL' ELSE ({status_expr}) END"

        # Once Closed, days_overdue freezes as of the last applied payment
        # instead of continuing to count against today/as_of_date — a paid
        # invoice shouldn't keep accumulating overdue days. Legacy-forced
        # rows have no real payment_date to freeze on, so they're zeroed
        # out directly below instead of falling through to today_expr.
        days_overdue_anchor = f"""
            CASE WHEN ({status_expr}) = 'CL' AND ({payment_date_expr}) IS NOT NULL
                 THEN ({payment_date_expr})
                 ELSE {today_expr}
            END
        """

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

        # Corporate-rate IDR conversion — Oracle's own rate, anchored to
        # as_of_date when given, otherwise today (same as get_ar_aging).
        # NOT affected by usd_rate — that only drives after_revaluation_idr
        # below, kept deliberately separate (see docstring).
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
                        AND  gdr2.conversion_date <= {today_expr}
                  )
            ), 1) END
        """

        # after_revaluation_idr — the ONLY figure usd_rate touches. USD rows
        # use the user's rate when given; every other row (including USD
        # when no override was given) falls back to the same Corporate rate
        # rate_case already computes, so this column is never blank/zero
        # relative to remaining_amount_idr, just potentially different for
        # USD when an override is active.
        reval_rate_case = "({rate_case})".format(rate_case=rate_case)
        if usd_rate:
            params["usd_rate"] = usd_rate
            reval_rate_case = f"""
                CASE WHEN rct.invoice_currency_code = 'USD' THEN :usd_rate
                ELSE ({rate_case}) END
            """

        base_sql = f"""
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
                ROUND(({remaining_expr}) * ({reval_rate_case}), 2)   AS after_revaluation_idr,
                CASE WHEN {legacy_cond} THEN 0
                     ELSE ROUND(({days_overdue_anchor}) - aps.due_date, 0) END AS days_overdue,
                CASE WHEN ({status_expr}) = 'CL' THEN TO_CHAR(({payment_date_expr}), 'YYYY-MM-DD') END AS payment_date,
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
        """
        list_sql = f"""
            {base_sql}
            ORDER BY
                CASE WHEN ({status_expr}) = 'OP' THEN 0 ELSE 1 END,
                aps.due_date ASC,
                hp.party_name
            FETCH FIRST {limit} ROWS ONLY
        """
        # Aggregate over the FULL matching set (no FETCH FIRST) — see
        # docstring on why this can't be a Python sum() over the capped
        # list_sql rows.
        agg_sql = f"""
            SELECT
                SUM(CASE WHEN status = 'OP' THEN 1 ELSE 0 END)                                   AS open_invoice_count,
                SUM(CASE WHEN status = 'OP' AND days_overdue > 0 THEN 1 ELSE 0 END)               AS overdue_count,
                SUM(CASE WHEN status = 'OP' THEN remaining_amount ELSE 0 END)                     AS total_remaining,
                SUM(CASE WHEN status = 'OP' AND days_overdue > 0 THEN remaining_amount ELSE 0 END) AS total_overdue,
                SUM(CASE WHEN status = 'OP' THEN remaining_amount_idr ELSE 0 END)                 AS total_remaining_idr,
                SUM(CASE WHEN status = 'OP' AND days_overdue > 0 THEN remaining_amount_idr ELSE 0 END) AS total_overdue_idr,
                SUM(CASE WHEN status = 'OP' THEN after_revaluation_idr ELSE 0 END)                AS total_after_revaluation_idr,
                SUM(CASE WHEN status = 'OP' AND class = 'CM' THEN 1 ELSE 0 END)                   AS returns_count,
                SUM(CASE WHEN status = 'OP' AND class = 'CM' THEN remaining_amount_idr ELSE 0 END) AS returns_remaining_idr
            FROM ({base_sql})
        """
        try:
            rows = await asyncio.to_thread(self._query, list_sql, params)
            clean = []
            for r in rows:
                clean.append({
                    k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)) else v)
                    for k, v in r.items()
                })
            # Credit memos are queried and netted into every summary total
            # (via agg_sql, which sees the full base_sql result set) exactly
            # like any other row, but aren't returned as their own line —
            # "tidak ditampilkan tapi langsung mengurangi" (not shown, but
            # still directly reduces the totals). The Returns (CM) summary
            # card remains the only visibility into them.
            visible_rows = [r for r in clean if r.get("class") != "CM"]

            agg_rows = await asyncio.to_thread(self._query, agg_sql, params)
            agg = agg_rows[0] if agg_rows else {}
            def _n(key):
                v = agg.get(key)
                return float(v) if v is not None else 0.0

            return {
                "success":    True,
                "count":      len(visible_rows),
                "limit":      limit,
                "usd_rate":   usd_rate,
                "as_of_date": as_of_date,
                "summary": {
                    "open_invoice_count":          int(_n("open_invoice_count")),
                    "overdue_count":                int(_n("overdue_count")),
                    "total_remaining":              round(_n("total_remaining"), 2),
                    "total_overdue":                round(_n("total_overdue"), 2),
                    "total_remaining_idr":          round(_n("total_remaining_idr"), 2),
                    "total_overdue_idr":            round(_n("total_overdue_idr"), 2),
                    "total_after_revaluation_idr":  round(_n("total_after_revaluation_idr"), 2),
                    "returns_count":                int(_n("returns_count")),
                    "returns_remaining_idr":         round(_n("returns_remaining_idr"), 2),
                },
                "data": visible_rows,
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
        past date. When as_of_date is today (the default), remaining comes
        straight from Oracle's live aps.amount_due_remaining, same as
        get_ar_outstanding's own default — only a genuine past date
        triggers the replay-based reconstruction below. Without this,
        Aging always reconstructed (even "as of today") while List
        defaulted to live data, and the two disagreed.

        Like get_ar_outstanding's as_of_date, remaining balance is
        reconstructed by replaying AR_RECEIVABLE_APPLICATIONS_ALL
        (status='APP', gl_date <= as_of_date — gl_date rather than
        apply_date, see get_ar_outstanding's docstring on the 24110047
        typo'd-apply_date case) AND AR_ADJUSTMENTS_ALL (status='A', same
        gl_date cutoff — confirmed live via invoice 26130003, a PPh/
        withholding-tax deduction is recorded as an approved adjustment
        here, not a receivable application; skipping it left the invoice
        looking permanently open under any As of Date even though Oracle's
        live status was already CL) against amount_due_original — NOT by
        reading today's live aps.status/amount_due_remaining — so a
        since-closed invoice that was still genuinely open as of the chosen
        date is correctly bucketed (see the MENSA 26110012 case that
        prompted this). due_date remains the reference column for every
        bucket (days_overdue = as_of_date - due_date), unchanged from before.

        LEGACY_PAID_CUTOFF (see get_ap_outstanding / get_ar_outstanding)
        applies here too — invoices dated on/before it are forced
        remaining=0, which drops them out of the report entirely via the
        remaining!=0 filter below, same dashboard-only exception, Oracle
        untouched.
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

        # Only reconstruct (replay applications+adjustments) for a genuine
        # PAST date — for "today" (the default), use Oracle's own live
        # amount_due_remaining directly, same as get_ar_outstanding's
        # default (no as_of_date) branch. Without this, Aging ALWAYS
        # reconstructed even at "today" while List defaulted to live Oracle
        # data — two different code paths computing what should be the same
        # number, confirmed live to disagree ("data di aging dengan data di
        # list tidak sinkron"). Same "historical only if actually in the
        # past" principle already used in exchange_rate_service.get_rates.
        is_historical = as_of_date != date.today().isoformat()
        if is_historical:
            applied_asof_expr = """
                NVL((
                    SELECT SUM(araa.amount_applied)
                    FROM apps.ar_receivable_applications_all araa
                    WHERE araa.applied_payment_schedule_id = aps.payment_schedule_id
                      AND araa.status = 'APP'
                      AND araa.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                ), 0)
                -
                NVL((
                    SELECT SUM(adj.amount)
                    FROM apps.ar_adjustments_all adj
                    WHERE adj.payment_schedule_id = aps.payment_schedule_id
                      AND adj.status = 'A'
                      AND adj.gl_date <= TO_DATE(:as_of_date, 'YYYY-MM-DD')
                ), 0)
            """
            remaining_asof_expr = f"(NVL(aps.amount_due_original, 0) - ({applied_asof_expr}))"
        else:
            remaining_asof_expr = "NVL(aps.amount_due_remaining, 0)"

        params["legacy_paid_cutoff"] = self.LEGACY_PAID_CUTOFF
        legacy_cond = "rct.trx_date <= TO_DATE(:legacy_paid_cutoff, 'YYYY-MM-DD')"
        remaining_asof_expr = f"CASE WHEN {legacy_cond} THEN 0 ELSE ({remaining_asof_expr}) END"

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
                ROUND(SUM(original_idr), 2)                                                              AS total_amount_idr,
                COUNT(*)                                                                                 AS item_count
            FROM (
                SELECT
                    hp.party_name                                    AS customer_name,
                    hca.account_number,
                    ({asof_expr} - aps.due_date)                     AS days_overdue,
                    ({remaining_asof_expr}) * ({rate_case})          AS remaining_idr,
                    NVL(aps.amount_due_original, 0) * ({rate_case})  AS original_idr
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
                "current_amt":     round(sum(r.get("current_amt", 0) for r in clean), 2),
                "d1_30":           round(sum(r.get("d1_30", 0) for r in clean), 2),
                "d31_60":          round(sum(r.get("d31_60", 0) for r in clean), 2),
                "d61_90":          round(sum(r.get("d61_90", 0) for r in clean), 2),
                "over_90":         round(sum(r.get("over_90", 0) for r in clean), 2),
                "total_idr":       round(sum(r.get("total_idr", 0) for r in clean), 2),
                "total_amount_idr": round(sum(r.get("total_amount_idr", 0) for r in clean), 2),
                "item_count":      sum(r.get("item_count", 0) for r in clean),
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
