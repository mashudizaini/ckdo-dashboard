"""
Financial Statement — Excel Upload Source
─────────────────────────────────────────
Alternative to the live Oracle EBS GL_BALANCES query
(financial_statement_service.py), for the transition period where some
reports are still produced manually in Excel. Parses the same 3 sheets the
whole Financial Statement module was originally modeled after —
sumber/FS_CKD OTTO 2015-2026_sent.xlsx — and stores the result as JSON,
one row per report_type, so the API layer can serve either source through
the same response shape the frontend already consumes.

Sheet -> report_type:
  "Balance sheet"    -> balance_sheet
  "Profit or loss"   -> profit_loss       (annual, FY columns)
  "PL_monthly"       -> profit_loss_monthly (single MTD/YTD this-vs-last-year snapshot)

Label-matching notes (verified against the actual reference file — NOT
assumed):
  - Balance Sheet's line-item labels match the Oracle-mode bucket labels
    (BS_ASSET_CURRENT etc.) exactly, so those fixed buckets are reused for
    ordering/validation.
  - Profit or loss's NET SALES/COGS breakdown is per-customer in the manual
    file vs. per-channel in Oracle-mode — and EXPENSES also isn't a clean
    1:1 match (e.g. the file has "STORAGE" where Oracle-mode's fixed list
    has "CONFERENCE & CONVENTION"). Rather than force either sheet's lines
    into Oracle's bucket labels (which would silently misattribute rows),
    every section's line items are kept exactly as found in the file, in
    file order — only the section header / TOTAL row labels are matched
    literally (verified 1:1 against the file), since those drive the
    growth-rate chart and the table's bold TOTAL rows.
  - PL_monthly uses its own distinct TOTAL-row wording (e.g. "TOTAL INCOME
    TAX", "NET PROFIT (LOSS)") — different from both Balance Sheet's and
    the annual Profit or loss sheet's TOTAL labels — matching the labels
    ProfitLossMonthlyPanel already renders in the frontend.
"""
import io
import re
from datetime import datetime

import openpyxl

from app.services.financial_statement_service import (
    BS_ASSET_CURRENT, BS_ASSET_NONCURRENT, BS_LIAB_CURRENT, BS_LIAB_NONCURRENT, BS_EQUITY_ORDER,
)

_MONTH_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b", re.I)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).upper()


# Known typo/spacing variant -> canonical label, found in the actual
# reference file (not a hypothetical).
_ALIASES = {
    "DEFFERED TAX INCOME ( EXPENSE)": "DEFERRED TAX INCOME (EXPENSE)",
}


def _num(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sheet(wb, name: str):
    for s in wb.sheetnames:
        if s.strip().lower() == name.lower():
            return wb[s]
    raise ValueError(f"Sheet '{name}' tidak ditemukan di file — sheet yang ada: {', '.join(wb.sheetnames)}")


def _row_label(ws, row: int, max_col: int = 6):
    for c in range(1, max_col + 1):
        v = ws.cell(row=row, column=c).value
        if isinstance(v, str) and v.strip():
            label = _norm(v)
            return _ALIASES.get(label, label)
    return None


def _find_row(ws, label: str, max_row: int, start_row: int = 1) -> int | None:
    target = _norm(label)
    for r in range(start_row, max_row + 1):
        if _row_label(ws, r) == target:
            return r
    return None


def _lines_between(ws, header_row: int, total_row: int, value_cols: list[int]) -> list[dict]:
    """Every non-empty labeled row strictly between a section header and
    its TOTAL row, kept in file order with the file's own label — see
    module docstring for why this isn't matched against Oracle's bucket
    labels."""
    lines = []
    for r in range(header_row + 1, total_row):
        label = _row_label(ws, r)
        if not label:
            continue
        values = [_num(ws.cell(row=r, column=c).value) for c in value_cols]
        if all(v == 0 for v in values):
            continue
        lines.append({"label": label, "values": values})
    return lines


def _row_values(ws, row: int, value_cols: list[int]) -> list[float]:
    return [_num(ws.cell(row=row, column=c).value) for c in value_cols]


# ── Balance Sheet ────────────────────────────────────────────────────────

_BS_TOTAL_LABELS = {
    "current_assets":       "TOTAL CURRENT ASSETS",
    "noncurrent_assets":    "TOTAL NON CURRENT ASSETS",
    "assets":               "TOTAL ASSETS",
    "current_liabilities":  "TOTAL CURRENT LIABILITIES",
    "noncurrent_liabilities": "TOTAL NONCURRENT LIABILITIES",
    "liabilities":          "TOTAL LIABILITIES",
    "equity":               "TOTAL EQUITY",
    "liabilities_and_equity": "TOTAL LIABILITIES AND EQUITY",
}


def parse_balance_sheet_excel(content: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = _sheet(wb, "Balance sheet")

    year_cols: dict[int, int] = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=6, column=c).value
        if isinstance(v, str) and re.match(r"^FY\s*\d{4}$", v.strip(), re.I):
            year_cols[int(re.search(r"\d{4}", v).group())] = c
    if not year_cols:
        raise ValueError("Header tahun (\"FY YYYY\") tidak ditemukan di baris 6 sheet 'Balance sheet'.")
    years = sorted(year_cols)
    value_cols = [year_cols[y] for y in years]

    as_of_label = None
    for r in range(1, 6):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and _MONTH_RE.search(v):
            as_of_label = v.strip()
            break

    label_values: dict[str, list[float]] = {}
    for r in range(7, ws.max_row + 1):
        label = _row_label(ws, r)
        if not label:
            continue
        values = _row_values(ws, r, value_cols)
        if all(v == 0 for v in values):
            continue
        label_values[label] = values

    zeros = [0.0] * len(years)

    def section(labels):
        return [{"label": l, "values": label_values.get(_norm(l), zeros)} for l in labels]

    def total(key, computed):
        return label_values.get(_norm(_BS_TOTAL_LABELS[key]), computed)

    current_assets = section(BS_ASSET_CURRENT)
    noncurrent_assets = section(BS_ASSET_NONCURRENT)
    current_liab = section(BS_LIAB_CURRENT)
    noncurrent_liab = section(BS_LIAB_NONCURRENT)
    equity = section(BS_EQUITY_ORDER)

    def sum_rows(rows_):
        return [sum(row["values"][i] for row in rows_) for i in range(len(years))]

    total_current_assets = total("current_assets", sum_rows(current_assets))
    total_noncurrent_assets = total("noncurrent_assets", sum_rows(noncurrent_assets))
    total_assets = total("assets", [a + b for a, b in zip(total_current_assets, total_noncurrent_assets)])
    total_current_liab = total("current_liabilities", sum_rows(current_liab))
    total_noncurrent_liab = total("noncurrent_liabilities", sum_rows(noncurrent_liab))
    total_liabilities = total("liabilities", [a + b for a, b in zip(total_current_liab, total_noncurrent_liab)])
    total_equity = total("equity", sum_rows(equity))
    total_liab_equity = total("liabilities_and_equity", [a + b for a, b in zip(total_liabilities, total_equity)])

    known = {_norm(l) for l in (BS_ASSET_CURRENT + BS_ASSET_NONCURRENT + BS_LIAB_CURRENT
                                 + BS_LIAB_NONCURRENT + BS_EQUITY_ORDER)} | {_norm(v) for v in _BS_TOTAL_LABELS.values()}
    unmapped = sorted(l for l in label_values if l not in known)

    return {
        "years": years, "as_of_label": as_of_label,
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


# ── Profit or Loss (annual) ──────────────────────────────────────────────

def _parse_pl_sheet(ws, value_cols: list[int], totals: dict) -> dict:
    """Shared section-scanner for the annual 'Profit or loss' sheet and the
    'PL_monthly' sheet — same section structure, different TOTAL-row
    wording (passed in via `totals`) and different value columns."""
    max_row = ws.max_row

    def find(label):
        r = _find_row(ws, label, max_row)
        if r is None:
            raise ValueError(f"Baris '{label}' tidak ditemukan di sheet.")
        return r

    r_net_sales = find("NET SALES")
    r_total_net_sales = find(totals["total_net_sales"])
    r_cogs = find("COGS")
    r_total_cogs = find(totals["total_cogs"])
    r_gross_profit = find(totals["gross_profit"])
    r_expenses = find("EXPENSES")
    r_total_expenses = find(totals["total_expenses"])
    r_other = find("OTHER INCOME / EXPENSES")
    r_total_other = find(totals["total_other"])
    r_pbt = find(totals["profit_before_tax"])
    r_tax = find("INCOME TAX")
    r_total_tax = find(totals["total_tax"])
    r_pat = find(totals["profit_after_tax"])
    r_oci = find(totals["oci"])
    r_total_comprehensive = find(totals["total_comprehensive"])

    sales_lines = _lines_between(ws, r_net_sales, r_total_net_sales, value_cols)
    cogs_lines = _lines_between(ws, r_cogs, r_total_cogs, value_cols)
    expense_lines = _lines_between(ws, r_expenses, r_total_expenses, value_cols)
    other_lines = _lines_between(ws, r_other, r_total_other, value_cols)
    tax_lines = _lines_between(ws, r_tax, r_total_tax, value_cols)

    return {
        "sales_lines": sales_lines, "contra_lines": [], "total_net_sales": _row_values(ws, r_total_net_sales, value_cols),
        "cogs_lines": cogs_lines, "total_cogs": _row_values(ws, r_total_cogs, value_cols),
        "gross_profit": _row_values(ws, r_gross_profit, value_cols),
        "expense_lines": expense_lines, "total_expenses": _row_values(ws, r_total_expenses, value_cols),
        "other_lines": other_lines, "total_other": _row_values(ws, r_total_other, value_cols),
        "profit_before_tax": _row_values(ws, r_pbt, value_cols),
        "tax_lines": tax_lines, "total_tax": _row_values(ws, r_total_tax, value_cols),
        "profit_after_tax": _row_values(ws, r_pat, value_cols),
        "oci": _row_values(ws, r_oci, value_cols),
        "total_comprehensive": _row_values(ws, r_total_comprehensive, value_cols),
        "unmapped_accounts": [],
    }


_PL_ANNUAL_TOTALS = {
    "total_net_sales": "TOTAL NET SALES", "total_cogs": "TOTAL COGS", "gross_profit": "GROSS PROFIT",
    "total_expenses": "TOTAL EXPENSES", "total_other": "TOTAL OTHER INCOME (EXPENSES)",
    "profit_before_tax": "PROFIT (LOSS) BEFORE TAX", "total_tax": "TOTAL INCOME TAX BENEFIT (EXPENSE)",
    "profit_after_tax": "PROFIT (LOSS) AFTER TAX", "oci": "OTHER COMPREHENSIVE INCOME",
    "total_comprehensive": "TOTAL COMPREHENSIVE INCOME (LOSS) FOR THE YEAR",
}

_PL_MONTHLY_TOTALS = {
    "total_net_sales": "TOTAL NET SALES", "total_cogs": "TOTAL COGS", "gross_profit": "GROSS PROFIT",
    "total_expenses": "TOTAL EXPENSES", "total_other": "TOTAL OTHER INCOME (EXPENSE)",
    "profit_before_tax": "PROFIT (LOSS) BEFORE INCOME TAX", "total_tax": "TOTAL INCOME TAX",
    "profit_after_tax": "NET PROFIT (LOSS)", "oci": "OTHER COMPREHENSIVE INCOME (LOSS)",
    "total_comprehensive": "TOTAL COMPREHENSIVE INCOME (LOSS) FOR THE YEAR",
}


def parse_profit_loss_excel(content: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = _sheet(wb, "Profit or loss")

    year_cols: dict[int, int] = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=6, column=c).value
        if isinstance(v, str) and re.match(r"^FY\s*\d{4}$", v.strip(), re.I):
            year_cols[int(re.search(r"\d{4}", v).group())] = c
    if not year_cols:
        raise ValueError("Header tahun (\"FY YYYY\") tidak ditemukan di baris 6 sheet 'Profit or loss'.")
    years = sorted(year_cols)
    value_cols = [year_cols[y] for y in years]

    data = _parse_pl_sheet(ws, value_cols, _PL_ANNUAL_TOTALS)
    data["years"] = years
    data["columns"] = [f"FY {y}" for y in years]
    return data


# ── Profit or Loss Monthly ───────────────────────────────────────────────

def parse_profit_loss_monthly_excel(content: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = _sheet(wb, "PL_monthly")

    # Row 7: date labels spanning each year's MTD/YTD pair (e.g. "June 30,
    # 2025" over cols G:H, "June 30, 2026" over cols I:J). Row 8 confirms
    # the MTD/YTD sub-labels at those same 4 columns.
    date_cells = [(c, ws.cell(row=7, column=c).value) for c in range(1, ws.max_column + 1)
                  if isinstance(ws.cell(row=7, column=c).value, str) and ws.cell(row=7, column=c).value.strip()]
    if len(date_cells) < 2:
        raise ValueError("Header tanggal (baris 7) tidak ditemukan di sheet 'PL_monthly'.")
    (col_last, date_last), (col_this, date_this) = date_cells[0], date_cells[1]
    value_cols = [col_last, col_last + 1, col_this, col_this + 1]  # MTD Last, YTD Last, MTD This, YTD This

    data = _parse_pl_sheet(ws, value_cols, _PL_MONTHLY_TOTALS)
    data["date_last"] = date_last.strip()
    data["date_this"] = date_this.strip()
    data["columns"] = ["MTD Last Year", "YTD Last Year", "MTD This Year", "YTD This Year"]
    return data


_PARSERS = {
    "balance_sheet": parse_balance_sheet_excel,
    "profit_loss": parse_profit_loss_excel,
    "profit_loss_monthly": parse_profit_loss_monthly_excel,
}


class FinancialStatementUploadService:

    async def save_upload(self, db, report_type: str, content: bytes, filename: str, username: str) -> dict:
        from app.models.financial_statement_upload import FinancialStatementUpload
        from sqlalchemy import select

        parser = _PARSERS.get(report_type)
        if not parser:
            return {"success": False, "error": f"Tipe laporan tidak dikenal: {report_type}"}
        try:
            parsed = parser(content)
        except Exception as e:
            return {"success": False, "error": str(e)}

        result = await db.execute(select(FinancialStatementUpload).where(FinancialStatementUpload.report_type == report_type))
        row = result.scalar_one_or_none()
        if row:
            row.content = parsed
            row.original_filename = filename
            row.uploaded_by = username
            row.uploaded_at = datetime.utcnow()
        else:
            row = FinancialStatementUpload(
                report_type=report_type, content=parsed,
                original_filename=filename, uploaded_by=username,
            )
            db.add(row)
        await db.commit()
        return {"success": True, "data": parsed, "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None}

    async def get_upload(self, db, report_type: str) -> dict | None:
        from app.models.financial_statement_upload import FinancialStatementUpload
        from sqlalchemy import select

        result = await db.execute(select(FinancialStatementUpload).where(FinancialStatementUpload.report_type == report_type))
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "content": row.content,
            "original_filename": row.original_filename,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        }
