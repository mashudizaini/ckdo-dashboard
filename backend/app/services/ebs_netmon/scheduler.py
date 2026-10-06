"""
Oracle EBS Network Monitoring — background poller (same pattern as
vpn_monitor_scheduler). Every 5 minutes: probe every enabled target, then
snapshot the FortiGates and EBS health when enabled in Setup. That steady
series is what makes "EBS was slow at 14:32" answerable after the fact —
the script's test matrix (08:00 / 11:00 / 14:00 / 15:00-16:00) is covered
automatically on the server side; only the laptop side needs a person.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.models.ebs_netmon import EbsNetSessionLocal
from app.services.ebs_netmon import service
from app.services.ebs_netmon import settings as cfg

logger = logging.getLogger("ebs_netmon.scheduler")

_scheduler: BackgroundScheduler | None = None
_ticks = 0


def _tick():
    global _ticks
    _ticks += 1
    db = EbsNetSessionLocal()
    try:
        s = cfg.get_all(db)
        service.run_probes(db)
        if s.get("poll_fortigate") and service.fortigate_ids(s):
            service.capture_fortigates(db)
        if s.get("poll_ebs"):
            # App-tier SSH is the slow part — every 3rd tick (15 min) is
            # enough and matches Server Process Monitoring's own cadence.
            service.capture_ebs(db, include_app_tier=(_ticks % 3 == 1))
        if _ticks % 12 == 1:
            service.prune(db)
    except Exception:
        logger.exception("EBS network monitor tick failed")
        db.rollback()
    finally:
        db.close()


def start():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", minutes=5, id="ebs_netmon_poller",
                       next_run_time=datetime.utcnow(), max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info("EBS network monitor poller started (5min interval)")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
