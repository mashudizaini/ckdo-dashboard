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

                # The manifest lives where the ARCHIVE landed, which is not
                # always the server that ran the job. An application backup
                # streamed to the DB server runs on the App server and writes
                # to the DB server — and the App server has no /backup at all,
                # so reading the manifest there returns nothing and a finished,
                # successful backup gets recorded as failed. That is exactly
                # what happened to job #4 on 2026-10-07: 13 GB transferred, the
                # manifest said success, and the dashboard said failed — which
                # also meant the Synology copy never chained.
                data = {}
                if job.output_path:
                    holder_ssh, holder_cm = ssh, None
                    try:
                        from app.routers.dashboard.ebs_backup import _archive_holder
                        from app.database import SessionLocal as _AppSession
                        app_db = _AppSession()
                        try:
                            holder = _archive_holder(app_db, job)
                        finally:
                            app_db.close()
                        if holder and holder.id != job.target_server_id:
                            h_cred = db.query(EbsCredential).filter(
                                EbsCredential.server_id == holder.id,
                                EbsCredential.cred_type.in_(["ssh_password", "ssh_key"]),
                            ).first()
                            h_srv = db.query(EbsServer).get(holder.id)
                            if h_cred and h_srv:
                                holder_cm = ssh_from_server(h_srv, h_cred)
                                holder_ssh = holder_cm.__enter__()
                    except Exception:
                        holder_ssh, holder_cm = ssh, None

                    try:
                        r = holder_ssh.run(f"cat {job.output_path}/manifest.json 2>/dev/null || echo '{{}}'")
                        try:
                            data = json.loads((r.stdout or "").strip())
                        except Exception:
                            data = {}
                    finally:
                        if holder_cm is not None:
                            holder_cm.__exit__(None, None, None)

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

            if job.status == "success":
                _chain_synology_sync(db, job)
        except Exception:
            db.rollback()
            logger.exception("Could not reap job #%s", job.id)




def _chain_synology_sync(db, job):
    """Copy a finished archive to Synology when the job asked for it.

    Two stages rather than two simultaneous destinations: the archive lands on
    the DB server, which has the room, and is copied from there. Streaming to
    both at once would mean reading the application tier twice over the network.

    Chained here, off the same heartbeat that noticed the job finished, so the
    copy starts on its own — nobody has to be watching the page at 22:30 to
    press a second button.
    """
    try:
        params = json.loads(job.parameters or "{}")
    except Exception:
        return
    target_id = params.get("sync_synology_server_id")
    if not target_id:
        return

    try:
        from fastapi import BackgroundTasks
        from app.database import SessionLocal
        from app.routers.dashboard.ebs_backup import SyncBackupIn, _sync_existing_backup

        # BackgroundTasks outside a request never runs itself, so the tasks it
        # collects are executed here explicitly.
        bg = BackgroundTasks()
        app_db = SessionLocal()
        try:
            res = _sync_existing_backup(
                app_db, bg, SyncBackupIn(job_id=job.id, target_server_id=int(target_id)), "synology",
            )
        finally:
            app_db.close()
        for task in bg.tasks:
            task.func(*task.args, **task.kwargs)
        logger.info("Job #%s finished; Synology sync submitted as job #%s -> %s",
                    job.id, res.get("job_id"), res.get("destination"))
    except Exception:
        logger.exception("Could not chain Synology sync for job #%s", job.id)


def _fire_scheduled_jobs(db):
    """Launch jobs whose chosen time has arrived.

    A one-off "run at 22:00" is stored as a job row with status 'scheduled' and
    run_at_utc inside parameters — no new table, and no cron expression pretending
    to mean "once". The script is built HERE rather than when the user picked the
    time, so the staging directory is stamped with the moment it actually runs.

    Wrapped per job: a server that cannot be reached must not stop the other
    schedules sharing this tick, and must not leave the row claiming to be
    running when nothing was launched.
    """
    from app.routers.dashboard.ebs_backup import (
        BackupOnlineIn, BackupAppIn, build_online_script, build_app_script, _deploy_and_run,
    )

    # Which payload and which builder, per job type. Adding a type here is the
    # whole change needed to make it schedulable.
    BUILDERS = {
        "online_full": (BackupOnlineIn, build_online_script),
        "online_incremental": (BackupOnlineIn, build_online_script),
        "app_fs": (BackupAppIn, build_app_script),
    }
    from app.database import SessionLocal
    from app.models.ebs_backup import EbsServer as _Srv

    now = datetime.utcnow()
    due = db.query(EbsBackupJob).filter(EbsBackupJob.status == "scheduled").all()
    for job in due:
        try:
            params = json.loads(job.parameters or "{}")
            run_at = params.get("run_at_utc")
            if not run_at or datetime.strptime(run_at, "%Y-%m-%d %H:%M:%S") > now:
                continue

            # Build with the router's own session: build_online_script reads
            # servers and credentials through the main app's models.
            model, builder = BUILDERS.get(job.job_type, (None, None))
            if builder is None:
                raise RuntimeError(f"Jenis job '{job.job_type}' belum bisa dijadwalkan")

            app_db = SessionLocal()
            try:
                srv = app_db.query(_Srv).get(job.target_server_id)
                payload = model(**{k: v for k, v in params.items()
                                   if k in model.model_fields and k != "run_at_local"})
                bash, target = builder(app_db, srv, payload, job.id)
            finally:
                app_db.close()

            job.status = "pending"
            job.started_at = now
            job.output_path = target
            db.commit()

            _deploy_and_run(job.id, bash, target)
            logger.info("Scheduled job #%s fired (was due %s UTC)", job.id, run_at)
        except Exception:
            db.rollback()
            job.status = "failed"
            job.error_message = "Gagal meluncurkan job terjadwal — lihat log backend."
            job.finished_at = datetime.utcnow()
            db.commit()
            logger.exception("Could not fire scheduled job #%s", job.id)


def _tick():
    db = EbsSessionLocal()
    try:
        # Before dispatching anything new, close out what has already died —
        # otherwise a dead job stays "running" until someone opens its page.
        _reap_dead_jobs(db)
        _fire_scheduled_jobs(db)

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
