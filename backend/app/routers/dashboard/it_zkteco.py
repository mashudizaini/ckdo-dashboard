"""
ZKTeco Plant Attendance Integration — IT dashboard control tab for the
Plant location's "Solution" X606-S (ZKTeco-protocol) attendance terminals.
Unlike HikCentral (one device, one config row), Plant has up to 8 physical
terminals (Lobby, Loker Male, Loker Female, Server IT, Female Lab, Male
Lab, Mall, Office — confirmed live 2026-08-28), so this manages a list of
devices instead of a single config.

  GET    /devices              — list all configured devices
  POST   /devices               — add a device
  PUT    /devices/{id}          — edit a device
  DELETE /devices/{id}          — remove a device
  POST   /devices/{id}/test      — on-demand connectivity probe (connect,
                                  count users) — same protocol path as sync
  GET    /sync/status           — configured?, last sync summary, poll interval
  POST   /sync/now               — starts a manual sync in the background
                                  (same code path as the 15-minute poller,
                                  all devices) and returns immediately —
                                  a full sync reprocesses every device's
                                  entire history and can take a while.
  GET    /sync/now/status         — progress/result of the running (or
                                  last) manual sync — poll this after
                                  POST /sync/now.
  GET    /sync/history           — recent sync log rows (AttendanceUploadLog,
                                  source="zkteco")

Role-gated at the router level in main.py (require_role(Roles.IT)).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import SessionLocal
from app.dependencies import get_current_user, CurrentUser
from app.models.attendance import AttendanceUploadLog
from app.models.zkteco import ZKTecoDevice, get_zkteco_db
from app.services import zkteco_scheduler
from app.services.zkteco_client import ZKTecoClient, ZKTecoError

router = APIRouter()

SYNC_INTERVAL_MINUTES = 15


def _device_dict(d: ZKTecoDevice) -> dict:
    return {
        "id": d.id, "name": d.name, "ip": d.ip, "port": d.port,
        "has_password": bool(d.password), "enabled": d.enabled,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "updated_by": d.updated_by,
    }


@router.get("/devices")
def list_devices(db=Depends(get_zkteco_db)):
    rows = db.query(ZKTecoDevice).order_by(ZKTecoDevice.name).all()
    return [_device_dict(d) for d in rows]


class DeviceIn(BaseModel):
    name: str
    ip: str
    port: int = 4370
    password: int = 0
    enabled: bool = True


@router.post("/devices")
def create_device(payload: DeviceIn, db=Depends(get_zkteco_db), user: CurrentUser = Depends(get_current_user)):
    d = ZKTecoDevice(
        name=payload.name.strip(), ip=payload.ip.strip(), port=payload.port,
        password=payload.password, enabled=payload.enabled, updated_by=user.username,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _device_dict(d)


@router.put("/devices/{device_id}")
def update_device(device_id: int, payload: DeviceIn, db=Depends(get_zkteco_db), user: CurrentUser = Depends(get_current_user)):
    d = db.query(ZKTecoDevice).filter(ZKTecoDevice.id == device_id).first()
    if not d:
        raise HTTPException(404, "Device not found")
    d.name = payload.name.strip()
    d.ip = payload.ip.strip()
    d.port = payload.port
    d.password = payload.password
    d.enabled = payload.enabled
    d.updated_by = user.username
    d.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(d)
    return _device_dict(d)


@router.delete("/devices/{device_id}")
def delete_device(device_id: int, db=Depends(get_zkteco_db)):
    d = db.query(ZKTecoDevice).filter(ZKTecoDevice.id == device_id).first()
    if not d:
        raise HTTPException(404, "Device not found")
    db.delete(d)
    db.commit()
    return {"status": "deleted"}


@router.post("/devices/{device_id}/test")
def test_device(device_id: int, db=Depends(get_zkteco_db)):
    """Connects to just this one device and counts its enrolled users —
    cheap, doesn't touch AttendanceRecord. A failure here is almost
    always one of: IP/port wrong, the device unreachable from this server
    (LAN/VLAN/firewall — Plant terminals sit on their own subnet), or a
    wrong comm key ("password")."""
    d = db.query(ZKTecoDevice).filter(ZKTecoDevice.id == device_id).first()
    if not d:
        raise HTTPException(404, "Device not found")
    try:
        names, _ = ZKTecoClient(d.ip, port=d.port, password=d.password).fetch()
        return {"ok": True, "message": f"Connected — {len(names)} enrolled user(s).", "user_count": len(names)}
    except ZKTecoError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@router.get("/sync/status")
def sync_status():
    return {
        "configured": zkteco_scheduler.is_configured(),
        "last_sync": zkteco_scheduler.get_last_sync(),
        "interval_minutes": SYNC_INTERVAL_MINUTES,
    }


@router.post("/sync/now")
def sync_now(user: CurrentUser = Depends(get_current_user)):
    """Starts a sync in the background and returns immediately — a full
    sync can take a while (every device's ENTIRE attendance history is
    reprocessed each time, and this company's real data spans ~150
    employees across 2018-2026), easily longer than an HTTP/reverse-proxy
    timeout. Poll /sync/now/status for progress and the result."""
    try:
        return zkteco_scheduler.start_manual_sync(uploaded_by=user.username)
    except ZKTecoError as e:
        raise HTTPException(409, str(e))


@router.get("/sync/now/status")
def sync_now_status():
    return zkteco_scheduler.get_manual_sync_status()


@router.get("/sync/history")
def sync_history(limit: int = 20):
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(AttendanceUploadLog)
                .where(AttendanceUploadLog.source == "zkteco")
                .order_by(AttendanceUploadLog.uploaded_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "batch_id": r.batch_id, "total_rows": r.total_rows,
                "inserted": r.inserted, "updated": r.updated,
                "notes": r.notes, "uploaded_by": r.uploaded_by,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
