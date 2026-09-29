"""
CKDO Company Data Tools / CKDO Company Documents — the EBS Chat tools as
OpenAPI tool servers, so CoChat's own model calls them directly.

Before (2026-09-30) the "Oracle EBS Assistant" and "Company Rules" assistants
had one CoChat tool, oracle_ebs_query(question), that posted the question to
/api/v1/ai/ebs-chat/query — where the dashboard ran a second Claude loop
(tool planning + answer), whose prose CoChat's model then rewrote. Two LLM
layers per question, and the "Qwen Local" variants were never local: the
dashboard's Claude did the real work. Here the CoChat model picks the tool
and writes the answer itself; the dashboard only executes.

Two servers because Open WebUI attaches tools to a model per server, not per
operation: Company Rules gets only the document search, the Oracle EBS
Assistant gets both.

  /api/v1/eis-tools      one POST operation per eis_tools.EIS_TOOLS entry
  /api/v1/company-docs   search_company_documents (rag_service)

Access is unchanged from ebs_chat_service.answer_question, and enforced here
on every call, never by the prompt:
  - identity: service key (bearer) + X-OpenWebUI-User-Email, which Open WebUI
    fills from the logged-in account ({{USER_EMAIL}}); the user cannot set it
  - ebs_chat_scope row required (403 tells scope_not_configured apart from an
    unknown email, as the old tool did)
  - allowed_modules -> the tool must be in the caller's module set (the IT
    module stays opt-in)
  - departments -> the query runs on the RLS-scoped ebs_chat_reader
    connection (SET LOCAL app.*)
  - kb_departments -> document search is limited to the caller's KB tags,
    taken from the scope row, never from the model's arguments
"""
import hmac
from typing import Literal, Optional

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field, create_model

from app.config import get_settings
from app.services import ebs_chat_service, eis_tools, rag_service

settings = get_settings()
logger = structlog.get_logger()

_CORS = dict(allow_origin_regex=r"https?://cochat(-dev)?\.ckd-otto\.com", allow_methods=["GET", "POST"],
             allow_headers=["*"])

data_app = FastAPI(
    title="CKDO Company Data Tools",
    description=(
        "Read-only company data from Oracle EBS (via the dashboard's data warehouse) for PT CKD OTTO "
        "Pharmaceuticals: sales, COGS/margin, production, budget, AR/AP, inventory, purchasing, purchase "
        "and sales orders, headcount and employee directory, daily sales, and (IT users only) Oracle "
        "tablespace, server CPU/memory/disk and processes. Results are limited to the caller's access."
    ),
    version="1.0.0",
    root_path_in_servers=False,
)
docs_app = FastAPI(
    title="CKDO Company Documents",
    description="Search the company's policy, rules and SOP documents (the dashboard's knowledge base), "
                "limited to the document categories the caller may read.",
    version="1.0.0",
    root_path_in_servers=False,
)
for _a in (data_app, docs_app):
    _a.add_middleware(CORSMiddleware, **_CORS)


# ── Identity & scope ─────────────────────────────────────────────────────────

class Caller:
    def __init__(self, email: str, scope: dict):
        self.email, self.scope = email, scope


_NOT_CONFIGURED = ("[SYSTEM INFO] This user is a known employee, but their Oracle EBS data access has not been set "
                   "up yet. Tell the user exactly that: their account is recognised and IT/Dashboard needs to "
                   "configure their access (Setup > AI > EBS Chat Access). Do not guess other causes.")
_UNKNOWN = ("[SYSTEM INFO] This user's email is not found as an employee in the dashboard HR data or in Oracle "
            "EBS. Tell the user exactly that and ask them to contact IT/Dashboard to check the company email "
            "they log in with. Do not guess other causes.")


async def current_caller(
    authorization: Optional[str] = Header(None),
    x_service_key: Optional[str] = Header(None),
    x_openwebui_user_email: Optional[str] = Header(None),
) -> Caller:
    key = settings.ebs_chat_service_key
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    presented = x_service_key or bearer
    if not key or not presented or not hmac.compare_digest(presented, key):
        raise HTTPException(401, "Invalid or missing service key")
    email = (x_openwebui_user_email or "").strip().lower()
    if not email:
        raise HTTPException(401, "Service key accepted, but the user's email was not forwarded")
    scope = await run_in_threadpool(ebs_chat_service._get_scope, email)
    if scope is None:
        known = await ebs_chat_service._employee_exists(email)
        raise HTTPException(403, _NOT_CONFIGURED if known else _UNKNOWN)
    return Caller(email, scope)


def _run_scoped(caller: Caller, tool: str, arguments: dict) -> list[dict]:
    """Same connection handling as ebs_chat_service.answer_question: SET LOCAL
    only lives for the transaction, so the tool runs inside it."""
    conn = ebs_chat_service._open_scoped_connection(caller.scope)
    try:
        with eis_tools.use_connection(conn):
            rows = eis_tools.execute_tool(tool, arguments)
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Data tools: one operation per EIS_TOOLS entry ───────────────────────────

_PY = {"string": str, "number": float, "integer": int, "boolean": bool}


def _body_model(tool: dict):
    fn = tool["function"]
    props = fn.get("parameters", {}).get("properties", {})
    required = set(fn.get("parameters", {}).get("required", []))
    fields = {}
    for name, p in props.items():
        typ = Literal[tuple(p["enum"])] if p.get("enum") else _PY.get(p.get("type"), str)
        if name in required:
            fields[name] = (typ, Field(..., description=p.get("description", "")))
        else:
            # Plain type with a None default (not Optional[...]): the schema
            # stays {"type": ...} instead of anyOf-with-null, which is what
            # Open WebUI turns into tool parameters most reliably.
            fields[name] = (typ, Field(None, description=p.get("description", "")))
    return create_model(f"{fn['name']}_in", **fields)


def _add_data_route(tool: dict):
    name = tool["function"]["name"]
    Body = _body_model(tool)

    async def endpoint(body: Body, caller: Caller = Depends(current_caller)):  # type: ignore[valid-type]
        allowed = ebs_chat_service._tools_for_modules(caller.scope["allowed_modules"])
        if name not in allowed:
            logger.warning("eis_tool_denied", tool=name, email=caller.email)
            raise HTTPException(403, f"[SYSTEM INFO] {name} is outside this user's granted data access. "
                                     "Tell the user they do not have access to this kind of data.")
        args = body.model_dump(exclude_none=True)
        try:
            rows = await run_in_threadpool(_run_scoped, caller, name, args)
        except ValueError as e:   # bad period format and similar argument errors
            raise HTTPException(422, str(e))
        logger.info("eis_tool_call", tool=name, email=caller.email, arguments=args, rows=len(rows))
        out = {"tool": name, "count": len(rows)}
        totals = eis_tools.summarize(name, rows)
        if totals:
            out["totals"] = totals   # before data, so the model reads the exact sums first
        out["data"] = rows
        return out

    data_app.post(f"/{name}", operation_id=name, summary=name,
                  description=tool["function"].get("description", ""))(endpoint)


for _t in eis_tools.EIS_TOOLS:
    _add_data_route(_t)


# ── Company documents ────────────────────────────────────────────────────────

_DocsIn = create_model("search_company_documents_in", query=(str, Field(
    ..., description="The question or topic to look up in the company documents, in the user's words")))


@docs_app.post(
    "/search_company_documents", operation_id="search_company_documents", summary="search_company_documents",
    description="Search the company's policy/rules/SOP documents (HR, Accounting, PAC, Purchasing, IT, General) "
                "for passages that answer a question about internal rules or procedures — NOT for Oracle EBS "
                "transaction data. Answer only from the returned excerpts and cite the document.",
)
async def search_company_documents(body: _DocsIn, caller: Caller = Depends(current_caller)):  # type: ignore[valid-type]
    if "search_company_documents" not in ebs_chat_service._tools_for_modules(caller.scope["allowed_modules"]):
        raise HTTPException(403, "[SYSTEM INFO] Company documents are outside this user's granted access.")
    # KB tags come from the caller's scope row, never from the model.
    kb = None if caller.scope["full_access"] else (caller.scope["kb_departments"] or ["General"])
    result = await run_in_threadpool(rag_service.retrieve_context, body.query, department_filter=kb)
    logger.info("eis_docs_search", email=caller.email, query=body.query, found=bool(result.get("context")))
    if not result.get("context"):
        return {"found": False, "note": "No matching document passage. Say so plainly; do not invent a rule."}
    return {"found": True, "excerpt": result["context"], "citations": result.get("sources", [])}
