"""
PAC Dashboard Router
Route prefix : /api/v1/dashboard/pac
Required role: pac_staff OR admin

Endpoints:
  GET  /summary
  GET  /budget-usage              — Actual vs Budget per period/cost-center
  GET  /lov/ledgers               — GL ledger LOV
  GET  /business-plans            — List business plan documents
  GET  /business-plans/{id}       — Get single document
  POST /business-plans            — Create / update document (upsert)
  DELETE /business-plans/{id}     — Delete document
"""
import asyncio
import io
import json
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from app.dependencies import require_role, CurrentUser, Roles
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pac_service import PACService
from app.services.business_plan_service import BusinessPlanService
from app.services.business_plan_setup_service import BusinessPlanSetupService
from app.services.sales_plan_service import SalesPlanService
from app.services.purchase_plan_service import PurchasePlanService
from app.services.personnel_plan_service import PersonnelPlanService
from app.services.manufacture_plan_service import ManufacturePlanService
from app.services.investment_plan_service import InvestmentPlanService
from app.services.opex_plan_service import OpexPlanService
from app.services.ai_service import AIService
from app.services import exchange_rate_service

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.PAC))):
    return {"module": "pac", "status": "ready"}


@router.get("/budget-usage")
async def get_budget_usage(
    year:         Optional[int] = Query(None),
    month:        Optional[int] = Query(None),
    cost_center:  Optional[str] = Query(None),
    account_type: Optional[str] = Query(None),
    ledger_id:    Optional[int] = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Actual vs Business Plan (Budget) per cost center per GL period."""
    filters = dict(year=year, month=month, cost_center=cost_center,
                   account_type=account_type, ledger_id=ledger_id)
    return await PACService().get_budget_usage(filters)


@router.get("/lov/ledgers")
async def get_ledgers(user: CurrentUser = Depends(require_role(Roles.PAC))):
    return await PACService().get_ledgers()


# ── Business Plan ─────────────────────────────────────────────────────────────

class BusinessPlanPayload(BaseModel):
    id:          Optional[int]  = None
    doc_type:    str            = "strategy_plan"   # managerial_obj | strategy_plan
    plan_year:   int
    department:  Optional[str]  = "ALL"
    team_code:   Optional[str]  = ""
    team_name:   Optional[str]  = ""
    plan_role:   Optional[str]  = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/business-plans")
async def list_business_plans(
    plan_year:  Optional[int] = Query(None),
    doc_type:   Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().list_plans(db, plan_year, doc_type, department)


@router.get("/business-plans/{plan_id}")
async def get_business_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().get_plan(db, plan_id)


@router.post("/business-plans")
async def upsert_business_plan(
    body: BusinessPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().upsert_plan(db, body.model_dump(), user.username)


@router.post("/business-plans/upload")
async def upload_business_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import a Strategy & Action Plan from an Excel file matching the
    "Strategy_Action Plan - Mashudi.xlsx" template."""
    content = await file.read()
    return await BusinessPlanService().import_excel(db, content, plan_year, user.username)


@router.delete("/business-plans/{plan_id}")
async def delete_business_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().delete_plan(db, plan_id)


# ── Business Plan Setup (Schedule / Guideline / Outlook) ───────────────────────

class SetupPayload(BaseModel):
    id:           Optional[int]  = None
    setup_module: str            = "schedule"   # schedule | guideline | outlook
    plan_year:    int
    content:      dict           = {}
    status:       Optional[str]  = "draft"


@router.get("/setup-modules")
async def list_setup_modules(
    setup_module: Optional[str] = Query(None),
    plan_year:    Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List setup modules (schedule, guideline, outlook) filtered by year/module."""
    return await BusinessPlanSetupService().list_setup(db, setup_module, plan_year)


@router.get("/setup-modules/{setup_id}")
async def get_setup_module(
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single setup module document."""
    return await BusinessPlanSetupService().get_setup(db, setup_id)


@router.post("/setup-modules")
async def upsert_setup_module(
    body: SetupPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update setup module document."""
    return await BusinessPlanSetupService().upsert_setup(db, body.model_dump(), user.username)


@router.delete("/setup-modules/{setup_id}")
async def delete_setup_module(
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete setup module document."""
    return await BusinessPlanSetupService().delete_setup(db, setup_id)


class GenerateOutlookRequest(BaseModel):
    year: int
    context: Optional[str] = None


@router.post("/setup-modules/generate-outlook")
async def generate_outlook(
    body: GenerateOutlookRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """
    Generate Business Plan Outlook content using AI based on the selected year.
    Returns structured outlook data that can be saved via upsert.
    """
    ai = AIService()
    prompt = f"""Generate a comprehensive Business Plan Outlook for PT CKD OTTO Pharmaceuticals for year {body.year}.
{f'Additional context: {body.context}' if body.context else ''}

Return ONLY valid JSON with this exact structure:
{{
  "global_economic": {{
    "title": "I. Global Economic Outlook",
    "items": [
      {{"label": "Global GDP Forecast", "value": "..."}},
      {{"label": "Key Factor 1", "value": "..."}},
      {{"label": "Key Factor 2", "value": "..."}},
      {{"label": "Fed Interest Rate", "value": "..."}},
      {{"label": "Global Inflation", "value": "..."}}
    ]
  }},
  "indonesia_economic": {{
    "title": "II. Indonesia Economic Outlook",
    "items": [
      {{"label": "GDP Forecast", "value": "..."}},
      {{"label": "Inflation", "value": "..."}},
      {{"label": "Interest Rate", "value": "..."}},
      {{"label": "Exchange Rate", "value": "..."}},
      {{"label": "Government Focus", "value": "..."}}
    ]
  }},
  "pharmaceutical": {{
    "title": "III. Pharmaceutical Industry",
    "items": [
      {{"label": "Global Market", "value": "..."}},
      {{"label": "Indonesia Market", "value": "..."}},
      {{"label": "Oncology", "value": "..."}},
      {{"label": "CKD OTTO Strategy", "value": "..."}}
    ]
  }}
}}

Make it realistic for {body.year} with specific numbers and trends. Keep values concise but informative."""

    try:
        response = await ai.generate_chat_completion([
            {"role": "system", "content": "You are a business analyst. Return only valid JSON, no markdown, no explanations."},
            {"role": "user", "content": prompt}
        ])
        content = json.loads(response)
        return {"success": True, "data": {"setup_module": "outlook", "plan_year": body.year, "content": content, "status": "draft"}}
    except Exception as e:
        return {"success": False, "error": f"Failed to generate outlook: {str(e)}", "data": None}


# ── Sales Plan ────────────────────────────────────────────────────────────────

class SalesPlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    team_code:   str            = ""
    team_name:   str            = ""
    plan_type:   str            = "value"   # value | unit
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/sales-plans")
async def list_sales_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    team_code:  Optional[str] = Query(None),
    plan_type:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List sales plans filtered by year/department/team/type."""
    return await SalesPlanService().list_sales_plans(db, plan_year, department, team_code, plan_type)


@router.get("/sales-plans/gross-sales-report")
async def export_gross_sales_report(
    plan_year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Export the Gross Sales Report — same column layout and calculations
    (Sales Quantity = Sales Amount / Price) as sumber/output_grossales2026.xlsx,
    built entirely from Sales Plan Data (Value) rows for the given year.
    Registered before /sales-plans/{plan_id} — otherwise Starlette's string
    path matching would swallow this literal route as plan_id="gross-sales-report"
    and only fail with 422 at the int-conversion step."""
    result = await SalesPlanService().get_gross_sales_report_data(db, plan_year)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "Failed to load Sales Plan Data")
    try:
        return _build_gross_sales_report_xlsx(result["data"], plan_year)
    except Exception as e:
        raise HTTPException(500, f"Excel generation failed: {e}")


@router.get("/sales-plans/sales-summary")
async def export_sales_summary(
    plan_year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Export the Sales Summary — mirrors V5.Sales Estimation2026.xlsx's
    "Summary" sheet (business-unit breakdown with formulas referencing a raw
    Gross Sales data sheet in the same workbook), built entirely from Sales
    Plan Data for the given year. Registered before /sales-plans/{plan_id}
    for the same string-vs-int path matching reason as gross-sales-report."""
    result = await SalesPlanService().get_gross_sales_report_data(db, plan_year)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "Failed to load Sales Plan Data")
    try:
        return _build_sales_summary_xlsx(result["data"], plan_year)
    except Exception as e:
        raise HTTPException(500, f"Excel generation failed: {e}")


@router.get("/sales-plans/{plan_id}")
async def get_sales_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single sales plan."""
    return await SalesPlanService().get_sales_plan(db, plan_id)


@router.post("/sales-plans")
async def upsert_sales_plan(
    body: SalesPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update sales plan."""
    return await SalesPlanService().upsert_sales_plan(db, body.model_dump(), user.username)


@router.delete("/sales-plans/{plan_id}")
async def delete_sales_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete sales plan."""
    return await SalesPlanService().delete_sales_plan(db, plan_id)


@router.post("/sales-plans/{plan_id}/export")
async def export_sales_plan_excel(
    plan_id: int,
    plan_type: str = Query(..., description="value atau unit"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Export Sales Plan ke Excel (S1 Value atau S2 Unit)."""
    return await SalesPlanService().export_excel(db, plan_id, plan_type, user.username)


@router.post("/sales-plans/upload")
async def upload_sales_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import a Sales Plan from an Excel file matching the "(S1) Sales
    plan_Value.xlsx" template — creates/overwrites the plan for whatever
    department/team the file's own meta section specifies."""
    content = await file.read()
    return await SalesPlanService().import_excel(db, content, plan_year, user.username)


def _write_gross_sales_sheet(ws, lines: list, plan_year: int) -> tuple:
    """Populate `ws` with the Gross Sales Report layout — mirrors
    output_grossales2026.xlsx: title row, a totals row, a two-row grouped
    header, then one data row per Sales Plan Data product. Columns
    requiring external product-master data the app doesn't track (Tech
    Transfer partner, active ingredient, product type, prior-year actuals)
    are intentionally left out — only what's derivable from Sales Plan Data
    (Market/Customer/Product/Price/Quantity/Amount) is populated; "Actual
    Sales" columns are kept for layout parity but always 0 since this app
    has no actuals feed. Returns (data_start_row, last_data_row) so callers
    (e.g. the Sales Summary sheet) can SUMIFS over this sheet by name."""
    COL_NO, COL_MARKET, COL_CUSTOMER, COL_PRODUCT = 2, 3, 4, 5
    COL_PRICE_ORIG_25, COL_PRICE_ORIG_26 = 6, 7
    COL_PRICE_IDR_25, COL_PRICE_IDR_26 = 8, 9
    COL_QTY_START, COL_QTY_END = 10, 22          # Jan..Dec + Total
    COL_AMT_START, COL_AMT_END = 23, 35          # Jan..Dec + Total
    COL_PRICE_UNIT = 37
    COL_ACT26_START, COL_ACT26_END = 38, 50      # Jan..Dec + Total
    COL_ACT25_START, COL_ACT25_END = 51, 63      # Jan..Dec + Total
    LAST_COL = COL_ACT25_END

    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    title_font = Font(bold=True, size=13)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")

    def merge(r1, c1, r2, c2, value=None, font=None, align=center):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
        cell = ws.cell(row=r1, column=c1, value=value)
        if font: cell.font = font
        if align: cell.alignment = align
        return cell

    merge(1, 1, 1, 20, f"PT CKD OTTO Pharmaceuticals - Gross Sales Report {plan_year}", title_font, Alignment(horizontal="left"))

    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    HR1, HR2 = 3, 4

    def vgroup(col, label):
        merge(HR1, col, HR2, col, label, bold)
        ws.cell(row=HR1, column=col).fill = fill_hdr

    vgroup(COL_NO, "No")
    vgroup(COL_MARKET, "Market")
    vgroup(COL_CUSTOMER, "Customer")
    vgroup(COL_PRODUCT, "Products")
    merge(HR1, COL_PRICE_ORIG_25, HR1, COL_PRICE_ORIG_26, "Price (Original curr)", bold)
    ws.cell(row=HR2, column=COL_PRICE_ORIG_25, value="2025").font = bold
    ws.cell(row=HR2, column=COL_PRICE_ORIG_26, value=plan_year).font = bold
    merge(HR1, COL_PRICE_IDR_25, HR1, COL_PRICE_IDR_26, "Price (IDR)", bold)
    ws.cell(row=HR2, column=COL_PRICE_IDR_25, value="2025").font = bold
    ws.cell(row=HR2, column=COL_PRICE_IDR_26, value=plan_year).font = bold
    merge(HR1, COL_QTY_START, HR1, COL_QTY_END, "Sales Quantity", bold)
    for i, m in enumerate(MONTHS):
        ws.cell(row=HR2, column=COL_QTY_START + i, value=m).font = bold
    ws.cell(row=HR2, column=COL_QTY_END, value="Total").font = bold
    merge(HR1, COL_AMT_START, HR1, COL_AMT_END, "Sales Amount", bold)
    for i, m in enumerate(MONTHS):
        ws.cell(row=HR2, column=COL_AMT_START + i, value=m).font = bold
    ws.cell(row=HR2, column=COL_AMT_END, value="Total").font = bold
    vgroup(COL_PRICE_UNIT, f"Price / unit ({plan_year})")
    merge(HR1, COL_ACT26_START, HR1, COL_ACT26_END, f"Actual Sales {plan_year} (Qty)", bold)
    for i, m in enumerate(MONTHS):
        ws.cell(row=HR2, column=COL_ACT26_START + i, value=m).font = bold
    ws.cell(row=HR2, column=COL_ACT26_END, value="Total").font = bold
    merge(HR1, COL_ACT25_START, HR1, COL_ACT25_END, "Actual Sales 2025 (Value)", bold)
    for i, m in enumerate(MONTHS):
        ws.cell(row=HR2, column=COL_ACT25_START + i, value=m).font = bold
    ws.cell(row=HR2, column=COL_ACT25_END, value="Total").font = bold

    for c in range(1, LAST_COL + 1):
        ws.cell(row=HR1, column=c).fill = fill_hdr
        ws.cell(row=HR2, column=c).fill = fill_hdr

    NUMFMT = "#,##0"
    r0 = HR2 + 1              # totals row (row 5)
    data_start = r0 + 1       # first data row (row 6)
    last_row = data_start + len(lines) - 1 if lines else data_start

    for r_idx, line in enumerate(lines, start=data_start):
        no = r_idx - data_start + 1
        price = line["price"] or 0
        ws.cell(row=r_idx, column=COL_NO, value=no)
        ws.cell(row=r_idx, column=COL_MARKET, value=line["market"])
        ws.cell(row=r_idx, column=COL_CUSTOMER, value=line["customer"])
        ws.cell(row=r_idx, column=COL_PRODUCT, value=line["product"])
        ws.cell(row=r_idx, column=COL_PRICE_ORIG_26, value=price)
        ws.cell(row=r_idx, column=COL_PRICE_IDR_26, value=price)
        price_col = get_column_letter(COL_PRICE_IDR_26)
        # Sales Plan Data's monthly cells are Sales VALUE (Rp), not quantity
        # — Amount is the real entered figure, Quantity is derived from it.
        for i, amt in enumerate(line["amounts"]):
            ws.cell(row=r_idx, column=COL_AMT_START + i, value=amt)
        amt_first, amt_last = get_column_letter(COL_AMT_START), get_column_letter(COL_AMT_END - 1)
        ws.cell(row=r_idx, column=COL_AMT_END, value=f"=SUM({amt_first}{r_idx}:{amt_last}{r_idx})")
        for i in range(12):
            amt_col = get_column_letter(COL_AMT_START + i)
            ws.cell(row=r_idx, column=COL_QTY_START + i,
                    value=f"=IFERROR({amt_col}{r_idx}/${price_col}${r_idx},0)")
        qty_first, qty_last = get_column_letter(COL_QTY_START), get_column_letter(COL_QTY_END - 1)
        ws.cell(row=r_idx, column=COL_QTY_END, value=f"=SUM({qty_first}{r_idx}:{qty_last}{r_idx})")
        ws.cell(row=r_idx, column=COL_PRICE_UNIT, value=f"={price_col}{r_idx}")
        for c in range(COL_ACT26_START, COL_ACT25_END + 1):
            ws.cell(row=r_idx, column=c, value=0)
        for c in range(COL_PRICE_ORIG_25, LAST_COL + 1):
            ws.cell(row=r_idx, column=c).number_format = NUMFMT

    # Totals row — SUM over the data range, positioned above the header like
    # the reference file's SUBTOTAL row.
    ws.cell(row=r0, column=COL_PRODUCT, value="GRAND TOTAL").font = bold
    if lines:
        for c in list(range(COL_QTY_START, COL_AMT_END + 1)) + [COL_ACT26_END, COL_ACT25_END]:
            col = get_column_letter(c)
            cell = ws.cell(row=r0, column=c, value=f"=SUM({col}{data_start}:{col}{last_row})")
            cell.font = bold
            cell.number_format = NUMFMT

    ws.column_dimensions["B"].width = 5
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 28
    for c in range(6, LAST_COL + 1):
        ws.column_dimensions[get_column_letter(c)].width = 12
    ws.freeze_panes = f"{get_column_letter(COL_PRODUCT + 1)}{data_start}"

    return data_start, last_row


def _build_gross_sales_report_xlsx(lines: list, plan_year: int) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Grosssales_{plan_year}"
    _write_gross_sales_sheet(ws, lines, plan_year)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"Gross_Sales_Report_{plan_year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _build_manufacture_plan_detail_xlsx(rows: list, plan_year: int) -> StreamingResponse:
    """rows: raw ManufacturePlan.content.rows lists, shape matches
    manufacture_plan_service.HEADERS:
      [No, Customer, ItemCode, Name, BatchSize, Yield%, Jan..Dec(12),
       TotalBatch, QtyBeforeYield, QtyAfterYield, SalesQty, Coverage]

    Total Batch / Qty Before Yield / Qty After Yield / Coverage are
    RECOMPUTED here from the raw inputs (monthly batches, batch size,
    yield%, sales qty) rather than trusting the stored derived columns —
    the manufacture plan editor only keeps "Total Batch" in sync when a
    monthly cell changes (see PAC.jsx's updateCell), not the downstream
    yield/coverage columns, so a report built off stale stored values
    could silently disagree with its own inputs. Formulas:
      Total Batch            = SUM(Jan..Dec)
      Total Qty Before Yield = Total Batch * Batch Size
      Total Qty After Yield  = Total Qty Before Yield * Yield%
      Coverage                = Total Qty After Yield / Sales Quantity
    — same chain as sumber/'BOM, Manufacturing plan.xlsx' ('Detail
    Manufacturing plan_All': W = S*T*V, Coverage = After-Yield / Sales Plan).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Detail_Manufacturing_{plan_year}"

    bold = Font(bold=True)
    title_font = Font(bold=True, size=13)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")
    fill_total = PatternFill("solid", fgColor="F2F2F2")

    headers = (
        ["No", "Business Type", "Item Code", "Product Name"]
        + _MONTH_LABELS
        + ["Total Batch", "Batch Size (Vial)", "Total Qty Before Yield", "Yield (%)",
           "Total Production After Yield (Vial)", "Sales Quantity (Vial)", "Coverage"]
    )

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value="PT CKD OTTO Pharmaceuticals").font = title_font
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.cell(row=2, column=1, value=f"Manufacturing Plan Detail — {plan_year}").font = Font(italic=True, size=10)

    HR = 4
    for c, label in enumerate(headers, 1):
        cell = ws.cell(row=HR, column=c, value=label)
        cell.font, cell.alignment, cell.fill = bold, center, fill_hdr

    # sort by Business Type then Item Code, mirroring the reference file's
    # grouping (products clustered by Local/Export/CMO)
    def sort_key(r):
        return (str(r[1] if len(r) > 1 else ""), str(r[2] if len(r) > 2 else ""))

    sorted_rows = sorted(rows, key=sort_key)

    r = HR + 1
    totals = {"batch": 0, "before": 0.0, "after": 0.0, "sales": 0.0}
    for i, row in enumerate(sorted_rows, 1):
        customer   = row[1] if len(row) > 1 else ""
        item_code  = row[2] if len(row) > 2 else ""
        name       = row[3] if len(row) > 3 else ""
        batch_size = float(row[4] or 0) if len(row) > 4 else 0.0
        yield_pct  = float(row[5] or 0) if len(row) > 5 else 0.0
        months     = [float(row[6 + m] or 0) if len(row) > 6 + m else 0.0 for m in range(12)]
        sales_qty  = float(row[21] or 0) if len(row) > 21 else 0.0

        total_batch = sum(months)
        qty_before  = total_batch * batch_size
        qty_after   = qty_before * yield_pct
        coverage    = (qty_after / sales_qty) if sales_qty else None

        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=customer)
        ws.cell(row=r, column=3, value=item_code)
        ws.cell(row=r, column=4, value=name)
        for m in range(12):
            ws.cell(row=r, column=5 + m, value=months[m] or None)
        ws.cell(row=r, column=17, value=total_batch)
        ws.cell(row=r, column=18, value=batch_size)
        ws.cell(row=r, column=19, value=qty_before)
        c_yield = ws.cell(row=r, column=20, value=yield_pct)
        c_yield.number_format = "0.0%"
        ws.cell(row=r, column=21, value=qty_after)
        ws.cell(row=r, column=22, value=sales_qty)
        c_cov = ws.cell(row=r, column=23, value=coverage)
        if coverage is not None:
            c_cov.number_format = "0.00"

        totals["batch"]  += total_batch
        totals["before"] += qty_before
        totals["after"]  += qty_after
        totals["sales"]  += sales_qty
        r += 1

    last_row = r - 1
    ws.cell(row=r, column=4, value="TOTAL").font = bold
    ws.cell(row=r, column=17, value=totals["batch"]).font = bold
    ws.cell(row=r, column=19, value=totals["before"]).font = bold
    ws.cell(row=r, column=21, value=totals["after"]).font = bold
    ws.cell(row=r, column=22, value=totals["sales"]).font = bold
    total_cov = (totals["after"] / totals["sales"]) if totals["sales"] else None
    if total_cov is not None:
        c = ws.cell(row=r, column=23, value=total_cov)
        c.font, c.number_format = bold, "0.00"
    for c in range(1, len(headers) + 1):
        ws.cell(row=r, column=c).fill = fill_total

    ws.freeze_panes = ws.cell(row=HR + 1, column=5)
    ws.column_dimensions["D"].width = 26
    for col_letter in ["B", "C"]:
        ws.column_dimensions[col_letter].width = 14
    for m in range(12):
        ws.column_dimensions[get_column_letter(5 + m)].width = 6
    for col_letter in ["Q", "R", "S", "T", "U", "V", "W"]:
        ws.column_dimensions[col_letter].width = 16

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"Manufacturing_Plan_Detail_{plan_year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


def _classify_business_unit(market: str) -> str:
    """Business-unit bucket rule mirrored from V5.Sales Estimation2026.xlsx's
    Summary sheet: Local = Public/Private, CMO/Export are their own units,
    everything else (Service Agreement, Dossier Fee, ...) falls into Others —
    fully data-driven off whatever Market values actually appear, no
    hardcoded customer names."""
    m = (market or "").strip().lower()
    if m in ("public", "private"):
        return "Local"
    if m == "cmo":
        return "CMO"
    if m == "export":
        return "Export"
    return "Others"


def _esc(text: str) -> str:
    return str(text or "").replace('"', '""')


def _build_sales_summary_xlsx(lines: list, plan_year: int) -> StreamingResponse:
    """Sales Summary — mirrors V5.Sales Estimation2026.xlsx's "Summary"
    sheet: a business-unit breakdown (Local/CMO/Others/Export, each broken
    into its Market or Customer sub-rows) with SUMIFS formulas pointing at
    a raw data sheet in the SAME workbook — same cross-sheet-formula
    structure as the reference file's Summary -> Grosssales_2026 link.
    Scope note: only the current plan year's Business Plan figures are
    shown (Value in Rp mil, Quantity) — the reference file's 2024 Actual /
    2025 Estimation / Achievement / CAGR columns depend on prior-year
    actuals this app has no data source for, so they're intentionally
    left out rather than faked as blank/zero."""
    wb = openpyxl.Workbook()
    ws_gross = wb.create_sheet(f"Grosssales_{plan_year}")
    data_start, last_row = _write_gross_sales_sheet(ws_gross, lines, plan_year)
    gsheet = ws_gross.title

    ws = wb.active
    ws.title = "Summary"

    bold = Font(bold=True)
    title_font = Font(bold=True, size=13)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")
    fill_unit = PatternFill("solid", fgColor="F2F2F2")

    def merge(r1, c1, r2, c2, value=None, font=None, align=center):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
        cell = ws.cell(row=r1, column=c1, value=value)
        if font: cell.font = font
        if align: cell.alignment = align
        return cell

    merge(1, 1, 1, 5, f"PT CKD OTTO Pharmaceuticals - {plan_year} Sales Summary", title_font, Alignment(horizontal="left"))
    merge(2, 1, 2, 5, "Summary Sales by Business Unit — derived from Gross Sales Report / Sales Plan Data", Font(italic=True, size=10), Alignment(horizontal="left"))

    HR = 4
    headers = ["Business Unit", "", f"{plan_year} Business Plan Value (Rp mil)", f"{plan_year} Business Plan Quantity", "% of Total Value"]
    for c, label in enumerate(headers, 1):
        cell = ws.cell(row=HR, column=c, value=label)
        cell.font, cell.alignment, cell.fill = bold, center, fill_hdr

    # Group lines into business-unit -> sub-group (Market for Local/Others,
    # Customer for CMO/Export) — same bucket rule as the reference file's
    # own Local/CMO/Others/Export sections.
    UNIT_ORDER = ["Local", "CMO", "Others", "Export"]
    units: dict = {u: {} for u in UNIT_ORDER}
    for line in lines:
        unit = _classify_business_unit(line["market"])
        if unit in ("Local", "Others"):
            key = line["market"] or "(unknown)"
            units[unit].setdefault(key, {"market": line["market"], "customer": None})
        else:
            key = line["customer"] or "(no customer)"
            units[unit].setdefault(key, {"market": line["market"], "customer": line["customer"]})

    # Pass 1 — assign row numbers before writing any formulas, since the
    # unit header row's SUM needs to reference its sub-rows' final range.
    row_plan = []  # (unit, header_row, [sub_rows...])
    r = HR + 1
    for unit in UNIT_ORDER:
        if not units[unit]:
            continue
        header_row = r
        r += 1
        sub_rows = list(range(r, r + len(units[unit])))
        r += len(units[unit])
        row_plan.append((unit, header_row, sub_rows))
    grand_total_row = r

    NUMFMT = "#,##0"
    PCTFMT = "0.0%"

    def write_row(row, label, value_formula, qty_formula, is_bold, fill=None, indent=False):
        c1 = ws.cell(row=row, column=1, value=label)
        if indent:
            c1.alignment = Alignment(indent=1)
        c3 = ws.cell(row=row, column=3, value=value_formula)
        c4 = ws.cell(row=row, column=4, value=qty_formula)
        c5 = ws.cell(row=row, column=5, value=f"=IFERROR(C{row}/$C${grand_total_row},0)")
        c3.number_format = NUMFMT
        c4.number_format = NUMFMT
        c5.number_format = PCTFMT
        if is_bold:
            for cell in (c1, c3, c4, c5):
                cell.font = bold
        if fill:
            for c in range(1, 6):
                ws.cell(row=row, column=c).fill = fill

    for unit, header_row, sub_rows in row_plan:
        keys = list(units[unit].keys())
        for sub_row, key in zip(sub_rows, keys):
            info = units[unit][key]
            market_f = _esc(info["market"])
            if info["customer"]:
                customer_f = _esc(info["customer"])
                value_formula = f'=SUMIFS({gsheet}!$AI:$AI,{gsheet}!$C:$C,"{market_f}",{gsheet}!$D:$D,"{customer_f}")/1000000'
                qty_formula = f'=SUMIFS({gsheet}!$V:$V,{gsheet}!$C:$C,"{market_f}",{gsheet}!$D:$D,"{customer_f}")'
            else:
                value_formula = f'=SUMIFS({gsheet}!$AI:$AI,{gsheet}!$C:$C,"{market_f}")/1000000'
                qty_formula = f'=SUMIFS({gsheet}!$V:$V,{gsheet}!$C:$C,"{market_f}")'
            write_row(sub_row, key, value_formula, qty_formula, is_bold=False, indent=True)

        if sub_rows:
            v_first, v_last = f"C{sub_rows[0]}", f"C{sub_rows[-1]}"
            q_first, q_last = f"D{sub_rows[0]}", f"D{sub_rows[-1]}"
            write_row(header_row, unit, f"=SUM({v_first}:{v_last})", f"=SUM({q_first}:{q_last})", is_bold=True, fill=fill_unit)
        else:
            write_row(header_row, unit, 0, 0, is_bold=True, fill=fill_unit)

    if row_plan:
        header_rows = [hr for _, hr, _ in row_plan]
        v_terms = "+".join(f"C{r}" for r in header_rows)
        q_terms = "+".join(f"D{r}" for r in header_rows)
        write_row(grand_total_row, "GRAND TOTAL", f"={v_terms}", f"={q_terms}", is_bold=True, fill=fill_unit)
    else:
        write_row(grand_total_row, "GRAND TOTAL", 0, 0, is_bold=True, fill=fill_unit)

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 3
    ws.column_dimensions["C"].width = 26
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 14
    ws.freeze_panes = f"A{HR + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"Sales_Summary_{plan_year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ── Purchase Plan (Material) ────────────────────────────────────────────────────

class PurchasePlanPayload(BaseModel):
    id:            Optional[int]  = None
    plan_year:     int
    plan_category: str            = "Local"   # Summary | Local | CMO | Export
    department:    str            = ""
    team_code:     str            = ""
    team_name:     str            = ""
    content:       dict           = {}
    status:        Optional[str]  = "draft"


@router.get("/purchase-plans")
async def list_purchase_plans(
    plan_year:     Optional[int] = Query(None),
    department:    Optional[str] = Query(None),
    team_code:     Optional[str] = Query(None),
    plan_category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List purchase plans filtered by year/department/team/category."""
    return await PurchasePlanService().list_purchase_plans(db, plan_year, department, team_code, plan_category)


@router.get("/purchase-plans/{plan_id}")
async def get_purchase_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single purchase plan."""
    return await PurchasePlanService().get_purchase_plan(db, plan_id)


@router.post("/purchase-plans")
async def upsert_purchase_plan(
    body: PurchasePlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update purchase plan."""
    return await PurchasePlanService().upsert_purchase_plan(db, body.model_dump(), user.username)


@router.delete("/purchase-plans/{plan_id}")
async def delete_purchase_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete purchase plan."""
    return await PurchasePlanService().delete_purchase_plan(db, plan_id)


@router.post("/purchase-plans/upload")
async def upload_purchase_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import Purchase Plan (Material) data from an Excel file matching the
    "(P1-M) Purchase plan_Material.xlsx" template — one plan created/updated
    per recognized data sheet (Summary/Local/CMO/Export)."""
    content = await file.read()
    return await PurchasePlanService().import_excel(db, content, plan_year, user.username)


# ── Personnel Plan ("Personal Plan Data") ──────────────────────────────────────

class PersonnelPlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/personnel-plans")
async def list_personnel_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List personnel plans filtered by year/department."""
    return await PersonnelPlanService().list_personnel_plans(db, plan_year, department)


@router.get("/personnel-plans/{plan_id}")
async def get_personnel_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single personnel plan."""
    return await PersonnelPlanService().get_personnel_plan(db, plan_id)


@router.post("/personnel-plans")
async def upsert_personnel_plan(
    body: PersonnelPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update personnel plan."""
    return await PersonnelPlanService().upsert_personnel_plan(db, body.model_dump(), user.username)


@router.delete("/personnel-plans/{plan_id}")
async def delete_personnel_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete personnel plan."""
    return await PersonnelPlanService().delete_personnel_plan(db, plan_id)


@router.post("/personnel-plans/upload")
async def upload_personnel_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import Personnel Plan data from an Excel file matching the "Personal
    plan template.xlsx" layout (headcount by level + recruitment schedules)."""
    content = await file.read()
    return await PersonnelPlanService().import_excel(db, content, plan_year, user.username)


# ── Manufacture Plan ────────────────────────────────────────────────────────────

class ManufacturePlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    team_code:   str            = ""
    team_name:   str            = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/manufacture-plans")
async def list_manufacture_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    team_code:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List manufacture plans filtered by year/department/team."""
    return await ManufacturePlanService().list_manufacture_plans(db, plan_year, department, team_code)


@router.get("/manufacture-plans/detail-report")
async def export_manufacture_plan_detail_report(
    plan_year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Export the Manufacturing Plan detail report — same column layout and
    calculations as sumber/'BOM, Manufacturing plan.xlsx' sheet
    'Detail Manufacturing plan_All', built from every Manufacture Plan
    record for the given year (2026 scope only — no 2027 H1 columns, since
    this app has no 2027 planning data source to build them from).
    Registered before /manufacture-plans/{plan_id} for the same reason as
    /sales-plans/gross-sales-report — otherwise Starlette's path matching
    would swallow this route as plan_id="detail-report"."""
    result = await ManufacturePlanService().list_manufacture_plans(db, plan_year=plan_year)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "Failed to load Manufacture Plan data")
    rows = [row for plan in result["data"] for row in (plan.get("content") or {}).get("rows", [])]
    if not rows:
        raise HTTPException(404, f"Tidak ada data Manufacture Plan untuk tahun {plan_year}")
    try:
        return _build_manufacture_plan_detail_xlsx(rows, plan_year)
    except Exception as e:
        raise HTTPException(500, f"Excel generation failed: {e}")


@router.get("/manufacture-plans/{plan_id}")
async def get_manufacture_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single manufacture plan."""
    return await ManufacturePlanService().get_manufacture_plan(db, plan_id)


@router.post("/manufacture-plans")
async def upsert_manufacture_plan(
    body: ManufacturePlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update manufacture plan."""
    return await ManufacturePlanService().upsert_manufacture_plan(db, body.model_dump(), user.username)


@router.delete("/manufacture-plans/{plan_id}")
async def delete_manufacture_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete manufacture plan."""
    return await ManufacturePlanService().delete_manufacture_plan(db, plan_id)


@router.post("/manufacture-plans/upload")
async def upload_manufacture_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import Manufacture Plan data from an Excel file matching the
    "manufacture plan template.xlsx" layout."""
    content = await file.read()
    return await ManufacturePlanService().import_excel(db, content, plan_year, user.username)


# ── Investment Plan ──────────────────────────────────────────────────────────────

class InvestmentPlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    team_code:   str            = ""
    team_name:   str            = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/investment-plans")
async def list_investment_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    team_code:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List investment plans filtered by year/department/team."""
    return await InvestmentPlanService().list_investment_plans(db, plan_year, department, team_code)


@router.get("/investment-plans/{plan_id}")
async def get_investment_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single investment plan."""
    return await InvestmentPlanService().get_investment_plan(db, plan_id)


@router.post("/investment-plans")
async def upsert_investment_plan(
    body: InvestmentPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update investment plan."""
    return await InvestmentPlanService().upsert_investment_plan(db, body.model_dump(), user.username)


@router.delete("/investment-plans/{plan_id}")
async def delete_investment_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete investment plan."""
    return await InvestmentPlanService().delete_investment_plan(db, plan_id)


@router.post("/investment-plans/upload")
async def upload_investment_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import Investment Plan data from an Excel file matching the
    "investment plan template.xlsx" layout."""
    content = await file.read()
    return await InvestmentPlanService().import_excel(db, content, plan_year, user.username)


# ── OPEX Plan ─────────────────────────────────────────────────────────────────────

class OpexPlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    team_code:   str            = ""
    team_name:   str            = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/opex-plans")
async def list_opex_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    team_code:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List OPEX plans filtered by year/department/team."""
    return await OpexPlanService().list_opex_plans(db, plan_year, department, team_code)


@router.get("/opex-plans/{plan_id}")
async def get_opex_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single OPEX plan."""
    return await OpexPlanService().get_opex_plan(db, plan_id)


@router.post("/opex-plans")
async def upsert_opex_plan(
    body: OpexPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update OPEX plan."""
    return await OpexPlanService().upsert_opex_plan(db, body.model_dump(), user.username)


@router.delete("/opex-plans/{plan_id}")
async def delete_opex_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete OPEX plan."""
    return await OpexPlanService().delete_opex_plan(db, plan_id)


@router.post("/opex-plans/upload")
async def upload_opex_plan_excel(
    plan_year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Import OPEX Plan data from an Excel file matching the
    "(O1) OPEX Plan_Summary_Department.xlsx" layout."""
    content = await file.read()
    return await OpexPlanService().import_excel(db, content, plan_year, user.username)


# ── Exchange Rates ─────────────────────────────────────────────────────────────

@router.get("/exchange-rates")
async def get_exchange_rates(
    refresh: bool = Query(False, description="Force re-scrape even if cache is fresh"),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Kurs Transaksi Bank Indonesia — scraped daily, cached 4 hours."""
    return await asyncio.to_thread(exchange_rate_service.get_rates, refresh)


class PushToEBSRequest(BaseModel):
    rate_date:   str        # "2026-07-03"
    rate_type:   str        = "Corporate"       # Corporate | Spot | user-defined
    rate_source: str        = "tengah"          # jual | beli | tengah
    currencies:  list[str]  = ["USD", "EUR", "SGD", "JPY", "GBP", "AUD", "CNY", "MYR"]


@router.post("/exchange-rates/push-to-ebs")
async def push_exchange_rates_to_ebs(
    body: PushToEBSRequest,
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """
    Push Kurs Transaksi BI ke Oracle EBS GL Daily Rates menggunakan
    GL_DAILY_RATES_API.INSERT_RATE / UPDATE_RATE.
    """
    # Get current cached rates (don't re-scrape unless cache is empty)
    cached = await asyncio.to_thread(exchange_rate_service.get_rates, False)
    if not cached.get("rates"):
        return {"success": False, "error": "Tidak ada data kurs — ambil data dari BI terlebih dahulu", "results": []}

    results = await asyncio.to_thread(
        exchange_rate_service.push_rates_to_ebs,
        cached["rates"],
        body.rate_date,
        body.rate_type,
        body.rate_source,
        body.currencies,
    )

    success_count = sum(1 for r in results if r["status"] == "success")
    error_count   = sum(1 for r in results if r["status"] == "error")
    return {
        "success":       error_count == 0,
        "rate_date":     body.rate_date,
        "rate_type":     body.rate_type,
        "rate_source":   body.rate_source,
        "total":         len(results),
        "success_count": success_count,
        "error_count":   error_count,
        "results":       results,
    }
