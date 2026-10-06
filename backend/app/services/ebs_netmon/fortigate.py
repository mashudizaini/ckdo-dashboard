"""
Read-only FortiGate snapshot over SSH, for the HO and Plant FortiGates
(FortiOS 7.2, no VDOMs). The login comes from Server Control — pick the two
entries in this module's Setup — so the password is rotated in one place.

Only a fixed set of `get` / `diagnose` commands is ever sent: this module
reads the firewall, it never configures it. Every command's raw output is
kept next to the parsed summary; FortiOS output shifts between releases, so
when a number looks wrong, read the raw text before changing a parser
(same lesson as vpn_monitor_service._parse_ssl_monitor).
"""
import re

import paramiko

from app.services import it_monitoring_store as store

SSH_TIMEOUT = 10
CMD_TIMEOUT = 25


def _commands(ebs_ip: str | None) -> list[tuple[str, str]]:
    cmds = [
        ("status", "get system status"),
        ("performance", "get system performance status"),
        ("sdwan_health", "diagnose sys sdwan health-check"),
        ("sdwan_member", "diagnose sys sdwan member"),
        ("sdwan_service", "diagnose sys sdwan service"),
        ("ipsec_summary", "get vpn ipsec tunnel summary"),
        ("tunnel_list", "diagnose vpn tunnel list"),
    ]
    if ebs_ip and re.fullmatch(r"[0-9.]+", ebs_ip):
        cmds.append(("route_ebs", f"get router info routing-table details {ebs_ip}"))
    return cmds


def _connect(srv: dict) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(srv["ip"], port=int(srv.get("port") or 22), username=srv["username"],
                   password=srv.get("password"), timeout=SSH_TIMEOUT, banner_timeout=SSH_TIMEOUT,
                   auth_timeout=SSH_TIMEOUT, look_for_keys=False, allow_agent=False)
    return client


def _run_all(srv: dict, commands: list[tuple[str, str]]) -> dict:
    """One connection, one channel per command. Some FortiOS builds drop the
    transport after a single exec, so a failed command reconnects once."""
    raw = {}
    client = _connect(srv)
    try:
        for key, cmd in commands:
            for attempt in (1, 2):
                try:
                    _, stdout, _ = client.exec_command(cmd, timeout=CMD_TIMEOUT)
                    raw[key] = stdout.read().decode("utf-8", "replace")
                    break
                except Exception as e:
                    if attempt == 2:
                        raw[key] = f"[error] {e}"
                    else:
                        try:
                            client.close()
                        except Exception:
                            pass
                        client = _connect(srv)
    finally:
        client.close()
    return raw


# ── Parsers ────────────────────────────────────────────────────────────────

def _num(pattern: str, text: str, cast=float, flags=0):
    m = re.search(pattern, text or "", flags)
    if not m:
        return None
    try:
        return cast(m.group(1))
    except (TypeError, ValueError):
        return None


def parse_status(raw: str) -> dict:
    return {
        "version": (re.search(r"Version:\s*(.+)", raw or "") or [None, None])[1],
        "hostname": (re.search(r"Hostname:\s*(\S+)", raw or "") or [None, None])[1],
    }


def parse_performance(raw: str) -> dict:
    idle = _num(r"CPU states:.*?(\d+)%\s+idle", raw)
    net = re.search(r"Average network usage:\s*(\d+)\s*/\s*(\d+)\s*kbps in 1 minute", raw or "")
    uptime = re.search(r"Uptime:\s*(.+)", raw or "")
    return {
        "cpu_pct": (100 - idle) if idle is not None else None,
        "mem_pct": _num(r"Memory:.*?\(([\d.]+)%\)", raw),
        "sessions": _num(r"Average sessions:\s*(\d+)\s+sessions in 1 minute", raw, int),
        "net_in_kbps": int(net.group(1)) if net else None,
        "net_out_kbps": int(net.group(2)) if net else None,
        "uptime": uptime.group(1).strip() if uptime else None,
    }


def parse_sdwan_health(raw: str) -> list[dict]:
    """Lines look like:
    Health Check(EBS_SLA):
    Seq(1 port1): state(alive), packet-loss(0.000%) latency(15.123), jitter(0.456), mos(4.402), ... sla_map=0x1
    """
    out, check = [], None
    for line in (raw or "").splitlines():
        h = re.match(r"\s*Health Check\((.+?)\):", line)
        if h:
            check = h.group(1)
            continue
        m = re.search(r"Seq\((\d+)\s+([^)]+)\):\s*state\((\w+)\)(.*)", line)
        if not m:
            continue
        rest = m.group(4)
        out.append({
            "check": check, "seq": int(m.group(1)), "member": m.group(2).strip(), "state": m.group(3),
            "loss_pct": _num(r"packet-loss\(([\d.]+)%\)", rest),
            "latency_ms": _num(r"latency\(([\d.]+)\)", rest),
            "jitter_ms": _num(r"jitter\(([\d.]+)\)", rest),
            "mos": _num(r"mos\(([\d.]+)\)", rest),
            "sla_map": (re.search(r"sla_map=(0x[0-9a-fA-F]+)", rest) or [None, None])[1],
        })
    return out


def parse_ipsec_summary(raw: str) -> list[dict]:
    pat = re.compile(
        r"'([^']+)'\s+(\S+)\s+selectors\(total,up\):\s*(\d+)/(\d+)\s+"
        r"rx\(pkt,err\):\s*(\d+)/(\d+)\s+tx\(pkt,err\):\s*(\d+)/(\d+)"
    )
    return [{
        "name": m.group(1), "peer": m.group(2),
        "selectors_total": int(m.group(3)), "selectors_up": int(m.group(4)),
        "rx_pkt": int(m.group(5)), "rx_err": int(m.group(6)),
        "tx_pkt": int(m.group(7)), "tx_err": int(m.group(8)),
        "up": int(m.group(4)) > 0,
    } for m in pat.finditer(raw or "")]


def parse_tunnel_list(raw: str) -> list[dict]:
    """`diagnose vpn tunnel list` — one block per tunnel starting `name=`."""
    blocks = re.split(r"\n(?=name=)", raw or "")
    out = []
    for b in blocks:
        name = re.search(r"^name=(\S+)", b.strip())
        if not name:
            continue
        stat = re.search(r"stat:\s*rxp=(\d+)\s+txp=(\d+)\s+rxb=(\d+)\s+txb=(\d+)", b)
        dpd = re.search(r"dpd:\s*mode=(\S+).*?count=(\d+)", b)
        out.append({
            "name": name.group(1),
            "mtu": _num(r"\bmtu=(\d+)", b, int),
            "rx_pkt": int(stat.group(1)) if stat else None,
            "tx_pkt": int(stat.group(2)) if stat else None,
            "dpd_mode": dpd.group(1) if dpd else None,
            "dpd_fail_count": int(dpd.group(2)) if dpd else None,
            "npu_offload": bool(re.search(r"npu_flag=0[1-3]", b)),
        })
    return out


def parse_route(raw: str) -> list[str]:
    seen = []
    for m in re.finditer(r"via\s+([\w./-]+)", raw or ""):
        v = m.group(1).rstrip(",")
        if v not in seen:
            seen.append(v)
    return seen


def snapshot(server_id: int, ebs_ip: str | None) -> dict:
    """{ok, name, summary, raw, error} — never raises."""
    srv = store.get_server(server_id, with_secret=True)
    if srv is None:
        return {"ok": False, "name": f"server #{server_id}", "summary": None, "raw": None,
                "error": "Server tidak ditemukan di Server Control"}
    if srv.get("problem"):
        return {"ok": False, "name": srv["name"], "summary": None, "raw": None, "error": srv["problem"]}
    try:
        raw = _run_all(srv, _commands(ebs_ip))
    except Exception as e:
        return {"ok": False, "name": srv["name"], "summary": None, "raw": None, "error": f"SSH gagal: {e}"}

    summary = {
        **parse_status(raw.get("status", "")),
        **parse_performance(raw.get("performance", "")),
        "sdwan": parse_sdwan_health(raw.get("sdwan_health", "")),
        "tunnels": parse_ipsec_summary(raw.get("ipsec_summary", "")),
        "tunnel_detail": parse_tunnel_list(raw.get("tunnel_list", "")),
        "ebs_route_via": parse_route(raw.get("route_ebs", "")),
        "address": srv["ip"],
    }
    return {"ok": True, "name": srv["name"], "summary": summary, "raw": raw, "error": None}
