"""
EBS Data Mart admin — Setup > AI > EBS Data Mart.
Route prefix: /api/v1/ai/ebs-mart (IT / admin only, gated in main.py).

  GET    /overview                   marts (all phases), row counts, as_of, recent ETL runs
  POST   /trigger/{job}              manual ETL / refresh (logged as MANUAL, advisory-locked)
  GET    /catalog                    meta.column_catalog
  PUT    /catalog/{mart}/{column}    edit description / synonyms
  GET    /golden-queries             meta.golden_query
  POST   /golden-queries             add
  PUT    /golden-queries/{id}        edit
  DELETE /golden-queries/{id}        remove
  POST   /golden-queries/{id}/verify mark verified (by the caller, today)
  POST   /sql                        run SQL through the same guard as run_sql (playground)
  POST   /tool/{name}                call an intent tool as a chosen ebs-* group (test)
  POST   /security-test              blueprint section 11 checks, pass/fail each
  GET    /query-log                  meta.chat_query_log, filterable
  GET    /query-log/stats            7/30-day volume, error rate, median duration per tool
  GET    /subinventories             core.dim_subinventory + classification
  PUT    /subinventories/{code}      set GOOD / REJECT / QUARANTINE (then refresh the mart)
  GET    /openwebui-kit              system prompt, skills, prompts, filter, action, URLs
"""
import json
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, Roles, require_role
from app.services.ebs_mart import query, sql_guard, tools
from app.services.ebs_mart.access import AccessDenied, Caller
from app.services.ebs_mart.constants import (
    DOMAIN_BY_GROUP, EBS_GROUPS, GROUP_LABELS, MARTS, MAX_ROWS, STATEMENT_TIMEOUT,
)
from app.services.ebs_mart.query import QueryFailed

router = APIRouter()
_admin = require_role(Roles.IT, Roles.ADMIN)
_KIT = Path(__file__).resolve().parents[2] / "services" / "ebs_mart" / "openwebui_kit"

JOBS = {
    "etl_mart_ap": "AP (incremental)",
    "etl_mart_inventory": "Inventory on-hand per lot (snapshot)",
    "etl_inventory_txn": "Mutasi inventory (sumber inv_movement_daily)",
    "refresh_ebs_marts": "Refresh semua mart",
}


def _admin_caller(user: CurrentUser, group: str = "ebs-management", source: str = "dashboard") -> Caller:
    return Caller(email=(user.email or user.username or "admin").lower(), groups={group}, source=source)


def _rows(sql: str, params=None, commit: bool = False) -> list[dict]:
    conn = query._rw()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            out = [{c: query._jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        if commit:
            conn.commit()
        return out
    finally:
        conn.close()


def _exec(sql: str, params=None) -> int:
    conn = query._rw()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


# ── Overview & ETL ───────────────────────────────────────────────────────────

def _overview() -> dict:
    counts = {}
    built = {r["matviewname"]: r for r in _rows(
        "SELECT matviewname, ispopulated FROM pg_matviews WHERE schemaname = 'mart'")}
    for name in built:
        counts[name] = _rows(f"SELECT COUNT(*) AS n FROM mart.{name}")[0]["n"]
    marts = []
    for name, m in MARTS.items():
        marts.append({
            "mart": name, "domain": m["domain"], "phase": m["phase"], "grain": m["grain"],
            "description": m["description"], "sources": m["sources"],
            "built": name in built, "row_count": counts.get(name),
            "as_of": query.as_of([name]) if name in built else None,
            "source_jobs": m.get("source_jobs", []),
        })
    runs = _rows(
        """SELECT run_id, job_name, trigger_type, triggered_by, status, rows_read, rows_upserted,
                  watermark_from, watermark_to, error_msg, started_at, finished_at,
                  EXTRACT(EPOCH FROM (COALESCE(finished_at, NOW()) - started_at))::int AS duration_secs
             FROM meta.etl_run_log
            WHERE job_name = ANY(%s)
            ORDER BY started_at DESC LIMIT 30""",
        (list(JOBS),),
    )
    watermarks = _rows("SELECT job_name, stream, watermark, updated_at FROM meta.etl_watermark ORDER BY 1, 2")
    return {"marts": marts, "runs": runs, "watermarks": watermarks, "jobs": JOBS,
            "groups": [{"group": g, "label": GROUP_LABELS[g], "prefixes": sorted(DOMAIN_BY_GROUP[g])} for g in EBS_GROUPS],
            "guardrails": {"max_rows": MAX_ROWS, "statement_timeout": STATEMENT_TIMEOUT}}


@router.get("/overview")
async def overview(user: CurrentUser = Depends(_admin)):
    return await run_in_threadpool(_overview)


class TriggerIn(BaseModel):
    full_refresh: bool = False


@router.post("/trigger/{job}")
async def trigger(job: str, body: TriggerIn = TriggerIn(), user: CurrentUser = Depends(_admin)):
    if job not in JOBS:
        raise HTTPException(400, f"Job tidak dikenal. Pilihan: {list(JOBS)}")
    from app.tasks.celery_app import celery_app
    kwargs: dict = {}
    if job != "etl_inventory_txn":
        kwargs = {"trigger_type": "MANUAL", "triggered_by": user.username or user.email}
    if job == "etl_mart_ap" and body.full_refresh:
        kwargs["full_refresh"] = True
    result = celery_app.send_task(f"app.tasks.etl_tasks.{job}", kwargs=kwargs)
    return {"message": f"{JOBS[job]} dijalankan", "task_id": result.id}


# ── Catalog ──────────────────────────────────────────────────────────────────

@router.get("/catalog")
async def catalog(user: CurrentUser = Depends(_admin)):
    return await run_in_threadpool(_rows, """
        SELECT mart_name, column_name, data_type, description_id, synonyms, sample_values, domain,
               updated_by, updated_at
          FROM meta.column_catalog ORDER BY mart_name, column_name""")


class CatalogIn(BaseModel):
    description_id: Optional[str] = None
    synonyms: list[str] = []


@router.put("/catalog/{mart}/{column}")
async def update_catalog(mart: str, column: str, body: CatalogIn, user: CurrentUser = Depends(_admin)):
    syn = sorted({s.strip() for s in body.synonyms if s.strip()})
    n = await run_in_threadpool(_exec, """
        UPDATE meta.column_catalog SET description_id = %s, synonyms = %s, updated_by = %s, updated_at = now()
         WHERE mart_name = %s AND column_name = %s""",
        (body.description_id, syn, user.username, mart, column))
    if not n:
        raise HTTPException(404, "Kolom tidak ada di katalog")
    return {"ok": True}


# ── Golden queries ───────────────────────────────────────────────────────────

class GoldenIn(BaseModel):
    domain: str
    question_id: str
    sql_text: str


@router.get("/golden-queries")
async def golden_list(user: CurrentUser = Depends(_admin)):
    return await run_in_threadpool(_rows, """
        SELECT id, domain, question_id, sql_text, verified_by, verified_at, created_by, created_at
          FROM meta.golden_query ORDER BY domain, id""")


def _check_sql(sql: str):
    try:
        sql_guard.validate(sql.replace("<kode item>", "X"))
    except sql_guard.SqlRejected as e:
        raise HTTPException(400, f"SQL ditolak guardrail: {e}")


@router.post("/golden-queries")
async def golden_add(body: GoldenIn, user: CurrentUser = Depends(_admin)):
    _check_sql(body.sql_text)
    try:
        rows = await run_in_threadpool(_rows, """
        INSERT INTO meta.golden_query (domain, question_id, sql_text, created_by)
        VALUES (%s, %s, %s, %s) RETURNING id""", (body.domain, body.question_id.strip(), body.sql_text, user.username),
            True)
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(400, "Pertanyaan yang sama sudah ada di golden query")
    return rows[0]


@router.put("/golden-queries/{gid}")
async def golden_update(gid: int, body: GoldenIn, user: CurrentUser = Depends(_admin)):
    _check_sql(body.sql_text)
    # Editing the SQL clears verification: what was verified is gone.
    await run_in_threadpool(_exec, """
        UPDATE meta.golden_query
           SET domain = %s, question_id = %s,
               verified_by = CASE WHEN sql_text = %s THEN verified_by END,
               verified_at = CASE WHEN sql_text = %s THEN verified_at END,
               sql_text = %s
         WHERE id = %s""",
        (body.domain, body.question_id.strip(), body.sql_text, body.sql_text, body.sql_text, gid))
    return {"ok": True}


@router.delete("/golden-queries/{gid}")
async def golden_delete(gid: int, user: CurrentUser = Depends(_admin)):
    await run_in_threadpool(_exec, "DELETE FROM meta.golden_query WHERE id = %s", (gid,))
    return {"ok": True}


@router.post("/golden-queries/{gid}/verify")
async def golden_verify(gid: int, user: CurrentUser = Depends(_admin)):
    await run_in_threadpool(_exec, "UPDATE meta.golden_query SET verified_by = %s, verified_at = %s WHERE id = %s",
                            (user.username, date.today(), gid))
    return {"ok": True}


# ── Playground ───────────────────────────────────────────────────────────────

class SqlIn(BaseModel):
    sql: str
    group: str = "ebs-management"


def _tool_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except sql_guard.SqlRejected as e:
        raise HTTPException(400, str(e))
    except AccessDenied as e:
        raise HTTPException(403, str(e))
    except QueryFailed as e:
        raise HTTPException(422, str(e))


@router.post("/sql")
async def run_sql(body: SqlIn, user: CurrentUser = Depends(_admin)):
    if body.group not in EBS_GROUPS:
        raise HTTPException(400, "Grup tidak dikenal")
    caller = _admin_caller(user, body.group)
    return await run_in_threadpool(_tool_call, tools.run_sql, caller, body.sql, "admin playground")


_INTENT_TOOLS = {
    "find_marts": tools.find_marts,
    "get_data_freshness": tools.get_data_freshness,
    "get_ap_aging": tools.get_ap_aging,
    "get_ap_open_invoices": tools.get_ap_open_invoices,
    "get_ap_payments": tools.get_ap_payments,
    "get_ap_holds": tools.get_ap_holds,
    "get_expiring_lots": tools.get_expiring_lots,
    "get_stock_onhand": tools.get_stock_onhand,
    "get_stock_movement": tools.get_stock_movement,
}


class ToolIn(BaseModel):
    args: dict = {}
    group: str = "ebs-management"


@router.post("/tool/{name}")
async def call_tool(name: str, body: ToolIn, user: CurrentUser = Depends(_admin)):
    fn = _INTENT_TOOLS.get(name)
    if not fn:
        raise HTTPException(400, f"Tool tidak dikenal: {name}")
    if body.group not in EBS_GROUPS:
        raise HTTPException(400, "Grup tidak dikenal")
    # "" = not given (tool default); explicit null = "no filter".
    args = {k: v for k, v in body.args.items() if v != ""}
    for k in ("due_from", "due_to", "date_from", "date_to"):
        if args.get(k) is not None:
            try:
                args[k] = date.fromisoformat(str(args[k]))
            except ValueError:
                raise HTTPException(400, f"{k} harus YYYY-MM-DD")
    for k in ("days", "min_days_overdue"):
        if args.get(k) is not None:
            args[k] = int(args[k])
    caller = _admin_caller(user, body.group)
    try:
        return await run_in_threadpool(_tool_call, fn, caller, **args)
    except TypeError as e:
        raise HTTPException(400, f"Argumen tidak valid: {e}")


# ── Security self-test (blueprint section 11, "Uji keamanan tool server") ────

_NEGATIVE_SQL = [
    ("DELETE ditolak", "DELETE FROM mart.ap_open_invoice"),
    ("UPDATE ditolak", "UPDATE mart.ap_open_invoice SET vendor_name = 'x'"),
    ("INSERT ditolak", "INSERT INTO mart.ap_open_invoice (invoice_id) VALUES (1)"),
    ("DROP ditolak", "DROP TABLE mart.ap_open_invoice"),
    ("Multi-statement ditolak", "SELECT 1 FROM mart.ap_open_invoice; DROP TABLE mart.ap_open_invoice"),
    ("raw.* ditolak", "SELECT * FROM raw.ap_invoices_all"),
    ("core.* ditolak", "SELECT * FROM core.fact_ap_payment_schedule"),
    ("pg_catalog ditolak", "SELECT * FROM pg_catalog.pg_authid"),
    ("information_schema ditolak", "SELECT * FROM information_schema.tables"),
    ("eis.* ditolak", "SELECT * FROM eis.fact_sales"),
    ("Subquery ke tabel lain ditolak", "SELECT (SELECT COUNT(*) FROM public.employees) FROM mart.ap_open_invoice"),
    ("pg_sleep ditolak", "SELECT pg_sleep(20) FROM mart.ap_open_invoice"),
    ("set_config ditolak", "SELECT set_config('statement_timeout', '0', false) FROM mart.ap_open_invoice"),
    ("SELECT INTO ditolak", "SELECT * INTO mart.x FROM mart.ap_open_invoice"),
    ("FOR UPDATE ditolak", "SELECT * FROM mart.ap_open_invoice FOR UPDATE"),
]


def _security_test(user: CurrentUser) -> dict:
    results = []
    # Test calls are tagged source='security-test' so they stay out of the
    # audit views and usage stats, and so the last check can count them.
    admin = _admin_caller(user, source="security-test")
    before = _rows("SELECT COALESCE(MAX(id), 0) AS id FROM meta.chat_query_log")[0]["id"]

    for label, sql in _NEGATIVE_SQL:
        try:
            tools.run_sql(admin, sql, "security-test")
            results.append({"test": label, "passed": False, "detail": "Query LOLOS guardrail"})
        except sql_guard.SqlRejected as e:
            results.append({"test": label, "passed": True, "detail": str(e)})
        except Exception as e:
            results.append({"test": label, "passed": True, "detail": f"Ditolak di database: {e}"})

    # Cross-domain 403: warehouse must not read AP (gl_* is not built yet;
    # AP is the finance mart that exists today).
    wh = _admin_caller(user, "ebs-warehouse", source="security-test")
    try:
        tools.run_sql(wh, "SELECT COUNT(*) FROM mart.ap_open_invoice", "security-test")
        results.append({"test": "Grup gudang ditolak membaca mart AP", "passed": False, "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "Grup gudang ditolak membaca mart AP", "passed": True, "detail": str(e)})
    try:
        tools.get_ap_aging(wh)
        results.append({"test": "Grup gudang ditolak intent tool AP", "passed": False, "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "Grup gudang ditolak intent tool AP", "passed": True, "detail": str(e)})
    nobody = Caller(email=admin.email, groups=set(), source="security-test")
    try:
        tools.run_sql(nobody, "SELECT COUNT(*) FROM mart.inv_onhand_lot", "security-test")
        results.append({"test": "User tanpa grup EBS ditolak", "passed": False, "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "User tanpa grup EBS ditolak", "passed": True, "detail": str(e)})

    # The reader connection itself: read-only, timeout, and no write grant.
    conn = query._reader()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cur.execute("SHOW statement_timeout")
            timeout = cur.fetchone()[0]
            cur.execute("SHOW transaction_read_only")
            ro = cur.fetchone()[0]
            cur.execute("SELECT current_user")
            role = cur.fetchone()[0]
            cur.execute("SELECT has_schema_privilege(current_user, 'core', 'USAGE')")
            core_usage = cur.fetchone()[0]
        conn.rollback()
    finally:
        conn.close()
    results.append({"test": f"statement_timeout = {STATEMENT_TIMEOUT}", "passed": timeout == STATEMENT_TIMEOUT, "detail": timeout})
    results.append({"test": "Koneksi reader read-only", "passed": ro == "on", "detail": f"transaction_read_only={ro}"})
    results.append({"test": "Role reader tanpa akses core.*", "passed": not core_usage,
                    "detail": f"role={role}, USAGE core={core_usage}"
                              + ("" if role == "llm_ro" else " — role llm_ro belum dipakai (EIS_LLM_RO_URL kosong)")})

    # Heavy query stops at the timeout (runs as a real query through run_sql).
    try:
        tools.run_sql(admin, "SELECT COUNT(*) FROM mart.inv_movement_daily a CROSS JOIN mart.inv_movement_daily b "
                             "CROSS JOIN mart.inv_movement_daily c CROSS JOIN mart.inv_movement_daily d",
                      "security-test")
        results.append({"test": "Query berat berhenti di timeout", "passed": None,
                        "detail": "Query selesai sebelum timeout (data masih kecil) — tidak terbukti"})
    except QueryFailed as e:
        results.append({"test": "Query berat berhenti di timeout", "passed": "statement_timeout" in str(e), "detail": str(e)})

    # Every call above must be in the audit log.
    logged = _rows("""SELECT COUNT(*) AS n FROM meta.chat_query_log
                       WHERE id > %s AND source = 'security-test'""", (before,))[0]["n"]
    expected = len(_NEGATIVE_SQL) + 3 + 1
    results.append({"test": "Setiap panggilan tercatat di meta.chat_query_log", "passed": logged >= expected,
                    "detail": f"{logged} baris tercatat (diharapkan ≥ {expected})"})

    passed = sum(1 for r in results if r["passed"] is True)
    return {"passed": passed, "total": len(results), "results": results}


@router.post("/security-test")
async def security_test(user: CurrentUser = Depends(_admin)):
    return await run_in_threadpool(_security_test, user)


# ── Audit log ────────────────────────────────────────────────────────────────

@router.get("/query-log")
async def query_log(
    user_email: Optional[str] = None, status: Optional[str] = None, tool: Optional[str] = None,
    limit: int = Query(100, le=1000), user: CurrentUser = Depends(_admin),
):
    return await run_in_threadpool(_rows, """
        SELECT id, user_email, chat_id, source, groups, tool_name, tool_args, question, sql_text, marts,
               row_count, truncated, duration_ms, status, error_msg, created_at
          FROM meta.chat_query_log
         WHERE (%(u)s::text IS NULL OR user_email ILIKE %(u)s::text)
           AND (%(s)s::text IS NULL OR status = %(s)s::text)
           AND (%(t)s::text IS NULL OR tool_name = %(t)s::text)
           AND COALESCE(source, '') <> 'security-test'
         ORDER BY created_at DESC LIMIT %(l)s""",
        {"u": f"%{user_email}%" if user_email else None, "s": status, "t": tool, "l": limit})


@router.get("/query-log/stats")
async def query_log_stats(days: int = Query(30, le=365), user: CurrentUser = Depends(_admin)):
    params = {"d": days}
    per_tool = await run_in_threadpool(_rows, """
        SELECT tool_name,
               COUNT(*)                                                     AS calls,
               COUNT(*) FILTER (WHERE status = 'OK')                        AS ok,
               COUNT(*) FILTER (WHERE status IN ('ERROR','TIMEOUT'))        AS errors,
               COUNT(*) FILTER (WHERE status = 'REJECTED')                  AS rejected,
               COUNT(*) FILTER (WHERE status = 'DENIED')                    AS denied,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms)     AS median_ms,
               COUNT(DISTINCT user_email)                                   AS users
          FROM meta.chat_query_log
         WHERE created_at > now() - make_interval(days => %(d)s)
           AND COALESCE(source, '') <> 'security-test'
         GROUP BY tool_name ORDER BY calls DESC""", params)
    per_day = await run_in_threadpool(_rows, """
        SELECT DATE(created_at AT TIME ZONE 'Asia/Jakarta') AS day, COUNT(*) AS calls,
               COUNT(*) FILTER (WHERE status <> 'OK') AS not_ok
          FROM meta.chat_query_log
         WHERE created_at > now() - make_interval(days => %(d)s)
           AND COALESCE(source, '') <> 'security-test'
         GROUP BY 1 ORDER BY 1""", params)
    return {"per_tool": per_tool, "per_day": per_day}


# ── Subinventory classification ──────────────────────────────────────────────

@router.get("/subinventories")
async def subinventories(user: CurrentUser = Depends(_admin)):
    return await run_in_threadpool(_rows, """
        SELECT s.subinventory_code, s.description, s.availability_type, s.disable_date, s.guessed_type,
               c.subinventory_type AS official_type, c.notes, c.updated_by, c.updated_at,
               COALESCE(c.subinventory_type, s.guessed_type, 'GOOD') AS effective_type
          FROM core.dim_subinventory s
          LEFT JOIN meta.subinventory_class c ON c.subinventory_code = s.subinventory_code
         ORDER BY s.subinventory_code""")


class SubinvIn(BaseModel):
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = None
    notes: Optional[str] = None


@router.put("/subinventories/{code}")
async def set_subinventory(code: str, body: SubinvIn, user: CurrentUser = Depends(_admin)):
    if body.subinventory_type is None:
        await run_in_threadpool(_exec, "DELETE FROM meta.subinventory_class WHERE subinventory_code = %s", (code,))
    else:
        await run_in_threadpool(_exec, """
            INSERT INTO meta.subinventory_class (subinventory_code, subinventory_type, notes, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (subinventory_code) DO UPDATE SET subinventory_type = EXCLUDED.subinventory_type,
                notes = EXCLUDED.notes, updated_by = EXCLUDED.updated_by, updated_at = now()""",
            (code, body.subinventory_type, body.notes, user.username))
    from app.services.ebs_mart.schema import refresh_marts
    result = await run_in_threadpool(refresh_marts, ["inv_onhand_lot"])
    return {"ok": True, "refresh": result}


# ── Open WebUI kit ───────────────────────────────────────────────────────────

@router.get("/openwebui-kit")
async def openwebui_kit(user: CurrentUser = Depends(_admin)):
    # Path only — the page prefixes window.location.origin, which carries the
    # right scheme (nginx does not forward X-Forwarded-Proto).
    base = "/api/v1/ebs-tools"

    def read(name):
        return (_KIT / name).read_text(encoding="utf-8")

    return {
        "tool_server": {"url": base, "openapi": "openapi.json", "docs": f"{base}/docs"},
        "system_prompt": read("system_prompt.md"),
        "skills": [{"name": p.stem, "content": p.read_text(encoding="utf-8")}
                   for p in sorted((_KIT / "skills").glob("*.md"))],
        "prompts": json.loads(read("prompts.json")),
        "filter": read("filter_ebs_context.py"),
        "action": read("action_export_excel.py"),
        "model_settings": {
            "name": "EBS Analyst",
            "function_calling": "Native",
            "temperature": "default (Claude Opus 5.5 menolak parameter temperature)",
            "context_length_min": 16384,
            "memory": "Nonaktif",
            "web_search": "Nonaktif",
            "access": "Grup ebs-* saja",
        },
    }
