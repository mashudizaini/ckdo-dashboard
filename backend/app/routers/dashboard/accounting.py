"""
ACCOUNTING Dashboard Router
Route prefix : /api/v1/dashboard/accounting
Required role: accounting_staff OR admin

Endpoints:
  GET  /summary                        — placeholder
  GET  /material-transactions          — MTL_MATERIAL_TRANSACTIONS export
"""
from fastapi import APIRouter, Depends, Query
from app.dependencies import require_role, CurrentUser, Roles
from app.services.accounting_service import AccountingService

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.ACCOUNTING))):
    return {"module": "accounting", "status": "ready"}


# ── AP Outstanding ───────────────────────────────────────────────────────────

@router.get("/ap-outstanding")
async def get_ap_outstanding(
    as_of_date:     str  = Query(None, description="As-of date YYYY-MM-DD (default: today)"),
    supplier_name:  str  = Query(None, description="Partial supplier name filter"),
    operating_unit: str  = Query(None, description="Partial operating unit name filter"),
    payment_status: str  = Query(None, description="Not Paid | Partially Paid | ALL"),
    limit:          int  = Query(500, ge=1, le=2000),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """
    AP Outstanding — AP_INVOICES_ALL + AP_PAYMENT_SCHEDULES_ALL.
    Excludes fully Paid invoices. As-of date defaults to SYSDATE.
    """
    return await AccountingService().get_ap_outstanding(
        as_of_date, supplier_name, operating_unit, payment_status, limit
    )


# ── AR Outstanding ───────────────────────────────────────────────────────────

@router.get("/ar-outstanding")
async def get_ar_outstanding(
    customer_name:  str  = Query(None, description="Partial customer name filter"),
    invoice_number: str  = Query(None, description="Partial invoice number filter"),
    date_from:      str  = Query(None, description="Invoice date from YYYY-MM-DD"),
    date_to:        str  = Query(None, description="Invoice date to YYYY-MM-DD"),
    status:         str  = Query("OP",  description="OP=open, CL=closed, ALL=both"),
    limit:          int  = Query(500, ge=1, le=2000),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """
    AR Outstanding from Oracle EBS — AR_PAYMENT_SCHEDULES_ALL + RA_CUSTOMER_TRX_ALL.
    Class filter: INV + DM (invoices and debit memos only).
    """
    return await AccountingService().get_ar_outstanding(
        customer_name, invoice_number, date_from, date_to, status, limit
    )


# ── COGS / Inventory RM PM ───────────────────────────────────────────────────

@router.get("/inventory-rm-pm")
async def get_inventory_rm_pm(
    period:        str  = Query(...,  description="OPM period code e.g. JAN-26"),
    include_begin: bool = Query(True, description="Calculate beginning balance (slower)"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """
    Inventory RM PM monthly report — movements + price + beginning/ending balance.
    Fixed: org 121. Data: MTL_MATERIAL_TRANSACTIONS + CKDO_GET_ITEM_COST.
    """
    return await AccountingService().get_inventory_rm_pm(period, include_begin)


# ── COGS / Item Cost Components ───────────────────────────────────────────────

@router.get("/item-cost-components")
async def get_item_cost_components(
    period: str = Query(..., description="OPM period code e.g. JAN-2025"),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """
    Item cost breakdown per cost component — Oracle OPM CM_CMPT_DTL.
    Fixed org=121 (CKDO), cost_type=1000 (Actual).
    """
    return await AccountingService().get_item_cost_components(period)


# ── COGS / Material Transactions ─────────────────────────────────────────────

@router.get("/material-transactions")
async def get_material_transactions(
    date_from:   str = Query(..., description="Start date YYYY-MM-DD"),
    date_to:     str = Query(..., description="End date   YYYY-MM-DD"),
    org_code:    str = Query(None, description="Filter by organization code"),
    item_number: str = Query(None, description="Filter by item number (partial)"),
    trx_type:    str = Query(None, description="Filter by transaction type (partial)"),
    limit:       int = Query(1000, ge=1, le=5000),
    user: CurrentUser = Depends(require_role(Roles.ACCOUNTING)),
):
    """
    Material Transactions from MTL_MATERIAL_TRANSACTIONS — mirrors
    Oracle EBS Inventory > Material Transactions > Export to Excel.
    """
    return await AccountingService().get_material_transactions(
        date_from, date_to, org_code, item_number, trx_type, limit
    )
