"""
EBS Chat — default access for first-time users
───────────────────────────────────────────────
Before this, an employee who opened EBS Chat / CoChat's EBS Assistant without
an ebs_chat_scope row got "scope_not_configured" until an admin registered
them by hand in Setup > AI > EBS Chat Access. Now _get_scope() provisions a
row on first use, derived from that employee's own record in `employees`:

  departments     <- the employee's canonical department (row-level scope)
  allowed_modules <- BASE_MODULES + TEAM_RULES[team]["modules"]
  kb_departments  <- BASE_KB      + TEAM_RULES[team]["kb"]

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

# employees.team -> extra modules / KB tags on top of the base set.
# modules: keys of ebs_chat_service.MODULE_TOOL_MAP
# kb:      rag_service.DEPARTMENTS (General/HR/Accounting/PAC/Purchasing/IT)
TEAM_RULES: dict[str, dict[str, list[str]]] = {
    "HRGA": {"modules": ["HR"], "kb": ["HR"]},
}

AUTO_CREATED_BY = "auto-default"


def _merge(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for lst in lists:
        for v in lst:
            if v not in out:
                out.append(v)
    return out


def _find_employee(cur, email: str) -> Optional[tuple[str, str]]:
    """(department, team) of the active employee owning this email, or None."""
    cur.execute(
        """SELECT department, team FROM employees
            WHERE (LOWER(company_email) = %s OR LOWER(personal_email) = %s)
              AND employment_status = 'Active'
            ORDER BY (LOWER(company_email) = %s) DESC
            LIMIT 1""",
        (email, email, email),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def build_default_scope(department: Optional[str], team: Optional[str]) -> dict:
    canonical = normalize_department(department) or (department if department in CANONICAL_DEPARTMENTS else None)
    rule = TEAM_RULES.get((team or "").strip(), {})
    return {
        "full_access": False,
        "departments": [canonical] if canonical else [],
        "allowed_modules": _merge(BASE_MODULES, rule.get("modules", [])),
        "kb_departments": _merge(BASE_KB, rule.get("kb", [])),
    }


def provision_default_scope(conn, email: str) -> Optional[dict]:
    """Insert a default ebs_chat_scope row for a known, active employee that
    has none yet, and return the scope now stored for them. Returns None when
    the email is not an active employee (caller keeps its existing
    unknown-user handling). Uses the caller's connection and commits."""
    email = (email or "").strip().lower()
    if not email:
        return None
    cur = conn.cursor()
    emp = _find_employee(cur, email)
    if not emp:
        return None
    department, team = emp
    scope = build_default_scope(department, team)
    cur.execute(
        """INSERT INTO ebs_chat_scope
               (email, full_access, departments, allowed_modules, kb_departments, ebs_groups, notes, created_by, updated_at)
           VALUES (%s, %s, %s, %s, %s, '[]'::jsonb, %s, %s, NOW())
           ON CONFLICT (email) DO NOTHING""",
        (
            email, scope["full_access"], Json(scope["departments"]), Json(scope["allowed_modules"]),
            Json(scope["kb_departments"]), f"auto: {department or '-'} / {team or '-'}", AUTO_CREATED_BY,
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
