"""
ACCOUNTING Dashboard Router
Route prefix : /api/v1/dashboard/accounting
Required role: accounting_staff OR admin
"""
from fastapi import APIRouter, Depends
from app.dependencies import require_role, CurrentUser, Roles

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.ACCOUNTING))):
    """KPI cards ACCOUNTING Dashboard."""
    return {"module": "accounting", "status": "ready", "message": "Implement ACCOUNTINGService"}
