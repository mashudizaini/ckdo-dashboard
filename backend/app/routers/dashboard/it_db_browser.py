"""
IT Database Browser Router
─────────────────────────────────────────
Route prefix : /api/v1/dashboard/it/db-browser
Required role: it_staff OR admin

An in-dashboard object browser + SQL console for the app's own PostgreSQL
database (ckdo_dashboard) — lets IT see every table/view/sequence/function
that exists, browse data, delete rows, and run arbitrary SQL to
create/alter/drop objects, without a separate DB tool.

Structurally scoped to this database only: the connection (app.database)
only ever points at ckdo_dashboard, even though the same Postgres instance
also hosts a separate `keycloak` database for auth — there is no code path
here that can reach it.

Every statement run through the SQL console (and every row delete) is
recorded in db_browser_audit_log for accountability. Statements that look
destructive (DROP/TRUNCATE, or DELETE/UPDATE with no WHERE clause) are
rejected unless resubmitted with confirm=true.

Endpoints:
  GET    /objects                          — list tables/views/sequences/functions
  GET    /objects/{schema}/{table}/structure — columns, primary key, foreign keys, indexes
  GET    /objects/{schema}/{table}/data      — paginated row data
  DELETE /objects/{schema}/{table}/rows      — delete one row by primary key
  POST   /query                              — run arbitrary SQL (the console)
  GET    /audit-log                          — recent executions
"""
import re
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import sqlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.db_browser_audit import DbBrowserAuditLog

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

def _jsonify(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    return v


def _row_to_dict(row) -> dict:
    return {k: _jsonify(v) for k, v in row._mapping.items()}


def _qi(name: str) -> str:
    """Quote a Postgres identifier we already validated against pg_catalog."""
    return '"' + name.replace('"', '""') + '"'


def _pretty_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("bytes", "kB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


async def _validate_object(db: AsyncSession, schema: str, table: str):
    result = await db.execute(
        text("""
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :table AND c.relkind IN ('r','v','m')
        """),
        {"schema": schema, "table": table},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail=f"Object {schema}.{table} not found")


async def _get_pk_columns(db: AsyncSession, schema: str, table: str) -> list[str]:
    result = await db.execute(
        text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = :schema AND tc.table_name = :table
            ORDER BY kcu.ordinal_position
        """),
        {"schema": schema, "table": table},
    )
    return [r[0] for r in result.fetchall()]


async def _log_audit(
    db: AsyncSession, user: CurrentUser, sql: str, statement_type: str,
    success: bool, error: Optional[str], rows_affected: Optional[int], duration_ms: Optional[int],
):
    """Commits independently of the statement's own transaction so the audit
    trail survives even when the statement itself failed and was rolled back."""
    log = DbBrowserAuditLog(
        executed_by=user.username or user.email or "unknown",
        sql_text=sql[:10000],
        statement_type=statement_type,
        success=success,
        error_message=(error[:2000] if error else None),
        rows_affected=rows_affected,
        duration_ms=duration_ms,
    )
    db.add(log)
    await db.commit()


_DANGEROUS_TYPES = ("DROP", "TRUNCATE")


def _classify_and_check(sql: str) -> tuple[str, bool]:
    """Returns (statement_type, requires_confirmation)."""
    stripped = sql.strip().rstrip(";").strip()
    m = re.match(r"^\s*(\w+)", stripped)
    stype = m.group(1).upper() if m else "OTHER"
    upper = f" {stripped.upper()} "
    requires_confirm = stype in _DANGEROUS_TYPES
    if stype in ("DELETE", "UPDATE") and " WHERE " not in upper:
        requires_confirm = True
    return stype, requires_confirm


# ── Object listing ───────────────────────────────────────────────────────────

@router.get("/objects")
async def list_objects(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    rel_result = await db.execute(text("""
        SELECT
          n.nspname AS schema,
          c.relname AS name,
          CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view' WHEN 'm' THEN 'materialized_view' END AS type,
          (c.relpages::bigint * 8192)                                       AS size_bytes,
          GREATEST(c.reltuples, 0)::bigint                                  AS row_estimate
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r','v','m')
          AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
        ORDER BY n.nspname, c.relname
    """))
    # relpages/reltuples come straight from pg_class (updated by autovacuum/
    # analyze) — reading them is essentially free, unlike pg_total_relation_size()
    # which does a live size computation per relation and gets noticeably slow
    # once there are a lot of objects to list.
    relations = [_row_to_dict(r) for r in rel_result.fetchall()]
    for r in relations:
        r["size_pretty"] = _pretty_size(r["size_bytes"])

    seq_result = await db.execute(text("""
        SELECT sequence_schema AS schema, sequence_name AS name, data_type
        FROM information_schema.sequences
        WHERE sequence_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY sequence_schema, sequence_name
    """))
    sequences = [_row_to_dict(r) for r in seq_result.fetchall()]

    func_result = await db.execute(text("""
        SELECT n.nspname AS schema, p.proname AS name,
               pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
               t.typname AS return_type
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_type t ON t.oid = p.prorettype
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
        ORDER BY n.nspname, p.proname
    """))
    functions = [_row_to_dict(r) for r in func_result.fetchall()]

    return {
        "tables":    [t for t in relations if t["type"] in ("table", "materialized_view")],
        "views":     [t for t in relations if t["type"] == "view"],
        "sequences": sequences,
        "functions": functions,
    }


# ── Structure ─────────────────────────────────────────────────────────────

@router.get("/objects/{schema}/{table}/structure")
async def get_structure(
    schema: str, table: str,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    await _validate_object(db, schema, table)

    cols_result = await db.execute(
        text("""
            SELECT column_name, data_type, is_nullable, column_default, character_maximum_length, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
        """),
        {"schema": schema, "table": table},
    )
    columns = [_row_to_dict(r) for r in cols_result.fetchall()]

    pk_cols = await _get_pk_columns(db, schema, table)
    for c in columns:
        c["is_primary_key"] = c["column_name"] in pk_cols

    fk_result = await db.execute(
        text("""
            SELECT kcu.column_name, ccu.table_schema AS foreign_schema,
                   ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = :schema AND tc.table_name = :table
        """),
        {"schema": schema, "table": table},
    )
    foreign_keys = [_row_to_dict(r) for r in fk_result.fetchall()]

    idx_result = await db.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = :schema AND tablename = :table"),
        {"schema": schema, "table": table},
    )
    indexes = [_row_to_dict(r) for r in idx_result.fetchall()]

    return {"columns": columns, "primary_key": pk_cols, "foreign_keys": foreign_keys, "indexes": indexes}


# ── Data browse ───────────────────────────────────────────────────────────

@router.get("/objects/{schema}/{table}/data")
async def get_data(
    schema: str, table: str,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    await _validate_object(db, schema, table)
    ident = f"{_qi(schema)}.{_qi(table)}"

    total = (await db.execute(text(f"SELECT COUNT(*) FROM {ident}"))).scalar()
    offset = (page - 1) * page_size
    result = await db.execute(
        text(f"SELECT * FROM {ident} LIMIT :limit OFFSET :offset"),
        {"limit": page_size, "offset": offset},
    )
    columns = list(result.keys())
    rows = [[_jsonify(v) for v in row] for row in result.fetchall()]
    pk_cols = await _get_pk_columns(db, schema, table)

    return {"columns": columns, "rows": rows, "total": total, "page": page, "page_size": page_size, "primary_key": pk_cols}


# ── Delete row ────────────────────────────────────────────────────────────

class DeleteRowBody(BaseModel):
    pk: dict[str, Any]


@router.delete("/objects/{schema}/{table}/rows")
async def delete_row(
    schema: str, table: str, body: DeleteRowBody,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    await _validate_object(db, schema, table)
    pk_cols = await _get_pk_columns(db, schema, table)
    if not pk_cols:
        raise HTTPException(status_code=400, detail="Table has no primary key — delete rows via the SQL Console instead")
    if set(body.pk.keys()) != set(pk_cols):
        raise HTTPException(status_code=400, detail=f"Must supply values for exactly these primary key columns: {pk_cols}")

    ident = f"{_qi(schema)}.{_qi(table)}"
    where_clause = " AND ".join(f"{_qi(c)} = :{c}" for c in pk_cols)
    sql = f"DELETE FROM {ident} WHERE {where_clause}"

    try:
        result = await db.execute(text(sql), body.pk)
        await _log_audit(db, user, sql, "DELETE", True, None, result.rowcount, None)
        return {"success": True, "rows_deleted": result.rowcount}
    except Exception as e:
        await db.rollback()
        await _log_audit(db, user, sql, "DELETE", False, str(e), None, None)
        raise HTTPException(status_code=422, detail=str(e))


# ── SQL console ───────────────────────────────────────────────────────────

class QueryBody(BaseModel):
    sql: str
    confirm: bool = False


@router.post("/query")
async def run_query(
    body: QueryBody,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    if not body.sql.strip():
        raise HTTPException(status_code=400, detail="SQL statement is empty")

    # asyncpg refuses more than one command in a single prepared-statement
    # execute() call ("cannot insert multiple commands into a prepared
    # statement") — unlike psycopg2, it has no implicit multi-statement
    # support. sqlparse.split() safely splits on ';' while respecting string
    # literals and $$-quoted function bodies (a naive str.split(";") would
    # mangle those), so each statement can be run as its own execute() call
    # instead. They still share one DB transaction (see _log_audit's comment
    # below), so a failure partway through rolls back everything already run.
    statements = [s.strip() for s in sqlparse.split(body.sql) if s.strip()]
    if not statements:
        raise HTTPException(status_code=400, detail="SQL statement is empty")

    classified = [_classify_and_check(s) for s in statements]
    if any(req for _, req in classified) and not body.confirm:
        dangerous_types = ", ".join(sorted({t for t, req in classified if req}))
        raise HTTPException(
            status_code=400,
            detail=f"This includes a {dangerous_types} statement that looks destructive (DROP/TRUNCATE, or "
                   f"DELETE/UPDATE with no WHERE clause). Re-submit with confirm=true to proceed.",
        )
    # Single statement keeps the exact type it always had; multiple statements
    # get a "+"-joined summary (e.g. "SELECT+ALTER") for the audit log.
    stype = classified[0][0] if len(statements) == 1 else "+".join(dict.fromkeys(t for t, _ in classified))

    start = time.monotonic()
    try:
        payload = {"columns": [], "rows": [], "row_count": 0, "truncated": False}
        for stmt in statements:
            result = await db.execute(text(stmt))
            if result.returns_rows:
                columns = list(result.keys())
                rows = result.fetchmany(500)
                payload = {
                    "columns": columns,
                    "rows": [[_jsonify(v) for v in r] for r in rows],
                    "row_count": len(rows),
                    "truncated": len(rows) == 500,
                }
            else:
                payload = {"columns": [], "rows": [], "row_count": result.rowcount, "truncated": False}
        duration_ms = int((time.monotonic() - start) * 1000)
        await _log_audit(db, user, body.sql, stype, True, None, payload["row_count"], duration_ms)
        return {"success": True, "duration_ms": duration_ms, **payload}
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        await db.rollback()
        await _log_audit(db, user, body.sql, stype, False, str(e), None, duration_ms)
        raise HTTPException(status_code=422, detail=str(e))


# ── Audit log ─────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.IT)),
):
    result = await db.execute(
        select(DbBrowserAuditLog).order_by(DbBrowserAuditLog.executed_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id":              l.id,
            "executed_by":     l.executed_by,
            "executed_at":     l.executed_at.isoformat() if l.executed_at else None,
            "statement_type":  l.statement_type,
            "sql_text":        l.sql_text,
            "success":         l.success,
            "error_message":   l.error_message,
            "rows_affected":   l.rows_affected,
            "duration_ms":     l.duration_ms,
        }
        for l in logs
    ]
