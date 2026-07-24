"""
Financial Statement Router
Route prefix : /api/v1/dashboard/accounting/financial-statement
Required role: accounting_staff OR admin

Balance Sheet / Profit & Loss reporting sourced live from Oracle EBS 12.2.8
GL_BALANCES — see app/services/financial_statement_service.py for the
account-mapping and balance-formula documentation.

Endpoints:
  GET  /periods                     — GL periods available for the period selectors
  GET  /balance-sheet               — line-item Balance Sheet, one column per period
  GET  /balance-sheet/export        — same, as .xlsx (format matches FS_CKD OTTO 2015-2026_sent.xlsx)
  GET  /balance-sheet-detail        — natural-account-level Balance Sheet drill-down
  GET  /balance-sheet-detail/export — same, as .xlsx
  GET  /profit-loss                 — line-item P&L, one column per fiscal year/YTD range
  GET  /profit-loss/export          — same, as .xlsx
  GET  /profit-loss-monthly         — MTD/YTD this year vs same period last year
  GET  /profit-loss-monthly/export  — same, as .xlsx
"""
import io
import json
from datetime import datetime
from typing import Optional

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.dependencies import require_role, CurrentUser, Roles
from app.services.financial_statement_service import FinancialStatementService

router = APIRouter()


@router.get("/periods")
async def get_periods(user: CurrentUser = Depends(require_role(Roles.ACCOUNTING))):
    """List GL periods for the primary ledger, with a has_activity flag so
    the frontend can default to the latest period with posted balances."""
    return await FinancialStatementService().get_periods()


@router.get("/balance-sheet")
async def get_balance_sheet(
    periods: str = Query(..., description="Comma-separated GL period names, e.g. DEC-24,DEC-25,JAN-26,FEB-26"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """Balance Sheet grouped into line items — one column per period."""
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    return await FinancialStatementService().get_balance_sheet(period_list)


@router.get("/balance-sheet-detail")
async def get_balance_sheet_detail(
    periods: str = Query(..., description="Comma-separated GL period names"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """Balance Sheet at natural-account granularity — drill-down view."""
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    return await FinancialStatementService().get_balance_sheet_detail(period_list)


@router.get("/profit-loss")
async def get_profit_and_loss(
    columns: str = Query(..., description='JSON list of {"label","periods":[...]} — one per fiscal year/YTD range'),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """P&L grouped into line items — one column per fiscal year / YTD range."""
    col_list = json.loads(columns)
    return await FinancialStatementService().get_profit_and_loss(col_list)


@router.get("/profit-loss-monthly")
async def get_profit_and_loss_monthly(
    period_this: str = Query(..., description="This year's MTD period, e.g. JUN-26"),
    ytd_this: str = Query(..., description="Comma-separated periods JAN-26,...,JUN-26"),
    period_last: str = Query(..., description="Same month last year, e.g. JUN-25"),
    ytd_last: str = Query(..., description="Comma-separated periods JAN-25,...,JUN-25"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """MTD/YTD comparison — this year's period vs the same period last year."""
    ytd_this_list = [p.strip() for p in ytd_this.split(",") if p.strip()]
    ytd_last_list = [p.strip() for p in ytd_last.split(",") if p.strip()]
    return await FinancialStatementService().get_profit_and_loss_monthly(
        period_this, ytd_this_list, period_last, ytd_last_list
    )


# ── Excel exports — layout mirrors FS_CKD OTTO 2015-2026_sent.xlsx ────────────
# (title block, dark-navy header row, indented hierarchical line items, bold
# light-blue total rows, accounting number format with parentheses for
# negatives) — that's the format management is used to seeing, per the user.

TITLE_FONT   = Font(bold=True, size=18)
SUB_FONT     = Font(bold=True, size=11)
HEADER_FONT  = Font(bold=True, size=10, color="FFFFFF")
HEADER_FILL  = PatternFill("solid", fgColor="1F4E78")
TOTAL_FONT   = Font(bold=True, size=10)
TOTAL_FILL   = PatternFill("solid", fgColor="D9E1F2")
SECTION_FONT = Font(bold=True, size=10)
LABEL_FONT   = Font(size=10)
CENTER       = Alignment(horizontal="center", vertical="center", wrap_text=True)
ACC_NUMFMT   = '_(* #,##0_);_(* (#,##0);_(* "-"??_);_(@_)'


def _title_block(ws, title2: str, date_label: str, last_col: int):
    ws.cell(row=1, column=1, value="PT CKD OTTO Pharmaceuticals").font = TITLE_FONT
    ws.cell(row=2, column=1, value=title2).font = TITLE_FONT
    ws.cell(row=3, column=1, value=date_label).font = SUB_FONT
    ws.cell(row=4, column=1, value="Amount in IDR").font = SUB_FONT


def _header_row(ws, row: int, columns: list, last_col: int):
    c = ws.cell(row=row, column=1, value="ACCOUNT")
    c.font, c.fill, c.alignment = HEADER_FONT, HEADER_FILL, CENTER
    for i, label in enumerate(columns, start=2):
        c = ws.cell(row=row, column=i, value=label)
        c.font, c.fill, c.alignment = HEADER_FONT, HEADER_FILL, CENTER
    for c_idx in range(1, last_col + 1):
        ws.cell(row=row, column=c_idx).fill = HEADER_FILL


def _write_row(ws, row: int, label: str, values: list, level: int = 0, bold: bool = False, fill=None):
    lc = ws.cell(row=row, column=1, value=label)
    lc.font = TOTAL_FONT if bold else LABEL_FONT
    lc.alignment = Alignment(indent=level)
    if fill:
        lc.fill = fill
    for i, v in enumerate(values, start=2):
        vc = ws.cell(row=row, column=i, value=v)
        vc.number_format = ACC_NUMFMT
        vc.font = TOTAL_FONT if bold else LABEL_FONT
        if fill:
            vc.fill = fill


def _autosize(ws, ncols: int, first_width: int = 34, other_width: int = 15):
    from openpyxl.utils import get_column_letter
    ws.column_dimensions["A"].width = first_width
    for i in range(2, ncols + 2):
        ws.column_dimensions[get_column_letter(i)].width = other_width
    ws.freeze_panes = "B7"


def _stream(wb, fname: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


def _bs_sections(data: dict) -> list:
    """(section_label, line_rows, (total_label, total_values), indent_level)"""
    return [
        ("ASSETS", None, None, 0),
        ("CURRENT ASSETS", data["current_assets"], ("TOTAL CURRENT ASSETS", data["total_current_assets"]), 1),
        ("NON CURRENT ASSET", data["noncurrent_assets"], ("TOTAL NON CURRENT ASSETS", data["total_noncurrent_assets"]), 1),
        (None, None, ("TOTAL ASSETS", data["total_assets"]), 0),
        ("LIABILITIES", None, None, 0),
        ("CURRENT LIABILITIES", data["current_liabilities"], ("TOTAL CURRENT LIABILITIES", data["total_current_liabilities"]), 1),
        ("NONCURRENT LIABILITIES", data["noncurrent_liabilities"], ("TOTAL NONCURRENT LIABILITIES", data["total_noncurrent_liabilities"]), 1),
        (None, None, ("TOTAL  LIABILITIES", data["total_liabilities"]), 0),
        ("EQUITY", data["equity"], ("TOTAL  EQUITY", data["total_equity"]), 0),
        (None, None, ("TOTAL  LIABILITIES AND EQUITY", data["total_liabilities_and_equity"]), 0),
    ]


def _build_balance_sheet_xlsx(data: dict, column_labels: list, as_of_label: str, detail: bool) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Balance Sheet Detail" if detail else "Balance Sheet"
    ncols = len(column_labels)
    _title_block(ws, "Balance Sheet Detail" if detail else "Balance Sheet", as_of_label, ncols + 1)
    _header_row(ws, 6, column_labels, ncols + 1)

    row = 7
    if detail:
        by_type = {"A": [], "L": [], "O": []}
        for a in data["accounts"]:
            by_type.setdefault(a["account_type"], []).append(a)
        for section_label, key in [("ASSETS", "A"), ("LIABILITIES", "L"), ("EQUITY", "O")]:
            _write_row(ws, row, section_label, [], level=0, bold=True)
            row += 1
            for acc in by_type.get(key, []):
                _write_row(ws, row, f"{acc['account_code']} — {acc['account_desc'] or acc['line_item']}", acc["values"], level=1)
                row += 1
            row += 1
    else:
        for section_label, rows_, total_, level in _bs_sections(data):
            if section_label:
                _write_row(ws, row, section_label, [], level=level, bold=True)
                row += 1
            if rows_:
                for line in rows_:
                    _write_row(ws, row, line["label"], line["values"], level=level + 1)
                    row += 1
            if total_:
                _write_row(ws, row, total_[0], total_[1], level=level, bold=True, fill=TOTAL_FILL)
                row += 1

    _autosize(ws, ncols)
    fname = f"Balance_Sheet{'_Detail' if detail else ''}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return _stream(wb, fname)


def _pl_sections(data: dict) -> list:
    return [
        ("NET SALES", data["sales_lines"] + data["contra_lines"], ("TOTAL NET SALES", data["total_net_sales"])),
        ("COGS", data["cogs_lines"], ("TOTAL COGS", data["total_cogs"])),
        (None, None, ("GROSS PROFIT", data["gross_profit"])),
        ("EXPENSES", data["expense_lines"], ("TOTAL EXPENSES", data["total_expenses"])),
        ("OTHER INCOME / EXPENSES", data["other_lines"], ("TOTAL OTHER INCOME (EXPENSES)", data["total_other"])),
        (None, None, ("PROFIT (LOSS) BEFORE TAX", data["profit_before_tax"])),
        ("INCOME TAX", data["tax_lines"], ("TOTAL INCOME TAX BENEFIT (EXPENSE)", data["total_tax"])),
        (None, None, ("PROFIT (LOSS) AFTER TAX", data["profit_after_tax"])),
        (None, [{"label": "OTHER COMPREHENSIVE INCOME", "values": data["oci"]}],
         ("TOTAL COMPREHENSIVE INCOME (LOSS) FOR THE YEAR", data["total_comprehensive"])),
    ]


def _build_pl_xlsx(data: dict, title2: str, date_label: str, sheet_title: str) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    column_labels = data["columns"]
    ncols = len(column_labels)
    _title_block(ws, title2, date_label, ncols + 1)
    _header_row(ws, 6, column_labels, ncols + 1)

    row = 7
    for section_label, rows_, total_ in _pl_sections(data):
        if section_label:
            _write_row(ws, row, section_label, [], level=0, bold=True)
            row += 1
        if rows_:
            for line in rows_:
                _write_row(ws, row, line["label"], line["values"], level=1)
                row += 1
        if total_:
            _write_row(ws, row, total_[0], total_[1], level=0, bold=True, fill=TOTAL_FILL)
            row += 1
        row += 1

    _autosize(ws, ncols)
    fname = f"{sheet_title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return _stream(wb, fname)


@router.get("/balance-sheet/export")
async def export_balance_sheet(
    periods: str = Query(...),
    as_of_label: str = Query("", description="Display label for the report date line, e.g. 'June 30, 2026'"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    data = await FinancialStatementService().get_balance_sheet(period_list)
    labels = [FinancialStatementService.period_display_label(p) for p in period_list]
    return _build_balance_sheet_xlsx(data, labels, as_of_label or labels[-1], detail=False)


@router.get("/balance-sheet-detail/export")
async def export_balance_sheet_detail(
    periods: str = Query(...),
    as_of_label: str = Query(""),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    data = await FinancialStatementService().get_balance_sheet_detail(period_list)
    labels = [FinancialStatementService.period_display_label(p) for p in period_list]
    return _build_balance_sheet_xlsx(data, labels, as_of_label or labels[-1], detail=True)


@router.get("/profit-loss/export")
async def export_profit_and_loss(
    columns: str = Query(...),
    date_label: str = Query(""),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    col_list = json.loads(columns)
    data = await FinancialStatementService().get_profit_and_loss(col_list)
    return _build_pl_xlsx(data, "Profit or Loss", date_label or datetime.now().strftime("%B %d, %Y"), "Profit or Loss")


@router.get("/profit-loss-monthly/export")
async def export_profit_and_loss_monthly(
    period_this: str = Query(...),
    ytd_this: str = Query(...),
    period_last: str = Query(...),
    ytd_last: str = Query(...),
    date_label: str = Query(""),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    ytd_this_list = [p.strip() for p in ytd_this.split(",") if p.strip()]
    ytd_last_list = [p.strip() for p in ytd_last.split(",") if p.strip()]
    data = await FinancialStatementService().get_profit_and_loss_monthly(
        period_this, ytd_this_list, period_last, ytd_last_list
    )
    label = date_label or FinancialStatementService.period_display_label(period_this)
    return _build_pl_xlsx(data, "Profit or Loss", label, "PL Monthly")
