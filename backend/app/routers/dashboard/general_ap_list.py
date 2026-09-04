"""
AP List Router
Route prefix : /api/v1/dashboard/general/ap-list
Required role: any authenticated user (matches ap-payment's convention —
company-wide payment visibility, not gated to accounting_staff).

  GET "" — every AP transaction by GL Date, Paid and unpaid alike, with
           DPP/VAT/WHT/Total, Payment, Remaining AP, payment exchange rate,
           and supplier NPWP (see AccountingService.get_ap_list).
"""
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, CurrentUser
from app.services.accounting_service import AccountingService

router = APIRouter()


@router.get("")
async def get_ap_list(
    gl_date_from:        str  = Query(None, description="GL Date From YYYY-MM-DD"),
    gl_date_to:          str  = Query(None, description="GL Date To YYYY-MM-DD"),
    payment_date_cutoff: str  = Query(None, description="Only count payments on/before this date (default: today) — reconstructs AP as of a past payment cutoff"),
    supplier_name:       str  = Query(None, description="Partial supplier name filter"),
    payment_status:      str  = Query(None, description="Not Paid | Partially Paid | Paid | ALL"),
    limit:               int  = Query(500, ge=1, le=20000),
    user: CurrentUser = Depends(get_current_user),
):
    """
    AP List — one row per invoice (unlike AP Outstanding with Payment's
    one-row-per-payment-application shape), covering ALL invoices in the
    GL Date range regardless of payment status. See
    AccountingService.get_ap_list's docstring for the DPP/VAT/WHT formula
    and why Payment Status/payment_date_cutoff work the way they do.
    """
    return await AccountingService().get_ap_list(
        gl_date_from=gl_date_from, gl_date_to=gl_date_to,
        payment_date_cutoff=payment_date_cutoff,
        supplier_name=supplier_name, payment_status=payment_status, limit=limit,
    )
