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

Callers with departments=[] and full_access=false can still ask about
sales/production/COGS/etc. — those 9 tables are unaffected by RLS regardless
of department. They only get zero rows back from the 3 scoped tables
(get_employee_directory, get_employee_headcount, get_budget_vs_actual), not
an error — same as PLANT_DIRECT would in Oracle.

allowed_modules (added 2026-09-18, see MODULE_TOOL_MAP) is the answer to
"but I don't want this caller reaching sales/production at all" — an
independent, coarser restriction that hides whole tools from the model
rather than filtering their rows. departments/full_access and
allowed_modules compose: a caller can be tool-restricted to just Inventory
AND department-restricted within any tools that still support it.
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
from app.services import eis_tools, rag_service
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

# Business-friendly grouping of the 12 eis_tools functions, for the
# per-caller tool-level restriction (independent of the department/row-level
# scoping above — a caller can be limited to a subset of MODULES regardless
# of which departments' rows they're allowed to see within them). Every
# tool belongs to exactly one module here; keep in sync with EIS_TOOLS in
# eis_tools.py if a new tool is ever added there.
MODULE_TOOL_MAP: dict[str, list[str]] = {
    "Sales":         ["get_sales_performance", "get_sales_order_detail"],
    "Production":    ["get_production_performance"],
    "Financial":     ["get_financial_summary", "get_ar_ap_summary"],
    "COGS":          ["get_cogs_performance"],
    "Inventory":     ["get_inventory_summary"],
    "Purchasing":    ["get_purchasing_performance", "get_purchase_order_detail"],
    "HR":            ["get_employee_directory", "get_employee_headcount"],
    "Budget":        ["get_budget_vs_actual"],
    "Company Rules": ["search_company_documents"],
    # Infrastructure health, read from the eis.fact_it_* snapshots that
    # etl_it_monitoring writes every 15 minutes. See _OPT_IN_MODULES below —
    # this one is never granted by omission.
    "IT": [
        "get_tablespace_usage",
        "get_tablespace_trend",
        "get_server_resources",
        "get_disk_usage",
        "get_oracle_activity",
    ],
}

# Modules an empty allowed_modules list does NOT grant.
#
# _tools_for_modules treats an empty list as "no restriction", because every
# scope row predating that column has to keep working. That default was safe
# while every tool returned business data: the worst case was a caller seeing
# sales figures they had no business reading, which departments/RLS already
# governed.
#
# The IT tools are a different kind of answer — server addresses, mount
# points, filesystem headroom, which tablespace is closest to full. That is
# reconnaissance material, and handing it to everyone who happens to have a
# blank column is not a default anyone chose. So these are opt-in: a caller
# reaches them by having "IT" listed explicitly, never by omission.
_OPT_IN_MODULES = {"IT"}

_ALL_TOOL_NAMES = {
    name
    for module, names in MODULE_TOOL_MAP.items()
    if module not in _OPT_IN_MODULES
    for name in names
}


def _tools_for_modules(modules: list[str]) -> set[str]:
    """Empty/None modules list = no restriction (every existing scope row
    predates this column and must keep working exactly as before)."""
    if not modules:
        return set(_ALL_TOOL_NAMES)
    out = set()
    for m in modules:
        out.update(MODULE_TOOL_MAP.get(m, []))
    return out


# search_company_documents isn't one of eis_tools.EIS_TOOLS (it doesn't touch
# Oracle EBS data at all — it's the Dashboard's own pgvector Knowledge Base,
# see rag_service.py) so it's defined and dispatched right here instead of
# living in eis_tools.py.
_COMPANY_RULES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_company_documents",
        "description": (
            "Cari jawaban dari dokumen kebijakan/peraturan perusahaan (SOP, company rules, "
            "kebijakan HR/Accounting/PAC/Purchasing/IT) — untuk pertanyaan seputar peraturan "
            "atau prosedur internal perusahaan, BUKAN data transaksi Oracle EBS."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Pertanyaan atau topik yang ingin dicari dalam dokumen perusahaan"},
            },
            "required": ["query"],
        },
    },
}

# ebs_chat_scope.kb_departments values <- rag_service.DEPARTMENTS tags
# (General/HR/Accounting/PAC/Purchasing/IT) — deliberately its OWN field
# rather than derived from `departments` (the CANONICAL_DEPARTMENTS used for
# eis.* row scoping): the two vocabularies don't line up cleanly enough to
# translate automatically (CANONICAL_DEPARTMENTS are 4 broad organizational
# buckets, the KB's 6 tags are functional teams), and guessing a mapping
# wrong here risks leaking or hiding actual policy document content — an
# admin explicitly picking which KB tags a caller can read removes that
# guesswork entirely, same as they already do for `departments`/
# `allowed_modules`. Unlike those two fields, empty here means "General
# only" (NOT unrestricted) — this is a brand new field nobody has set yet,
# so there's no pre-existing access to preserve, and document content
# warrants a safer default than structured tool output does.
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
        # allowed_modules: added 2026-09-18 for per-tool restriction (see
        # MODULE_TOOL_MAP) — NULL/empty on every pre-existing row, which
        # _tools_for_modules() treats as "no restriction", so this migration
        # can't silently narrow anyone's existing access.
        cur.execute("ALTER TABLE ebs_chat_scope ADD COLUMN IF NOT EXISTS allowed_modules JSONB NOT NULL DEFAULT '[]'")
        # kb_departments: added 2026-09-18 — see the comment above
        # FINAL_ANSWER_MAX_TOKENS for why empty here means "General only",
        # unlike departments/allowed_modules where empty means unrestricted.
        cur.execute("ALTER TABLE ebs_chat_scope ADD COLUMN IF NOT EXISTS kb_departments JSONB NOT NULL DEFAULT '[]'")
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
            SELECT email, full_access, departments, allowed_modules, kb_departments, notes, created_by, created_at, updated_at
            FROM ebs_chat_scope ORDER BY email
        """)
        rows = cur.fetchall()
        return [
            {
                "email": r[0], "full_access": r[1], "departments": r[2] or [], "allowed_modules": r[3] or [],
                "kb_departments": r[4] or [], "notes": r[5], "created_by": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
                "updated_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()


def upsert_scope(
    email: str, full_access: bool, departments: list[str], notes: Optional[str], updated_by: str,
    allowed_modules: Optional[list[str]] = None, kb_departments: Optional[list[str]] = None,
) -> dict:
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    bad = [d for d in departments or [] if d not in CANONICAL_DEPARTMENTS]
    if bad:
        raise ValueError(f"Unknown department(s): {bad} — must be one of {CANONICAL_DEPARTMENTS}")
    bad_modules = [m for m in allowed_modules or [] if m not in MODULE_TOOL_MAP]
    if bad_modules:
        raise ValueError(f"Unknown module(s): {bad_modules} — must be one of {list(MODULE_TOOL_MAP)}")
    bad_kb = [d for d in kb_departments or [] if d not in rag_service.DEPARTMENTS]
    if bad_kb:
        raise ValueError(f"Unknown KB department(s): {bad_kb} — must be one of {rag_service.DEPARTMENTS}")

    from psycopg2.extras import Json
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ebs_chat_scope (email, full_access, departments, allowed_modules, kb_departments, notes, created_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (email) DO UPDATE SET
                full_access     = EXCLUDED.full_access,
                departments     = EXCLUDED.departments,
                allowed_modules = EXCLUDED.allowed_modules,
                kb_departments  = EXCLUDED.kb_departments,
                notes           = EXCLUDED.notes,
                updated_at      = NOW()
        """, (
            email, full_access, Json(departments or []), Json(allowed_modules or []),
            Json(kb_departments or []), notes, updated_by,
        ))
        conn.commit()
        return {
            "email": email, "full_access": full_access, "departments": departments or [],
            "allowed_modules": allowed_modules or [], "kb_departments": kb_departments or [], "notes": notes,
        }
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
            "SELECT full_access, departments, allowed_modules, kb_departments FROM ebs_chat_scope WHERE email = %s",
            ((email or "").strip().lower(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "full_access": row[0], "departments": row[1] or [], "allowed_modules": row[2] or [],
            "kb_departments": row[3] or [],
        }
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
            result = await _run_tool_calling_turn(
                question,
                allowed_tools=_tools_for_modules(scope["allowed_modules"]),
                kb_departments=None if scope["full_access"] else (scope["kb_departments"] or ["General"]),
            )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _run_tool_calling_turn(
    question: str, allowed_tools: Optional[set[str]] = None, kb_departments: Optional[list[str]] = None,
) -> dict:
    """Single-turn (no chat history — each CoChat call is a fresh question),
    non-streaming Anthropic tool-calling turn. Mirrors oracle_chat_service.
    _stream_chat_anthropic's two-step flow, but eis_tools.execute_tool()
    now runs against whatever connection use_connection() has set active
    for this request (see answer_question above) instead of opening its
    own chat_readonly connection — that's what makes the RLS scope apply.

    allowed_tools (from the caller's MODULE_TOOL_MAP restriction, see
    _tools_for_modules) is applied twice: once by simply not OFFERING the
    disallowed tools to the model at all (so it never even considers them),
    and again as a defense-in-depth check right before execute_tool() — the
    second check is what actually matters for safety, the first is just
    what keeps the model from wasting a turn asking for something it can't
    have."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = ANTHROPIC_CHAT_DEFAULT_MODEL
    messages = [{"role": "user", "content": question}]

    all_tools = eis_tools.EIS_TOOLS + [_COMPANY_RULES_TOOL]
    offered_tools = (
        [t for t in all_tools if t["function"]["name"] in allowed_tools]
        if allowed_tools is not None else all_tools
    )
    offered_names = {t["function"]["name"] for t in offered_tools}

    # Only mention search_company_documents when it's actually offered —
    # SYSTEM_PROMPT is shared with oracle_chat_service.py (the Dashboard's
    # own internal chat), which never has this tool at all.
    turn_system = SYSTEM_PROMPT
    if "search_company_documents" in offered_names:
        turn_system += (
            "\n\n- Untuk pertanyaan seputar kebijakan/SOP/peraturan perusahaan (BUKAN data transaksi "
            "Oracle EBS), gunakan tool search_company_documents. Jawab HANYA berdasarkan isi dokumen yang "
            "ditemukan — jika tidak ada dokumen relevan, katakan terus terang tidak menemukan aturan yang "
            "dimaksud, jangan mengarang."
        )

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=turn_system,
        messages=messages,
        tools=_to_anthropic_tools(offered_tools),
    )

    sources = []
    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
    if tool_use_blocks:
        messages.append({"role": "assistant", "content": response.content})
        tool_result_blocks = []
        for block in tool_use_blocks:
            tool_name = block.name
            arguments = block.input
            if allowed_tools is not None and tool_name not in allowed_tools:
                data = []
                error = "This tool is outside your granted access scope."
                logger.warning("ebs_chat_tool_denied", tool=tool_name, arguments=arguments)
            elif tool_name == "search_company_documents":
                # Not an eis_tools.EIS_TOOLS entry — dispatched here directly
                # instead of via eis_tools.execute_tool() because it needs
                # kb_departments injected from the CALLER's own scope, never
                # from the model/arguments, so a prompt can't talk its way
                # into a department it wasn't granted.
                try:
                    rag_result = rag_service.retrieve_context(
                        arguments.get("query", question), department_filter=kb_departments,
                    )
                    # One combined "row" carrying the actual excerpt text the
                    # model needs to read plus its citations — rag_service
                    # merges all matched chunks into one context string
                    # (build_context), it doesn't return per-source content.
                    data = (
                        [{"excerpt": rag_result["context"], "citations": rag_result["sources"]}]
                        if rag_result.get("context") else []
                    )
                    error = None
                except Exception as e:
                    data = []
                    error = str(e)
                    logger.warning("ebs_chat_kb_search_error", arguments=arguments, error=error)
            else:
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
                "content": json.dumps(
                    {"error": error} if error else {"data": data, "count": len(data)}, default=str
                ),
            })
        messages.append({"role": "user", "content": tool_result_blocks})

    lang = _detect_language(question)
    final_system = turn_system + "\n\n" + (
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
