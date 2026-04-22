"""
HR Dashboard Router
Route prefix : /api/v1/dashboard/hr
Required role: hr_staff OR admin
"""
from fastapi import APIRouter, Depends
from app.dependencies import require_role, CurrentUser, Roles
from app.routers.dashboard import hr_employees

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.HR))):
    """KPI cards HR Dashboard."""
    return {"module": "hr", "status": "ready", "message": "Implement HRService"}


# Sub-router: employee data upload & query
router.include_router(hr_employees.router, prefix="/employees", tags=["Dashboard - HR Employees"])
