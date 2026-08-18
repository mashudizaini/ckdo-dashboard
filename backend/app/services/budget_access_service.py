"""
Budget Monitoring — per-user team access control.

Restricts which Oracle GL department (segment3 / CKDO_GL_COA_DEPARTMENT)
code a user can query budget for, based on their own Employee record's
`team` — matched to the logged-in Keycloak user via Employee.company_email
— unless they're on the IT team or one of a short list of exempted users
who need to see every team's budget (see EXEMPT_USERNAMES).

TEAM_TO_DEPT verified live against Oracle (FND_FLEX_VALUES_VL, value set
CKDO_GL_COA_DEPARTMENT) and the distinct employees.team values present at
the time this was written (2026-08-18) — re-verify both sides if either
taxonomy changes.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser
from app.models.employee import Employee

# employees.team (fine-grained) -> (Oracle dept_code, dept_name).
TEAM_TO_DEPT: dict[str, tuple[str, str]] = {
    "IT":                      ("15", "IT"),
    "HRGA":                    ("14", "HUMAN RESOURCE AND GENERAL AFFAIR"),
    "PURCHASING":              ("13", "PURCHASING"),
    "PLANNING & COORDINATION": ("11", "PLANNING & COORDINATION"),
    # Oracle also carries a separate "12 TAX" code — employees.team combines
    # Accounting and Tax into one team with no way to tell which a given
    # transaction belongs to, so this maps to the closer, larger bucket.
    "ACCOUNTING & TAX":        ("16", "ACCOUNTING"),
    "MARKETING":               ("22", "MARKETING"),
    "SALES":                   ("21", "SALES"),
    "GLOBAL BUSINESS":         ("61", "GLOBAL BUSINESS"),
    "BUSINESS DEVELOPMENT":    ("62", "BUSINESS DEVELOPMENT"),
    "REGULATORY AFFAIRS":      ("63", "REGULATORY AFFAIR"),
    "ENGINEERING":             ("33", "ENGINEERING"),
    "PRODUCTION":              ("38", "PRODUCTION"),
    "QA":                      ("31", "QUALITY ASSURANCE"),
    "QC":                      ("32", "QUALITY CONTROL"),
    "VALIDATION":              ("39", "VALIDATION"),
    "MEDICAL AFFAIR":          ("37", "MEDICAL AFFAIR"),
    "GA":                      ("36", "GENERAL AFFAIR"),
    # Oracle has two separate "DIRECTOR" codes (40, 42) with no way to tell
    # them apart by name alone — 40 picked as the primary/first.
    "DIRECTOR":                ("40", "DIRECTOR"),
    # Not mapped here (ambiguous, no single correct Oracle code) — falls
    # through to DEPARTMENT_TO_DEPT below instead:
    #   "General Manager" — a GM exists in every department, not one team.
    #   "PPWH" — spans Oracle's separate Production Planning (35) and
    #     Warehouse (34) codes.
}

# Fallback for employees whose specific `team` has no clean Oracle match —
# coarser canonical department (see department_taxonomy.py) -> dept_code.
DEPARTMENT_TO_DEPT: dict[str, tuple[str, str]] = {
    "ADMINISTRATION":          ("10", "ADMINISTRATION"),
    "SALES & MARKETING":       ("20", "SALES MARKETING"),
    "STRATEGY & DEVELOPMENT":  ("60", "STRATEGY DEVELOPMENT"),
    "PLANT":                   ("30", "PLANT"),
}

# Logins allowed to view every team's budget in addition to the IT team —
# matched against the Keycloak username's local part (before @), lowercase.
EXEMPT_USERNAMES = {"mashudi", "hardian", "utomo"}


def _username_local(username: str) -> str:
    return (username.split("@")[0] if "@" in username else username).strip().lower()


async def _find_employee(user: CurrentUser, db: AsyncSession) -> Optional[Employee]:
    """Matches the logged-in Keycloak user to their Employee row via
    company_email — the only field on Employee that corresponds to a login
    identity. Tries user.email first, then user.username (Keycloak's
    preferred_username is also an email address in this realm)."""
    for candidate in (user.email, user.username):
        if not candidate:
            continue
        result = await db.execute(select(Employee).where(Employee.company_email.ilike(candidate.strip())))
        employee = result.scalar_one_or_none()
        if employee:
            return employee
    return None


async def resolve_budget_access(user: CurrentUser, db: AsyncSession) -> dict:
    """Returns {allowed_all, dept_code, dept_name, team, employee_matched}.

    allowed_all=True means the caller may query any dept_code (IT team, or
    one of EXEMPT_USERNAMES). Otherwise dept_code/dept_name is the one team
    they're allowed to see — None if their team couldn't be resolved at all
    (no Employee match, or a team with no Oracle mapping and no usable
    department fallback)."""
    employee = await _find_employee(user, db)
    team = (employee.team or "").strip().upper() if employee else ""
    allowed_all = team == "IT" or _username_local(user.username) in EXEMPT_USERNAMES

    dept_code = dept_name = None
    if team in TEAM_TO_DEPT:
        dept_code, dept_name = TEAM_TO_DEPT[team]
    elif employee and employee.department:
        dept_code, dept_name = DEPARTMENT_TO_DEPT.get(employee.department.strip().upper(), (None, None))

    return {
        "allowed_all": allowed_all,
        "dept_code": dept_code,
        "dept_name": dept_name,
        "team": employee.team if employee else None,
        "employee_matched": employee is not None,
    }
