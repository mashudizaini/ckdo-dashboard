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
  GET    /access-policy              roles, grants (mart x level), marts with their money columns
  PUT    /access-policy/roles/{code} create / edit an access role
  DELETE /access-policy/roles/{code} remove a role (its grants go with it)
  PUT    /access-policy/grant        set one role x mart to full / qty / none
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, Roles, require_role
from app.services.ebs_mart import policy, query, sa_tools, sql_guard, tools
from app.services.ebs_mart.access import AccessDenied, Caller
from app.services.ebs_mart.constants import (
    DOMAIN_BY_GROUP, EBS_GROUPS, GROUP_LABELS, MARTS, MAX_ROWS, SA_READER_ROLE, STATEMENT_TIMEOUT,
    SYSADMIN_ALLOWLIST,
)
from app.services.ebs_mart.query import QueryFailed

router = APIRouter()
_admin = require_role(Roles.IT, Roles.ADMIN)
_KIT = Path(__file__).resolve().parents[2] / "services" / "ebs_mart" / "openwebui_kit"

JOBS = {
    "etl_mart_ap": "AP (incremental)",
    "etl_mart_inventory": "Inventory on-hand per lot (snapshot)",
    "etl_inventory_txn": "Mutasi inventory (sumber inv_movement_daily)",
    "etl_mart_po": "PO & PR (incremental)",
    "etl_mart_item_cost": "Biaya OPM PMAC (valuasi)",
    "etl_mart_om": "Sales order & pengiriman (incremental)",
    "etl_mart_ar": "Piutang, invoice & penerimaan kas (incremental)",
    "etl_mart_opm": "Batch produksi OPM (incremental)",
    "etl_mart_gl": "GL: saldo, jurnal & laba rugi (incremental)",
    "etl_mart_close": "Closing: status periode, selisih SLA-GL, AutoInvoice, rekon bank (per jam)",
    "etl_mart_fa": "Aset tetap & penyusutan (harian)",
    "etl_mart_ext": "Approval PO/PR, hold SO, withholding, budget, interface (per jam)",
    "etl_mart_sa": "System Administration: user, akses, profile, login, patch (harian)",
    "etl_mart_sa_ops": "System Administration: concurrent request/manager & workflow (10 menit)",
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
            "groups": [{"group": code, "label": r["label"], "all_access": r["all_access"],
                        "marts": sorted(policy.load()["grants"].get(code, {}))}
                       for code, r in sorted(policy.load()["roles"].items())],
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
    if job in ("etl_mart_ap", "etl_mart_po", "etl_mart_om", "etl_mart_ar", "etl_mart_opm", "etl_mart_gl") and body.full_refresh:
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
        # Template placeholders like '<kode item>' / '<nomor PO>' stand for a
        # value; they are always quoted literals, so only those are replaced.
        sql_guard.validate(re.sub(r"'<[^'<>]+>'", "'X'", sql))
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
    if body.group not in policy.role_codes():
        raise HTTPException(400, "Grup tidak dikenal")
    caller = _admin_caller(user, body.group)
    return await run_in_threadpool(_tool_call, tools.run_sql, caller, body.sql, "admin playground")


_INTENT_TOOLS = {
    "find_marts": tools.find_marts,
    "get_data_freshness": tools.get_data_freshness,
    "ap_get_aging": tools.ap_get_aging,
    "ap_get_open_invoices": tools.ap_get_open_invoices,
    "ap_get_payments": tools.ap_get_payments,
    "ap_get_holds": tools.ap_get_holds,
    "inv_get_expiring_lots": tools.inv_get_expiring_lots,
    "inv_get_onhand": tools.inv_get_onhand,
    "inv_get_movements": tools.inv_get_movements,
    "po_get_outstanding": tools.po_get_outstanding,
    "po_get_match_status": tools.po_get_match_status,
    "pr_get_pending": tools.pr_get_pending,
    "inv_get_valuation": tools.inv_get_valuation,
    "ar_get_aging": tools.ar_get_aging,
    "ar_get_open_invoices": tools.ar_get_open_invoices,
    "ar_get_receipts": tools.ar_get_receipts,
    "so_get_backlog": tools.so_get_backlog,
    "so_get_shipment_status": tools.so_get_shipment_status,
    "sales_get_summary": tools.sales_get_summary,
    "opm_get_batch": tools.opm_get_batch,
    "opm_get_yield": tools.opm_get_yield,
    "opm_get_material_usage": tools.opm_get_material_usage,
    "gl_get_pl": tools.gl_get_pl,
    "gl_get_trial_balance": tools.gl_get_trial_balance,
    "gl_get_journals": tools.gl_get_journals,
    **{name: getattr(tools, name) for name in ("gl_get_period_status", "gl_get_subledger_gap", "po_get_uninvoiced_receipts", "so_get_shipped_not_invoiced", "ar_get_unapplied_receipts", "ar_get_autoinvoice_errors", "opm_get_open_batches", "ce_get_unreconciled", "fa_get_assets", "fa_get_depreciation")},
    # System Administration: allowed only when the signed-in admin's own email
    # is in SYSADMIN_ALLOWLIST — the group chosen here does not matter.
    **{name: getattr(sa_tools, name) for name in (
        "sa_get_user", "sa_get_user_resps", "sa_who_has_resp", "sa_who_has_function", "sa_get_resp_functions",
        "sa_get_resp_programs", "sa_get_dormant_users", "sa_get_terminated_active_users", "sa_get_sod_violations",
        "sa_get_profile_value", "sa_get_login_history", "sa_get_manager_status", "sa_get_pending_approvals",
        "sa_check_patch", "sa_get_form_personalizations", "it_get_concurrent_requests", "it_get_interface_errors")},
    **{name: getattr(tools, name) for name in ("lookup_master", "po_get_document", "po_get_pending_approval", "ap_get_invoice", "ap_get_due_forecast", "ap_get_withholding", "so_get_order", "so_get_holds", "ar_get_customer_balance", "inv_get_stock_card", "inv_get_slow_moving", "opm_get_item_cost", "gl_get_account_movement", "gl_get_budget_vs_actual",
                                               "pac_get_business_plan", "pac_get_sales_plan_vs_actual")},
}


class ToolIn(BaseModel):
    args: dict = {}
    group: str = "ebs-management"


@router.post("/tool/{name}")
async def call_tool(name: str, body: ToolIn, user: CurrentUser = Depends(_admin)):
    fn = _INTENT_TOOLS.get(name)
    if not fn:
        raise HTTPException(400, f"Tool tidak dikenal: {name}")
    if body.group not in policy.role_codes():
        raise HTTPException(400, "Grup tidak dikenal")
    # "" = not given (tool default); explicit null = "no filter".
    args = {k: v for k, v in body.args.items() if v != ""}
    for flag in ("late_only", "include_reversed", "include_expired", "ytd", "compare_prior_year",
                 "include_inactive", "exclude_seeded", "include_seeded", "only_problems", "include_fyi",
                 "include_unheld", "include_errors", "include_revenue", "include_incomplete"):
        if isinstance(args.get(flag), str):
            args[flag] = args[flag] == "true"
    for k in ("due_from", "due_to", "date_from", "date_to", "ordered_from", "ordered_to"):
        if args.get(k) is not None:
            try:
                args[k] = date.fromisoformat(str(args[k]))
            except ValueError:
                raise HTTPException(400, f"{k} harus YYYY-MM-DD")
    for k in ("days", "min_days_overdue", "min_days_waiting", "hours", "days_open", "weeks_ahead", "min_days",
              "days_no_movement"):
        if args.get(k) is not None:
            args[k] = int(args[k])
    for k in ("below_pct", "over_pct", "min_amount"):
        if args.get(k) is not None:
            args[k] = float(args[k])
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


def _mart_cols(mart: str):
    from app.services.ebs_mart.schema import mart_columns
    conn = query._rw()
    try:
        with conn.cursor() as cur:
            return mart_columns(cur, mart)
    finally:
        conn.close()


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
        tools.ap_get_aging(wh)
        results.append({"test": "Grup gudang ditolak intent tool AP", "passed": False, "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "Grup gudang ditolak intent tool AP", "passed": True, "detail": str(e)})
    nobody = Caller(email=admin.email, groups=set(), source="security-test")
    try:
        tools.run_sql(nobody, "SELECT COUNT(*) FROM mart.inv_onhand_lot", "security-test")
        results.append({"test": "User tanpa grup EBS ditolak", "passed": False, "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "User tanpa grup EBS ditolak", "passed": True, "detail": str(e)})

    # Quantity-only access (policy): money columns never leave the dashboard.
    qty_cases = [(r, m) for r, g in policy.load()["grants"].items() for m, lv in g.items() if lv == "qty"]
    if qty_cases:
        role, mart = qty_cases[0]
        qc = Caller(email="qty-check@ckd-otto.com", groups={role}, source="security-test")
        try:
            tools.run_sql(qc, f"SELECT * FROM mart.{mart}", "security-test")
            results.append({"test": f"Akses kuantitas ({role} → {mart}): SELECT * ditolak", "passed": False,
                            "detail": "Tidak ditolak"})
        except AccessDenied as e:
            results.append({"test": f"Akses kuantitas ({role} → {mart}): SELECT * ditolak", "passed": True,
                            "detail": str(e)})
        cols = [c for c, _ in _mart_cols(mart)]
        money = [c for c in cols if policy.is_money(c)]
        plain = [c for c in cols if not policy.is_money(c)][:3]
        if money:
            try:
                tools.run_sql(qc, f"SELECT {money[0]} AS x FROM mart.{mart}", "security-test")
                results.append({"test": f"Akses kuantitas: kolom nilai {money[0]} ditolak walau di-alias",
                                "passed": False, "detail": "Tidak ditolak"})
            except AccessDenied as e:
                results.append({"test": f"Akses kuantitas: kolom nilai {money[0]} ditolak walau di-alias",
                                "passed": True, "detail": str(e)})
        if plain:
            r = tools.run_sql(qc, f"SELECT {', '.join(plain)} FROM mart.{mart}", "security-test")
            results.append({"test": "Akses kuantitas: kolom non-nilai tetap terbaca", "passed": r["row_count"] >= 0,
                            "detail": f"{r['row_count']} baris, kolom {r['columns']}"})

    # System Administration: three fences (blueprint v2 section 7).
    outsider = Caller(email="bukan-sysadmin@ckd-otto.com", groups={"ebs-management"}, source="security-test")
    try:
        sa_tools.sa_get_user(outsider, "SYSADMIN")
        results.append({"test": "SA: email di luar allowlist ditolak (walau grup ebs-management)", "passed": False,
                        "detail": "Tidak ditolak"})
    except AccessDenied as e:
        results.append({"test": "SA: email di luar allowlist ditolak (walau grup ebs-management)", "passed": True,
                        "detail": str(e)})
    sa_admin = Caller(email=sorted(SYSADMIN_ALLOWLIST)[0], groups=set(), source="security-test")
    try:
        tools.run_sql(sa_admin, "SELECT COUNT(*) FROM mart.sa_user", "security-test")
        results.append({"test": "SA: run_sql ke mart.sa_* ditolak (juga untuk allowlist)", "passed": False,
                        "detail": "Tidak ditolak"})
    except (AccessDenied, sql_guard.SqlRejected) as e:
        results.append({"test": "SA: run_sql ke mart.sa_* ditolak (juga untuk allowlist)", "passed": True,
                        "detail": str(e)})
    conn = query._reader()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, has_table_privilege(current_user, 'mart.sa_user', 'SELECT')")
            role, can = cur.fetchone()
        conn.rollback()
    finally:
        conn.close()
    results.append({"test": "SA: role reader biasa tanpa grant ke mart.sa_*", "passed": not can,
                    "detail": f"role={role}, SELECT mart.sa_user={can}"})
    try:
        conn = query._sa_reader()
        try:
            with conn.cursor() as cur:
                cur.execute("""SELECT current_user,
                                      has_table_privilege(current_user, 'mart.sa_user', 'SELECT'),
                                      has_table_privilege(current_user, 'mart.ap_open_invoice', 'SELECT'),
                                      has_schema_privilege(current_user, 'core', 'USAGE')""")
                sa_role, sa_can, sa_ap, sa_core = cur.fetchone()
            conn.rollback()
        finally:
            conn.close()
        results.append({"test": f"SA: tool sa_* membaca sebagai {SA_READER_ROLE}, hanya mart.sa_*",
                        "passed": sa_role == SA_READER_ROLE and sa_can and not sa_ap and not sa_core,
                        "detail": f"role={sa_role}, sa_user={sa_can}, ap_open_invoice={sa_ap}, core={sa_core}"})
    except Exception as e:
        results.append({"test": f"SA: tool sa_* membaca sebagai {SA_READER_ROLE}, hanya mart.sa_*", "passed": False,
                        "detail": f"Koneksi {SA_READER_ROLE} gagal: {e}"})

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
    expected = len(_NEGATIVE_SQL) + 3 + 1 + 2
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


# ── Access policy (Setup > AI > EBS Chat Access) ─────────────────────────────

_ROLE_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _scope_rows(sql: str, params=None) -> list[dict]:
    """ebs_chat_scope belongs to the dashboard's own database role, not the
    EIS role _rows connects as — read it the way ebs_chat_service does."""
    from app.services.ebs_chat_service import _get_pg
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def _money_columns() -> dict[str, list[str]]:
    from app.services.ebs_mart.schema import mart_columns
    out = {}
    conn = query._rw()
    try:
        with conn.cursor() as cur:
            for name in policy._mart_names():
                out[name] = [c for c, _ in mart_columns(cur, name) if policy.is_money(c)]
    finally:
        conn.close()
    return out


@router.get("/access-policy")
async def access_policy(user: CurrentUser = Depends(_admin)):
    policy.invalidate()
    p = await run_in_threadpool(policy.load)
    money = await run_in_threadpool(_money_columns)
    marts = [{"mart": m, "domain": MARTS[m]["domain"], "phase": MARTS[m]["phase"],
              "description": MARTS[m]["description"], "money_columns": money.get(m, []),
              "explicit_grant": policy.is_explicit(m)}
             for m in policy._mart_names()]
    users = await run_in_threadpool(_scope_rows, """
        SELECT g AS role_code, COUNT(*) AS users FROM ebs_chat_scope, jsonb_array_elements_text(ebs_groups) g
         GROUP BY g""")
    return {"roles": [{"role_code": c, **r, "users": next((u["users"] for u in users if u["role_code"] == c), 0)}
                      for c, r in sorted(p["roles"].items())],
            "grants": [{"role_code": c, "mart": m, "level": lv} for c, g in p["grants"].items() for m, lv in g.items()],
            "marts": marts, "levels": list(policy.LEVELS)}


class RoleIn(BaseModel):
    label: str
    description: Optional[str] = None
    all_access: bool = False


@router.put("/access-policy/roles/{code}")
async def upsert_role(code: str, body: RoleIn, user: CurrentUser = Depends(_admin)):
    code = code.strip().lower()
    if not _ROLE_CODE.match(code):
        raise HTTPException(400, "Role code: lowercase letters, digits and hyphens, 2–41 characters (e.g. ebs-purchasing-stock).")
    if not body.label.strip():
        raise HTTPException(400, "Role name is required.")
    await run_in_threadpool(_exec, """
        INSERT INTO meta.access_role (role_code, label, description, all_access, updated_by, updated_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (role_code) DO UPDATE SET label = EXCLUDED.label, description = EXCLUDED.description,
               all_access = EXCLUDED.all_access, updated_by = EXCLUDED.updated_by, updated_at = now()""",
        (code, body.label.strip(), body.description, body.all_access, user.email or user.username))
    policy.invalidate()
    return {"message": f"Role {code} saved"}


@router.delete("/access-policy/roles/{code}")
async def delete_role(code: str, user: CurrentUser = Depends(_admin)):
    used = await run_in_threadpool(_scope_rows, """
        SELECT email FROM ebs_chat_scope WHERE ebs_groups ? %s ORDER BY email""", (code,))
    if used:
        raise HTTPException(400, f"Role {code} is still assigned to {len(used)} user(s) ("
                                 f"{', '.join(u['email'] for u in used[:5])}{'…' if len(used) > 5 else ''}). "
                                 "Remove it from them first.")
    n = await run_in_threadpool(_exec, "DELETE FROM meta.access_role WHERE role_code = %s", (code,))
    policy.invalidate()
    if not n:
        raise HTTPException(404, "Role not found")
    return {"message": f"Role {code} deleted"}


class GrantIn(BaseModel):
    role_code: str
    mart: str
    level: Optional[Literal["full", "qty"]] = None  # None = no access


@router.put("/access-policy/grant")
async def set_grant(body: GrantIn, user: CurrentUser = Depends(_admin)):
    if body.mart not in policy._mart_names():
        raise HTTPException(400, "Unknown data set (System Administration data is governed by the IT allowlist, not here).")
    if body.role_code not in policy.role_codes():
        raise HTTPException(400, "Unknown role")
    if body.level is None:
        await run_in_threadpool(_exec, "DELETE FROM meta.access_grant WHERE role_code = %s AND mart_name = %s",
                                (body.role_code, body.mart))
    else:
        await run_in_threadpool(_exec, """
            INSERT INTO meta.access_grant (role_code, mart_name, level, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (role_code, mart_name) DO UPDATE SET level = EXCLUDED.level,
                   updated_by = EXCLUDED.updated_by, updated_at = now()""",
            (body.role_code, body.mart, body.level, user.email or user.username))
    policy.invalidate()
    return {"message": "Saved"}
