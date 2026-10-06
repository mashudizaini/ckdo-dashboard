"""
Oracle EBS Network Monitoring — orchestration over the models: run and store
probes, take FortiGate / EBS snapshots, ingest laptop reports, build the
overview. Sync (Session from get_ebsnet_db / EbsNetSessionLocal).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import func

from app.models.ebs_netmon import (
    EbsNetClientReport, EbsNetProbeLog, EbsNetSnapshot, EbsNetTarget,
)
from app.services.ebs_netmon import analysis, ebs_health, fortigate, probes, sdwan_config
from app.services.ebs_netmon import settings as cfg

RAW_KEEP_DAYS = 2
LOG_RETENTION_DAYS = 30


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _loads(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return None


# ── Targets & probes ──────────────────────────────────────────────────────

def target_dict(t: EbsNetTarget) -> dict:
    return {"id": t.id, "name": t.name, "segment": t.segment, "check_type": t.check_type,
            "host": t.host, "port": t.port, "url": t.url, "enabled": t.enabled,
            "sequence": t.sequence, "notes": t.notes}


def log_dict(l: EbsNetProbeLog | None) -> dict | None:
    if not l:
        return None
    return {"checked_at": _iso(l.checked_at), "samples": l.samples, "ok_count": l.ok_count,
            "loss_pct": l.loss_pct, "rtt_min": l.rtt_min, "rtt_avg": l.rtt_avg, "rtt_max": l.rtt_max,
            "jitter_ms": l.jitter_ms, "http_status": l.http_status, "error": l.error}


def run_probes(db, target_ids: list[int] | None = None) -> list[dict]:
    """Probe every enabled target in parallel (a dead host costs its own
    timeout, not everyone's) and append one log row each."""
    s = cfg.get_all(db)
    q = db.query(EbsNetTarget).filter(EbsNetTarget.enabled.is_(True))
    if target_ids:
        q = q.filter(EbsNetTarget.id.in_(target_ids))
    targets = q.order_by(EbsNetTarget.sequence, EbsNetTarget.id).all()
    samples = int(s.get("probe_samples") or 5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda t: probes.run_target(t, samples), targets))
    out = []
    now = datetime.utcnow()
    for t, r in zip(targets, results):
        if not r.get("skipped"):
            db.add(EbsNetProbeLog(
                target_id=t.id, checked_at=now, samples=r["samples"], ok_count=r["ok_count"],
                loss_pct=r["loss_pct"], rtt_min=r["rtt_min"], rtt_avg=r["rtt_avg"], rtt_max=r["rtt_max"],
                jitter_ms=r["jitter_ms"], http_status=r.get("http_status"), error=r.get("error"),
            ))
        out.append({**target_dict(t), "last": {**r, "checked_at": _iso(now)}})
    db.commit()
    return out


def latest_probes(db) -> list[dict]:
    targets = db.query(EbsNetTarget).order_by(EbsNetTarget.sequence, EbsNetTarget.id).all()
    last_ids = dict(db.query(EbsNetProbeLog.target_id, func.max(EbsNetProbeLog.id))
                    .group_by(EbsNetProbeLog.target_id).all())
    logs = {l.target_id: l for l in db.query(EbsNetProbeLog).filter(EbsNetProbeLog.id.in_(list(last_ids.values()) or [0]))}
    t24 = datetime.utcnow() - timedelta(hours=24)
    stats = {r[0]: r for r in db.query(
        EbsNetProbeLog.target_id, func.avg(EbsNetProbeLog.rtt_avg), func.max(EbsNetProbeLog.rtt_max),
        func.avg(EbsNetProbeLog.loss_pct), func.count(EbsNetProbeLog.id),
    ).filter(EbsNetProbeLog.checked_at >= t24).group_by(EbsNetProbeLog.target_id).all()}
    out = []
    for t in targets:
        st = stats.get(t.id)
        out.append({**target_dict(t), "last": log_dict(logs.get(t.id)), "day": {
            "rtt_avg": round(st[1], 1) if st and st[1] is not None else None,
            "rtt_max": round(st[2], 1) if st and st[2] is not None else None,
            "loss_avg": round(st[3], 2) if st and st[3] is not None else None,
            "runs": st[4] if st else 0,
        }})
    return out


def probe_history(db, target_id: int, hours: int = 24) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (db.query(EbsNetProbeLog)
            .filter(EbsNetProbeLog.target_id == target_id, EbsNetProbeLog.checked_at >= since)
            .order_by(EbsNetProbeLog.checked_at).all())
    return [log_dict(r) for r in rows]


# ── Snapshots ─────────────────────────────────────────────────────────────

def snapshot_dict(r: EbsNetSnapshot | None, with_raw: bool = False) -> dict | None:
    if not r:
        return None
    d = {"id": r.id, "kind": r.kind, "name": r.source, "checked_at": _iso(r.checked_at), "ok": r.ok,
         "summary": _loads(r.summary), "error": r.error}
    if with_raw:
        d["raw"] = _loads(r.raw)
    return d


def _save_snapshot(db, kind: str, source: str, res: dict) -> EbsNetSnapshot:
    row = EbsNetSnapshot(kind=kind, source=source, ok=bool(res.get("ok")),
                         summary=json.dumps(res.get("summary"), default=str),
                         raw=json.dumps(res.get("raw"), default=str) if res.get("raw") else None,
                         error=res.get("error"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def fortigate_ids(s: dict) -> list[tuple[str, int]]:
    out = []
    for role, key in (("HO", "fortigate_ho_server_id"), ("Plant", "fortigate_plant_server_id")):
        if s.get(key):
            out.append((role, int(s[key])))
    return out


def capture_fortigates(db) -> list[dict]:
    s = cfg.get_all(db)
    ids = fortigate_ids(s)
    if not ids:
        return []
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: fortigate.snapshot(x[1], s.get("ebs_host")), ids))
    out = []
    for (role, _), res in zip(ids, results):
        source = f"{role}: {res['name']}"
        out.append(snapshot_dict(_save_snapshot(db, "fortigate", source, res), with_raw=True))
    return out


def ebs_ips(db) -> list[str]:
    """EBS addresses the SD-WAN checks look for — web/app tier first (users
    open :8000 there), then the DB host from Setup."""
    out = []
    web = (db.query(EbsNetTarget.host).filter(EbsNetTarget.segment.in_(("ebs_web", "ebs_db")))
           .order_by(EbsNetTarget.segment.desc(), EbsNetTarget.sequence).all())
    for (h,) in web + [(cfg.get_all(db).get("ebs_host"),)]:
        if h and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", h) and h not in out:
            out.append(h)
    return out


def capture_sdwan_config(db) -> dict:
    ids = fortigate_ids(cfg.get_all(db))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: sdwan_config.capture(x[1]), ids))
    for (role, _), res in zip(ids, results):
        _save_snapshot(db, "sdwan_cfg", f"{role}: {res['name']}", res)
    return sdwan_config_view(db)


def sdwan_config_view(db) -> dict:
    """Newest config read per side, plus the HO↔Plant analysis over them."""
    snaps = sorted(latest_snapshots(db, "sdwan_cfg", with_raw=True), key=lambda s: s["checked_at"], reverse=True)
    side = {role: next((s for s in snaps if s["name"].startswith(f"{role}:")), None) for role in ("HO", "Plant")}
    ok = {role: (s["summary"] if s and s["ok"] else None) for role, s in side.items()}
    return {"devices": side, "analysis": sdwan_config.analyze(ok["HO"], ok["Plant"], ebs_ips(db)),
            "configured": len(fortigate_ids(cfg.get_all(db)))}


def capture_ebs(db, include_app_tier: bool = True) -> dict:
    res = ebs_health.snapshot(include_app_tier=include_app_tier)
    return snapshot_dict(_save_snapshot(db, "ebs", "EBS", res))


def latest_snapshots(db, kind: str, with_raw: bool = False) -> list[dict]:
    """Newest row per source of `kind`."""
    ids = [r[0] for r in db.query(func.max(EbsNetSnapshot.id))
           .filter(EbsNetSnapshot.kind == kind).group_by(EbsNetSnapshot.source).all()]
    rows = db.query(EbsNetSnapshot).filter(EbsNetSnapshot.id.in_(ids or [0])).order_by(EbsNetSnapshot.source).all()
    return [snapshot_dict(r, with_raw) for r in rows]


def snapshot_series(db, kind: str, hours: int = 24) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (db.query(EbsNetSnapshot).filter(EbsNetSnapshot.kind == kind, EbsNetSnapshot.checked_at >= since)
            .order_by(EbsNetSnapshot.checked_at).all())
    return [snapshot_dict(r) for r in rows]


def nearest_snapshots(db, at: datetime, minutes: int = 15) -> dict:
    """Snapshots/probes closest to an incident time — the correlation step."""
    lo, hi = at - timedelta(minutes=minutes), at + timedelta(minutes=minutes)
    # Config reads (sdwan_cfg) are not measurements — leave them out.
    snaps = (db.query(EbsNetSnapshot).filter(EbsNetSnapshot.checked_at.between(lo, hi),
                                             EbsNetSnapshot.kind != "sdwan_cfg")
             .order_by(EbsNetSnapshot.checked_at).all())
    logs = (db.query(EbsNetProbeLog, EbsNetTarget.name, EbsNetTarget.segment)
            .join(EbsNetTarget, EbsNetTarget.id == EbsNetProbeLog.target_id)
            .filter(EbsNetProbeLog.checked_at.between(lo, hi)).order_by(EbsNetProbeLog.checked_at).all())
    return {
        "window_minutes": minutes,
        "snapshots": [snapshot_dict(s) for s in snaps],
        "probes": [{**log_dict(l), "name": n, "segment": seg} for l, n, seg in logs],
    }


# ── Client reports ────────────────────────────────────────────────────────

def _f(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def columns_from_agent(p: dict) -> dict:
    gw = p.get("ping_gateway") or {}
    eb = p.get("ping_ebs") or {}
    http = p.get("http_ebs") or {}
    res = p.get("resources") or {}
    wifi = ((p.get("network") or {}).get("wifi")) or {}
    cond = p.get("condition") or None
    return {
        "source": "agent", "hostname": (p.get("hostname") or "")[:150], "reported_by": (p.get("user") or "")[:150],
        "connection": p.get("connection"), "ebs_condition": cond, "note": p.get("note"),
        "gw_rtt_avg": _f(gw.get("avg")), "gw_loss_pct": _f(gw.get("loss_pct")),
        "ebs_rtt_avg": _f(eb.get("avg")), "ebs_rtt_max": _f(eb.get("max")),
        "ebs_loss_pct": _f(eb.get("loss_pct")), "ebs_jitter_ms": _f(eb.get("jitter")),
        "http_ttfb_ms": _f(http.get("avg")), "path_mtu": int(p["path_mtu"]) if p.get("path_mtu") else None,
        "cpu_pct": _f(res.get("cpu_pct")), "ram_avail_pct": _f(res.get("ram_avail_pct")),
        "disk_pct": _f(res.get("disk_pct")),
        "wifi_signal": int(wifi["signal_pct"]) if wifi.get("signal_pct") is not None else None,
    }


def columns_from_browser(p: dict, user: str) -> dict:
    lat = p.get("latency") or {}
    return {
        "source": "browser", "reported_by": user, "hostname": (p.get("hostname") or "")[:150] or None,
        "connection": p.get("connection") or None, "ebs_condition": p.get("condition") or None,
        "note": p.get("note"),
        "ebs_rtt_avg": _f(lat.get("rtt_avg")), "ebs_rtt_max": _f(lat.get("rtt_max")),
        "ebs_loss_pct": _f(lat.get("loss_pct")), "ebs_jitter_ms": _f(lat.get("jitter_ms")),
        "http_ttfb_ms": _f((p.get("ebs_probe") or {}).get("rtt_avg")),
        "down_mbps": _f(p.get("down_mbps")), "up_mbps": _f(p.get("up_mbps")),
    }


def _fleet_median(db, exclude_host: str | None, source: str) -> float | None:
    since = datetime.utcnow() - timedelta(hours=24)
    q = db.query(EbsNetClientReport.ebs_rtt_avg).filter(
        EbsNetClientReport.created_at >= since, EbsNetClientReport.source == source)
    if exclude_host:
        q = q.filter(EbsNetClientReport.hostname != exclude_host)
    return analysis.fleet_median([r[0] for r in q.all()])


def save_client_report(db, cols: dict, detail: dict) -> dict:
    t = cfg.get_all(db)["thresholds"]
    verdict, codes = analysis.classify_client(cols, t, _fleet_median(db, cols.get("hostname"), cols["source"]))
    row = EbsNetClientReport(**cols, verdict=verdict, codes=",".join(codes),
                             detail=json.dumps(detail, default=str))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**report_dict(row), "verdict_text": analysis.VERDICT_TEXT[verdict]}


def report_dict(r: EbsNetClientReport, with_detail: bool = False) -> dict:
    d = {c.name: getattr(r, c.name) for c in EbsNetClientReport.__table__.columns if c.name != "detail"}
    d["created_at"] = _iso(r.created_at)
    d["codes"] = [c for c in (r.codes or "").split(",") if c]
    if with_detail:
        d["detail"] = _loads(r.detail)
    return d


def list_reports(db, hours: int = 168, limit: int = 200) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (db.query(EbsNetClientReport).filter(EbsNetClientReport.created_at >= since)
            .order_by(EbsNetClientReport.created_at.desc()).limit(limit).all())
    return [report_dict(r) for r in rows]


# ── Overview & full capture ───────────────────────────────────────────────

def overview(db) -> dict:
    s = cfg.get_all(db)
    t = s["thresholds"]
    probes_ = latest_probes(db)
    fgs = latest_snapshots(db, "fortigate")
    ebs = (latest_snapshots(db, "ebs") or [None])[0]
    clients = list_reports(db, hours=24)
    ov = analysis.overview([p for p in probes_ if p["enabled"]], fgs,
                           (ebs or {}).get("summary") if ebs and ebs.get("ok") else None, clients, t)
    return {
        **ov,
        "generated_at": _iso(datetime.utcnow()),
        "probes": probes_,
        "fortigates": fgs,
        "ebs": ebs,
        "clients_24h": {
            "count": len(clients),
            "by_verdict": {v: sum(1 for c in clients if c["verdict"] == v) for v in ("A", "B", "C", "D", "OK")},
            "latest": clients[:8],
        },
        "configured": {
            "fortigates": len(fortigate_ids(s)),
            "targets_enabled": sum(1 for p in probes_ if p["enabled"]),
            "ebs_web_url": bool(s.get("ebs_web_url")),
        },
    }


def capture_all(db) -> dict:
    """Everything, now — used when an incident is logged."""
    return {
        "captured_at": _iso(datetime.utcnow()),
        "probes": run_probes(db),
        "fortigates": [{k: v for k, v in f.items() if k != "raw"} for f in capture_fortigates(db)],
        "ebs": capture_ebs(db),
    }


def prune(db):
    now = datetime.utcnow()
    db.query(EbsNetProbeLog).filter(EbsNetProbeLog.checked_at < now - timedelta(days=LOG_RETENTION_DAYS)).delete()
    db.query(EbsNetSnapshot).filter(EbsNetSnapshot.checked_at < now - timedelta(days=LOG_RETENTION_DAYS)).delete()
    # Raw CLI text is only useful while debugging a parser — keep it 2 days.
    db.query(EbsNetSnapshot).filter(EbsNetSnapshot.checked_at < now - timedelta(days=RAW_KEEP_DAYS),
                                    EbsNetSnapshot.raw.isnot(None)).update({EbsNetSnapshot.raw: None},
                                                                           synchronize_session=False)
    db.commit()
