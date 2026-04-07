"""
PAC Dashboard Router
Route prefix : /api/v1/dashboard/pac
Required role: pac_staff OR admin

Endpoints:
  GET  /summary
  GET  /budget-usage           — Actual vs Budget per period/cost-center
  GET  /lov/ledgers            — GL ledger LOV
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.dependencies import require_role, CurrentUser, Roles
from app.services.pac_service import PACService

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
