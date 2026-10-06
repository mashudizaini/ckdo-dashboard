"""
Turns measurements into the verdicts of sections 10 and 17 of the diagnostic
script — Case A (HO LAN), B (HO->Plant WAN/VPN), C (network fine, EBS slow),
D (one laptop only) — and the root-cause codes NET-/CLI-/EBS-/DB-.

These are pointers for where to look, never a conclusion: the script is
explicit that one measurement proves nothing, and the UI says so too.
"""
import statistics

# Order = position on the path from the HO laptop to the EBS database.
SEGMENTS = {
    "ho_lan":    "LAN HO",
    "wan":       "Jalur HO ↔ Plant (tunnel)",
    "plant_lan": "LAN Plant",
    "ebs_web":   "EBS Web / App Tier",
    "ebs_db":    "EBS Database",
    "internet":  "Internet / ISP",
}

ROOT_CAUSE_CODES = {
    "NET-01": "High Latency", "NET-02": "Packet Loss", "NET-03": "High Jitter",
    "NET-04": "VPN Instability", "NET-05": "Bandwidth Saturation", "NET-06": "MTU/MSS Problem",
    "NET-07": "Routing Problem", "NET-08": "ISP Problem",
    "CLI-01": "High CPU", "CLI-02": "High RAM", "CLI-03": "Disk Bottleneck",
    "CLI-04": "Browser Problem", "CLI-05": "Windows Problem", "CLI-06": "LAN/Wi-Fi Problem",
    "EBS-01": "Forms", "EBS-02": "Web Tier", "EBS-03": "Application Tier", "EBS-04": "Concurrent Manager",
    "DB-01": "CPU", "DB-02": "Memory", "DB-03": "I/O", "DB-04": "SQL", "DB-05": "Lock",
    "DB-06": "Wait Event", "DB-07": "Session",
}

LEVELS = ["ok", "warn", "crit"]


def _worst(*levels: str) -> str:
    present = [l for l in levels if l in LEVELS]
    return max(present, key=LEVELS.index) if present else "unknown"


def probe_level(p: dict | None, t: dict) -> str:
    if not p or p.get("skipped"):
        return "unknown"
    loss = p.get("loss_pct")
    if loss is None or loss >= 100:
        return "crit"
    lvl = "ok"
    if loss >= t["loss_crit"]:
        lvl = "crit"
    elif loss >= t["loss_warn"]:
        lvl = "warn"
    avg, jit = p.get("rtt_avg") or 0, p.get("jitter_ms") or 0
    if avg >= t["latency_crit"] or jit >= t["jitter_crit"]:
        lvl = _worst(lvl, "crit")
    elif avg >= t["latency_warn"] or jit >= t["jitter_warn"]:
        lvl = _worst(lvl, "warn")
    if p.get("http_status") and p["http_status"] >= 500:
        lvl = "crit"
    return lvl


def fortigate_findings(name: str, s: dict | None, t: dict) -> tuple[str, list[str]]:
    if not s:
        return "unknown", []
    lvl, notes = "ok", []
    if (s.get("cpu_pct") or 0) >= t["fgt_cpu_warn"]:
        lvl = "warn"; notes.append(f"{name}: CPU firewall {s['cpu_pct']}%")
    if (s.get("mem_pct") or 0) >= t["fgt_mem_warn"]:
        lvl = "warn"; notes.append(f"{name}: memori firewall {s['mem_pct']}% (conserve mode dimulai ~88%)")
    for tun in s.get("tunnels", []):
        if not tun["up"]:
            lvl = "crit"; notes.append(f"{name}: tunnel {tun['name']} DOWN (NET-04)")
        elif tun["rx_err"] or tun["tx_err"]:
            lvl = _worst(lvl, "warn"); notes.append(f"{name}: tunnel {tun['name']} ada error rx/tx")
    for m in s.get("sdwan", []):
        if m["state"] != "alive":
            lvl = _worst(lvl, "warn"); notes.append(f"{name}: SD-WAN member {m['member']} {m['state']}")
        else:
            pl = probe_level({"loss_pct": m.get("loss_pct") or 0, "rtt_avg": m.get("latency_ms"),
                              "jitter_ms": m.get("jitter_ms")}, t)
            if pl != "ok":
                lvl = _worst(lvl, pl)
                notes.append(f"{name}: SLA {m['check']} via {m['member']} — loss {m.get('loss_pct')}%, "
                             f"latency {m.get('latency_ms')} ms, jitter {m.get('jitter_ms')} ms")
    for d in s.get("tunnel_detail", []):
        if d.get("mtu") and d["mtu"] < 1350:
            notes.append(f"{name}: MTU tunnel {d['name']} = {d['mtu']} — pastikan MSS clamping (NET-06)")
    return lvl, notes


def ebs_findings(s: dict | None) -> tuple[str, str, list[str]]:
    """Returns (app_level, db_level, notes)."""
    if not s:
        return "unknown", "unknown", []
    app, db, notes = "ok", "ok", []
    if s.get("icm_up") is False:
        app = "crit"; notes.append("Internal Concurrent Manager (FNDICM) mati (EBS-04)")
    down = [m["name"] for m in s.get("managers_down", [])]
    if down:
        app = _worst(app, "warn"); notes.append(f"Manager di bawah target: {', '.join(down[:4])} (EBS-04)")
    if (s.get("requests_pending") or 0) > 50:
        app = _worst(app, "warn"); notes.append(f"{s['requests_pending']} concurrent request pending")
    for srv in s.get("app_tier", []):
        if srv.get("status") == "error":
            app = _worst(app, "warn"); notes.append(f"SSH ke {srv.get('server_label')} gagal")
        elif (srv.get("cpu") or 0) >= 85:
            app = _worst(app, "warn"); notes.append(f"CPU {srv.get('server_label')} {srv['cpu']}% (EBS-03)")
        elif (srv.get("memory_percent") or 0) >= 92 or (srv.get("swap_percent") or 0) >= 30:
            app = _worst(app, "warn"); notes.append(f"Memori/swap {srv.get('server_label')} tinggi (EBS-03)")
    if (s.get("sessions_blocked") or 0) > 0:
        db = "warn" if s["sessions_blocked"] < 5 else "crit"
        notes.append(f"{s['sessions_blocked']} sesi terblokir lock (DB-05)")
    if (s.get("host_cpu_pct") or 0) >= 85:
        db = _worst(db, "warn"); notes.append(f"CPU host DB {s['host_cpu_pct']}% (DB-01)")
    if (s.get("single_block_read_ms") or 0) >= 20:
        db = _worst(db, "warn"); notes.append(f"Latency baca single-block {s['single_block_read_ms']} ms (DB-03)")
    if s.get("long_sql"):
        db = _worst(db, "warn"); notes.append(f"{len(s['long_sql'])} SQL aktif > 5 menit (DB-04)")
    return app, db, notes


def classify_client(r: dict, t: dict, fleet_median_rtt: float | None = None) -> tuple[str, list[str]]:
    """Verdict for one laptop report. `r` uses EbsNetClientReport column names."""
    codes = []
    gw_bad = (r.get("gw_loss_pct") or 0) > 0 or (r.get("gw_rtt_avg") or 0) > t["lan_rtt_warn"]
    ebs_loss = r.get("ebs_loss_pct") or 0
    ebs_avg = r.get("ebs_rtt_avg") or 0
    ebs_jit = r.get("ebs_jitter_ms") or 0
    ebs_bad = ebs_loss >= t["loss_warn"] or ebs_avg >= t["latency_warn"] or ebs_jit >= t["jitter_warn"]

    if (r.get("cpu_pct") or 0) >= t["cpu_warn"]:
        codes.append("CLI-01")
    if r.get("ram_avail_pct") is not None and r["ram_avail_pct"] < t["ram_avail_warn"]:
        codes.append("CLI-02")
    if (r.get("disk_pct") or 0) >= t["disk_warn"]:
        codes.append("CLI-03")
    wifi_weak = r.get("wifi_signal") is not None and r["wifi_signal"] < 60
    if gw_bad or wifi_weak:
        codes.append("CLI-06")
    if ebs_bad and not gw_bad:
        if ebs_avg >= t["latency_warn"]:
            codes.append("NET-01")
        if ebs_loss >= t["loss_warn"]:
            codes.append("NET-02")
        if ebs_jit >= t["jitter_warn"]:
            codes.append("NET-03")
    if r.get("path_mtu") and r["path_mtu"] < 1350:
        codes.append("NET-06")

    if gw_bad:
        verdict = "A"
    elif ebs_bad:
        verdict = "B"
    elif any(c.startswith("CLI-0") for c in codes) or (
            fleet_median_rtt and ebs_avg and ebs_avg > max(2 * fleet_median_rtt, fleet_median_rtt + 15)):
        verdict = "D"
    elif r.get("ebs_condition") in ("Slow", "Hang", "Restart") or (r.get("http_ttfb_ms") or 0) >= t["ttfb_warn"]:
        verdict = "C"
    else:
        verdict = "OK"
    return verdict, codes


VERDICT_TEXT = {
    "A": "Case A — LAN HO bermasalah (laptop → gateway sudah buruk). Periksa Wi-Fi, kabel, AP, switch, NIC.",
    "B": "Case B — LAN normal, jalur HO → Plant bermasalah. Fokus WAN/VPN, ISP, routing, MTU/MSS, congestion.",
    "C": "Case C — jaringan normal tetapi EBS lambat. Fokus Forms/web tier, Concurrent Manager, database.",
    "D": "Case D — kemungkinan hanya laptop ini. Periksa CPU/RAM/disk, browser, Java, Wi-Fi laptop.",
    "OK": "Tidak ada indikasi masalah pada pengukuran ini.",
}


def fleet_median(rtts: list[float]) -> float | None:
    vals = [v for v in rtts if v]
    return statistics.median(vals) if len(vals) >= 3 else None


def overview(latest_probes: list[dict], fortigates: list[dict], ebs: dict | None,
             clients: list[dict], t: dict) -> dict:
    """Segment cards + one-line diagnosis for the Overview tab.
    latest_probes: [{target fields..., "last": probe dict}], fortigates:
    [{name, ok, summary, error}], ebs: snapshot summary, clients: recent
    report dicts."""
    seg = {k: {"key": k, "label": v, "level": "unknown", "notes": [], "targets": []} for k, v in SEGMENTS.items()}

    for p in latest_probes:
        s = seg.get(p["segment"])
        if not s:
            continue
        lvl = probe_level(p.get("last"), t)
        s["targets"].append({"name": p["name"], "level": lvl, "last": p.get("last")})
        s["level"] = _worst(s["level"], lvl) if s["level"] != "unknown" else lvl
        last = p.get("last") or {}
        if lvl != "ok" and last:
            if last.get("error"):
                s["notes"].append(f"{p['name']}: {last['error']}")
            else:
                s["notes"].append(f"{p['name']}: avg {last.get('rtt_avg')} ms, loss {last.get('loss_pct')}%, "
                                  f"jitter {last.get('jitter_ms')} ms")

    for fg in fortigates:
        if not fg.get("ok"):
            seg["wan"]["notes"].append(f"{fg['name']}: {fg.get('error') or 'snapshot gagal'}")
            continue
        lvl, notes = fortigate_findings(fg["name"], fg.get("summary"), t)
        seg["wan"]["level"] = lvl if seg["wan"]["level"] == "unknown" else _worst(seg["wan"]["level"], lvl)
        seg["wan"]["notes"].extend(notes)

    app_lvl, db_lvl, ebs_notes = ebs_findings(ebs)
    for key, lvl in (("ebs_web", app_lvl), ("ebs_db", db_lvl)):
        if lvl != "unknown":
            seg[key]["level"] = lvl if seg[key]["level"] == "unknown" else _worst(seg[key]["level"], lvl)
    for n in ebs_notes:
        seg["ebs_db" if "(DB-" in n else "ebs_web"]["notes"].append(n)

    # HO LAN can only be seen from a laptop at HO.
    ho_clients = [c for c in clients if c.get("gw_rtt_avg") is not None]
    if ho_clients:
        bad = [c for c in ho_clients if c.get("verdict") == "A"]
        seg["ho_lan"]["level"] = "warn" if bad else "ok"
        seg["ho_lan"]["notes"].append(
            f"{len(ho_clients)} laporan agen 24 jam terakhir, {len(bad)} menunjukkan LAN/Wi-Fi bermasalah")
    else:
        seg["ho_lan"]["notes"].append("Belum ada laporan agen dari laptop HO dalam 24 jam — jalankan Client Test.")

    levels = {k: v["level"] for k, v in seg.items()}
    if levels["ho_lan"] in ("warn", "crit"):
        diagnosis = "A"
    elif levels["wan"] in ("warn", "crit"):
        diagnosis = "B"
    elif _worst(levels["ebs_web"], levels["ebs_db"]) in ("warn", "crit"):
        diagnosis = "C"
    elif all(l in ("ok", "unknown") for l in levels.values()):
        diagnosis = "OK"
    else:
        diagnosis = "B" if levels["internet"] in ("warn", "crit") else "OK"
    return {
        "segments": list(seg.values()),
        "diagnosis": diagnosis,
        "diagnosis_text": VERDICT_TEXT[diagnosis],
    }
