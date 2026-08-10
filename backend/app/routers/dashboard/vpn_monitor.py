"""
VPN Access Monitoring — reachability + active-session monitoring for the
office FortiClient SSL-VPN gateway.

  Gateways      GET/POST /gateways, DELETE /gateways/{id}
  Credentials   POST /gateways/{id}/credential
  Checks        POST /gateways/{id}/check (on-demand, "Check Now")
  History       GET /gateways/{id}/history
  Sessions      GET /gateways/{id}/sessions (live, not from the log)

Role-gated at the router level in main.py (require_role(Roles.IT)), same as
ebs_backup — not per-route here.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.vpn_monitor import get_vpn_db, VpnGateway, VpnCredential, VpnCheckLog
from app.services import crypto
from app.services import vpn_monitor_service as svc

router = APIRouter()


class GatewayIn(BaseModel):
    name: str
    public_host: str
    public_port: int = 443
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    notes: Optional[str] = None
    enabled: bool = True


class CredentialIn(BaseModel):
    username: str
    password: str


def _serialize_gateway(g: VpnGateway, db: Session) -> dict:
    has_cred = db.query(VpnCredential).filter(VpnCredential.gateway_id == g.id).first() is not None
    return {
        "id": g.id, "name": g.name, "public_host": g.public_host, "public_port": g.public_port,
        "ssh_host": g.ssh_host, "ssh_port": g.ssh_port, "enabled": g.enabled, "notes": g.notes,
        "has_credential": has_cred,
    }


@router.get("/gateways")
def list_gateways(db: Session = Depends(get_vpn_db)):
    rows = db.query(VpnGateway).order_by(VpnGateway.name).all()
    return [_serialize_gateway(g, db) for g in rows]


@router.post("/gateways")
def upsert_gateway(payload: GatewayIn, db: Session = Depends(get_vpn_db)):
    """Matches by name (same upsert convention as ebs_backup's server registry) —
    saving again with the same name edits that gateway instead of duplicating it."""
    g = db.query(VpnGateway).filter(VpnGateway.name == payload.name).first()
    if not g:
        g = VpnGateway(**payload.model_dump())
        db.add(g)
    else:
        for k, v in payload.model_dump().items():
            setattr(g, k, v)
        g.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(g)
    return _serialize_gateway(g, db)


@router.delete("/gateways/{gateway_id}")
def delete_gateway(gateway_id: int, db: Session = Depends(get_vpn_db)):
    g = db.query(VpnGateway).filter(VpnGateway.id == gateway_id).first()
    if not g:
        raise HTTPException(404, "Gateway not found")
    db.query(VpnCredential).filter(VpnCredential.gateway_id == gateway_id).delete()
    db.query(VpnCheckLog).filter(VpnCheckLog.gateway_id == gateway_id).delete()
    db.delete(g)
    db.commit()
    return {"deleted": True}


@router.post("/gateways/{gateway_id}/credential")
def upsert_credential(gateway_id: int, payload: CredentialIn, db: Session = Depends(get_vpn_db)):
    g = db.query(VpnGateway).filter(VpnGateway.id == gateway_id).first()
    if not g:
        raise HTTPException(404, "Gateway not found")
    cred = db.query(VpnCredential).filter(VpnCredential.gateway_id == gateway_id).first()
    encrypted = crypto.encrypt(payload.password)
    if not cred:
        cred = VpnCredential(gateway_id=gateway_id, username=payload.username, secret_encrypted=encrypted)
        db.add(cred)
    else:
        cred.username = payload.username
        cred.secret_encrypted = encrypted
    db.commit()
    return {"id": cred.id, "status": "saved"}


def _do_check(gateway: VpnGateway, db: Session) -> dict:
    reach = svc.check_reachable(gateway.public_host, gateway.public_port)
    sessions_result = None
    active_count = None
    if reach["reachable"]:
        cred = db.query(VpnCredential).filter(VpnCredential.gateway_id == gateway.id).first()
        if cred:
            sessions_result = svc.get_active_sessions(gateway, cred)
            if sessions_result["ok"]:
                active_count = len(sessions_result["sessions"])

    db.add(VpnCheckLog(
        gateway_id=gateway.id, reachable=reach["reachable"],
        latency_ms=reach["latency_ms"], error=reach["error"], active_user_count=active_count,
    ))
    db.commit()

    return {
        "gateway_id": gateway.id, "checked_at": datetime.utcnow().isoformat(),
        "reachable": reach["reachable"], "latency_ms": reach["latency_ms"], "error": reach["error"],
        "sessions": sessions_result,
    }


@router.post("/gateways/{gateway_id}/check")
def check_now(gateway_id: int, db: Session = Depends(get_vpn_db)):
    g = db.query(VpnGateway).filter(VpnGateway.id == gateway_id).first()
    if not g:
        raise HTTPException(404, "Gateway not found")
    return _do_check(g, db)


@router.get("/gateways/{gateway_id}/history")
def get_history(gateway_id: int, hours: int = 24, db: Session = Depends(get_vpn_db)):
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(VpnCheckLog)
        .filter(VpnCheckLog.gateway_id == gateway_id, VpnCheckLog.checked_at >= since)
        .order_by(VpnCheckLog.checked_at.asc())
        .all()
    )
    return [
        {
            "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            "reachable": r.reachable, "latency_ms": r.latency_ms, "error": r.error,
            "active_user_count": r.active_user_count,
        }
        for r in rows
    ]


@router.get("/gateways/{gateway_id}/sessions")
def get_sessions(gateway_id: int, db: Session = Depends(get_vpn_db)):
    g = db.query(VpnGateway).filter(VpnGateway.id == gateway_id).first()
    if not g:
        raise HTTPException(404, "Gateway not found")
    cred = db.query(VpnCredential).filter(VpnCredential.gateway_id == gateway_id).first()
    if not cred:
        return {"ok": False, "error": "No SSH credential configured for this gateway — set it in Setup", "sessions": [], "raw_output": None}
    return svc.get_active_sessions(g, cred)
