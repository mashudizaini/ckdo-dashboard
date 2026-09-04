"""
General Dashboard Router
Route prefix : /api/v1/dashboard/general

Unlike HR/IT/PAC/etc., this section is intentionally NOT gated to a single
Keycloak role at the router level — it's meant to be reachable by any
authenticated user, with each sub-module applying its own finer-grained
access control instead. Budget Monitoring, for example, restricts by the
caller's own team (see general_budget.py / budget_access_service.py)
rather than by role.
"""
from fastapi import APIRouter
from app.routers.dashboard import general_budget, general_ap_payment, general_ap_list, general_access_control

router = APIRouter()

# Sub-router: budget monitoring (moved here from HRGA — see general_budget.py)
router.include_router(general_budget.router, prefix="/budget", tags=["Dashboard - General Budget"])

# Sub-router: AP Outstanding with Payment (see general_ap_payment.py) —
# same Oracle data as Accounting & Tax > AP Outstanding, deliberately placed
# here instead so it's visible company-wide, not gated to accounting_staff.
router.include_router(general_ap_payment.router, prefix="/ap-payment", tags=["Dashboard - General AP Outstanding with Payment"])

# Sub-router: AP List (see general_ap_list.py) — every AP transaction by GL
# Date, Paid and unpaid alike, with DPP/VAT/WHT breakdown and NPWP, format
# matching sumber/FORMAT LIST AP 2025.xlsx. Placed here for the same
# company-wide-visibility reason as ap-payment above.
router.include_router(general_ap_list.router, prefix="/ap-list", tags=["Dashboard - General AP List"])

# Sub-router: per-user menu access control (see general_access_control.py /
# menu_access_service.py) — gated per-endpoint inside that router, not here,
# since it mixes IT-only admin endpoints with one endpoint any user needs.
router.include_router(general_access_control.router, prefix="/access-control", tags=["Dashboard - General Access Control"])
