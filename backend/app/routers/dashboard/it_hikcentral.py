"""
HikCentral Integration — IT dashboard control tab for the office's Hikvision
DS-K1T342MFWX face-recognition terminals, aggregated behind HikCentral
(OpenAPI/Artemis). One place to configure the connection, test it, trigger a
manual sync, and see recent sync history — instead of needing an SSH session
into the backend + a raw .env edit + restart every time something needs to
change, which was the slow loop the initial integration setup went through.

  GET  /config          — current config (base_url, masked app_key, source)
  POST /config           — save base_url/app_key/app_secret (DB-backed,
                            takes effect immediately, no restart)
  POST /config/test       — on-demand connectivity probe (narrow time-window
                            door-events search)
  GET  /sync/status      — configured?, last sync summary, poll interval
  POST /sync/now          — manual "Sync Now" (same code path as the
                            15-minute background poller)
  GET  /sync/history      — recent sync log rows (AttendanceUploadLog,
                            source="hikcentral")

Role-gated at the router level in main.py (require_role(Roles.IT)).
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_user, CurrentUser
from app.models.attendance import AttendanceUploadLog
from app.models.hikcentral import HikCentralConfig, get_hikcentral_db, resolve_effective_config
from app.services import crypto
from app.services import hikcentral_scheduler
from app.services.hikcentral_client import HikCentralClient, HikCentralError

router = APIRouter()

SYNC_INTERVAL_MINUTES = 15


def _mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 4:
        return "•" * len(value)
    return value[:4] + "•" * (len(value) - 4)


@router.get("/config")
def get_config(db: Session = Depends(get_hikcentral_db)):
    cfg = resolve_effective_config(db)
    return {
        "configured": bool(cfg["base_url"] and cfg["app_key"] and cfg["app_secret"]),
        "base_url": cfg["base_url"],
        "app_key_masked": _mask(cfg["app_key"]),
        "source": cfg["source"],  # "database" | "env" | "none"
    }


class ConfigIn(BaseModel):
    base_url: str
    app_key: str
    app_secret: str


@router.post("/config")
def save_config(payload: ConfigIn, db: Session = Depends(get_hikcentral_db), user: CurrentUser = Depends(get_current_user)):
    row = db.query(HikCentralConfig).first()
    encrypted = crypto.encrypt(payload.app_secret)
    if not row:
        row = HikCentralConfig(
            base_url=payload.base_url.rstrip("/"), app_key=payload.app_key,
            app_secret_encrypted=encrypted, updated_by=user.username,
        )
        db.add(row)
    else:
        row.base_url = payload.base_url.rstrip("/")
        row.app_key = payload.app_key
        row.app_secret_encrypted = encrypted
        row.updated_by = user.username
        row.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "saved"}


@router.post("/config/test")
def test_connection(db: Session = Depends(get_hikcentral_db)):
    """Narrow-window (last 5 minutes) door-events search — cheap, doesn't
    need any real events to succeed, just a well-formed authorized response.
    A failure here is almost always one of: base_url/AppKey/AppSecret wrong,
    HikCentral unreachable from this server, or (the issue found during
    initial setup) the OpenAPI Gateway's "Authorized APIs" list is empty —
    which needs enabling in HikCentral's own admin console, not fixable
    from here."""
    cfg = resolve_effective_config(db)
    if not (cfg["base_url"] and cfg["app_key"] and cfg["app_secret"]):
        return {"ok": False, "error": "Not configured — fill in Base URL / AppKey / AppSecret below and save first."}

    now = datetime.now().astimezone()
    tz = now.strftime("%z")
    tz = f"{tz[:3]}:{tz[3:]}" if tz else "+07:00"
    start = (now - timedelta(minutes=5)).strftime(f"%Y-%m-%dT%H:%M:%S{tz}")
    end = now.strftime(f"%Y-%m-%dT%H:%M:%S{tz}")

    try:
        client = HikCentralClient(base_url=cfg["base_url"], app_key=cfg["app_key"], app_secret=cfg["app_secret"])
        result = client.search_door_events(start, end, page_no=1, page_size=10)
        events = result.get("list") or result.get("events") or []
        return {"ok": True, "message": f"Connected — {len(events)} event(s) in the last 5 minutes.", "event_count": len(events)}
    except HikCentralError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@router.get("/sync/status")
def sync_status(db: Session = Depends(get_hikcentral_db)):
    cfg = resolve_effective_config(db)
    return {
        "configured": bool(cfg["base_url"] and cfg["app_key"] and cfg["app_secret"]),
        "last_sync": hikcentral_scheduler.get_last_sync(),
        "interval_minutes": SYNC_INTERVAL_MINUTES,
    }


@router.post("/sync/now")
def sync_now(user: CurrentUser = Depends(get_current_user)):
    try:
        return hikcentral_scheduler.run_sync(uploaded_by=user.username)
    except HikCentralError as e:
        raise HTTPException(502, str(e))


@router.get("/sync/history")
def sync_history(limit: int = 20):
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(AttendanceUploadLog)
                .where(AttendanceUploadLog.source == "hikcentral")
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
