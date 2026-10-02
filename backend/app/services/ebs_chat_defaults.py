"""
EBS Chat — default access for first-time users
───────────────────────────────────────────────
Before this, an employee who opened EBS Chat / CoChat's EBS Assistant or EBS
Analyst without an ebs_chat_scope row was refused until an admin registered
them by hand in Setup > AI > EBS Chat Access. Now both entry points
(ebs_chat_service._get_scope for the EIS tools, ebs_mart.access.scope_groups
for the EBS mart tools) provision a row on first use, derived from that
employee's own record in `employees`:

  departments     <- the employee's canonical department (row-level scope)
  allowed_modules <- BASE_MODULES + TEAM_RULES[team]["modules"]   (EBS Assistant)
  kb_departments  <- BASE_KB      + TEAM_RULES[team]["kb"]
  ebs_groups      <- TEAM_RULES[team]["ebs_groups"]               (EBS Analyst marts)

Rules are keyed by employees.team (exact value, e.g. "HRGA"). A team with no
rule still gets the base set, nothing more — extend TEAM_RULES as each team's
access is agreed rather than guessing a mapping that could expose data.

The row is only ever INSERTed when missing: anything an admin has already set
(or later edits) in Setup > AI > EBS Chat Access is never overwritten. It is
marked created_by='auto-default' so auto-provisioned rows are easy to find.

allowed_modules must never be left empty here — an empty list means "every
module" in ebs_chat_service._tools_for_modules.
"""
from typing import Optional

import structlog
from psycopg2.extras import Json

from app.services.department_taxonomy import CANONICAL_DEPARTMENTS, normalize_department

logger = structlog.get_logger()

# Every auto-provisioned user: company documents, General tag only.
BASE_MODULES = ["Company Rules"]
BASE_KB = ["General"]

# employees.team -> extra access on top of the base set.
# modules:    keys of ebs_chat_service.MODULE_TOOL_MAP
# kb:         rag_service.DEPARTMENTS (General/HR/Accounting/PAC/Purchasing/IT)
# ebs_groups: ebs_mart.policy.role_codes() — which EBS marts EBS Analyst may read
TEAM_RULES: dict[str, dict[str, list[str]]] = {
    "HRGA":             {"modules": ["HR"], "kb": ["HR"]},
    "Accounting & Tax": {"modules": ["Financial", "COGS", "Budget"], "kb": ["Accounting"], "ebs_groups": ["ebs-finance"]},
    "Purchasing":       {"modules": ["Purchasing", "Inventory"], "kb": ["Purchasing"], "ebs_groups": ["ebs-purchasing"]},
    "Sales":            {"modules": ["Sales"], "ebs_groups": ["ebs-sales"]},
    "Marketing":        {"modules": ["Sales"], "ebs_groups": ["ebs-sales"]},
    "Production":       {"modules": ["Production"], "ebs_groups": ["ebs-production"]},
    "Engineering":      {"modules": ["Production"], "ebs_groups": ["ebs-production"]},
    "PPWH":             {"modules": ["Inventory", "Production"], "ebs_groups": ["ebs-warehouse"]},
}

AUTO_CREATED_BY = "auto-default"


def _merge(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for lst in lists:
        for v in lst:
            if v not in out:
                out.append(v)
    return out


def _find_employee(conn, email: str) -> Optional[tuple[str, str]]:
    """(department, team) of the active employee owning this email, or None.

    Matched on the HR master's own email columns first. Many active employees
    have no email there (HR never filled it), so fall back to Oracle EBS:
    core.hr_ebs_employee maps the login email to an employee_number, which is
    the HR master's user_id (NIK)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT department, team FROM employees
            WHERE (LOWER(company_email) = %s OR LOWER(personal_email) = %s)
              AND employment_status = 'Active'
            ORDER BY (LOWER(company_email) = %s) DESC
            LIMIT 1""",
        (email, email, email),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1]
    try:
        cur.execute(
            """SELECT e.department, e.team FROM core.hr_ebs_employee h
                 JOIN employees e ON e.user_id = h.employee_number
                WHERE LOWER(h.email) = %s AND e.employment_status = 'Active'
                LIMIT 1""",
            (email,),
        )
        row = cur.fetchone()
    except Exception:
        # core.* not created yet on this host — HR master email is all we have.
        conn.rollback()
        return None
    return (row[0], row[1]) if row else None


def build_default_scope(department: Optional[str], team: Optional[str]) -> dict:
    canonical = normalize_department(department) or (department if department in CANONICAL_DEPARTMENTS else None)
    rule = TEAM_RULES.get((team or "").strip(), {})
    return {
        "full_access": False,
        "departments": [canonical] if canonical else [],
        "allowed_modules": _merge(BASE_MODULES, rule.get("modules", [])),
        "kb_departments": _merge(BASE_KB, rule.get("kb", [])),
        "ebs_groups": list(rule.get("ebs_groups", [])),
    }


def provision_default_scope(conn, email: str) -> Optional[dict]:
    """Insert a default ebs_chat_scope row for a known, active employee that
    has none yet, and return the scope now stored for them. Returns None when
    the email is not an active employee (caller keeps its existing
    unknown-user handling). Uses the caller's connection and commits."""
    email = (email or "").strip().lower()
    if not email:
        return None
    emp = _find_employee(conn, email)
    if not emp:
        return None
    department, team = emp
    cur = conn.cursor()
    scope = build_default_scope(department, team)
    cur.execute(
        """INSERT INTO ebs_chat_scope
               (email, full_access, departments, allowed_modules, kb_departments, ebs_groups, notes, created_by, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (email) DO NOTHING""",
        (
            email, scope["full_access"], Json(scope["departments"]), Json(scope["allowed_modules"]),
            Json(scope["kb_departments"]), Json(scope["ebs_groups"]),
            f"auto: {department or '-'} / {team or '-'}", AUTO_CREATED_BY,
        ),
    )
    conn.commit()
    logger.info("ebs_chat_scope auto-provisioned", email=email, department=department, team=team, **scope)
    # Re-read: a concurrent request (or an admin) may have inserted first.
    cur.execute(
        "SELECT full_access, departments, allowed_modules, kb_departments FROM ebs_chat_scope WHERE email = %s",
        (email,),
    )
    row = cur.fetchone()
    return {
        "full_access": row[0], "departments": row[1] or [], "allowed_modules": row[2] or [],
        "kb_departments": row[3] or [],
    } if row else None
