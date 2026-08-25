"""
Financial Statement Service
─────────────────────────────────────────
Balance Sheet / Profit & Loss reporting sourced live from Oracle EBS 12.2.8
GL_BALANCES, matching the layout of sumber/FS_CKD OTTO 2015-2026_sent.xlsx.

COA structure (CKDO LEDGER, ledger_id verified live): 6-segment accounting
flexfield — Company.LineOfBusiness.Department.Account.Future1.Future2
(segment4 = natural account, verified against FND_ID_FLEX_SEGMENTS).

Balance formula (verified against 7/8 known reference-file values to the
cent for period JUN-26):
  Asset accounts (account_type='A'):     begin_balance_dr - begin_balance_cr
                                          + period_net_dr  - period_net_cr
  Liability/Equity (account_type='L'/'O'): the negation of the same (credit-
                                          normal), i.e. begin_cr - begin_dr
                                          + period_net_cr - period_net_dr
Critical gotchas discovered during validation:
  - MUST filter gcc.summary_flag='N' — parent/rollup code combinations also
    carry a balance row in gl_balances, and without this filter Property
    Plant & Equipment came out at 2.55x the correct value (children +
    parent double-counted).
  - MUST filter gb.currency_code='IDR' AND gb.translated_flag IS NULL —
    gl_balances also carries translated/reporting-currency rows (USD, EUR,
    SGD, JPY with translated_flag='R') for the same functional-currency
    balance; including them would multiply-count.
  - P&L (nominal) accounts do NOT use begin_balance — GL_BALANCES resets
    period_net to that period's activity only, so YTD = SUM(period_net)
    across the periods in range, no begin_balance term.
  - account_type is inconsistently tagged for a handful of accounts (e.g.
    411115/421113 tagged 'E' despite being revenue/discount accounts by
    number) — P&L classification here is done by natural-account NUMBER
    RANGE, not account_type, for reliability.

Known open item: TAX PAYABLES (213xxx) does not reconcile exactly against
the reference file (diff ~4.1bn on a 2.77bn line at JUN-26) — likely a
VAT netting/presentation convention (VAT Out/VAT Payable vs VAT Input)
that the client's finance team should confirm. Everything else validated
to the cent.
"""
import asyncio
from typing import Optional
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()

LEDGER_FILTER = """
    gb.actual_flag = 'A'
    AND gb.currency_code = 'IDR'
    AND gb.translated_flag IS NULL
    AND gcc.summary_flag = 'N'
    AND NVL(gcc.enabled_flag,'Y') = 'Y'
"""

ACCOUNT_DESC_JOIN = """
    LEFT JOIN fnd_flex_values_vl ffvl
      ON ffvl.flex_value = gcc.segment4
     AND ffvl.flex_value_set_id = (
          SELECT flex_value_set_id FROM fnd_id_flex_segments
          WHERE application_id=101 AND id_flex_code='GL#' AND segment_name='Account' AND ROWNUM=1)
"""


def _bucket(code: str, mapping: list) -> str:
    """First matching (label, prefixes, exact_codes) wins; falls back to
    'UNMAPPED' so nothing silently disappears from a total."""
    for label, prefixes, exact in mapping:
        if code in exact:
            return label
        for p in prefixes:
            if code.startswith(p):
                return label
    return "UNMAPPED"


# ── Balance Sheet — natural account -> line item ────────────────────────────
# (label, prefixes, exact_codes) — checked in order, first match wins.

BS_ASSET_MAP = [
    ("CASH & CASH EQUIVALENTS",   ["111"], ["911112"]),
    ("ACCOUNT RECEIVABLES",       ["112"], ["911113"]),
    ("INVENTORY",                 ["113"], ["911111"]),
    ("PREPAIDS",                  ["1141"], []),
    ("ACCRUED INCOME",            ["117"], []),
    ("OTHER CURRENT ASSETS",      ["1142", "115"], []),
    ("PROPERTY, PLANT AND EQUIPMENT", ["121"], []),
    ("INTANGIBLE ASSET",          ["122"], []),
    ("OTHER NON - CURRENT ASSETS", ["123", "124", "129"], []),
]

BS_LIABILITY_MAP = [
    ("SHORT TERM BORROWINGS",     ["211"], []),
    ("ACCOUNT PAYABLES",          ["212"], ["911121"]),
    # VAT (213118/9) is checked BEFORE the "2131" TAX PAYABLES prefix below
    # — _bucket() matches in list order, so this exact-code rule must come
    # first or the broader prefix would swallow it. Reference file's TAX
    # PAYABLES only reconciles once VAT Out/VAT Payable are excluded (VAT
    # netting is a distinct presentation convention from income-tax-type
    # withholding payables).
    ("OTHER CURRENT LIABILITIES", ["216"], ["213118", "213119"]),
    ("TAX PAYABLES",              ["2131"], []),  # remaining: 213111-213117, 213121
    ("ACCRUED EXPENSES",          ["214"], []),
    ("CURRENT PORTION OF LONG TERM BORROWINGS", ["215"], []),
    ("CURRENT LEASE LIABILITIES", ["217"], []),
    ("LTB-LOANS",                 ["221"], []),
    ("ESTIMATED LIABILITIES FOR EMPLOYEES", ["222"], []),
    ("NON-CURRENT SALES RETURN ALLOWANCE", ["223"], []),
    ("LONG-TERM LEASE LIABILITIES", ["225"], []),
]

BS_EQUITY_MAP = [
    ("CAPITAL STOCK",             ["311"], []),
    ("RETAINED EARNINGS - PRIOR YEAR", [], ["341111"]),
    ("RETAINED EARNINGS - CURRENT YEAR", [], ["341112"]),
    ("OTHER COMPREHENSIVE INCOME - PRIOR YEAR", [], ["341113"]),
    ("OTHER COMPREHENSIVE INCOME - CURRENT YEAR", [], ["34114"]),
]

# Which BS line items are "current" vs "non-current" — drives the
# CURRENT ASSETS / NON CURRENT ASSET / CURRENT LIABILITIES / NONCURRENT
# LIABILITIES grouping in the reference file.
BS_ASSET_CURRENT = ["CASH & CASH EQUIVALENTS", "ACCOUNT RECEIVABLES", "INVENTORY",
                     "PREPAIDS", "OTHER CURRENT ASSETS", "ACCRUED INCOME"]
BS_ASSET_NONCURRENT = ["PROPERTY, PLANT AND EQUIPMENT", "OTHER NON - CURRENT ASSETS", "INTANGIBLE ASSET"]
BS_LIAB_CURRENT = ["SHORT TERM BORROWINGS", "ACCOUNT PAYABLES", "TAX PAYABLES", "ACCRUED EXPENSES",
                    "CURRENT PORTION OF LONG TERM BORROWINGS", "CURRENT LEASE LIABILITIES",
                    "OTHER CURRENT LIABILITIES"]
BS_LIAB_NONCURRENT = ["LTB-LOANS", "ESTIMATED LIABILITIES FOR EMPLOYEES",
                       "NON-CURRENT SALES RETURN ALLOWANCE", "LONG-TERM LEASE LIABILITIES"]
BS_EQUITY_ORDER = ["CAPITAL STOCK", "RETAINED EARNINGS - PRIOR YEAR", "RETAINED EARNINGS - CURRENT YEAR",
                    "OTHER COMPREHENSIVE INCOME - PRIOR YEAR", "OTHER COMPREHENSIVE INCOME - CURRENT YEAR"]


# ── Profit & Loss — natural account -> line item (by number range, not
# account_type, since account_type is inconsistently tagged for a handful
# of accounts) ───────────────────────────────────────────────────────────

PL_SALES_MAP = [
    ("GROSS SALES - DOMESTIC",  [], ["411111"]),
    ("GROSS SALES - EXPORT",    [], ["411112"]),
    ("GROSS SALES - CMO",       [], ["411114"]),
    ("GROSS SALES - CONSIGNMENT", [], ["411116"]),
    ("GROSS SALES - OTHERS",    [], ["411113", "411115"]),
    ("SALES DISCOUNT",          ["421"], []),
    ("SALES RETURN",            ["431"], []),
]

PL_COGS_MAP = [
    ("COGS STANDARD / ACTUAL",  [], ["511111", "511112", "511121"]),
    ("PURCHASE / INVOICE PRICE VARIANCE", ["521"], []),
    ("FOH ALLOCATION / TRANSFER", ["531"], []),
    ("INVENTORY STOCKOPNAME ADJUSTMENT", ["541", "542"], []),
]

PL_EXPENSE_MAP = [
    ("EMPLOYEE COMPENSATION", [], [
        "610111", "610113", "610114", "610115", "610116",
        "610140", "610141", "610142", "610143", "610144", "610145",
        "610150", "610151", "610152", "610153", "610154",
        "610155", "610156", "610157", "610158", "610159",
    ]),
    ("EMPLOYEE ALLOWANCE COMPENSATION", [], [
        "610112", "610121", "610122", "610123", "610124", "610125", "610126", "610127",
        "610128", "610129", "610130", "610131", "610132", "610133", "610134",
        "610160", "610161", "610162", "610163", "610164",
        "610170", "610171", "610172", "610173", "610174",
        "610180", "610181", "610182", "610183", "610184",
        "610190", "610191", "610192", "610193", "610194",
        "610195", "610196", "610197", "610198", "610199",
    ]),
    ("RECRUITMENT & SELECTIONS", ["610211", "610212"], []),
    ("TRAINING & EDUCATION", ["610311", "610312"], []),
    ("OFFICE SUPPLIES", ["6104"], []),
    ("MAIL POSTAGE & FREIGHT EXPENSE", ["6105"], []),
    ("CONFERENCE & CONVENTION", ["610611", "610612"], []),
    ("TRAVELLING", ["610711", "610712"], []),
    ("RENT & SERVICE CHARGE", ["6108"], []),
    ("REPAIR & MAINTENANCE", ["6109"], []),
    ("INSURANCES", ["6110"], []),
    ("DEPRECIATIONS & AMORTIZATION", ["6111", "6112"], []),
    ("UTILITIES", ["6113"], []),
    ("PROFESSIONAL & JOB FEES", ["6114"], []),
    ("TAXES, RETRIBUTION & LICENSE", ["6115"], []),
    ("ADVERTISING, PROMOTION & MARKETING EXPENSE", ["6116"], []),
    ("MEETING & SUBSCRIPTION FEE", [], ["611711", "611811"]),
    ("ENTERTAINMENT & REPRESENTATION", ["6119"], []),
    ("INVENTORY ADJUSTMENT & WRITE OFF", ["6120"], []),
    ("SCIENTIFIC TRAINING", ["61217"], []),
    ("PRODUCT & MARKET DEVELOPMENT", ["6121"], []),  # after SCIENTIFIC TRAINING (612171-9) so those match first
    ("COMMISSION - OVERSEAS", [], ["612181"]),
    ("COMMISSION - LOCAL", [], ["612182"]),
    ("TOTAL REJECT , MATERIAL & WASTE TREATMENT", [], ["612311", "612411", "612412", "612511"]),
    ("TRANSPORTATION", [], ["612611"]),
    ("CLEANING TREATMENT", [], ["612711"]),
    ("SECURITIES", [], ["612811"]),
    ("DONATION", [], ["612911"]),
    ("BENEFIT PAID", ["6130"], []),
    ("BAD DEBT", [], ["613111"]),
    ("INTEREST EXPENSE OF LEASE LIABILITIES", [], ["614111"]),
    ("OTHER EXPENSES", ["6122", "613112", "613113", "619", "699999"], []),
]

PL_OTHER_MAP = [
    ("FINANCIAL INCOME", [], ["711111", "711112", "711114"]),
    ("FINANCIAL EXPENSE", ["7112"], []),
    ("OTHER NON-OPERATING INCOME/EXPENSE", ["7311"], []),
]

PL_TAX_MAP = [
    ("CORPORATE INCOME TAX", [], ["811111"]),
    ("DEFERRED TAX INCOME (EXPENSE)", [], ["811112"]),
]

PL_OCI_MAP = [
    ("OTHER COMPREHENSIVE INCOME", [], ["811116"]),
]

PL_EXPENSE_ORDER = [label for label, _, _ in PL_EXPENSE_MAP if label != "PRODUCT & MARKET DEVELOPMENT"]
# Keep the reference file's original row order (Product & Market Development
# appears before Scientific Training there) rather than the match-priority
# order used internally.
PL_EXPENSE_DISPLAY_ORDER = [
    "EMPLOYEE COMPENSATION", "EMPLOYEE ALLOWANCE COMPENSATION", "RECRUITMENT & SELECTIONS",
    "TRAINING & EDUCATION", "OFFICE SUPPLIES", "MAIL POSTAGE & FREIGHT EXPENSE",
    "CONFERENCE & CONVENTION", "TRAVELLING", "RENT & SERVICE CHARGE", "REPAIR & MAINTENANCE",
    "INSURANCES", "DEPRECIATIONS & AMORTIZATION", "UTILITIES", "PROFESSIONAL & JOB FEES",
    "TAXES, RETRIBUTION & LICENSE", "ADVERTISING, PROMOTION & MARKETING EXPENSE",
    "MEETING & SUBSCRIPTION FEE", "ENTERTAINMENT & REPRESENTATION", "INVENTORY ADJUSTMENT & WRITE OFF",
    "PRODUCT & MARKET DEVELOPMENT", "SCIENTIFIC TRAINING", "COMMISSION - OVERSEAS", "COMMISSION - LOCAL",
    "TOTAL REJECT , MATERIAL & WASTE TREATMENT", "TRANSPORTATION", "CLEANING TREATMENT", "SECURITIES",
    "DONATION", "BENEFIT PAID", "INTEREST EXPENSE OF LEASE LIABILITIES", "BAD DEBT", "OTHER EXPENSES",
]


class FinancialStatementService:

    _MONTH_NAMES = {"JAN": "January", "FEB": "February", "MAR": "March", "APR": "April",
                     "MAY": "May", "JUN": "June", "JUL": "July", "AUG": "August",
                     "SEP": "September", "OCT": "October", "NOV": "November", "DEC": "December"}

    @staticmethod
    def period_display_label(period_name: str) -> str:
        """GL period names are 'MON-YY' (e.g. 'JUN-26') or 'ADJ-YY' — parsed
        directly, no DB round-trip needed, for Excel export title/header
        labels."""
        parts = (period_name or "").split("-")
        if len(parts) != 2:
            return period_name
        mon, yy = parts
        year = 2000 + int(yy) if yy.isdigit() else yy
        if mon == "ADJ":
            return f"Adjustment {year}"
        return f"{FinancialStatementService._MONTH_NAMES.get(mon, mon)} {year}"

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ── Periods ──────────────────────────────────────────────────────────

    async def get_periods(self) -> dict:
        """All GL periods for the primary ledger, plus which ones actually
        have posted balances (so the frontend can default to a sensible
        'through' period instead of showing empty future months)."""
        sql = """
            SELECT gp.period_name, gp.period_year, gp.period_num, gp.adjustment_period_flag,
                   gp.start_date, gp.end_date,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM gl_balances gb WHERE gb.period_name = gp.period_name AND gb.actual_flag='A'
                   ) THEN 'Y' ELSE 'N' END AS has_activity
            FROM gl_periods gp
            WHERE gp.period_set_name = (
                SELECT period_set_name FROM gl_ledgers WHERE ledger_category_code='PRIMARY' AND object_type_code='L' AND ROWNUM=1)
            ORDER BY gp.start_date
        """
        rows = await asyncio.to_thread(self._query, sql)
        for r in rows:
            r["start_date"] = r["start_date"].isoformat() if r["start_date"] else None
            r["end_date"] = r["end_date"].isoformat() if r["end_date"] else None
        return {"success": True, "data": rows}

    def _periods_lookup(self) -> dict:
        """period_name -> {year, num, adj} for every period in the primary
        ledger's calendar — used to derive 'Jan through this period, same
        fiscal year' ranges for the current-year retained earnings/OCI fix
        below, without the caller having to pass that in."""
        sql = """
            SELECT period_name, period_year, period_num, adjustment_period_flag
            FROM gl_periods
            WHERE period_set_name = (
                SELECT period_set_name FROM gl_ledgers WHERE ledger_category_code='PRIMARY' AND object_type_code='L' AND ROWNUM=1)
        """
        rows = self._query(sql)
        return {r["period_name"]: {"year": r["period_year"], "num": r["period_num"],
                                    "adj": r["adjustment_period_flag"]} for r in rows}

    def _ytd_periods(self, period_name: str, lookup: dict) -> list[str]:
        """All non-adjustment period_names in the same fiscal year as
        `period_name`, from period 1 through (and including) it — the
        'Jan through this period' range GL closes retained earnings from."""
        info = lookup.get(period_name)
        if not info:
            return [period_name]
        year, num = info["year"], info["num"]
        return sorted(
            (p for p, i in lookup.items() if i["year"] == year and i["adj"] == "N" and i["num"] <= num),
            key=lambda p: lookup[p]["num"],
        )

    # ── Balance Sheet ────────────────────────────────────────────────────

    # account_group query param -> Oracle account_type codes. "All"/None
    # keeps the original ('A','L','O') scan; a specific group both shrinks
    # the GL_BALANCES scan and (in get_balance_sheet below) skips the
    # equity-only retained-earnings/OCI P&L lookup entirely when it isn't
    # even going to be displayed.
    _ACCOUNT_GROUP_TYPES = {"ASSETS": ("A",), "LIABILITIES": ("L",), "EQUITY": ("O",)}

    def _fetch_balances(self, period_names: list[str], account_types: tuple = ("A", "L", "O")) -> list[dict]:
        placeholders = ",".join(f":p{i}" for i in range(len(period_names)))
        params = {f"p{i}": p for i, p in enumerate(period_names)}
        type_placeholders = ",".join(f":t{i}" for i in range(len(account_types)))
        for i, t in enumerate(account_types):
            params[f"t{i}"] = t
        sql = f"""
            SELECT gb.period_name, gcc.segment4 AS account_code, ffvl.description AS account_desc,
                   gcc.account_type,
                   SUM(gb.begin_balance_dr - gb.begin_balance_cr + gb.period_net_dr - gb.period_net_cr) AS raw_balance
            FROM gl_balances gb
            JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id
            {ACCOUNT_DESC_JOIN}
            WHERE gb.period_name IN ({placeholders})
              AND {LEDGER_FILTER}
              AND gcc.account_type IN ({type_placeholders})
            GROUP BY gb.period_name, gcc.segment4, ffvl.description, gcc.account_type
        """
        return self._query(sql, params)

    def _pl_after_tax_and_oci(self, periods: list[str]) -> tuple:
        rows = self._fetch_pl(periods)
        amt = self._pl_bucket_amounts(rows)
        sales = sum(amt.get(l, 0) for l, _, _ in PL_SALES_MAP)
        cogs = sum(amt.get(l, 0) for l, _, _ in PL_COGS_MAP)
        expenses = sum(amt.get(l, 0) for l in PL_EXPENSE_DISPLAY_ORDER)
        other = sum(amt.get(l, 0) for l, _, _ in PL_OTHER_MAP)
        tax = sum(amt.get(l, 0) for l, _, _ in PL_TAX_MAP)
        profit_after_tax = (sales - cogs) - expenses + other + tax
        oci = amt.get("OTHER COMPREHENSIVE INCOME", 0)
        return profit_after_tax, oci

    async def get_balance_sheet(self, period_names: list[str], account_group: Optional[str] = None) -> dict:
        """Balance Sheet grouped into line items — one column per period
        in `period_names` (annual FY-end periods and/or current-year
        monthly periods, matching the reference file's column layout).
        account_group ("ASSETS"/"LIABILITIES"/"EQUITY", or None for all)
        narrows both the GL_BALANCES scan and, when equity isn't requested,
        skips the retained-earnings/OCI P&L lookup below entirely."""
        account_types = self._ACCOUNT_GROUP_TYPES.get(account_group, ("A", "L", "O"))
        rows = await asyncio.to_thread(self._fetch_balances, period_names, account_types)

        # per period_name -> {line_item: amount}
        cols: dict = {p: {} for p in period_names}
        for r in rows:
            code, atype, raw = r["account_code"], r["account_type"], float(r["raw_balance"] or 0)
            if atype == "A":
                label = _bucket(code, BS_ASSET_MAP)
                amount = raw
            elif atype == "L":
                label = _bucket(code, BS_LIABILITY_MAP)
                amount = -raw
            else:  # 'O'
                label = _bucket(code, BS_EQUITY_MAP)
                amount = -raw
            cols[r["period_name"]][label] = cols[r["period_name"]].get(label, 0) + amount

        # RETAINED EARNINGS - CURRENT YEAR / OTHER COMPREHENSIVE INCOME -
        # CURRENT YEAR are only populated in GL_BALANCES once the fiscal
        # year is closed — for an open year (like the current one), the
        # reference file itself computes these two rows as a live formula
        # off the P&L sheet's Profit After Tax / OCI for Jan-through-this-
        # period, rather than trusting a GL account that's still empty.
        # Mirror that here rather than showing a false 0 that breaks
        # Assets = Liabilities + Equity. Only needed when Equity is part of
        # the requested account_group — skipped otherwise (no Assets/
        # Liabilities-only view needs it, and it's the most expensive part
        # of this endpoint: one extra Oracle round-trip per period).
        if "O" in account_types:
            lookup = await asyncio.to_thread(self._periods_lookup)
            # Was a sequential `for p in period_names: await ...` loop — one
            # fresh Oracle connection + query per period, one at a time. For
            # a wide year range (e.g. 2022-2026 -> 5-6 columns) that meant
            # 5-6 full round-trips back to back before anything came back,
            # which is what made wide ranges look like they'd hung. Firing
            # them concurrently instead turns that into ~1 round-trip's
            # worth of wall-clock time.
            ytd_lists = [self._ytd_periods(p, lookup) for p in period_names]
            pl_results = await asyncio.gather(*[
                asyncio.to_thread(self._pl_after_tax_and_oci, ytd) for ytd in ytd_lists
            ])
            for p, (profit_after_tax, oci) in zip(period_names, pl_results):
                cols[p]["RETAINED EARNINGS - CURRENT YEAR"] = profit_after_tax
                cols[p]["OTHER COMPREHENSIVE INCOME - CURRENT YEAR"] = oci
        else:
            for p in period_names:
                cols[p]["RETAINED EARNINGS - CURRENT YEAR"] = 0
                cols[p]["OTHER COMPREHENSIVE INCOME - CURRENT YEAR"] = 0

        def section(labels):
            return [{"label": l, "values": [cols[p].get(l, 0) for p in period_names]} for l in labels]

        current_assets = section(BS_ASSET_CURRENT)
        noncurrent_assets = section(BS_ASSET_NONCURRENT)
        current_liab = section(BS_LIAB_CURRENT)
        noncurrent_liab = section(BS_LIAB_NONCURRENT)
        equity = section(BS_EQUITY_ORDER)

        def totals(rows_):
            return [sum(row["values"][i] for row in rows_) for i in range(len(period_names))]

        total_current_assets = totals(current_assets)
        total_noncurrent_assets = totals(noncurrent_assets)
        total_assets = [a + b for a, b in zip(total_current_assets, total_noncurrent_assets)]
        total_current_liab = totals(current_liab)
        total_noncurrent_liab = totals(noncurrent_liab)
        total_liabilities = [a + b for a, b in zip(total_current_liab, total_noncurrent_liab)]
        total_equity = totals(equity)
        total_liab_equity = [a + b for a, b in zip(total_liabilities, total_equity)]

        unmapped = sorted({r["account_code"] for r in rows if _bucket(
            r["account_code"], BS_ASSET_MAP if r["account_type"] == "A" else
            BS_LIABILITY_MAP if r["account_type"] == "L" else BS_EQUITY_MAP) == "UNMAPPED"})

        return {
            "success": True,
            "periods": period_names,
            "column_labels": [self.period_display_label(p) for p in period_names],
            "current_assets": current_assets, "total_current_assets": total_current_assets,
            "noncurrent_assets": noncurrent_assets, "total_noncurrent_assets": total_noncurrent_assets,
            "total_assets": total_assets,
            "current_liabilities": current_liab, "total_current_liabilities": total_current_liab,
            "noncurrent_liabilities": noncurrent_liab, "total_noncurrent_liabilities": total_noncurrent_liab,
            "total_liabilities": total_liabilities,
            "equity": equity, "total_equity": total_equity,
            "total_liabilities_and_equity": total_liab_equity,
            "check_diff": [a - b for a, b in zip(total_liab_equity, total_assets)],
            "unmapped_accounts": unmapped,
        }

    async def get_balance_sheet_detail(self, period_names: list[str], account_group: Optional[str] = None) -> dict:
        """Same balances as get_balance_sheet but at natural-account
        granularity (no line-item grouping) — a drill-down view."""
        account_types = self._ACCOUNT_GROUP_TYPES.get(account_group, ("A", "L", "O"))
        rows = await asyncio.to_thread(self._fetch_balances, period_names, account_types)

        accounts: dict = {}
        for r in rows:
            code, atype, raw = r["account_code"], r["account_type"], float(r["raw_balance"] or 0)
            sign = 1 if atype == "A" else -1
            key = code
            if key not in accounts:
                accounts[key] = {
                    "account_code": code,
                    "account_desc": r["account_desc"] or "",
                    "account_type": atype,
                    "line_item": _bucket(code, BS_ASSET_MAP if atype == "A" else
                                          BS_LIABILITY_MAP if atype == "L" else BS_EQUITY_MAP),
                    "values": {p: 0 for p in period_names},
                }
            accounts[key]["values"][r["period_name"]] = accounts[key]["values"].get(r["period_name"], 0) + sign * raw

        out = []
        for acc in accounts.values():
            acc["values"] = [acc["values"].get(p, 0) for p in period_names]
            out.append(acc)
        out.sort(key=lambda a: (a["account_type"], a["account_code"]))
        return {
            "success": True, "periods": period_names,
            "column_labels": [self.period_display_label(p) for p in period_names],
            "accounts": out,
        }

    # ── Profit & Loss ────────────────────────────────────────────────────

    def _fetch_pl(self, period_names: list[str]) -> list[dict]:
        placeholders = ",".join(f":p{i}" for i in range(len(period_names)))
        params = {f"p{i}": p for i, p in enumerate(period_names)}
        sql = f"""
            SELECT gcc.segment4 AS account_code, ffvl.description AS account_desc,
                   SUM(gb.period_net_dr - gb.period_net_cr) AS raw_net
            FROM gl_balances gb
            JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id
            {ACCOUNT_DESC_JOIN}
            WHERE gb.period_name IN ({placeholders})
              AND {LEDGER_FILTER}
              AND gcc.account_type IN ('R','E')
            GROUP BY gcc.segment4, ffvl.description
        """
        return self._query(sql, params)

    def _pl_bucket_amounts(self, rows: list[dict]) -> dict:
        """Classify P&L accounts by NUMBER RANGE (not account_type — see
        module docstring) and return {line_item: amount} using each
        section's natural credit/debit sign so amounts read as a normal
        income statement (revenue positive, expenses positive-as-a-cost)."""
        out: dict = {}

        def add(label, amount):
            out[label] = out.get(label, 0) + amount

        unmapped = []
        for r in rows:
            code, raw = r["account_code"], float(r["raw_net"] or 0)
            if code.startswith("411") or code.startswith("421") or code.startswith("431"):
                label = _bucket(code, PL_SALES_MAP)
                add(label, -raw)  # revenue is credit-normal -> negate dr-cr
            elif code.startswith("511") or code.startswith("521") or code.startswith("531") \
                    or code.startswith("541") or code.startswith("542"):
                label = _bucket(code, PL_COGS_MAP)
                add(label, raw)  # cost accounts are debit-normal
            elif code.startswith("61"):
                label = _bucket(code, PL_EXPENSE_MAP)
                add(label, raw)
            elif code.startswith("711"):
                # Both Financial Income and Financial Expense are stored
                # as (cr-dr): income (credit-heavy) comes out positive,
                # expense (debit-heavy, even though Oracle tags these
                # accounts account_type='R') comes out negative — matching
                # the reference file's own sign convention for this section.
                label = _bucket(code, PL_OTHER_MAP)
                add(label, -raw)
            elif code.startswith("731"):
                label = _bucket(code, PL_OTHER_MAP)
                add(label, -raw)  # net gain(+)/loss(-) style, credit-normal
            elif code.startswith("811") and code != "811116":
                label = _bucket(code, PL_TAX_MAP)
                add(label, -raw)
            elif code == "811116":
                add("OTHER COMPREHENSIVE INCOME", -raw)
            else:
                unmapped.append(code)
                continue
            if label == "UNMAPPED":
                unmapped.append(code)
        out["_unmapped"] = sorted(set(unmapped))
        return out

    async def get_profit_and_loss(self, columns: list[dict]) -> dict:
        """`columns` = [{"label": "FY 2025", "periods": ["JAN-25", ..., "DEC-25", "ADJ-25"]}, ...]
        One column per fiscal year / YTD range, matching the reference
        file's year-by-year layout."""
        # One query per column — periods differ per column (each fiscal
        # year / YTD range), so there's no shared row set to reuse.
        col_amounts = []
        for c in columns:
            crows = await asyncio.to_thread(self._fetch_pl, c["periods"])
            col_amounts.append(self._pl_bucket_amounts(crows))

        labels = [c["label"] for c in columns]

        def line(label):
            return {"label": label, "values": [amt.get(label, 0) for amt in col_amounts]}

        sales_lines = [line(l) for l, _, _ in PL_SALES_MAP if l != "SALES DISCOUNT" and l != "SALES RETURN"]
        # Net sales already nets discount/return into whichever GROSS SALES
        # bucket it was summed with only if same label — they're distinct
        # labels here, so show them as their own contra-lines beneath sales.
        contra_lines = [line(l) for l, _, _ in PL_SALES_MAP if l in ("SALES DISCOUNT", "SALES RETURN")]
        total_net_sales = [sum(v) for v in zip(*[l["values"] for l in sales_lines + contra_lines])] if sales_lines else [0] * len(columns)

        cogs_lines = [line(l) for l, _, _ in PL_COGS_MAP]
        total_cogs = [sum(v) for v in zip(*[l["values"] for l in cogs_lines])] if cogs_lines else [0] * len(columns)

        gross_profit = [s - c for s, c in zip(total_net_sales, total_cogs)]

        expense_lines = [line(l) for l in PL_EXPENSE_DISPLAY_ORDER]
        total_expenses = [sum(v) for v in zip(*[l["values"] for l in expense_lines])] if expense_lines else [0] * len(columns)

        other_lines = [line(l) for l, _, _ in PL_OTHER_MAP]
        total_other = [sum(v) for v in zip(*[l["values"] for l in other_lines])] if other_lines else [0] * len(columns)

        profit_before_tax = [g - e + o for g, e, o in zip(gross_profit, total_expenses, total_other)]

        tax_lines = [line(l) for l, _, _ in PL_TAX_MAP]
        total_tax = [sum(v) for v in zip(*[l["values"] for l in tax_lines])] if tax_lines else [0] * len(columns)

        profit_after_tax = [p + t for p, t in zip(profit_before_tax, total_tax)]

        oci_line = line("OTHER COMPREHENSIVE INCOME")
        total_comprehensive = [p + o for p, o in zip(profit_after_tax, oci_line["values"])]

        unmapped = sorted(set(sum((amt.get("_unmapped", []) for amt in col_amounts), [])))

        return {
            "success": True, "columns": labels,
            "sales_lines": sales_lines, "contra_lines": contra_lines, "total_net_sales": total_net_sales,
            "cogs_lines": cogs_lines, "total_cogs": total_cogs, "gross_profit": gross_profit,
            "expense_lines": expense_lines, "total_expenses": total_expenses,
            "other_lines": other_lines, "total_other": total_other,
            "profit_before_tax": profit_before_tax,
            "tax_lines": tax_lines, "total_tax": total_tax,
            "profit_after_tax": profit_after_tax,
            "oci": oci_line["values"], "total_comprehensive": total_comprehensive,
            "unmapped_accounts": unmapped,
        }

    async def get_profit_and_loss_monthly(self, period_this: str, ytd_this: list[str],
                                           period_last: str, ytd_last: list[str]) -> dict:
        """MTD/YTD comparison — this year's period vs the same period last
        year, matching the PL_monthly reference tab (4 columns: MTD last
        year, YTD last year, MTD this year, YTD this year)."""
        columns = [
            {"label": "MTD Last Year", "periods": [period_last]},
            {"label": "YTD Last Year", "periods": ytd_last},
            {"label": "MTD This Year", "periods": [period_this]},
            {"label": "YTD This Year", "periods": ytd_this},
        ]
        return await self.get_profit_and_loss(columns)

    # ── Cash Flow (Indirect method) ─────────────────────────────────────────
    # There's no live Oracle equivalent of the statutory (direct) Cash Flow
    # statement — see cash-flow's own docstring in the router — but the
    # INDIRECT method is, by construction, entirely derivable from data this
    # service already computes: Net Profit After Tax (from get_profit_and_loss
    # for the exact period range) adjusted for non-cash items and the
    # PERIOD-OVER-PERIOD MOVEMENT of every other Balance Sheet line (from
    # get_balance_sheet at the opening and closing periods). Classification
    # below (which BS line -> Operating/Investing/Financing) follows standard
    # PSAK/IFRS indirect-method convention:
    #   Operating   = working-capital current assets/liabilities (AR,
    #                 Inventory, Prepaids, AP, Tax Payables, Accrued Expenses,
    #                 Other Current *) + non-current employee-benefit/sales-
    #                 return provisions (non-cash, not real financing) +
    #                 Depreciation & Amortization add-back.
    #   Investing   = non-current assets (PPE, Intangibles, Other Non-Current
    #                 Assets) — a change here is treated as the net of any
    #                 capex/disposal for the period (this service has no
    #                 separate capex sub-ledger to split gross additions from
    #                 depreciation runoff, so it's the net BS movement).
    #   Financing   = borrowings (short-term, current portion of LT, LT),
    #                 lease liabilities (current + non-current — lease
    #                 principal repayment is a financing activity under
    #                 PSAK 73/IFRS 16, not operating), and Capital Stock.
    #   Excluded    = Retained Earnings / OCI equity movements — already
    #                 fully represented by Net Profit After Tax above; adding
    #                 their BS delta too would double-count it.
    # Every Balance Sheet bucket this service knows about (BS_ASSET_CURRENT/
    # NONCURRENT, BS_LIAB_CURRENT/NONCURRENT, and Capital Stock from equity)
    # is classified exactly once above — Cash itself is used only as the
    # opening/closing anchor. That completeness is what makes the
    # reconciliation check below meaningful: opening cash + net movement
    # should equal closing cash almost exactly; a nonzero diff flags GL
    # activity this derivation can't see (FX translation, revaluations,
    # rounding in an adjustment period) worth a manual look from Accounting.
    _CF_OPERATING_CURRENT_ASSETS = ["ACCOUNT RECEIVABLES", "INVENTORY", "PREPAIDS", "ACCRUED INCOME", "OTHER CURRENT ASSETS"]
    _CF_OPERATING_CURRENT_LIAB   = ["ACCOUNT PAYABLES", "TAX PAYABLES", "ACCRUED EXPENSES", "OTHER CURRENT LIABILITIES"]
    _CF_OPERATING_NONCURRENT_LIAB = ["ESTIMATED LIABILITIES FOR EMPLOYEES", "NON-CURRENT SALES RETURN ALLOWANCE"]
    _CF_INVESTING_NONCURRENT_ASSETS = ["PROPERTY, PLANT AND EQUIPMENT", "INTANGIBLE ASSET", "OTHER NON - CURRENT ASSETS"]
    _CF_FINANCING_CURRENT_LIAB    = ["SHORT TERM BORROWINGS", "CURRENT PORTION OF LONG TERM BORROWINGS", "CURRENT LEASE LIABILITIES"]
    _CF_FINANCING_NONCURRENT_LIAB = ["LTB-LOANS", "LONG-TERM LEASE LIABILITIES"]

    def _all_periods_ordered(self) -> list[dict]:
        sql = """
            SELECT period_name, period_year, period_num, adjustment_period_flag
            FROM gl_periods
            WHERE period_set_name = (
                SELECT period_set_name FROM gl_ledgers WHERE ledger_category_code='PRIMARY' AND object_type_code='L' AND ROWNUM=1)
            ORDER BY start_date
        """
        return self._query(sql)

    async def get_cash_flow_indirect(self, period_from: str, period_to: str) -> dict:
        """Indirect Cash Flow statement for the range period_from..period_to
        inclusive (both GL period names, e.g. "JAN-26".."JUN-26") — one
        column, covering the whole range as a single movement, the way an
        indirect CF statement is normally read (not one column per month)."""
        all_periods = await asyncio.to_thread(self._all_periods_ordered)
        names = [p["period_name"] for p in all_periods if p["adjustment_period_flag"] != "Y"]
        if period_from not in names or period_to not in names:
            return {"success": False, "error": "Selected period not found in the GL calendar."}
        i_from, i_to = names.index(period_from), names.index(period_to)
        if i_from > i_to:
            return {"success": False, "error": "Period From must not be after Period To."}
        if i_from == 0:
            return {"success": False, "error": "No prior period exists to use as the opening Balance Sheet snapshot — pick a later Period From."}
        range_periods = names[i_from:i_to + 1]
        opening_period = names[i_from - 1]

        bs, pl = await asyncio.gather(
            self.get_balance_sheet([opening_period, period_to], None),
            self.get_profit_and_loss([{"label": "Period", "periods": range_periods}]),
        )
        if not bs.get("success"):
            return bs

        def bs_values(section: str, label: str) -> list:
            row = next((r for r in bs.get(section, []) if r["label"] == label), None)
            return row["values"] if row else [0, 0]

        def bs_delta(section: str, label: str) -> float:
            v = bs_values(section, label)
            return v[1] - v[0]

        net_income = pl["profit_after_tax"][0]
        depreciation = next(
            (l["values"][0] for l in pl.get("expense_lines", []) if l["label"] == "DEPRECIATIONS & AMORTIZATION"), 0
        )

        operating_lines = [("Depreciation & Amortization (add back)", depreciation)]
        for label in self._CF_OPERATING_CURRENT_ASSETS:
            d = bs_delta("current_assets", label)
            operating_lines.append((f"(Increase) / Decrease in {label.title()}", -d))
        for label in self._CF_OPERATING_CURRENT_LIAB:
            d = bs_delta("current_liabilities", label)
            operating_lines.append((f"Increase / (Decrease) in {label.title()}", d))
        for label in self._CF_OPERATING_NONCURRENT_LIAB:
            d = bs_delta("noncurrent_liabilities", label)
            operating_lines.append((f"Increase / (Decrease) in {label.title()}", d))
        net_operating = net_income + sum(v for _, v in operating_lines)

        investing_lines = []
        for label in self._CF_INVESTING_NONCURRENT_ASSETS:
            d = bs_delta("noncurrent_assets", label)
            investing_lines.append((f"(Acquisition) / Disposal — {label.title()}", -d))
        net_investing = sum(v for _, v in investing_lines)

        financing_lines = []
        for label in self._CF_FINANCING_CURRENT_LIAB:
            d = bs_delta("current_liabilities", label)
            financing_lines.append((f"Increase / (Decrease) in {label.title()}", d))
        for label in self._CF_FINANCING_NONCURRENT_LIAB:
            d = bs_delta("noncurrent_liabilities", label)
            financing_lines.append((f"Increase / (Decrease) in {label.title()}", d))
        d_capital = bs_delta("equity", "CAPITAL STOCK")
        financing_lines.append(("Increase / (Decrease) in Capital Stock", d_capital))
        net_financing = sum(v for _, v in financing_lines)

        net_change_in_cash = net_operating + net_investing + net_financing
        cash_vals = bs_values("current_assets", "CASH & CASH EQUIVALENTS")
        cash_opening, cash_closing = cash_vals[0], cash_vals[1]
        reconciliation_diff = (cash_opening + net_change_in_cash) - cash_closing

        def _line(label, val):
            return {"label": label, "type": "line", "level": 1, "values": [val]}

        rows = [
            {"label": "OPERATING ACTIVITIES", "type": "header", "level": 0},
            _line("Net Profit After Tax", net_income),
            *[_line(l, v) for l, v in operating_lines],
            {"label": "Net Cash from Operating Activities", "type": "total", "level": 0, "values": [net_operating]},

            {"label": "INVESTING ACTIVITIES", "type": "header", "level": 0},
            *[_line(l, v) for l, v in investing_lines],
            {"label": "Net Cash from Investing Activities", "type": "total", "level": 0, "values": [net_investing]},

            {"label": "FINANCING ACTIVITIES", "type": "header", "level": 0},
            *[_line(l, v) for l, v in financing_lines],
            {"label": "Net Cash from Financing Activities", "type": "total", "level": 0, "values": [net_financing]},

            {"label": "NET INCREASE (DECREASE) IN CASH", "type": "total", "level": 0, "values": [net_change_in_cash]},
            {"label": "Cash & Cash Equivalents, Beginning of Period", "type": "line", "level": 0, "values": [cash_opening]},
            {"label": "Cash & Cash Equivalents, End of Period", "type": "total", "level": 0, "values": [cash_closing]},
        ]

        return {
            "success": True,
            "period_from": period_from, "period_to": period_to, "opening_period": opening_period,
            "columns": [f"{self.period_display_label(period_from)} – {self.period_display_label(period_to)}"],
            "rows": rows,
            "reconciliation_diff": [reconciliation_diff],
        }
