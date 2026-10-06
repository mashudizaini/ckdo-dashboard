"""
EBS application/database health at a point in time — the "network is fine,
so is it EBS?" half of the diagnosis (Case C, codes EBS-0x / DB-0x).

Every query runs on its own: the APPS account may lack a grant on one
v$ view, and that must cost one panel, not the whole snapshot. All of it is
read-only. The app-tier OS numbers reuse Server Process Monitoring's SSH
collector on the servers flagged for monitoring in Server Control (the two
EBS hosts), so there is no second set of logins to maintain.
"""
import time
from datetime import date, datetime
from decimal import Decimal

import structlog

from app.database import get_oracle_connection, get_oracle_environment
from app.services import it_monitoring_store as store

logger = structlog.get_logger()

QUERIES = {
    "sessions": """
        SELECT COUNT(*)                                                         AS total,
               SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END)               AS active,
               SUM(CASE WHEN blocking_session IS NOT NULL THEN 1 ELSE 0 END)    AS blocked,
               SUM(CASE WHEN LOWER(program) LIKE 'frmweb%'
                          OR LOWER(module) LIKE 'frm:%' THEN 1 ELSE 0 END)      AS forms
          FROM v$session
         WHERE type = 'USER'
    """,
    "waits": """
        SELECT event, wait_class, COUNT(*) AS sessions, MAX(seconds_in_wait) AS max_wait_s
          FROM v$session
         WHERE type = 'USER' AND status = 'ACTIVE' AND wait_class <> 'Idle'
         GROUP BY event, wait_class
         ORDER BY COUNT(*) DESC
         FETCH FIRST 8 ROWS ONLY
    """,
    "blocking": """
        SELECT s.sid, s.serial# AS serial_num, s.username, SUBSTR(s.module, 1, 48) AS module,
               s.blocking_session, s.seconds_in_wait, s.event
          FROM v$session s
         WHERE s.blocking_session IS NOT NULL
         ORDER BY s.seconds_in_wait DESC
         FETCH FIRST 15 ROWS ONLY
    """,
    "long_sql": """
        SELECT s.sid, s.username, SUBSTR(s.module, 1, 48) AS module, s.sql_id,
               s.last_call_et AS seconds_active, s.event
          FROM v$session s
         WHERE s.type = 'USER' AND s.status = 'ACTIVE'
           AND s.wait_class <> 'Idle' AND s.last_call_et > 300
         ORDER BY s.last_call_et DESC
         FETCH FIRST 10 ROWS ONLY
    """,
    "sysmetric": """
        SELECT metric_name, ROUND(value, 2) AS value, metric_unit
          FROM v$sysmetric
         WHERE group_id = 2
           AND metric_name IN ('Host CPU Utilization (%)', 'Average Active Sessions',
                               'Database Wait Time Ratio', 'Database CPU Time Ratio',
                               'Average Synchronous Single-Block Read Latency',
                               'Current Logons Count', 'Response Time Per Txn',
                               'User Transaction Per Sec')
    """,
    "managers": """
        SELECT q.concurrent_queue_name AS short_name, q.user_concurrent_queue_name AS name,
               q.max_processes AS target, q.running_processes AS actual
          FROM apps.fnd_concurrent_queues_vl q
         WHERE q.enabled_flag = 'Y' AND q.max_processes > 0
         ORDER BY (q.max_processes - q.running_processes) DESC, q.user_concurrent_queue_name
    """,
    "requests": """
        SELECT SUM(CASE WHEN phase_code = 'P' AND status_code IN ('I', 'Q')
                         AND requested_start_date <= SYSDATE THEN 1 ELSE 0 END)          AS pending,
               SUM(CASE WHEN phase_code = 'R' THEN 1 ELSE 0 END)                          AS running,
               SUM(CASE WHEN phase_code = 'R' AND actual_start_date < SYSDATE - 1/24
                        THEN 1 ELSE 0 END)                                                AS long_running,
               SUM(CASE WHEN phase_code = 'C' AND status_code = 'E'
                         AND actual_completion_date > SYSDATE - 1/24 THEN 1 ELSE 0 END)   AS errors_1h
          FROM apps.fnd_concurrent_requests
         WHERE phase_code IN ('P', 'R') OR actual_completion_date > SYSDATE - 1/24
    """,
    "web_users": """
        SELECT COUNT(DISTINCT user_id) AS active_15m
          FROM apps.icx_sessions
         WHERE disabled_flag = 'N' AND last_connect > SYSDATE - 15/1440
    """,
}


def _clean(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _run_queries() -> tuple[dict, dict, float | None]:
    results, errors = {}, {}
    start = time.perf_counter()
    with get_oracle_connection() as conn:
        connect_ms = round((time.perf_counter() - start) * 1000, 1)
        for key, sql in QUERIES.items():
            try:
                cur = conn.cursor()
                cur.execute(sql)
                cols = [c[0].lower() for c in cur.description]
                results[key] = [{k: _clean(v) for k, v in zip(cols, row)} for row in cur.fetchall()]
            except Exception as e:
                errors[key] = str(e).splitlines()[0]
    return results, errors, connect_ms


def _app_tier() -> list[dict]:
    from app.services.it_service import ServerMonitorService
    svc = ServerMonitorService()
    out = []
    for srv in store.monitored_servers(with_secret=True):
        if srv.get("problem"):
            out.append({"server_label": srv["name"], "server_ip": srv["ip"], "status": "not_configured",
                        "error": srv["problem"]})
            continue
        row = svc._metrics_row(srv)
        out.append({k: row.get(k) for k in (
            "server_label", "server_ip", "status", "error", "cpu", "memory_percent", "load",
            "cpu_count", "swap_percent", "uptime")})
    return out


def snapshot(include_app_tier: bool = True) -> dict:
    """{ok, summary, error} — never raises."""
    env = get_oracle_environment().get("environment")
    try:
        r, errors, connect_ms = _run_queries()
    except Exception as e:
        logger.warning("ebsnet_ebs_health_failed", error=str(e))
        return {"ok": False, "summary": {"environment": env}, "error": f"Koneksi Oracle gagal: {e}"}

    sess = (r.get("sessions") or [{}])[0]
    req = (r.get("requests") or [{}])[0]
    metrics = {m["metric_name"]: m["value"] for m in r.get("sysmetric", [])}
    managers = r.get("managers", [])
    icm = next((m for m in managers if m["short_name"] == "FNDICM"), None)

    summary = {
        "environment": env,
        "db_connect_ms": connect_ms,
        "sessions_total": sess.get("total"),
        "sessions_active": sess.get("active"),
        "sessions_blocked": sess.get("blocked"),
        "forms_sessions": sess.get("forms"),
        "web_users_15m": (r.get("web_users") or [{}])[0].get("active_15m"),
        "host_cpu_pct": metrics.get("Host CPU Utilization (%)"),
        "avg_active_sessions": metrics.get("Average Active Sessions"),
        "db_wait_ratio": metrics.get("Database Wait Time Ratio"),
        "single_block_read_ms": metrics.get("Average Synchronous Single-Block Read Latency"),
        "response_per_txn_cs": metrics.get("Response Time Per Txn"),
        "requests_pending": req.get("pending"),
        "requests_running": req.get("running"),
        "requests_long_running": req.get("long_running"),
        "requests_errors_1h": req.get("errors_1h"),
        "icm_up": (icm["actual"] or 0) > 0 if icm else None,
        "managers_down": [m for m in managers if (m["actual"] or 0) < (m["target"] or 0)],
        "managers": managers,
        "waits": r.get("waits", []),
        "blocking": r.get("blocking", []),
        "long_sql": r.get("long_sql", []),
        "query_errors": errors,
        "app_tier": [],
    }
    if include_app_tier:
        try:
            summary["app_tier"] = _app_tier()
        except Exception as e:
            summary["app_tier_error"] = str(e)
    return {"ok": True, "summary": summary, "error": None}
