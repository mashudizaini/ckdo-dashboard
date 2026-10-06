"""
Diagnosis report ("Laporan" tab): re-take every measurement, grade each
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
STATUS_LABEL = {"good": "Bagus", "warn": "Waspada", "bad": "Buruk", "unknown": "Tidak ada data"}
PROBE_TO_STATUS = {"ok": "good", "warn": "warn", "crit": "bad", "unknown": "unknown"}
REPORT_RETENTION_DAYS = 180
# One build at a time: a manual "Proses" during an automatic run would
# otherwise SSH into the same FortiGates twice in parallel.
_build_lock = threading.Lock()

SECTIONS = [
    ("laptop",    "Laptop HO (client)",        "D"),
    ("ho_lan",    "LAN HO",                    "A"),
    ("wan",       "Jalur HO ↔ Plant (WAN/VPN)", "B"),
    ("plant_lan", "LAN Plant",                 "B"),
    ("ebs_web",   "EBS Web / App Tier",        "C"),
    ("ebs_db",    "EBS Database",              "C"),
    ("internet",  "Internet / ISP Plant",      None),
]
PATH = [s[0] for s in SECTIONS if s[0] != "internet"]
SECTION_LABEL = {k: l for k, l, _ in SECTIONS}

# What to do when an item is not good — keyed by item `key` prefix.
ACTIONS = {
    "cli_tests": "Jalankan Client Test / agen PowerShell di minimal 3 laptop HO, di jam 08:00, 11:00, 14:00 dan 15:00–16:00.",
    "cli_case_d": "Periksa laptop yang ditandai Case D: tutup aplikasi berat, cek RAM/CPU, bersihkan cache Java/browser, bandingkan dengan laptop lain di meja yang sama.",
    "cli_cpu": "Laptop dengan CPU tinggi: cek proses teratas di laporan agen (antivirus scan, Teams, update), atur power plan Balanced/High performance.",
    "cli_ram": "Laptop dengan RAM bebas < 20 %: kurangi aplikasi/tab terbuka atau upgrade RAM ke ≥ 8–16 GB.",
    "cli_slow": "User melaporkan EBS lambat/hang: catat sebagai insiden dengan snapshot saat kejadian agar bisa dikorelasikan.",
    "lan_gw_rtt": "RTT laptop → gateway HO tinggi: pindahkan user Forms ke kabel LAN, cek AP/switch HO, channel Wi-Fi dan beban klien per AP.",
    "lan_gw_loss": "Packet loss di LAN HO: cek kabel/port switch, error interface switch, dan sinyal Wi-Fi; ini harus 0 % sebelum menyalahkan WAN.",
    "lan_wifi": "Sinyal Wi-Fi lemah: dekatkan ke AP / tambah AP, gunakan 5 GHz, atau gunakan kabel LAN.",
    "lan_case_a": "Banyak laptop menunjukkan Case A: lakukan survey Wi-Fi HO dan audit switch HO.",
    "wan_probe": "Probe melewati tunnel buruk: cek status tunnel & SD-WAN SLA di FortiGate, utilisasi link ISP, lalu minta data ISP pada jam yang sama.",
    "wan_e2e": "RTT/jitter end-to-end laptop → Plant di atas baseline: cek utilisasi WAN, QoS untuk EBS, dan apakah traffic EBS memakai link terbaik (SD-WAN rule).",
    "wan_mtu": "Path MTU kecil: set tcp-mss ±1350 di policy tunnel EBS untuk mencegah fragmentasi (NET-06).",
    "fgt_tunnel": "Tunnel IPsec down / error: cek log VPN FortiGate (renegosiasi, DPD), sambungan ISP, dan siapkan tunnel cadangan via iForte.",
    "fgt_sla": "SD-WAN SLA member buruk / mati: cek link ISP terkait; pastikan rule SD-WAN EBS berbasis SLA agar pindah ke link sehat.",
    "fgt_cpu": "CPU/memori FortiGate tinggi: cek sesi teratas, profil UTM pada traffic internal, dan NPU offload tunnel.",
    "plant_probe": "LAN Plant buruk: cek switch core Plant, port server, dan beban jaringan lokal Plant.",
    "web_probe": "Web/app tier EBS lambat atau tak terjangkau: cek status OHS/WebLogic (oacore, forms), CPU/heap managed server, dan log error.",
    "web_ttfb": "Waktu respons halaman login EBS tinggi padahal jaringan normal: masalah di application tier (OHS/oacore), bukan network.",
    "app_os": "Server EBS CPU/memori/swap tinggi: cek proses teratas di Server Process Monitoring, sizing JVM, dan concurrent request berat.",
    "app_icm": "Internal Concurrent Manager mati: start ulang Concurrent Manager (adcmctl.sh) dan cek log ICM.",
    "app_mgr": "Concurrent manager di bawah target: cek manager terkait di Administer Concurrent Managers.",
    "app_pending": "Antrian concurrent request menumpuk: cek request yang macet/berat, tambah proses manager atau jadwalkan ulang ke luar jam kerja.",
    "app_long": "Ada request berjalan > 1 jam: cek apakah wajar; request berat di jam kerja menaikkan beban DB.",
    "db_probe": "Listener DB lambat/tak terjangkau: cek listener (lsnrctl status), CPU server DB dan jaringan Plant.",
    "db_connect": "Koneksi ke DB lambat: cek listener, beban server DB, dan resolusi DNS/host.",
    "db_cpu": "CPU host DB tinggi: ambil AWR/ASH, cari Top SQL; jadwalkan job berat di luar jam kerja.",
    "db_block": "Ada sesi terblokir lock: identifikasi sesi pemblokir di tab EBS Server, koordinasikan dengan user sebelum kill session.",
    "db_long": "SQL aktif > 5 menit: cek SQL ID di AWR, statistik tabel (Gather Schema Statistics), dan index.",
    "db_io": "Latency baca disk DB tinggi: cek storage/datastore DB, I/O VM host, dan backup yang berjalan di jam kerja.",
    "inet_probe": "Internet dari Plant juga buruk: kemungkinan masalah ISP Plant (NET-08) — eskalasi ke ISP dengan data probe ini.",
}

GAP_ACTIONS = {
    "fortigate": "Pilih FortiGate HO & Plant di Setup (dari Server Control) agar status tunnel & SD-WAN SLA ikut dinilai.",
    "wan_target": "Tambahkan target segmen Jalur HO ↔ Plant (mis. IP LAN FortiGate HO:443) di Setup.",
    "web_target": "Aktifkan target web EBS (host:port) dan URL login (HTTP TTFB) di Setup.",
    "clients": "Belum ada tes laptop dalam jendela laporan — minta user HO membuka /dashboard/ebs-check atau jalankan agen.",
    "agent": "Belum ada laporan agen PowerShell — LAN HO (gateway, Wi-Fi) hanya terukur dari agen.",
    "ebs": "Snapshot kesehatan EBS gagal — cek koneksi Oracle dashboard.",
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
               if last.get("rtt_avg") is not None else (last.get("error") or "tidak ada balasan"))
        note = (f"24 jam: avg {day.get('rtt_avg')} ms, max {day.get('rtt_max')} ms, loss rata-rata {day.get('loss_avg')}% ({day.get('runs')} kali)"
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
    items.append(_item("cli_tests", "Jumlah tes laptop", f"{n} tes dari {len(hosts)} laptop/user",
                       "unknown" if n == 0 else "good" if n >= 3 else "warn", "≥ 3 tes dari beberapa laptop"))
    if not n:
        return items
    d = [c for c in clients if c["verdict"] == "D"]
    share = len(d) / n
    items.append(_item("cli_case_d", "Tes dengan indikasi masalah laptop (Case D)",
                       f"{len(d)} dari {n}" + (f" — {', '.join(sorted({c['hostname'] or c['reported_by'] for c in d}))[:120]}" if d else ""),
                       "good" if not d else "bad" if share >= 0.5 else "warn", "0"))
    cpu = [c for c in clients if (c.get("cpu_pct") or 0) >= t["cpu_warn"]]
    with_cpu = [c for c in clients if c.get("cpu_pct") is not None]
    if with_cpu:
        items.append(_item("cli_cpu", "Laptop CPU tinggi saat tes", f"{len(cpu)} dari {len(with_cpu)} (median {_med([c['cpu_pct'] for c in with_cpu])}%)",
                           "good" if not cpu else "warn", f"CPU < {t['cpu_warn']}%"))
    ram = [c for c in clients if c.get("ram_avail_pct") is not None and c["ram_avail_pct"] < t["ram_avail_warn"]]
    with_ram = [c for c in clients if c.get("ram_avail_pct") is not None]
    if with_ram:
        items.append(_item("cli_ram", "Laptop RAM bebas rendah", f"{len(ram)} dari {len(with_ram)} (median {_med([c['ram_avail_pct'] for c in with_ram])}%)",
                           "good" if not ram else "bad" if len(ram) / len(with_ram) >= 0.5 else "warn", f"RAM bebas > {t['ram_avail_warn']}%"))
    slow = [c for c in clients if c.get("ebs_condition") in ("Slow", "Hang", "Restart")]
    items.append(_item("cli_slow", "User melaporkan EBS lambat/hang saat tes", f"{len(slow)} dari {n}",
                       "good" if not slow else "warn", "0",
                       "Kondisi yang dirasakan user — pembanding untuk angka teknis."))
    return items


def _sec_ho_lan(clients, t):
    agents = [c for c in clients if c.get("gw_rtt_avg") is not None]
    if not agents:
        return [_item("lan_gw_rtt", "RTT laptop → gateway HO", None, "unknown", f"< {t['lan_rtt_warn']} ms",
                      "Hanya terukur dari agen PowerShell di laptop HO.")]
    rtt = _med([c["gw_rtt_avg"] for c in agents])
    loss = _med([c.get("gw_loss_pct") for c in agents])
    items = [
        _item("lan_gw_rtt", "RTT laptop → gateway HO (median)", rtt,
              _grade(rtt, t["lan_rtt_warn"], t["lan_rtt_warn"] * 4), f"< {t['lan_rtt_warn']} ms (kabel ±1 ms)", f"{len(agents)} laporan agen", "ms"),
        _item("lan_gw_loss", "Packet loss laptop → gateway (median)", loss,
              _grade(loss, 0.01, 1), "0 %", "", "%"),
    ]
    wifi = [c for c in agents if c.get("wifi_signal") is not None]
    if wifi:
        sig = _med([c["wifi_signal"] for c in wifi])
        items.append(_item("lan_wifi", "Sinyal Wi-Fi laptop (median)", sig, _grade(sig, 70, 50, higher_is_bad=False),
                           "> 70 %", f"{len(wifi)} dari {len(agents)} laptop memakai Wi-Fi", "%"))
    a = [c for c in agents if c["verdict"] == "A"]
    items.append(_item("lan_case_a", "Laporan agen dengan Case A (LAN bermasalah)", f"{len(a)} dari {len(agents)}",
                       "good" if not a else "bad" if len(a) / len(agents) >= 0.5 else "warn", "0"))
    return items


def _sec_wan(probes, fgs, clients, t):
    items = _probe_items(probes, "wan", "wan_probe", t)
    if clients:
        rtt = _med([c.get("ebs_rtt_avg") for c in clients])
        jit = _med([c.get("ebs_jitter_ms") for c in clients])
        loss = _med([c.get("ebs_loss_pct") for c in clients])
        items.append(_item("wan_e2e", "RTT laptop HO → Plant (median semua tes)", rtt,
                           _grade(rtt, t["latency_warn"], t["latency_crit"]), f"< {t['latency_warn']} ms",
                           f"jitter median {_fmt(jit, 'ms')}, loss median {_fmt(loss, '%')}", "ms"))
        if jit is not None:
            items.append(_item("wan_e2e", "Jitter laptop HO → Plant (median)", jit,
                               _grade(jit, t["jitter_warn"], t["jitter_crit"]), f"< {t['jitter_warn']} ms", "", "ms"))
        if loss is not None:
            items.append(_item("wan_e2e", "Loss laptop HO → Plant (median)", loss,
                               _grade(loss, t["loss_warn"], t["loss_crit"]), "0 %", "", "%"))
        mtus = [c["path_mtu"] for c in clients if c.get("path_mtu")]
        if mtus:
            mtu = min(mtus)
            items.append(_item("wan_mtu", "Path MTU terkecil laptop → EBS", mtu, _grade(mtu, 1400, 1350, higher_is_bad=False),
                               "≥ 1400 (MSS clamping bila lebih kecil)", f"dari {len(mtus)} laporan agen"))
    for fg in fgs:
        name = fg["name"]
        if not fg.get("ok"):
            items.append(_item("fgt_tunnel", f"{name}: snapshot", fg.get("error"), "unknown", "SSH berhasil"))
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
            items.append(_item("fgt_cpu", f"{name}: CPU / memori firewall", f"{s['cpu_pct']}% / {s.get('mem_pct')}%",
                               _worst([_grade(s["cpu_pct"], t["fgt_cpu_warn"], 90), _grade(s.get("mem_pct"), t["fgt_mem_warn"], 88)]),
                               f"CPU < {t['fgt_cpu_warn']}%, memori < {t['fgt_mem_warn']}%",
                               f"{s.get('sessions')} sesi, trafik {s.get('net_in_kbps')}/{s.get('net_out_kbps')} kbps, rute EBS via {', '.join(s.get('ebs_route_via') or []) or '—'}"))
    return items


def _sec_ebs_web(probes, ebs, t):
    items = []
    for it in _probe_items(probes, "ebs_web", "web_probe", t):
        items.append(it)
    for p in probes:
        if p["segment"] == "ebs_web" and p["enabled"] and p["check_type"] == "http" and (p.get("last") or {}).get("rtt_avg") is not None:
            ttfb = p["last"]["rtt_avg"]
            items.append(_item("web_ttfb", f"Waktu respons halaman {p['name']}", ttfb,
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
        items.append(_item("app_mgr", "Concurrent manager di bawah target", f"{len(down)} manager" + (f": {', '.join(m['name'] for m in down[:4])}" if down else ""),
                           "good" if not down else "warn", "0"))
    if ebs.get("requests_pending") is not None:
        items.append(_item("app_pending", "Concurrent request pending", ebs["requests_pending"],
                           _grade(ebs["requests_pending"], 50, 200), "< 50", f"running {ebs.get('requests_running')}, error 1 jam {ebs.get('requests_errors_1h')}"))
        items.append(_item("app_long", "Request berjalan > 1 jam", ebs.get("requests_long_running"),
                           _grade(ebs.get("requests_long_running"), 1, 5), "0"))
    return items


def _sec_ebs_db(probes, ebs, t):
    items = _probe_items(probes, "ebs_db", "db_probe", t)
    if not ebs:
        return items
    items.append(_item("db_connect", "Waktu koneksi dashboard → DB", ebs.get("db_connect_ms"),
                       _grade(ebs.get("db_connect_ms"), 300, 1500), "< 300 ms", "termasuk login Oracle", "ms"))
    items.append(_item("db_cpu", "CPU host database", ebs.get("host_cpu_pct"), _grade(ebs.get("host_cpu_pct"), 75, 90),
                       "< 75 %", f"avg active sessions {ebs.get('avg_active_sessions')}, wait ratio {ebs.get('db_wait_ratio')}%", "%"))
    items.append(_item("db_block", "Sesi terblokir lock", ebs.get("sessions_blocked"), _grade(ebs.get("sessions_blocked"), 1, 5), "0",
                       f"sesi aktif {ebs.get('sessions_active')}/{ebs.get('sessions_total')}, Forms {ebs.get('forms_sessions')}"))
    items.append(_item("db_long", "SQL aktif > 5 menit", len(ebs.get("long_sql") or []), _grade(len(ebs.get("long_sql") or []), 1, 5), "0"))
    items.append(_item("db_io", "Latency baca single-block", ebs.get("single_block_read_ms"),
                       _grade(ebs.get("single_block_read_ms"), 10, 20), "< 10 ms", "", "ms"))
    waits = ebs.get("waits") or []
    if waits:
        items.append(_item("db_wait", "Wait event teratas saat ini", f"{waits[0]['event']} ({waits[0]['sessions']} sesi)", "good" if waits[0]["sessions"] < 5 else "warn",
                           "informasi", "; ".join(f"{w['event']} ×{w['sessions']}" for w in waits[1:4])))
    for k, v in (ebs.get("query_errors") or {}).items():
        items.append(_item("db_query", f"Query {k}", v, "unknown", "query berhasil", "Biasanya grant v$ view untuk user APPS."))
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
        headline = (f"Hambatan utama di {sec['label']} ({sec['status_label'].lower()}): "
                    + "; ".join(f"{i['name']} = {_fmt(i['value'], i['unit'])}" for i in bad_items[:3]))
        conclusion.append(headline + ".")
        if case:
            conclusion.append(analysis.VERDICT_TEXT[case])
        before = [by[k] for k in PATH[:PATH.index(bottleneck)]]
        ok_before = [b["label"] for b in before if b["status"] == "good"]
        unk_before = [b["label"] for b in before if b["status"] == "unknown"]
        if ok_before:
            conclusion.append(f"Segmen sebelumnya normal ({', '.join(ok_before)}), jadi masalah dimulai di {sec['label']}.")
        if unk_before:
            conclusion.append(f"Catatan: {', '.join(unk_before)} belum ada data — hambatan bisa saja sudah dimulai di sana.")
        after = [by[k]["label"] for k in PATH[PATH.index(bottleneck) + 1:] if by[k]["status"] in ("warn", "bad")]
        if after:
            conclusion.append(f"Segmen lain yang juga bermasalah: {', '.join(after)} — selesaikan {sec['label']} dulu, "
                              f"karena hambatan di depan ikut membuat segmen di belakangnya terlihat lambat.")
        if bottleneck in ("wan", "plant_lan") and by["internet"]["status"] in ("warn", "bad"):
            conclusion.append("Internet dari Plant juga buruk pada saat yang sama — indikasi kuat masalah ISP Plant (NET-08).")
        if bottleneck in ("ebs_web", "ebs_db") and all(by[k]["status"] in ("good", "unknown") for k in ("laptop", "ho_lan", "wan")):
            conclusion.append("Jaringan HO → Plant normal: keluhan lambat bersumber dari sisi aplikasi/database, bukan network.")
    else:
        headline = ("Tidak ditemukan hambatan pada segmen yang terukur."
                    if measured else "Belum ada data yang cukup untuk menilai.")
        conclusion.append(headline)
        unknown = [sec["label"] for sec in sections if sec["status"] == "unknown"]
        if unknown:
            conclusion.append(f"Belum ada data untuk: {', '.join(unknown)}. Lengkapi agar kesimpulan bisa dipercaya.")
        if any(c.get("ebs_condition") in ("Slow", "Hang", "Restart") for c in clients):
            conclusion.append("Ada user yang melaporkan lambat walau semua angka normal — kemungkinan masalah sesaat (intermittent): "
                              "minta user menjalankan tes TEPAT saat lambat dan catat insiden dengan snapshot.")
    open_inc = [i for i in incidents if i.status != "resolved"]
    if incidents:
        conclusion.append(f"Insiden 7 hari terakhir: {len(incidents)} ({len(open_inc)} belum selesai).")

    # Actions: bottleneck section first, then path order, bad before warn.
    seq = ([bottleneck] if bottleneck else []) + [k for k in PATH + ["internet"] if k != bottleneck]
    order = {k: i for i, k in enumerate(seq)}
    actions, seen = [], set()
    for sec in sorted(sections, key=lambda x: order.get(x["key"], 99)):
        for it in sorted(sec["items"], key=lambda i: -RANK[i["status"]]):
            if it["action"] and it["action"] not in seen:
                seen.add(it["action"])
                actions.append({"priority": "tinggi" if it["status"] == "bad" else "sedang",
                                "section": sec["label"], "item": it["name"], "text": it["action"]})
    for g in gaps:
        actions.append({"priority": "data", "section": "Kelengkapan data", "item": "", "text": g})
    if not any(a["priority"] != "data" for a in actions):
        actions.insert(0, {"priority": "rutin", "section": "Operasional", "item": "",
                           "text": "Pertahankan baseline: laporan otomatis tetap berjalan; bandingkan dengan laporan saat ada keluhan."})

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
        f'{"<br><b style=color:#c62828>◀ TITIK MACET</b>" if sec["key"] == c["bottleneck"] else ""}</td>'
        f'{"<td style=color:#94a3b8>→</td>" if i < len(PATH) - 1 else ""}'
        for i, sec in enumerate(s for s in c["sections"] if s["key"] in PATH))
    sections_html = ""
    for sec in c["sections"]:
        rows = "".join(
            f'<tr><td>{e(i["name"])}</td><td>{e(_fmt(i["value"], i["unit"]))}</td><td>{e(i["standard"])}</td>'
            f'<td>{_badge(i["status"])}</td><td>{e(i["note"] or "")}</td></tr>' for i in sec["items"])
        sections_html += (
            f'<h3 style="margin:22px 0 6px">{e(sec["label"])} {_badge(sec["status"])}</h3>'
            + (f'<table><tr><th>Item</th><th>Nilai</th><th>Standar</th><th>Status</th><th>Catatan</th></tr>{rows}</table>'
               if rows else '<p style="color:#64748b">Tidak ada data untuk segmen ini.</p>'))
    actions = "".join(
        f'<tr><td><b>{e(a["priority"])}</b></td><td>{e(a["section"])}</td><td>{e(a["text"])}'
        f'{"<br><span style=color:#64748b>" + e(a["item"]) + "</span>" if a["item"] else ""}</td></tr>' for a in c["actions"])
    concl = "".join(f"<li>{e(x)}</li>" for x in c["conclusion"])
    ctx = c["context"]
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laporan Diagnosis EBS HO-Plant {created:%Y-%m-%d %H:%M}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;color:#0f172a;max-width:1100px;margin:24px auto;padding:0 16px;font-size:13px;background:#fff}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f8fafc;color:#475569;font-size:12px}} h1{{font-size:20px;margin-bottom:2px}} h2{{font-size:16px;margin-top:26px}}
.box{{border-radius:10px;padding:12px 14px;margin:12px 0}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>Laporan Diagnosis Akses Oracle EBS — HO ↔ Plant</h1>
<div style="color:#64748b">{created:%d %B %Y %H:%M} WIB · {"otomatis" if c["trigger"] == "auto" else "manual oleh " + e(c.get("created_by") or "-")}
 · lingkungan EBS: {e(str(ctx.get("ebs_environment") or "-"))} · {ctx["client_reports"]} tes laptop ({ctx["client_window_hours"]} jam terakhir)
 · insiden 7 hari: {ctx["incidents_7d"]} · durasi proses {c.get("duration_s")} s</div>
<div class="box" style="background:{_BG[c["overall"]]};border:1px solid {_COLORS[c["overall"]]}55">
<div style="font-size:15px"><b>Status keseluruhan:</b> {_badge(c["overall"])}
{" &nbsp; <b>Titik macet:</b> " + e(c["bottleneck_label"]) if c["bottleneck"] else ""}</div>
<p style="margin:8px 0 0;font-size:14px"><b>{e(c["headline"])}</b></p></div>
<h2>Jalur akses</h2>
<table style="border:none"><tr style="border:none">{chain}</tr></table>
<p>Internet / ISP Plant: {_badge(next(s for s in c["sections"] if s["key"] == "internet")["status"])}</p>
<h2>Kesimpulan</h2><ul>{concl}</ul>
<h2>Tindakan</h2>
<table><tr><th style="width:80px">Prioritas</th><th style="width:170px">Segmen</th><th>Tindakan</th></tr>{actions}</table>
<h2>Data &amp; penilaian per segmen</h2>
{sections_html}
<p style="margin-top:28px;color:#94a3b8;font-size:11px">Standar = baseline operasional internal (bukan requirement resmi Oracle).
Kesimpulan adalah arah investigasi berdasarkan data saat laporan dibuat — konfirmasi dengan pengukuran berulang sebelum mengubah konfigurasi VPN, routing, MTU, firewall atau Oracle.
Dibuat oleh CKDO Dashboard · Oracle EBS Network Monitoring.</p>
</body></html>"""
