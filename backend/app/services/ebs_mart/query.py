"""
Guarded execution for every mart read (blueprint section 7).

Every tool answer carries as_of, sql_used, row_count and truncated, and every
call — allowed, rejected, denied or failed — is written to
meta.chat_query_log. The log write goes over the read-write connection: the
reader role cannot write, and must not be able to.
"""
import json
import time
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2
import structlog

from app.config import get_settings
from app.services.ebs_mart.access import Caller
from app.services.ebs_mart.constants import MARTS, MAX_ROWS, STATEMENT_TIMEOUT

logger = structlog.get_logger()
settings = get_settings()
_WIB = ZoneInfo("Asia/Jakarta")


class QueryFailed(RuntimeError):
    pass


def _reader():
    """llm_ro when configured (blueprint), else the existing chat_readonly
    role — both are SELECT-only and both are granted mart.* by schema.py."""
    conn = psycopg2.connect(settings.eis_llm_ro_url or settings.eis_database_url)
    conn.set_session(readonly=True)
    return conn


def _rw():
    return psycopg2.connect(settings.eis_database_url_rw)


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return v


def as_of(marts: list[str]) -> str | None:
    """When the data behind these marts was last pulled successfully.

    A mart is as fresh as its oldest source job, and a query over several
    marts is as fresh as its stalest mart — so this is the minimum over all
    source jobs involved of each job's latest successful finish, including
    runs started by the manual button (blueprint "Aturan ETL")."""
    jobs = sorted({j for m in marts for j in MARTS.get(m, {}).get("source_jobs", [])})
    if not jobs:
        return None
    conn = _rw()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_name, MAX(finished_at)
                  FROM eis.etl_job_log
                 WHERE status = 'success' AND job_name = ANY(%s)
                 GROUP BY job_name
                """,
                (jobs,),
            )
            latest = dict(cur.fetchall())
            cur.execute("SELECT current_setting('TimeZone')")
            db_tz = cur.fetchone()[0]
    finally:
        conn.close()
    if any(latest.get(j) is None for j in jobs):
        return None
    oldest = min(latest[j] for j in jobs)
    if oldest.tzinfo is None:
        # finished_at is filled by NOW() into a column without time zone, so
        # it holds the server's local time — whatever TimeZone says.
        try:
            oldest = oldest.replace(tzinfo=ZoneInfo(db_tz))
        except Exception:
            oldest = oldest.replace(tzinfo=ZoneInfo("UTC"))
    return oldest.astimezone(_WIB).strftime("%Y-%m-%d %H:%M WIB")


def log_call(caller: Caller | None, *, tool: str, question: str = "", sql: str | None = None,
             marts: list[str] | None = None, args: dict | None = None, row_count: int | None = None,
             truncated: bool | None = None, duration_ms: int | None = None, status: str,
             error: str | None = None):
    try:
        conn = _rw()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.chat_query_log
                        (user_email, chat_id, source, groups, tool_name, tool_args, question, sql_text,
                         marts, row_count, truncated, duration_ms, status, error_msg)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        caller.email if caller else None,
                        caller.chat_id if caller else None,
                        caller.source if caller else None,
                        sorted(caller.groups) if caller else None,
                        tool, json.dumps(args or {}, default=str), question or None, sql,
                        marts, row_count, truncated, duration_ms, status, error,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # An audit failure is logged loudly but does not take the answer away
        # from the user; the structlog line is the fallback record.
        logger.error("ebs_mart_audit_failed", tool=tool, error=str(e))


def run(caller: Caller, sql: str, params: dict | None = None, *, tool: str, marts: list[str],
        question: str = "", args: dict | None = None) -> dict:
    """Execute one SELECT (already validated or written by us) and shape the
    tool result. params=None for run_sql so a literal % in the model's LIKE
    pattern is not read as a placeholder."""
    wrapped = f"SELECT * FROM ({sql}) AS q LIMIT {MAX_ROWS + 1}"
    t0 = time.monotonic()
    try:
        conn = _reader()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
                cur.execute(wrapped, params)
                columns = [d.name for d in cur.description]
                rows = cur.fetchall()
            conn.rollback()
        finally:
            conn.close()
    except psycopg2.errors.QueryCanceled:
        ms = int((time.monotonic() - t0) * 1000)
        msg = f"Query dihentikan setelah {STATEMENT_TIMEOUT} (statement_timeout). Persempit filter atau agregasikan."
        log_call(caller, tool=tool, question=question, sql=sql, marts=marts, args=args,
                 duration_ms=ms, status="TIMEOUT", error=msg)
        raise QueryFailed(msg)
    except psycopg2.Error as e:
        ms = int((time.monotonic() - t0) * 1000)
        msg = (e.pgerror or str(e)).strip().splitlines()[0]
        log_call(caller, tool=tool, question=question, sql=sql, marts=marts, args=args,
                 duration_ms=ms, status="ERROR", error=msg)
        raise QueryFailed(f"Query gagal: {msg}")

    ms = int((time.monotonic() - t0) * 1000)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    log_call(caller, tool=tool, question=question, sql=sql, marts=marts, args=args,
             row_count=len(rows), truncated=truncated, duration_ms=ms, status="OK")

    return {
        "as_of": as_of(marts),
        "marts": marts,
        "columns": columns,
        "rows": [[_jsonable(v) for v in r] for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "sql_used": _inline_params(sql, params),
    }


def _inline_params(sql: str, params: dict | None) -> str:
    """SQL as the user should see it in the <details> block: placeholders
    replaced by the values used. Display only — never executed."""
    if not params:
        return " ".join(sql.split())
    out = sql
    for k, v in params.items():
        if v is None:
            lit = "NULL"
        elif isinstance(v, (int, float, Decimal)):
            lit = str(v)
        else:
            lit = "'" + str(v).replace("'", "''") + "'"
        out = out.replace(f"%({k})s", lit)
    return " ".join(out.replace("%%", "%").split())
