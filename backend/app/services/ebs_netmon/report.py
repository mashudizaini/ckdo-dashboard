"""
Diagnosis report ("Report" tab): re-take every measurement, grade each
data point good / warn / bad / unknown, find where along the path
laptop -> HO LAN -> tunnel -> Plant LAN -> EBS web/app -> DB it gets stuck,
and write the conclusion + prioritised actions. Saved in
ebsnet_summary_reports as JSON and as a self-contained HTML file.

The bottleneck is the FIRST segment along the path that grades "bad" (else
the first "warn"): a slow tunnel makes everything behind it look slow too,
so the earliest failing hop is where to start, not the loudest one.
"""
import html
import json
import statistics
import threading
import time
from datetime import datetime, timedelta

from app.models.ebs_netmon import EbsNetClientReport, EbsNetIncident, EbsNetSummaryReport
from app.services.ebs_netmon import analysis, service
from app.services.ebs_netmon import settings as cfg

RANK = {"unknown": -1, "good": 0, "warn": 1, "bad": 2}
STATUS_LABEL = {"good": "Good", "warn": "Warning", "bad": "Bad", "unknown": "No data"}
PROBE_TO_STATUS = {"ok": "good", "warn": "warn", "crit": "bad", "unknown": "unknown"}
REPORT_RETENTION_DAYS = 180
# One build at a time: a manual "Proses" during an automatic run would
# otherwise SSH into the same FortiGates twice in parallel.
_build_lock = threading.Lock()

SECTIONS = [
    ("laptop",    "HO laptop (client)",        "D"),
    ("ho_lan",    "HO LAN",                    "A"),
    ("wan",       "HO ↔ Plant path (WAN/VPN)", "B"),
    ("plant_lan", "Plant LAN",                 "B"),
    ("ebs_web",   "EBS Web / App Tier",        "C"),
    ("ebs_db",    "EBS Database",              "C"),
    ("internet",  "Internet / Plant ISP",      None),
]
PATH = [s[0] for s in SECTIONS if s[0] != "internet"]
SECTION_LABEL = {k: l for k, l, _ in SECTIONS}

# What to do when an item is not good — keyed by item `key` prefix.
ACTIONS = {
    "cli_tests": "Run the Client Test / PowerShell agent on at least 3 HO laptops, at 08:00, 11:00, 14:00 and 15:00–16:00.",
    "cli_case_d": "Check the laptops marked Case D: close heavy applications, check RAM/CPU, clear the Java/browser cache, compare with another laptop at the same desk.",
    "cli_cpu": "Laptops with high CPU: check the top processes in the agent report (antivirus scan, Teams, updates), set the power plan to Balanced/High performance.",
    "cli_ram": "Laptops with free RAM < 20 %: close applications/tabs or upgrade RAM to ≥ 8–16 GB.",
    "cli_slow": "Users report EBS slow/hanging: log it as an incident with a snapshot at the time so it can be correlated.",
    "lan_gw_rtt": "High laptop → HO gateway RTT: move Forms users to wired LAN, check HO APs/switches, Wi-Fi channels and clients per AP.",
    "lan_gw_loss": "Packet loss on the HO LAN: check cables/switch ports, switch interface errors and Wi-Fi signal; this must be 0 % before blaming the WAN.",
    "lan_wifi": "Weak Wi-Fi signal: move closer to an AP / add APs, use 5 GHz, or use wired LAN.",
    "lan_case_a": "Many laptops show Case A: run an HO Wi-Fi survey and audit the HO switches.",
    "wan_probe": "Probes through the tunnel are bad: check tunnel status & SD-WAN SLA on the FortiGate and ISP link utilisation, then ask the ISP for data for the same hours.",
    "wan_e2e": "End-to-end laptop → Plant RTT/jitter above baseline: check WAN utilisation, QoS for EBS, and whether EBS traffic uses the best link (SD-WAN rule).",
    "wan_mtu": "Small path MTU: set tcp-mss ±1350 on the EBS tunnel policy to prevent fragmentation (NET-06).",
    "fgt_tunnel": "IPsec tunnel down / errors: check the FortiGate VPN log (renegotiation, DPD) and the ISP connection, and prepare a backup tunnel via iForte.",
    "fgt_sla": "SD-WAN SLA member bad / dead: check the ISP link concerned; make sure the EBS SD-WAN rule is SLA-based so it moves to a healthy link.",
    "fgt_cpu": "High FortiGate CPU/memory: check the top sessions, UTM profiles on internal traffic, and tunnel NPU offload.",
    "plant_probe": "Plant LAN is bad: check the Plant core switch, server ports and local Plant network load.",
    "web_probe": "EBS web/app tier slow or unreachable: check OHS/WebLogic status (oacore, forms), managed server CPU/heap, and error logs.",
    "web_ttfb": "EBS login page response time is high while the network is normal: the problem is in the application tier (OHS/oacore), not the network.",
    "app_os": "High EBS server CPU/memory/swap: check the top processes in Server Process Monitoring, JVM sizing and heavy concurrent requests.",
    "app_icm": "The Internal Concurrent Manager is down: restart the Concurrent Managers (adcmctl.sh) and check the ICM log.",
    "app_mgr": "Concurrent managers below target: check them in Administer Concurrent Managers.",
    "app_pending": "The concurrent request queue is building up: check stuck/heavy requests, add manager processes or reschedule outside working hours.",
    "app_long": "Requests running > 1 hour: check whether that is expected; heavy requests during working hours raise the DB load.",
    "db_probe": "DB listener slow/unreachable: check the listener (lsnrctl status), DB server CPU and the Plant network.",
    "db_connect": "Slow connection to the DB: check the listener, DB server load and DNS/host resolution.",
    "db_cpu": "High DB host CPU: take AWR/ASH and find the Top SQL; schedule heavy jobs outside working hours.",
    "db_block": "Sessions blocked by locks: identify the blocking session in the EBS Server tab and coordinate with the user before killing it.",
    "db_long": "SQL active > 5 minutes: check the SQL ID in AWR, table statistics (Gather Schema Statistics) and indexes.",
    "db_io": "High DB disk read latency: check the DB storage/datastore, VM host I/O, and backups running during working hours.",
    "inet_probe": "Internet from Plant is also bad: probably a Plant ISP problem (NET-08) — escalate to the ISP with this probe data.",
}

GAP_ACTIONS = {
    "fortigate": "Choose the HO & Plant FortiGates in Setup (from Server Control) so tunnel status & SD-WAN SLA are graded too.",
    "wan_target": "Add a target in the HO ↔ Plant path segment (e.g. HO FortiGate LAN IP:443) in Setup.",
    "web_target": "Enable the EBS web target (host:port) and the login URL (HTTP TTFB) in Setup.",
    "clients": "No laptop tests in the report window — ask HO users to open /dashboard/ebs-check or run the agent.",
    "agent": "No PowerShell agent reports — the HO LAN (gateway, Wi-Fi) can only be measured by the agent.",
    "ebs": "The EBS health snapshot failed — check the dashboard's Oracle connection.",
}


def _worst(statuses):
    vals = [s for s in statuses if s in RANK and s != "unknown"]
    return max(vals, key=RANK.get) if vals else "unknown"


def _grade(value, warn, bad, higher_is_bad=True):
    if value is None:
        return "unknown"
    if higher_is_bad:
        return "bad" if value >= bad else "warn" if value >= warn else "good"
    return "bad" if value <= bad else "warn" if value <= warn else "good"


def _med(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def _item(key, name, value, status, standard="", note="", unit=""):
    return {"key": key, "name": name, "value": value, "unit": unit, "status": status,
            "status_label": STATUS_LABEL[status], "standard": standard, "note": note,
            "action": ACTIONS.get(key) if status in ("warn", "bad") else None}


def _fmt(v, unit=""):
    if v is None:
        return "—"
    return f"{v} {unit}".strip()


# ── Section builders ──────────────────────────────────────────────────────

def _probe_items(probes, segment, key, t):
    out = []
    for p in probes:
        if p["segment"] != segment or not p["enabled"]:
            continue
        last, day = p.get("last") or {}, p.get("day") or {}
        st = PROBE_TO_STATUS[analysis.probe_level(last if last else None, t)]
        addr = p["url"] if p["check_type"] == "http" else f"{p.get('host')}:{p.get('port')}"
        val = (f"avg {last.get('rtt_avg')} ms · max {last.get('rtt_max')} ms · jitter {last.get('jitter_ms')} ms · loss {last.get('loss_pct')}%"
               if last.get("rtt_avg") is not None else (last.get("error") or "no reply"))
        note = (f"24 h: avg {day.get('rtt_avg')} ms, max {day.get('rtt_max')} ms, average loss {day.get('loss_avg')}% ({day.get('runs')} runs)"
                if day.get("runs") else "")
        if last.get("error") and last.get("rtt_avg") is not None:
            note = f"{last['error']}. {note}"
        out.append(_item(key, f"{p['name']} ({addr})", val, st,
                         f"loss < {t['loss_warn']}%, latency < {t['latency_warn']} ms, jitter < {t['jitter_warn']} ms", note))
    return out


def _sec_laptop(clients, t):
    items = []
    n = len(clients)
    hosts = {c["hostname"] or c["reported_by"] for c in clients}
    items.append(_item("cli_tests", "Laptop tests", f"{n} tests from {len(hosts)} laptops/users",
                       "unknown" if n == 0 else "good" if n >= 3 else "warn", "≥ 3 tests from several laptops"))
    if not n:
        return items
    d = [c for c in clients if c["verdict"] == "D"]
    share = len(d) / n
    items.append(_item("cli_case_d", "Tests indicating a laptop problem (Case D)",
                       f"{len(d)} of {n}" + (f" — {', '.join(sorted({c['hostname'] or c['reported_by'] for c in d}))[:120]}" if d else ""),
                       "good" if not d else "bad" if share >= 0.5 else "warn", "0"))
    cpu = [c for c in clients if (c.get("cpu_pct") or 0) >= t["cpu_warn"]]
    with_cpu = [c for c in clients if c.get("cpu_pct") is not None]
    if with_cpu:
        items.append(_item("cli_cpu", "Laptops with high CPU during the test", f"{len(cpu)} of {len(with_cpu)} (median {_med([c['cpu_pct'] for c in with_cpu])}%)",
                           "good" if not cpu else "warn", f"CPU < {t['cpu_warn']}%"))
    ram = [c for c in clients if c.get("ram_avail_pct") is not None and c["ram_avail_pct"] < t["ram_avail_warn"]]
    with_ram = [c for c in clients if c.get("ram_avail_pct") is not None]
    if with_ram:
        items.append(_item("cli_ram", "Laptops with low free RAM", f"{len(ram)} of {len(with_ram)} (median {_med([c['ram_avail_pct'] for c in with_ram])}%)",
                           "good" if not ram else "bad" if len(ram) / len(with_ram) >= 0.5 else "warn", f"free RAM > {t['ram_avail_warn']}%"))
    slow = [c for c in clients if c.get("ebs_condition") in ("Slow", "Hang", "Restart")]
    items.append(_item("cli_slow", "Users reporting EBS slow/hanging during the test", f"{len(slow)} of {n}",
                       "good" if not slow else "warn", "0",
                       "What users experience — a comparison for the technical figures."))
    return items


def _sec_ho_lan(clients, t):
    agents = [c for c in clients if c.get("gw_rtt_avg") is not None]
    if not agents:
        return [_item("lan_gw_rtt", "Laptop → HO gateway RTT", None, "unknown", f"< {t['lan_rtt_warn']} ms",
                      "Only measured by the PowerShell agent on HO laptops.")]
    rtt = _med([c["gw_rtt_avg"] for c in agents])
    loss = _med([c.get("gw_loss_pct") for c in agents])
    items = [
        _item("lan_gw_rtt", "Laptop → HO gateway RTT (median)", rtt,
              _grade(rtt, t["lan_rtt_warn"], t["lan_rtt_warn"] * 4), f"< {t['lan_rtt_warn']} ms (wired ±1 ms)", f"{len(agents)} agent reports", "ms"),
        _item("lan_gw_loss", "Laptop → gateway packet loss (median)", loss,
              _grade(loss, 0.01, 1), "0 %", "", "%"),
    ]
    wifi = [c for c in agents if c.get("wifi_signal") is not None]
    if wifi:
        sig = _med([c["wifi_signal"] for c in wifi])
        items.append(_item("lan_wifi", "Laptop Wi-Fi signal (median)", sig, _grade(sig, 70, 50, higher_is_bad=False),
                           "> 70 %", f"{len(wifi)} of {len(agents)} laptops on Wi-Fi", "%"))
    a = [c for c in agents if c["verdict"] == "A"]
    items.append(_item("lan_case_a", "Agent reports with Case A (LAN problem)", f"{len(a)} of {len(agents)}",
                       "good" if not a else "bad" if len(a) / len(agents) >= 0.5 else "warn", "0"))
    return items


def _sec_wan(probes, fgs, clients, t):
    items = _probe_items(probes, "wan", "wan_probe", t)
    if clients:
        rtt = _med([c.get("ebs_rtt_avg") for c in clients])
        jit = _med([c.get("ebs_jitter_ms") for c in clients])
        loss = _med([c.get("ebs_loss_pct") for c in clients])
        items.append(_item("wan_e2e", "HO laptop → Plant RTT (median of all tests)", rtt,
                           _grade(rtt, t["latency_warn"], t["latency_crit"]), f"< {t['latency_warn']} ms",
                           f"jitter median {_fmt(jit, 'ms')}, loss median {_fmt(loss, '%')}", "ms"))
        if jit is not None:
            items.append(_item("wan_e2e", "HO laptop → Plant jitter (median)", jit,
                               _grade(jit, t["jitter_warn"], t["jitter_crit"]), f"< {t['jitter_warn']} ms", "", "ms"))
        if loss is not None:
            items.append(_item("wan_e2e", "HO laptop → Plant loss (median)", loss,
                               _grade(loss, t["loss_warn"], t["loss_crit"]), "0 %", "", "%"))
        mtus = [c["path_mtu"] for c in clients if c.get("path_mtu")]
        if mtus:
            mtu = min(mtus)
            items.append(_item("wan_mtu", "Smallest laptop → EBS path MTU", mtu, _grade(mtu, 1400, 1350, higher_is_bad=False),
                               "≥ 1400 (MSS clamping if smaller)", f"from {len(mtus)} agent reports"))
    for fg in fgs:
        name = fg["name"]
        if not fg.get("ok"):
            items.append(_item("fgt_tunnel", f"{name}: snapshot", fg.get("error"), "unknown", "SSH succeeds"))
            continue
        s = fg.get("summary") or {}
        for tun in s.get("tunnels", []):
            st = "bad" if not tun["up"] else "warn" if (tun["rx_err"] or tun["tx_err"]) else "good"
            items.append(_item("fgt_tunnel", f"{name}: tunnel {tun['name']}", "UP" if tun["up"] else "DOWN", st, "UP, error 0",
                               f"selector {tun['selectors_up']}/{tun['selectors_total']}, error rx/tx {tun['rx_err']}/{tun['tx_err']}"))
        for m in s.get("sdwan", []):
            if m["state"] != "alive":
                st, val = "bad", m["state"]
            else:
                st = PROBE_TO_STATUS[analysis.probe_level(
                    {"loss_pct": m.get("loss_pct") or 0, "rtt_avg": m.get("latency_ms"), "jitter_ms": m.get("jitter_ms")}, t)]
                val = f"latency {m.get('latency_ms')} ms · jitter {m.get('jitter_ms')} ms · loss {m.get('loss_pct')}%"
            items.append(_item("fgt_sla", f"{name}: SD-WAN SLA {m['check']} via {m['member']}", val, st,
                               f"alive, loss < {t['loss_warn']}%, latency < {t['latency_warn']} ms"))
        if s.get("cpu_pct") is not None:
            items.append(_item("fgt_cpu", f"{name}: firewall CPU / memory", f"{s['cpu_pct']}% / {s.get('mem_pct')}%",
                               _worst([_grade(s["cpu_pct"], t["fgt_cpu_warn"], 90), _grade(s.get("mem_pct"), t["fgt_mem_warn"], 88)]),
                               f"CPU < {t['fgt_cpu_warn']}%, memory < {t['fgt_mem_warn']}%",
                               f"{s.get('sessions')} sessions, traffic {s.get('net_in_kbps')}/{s.get('net_out_kbps')} kbps, EBS route via {', '.join(s.get('ebs_route_via') or []) or '—'}"))
    return items


def _sec_ebs_web(probes, ebs, t):
    items = []
    for it in _probe_items(probes, "ebs_web", "web_probe", t):
        items.append(it)
    for p in probes:
        if p["segment"] == "ebs_web" and p["enabled"] and p["check_type"] == "http" and (p.get("last") or {}).get("rtt_avg") is not None:
            ttfb = p["last"]["rtt_avg"]
            items.append(_item("web_ttfb", f"Page response time {p['name']}", ttfb,
                               _grade(ttfb, t["ttfb_warn"], t["ttfb_warn"] * 2), f"< {t['ttfb_warn']} ms",
                               f"HTTP {p['last'].get('http_status')}", "ms"))
    if not ebs:
        return items
    for srv in ebs.get("app_tier", []):
        if srv.get("status") != "online":
            items.append(_item("app_os", f"Server {srv.get('server_label')}", srv.get("error") or srv.get("status"),
                               "unknown" if srv.get("status") == "not_configured" else "bad", "online"))
            continue
        st = _worst([_grade(srv.get("cpu"), 70, 90), _grade(srv.get("memory_percent"), 85, 95), _grade(srv.get("swap_percent"), 10, 30)])
        items.append(_item("app_os", f"Server {srv.get('server_label')} ({srv.get('server_ip')})",
                           f"CPU {srv.get('cpu')}% · mem {srv.get('memory_percent')}% · swap {srv.get('swap_percent')}% · load {srv.get('load')}/{srv.get('cpu_count')} vCPU",
                           st, "CPU < 70%, mem < 85%, swap < 10%", f"uptime {srv.get('uptime')}"))
    if ebs.get("icm_up") is not None:
        items.append(_item("app_icm", "Internal Concurrent Manager", "UP" if ebs["icm_up"] else "DOWN",
                           "good" if ebs["icm_up"] else "bad", "UP"))
    down = ebs.get("managers_down") or []
    if ebs.get("managers"):
        items.append(_item("app_mgr", "Concurrent managers below target", f"{len(down)} manager" + (f": {', '.join(m['name'] for m in down[:4])}" if down else ""),
                           "good" if not down else "warn", "0"))
    if ebs.get("requests_pending") is not None:
        items.append(_item("app_pending", "Concurrent request pending", ebs["requests_pending"],
                           _grade(ebs["requests_pending"], 50, 200), "< 50", f"running {ebs.get('requests_running')}, errors in 1 h {ebs.get('requests_errors_1h')}"))
        items.append(_item("app_long", "Requests running > 1 hour", ebs.get("requests_long_running"),
                           _grade(ebs.get("requests_long_running"), 1, 5), "0"))
    return items


def _sec_ebs_db(probes, ebs, t):
    items = _probe_items(probes, "ebs_db", "db_probe", t)
    if not ebs:
        return items
    items.append(_item("db_connect", "Dashboard → DB connect time", ebs.get("db_connect_ms"),
                       _grade(ebs.get("db_connect_ms"), 300, 1500), "< 300 ms", "includes the Oracle login", "ms"))
    items.append(_item("db_cpu", "Database host CPU", ebs.get("host_cpu_pct"), _grade(ebs.get("host_cpu_pct"), 75, 90),
                       "< 75 %", f"avg active sessions {ebs.get('avg_active_sessions')}, wait ratio {ebs.get('db_wait_ratio')}%", "%"))
    items.append(_item("db_block", "Sessions blocked by locks", ebs.get("sessions_blocked"), _grade(ebs.get("sessions_blocked"), 1, 5), "0",
                       f"active sessions {ebs.get('sessions_active')}/{ebs.get('sessions_total')}, Forms {ebs.get('forms_sessions')}"))
    items.append(_item("db_long", "SQL active > 5 minutes", len(ebs.get("long_sql") or []), _grade(len(ebs.get("long_sql") or []), 1, 5), "0"))
    items.append(_item("db_io", "Single-block read latency", ebs.get("single_block_read_ms"),
                       _grade(ebs.get("single_block_read_ms"), 10, 20), "< 10 ms", "", "ms"))
    waits = ebs.get("waits") or []
    if waits:
        items.append(_item("db_wait", "Top wait event right now", f"{waits[0]['event']} ({waits[0]['sessions']} sessions)", "good" if waits[0]["sessions"] < 5 else "warn",
                           "information", "; ".join(f"{w['event']} ×{w['sessions']}" for w in waits[1:4])))
    for k, v in (ebs.get("query_errors") or {}).items():
        items.append(_item("db_query", f"Query {k}", v, "unknown", "query succeeds", "Usually the v$ view grants for the APPS user."))
    return items


# ── Build ─────────────────────────────────────────────────────────────────

def _section(key, items):
    st = _worst([i["status"] for i in items])
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("good", "warn", "bad", "unknown")}
    return {"key": key, "label": SECTION_LABEL[key], "status": st, "status_label": STATUS_LABEL[st],
            "counts": counts, "items": items}


def build(db, trigger: str = "manual", user: str | None = None, capture: bool = True) -> EbsNetSummaryReport:
    with _build_lock:
        return _build(db, trigger, user, capture)


def _build(db, trigger: str, user: str | None, capture: bool) -> EbsNetSummaryReport:
    start = time.perf_counter()
    s = cfg.get_all(db)
    t = s["thresholds"]
    captured = service.capture_all(db) if capture else None

    probes = service.latest_probes(db)
    fgs = service.latest_snapshots(db, "fortigate")
    ebs_snap = (service.latest_snapshots(db, "ebs") or [None])[0]
    ebs = ebs_snap["summary"] if ebs_snap and ebs_snap.get("ok") else None
    window = int(s.get("report_client_window_hours") or 24)
    clients = service.list_reports(db, hours=window, limit=500)
    since7 = datetime.utcnow() - timedelta(days=7)
    incidents = db.query(EbsNetIncident).filter(EbsNetIncident.started_at >= since7).all()

    sections = [
        _section("laptop", _sec_laptop(clients, t)),
        _section("ho_lan", _sec_ho_lan(clients, t)),
        _section("wan", _sec_wan(probes, fgs, clients, t)),
        _section("plant_lan", _probe_items(probes, "plant_lan", "plant_probe", t)),
        _section("ebs_web", _sec_ebs_web(probes, ebs, t)),
        _section("ebs_db", _sec_ebs_db(probes, ebs, t)),
        _section("internet", _probe_items(probes, "internet", "inet_probe", t)),
    ]
    by = {sec["key"]: sec for sec in sections}

    bottleneck = next((k for k in PATH if by[k]["status"] == "bad"), None) \
        or next((k for k in PATH if by[k]["status"] == "warn"), None)
    measured = [sec for sec in sections if sec["status"] != "unknown"]
    overall = _worst([sec["status"] for sec in sections])

    # Data gaps
    gaps = []
    if not service.fortigate_ids(s):
        gaps.append(GAP_ACTIONS["fortigate"])
    if not any(p["segment"] == "wan" and p["enabled"] for p in probes):
        gaps.append(GAP_ACTIONS["wan_target"])
    if not any(p["segment"] == "ebs_web" and p["enabled"] for p in probes):
        gaps.append(GAP_ACTIONS["web_target"])
    if not clients:
        gaps.append(GAP_ACTIONS["clients"])
    elif not any(c.get("gw_rtt_avg") is not None for c in clients):
        gaps.append(GAP_ACTIONS["agent"])
    if not ebs:
        gaps.append(GAP_ACTIONS["ebs"])

    # Conclusion
    conclusion = []
    case = None
    if bottleneck:
        sec = by[bottleneck]
        case = next(c for k, _, c in SECTIONS if k == bottleneck)
        bad_items = [i for i in sec["items"] if i["status"] == sec["status"]]
        headline = (f"Main bottleneck at {sec['label']} ({sec['status_label'].lower()}): "
                    + "; ".join(f"{i['name']} = {_fmt(i['value'], i['unit'])}" for i in bad_items[:3]))
        conclusion.append(headline + ".")
        if case:
            conclusion.append(analysis.VERDICT_TEXT[case])
        before = [by[k] for k in PATH[:PATH.index(bottleneck)]]
        ok_before = [b["label"] for b in before if b["status"] == "good"]
        unk_before = [b["label"] for b in before if b["status"] == "unknown"]
        if ok_before:
            conclusion.append(f"The segments before it are normal ({', '.join(ok_before)}), so the problem starts at {sec['label']}.")
        if unk_before:
            conclusion.append(f"Note: {', '.join(unk_before)} has no data yet — the bottleneck could already start there.")
        after = [by[k]["label"] for k in PATH[PATH.index(bottleneck) + 1:] if by[k]["status"] in ("warn", "bad")]
        if after:
            conclusion.append(f"Other segments with problems: {', '.join(after)} — fix {sec['label']} first, "
                              f"because a hold-up early on makes the segments after it look slow too.")
        if bottleneck in ("wan", "plant_lan") and by["internet"]["status"] in ("warn", "bad"):
            conclusion.append("Internet from Plant is also bad at the same time — a strong indication of a Plant ISP problem (NET-08).")
        if bottleneck in ("ebs_web", "ebs_db") and all(by[k]["status"] in ("good", "unknown") for k in ("laptop", "ho_lan", "wan")):
            conclusion.append("The HO → Plant network is normal: the slowness comes from the application/database side, not the network.")
    else:
        headline = ("No bottleneck found in the measured segments."
                    if measured else "Not enough data yet to grade.")
        conclusion.append(headline)
        unknown = [sec["label"] for sec in sections if sec["status"] == "unknown"]
        if unknown:
            conclusion.append(f"No data yet for: {', '.join(unknown)}. Fill these in so the conclusion can be trusted.")
        if any(c.get("ebs_condition") in ("Slow", "Hang", "Restart") for c in clients):
            conclusion.append("Some users report slowness although every figure is normal — probably an intermittent problem: "
                              "ask users to run the test EXACTLY while it is slow and log an incident with a snapshot.")
    open_inc = [i for i in incidents if i.status != "resolved"]
    if incidents:
        conclusion.append(f"Incidents in the last 7 days: {len(incidents)} ({len(open_inc)} not resolved).")

    # Actions: bottleneck section first, then path order, bad before warn.
    seq = ([bottleneck] if bottleneck else []) + [k for k in PATH + ["internet"] if k != bottleneck]
    order = {k: i for i, k in enumerate(seq)}
    actions, seen = [], set()
    for sec in sorted(sections, key=lambda x: order.get(x["key"], 99)):
        for it in sorted(sec["items"], key=lambda i: -RANK[i["status"]]):
            if it["action"] and it["action"] not in seen:
                seen.add(it["action"])
                actions.append({"priority": "high" if it["status"] == "bad" else "medium",
                                "section": sec["label"], "item": it["name"], "text": it["action"]})
    for g in gaps:
        actions.append({"priority": "data", "section": "Data completeness", "item": "", "text": g})
    if not any(a["priority"] != "data" for a in actions):
        actions.insert(0, {"priority": "routine", "section": "Operations", "item": "",
                           "text": "Keep the baseline: leave automatic reports running; compare with a report taken when there is a complaint."})

    created = datetime.utcnow()
    content = {
        "created_at": created.isoformat() + "Z", "trigger": trigger, "created_by": user,
        "overall": overall, "overall_label": STATUS_LABEL[overall],
        "bottleneck": bottleneck, "bottleneck_label": SECTION_LABEL.get(bottleneck),
        "case": case, "headline": headline, "conclusion": conclusion, "actions": actions,
        "sections": sections, "data_gaps": gaps,
        "context": {
            "client_window_hours": window, "client_reports": len(clients),
            "incidents_7d": len(incidents), "incidents_open": len(open_inc),
            "ebs_environment": (ebs or {}).get("environment"),
            "fortigates": [f["name"] for f in fgs],
            "thresholds": t,
        },
    }
    content["duration_s"] = round(time.perf_counter() - start, 1)
    row = EbsNetSummaryReport(
        created_at=created, trigger=trigger, created_by=user, overall=overall, bottleneck=bottleneck,
        headline=headline, content=json.dumps(content, default=str), duration_s=content["duration_s"],
    )
    row.html = render_html(content)
    db.add(row)
    db.query(EbsNetSummaryReport).filter(
        EbsNetSummaryReport.created_at < created - timedelta(days=REPORT_RETENTION_DAYS)).delete()
    db.commit()
    db.refresh(row)
    return row


def row_dict(r: EbsNetSummaryReport, full: bool = False) -> dict:
    d = {"id": r.id, "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
         "trigger": r.trigger, "created_by": r.created_by, "overall": r.overall,
         "overall_label": STATUS_LABEL.get(r.overall or "unknown"), "bottleneck": r.bottleneck,
         "bottleneck_label": SECTION_LABEL.get(r.bottleneck), "headline": r.headline, "duration_s": r.duration_s}
    if full:
        d["content"] = json.loads(r.content) if r.content else None
    return d


def last_auto(db) -> datetime | None:
    r = (db.query(EbsNetSummaryReport.created_at).filter(EbsNetSummaryReport.trigger == "auto")
         .order_by(EbsNetSummaryReport.created_at.desc()).first())
    return r[0] if r else None


def due(db) -> bool:
    hours = float(cfg.get_all(db).get("report_interval_hours") or 0)
    if hours <= 0:
        return False
    last = last_auto(db)
    # 2-minute slack: the poller ticks every 5 min, so "3 hours" lands on
    # the tick at or just before the mark rather than drifting 5 min later.
    return last is None or datetime.utcnow() - last >= timedelta(hours=hours) - timedelta(minutes=2)


# ── HTML file ─────────────────────────────────────────────────────────────

_COLORS = {"good": "#0a7d0a", "warn": "#9a6700", "bad": "#c62828", "unknown": "#64748b"}
_BG = {"good": "#e8f5e9", "warn": "#fff4d6", "bad": "#fdecea", "unknown": "#f1f5f9"}
_ICON = {"good": "✔", "warn": "▲", "bad": "✖", "unknown": "?"}


def _badge(status, label=None):
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-weight:700;font-size:11px;'
            f'color:{_COLORS[status]};background:{_BG[status]}">{_ICON[status]} {html.escape(label or STATUS_LABEL[status])}</span>')


def render_html(c: dict) -> str:
    e = html.escape
    created = datetime.fromisoformat(c["created_at"].rstrip("Z")) + timedelta(hours=7)
    chain = "".join(
        f'<td style="padding:8px;border-radius:8px;background:{_BG[sec["status"]]};border:{"3px solid " + _COLORS["bad"] if sec["key"] == c["bottleneck"] else "1px solid #e2e8f0"};'
        f'text-align:center;font-size:12px"><b>{e(sec["label"])}</b><br>{_badge(sec["status"])}'
        f'{"<br><b style=color:#c62828>◀ BOTTLENECK</b>" if sec["key"] == c["bottleneck"] else ""}</td>'
        f'{"<td style=color:#94a3b8>→</td>" if i < len(PATH) - 1 else ""}'
        for i, sec in enumerate(s for s in c["sections"] if s["key"] in PATH))
    sections_html = ""
    for sec in c["sections"]:
        rows = "".join(
            f'<tr><td>{e(i["name"])}</td><td>{e(_fmt(i["value"], i["unit"]))}</td><td>{e(i["standard"])}</td>'
            f'<td>{_badge(i["status"])}</td><td>{e(i["note"] or "")}</td></tr>' for i in sec["items"])
        sections_html += (
            f'<h3 style="margin:22px 0 6px">{e(sec["label"])} {_badge(sec["status"])}</h3>'
            + (f'<table><tr><th>Item</th><th>Value</th><th>Standard</th><th>Status</th><th>Notes</th></tr>{rows}</table>'
               if rows else '<p style="color:#64748b">No data for this segment.</p>'))
    actions = "".join(
        f'<tr><td><b>{e(a["priority"])}</b></td><td>{e(a["section"])}</td><td>{e(a["text"])}'
        f'{"<br><span style=color:#64748b>" + e(a["item"]) + "</span>" if a["item"] else ""}</td></tr>' for a in c["actions"])
    concl = "".join(f"<li>{e(x)}</li>" for x in c["conclusion"])
    ctx = c["context"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EBS HO-Plant Diagnosis Report {created:%Y-%m-%d %H:%M}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;color:#0f172a;max-width:1100px;margin:24px auto;padding:0 16px;font-size:13px;background:#fff}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f8fafc;color:#475569;font-size:12px}} h1{{font-size:20px;margin-bottom:2px}} h2{{font-size:16px;margin-top:26px}}
.box{{border-radius:10px;padding:12px 14px;margin:12px 0}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>Oracle EBS Access Diagnosis Report — HO ↔ Plant</h1>
<div style="color:#64748b">{created:%d %B %Y %H:%M} WIB · {"automatic" if c["trigger"] == "auto" else "manual by " + e(c.get("created_by") or "-")}
 · EBS environment: {e(str(ctx.get("ebs_environment") or "-"))} · {ctx["client_reports"]} laptop tests (last {ctx["client_window_hours"]} hours)
 · incidents in 7 days: {ctx["incidents_7d"]} · processing time {c.get("duration_s")} s</div>
<div class="box" style="background:{_BG[c["overall"]]};border:1px solid {_COLORS[c["overall"]]}55">
<div style="font-size:15px"><b>Overall status:</b> {_badge(c["overall"])}
{" &nbsp; <b>Bottleneck:</b> " + e(c["bottleneck_label"]) if c["bottleneck"] else ""}</div>
<p style="margin:8px 0 0;font-size:14px"><b>{e(c["headline"])}</b></p></div>
<h2>Access path</h2>
<table style="border:none"><tr style="border:none">{chain}</tr></table>
<p>Internet / Plant ISP: {_badge(next(s for s in c["sections"] if s["key"] == "internet")["status"])}</p>
<h2>Conclusion</h2><ul>{concl}</ul>
<h2>Actions</h2>
<table><tr><th style="width:80px">Priority</th><th style="width:170px">Segment</th><th>Action</th></tr>{actions}</table>
<h2>Data &amp; grading per segment</h2>
{sections_html}
<p style="margin-top:28px;color:#94a3b8;font-size:11px">Standard = internal operational baseline (not an official Oracle requirement).
The conclusion is a direction for investigation based on the data when the report was made — confirm with repeated measurements before changing VPN, routing, MTU, firewall or Oracle configuration.
Generated by the CKDO Dashboard · Oracle EBS Network Monitoring.</p>
</body></html>"""
