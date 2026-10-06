"""
Oracle EBS Network Monitoring — settings (key/value JSON in ebsnet_settings)
and the one-time seed of default probe targets.
"""
import copy
import json
from datetime import datetime

from app.config import get_settings
from app.models.ebs_netmon import EbsNetSessionLocal, EbsNetSetting, EbsNetTarget

_cfg = get_settings()

# Baselines from section 11 of the HO -> Plant diagnostic script: "baseline
# operasional, bukan Oracle official requirement". lan_rtt_warn is mine — a
# wired HO LAN hop to the gateway should be ~1 ms; Wi-Fi a few ms.
DEFAULT_THRESHOLDS = {
    "latency_warn": 50, "latency_crit": 100,
    "jitter_warn": 10, "jitter_crit": 30,
    "loss_warn": 0.1, "loss_crit": 2,
    "lan_rtt_warn": 5,
    "ttfb_warn": 1500,
    "cpu_warn": 80, "ram_avail_warn": 20, "disk_warn": 95,
    "fgt_cpu_warn": 70, "fgt_mem_warn": 80,
}

DEFAULT_SETTINGS = {
    # What the PowerShell agent pings / connects to from the laptop.
    "ebs_host": _cfg.oracle_prod_host,
    "ebs_ports": [_cfg.oracle_prod_port],
    # EBS login page, e.g. http://ebs.example.local:8000/OA_HTML/AppsLocalLogin.jsp
    "ebs_web_url": "",
    # Optional: a small static file on the EBS web tier the browser can load
    # (only useful when EBS is served over https — browsers block http
    # sub-resources on an https dashboard).
    "browser_probe_url": "",
    # Server Control ids of the two FortiGates (SSH, read-only commands).
    "fortigate_ho_server_id": None,
    "fortigate_plant_server_id": None,
    "tunnel_names": ["JKT-CKR", "CKR-JKT"],
    "poll_fortigate": True,
    "poll_ebs": True,
    "probe_samples": 5,
    "thresholds": DEFAULT_THRESHOLDS,
    # Automatic diagnosis report (Laporan tab): every N hours, 0 = off.
    "report_interval_hours": 3,
    # Laptop reports older than this are not used in a diagnosis report.
    "report_client_window_hours": 24,
    "playbook_checklist": {},
}


def get_all(db) -> dict:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    for row in db.query(EbsNetSetting).all():
        try:
            out[row.key] = json.loads(row.value) if row.value is not None else None
        except ValueError:
            continue
    # New threshold keys added later still get their default.
    out["thresholds"] = {**DEFAULT_THRESHOLDS, **(out.get("thresholds") or {})}
    return out


def set_many(db, values: dict, user: str | None) -> dict:
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        row = db.get(EbsNetSetting, key)
        if not row:
            row = EbsNetSetting(key=key)
            db.add(row)
        row.value = json.dumps(value)
        row.updated_by = user
        row.updated_at = datetime.utcnow()
    db.commit()
    return get_all(db)


def seed_defaults():
    """Seed the starter targets exactly once (marker setting `seeded`), so a
    target the admin deletes does not come back on the next restart. Only
    the DB listener is enabled: it is the one address+port this codebase
    already knows is right. The rest need an IP/port only IT can confirm."""
    db = EbsNetSessionLocal()
    try:
        if db.get(EbsNetSetting, "seeded"):
            return
        starters = [
            dict(name="EBS Database Listener (PROD)", segment="ebs_db", check_type="tcp",
                 host=_cfg.oracle_prod_host, port=_cfg.oracle_prod_port, enabled=True, sequence=10,
                 notes="Diambil dari konfigurasi koneksi Oracle dashboard."),
            dict(name="EBS Web / Application Tier", segment="ebs_web", check_type="tcp",
                 host="172.21.2.202", port=8000, enabled=False, sequence=20,
                 notes="Verifikasi host & port web EBS (R12.2 umumnya 8000 / 4443), lalu aktifkan."),
            dict(name="EBS Login Page (TTFB)", segment="ebs_web", check_type="http",
                 url="", enabled=False, sequence=21,
                 notes="Isi URL AppsLocalLogin.jsp — mengukur waktu respons web tier, bukan sekadar port terbuka."),
            dict(name="FortiGate HO (LAN interface)", segment="wan", check_type="tcp",
                 host="", port=443, enabled=False, sequence=30,
                 notes="Isi IP LAN FortiGate HO. Dari server Plant, probe ini melewati tunnel HO-Plant."),
            dict(name="Internet (Cloudflare 1.1.1.1)", segment="internet", check_type="tcp",
                 host="1.1.1.1", port=443, enabled=True, sequence=90,
                 notes="Pembanding: kalau internet ikut buruk, masalahnya di ISP Plant, bukan tunnel."),
        ]
        for s in starters:
            db.add(EbsNetTarget(**s))
        db.add(EbsNetSetting(key="seeded", value=json.dumps(True), updated_by="system"))
        db.commit()
    finally:
        db.close()
