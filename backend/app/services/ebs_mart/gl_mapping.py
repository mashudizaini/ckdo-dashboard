"""
Natural account -> financial statement line, for the GL marts (phase 5).

Not a second mapping: every rule here is the Financial Statement module's own
(app/services/financial_statement_service.py) — its PL_*/BS_* maps, its
number-range dispatch and its signs, which that module validated to the cent
against the finance team's reference file (FS_CKD OTTO 2015-2026). The
blueprint's open decision "siapa pemilik tabel mapping akun ke pos laba rugi"
is answered by that: the mapping lives in that module, and meta.gl_account_map
is regenerated from it on every GL load, so a change there reaches chat
without anyone editing two places.
"""
from app.services.financial_statement_service import (
    BS_ASSET_CURRENT, BS_ASSET_MAP, BS_EQUITY_MAP, BS_LIAB_CURRENT, BS_LIABILITY_MAP,
    PL_COGS_MAP, PL_EXPENSE_DISPLAY_ORDER, PL_EXPENSE_MAP, PL_OTHER_MAP, PL_SALES_MAP, PL_TAX_MAP, _bucket,
)

# P&L sections in statement order. sign turns GL's (dr - cr) into the
# statement's reading: revenue and other income positive, costs positive as
# costs — exactly _pl_bucket_amounts().
PL_SECTIONS = [
    ("SALES", 1), ("COGS", 2), ("OPERATING EXPENSES", 3), ("OTHER INCOME/EXPENSE", 4),
    ("TAX", 5), ("OTHER COMPREHENSIVE INCOME", 6),
]


def _order(label: str, maps: list) -> int:
    for i, (l, _, _) in enumerate(maps):
        if l == label:
            return i + 1
    return 99


def classify(code: str, account_type: str | None) -> dict:
    """{statement, section, section_order, line, line_order, sign} for one
    natural account. statement is 'PL', 'BS' or None (outside both)."""
    code = code or ""
    if code.startswith(("411", "421", "431")):
        line = _bucket(code, PL_SALES_MAP)
        return _pl("SALES", line, _order(line, PL_SALES_MAP), -1)
    if code.startswith(("511", "521", "531", "541", "542")):
        line = _bucket(code, PL_COGS_MAP)
        return _pl("COGS", line, _order(line, PL_COGS_MAP), 1)
    if code.startswith("61"):
        line = _bucket(code, PL_EXPENSE_MAP)
        order = PL_EXPENSE_DISPLAY_ORDER.index(line) + 1 if line in PL_EXPENSE_DISPLAY_ORDER else 99
        return _pl("OPERATING EXPENSES", line, order, 1)
    if code.startswith(("711", "731")):
        line = _bucket(code, PL_OTHER_MAP)
        return _pl("OTHER INCOME/EXPENSE", line, _order(line, PL_OTHER_MAP), -1)
    if code == "811116":
        return _pl("OTHER COMPREHENSIVE INCOME", "OTHER COMPREHENSIVE INCOME", 1, -1)
    if code.startswith("811"):
        line = _bucket(code, PL_TAX_MAP)
        return _pl("TAX", line, _order(line, PL_TAX_MAP), -1)

    # Balance sheet: by account_type, as get_balance_sheet() does. Assets are
    # debit-normal; liabilities and equity are shown credit-normal.
    if account_type == "A":
        line = _bucket(code, BS_ASSET_MAP)
        section = "CURRENT ASSETS" if line in BS_ASSET_CURRENT else "NON CURRENT ASSETS"
        return _bs(section, line, _order(line, BS_ASSET_MAP), 1)
    if account_type == "L":
        line = _bucket(code, BS_LIABILITY_MAP)
        section = "CURRENT LIABILITIES" if line in BS_LIAB_CURRENT else "NONCURRENT LIABILITIES"
        return _bs(section, line, _order(line, BS_LIABILITY_MAP), -1)
    if account_type == "O":
        line = _bucket(code, BS_EQUITY_MAP)
        return _bs("EQUITY", line, _order(line, BS_EQUITY_MAP), -1)
    return {"statement": None, "section": None, "section_order": None, "line": None, "line_order": None, "sign": 1}


def _pl(section, line, line_order, sign):
    section_order = dict(PL_SECTIONS)[section]
    if line == "UNMAPPED":
        # Excluded from every P&L total, as the Financial Statement report does.
        section, section_order = "UNMAPPED", 9
    return {"statement": "PL", "section": section, "section_order": section_order, "line": line,
            "line_order": line_order, "sign": sign}


def _bs(section, line, line_order, sign):
    order = {"CURRENT ASSETS": 1, "NON CURRENT ASSETS": 2, "CURRENT LIABILITIES": 3,
             "NONCURRENT LIABILITIES": 4, "EQUITY": 5}[section]
    return {"statement": "BS", "section": section, "section_order": order, "line": line,
            "line_order": line_order, "sign": sign}
