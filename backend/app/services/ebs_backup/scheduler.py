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

from datetime import timedelta

from app.models.ebs_backup import (
    EbsSessionLocal, EbsSchedule, EbsBackupJob, EbsServer, EbsCredential,
)

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



# A job is only considered dead after this long, so a just-submitted one whose
# PID is not yet visible over SSH is never reaped out from under itself.
_REAP_GRACE = timedelta(minutes=3)


def _reap_dead_jobs(db):
    """Close out jobs whose process is gone but whose row still says running.

    Until now this reconciliation lived ONLY in the job-detail endpoint, so a
    backup that died was recorded as finished exactly when a human happened to
    open that job's page — and not before. On 2026-10-06 an RMAN script aborted
    at parse time within seconds, and the dashboard still showed "running"
    twelve hours later: the operator believed a backup was in progress when
    nothing had been written at all. A backup system that reports a dead job as
    running is worse than one that reports nothing, because it answers the
    question "are we backed up?" with a confident yes.

    Runs on the same 60s heartbeat. Normally there are zero or one running
    jobs, so this is one SSH round trip a minute at most, and each job is
    isolated so an unreachable server cannot stall the schedule dispatch that
    shares this tick.
    """
    from app.services.ebs_backup.ssh_executor import ssh_from_server

    cutoff = datetime.utcnow() - _REAP_GRACE
    stale = db.query(EbsBackupJob).filter(
        EbsBackupJob.status.in_(("running", "paused")),
        EbsBackupJob.pid.isnot(None),
        EbsBackupJob.started_at.isnot(None),
        EbsBackupJob.started_at < cutoff,
    ).all()

    for job in stale:
        try:
            server = db.query(EbsServer).get(job.target_server_id)
            cred = db.query(EbsCredential).filter(
                EbsCredential.server_id == server.id,
                EbsCredential.cred_type.in_(["ssh_password", "ssh_key"]),
            ).first()
            if not server or not cred:
                continue

            with ssh_from_server(server, cred) as ssh:
                if ssh.is_pid_alive(job.pid):
                    continue

                data = {}
                if job.output_path:
                    r = ssh.run(f"cat {job.output_path}/manifest.json 2>/dev/null || echo '{{}}'")
                    try:
                        data = json.loads((r.stdout or "").strip())
                    except Exception:
                        data = {}

                job.status = data.get("status") or "failed"
                if data.get("total_size_bytes"):
                    job.total_size_bytes = data["total_size_bytes"]
                if data.get("file_count"):
                    job.file_count = data["file_count"]

                # "failed" with no reason sends the operator hunting through
                # logs on the DB server. The tail almost always holds the real
                # error — for the RMAN parse abort it was the RMAN-02001 stack.
                if job.status != "success" and not job.error_message:
                    tail = ""
                    for path in (f"{job.output_path}/rman_session.log" if job.output_path else None,
                                 job.log_path):
                        if not path:
                            continue
                        got = ssh.run(f"tail -n 25 {path} 2>/dev/null")
                        if (got.stdout or "").strip():
                            tail = got.stdout.strip()
                            break
                    job.error_message = tail or (
                        "Process ended without writing manifest.json — check the log on the server."
                    )

            job.finished_at = datetime.utcnow()
            if job.started_at:
                job.duration_sec = int((job.finished_at - job.started_at).total_seconds())
            db.commit()
            logger.warning("Reaped job #%s: process %s gone, marked %s",
                           job.id, job.pid, job.status)
        except Exception:
            db.rollback()
            logger.exception("Could not reap job #%s", job.id)


def _tick():
    db = EbsSessionLocal()
    try:
        # Before dispatching anything new, close out what has already died —
        # otherwise a dead job stays "running" until someone opens its page.
        _reap_dead_jobs(db)

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
