"""
VPN Access Monitoring — service functions.

Two independent checks, both blocking I/O (called from plain `def` FastAPI
routes so they run in FastAPI's threadpool, same convention as ebs_backup):
  - check_reachable(): raw TCP connect to the public SSL-VPN port, the same
    kind of check as `nc -zv host port` — tells you whether FortiClient
    itself would even be able to reach the gateway before attempting the
    SSL-VPN handshake.
  - get_active_sessions(): SSH into the FortiGate's own admin CLI and run
    `get vpn ssl monitor` to list who's currently connected.
"""
import socket
import time

import paramiko

from app.models.vpn_monitor import VpnGateway, VpnCredential
from app.services import crypto

SSH_CONNECT_TIMEOUT = 10
SSH_COMMAND_TIMEOUT = 20


def check_reachable(host: str, port: int, timeout: float = 3.0) -> dict:
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.monotonic() - start) * 1000
            return {"reachable": True, "latency_ms": round(latency_ms, 1), "error": None}
    except (socket.timeout, TimeoutError):
        return {"reachable": False, "latency_ms": None, "error": f"Timed out after {timeout}s"}
    except OSError as e:
        return {"reachable": False, "latency_ms": None, "error": str(e)}


def _fg_ssh_connect(gateway: VpnGateway, credential: VpnCredential) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=gateway.ssh_host or gateway.public_host,
        port=gateway.ssh_port or 22,
        username=credential.username,
        password=crypto.decrypt(credential.secret_encrypted),
        timeout=SSH_CONNECT_TIMEOUT, banner_timeout=SSH_CONNECT_TIMEOUT, auth_timeout=SSH_CONNECT_TIMEOUT,
        look_for_keys=False, allow_agent=False,
    )
    return client


def _parse_ssl_monitor(raw: str) -> list:
    """Best-effort parse of `get vpn ssl monitor` output. FortiOS versions
    differ in exact columns, so this uses whatever header row the box
    actually returns (must contain "Index" and "User") as the field names,
    instead of hardcoding a fixed column set — more resilient to version
    differences, at the cost of being defeated by any column whose value
    itself contains whitespace (not expected for this command's columns)."""
    lines = [l for l in raw.splitlines() if l.strip()]
    header_idx = next((i for i, l in enumerate(lines) if "Index" in l and "User" in l), None)
    if header_idx is None:
        return []

    headers = lines[header_idx].split()
    sessions = []
    for line in lines[header_idx + 1:]:
        parts = line.split(None, len(headers) - 1)
        if len(parts) < 2:
            continue
        sessions.append(dict(zip(headers, parts)))
    return sessions


def get_active_sessions(gateway: VpnGateway, credential: VpnCredential) -> dict:
    try:
        client = _fg_ssh_connect(gateway, credential)
    except Exception as e:
        return {"ok": False, "error": str(e), "sessions": [], "raw_output": None}

    try:
        _, stdout, stderr = client.exec_command("get vpn ssl monitor", timeout=SSH_COMMAND_TIMEOUT)
        raw = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return {"ok": True, "error": err.strip() or None, "sessions": _parse_ssl_monitor(raw), "raw_output": raw}
    except Exception as e:
        return {"ok": False, "error": str(e), "sessions": [], "raw_output": None}
    finally:
        client.close()
