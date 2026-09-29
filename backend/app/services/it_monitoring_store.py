"""
IT monitoring — where the servers come from and where the readings go.

Servers: Server Process Monitoring and Server Storage Monitoring poll every
Server Control entry with monitor_enabled, over SSH at its address and
ssh_port, logging in with its monitor_credential_id (or its first credential
when none is picked). Server Control is the single source of hosts and
passwords; the old backend/data/server_config.json is no longer read.

Readings: every poll — the 15-minute etl_it_monitoring run and each refresh
on the two dashboard pages — is appended to the eis.fact_it_* tables that
CoChat's IT tools read (eis_tools.get_server_resources / get_disk_usage /
get_server_top_processes). The `source` column says which one wrote a row.
Dashboard writes are throttled per server and per kind (DASHBOARD_MIN_GAP):
the Process page can auto-refresh every few seconds, and a row every five
seconds per server would bury the history the trend questions rely on
without making "now" any more accurate.
"""
import re
import threading
import time
from urllib.parse import urlparse

import psycopg2
import structlog
from sqlalchemy import text

from app.config import settings
from app.database import sync_engine
from app.services import crypto

logger = structlog.get_logger()

DASHBOARD_MIN_GAP = 60  # seconds between dashboard-sourced rows, per server and kind
_last_write: dict[tuple[str, str], float] = {}
_lock = threading.Lock()


def _host(address: str | None) -> str:
    """Server Control addresses are free text — a bare IP/hostname for
    servers, a URL for web consoles. SSH needs just the host part."""
    a = (address or "").strip()
    if "://" in a:
        return urlparse(a).hostname or ""
    return a.split("/")[0].split(":")[0]


def server_key(name: str) -> str:
    """Stable, readable key stored with every row, e.g. 'oracle-ebs-database'."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60] or "server"


def monitored_servers(with_secret: bool = False) -> list[dict]:
    """Every monitor_enabled server in Server Control, in Server Control's
    order. `problem` is set when a server cannot be polled as configured
    (no credential, no host); callers show it instead of attempting SSH.
    Passwords are decrypted only when with_secret is True."""
    with sync_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT e.id, e.name, e.category, e.address, e.ssh_port,
                   c.id AS credential_id, c.label AS credential_label, c.username,
                   c.secret_encrypted
              FROM server_registry_entries e
              LEFT JOIN LATERAL (
                   SELECT * FROM server_registry_credentials c
                    WHERE c.server_id = e.id
                      AND (e.monitor_credential_id IS NULL OR c.id = e.monitor_credential_id)
                    ORDER BY c.id LIMIT 1) c ON TRUE
             WHERE e.monitor_enabled
             ORDER BY e.category, e.sequence, e.name
        """)).mappings().all()

    out = []
    for r in rows:
        host = _host(r["address"])
        problem = None
        if not host:
            problem = "No IP/hostname in Server Control"
        elif not r["credential_id"]:
            problem = "No credential in Server Control"
        elif not r["username"]:
            problem = "The monitoring credential has no username"
        s = {
            "id": r["id"], "key": server_key(r["name"]), "name": r["name"], "category": r["category"],
            "ip": host, "port": r["ssh_port"] or 22, "username": r["username"],
            "credential_label": r["credential_label"], "problem": problem,
        }
        if with_secret and not problem:
            try:
                s["password"] = crypto.decrypt(r["secret_encrypted"])
            except Exception:
                s["problem"] = "The monitoring credential could not be decrypted"
        out.append(s)
    return out


def get_server(server_id: int | None, with_secret: bool = False) -> dict | None:
    servers = monitored_servers(with_secret)
    if server_id is None:
        return servers[0] if servers else None
    return next((s for s in servers if s["id"] == server_id), None)


# ── Writes ────────────────────────────────────────────────────────────────


def _due(source: str, key: str, kind: str) -> bool:
    if source != "dashboard":
        return True
    now = time.monotonic()
    with _lock:
        if now - _last_write.get((key, kind), 0) < DASHBOARD_MIN_GAP:
            return False
        _last_write[(key, kind)] = now
        return True


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def save_metrics(rows: list[dict], source: str, cur=None) -> int:
    """rows: ServerMonitorService metric dicts carrying server_key/label/ip."""
    rows = [m for m in rows if _due(source, m["server_key"], "metrics")]
    if not rows:
        return 0
    def write(c):
        for m in rows:
            c.execute(
                "INSERT INTO eis.fact_it_server_metrics "
                "(server_key, server_label, server_ip, status, cpu_pct, cpu_count, memory_pct, "
                " memory_used_gb, memory_total_gb, swap_pct, load_1, uptime, error_message, source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (m.get("server_key"), m.get("server_label"), m.get("server_ip"), m.get("status"),
                 m.get("cpu"), m.get("cpu_count"), m.get("memory_percent"), m.get("memory_used"),
                 m.get("memory_total"), m.get("swap_percent"), _to_float(m.get("load")),
                 m.get("uptime"), m.get("error"), source),
            )
    return _run(write, cur, len(rows))


def save_disks(server: dict, rows: list[dict], source: str, cur=None) -> int:
    """All mount points of one server in one statement batch, so they share
    one captured_at (now() is the transaction start) and read as one snapshot."""
    if not rows or not _due(source, server["server_key"], "disk"):
        return 0
    def write(c):
        for d in rows:
            c.execute(
                "INSERT INTO eis.fact_it_disk_usage "
                "(server_key, server_label, server_ip, mount_point, filesystem, "
                " size_gb, used_gb, avail_gb, used_pct, source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (server["server_key"], server["server_label"], server.get("server_ip"),
                 d.get("mountpoint"), d.get("filesystem"), d.get("total_gb"), d.get("used_gb"),
                 d.get("free_gb"), d.get("usage_percent"), source),
            )
    return _run(write, cur, len(rows))


def save_processes(server: dict, cpu: list[dict], mem: list[dict], source: str, cur=None) -> int:
    if not (cpu or mem) or not _due(source, server["server_key"], "processes"):
        return 0
    def write(c):
        for sort_by, rows in (("cpu", cpu), ("mem", mem)):
            for rank, p in enumerate(rows, 1):
                c.execute(
                    "INSERT INTO eis.fact_it_top_process "
                    "(server_key, server_label, server_ip, sort_by, rank, os_user, pid, "
                    " cpu_pct, mem_pct, command, source) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (server["server_key"], server["server_label"], server.get("server_ip"), sort_by, rank,
                     p.get("user"), _to_int(p.get("pid")), _to_float(p.get("cpu")), _to_float(p.get("mem")),
                     p.get("command"), source),
                )
    return _run(write, cur, len(cpu) + len(mem))


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _run(write, cur, n: int) -> int:
    """Use the caller's cursor (the ETL commits its own transaction) or open a
    short connection of our own. A failed dashboard write is logged and
    swallowed: the page must still show what it measured."""
    if cur is not None:
        write(cur)
        return n
    try:
        pg = psycopg2.connect(settings.eis_database_url_rw)
        try:
            with pg, pg.cursor() as c:
                write(c)
        finally:
            pg.close()
        return n
    except Exception as e:
        logger.warning("it_monitoring_store_write_failed", error=str(e))
        return 0
