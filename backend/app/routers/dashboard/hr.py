"""
HR Dashboard Router
Route prefix : /api/v1/dashboard/hr
Required role: hr_staff OR admin
"""
from fastapi import APIRouter, Depends
from app.dependencies import require_role, CurrentUser, Roles
from app.routers.dashboard import hr_employees, hr_attendance, hr_initiatives, hr_leave, hr_calendar, hr_todo, hr_cv_screening, hr_emagazine, hr_org_structure

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.HR))):
    """KPI cards HR Dashboard."""
    return {"module": "hr", "status": "ready", "message": "Implement HRService"}


# Sub-router: employee data upload & query
router.include_router(hr_employees.router,  prefix="/employees",  tags=["Dashboard - HR Employees"])

# Sub-router: attendance upload & query
router.include_router(hr_attendance.router, prefix="/attendance", tags=["Dashboard - HR Attendance"])

# Sub-router: leave upload & query
router.include_router(hr_leave.router,      prefix="/leave",      tags=["Dashboard - HR Leave"])

# Sub-router: working calendar
router.include_router(hr_calendar.router,   prefix="/calendar",   tags=["Dashboard - HR Calendar"])

# Sub-router: HRGA To Do List
router.include_router(hr_todo.router,       prefix="/todo",       tags=["Dashboard - HR Todo"])

# Sub-router: CV Screening
router.include_router(hr_cv_screening.router, prefix="/cv-screening", tags=["Dashboard - HR CV Screening"])

# Sub-router: HR department initiatives (budget vs actual per initiative)
router.include_router(hr_initiatives.router, prefix="/budget/initiatives", tags=["Dashboard - HR Budget Initiatives"])

# Sub-router: e-magazine management
router.include_router(hr_emagazine.router,  prefix="/e-magazine", tags=["Dashboard - HR e-Magazine"])

# Sub-router: organization structure (manual add/edit/delete org chart)
router.include_router(hr_org_structure.router, prefix="/org-structure", tags=["Dashboard - HR Org Structure"])
