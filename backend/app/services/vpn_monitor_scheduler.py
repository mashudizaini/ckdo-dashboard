"""
VPN Access Monitoring — background poller. Same pattern as
ebs_backup/scheduler.py: a single APScheduler heartbeat job, this time on a
5-minute interval, that checks every enabled VpnGateway (reachability, plus
active sessions if a credential is on file) and appends one VpnCheckLog row
each tick — this is what backs the uptime history strip, as opposed to the
on-demand "Check Now" button which also writes a log row but is user-triggered.
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.models.vpn_monitor import VpnSessionLocal, VpnGateway, VpnCredential, VpnCheckLog
from app.services import vpn_monitor_service as svc

logger = logging.getLogger("vpn_monitor.scheduler")

_scheduler: BackgroundScheduler | None = None

LOG_RETENTION_DAYS = 30


def _tick():
    db = VpnSessionLocal()
    try:
        gateways = db.query(VpnGateway).filter(VpnGateway.enabled.is_(True)).all()
        for gw in gateways:
            result = svc.check_reachable(gw.public_host, gw.public_port)
            active_count = None
            if result["reachable"]:
                cred = db.query(VpnCredential).filter(VpnCredential.gateway_id == gw.id).first()
                if cred:
                    sess = svc.get_active_sessions(gw, cred)
                    if sess["ok"]:
                        active_count = len(sess["sessions"])
            db.add(VpnCheckLog(
                gateway_id=gw.id, reachable=result["reachable"],
                latency_ms=result["latency_ms"], error=result["error"],
                active_user_count=active_count,
            ))
        cutoff = datetime.utcnow() - timedelta(days=LOG_RETENTION_DAYS)
        db.query(VpnCheckLog).filter(VpnCheckLog.checked_at < cutoff).delete()
        db.commit()
    except Exception:
        logger.exception("VPN monitor poll tick failed")
        db.rollback()
    finally:
        db.close()


def start():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", minutes=5, id="vpn_monitor_poller",
                        next_run_time=datetime.utcnow(), max_instances=1)
    _scheduler.start()
    logger.info("VPN monitor poller started (5min interval)")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
