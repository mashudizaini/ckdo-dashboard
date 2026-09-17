"""
EBS Chat — Dashboard-side (Track B) of the CoChat <-> Oracle EBS integration
─────────────────────────────────────────
CoChat (Open WebUI) calls POST /api/v1/ai/ebs-chat/query with a shared
service key plus the caller's own email (from Open WebUI's __user__ — CoChat
has its own separate login, there's no Keycloak session to read a role from
here). This module resolves that email to a department scope via the
ebs_chat_scope table (see below), then runs the SAME tool-calling engine
eis_tools.py already uses for the Dashboard's own internal Oracle EBS chat
(oracle_chat_service.py) — but on a single Postgres connection/transaction
opened as the `ebs_chat_reader` role with `SET LOCAL app.full_access` /
`app.allowed_departments` / `app.allowed_budget_groups` set from that
resolved scope. Row Level Security policies on eis.dim_employee /
eis.fact_employee / eis.fact_budget (created directly on the eis_dashboard
Postgres, not by this app's own startup code — see the runbook) enforce the
actual filtering; the LLM never sees or decides who can see what, it just
gets fewer/no rows back for tables outside its caller's scope.

Why the scope source is a manually-curated Dashboard table, not a synced
Oracle FND_USER_RESP_GROUPS table like the original runbook assumed:
Oracle EBS's own responsibility/org hierarchy carries no usable per-user
department info in this instance — every employee's hr_all_organization_
units row is the exact same single top-level "CKDO BG" business group (see
eis_etl_tasks.etl_employee's docstring, which already had to abandon Oracle
as dim_employee's source for the same reason). The Dashboard's own role
system (Roles.* in dependencies.py) is real and already trusted for
authorization everywhere else in this app, so it's the honest source here
too — an admin just has to assign each EBS Chat caller's email a set of
departments once, the same way ebs_full_access_users would have been
manually managed either way.

Why only 3 of the 12 eis.* tools are actually scoped: every other eis.*
table (fact_sales, fact_production, fact_financial, fact_cogs,
fact_financial_ratio, fact_purchasing, fact_po_line, fact_open_pr,
fact_sales_order, fact_batch, fact_inventory_txn) is a company-wide
aggregate or transactional table with no department-ownership column at
all — RLS can't filter a dimension the data doesn't carry. Only
dim_employee.department, fact_employee.dept_group (HR canonical taxonomy —
Administration / Sales & Marketing / Strategy & Development / Plant) and
fact_budget.dept_group (a DIFFERENT taxonomy, derived from GL cost-center
codes — SM / SD / Plant Direct / Plant Indirect / Admin, see
eis_etl_tasks.etl_budget._map_cost_center) have one. _BUDGET_GROUP_MAP below
is a best-effort translation between the two so an admin only ever has to
pick departments from the one taxonomy they already know from HR/Attendance
— note etl_budget's own cost-center-range mapping is flagged there as a
placeholder pending calibration against the real Oracle COA, so this
translation inherits that same uncertainty for the "SD" bucket in
particular.

Unscoped callers (any email in ebs_chat_scope with departments=[] and
full_access=false) can still ask about sales/production/COGS/etc. — those
tools are unaffected by RLS. They only get zero rows back from the 3 scoped
tables (get_employee_directory, get_employee_headcount,
get_budget_vs_actual), not an error — same as PLANT_DIRECT would in Oracle.
"""
import json
import re
from typing import Optional

import anthropic
import psycopg2
import structlog
from sqlalchemy import select, func

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.employee import Employee
from app.services import eis_tools
from app.services.ai_service import ANTHROPIC_CHAT_DEFAULT_MODEL
from app.services.department_taxonomy import CANONICAL_DEPARTMENTS
from app.services.oracle_chat_service import SYSTEM_PROMPT, _detect_language, _to_anthropic_tools

logger = structlog.get_logger()
settings = get_settings()

# fact_budget.dept_group taxonomy <- HR canonical department taxonomy.
# See module docstring — best-effort, "SD" in particular is unconfirmed.
_BUDGET_GROUP_MAP = {
    "Administration": ["Admin"],
    "Sales & Marketing": ["SM"],
    "Strategy & Development": ["SD"],
    "Plant": ["Plant Direct", "Plant Indirect"],
}

FINAL_ANSWER_MAX_TOKENS = 4096


def _get_pg():
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {settings.database_url}")
    return psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                             user=m.group(1), password=m.group(2))


def ensure_table():
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ebs_chat_scope (
                email         VARCHAR(200) PRIMARY KEY,
                full_access   BOOLEAN NOT NULL DEFAULT FALSE,
                departments   JSONB NOT NULL DEFAULT '[]',
                notes         VARCHAR(500),
                created_by    VARCHAR(150),
                created_at    TIMESTAMP DEFAULT NOW(),
                updated_at    TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Admin CRUD (Setup > AI > EBS Chat Access) ──────────────────────────

def list_scopes() -> list[dict]:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT email, full_access, departments, notes, created_by, created_at, updated_at
            FROM ebs_chat_scope ORDER BY email
        """)
        rows = cur.fetchall()
        return [
            {
                "email": r[0], "full_access": r[1], "departments": r[2] or [], "notes": r[3],
                "created_by": r[4], "created_at": r[5].isoformat() if r[5] else None,
                "updated_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()


def upsert_scope(email: str, full_access: bool, departments: list[str], notes: Optional[str], updated_by: str) -> dict:
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    bad = [d for d in departments or [] if d not in CANONICAL_DEPARTMENTS]
    if bad:
        raise ValueError(f"Unknown department(s): {bad} — must be one of {CANONICAL_DEPARTMENTS}")

    from psycopg2.extras import Json
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ebs_chat_scope (email, full_access, departments, notes, created_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (email) DO UPDATE SET
                full_access = EXCLUDED.full_access,
                departments = EXCLUDED.departments,
                notes       = EXCLUDED.notes,
                updated_at  = NOW()
        """, (email, full_access, Json(departments or []), notes, updated_by))
        conn.commit()
        return {"email": email, "full_access": full_access, "departments": departments or [], "notes": notes}
    finally:
        conn.close()


def delete_scope(email: str):
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ebs_chat_scope WHERE email = %s", ((email or "").strip().lower(),))
        conn.commit()
    finally:
        conn.close()


def _get_scope(email: str) -> Optional[dict]:
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT full_access, departments FROM ebs_chat_scope WHERE email = %s",
            ((email or "").strip().lower(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"full_access": row[0], "departments": row[1] or []}
    finally:
        conn.close()


# ── Scoped EIS connection ───────────────────────────────────────────────

def _budget_groups_for(departments: list[str]) -> list[str]:
    out = []
    for d in departments:
        out.extend(_BUDGET_GROUP_MAP.get(d, []))
    return out


def _open_scoped_connection(scope: dict):
    """One connection, one (implicit) transaction — SET LOCAL only lasts
    for the current transaction, so every tool call for this request must
    run on this same connection before it's committed/closed."""
    conn = psycopg2.connect(settings.eis_ebs_chat_reader_url)
    cur = conn.cursor()
    cur.execute("SET LOCAL app.full_access = %s", (str(bool(scope["full_access"])).lower(),))
    cur.execute("SET LOCAL app.allowed_departments = %s", (",".join(scope["departments"]),))
    cur.execute("SET LOCAL app.allowed_budget_groups = %s", (",".join(_budget_groups_for(scope["departments"])),))
    cur.close()
    return conn


async def _employee_exists(email: str) -> bool:
    """True if `email` matches an employee's company/personal email in
    this app's own Employee table — the real, actively-maintained HR
    source of truth (eis.dim_employee is itself mirrored FROM this table,
    not from Oracle EBS's per_people_f — see etl_employee)."""
    email = (email or "").strip().lower()
    if not email:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Employee.user_id).where(
                (func.lower(Employee.company_email) == email)
                | (func.lower(Employee.personal_email) == email)
            ).limit(1)
        )
        return result.scalar() is not None


# ── Answering a question ────────────────────────────────────────────────

async def answer_question(question: str, user_email: str) -> dict:
    """Returns {"answer": str, "sources": [...]}, or one of two distinct
    error shapes when the caller can't be answered for:
    - {"error": "user_not_found_in_ebs"}: the email isn't a known employee
      at all (not in the Employee master).
    - {"error": "scope_not_configured"}: the email IS a known employee,
      but no one has set up their ebs_chat_scope row yet — a different,
      more actionable situation (admin needs to register them) than a
      genuinely unknown/external email."""
    scope = _get_scope(user_email)
    if scope is None:
        if await _employee_exists(user_email):
            return {"error": "scope_not_configured"}
        return {"error": "user_not_found_in_ebs"}

    conn = _open_scoped_connection(scope)
    try:
        with eis_tools.use_connection(conn):
            result = await _run_tool_calling_turn(question)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _run_tool_calling_turn(question: str) -> dict:
    """Single-turn (no chat history — each CoChat call is a fresh question),
    non-streaming Anthropic tool-calling turn. Mirrors oracle_chat_service.
    _stream_chat_anthropic's two-step flow, but eis_tools.execute_tool()
    now runs against whatever connection use_connection() has set active
    for this request (see answer_question above) instead of opening its
    own chat_readonly connection — that's what makes the RLS scope apply."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = ANTHROPIC_CHAT_DEFAULT_MODEL
    messages = [{"role": "user", "content": question}]

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=_to_anthropic_tools(eis_tools.EIS_TOOLS),
    )

    sources = []
    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
    if tool_use_blocks:
        messages.append({"role": "assistant", "content": response.content})
        tool_result_blocks = []
        for block in tool_use_blocks:
            tool_name = block.name
            arguments = block.input
            try:
                data = eis_tools.execute_tool(tool_name, arguments)
                error = None
            except Exception as e:
                data = []
                error = str(e)
                logger.warning("ebs_chat_tool_execution_error", tool=tool_name, arguments=arguments, error=error)

            sources.append({"tool": tool_name, "arguments": arguments, "row_count": len(data), "error": error})
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps({"error": error} if error else {"data": data}, default=str),
            })
        messages.append({"role": "user", "content": tool_result_blocks})

    lang = _detect_language(question)
    final_system = SYSTEM_PROMPT + "\n\n" + (
        "PENTING: Tulis balasan berikut dalam Bahasa Indonesia. Jangan gunakan Bahasa Inggris."
        if lang == "id" else
        "IMPORTANT: Write the following reply in English. Do not use Indonesian."
    )

    final = await client.messages.create(
        model=model,
        max_tokens=FINAL_ANSWER_MAX_TOKENS,
        system=final_system,
        messages=messages,
    )
    answer = "".join(b.text for b in final.content if b.type == "text")

    if not answer.strip():
        logger.warning(
            "ebs_chat_empty_answer",
            stop_reason=final.stop_reason,
            block_types=[b.type for b in final.content],
            question=question,
        )
        final = await client.messages.create(
            model=model,
            max_tokens=FINAL_ANSWER_MAX_TOKENS,
            system=final_system,
            messages=messages,
        )
        answer = "".join(b.text for b in final.content if b.type == "text")

    if not answer.strip():
        logger.warning(
            "ebs_chat_empty_answer_after_retry",
            stop_reason=final.stop_reason,
            block_types=[b.type for b in final.content],
            question=question,
        )
        answer = _fallback_answer(sources, lang)

    return {"answer": answer, "sources": sources}


def _fallback_answer(sources: list[dict], lang: str) -> str:
    """Deterministic non-empty answer built from tool results, used only
    when the model's final turn returns no text (retried once first) —
    never surface a literal empty string to the user."""
    rows_found = [s for s in sources if not s.get("error") and s.get("row_count", 0) > 0]
    if rows_found:
        if lang == "id":
            parts = [f"{s['row_count']} baris dari {s['tool']}" for s in rows_found]
            return "Data ditemukan (" + "; ".join(parts) + "), tetapi jawaban tidak berhasil dibuat. Silakan coba tanyakan ulang dengan kalimat yang lebih spesifik."
        parts = [f"{s['row_count']} row(s) from {s['tool']}" for s in rows_found]
        return "Data was found (" + "; ".join(parts) + ") but an answer could not be generated. Please try rephrasing your question."
    if lang == "id":
        return "Maaf, tidak dapat membuat jawaban untuk pertanyaan ini. Silakan coba tanyakan ulang dengan kalimat yang lebih spesifik."
    return "Sorry, an answer could not be generated for this question. Please try rephrasing it."
