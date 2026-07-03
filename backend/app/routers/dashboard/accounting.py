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
