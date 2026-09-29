"""
IT monitoring — where the servers come from and where the readings go.

Servers: Server Process Monitoring and Server Storage Monitoring list every
server in Server Control and poll the one picked, over SSH at its address and
ssh_port, logging in with its monitor_credential_id (or its first credential
when none is picked). Server Control is the single source of hosts and
passwords. monitor_enabled now only means "include in the 15-minute scheduled
snapshot" (etl_it_monitoring); any server can still be polled on demand.

SSH is attempted only to internal addresses (private IPs, or hostnames that
resolve to one). Server Control also holds SaaS consoles (support.oracle.com,
hr.talenta.co, ...) with company passwords, and an on-demand poll must never
hand those to a host outside the network.

Readings: every poll — the scheduled run, each page load/refresh, and each
CoChat question that names a server — is appended to the eis.fact_it_* tables
that CoChat's IT tools read. `source` says which one wrote a row: 'schedule',
'dashboard', 'dashboard-auto' or 'cochat'. Only 'dashboard-auto' (the page's
auto-refresh timer, which can fire every few seconds) is throttled, to one
row per server and kind per DASHBOARD_MIN_GAP; a load someone asked for is
always stored.
"""
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urlparse

import psycopg2
import structlog
from sqlalchemy import text

from app.config import get_settings
from app.database import sync_engine
from app.services import crypto

logger = structlog.get_logger()

DASHBOARD_MIN_GAP = 60  # seconds between auto-refresh rows, per server and kind
_last_write: dict[tuple[str, str], float] = {}
_lock = threading.Lock()

_DNS_TTL = 300
_dns_cache: dict[str, tuple[float, bool]] = {}


def _host(address: str | None) -> str:
    """Server Control addresses are free text — a bare IP/hostname for
    servers, a URL for web consoles. SSH needs just the host part."""
    a = (address or "").strip()
    if "://" in a:
        return urlparse(a).hostname or ""
    return a.split("/")[0].split(":")[0]


def _is_internal(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        pass
    hit = _dns_cache.get(host)
    if hit and time.monotonic() - hit[0] < _DNS_TTL:
        return hit[1]
    try:
        ok = all(ipaddress.ip_address(info[4][0]).is_private
                 for info in socket.getaddrinfo(host, 22, proto=socket.IPPROTO_TCP))
    except OSError:
        ok = False
    _dns_cache[host] = (time.monotonic(), ok)
    return ok


def server_key(name: str) -> str:
    """Stable, readable key stored with every row, e.g. 'oracle-ebs-database'."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60] or "server"


def registry_servers(with_secret: bool = False, only_monitored: bool = False) -> list[dict]:
    """Servers in Server Control, in Server Control's order. `problem` is set
    when a server cannot be polled over SSH as configured (external address,
    no credential, no host); callers show it instead of attempting SSH.
    Passwords are decrypted only when with_secret is True."""
    with sync_engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT e.id, e.name, e.category, e.address, e.ssh_port, e.monitor_enabled,
                   c.id AS credential_id, c.label AS credential_label, c.username,
                   c.secret_encrypted
              FROM server_registry_entries e
              LEFT JOIN LATERAL (
                   SELECT * FROM server_registry_credentials c
                    WHERE c.server_id = e.id
                      AND (e.monitor_credential_id IS NULL OR c.id = e.monitor_credential_id)
                    ORDER BY c.id LIMIT 1) c ON TRUE
             {"WHERE e.monitor_enabled" if only_monitored else ""}
             ORDER BY e.category, e.sequence, e.name
        """)).mappings().all()

    out = []
    for r in rows:
        host = _host(r["address"])
        problem = None
        if not host:
            problem = "No IP/hostname in Server Control"
        elif not _is_internal(host):
            problem = "Not an internal address — SSH is not attempted"
        elif not r["credential_id"]:
            problem = "No credential in Server Control"
        elif not r["username"]:
            problem = "The credential has no username"
        s = {
            "id": r["id"], "key": server_key(r["name"]), "name": r["name"], "category": r["category"],
            "ip": host, "port": r["ssh_port"] or 22, "username": r["username"],
            "credential_label": r["credential_label"], "monitor_enabled": bool(r["monitor_enabled"]),
            "problem": problem,
        }
        if with_secret and not problem:
            try:
                s["password"] = crypto.decrypt(r["secret_encrypted"])
            except Exception:
                s["problem"] = "The credential could not be decrypted"
        out.append(s)
    return out


def monitored_servers(with_secret: bool = False) -> list[dict]:
    """The servers in the 15-minute scheduled snapshot."""
    return registry_servers(with_secret, only_monitored=True)


def get_server(server_id: int | None, with_secret: bool = False) -> dict | None:
    servers = registry_servers(with_secret)
    if server_id is None:
        return next((s for s in servers if s["monitor_enabled"] and not s["problem"]), None) \
            or next((s for s in servers if not s["problem"]), None)
    return next((s for s in servers if s["id"] == server_id), None)


def resolve_servers(query: str, with_secret: bool = False, limit: int = 5) -> list[dict]:
    """Servers a CoChat question refers to: exact IP or key first, then a
    name/key/category containing the words given ("database", "ebs dev").
    Capped at `limit` so a vague word never fans out to every host."""
    q = (query or "").strip().lower()
    if not q:
        return []
    servers = registry_servers(with_secret)
    exact = [s for s in servers if q in (s["ip"].lower(), s["key"], s["name"].lower())]
    if exact:
        return exact[:limit]
    words = [w for w in re.split(r"[^a-z0-9.]+", q) if w]
    hay = lambda s: f"{s['name']} {s['key']} {s['category'] or ''} {s['ip']}".lower()
    return [s for s in servers if all(w in hay(s) for w in words)][:limit]


# ── Writes ────────────────────────────────────────────────────────────────


def _due(source: str, key: str, kind: str) -> bool:
    if source != "dashboard-auto":
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


def _to_int(v):
    try:
        return int(v)
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
    """All mount points of one server in one transaction, so they share one
    captured_at (now() is the transaction start) and read as one snapshot."""
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


def _run(write, cur, n: int) -> int:
    """Use the caller's cursor (the ETL commits its own transaction) or open a
    short connection of our own. A failed on-demand write is logged and
    swallowed: the page or the chat must still get what was measured."""
    if cur is not None:
        write(cur)
        return n
    try:
        pg = psycopg2.connect(get_settings().eis_database_url_rw)
        try:
            with pg, pg.cursor() as c:
                write(c)
        finally:
            pg.close()
        return n
    except Exception as e:
        logger.warning("it_monitoring_store_write_failed", error=str(e))
        return 0
