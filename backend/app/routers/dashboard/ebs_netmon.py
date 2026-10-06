"""
Oracle EBS Network Monitoring — IT-only API (gated at the router level in
main.py with require_role(Roles.IT), same as vpn_monitor).

  Overview     GET  /overview
  Targets      GET/POST /targets, DELETE /targets/{id}, GET /targets/{id}/history
  Probes       POST /probes/run
  FortiGate    GET  /fortigate, POST /fortigate/capture, GET /fortigate/history
  SD-WAN cfg   GET  /sdwan-config, POST /sdwan-config/capture
  EBS health   GET  /ebs, POST /ebs/capture, GET /ebs/history
  Laptops      GET  /reports, GET/DELETE /reports/{id}, POST /reports/upload
  Agent        POST /agent/script
  Incidents    GET/POST /incidents, GET/PUT/DELETE /incidents/{id}
  Diagnosis    GET /summary-reports, POST /summary-reports/run,
               GET/DELETE /summary-reports/{id}, GET /summary-reports/{id}/download
  Setup        GET/PUT /settings, GET /servers, GET /meta

The laptop-facing endpoints (browser test, agent ingest) live in
ebs_netmon_client.py — they must work for any logged-in employee, or with
no login at all for the agent.
"""
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, get_current_user
from app.models.ebs_netmon import (
    EbsNetAgentToken, EbsNetClientReport, EbsNetIncident, EbsNetSummaryReport, EbsNetTarget, get_ebsnet_db,
)
from app.services import it_monitoring_store as store
from app.services.ebs_netmon import agent_script, analysis, report, service
from app.services.ebs_netmon import settings as cfg

router = APIRouter()


def _who(user: CurrentUser) -> str:
    return user.email or user.username


# ── Overview / meta ───────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(db: Session = Depends(get_ebsnet_db)):
    return service.overview(db)


@router.get("/meta")
def get_meta():
    return {"segments": analysis.SEGMENTS, "root_cause_codes": analysis.ROOT_CAUSE_CODES,
            "verdicts": analysis.VERDICT_TEXT}


# ── Targets ───────────────────────────────────────────────────────────────

class TargetIn(BaseModel):
    id: Optional[int] = None
    name: str
    segment: str = "plant_lan"
    check_type: str = "tcp"
    host: Optional[str] = None
    port: Optional[int] = None
    url: Optional[str] = None
    enabled: bool = True
    sequence: int = 0
    notes: Optional[str] = None


@router.get("/targets")
def list_targets(db: Session = Depends(get_ebsnet_db)):
    return service.latest_probes(db)


@router.post("/targets")
def upsert_target(payload: TargetIn, db: Session = Depends(get_ebsnet_db)):
    if payload.segment not in analysis.SEGMENTS:
        raise HTTPException(400, f"Segment tidak dikenal: {payload.segment}")
    if payload.check_type not in ("tcp", "http"):
        raise HTTPException(400, "check_type harus tcp atau http")
    if payload.check_type == "http" and payload.url and not payload.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL harus diawali http:// atau https://")
    data = payload.model_dump(exclude={"id"})
    t = db.get(EbsNetTarget, payload.id) if payload.id else None
    if payload.id and not t:
        raise HTTPException(404, "Target tidak ditemukan")
    if not t:
        t = EbsNetTarget(**data)
        db.add(t)
    else:
        for k, v in data.items():
            setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return service.target_dict(t)


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, db: Session = Depends(get_ebsnet_db)):
    t = db.get(EbsNetTarget, target_id)
    if not t:
        raise HTTPException(404, "Target tidak ditemukan")
    from app.models.ebs_netmon import EbsNetProbeLog
    db.query(EbsNetProbeLog).filter(EbsNetProbeLog.target_id == target_id).delete()
    db.delete(t)
    db.commit()
    return {"deleted": True}


@router.get("/targets/{target_id}/history")
def target_history(target_id: int, hours: int = 24, db: Session = Depends(get_ebsnet_db)):
    return service.probe_history(db, target_id, min(max(hours, 1), 24 * 30))


@router.post("/probes/run")
def run_probes(target_id: Optional[int] = None, db: Session = Depends(get_ebsnet_db)):
    return service.run_probes(db, [target_id] if target_id else None)


# ── FortiGate ─────────────────────────────────────────────────────────────

@router.get("/fortigate")
def get_fortigate(db: Session = Depends(get_ebsnet_db)):
    return service.latest_snapshots(db, "fortigate", with_raw=True)


@router.post("/fortigate/capture")
def capture_fortigate(db: Session = Depends(get_ebsnet_db)):
    if not service.fortigate_ids(cfg.get_all(db)):
        raise HTTPException(400, "Belum ada FortiGate dipilih di Setup")
    return service.capture_fortigates(db)


@router.get("/fortigate/history")
def fortigate_history(hours: int = 24, db: Session = Depends(get_ebsnet_db)):
    """Compact series for the charts: per snapshot, CPU/mem/sessions and
    each SD-WAN member's latency/jitter/loss."""
    out = []
    for s in service.snapshot_series(db, "fortigate", min(max(hours, 1), 24 * 7)):
        sm = s.get("summary") or {}
        out.append({"checked_at": s["checked_at"], "name": s["name"], "ok": s["ok"],
                    "cpu_pct": sm.get("cpu_pct"), "mem_pct": sm.get("mem_pct"), "sessions": sm.get("sessions"),
                    "net_in_kbps": sm.get("net_in_kbps"), "net_out_kbps": sm.get("net_out_kbps"),
                    "sdwan": [{k: m.get(k) for k in ("check", "member", "state", "latency_ms", "jitter_ms", "loss_pct")}
                              for m in sm.get("sdwan", [])]})
    return out


@router.get("/sdwan-config")
def get_sdwan_config(db: Session = Depends(get_ebsnet_db)):
    return service.sdwan_config_view(db)


@router.post("/sdwan-config/capture")
def capture_sdwan_config(db: Session = Depends(get_ebsnet_db)):
    if not service.fortigate_ids(cfg.get_all(db)):
        raise HTTPException(400, "Belum ada FortiGate dipilih di Setup")
    return service.capture_sdwan_config(db)


# ── EBS health ────────────────────────────────────────────────────────────

@router.get("/ebs")
def get_ebs(db: Session = Depends(get_ebsnet_db)):
    return (service.latest_snapshots(db, "ebs") or [None])[0]


@router.post("/ebs/capture")
def capture_ebs(db: Session = Depends(get_ebsnet_db)):
    return service.capture_ebs(db, include_app_tier=True)


@router.get("/ebs/history")
def ebs_history(hours: int = 24, db: Session = Depends(get_ebsnet_db)):
    keys = ("sessions_active", "sessions_blocked", "forms_sessions", "web_users_15m", "host_cpu_pct",
            "avg_active_sessions", "db_wait_ratio", "single_block_read_ms", "requests_pending",
            "requests_running", "db_connect_ms")
    return [{"checked_at": s["checked_at"], "ok": s["ok"], **{k: (s.get("summary") or {}).get(k) for k in keys}}
            for s in service.snapshot_series(db, "ebs", min(max(hours, 1), 24 * 7))]


# ── Laptop reports ────────────────────────────────────────────────────────

@router.get("/reports")
def list_reports(hours: int = 168, db: Session = Depends(get_ebsnet_db)):
    return service.list_reports(db, min(max(hours, 1), 24 * 90))


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_ebsnet_db)):
    r = db.get(EbsNetClientReport, report_id)
    if not r:
        raise HTTPException(404, "Laporan tidak ditemukan")
    d = service.report_dict(r, with_detail=True)
    d["verdict_text"] = analysis.VERDICT_TEXT.get(r.verdict or "OK")
    d["code_labels"] = {c: analysis.ROOT_CAUSE_CODES.get(c) for c in d["codes"]}
    return d


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_ebsnet_db)):
    r = db.get(EbsNetClientReport, report_id)
    if not r:
        raise HTTPException(404, "Laporan tidak ditemukan")
    db.delete(r)
    db.commit()
    return {"deleted": True}


@router.post("/reports/upload")
def upload_agent_report(payload: dict = Body(...), db: Session = Depends(get_ebsnet_db)):
    """summary.json from an agent that could not post it itself."""
    if "ping_ebs" not in payload:
        raise HTTPException(400, "Bukan summary.json dari agen EBS diagnostic")
    return service.save_client_report(db, service.columns_from_agent(payload), payload)


# ── Agent script ──────────────────────────────────────────────────────────

class AgentIn(BaseModel):
    base_url: str             # window.location.origin of the dashboard
    count: int = 100
    label: Optional[str] = None
    valid_days: int = 14


@router.post("/agent/script")
def generate_agent(payload: AgentIn, db: Session = Depends(get_ebsnet_db),
                   user: CurrentUser = Depends(get_current_user)):
    if not payload.base_url.startswith(("http://", "https://")):
        raise HTTPException(400, "base_url tidak valid")
    s = cfg.get_all(db)
    expires = datetime.utcnow() + timedelta(days=min(max(payload.valid_days, 1), 90))
    tok = EbsNetAgentToken(token=secrets.token_urlsafe(32), label=payload.label, created_by=_who(user),
                           expires_at=expires)
    db.add(tok)
    db.commit()
    ingest = f"{payload.base_url.rstrip('/')}/api/v1/ebs-netmon-agent/ingest/{tok.token}"
    compare = ["1.1.1.1"]
    ho_fgt = next((t for t in db.query(EbsNetTarget).filter(EbsNetTarget.segment == "wan").all() if t.host), None)
    if ho_fgt:
        compare.insert(0, ho_fgt.host)
    script = agent_script.render(
        ebs_host=s.get("ebs_host") or "", ebs_ports=s.get("ebs_ports") or [], ebs_url=s.get("ebs_web_url") or "",
        ingest_url=ingest, compare_hosts=compare, count=min(max(payload.count, 10), 1000), expires_at=expires,
    )
    return Response(content=script, media_type="text/plain; charset=us-ascii",
                    headers={"Content-Disposition": 'attachment; filename="EBS_HO_Diagnostic.ps1"'})


# ── Incidents ─────────────────────────────────────────────────────────────

class IncidentIn(BaseModel):
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str = "open"
    user_name: Optional[str] = None
    laptop: Optional[str] = None
    location: Optional[str] = "HO"
    ebs_module: Optional[str] = None
    transaction: Optional[str] = None
    symptom: Optional[str] = None
    root_cause_code: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    client_report_id: Optional[int] = None
    capture_now: bool = False


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None or dt.tzinfo is None:
        return dt
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def _incident_dict(i: EbsNetIncident, full: bool = False) -> dict:
    d = {c.name: getattr(i, c.name) for c in EbsNetIncident.__table__.columns if c.name != "snapshot"}
    for k in ("started_at", "ended_at", "created_at", "updated_at"):
        d[k] = d[k].isoformat() + "Z" if d[k] else None
    d["root_cause_label"] = analysis.ROOT_CAUSE_CODES.get(i.root_cause_code or "")
    d["has_snapshot"] = bool(i.snapshot)
    if full:
        d["snapshot"] = json.loads(i.snapshot) if i.snapshot else None
    return d


@router.get("/incidents")
def list_incidents(days: int = 90, db: Session = Depends(get_ebsnet_db)):
    since = datetime.utcnow() - timedelta(days=min(max(days, 1), 365))
    rows = (db.query(EbsNetIncident).filter(EbsNetIncident.started_at >= since)
            .order_by(EbsNetIncident.started_at.desc()).all())
    return [_incident_dict(r) for r in rows]


@router.post("/incidents")
def create_incident(payload: IncidentIn, db: Session = Depends(get_ebsnet_db),
                    user: CurrentUser = Depends(get_current_user)):
    if payload.root_cause_code and payload.root_cause_code not in analysis.ROOT_CAUSE_CODES:
        raise HTTPException(400, "Kode root cause tidak dikenal")
    data = payload.model_dump(exclude={"capture_now"})
    data["started_at"] = _naive_utc(data["started_at"])
    data["ended_at"] = _naive_utc(data["ended_at"])
    inc = EbsNetIncident(**data, created_by=_who(user))
    if payload.capture_now:
        inc.snapshot = json.dumps(service.capture_all(db), default=str)
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return _incident_dict(inc)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_ebsnet_db)):
    inc = db.get(EbsNetIncident, incident_id)
    if not inc:
        raise HTTPException(404, "Insiden tidak ditemukan")
    d = _incident_dict(inc, full=True)
    d["correlation"] = service.nearest_snapshots(db, inc.started_at)
    if inc.client_report_id:
        r = db.get(EbsNetClientReport, inc.client_report_id)
        d["client_report"] = service.report_dict(r) if r else None
    return d


@router.put("/incidents/{incident_id}")
def update_incident(incident_id: int, payload: IncidentIn, db: Session = Depends(get_ebsnet_db)):
    inc = db.get(EbsNetIncident, incident_id)
    if not inc:
        raise HTTPException(404, "Insiden tidak ditemukan")
    if payload.root_cause_code and payload.root_cause_code not in analysis.ROOT_CAUSE_CODES:
        raise HTTPException(400, "Kode root cause tidak dikenal")
    for k, v in payload.model_dump(exclude={"capture_now"}).items():
        setattr(inc, k, _naive_utc(v) if k in ("started_at", "ended_at") else v)
    if payload.capture_now:
        inc.snapshot = json.dumps(service.capture_all(db), default=str)
    db.commit()
    db.refresh(inc)
    return _incident_dict(inc)


@router.delete("/incidents/{incident_id}")
def delete_incident(incident_id: int, db: Session = Depends(get_ebsnet_db)):
    inc = db.get(EbsNetIncident, incident_id)
    if not inc:
        raise HTTPException(404, "Insiden tidak ditemukan")
    db.delete(inc)
    db.commit()
    return {"deleted": True}


# ── Diagnosis reports (Laporan tab) ────────────────────────────────────────

@router.get("/summary-reports")
def list_summary_reports(days: int = 30, db: Session = Depends(get_ebsnet_db)):
    since = datetime.utcnow() - timedelta(days=min(max(days, 1), 180))
    rows = (db.query(EbsNetSummaryReport).filter(EbsNetSummaryReport.created_at >= since)
            .order_by(EbsNetSummaryReport.created_at.desc()).limit(500).all())
    s = cfg.get_all(db)
    last = report.last_auto(db)
    hours = float(s.get("report_interval_hours") or 0)
    return {
        "reports": [report.row_dict(r) for r in rows],
        "schedule": {
            "interval_hours": hours,
            "last_auto_at": last.isoformat() + "Z" if last else None,
            "next_auto_at": ((last + timedelta(hours=hours)).isoformat() + "Z" if last else "segera")
                            if hours > 0 else None,
        },
    }


@router.post("/summary-reports/run")
def run_summary_report(db: Session = Depends(get_ebsnet_db), user: CurrentUser = Depends(get_current_user)):
    """Re-take every measurement now, grade it, and save the report."""
    return report.row_dict(report.build(db, trigger="manual", user=_who(user), capture=True), full=True)


@router.get("/summary-reports/{report_id}")
def get_summary_report(report_id: int, db: Session = Depends(get_ebsnet_db)):
    r = db.get(EbsNetSummaryReport, report_id)
    if not r:
        raise HTTPException(404, "Laporan tidak ditemukan")
    return report.row_dict(r, full=True)


@router.get("/summary-reports/{report_id}/download")
def download_summary_report(report_id: int, fmt: str = "html", db: Session = Depends(get_ebsnet_db)):
    r = db.get(EbsNetSummaryReport, report_id)
    if not r:
        raise HTTPException(404, "Laporan tidak ditemukan")
    stamp = (r.created_at + timedelta(hours=7)).strftime("%Y%m%d_%H%M")
    if fmt == "json":
        return Response(content=r.content or "{}", media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="EBS_Diagnosis_{stamp}.json"'})
    return Response(content=r.html or "", media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="EBS_Diagnosis_{stamp}.html"'})


@router.delete("/summary-reports/{report_id}")
def delete_summary_report(report_id: int, db: Session = Depends(get_ebsnet_db)):
    r = db.get(EbsNetSummaryReport, report_id)
    if not r:
        raise HTTPException(404, "Laporan tidak ditemukan")
    db.delete(r)
    db.commit()
    return {"deleted": True}


# ── Setup ─────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings_(db: Session = Depends(get_ebsnet_db)):
    return cfg.get_all(db)


@router.put("/settings")
def put_settings(payload: dict = Body(...), db: Session = Depends(get_ebsnet_db),
                 user: CurrentUser = Depends(get_current_user)):
    return cfg.set_many(db, payload, _who(user))


@router.get("/servers")
def list_servers():
    """Server Control entries (no secrets) for the FortiGate pickers."""
    return [{k: s[k] for k in ("id", "name", "category", "ip", "port", "username", "problem")}
            for s in store.registry_servers(with_secret=False)]
