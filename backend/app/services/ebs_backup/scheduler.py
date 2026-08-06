"""
Schedule execution engine — ported from the standalone ebs-backup-dashboard app.

The `ebs_schedules` table only stores cron metadata (see the /schedules routes
in app/routers/dashboard/ebs_backup.py) with no process reading it unless this
module runs. It's a single APScheduler heartbeat job that polls every 60s for
schedules whose `next_run_at` has passed, dispatches them to the matching
backup trigger, and advances `next_run_at` via croniter.

Polling the DB (instead of registering one APScheduler job per schedule) means
schedules created/edited/toggled through the API take effect on the very next
tick with no restart and no need to keep two schedule stores in sync.
"""
import json
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.models.ebs_backup import EbsSessionLocal, EbsSchedule

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

logger = logging.getLogger("ebs_backup.scheduler")

_scheduler: BackgroundScheduler | None = None


def _next_run(cron_expr: str, base: datetime) -> datetime | None:
    if not HAS_CRONITER:
        return None
    try:
        return croniter(cron_expr, base).get_next(datetime)
    except Exception:
        logger.warning("Bad cron expression %r, schedule will not re-fire", cron_expr)
        return None


def _run_archivelog_sync(db, schedule: EbsSchedule) -> int:
    # Local import: avoids a circular import at module load time (the router
    # doesn't import this scheduler module, but keeping this import scoped
    # here means load order between the two never matters).
    from app.routers.dashboard.ebs_backup import build_archivelog_sync_job, _deploy_and_run, ArchiveLogSyncIn

    params = json.loads(schedule.parameters) if schedule.parameters else {}
    payload = ArchiveLogSyncIn(
        server_id=schedule.target_server_id,
        minio_server_id=params.get("minio_server_id"),
        source_dir=params.get("source_dir", "/data04/PROD/archive"),
        local_staging=params.get("local_staging", "/backup/backup_local_2026/archive_log"),
        minio_prefix=params.get("minio_prefix", "archive-logs"),
        retention_days=params.get("retention_days", 30),
    )
    job, bash, target = build_archivelog_sync_job(db, payload)
    # We're already off-request in a background thread, so just run the
    # deploy step directly instead of going through FastAPI's BackgroundTasks.
    _deploy_and_run(job.id, bash, target)
    return job.id


# Job types with a wired execution path. Anything else (online_full,
# online_incremental, app_fs, archivelog) still needs a human to click
# "Trigger" in its tab — the schedule row just tracks intent/next_run_at for
# those until they get their own runner here.
_RUNNERS = {
    "archivelog_sync": _run_archivelog_sync,
}


def _tick():
    db = EbsSessionLocal()
    try:
        now = datetime.utcnow()
        due = db.query(EbsSchedule).filter(
            EbsSchedule.enabled.is_(True),
            EbsSchedule.next_run_at.isnot(None),
            EbsSchedule.next_run_at <= now,
        ).all()
        for sched in due:
            runner = _RUNNERS.get(sched.job_type)
            sched.next_run_at = _next_run(sched.cron_expression, now)
            if not runner:
                db.commit()
                continue
            try:
                job_id = runner(db, sched)
                sched.last_run_at = now
                sched.last_run_status = "submitted"
                sched.last_run_job_id = job_id
                logger.info("Schedule %r fired -> job #%s", sched.name, job_id)
            except Exception:
                logger.exception("Schedule %r failed to launch", sched.name)
                sched.last_run_at = now
                sched.last_run_status = "failed"
            db.commit()
    finally:
        db.close()


def start():
    global _scheduler
    if _scheduler is not None:
        return
    if not HAS_CRONITER:
        logger.warning("croniter not installed — EBS backup schedule poller NOT started")
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", seconds=60, id="ebs_backup_schedule_poller",
                        next_run_time=datetime.utcnow(), max_instances=1)
    _scheduler.start()
    logger.info("EBS backup schedule poller started (60s interval)")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
