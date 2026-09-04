"""
AP Outstanding with Payment Router
Route prefix : /api/v1/dashboard/general/ap-payment
Required role: any authenticated user (see general.py — this section is
intentionally not gated to accounting_staff, unlike /dashboard/accounting's
own AP Outstanding, since the request was to make payment visibility
available company-wide, not just to the Accounting team).

  GET "" — AP Outstanding rows + payment application history (see
           AccountingService.get_ap_outstanding_with_payment)
"""
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, CurrentUser
from app.services.accounting_service import AccountingService

router = APIRouter()


@router.get("")
async def get_ap_outstanding_with_payment(
    as_of_date:     str  = Query(None, description="As-of date YYYY-MM-DD (default: today)"),
    date_from:      str  = Query(None, description="Period From — invoice date YYYY-MM-DD"),
    date_to:        str  = Query(None, description="Period To — invoice date YYYY-MM-DD"),
    supplier_name:  str  = Query(None, description="Partial supplier name filter"),
    payment_status: str  = Query(None, description="Not Paid | Partially Paid | ALL"),
    limit:          int  = Query(500, ge=1, le=20000),
    user: CurrentUser = Depends(get_current_user),
):
    """
    AP Outstanding, one row per (invoice, payment applied) — same
    filters/scope as Accounting & Tax > AP Outstanding, with payment number/
    date/amount added. An invoice not yet paid at all still appears once
    (payment columns NULL); a partially-paid invoice appears once per
    payment applied against it.
    """
    return await AccountingService().get_ap_outstanding_with_payment(
        as_of_date=as_of_date, date_from=date_from, date_to=date_to,
        supplier_name=supplier_name, payment_status=payment_status, limit=limit,
    )
