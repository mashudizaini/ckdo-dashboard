"""
Oracle EBS Backup Recovery Router
─────────────────────────────────────────
Route prefix : /api/v1/dashboard/it/ebs-backup
Required role: it_staff OR admin (enforced at include_router() in main.py —
               every route below is unauthenticated by itself, exactly like
               the standalone ebs-backup-dashboard app it was ported from,
               which had NO auth at all and relied on network isolation.)

Ported near-verbatim from the standalone `ebs-backup-dashboard` app (was
running separately on port 28200/28201) — see backend/app/models/ebs_backup.py
for why this stays sync SQLAlchemy + plain `def` routes instead of the async
convention used elsewhere in this app: the real work here is blocking SSH
(Paramiko) to Oracle EBS servers, exactly as the original was written and
tested, including a restore path — not worth the risk of an async rewrite.

Endpoint groups (each was its own file in the standalone app; combined here
into one module purely to sidestep circular imports between them — e.g.
restore.py called into backup.py's _deploy_and_run, storage.py's
_minio_client was reused by inventory.py):
  Overview      GET  /overview, /disk-space
  Servers       GET/POST /servers, DELETE /servers/{id}, POST /servers/credentials,
                GET /servers/{id}/credentials, POST /servers/test-connection
  Backup        POST /backup/online, GET /backup/online/preflight/{id},
                POST /backup/online/sync-minio, /backup/online/sync-synology,
                POST /backup/archivelog, /backup/offline, /backup/app,
                POST /backup/archivelog-sync
  Jobs          GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel|pause|resume|delete-output
  Schedules     GET/POST /schedules, DELETE /schedules/{id}, POST /schedules/{id}/toggle
  SSH Setup     POST /ssh-setup/generate-key, /ssh-setup/copy-id, /ssh-setup/test
  Storage       GET /storage/minio/{id}/usage|list, POST /storage/minio/{id}/delete,
                GET /storage/synology/{id}/usage|list, POST /storage/synology/{id}/delete
  Restore       GET /restore/preflight, POST /restore/dev-database
  Reports       GET /reports/summary
  Inventory     GET /inventory/scan, POST /inventory/delete
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from minio import Minio
from minio.deleteobjects import DeleteObject

from app.models.ebs_backup import (
    get_ebs_db as get_db, EbsServer as Server, EbsCredential as Credential,
    EbsBackupJob as BackupJob, EbsSchedule as Schedule, EbsSessionLocal as SessionLocal,
)
from app.services.ebs_backup.ssh_executor import ssh_from_server, SSHExecutor
from app.services.ebs_backup.vault_shim import vault
from app.services.ebs_backup import rman_templates

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

router = APIRouter()


# Fallback paths when a per-server override isn't set. These mirror the
# standalone app's config.py defaults — kept as plain constants here rather
# than added to the shared app Settings, since nothing else in this app talks
# to these paths (Oracle here is only ever reached via SSH+sqlplus on the
# remote box, never oracledb — unrelated to the rest of the app's Oracle EBS
# connection settings).
class _Defaults:
    BACKUP_ROOT = "/backup"
    BACKUP_STAGING = "/backup/staging"
    ORACLE_HOME = "/u01/app/oracle/product/12.1.0/dbhome_1"
    ORACLE_SID = "PROD"
    APPS_BASE = "/u01/install/PROD"


settings = _Defaults()


# ============================================================
# Schemas
# ============================================================
class ServerIn(BaseModel):
    name: str
    role: str
    host: str
    port: int = 22
    oracle_sid: Optional[str] = None
    oracle_home: Optional[str] = None
    apps_base: Optional[str] = None
    current_fs: Optional[str] = None
    endpoint_url: Optional[str] = None
    bucket: Optional[str] = None
    region: Optional[str] = None
    share_path: Optional[str] = None
    protocol: Optional[str] = None
    notes: Optional[str] = None
    enabled: bool = True


class CredentialIn(BaseModel):
    server_id: int
    cred_type: str
    username: Optional[str] = None
    secret: str
    key_passphrase: Optional[str] = None


class TestConnectionIn(BaseModel):
    server_id: int


class BackupOnlineIn(BaseModel):
    server_id: int
    job_type: str = "online_full"
    incremental_level: int = 1
    parallelism: int = 4
    compression: bool = True
    include_archivelog: bool = True
    archivelog_delete_input: bool = False
    destination: str = "staging"
    minio_server_id: Optional[int] = None
    synology_server_id: Optional[int] = None


class SyncBackupIn(BaseModel):
    job_id: int
    target_server_id: int


class BackupOfflineIn(BaseModel):
    server_id: int
    data_paths: List[str] = ["/data01", "/data02", "/data03", "/data04"]
    stop_apps_first: bool = True
    confirm_token: str


class BackupArchlogIn(BaseModel):
    server_id: int
    delete_input: bool = True


class BackupAppIn(BaseModel):
    server_id: int
    fs_target: str = "fs2"
    include_inst_top: bool = True
    remote_target_server_id: Optional[int] = None


class RestoreDevIn(BaseModel):
    source_job_id: int
    dev_server_id: int


class ArchiveLogSyncIn(BaseModel):
    server_id: int
    minio_server_id: int
    source_dir: str = "/data04/PROD/archive"
    local_staging: str = "/backup/backup_local_2026/archive_log"
    minio_prefix: str = "archive-logs"
    retention_days: int = 30


class ScheduleIn(BaseModel):
    name: str
    job_type: str
    cron_expression: str
    target_server_id: int
    parameters: Dict[str, Any] = {}
    enabled: bool = True


# ============================================================
# Overview & Disk Space
# ============================================================

# Archive log backup to MinIO runs via an existing cron job directly on the DB
# server (not triggered by this dashboard) — this dashboard only reads its
# result, by checking the newest file in the shared staging path it writes to.
ARCHIVELOG_STAGING_PATH = "/backup/staging/database/archivelog"


def _external_archivelog_status(db: Session) -> dict | None:
    server = db.query(Server).filter(Server.role == "db", Server.enabled == True).first()  # noqa: E712
    if not server:
        return None
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        return None
    try:
        with ssh_from_server(server, cred) as ssh:
            r = ssh.run(
                f'LATEST=$(ls -t {ARCHIVELOG_STAGING_PATH}/*.arc 2>/dev/null | head -1); '
                f'if [ -n "$LATEST" ]; then stat -c %Y "$LATEST"; else echo 0; fi; '
                f'find {ARCHIVELOG_STAGING_PATH} -name "*.arc" 2>/dev/null | wc -l; '
                f'du -sb {ARCHIVELOG_STAGING_PATH} 2>/dev/null | cut -f1',
                timeout=10,
            )
        lines = r.stdout.strip().split("\n")
        latest_epoch = int(lines[0]) if lines[0].isdigit() else 0
        file_count = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0
        total_bytes = int(lines[2]) if len(lines) > 2 and lines[2].isdigit() else 0
        if latest_epoch == 0:
            return None
        return {
            "latest_file_at": datetime.utcfromtimestamp(latest_epoch).isoformat(),
            "file_count": file_count,
            "total_size_bytes": total_bytes,
            "source": "external_cron",
            "staging_path": ARCHIVELOG_STAGING_PATH,
        }
    except Exception:
        return None


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    jobs_7d = db.query(BackupJob).filter(BackupJob.created_at >= last_7).all()
    jobs_30d_count = db.query(BackupJob).filter(BackupJob.created_at >= last_30).count()
    success_7d = sum(1 for j in jobs_7d if j.status == "success")
    failed_7d = sum(1 for j in jobs_7d if j.status == "failed")
    running_now = db.query(BackupJob).filter(BackupJob.status == "running").count()

    last_full = (
        db.query(BackupJob)
        .filter(BackupJob.job_type == "online_full", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc())
        .first()
    )
    last_archlog = (
        db.query(BackupJob)
        .filter(BackupJob.job_type == "archivelog", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc())
        .first()
    )
    last_app = (
        db.query(BackupJob)
        .filter(BackupJob.job_type == "app_fs", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc())
        .first()
    )

    archivelog_external = _external_archivelog_status(db)
    last_archlog_at = last_archlog.finished_at if last_archlog else None
    if archivelog_external:
        ext_at = datetime.fromisoformat(archivelog_external["latest_file_at"])
        if not last_archlog_at or ext_at > last_archlog_at:
            last_archlog_at = ext_at

    rpo_minutes = None
    if last_archlog_at:
        rpo_minutes = int((now - last_archlog_at).total_seconds() / 60)

    warnings = []
    if not last_full:
        warnings.append({"level": "high", "msg": "No successful full backup recorded yet"})
    elif (now - last_full.finished_at).days > 7:
        warnings.append({"level": "high", "msg": "Last full backup was >7 days ago"})
    if not last_app:
        warnings.append({"level": "critical", "msg": "No app backup recorded yet — high risk"})
    elif (now - last_app.finished_at).days > 30:
        warnings.append({"level": "critical", "msg": "Last app backup was >30 days ago"})
    if rpo_minutes is not None and rpo_minutes > 1440:
        warnings.append({"level": "high", "msg": f"RPO {rpo_minutes // 60} hours — archivelog behind"})

    return {
        "last_full_backup": last_full.finished_at.isoformat() if last_full else None,
        "last_archlog_backup": last_archlog_at.isoformat() if last_archlog_at else None,
        "archivelog_external": archivelog_external,
        "last_app_backup": last_app.finished_at.isoformat() if last_app else None,
        "rpo_minutes": rpo_minutes,
        "success_7d": success_7d,
        "failed_7d": failed_7d,
        "running_now": running_now,
        "jobs_30d": jobs_30d_count,
        "warnings": warnings,
    }


@router.get("/disk-space")
def disk_space(db: Session = Depends(get_db)):
    results = []
    servers = db.query(Server).filter(Server.enabled == True).all()  # noqa: E712
    for s in servers:
        if s.role not in ("db", "app", "dev"):
            continue
        cred = db.query(Credential).filter(
            Credential.server_id == s.id,
            Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        if not cred:
            results.append({"server": s.name, "host": s.host, "role": s.role, "error": "No SSH credential"})
            continue
        try:
            with ssh_from_server(s, cred) as ssh:
                r = ssh.run("df -h -B 1G | tail -n +2", timeout=15)
                mounts = []
                for line in r.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) < 6:
                        continue
                    fs, size, used, avail, pct, mp = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                    mounts.append({
                        "filesystem": fs, "size_gb": size.rstrip("G"), "used_gb": used.rstrip("G"),
                        "avail_gb": avail.rstrip("G"), "use_percent": int(pct.rstrip("%")), "mount_point": mp,
                    })
                results.append({"server": s.name, "host": s.host, "role": s.role, "mounts": mounts})
        except Exception as e:
            results.append({"server": s.name, "host": s.host, "role": s.role, "error": str(e)})
    return {"results": results, "fetched_at": datetime.utcnow().isoformat()}


# ============================================================
# Servers & Credentials
# ============================================================

@router.get("/servers")
def list_servers(db: Session = Depends(get_db)):
    rows = db.query(Server).order_by(Server.role, Server.name).all()
    return [_serialize_server(s) for s in rows]


@router.post("/servers")
def upsert_server(payload: ServerIn, db: Session = Depends(get_db)):
    s = db.query(Server).filter(Server.name == payload.name).first()
    data = payload.model_dump()
    if not s:
        s = Server(**data)
        db.add(s)
    else:
        for k, v in data.items():
            setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return _serialize_server(s)


@router.delete("/servers/{server_id}")
def delete_server(server_id: int, db: Session = Depends(get_db)):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"deleted": True}


@router.post("/servers/credentials")
def upsert_credential(payload: CredentialIn, db: Session = Depends(get_db)):
    enc_secret = vault.encrypt(payload.secret)
    enc_pass = vault.encrypt(payload.key_passphrase) if payload.key_passphrase else None

    cred = db.query(Credential).filter(
        Credential.server_id == payload.server_id,
        Credential.cred_type == payload.cred_type,
    ).first()
    if not cred:
        cred = Credential(
            server_id=payload.server_id, cred_type=payload.cred_type, username=payload.username,
            secret_encrypted=enc_secret, key_passphrase_encrypted=enc_pass,
        )
        db.add(cred)
    else:
        cred.username = payload.username
        cred.secret_encrypted = enc_secret
        cred.key_passphrase_encrypted = enc_pass
    db.commit()
    return {"id": cred.id, "status": "saved"}


@router.get("/servers/{server_id}/credentials")
def list_credentials(server_id: int, db: Session = Depends(get_db)):
    """Return credential types only (NEVER decrypt secret)."""
    rows = db.query(Credential).filter(Credential.server_id == server_id).all()
    return [
        {"id": c.id, "cred_type": c.cred_type, "username": c.username,
         "has_passphrase": bool(c.key_passphrase_encrypted)}
        for c in rows
    ]


@router.post("/servers/test-connection")
def test_connection(payload: TestConnectionIn, db: Session = Depends(get_db)):
    s = db.query(Server).filter(Server.id == payload.server_id).first()
    if not s:
        raise HTTPException(404, "Server not found")

    # MinIO has no SSH daemon — it's an S3-compatible HTTP API, so it needs
    # its own client-based check instead of the generic SSH probe below.
    # (Using ssh_from_server here is exactly what produced "Error reading
    # SSH protocol banner": Paramiko tried an SSH handshake against MinIO's
    # HTTP port and got an HTTP response back instead of an SSH banner.)
    if s.role == "minio":
        if not s.endpoint_url or not s.bucket:
            return {"ok": False, "error": "MinIO server is missing endpoint_url/bucket — set it in Setup tab"}
        cred = db.query(Credential).filter(
            Credential.server_id == s.id, Credential.cred_type == "minio",
        ).first()
        if not cred:
            return {"ok": False, "error": "No MinIO credential configured for this server (credential type must be 'MinIO', not SSH)"}
        try:
            client = _minio_client(s, cred)
            exists = client.bucket_exists(s.bucket)
            return {
                "ok": True,
                "output": f"Connected to {s.endpoint_url} — bucket '{s.bucket}' {'exists' if exists else 'does NOT exist yet'}",
                "error": None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    cred = db.query(Credential).filter(
        Credential.server_id == s.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        return {"ok": False, "error": "No SSH credential configured for this server"}
    try:
        with ssh_from_server(s, cred) as ssh:
            r = ssh.run("hostname && uname -a && whoami && echo '---' "
                        "&& df -h /backup 2>/dev/null || true", timeout=15)
            return {"ok": r.ok, "output": r.stdout, "error": r.stderr if not r.ok else None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _serialize_server(s: Server) -> dict:
    return {
        "id": s.id, "name": s.name, "role": s.role,
        "host": s.host, "port": s.port,
        "oracle_sid": s.oracle_sid, "oracle_home": s.oracle_home,
        "apps_base": s.apps_base, "current_fs": s.current_fs,
        "endpoint_url": s.endpoint_url, "bucket": s.bucket, "region": s.region,
        "share_path": s.share_path, "protocol": s.protocol,
        "enabled": s.enabled, "notes": s.notes,
    }


# ============================================================
# Backup operations
# ============================================================

def _minio_sync_params(db: Session, minio_server_id: int) -> dict:
    minio_srv = db.query(Server).filter(Server.id == minio_server_id).first()
    if not minio_srv or minio_srv.role != "minio":
        raise HTTPException(400, "Target server must be a MinIO server")
    if not minio_srv.endpoint_url or not minio_srv.bucket:
        raise HTTPException(400, "MinIO server is missing endpoint_url/bucket — set it in Setup tab")
    minio_cred = db.query(Credential).filter(
        Credential.server_id == minio_srv.id, Credential.cred_type == "minio",
    ).first()
    if not minio_cred:
        raise HTTPException(400, "No MinIO credential configured — set it in Setup tab")
    return {
        "minio_endpoint": minio_srv.endpoint_url,
        "minio_access_key": minio_cred.username,
        "minio_secret_key": vault.decrypt(minio_cred.secret_encrypted),
        "minio_bucket": minio_srv.bucket,
    }


def _synology_sync_params(db: Session, synology_server_id: int) -> dict:
    syn_srv = db.query(Server).filter(Server.id == synology_server_id).first()
    if not syn_srv or syn_srv.role != "synology":
        raise HTTPException(400, "Target server must be a Synology server")
    if not syn_srv.share_path:
        raise HTTPException(400, "Synology server is missing share_path — set it in Setup tab")
    syn_cred = db.query(Credential).filter(
        Credential.server_id == syn_srv.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not syn_cred:
        raise HTTPException(400, "No SSH credential configured for Synology — set it in Setup tab")
    return {
        "synology_host": syn_srv.host,
        "synology_user": syn_cred.username,
        "synology_port": syn_srv.port or 22,
        "synology_share_path": syn_srv.share_path,
    }


def _create_job(db: Session, job_type: str, server_id: int, params: dict) -> BackupJob:
    job = BackupJob(
        job_type=job_type, target_server_id=server_id, status="pending",
        parameters=json.dumps(params), started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _deploy_and_run(job_id: int, bash_script: str, target_dir: str):
    """Background task: SFTP script to server, submit via nohup, update DB."""
    db = SessionLocal()
    job = None
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        server = db.query(Server).filter(Server.id == job.target_server_id).first()
        cred = db.query(Credential).filter(
            Credential.server_id == server.id,
            Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        if not cred:
            raise RuntimeError("No SSH credential for server")

        job.status = "running"
        db.commit()

        with ssh_from_server(server, cred) as ssh:
            script_path = f"/tmp/ebs_backup_job_{job_id}.sh"
            log_path = f"/tmp/ebs_backup_job_{job_id}.log"
            pid_path = f"/tmp/ebs_backup_job_{job_id}.pid"
            ssh.upload_text(bash_script, script_path)
            pid = ssh.submit_background(script_path, log_path, pid_path)

            job.pid = pid
            job.log_path = log_path
            job.output_path = target_dir
            db.commit()
    except Exception as e:
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
    finally:
        db.close()


def _has_spfile(server: Server, cred: Credential) -> bool:
    """RMAN's BACKUP SPFILE errors out (RMAN-06062) if the instance was
    started with a PFILE instead of an SPFILE — check first so that case
    can skip the step instead of failing the whole backup at the last step."""
    try:
        with ssh_from_server(server, cred) as ssh:
            oracle_home = server.oracle_home or settings.ORACLE_HOME
            oracle_sid = server.oracle_sid or settings.ORACLE_SID
            cmd = (
                f"export ORACLE_HOME={oracle_home}; export ORACLE_SID={oracle_sid}; "
                f"export PATH=$ORACLE_HOME/bin:$PATH; sqlplus -s / as sysdba <<'SQLEOF'\n"
                f"SET PAGES 0 FEED OFF VERIFY OFF HEADING OFF\n"
                f"SELECT value FROM v$parameter WHERE name='spfile';\n"
                f"EXIT;\nSQLEOF"
            )
            r = ssh.run(cmd, timeout=20)
            return bool(r.stdout.strip())
    except Exception:
        return True


@router.post("/backup/online")
def trigger_online(payload: BackupOnlineIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server or server.role != "db":
        raise HTTPException(400, "Server is not DB")
    if payload.destination not in ("staging", "minio_direct", "synology_direct"):
        raise HTTPException(400, "Invalid destination")

    job = _create_job(db, payload.job_type, server.id, payload.model_dump())

    if payload.job_type == "online_full":
        sync_kwargs = {}
        if payload.destination == "minio_direct":
            if not payload.minio_server_id:
                raise HTTPException(400, "minio_server_id required for destination=minio_direct")
            sync_kwargs = {"sync_target": "minio", **_minio_sync_params(db, payload.minio_server_id)}
        elif payload.destination == "synology_direct":
            if not payload.synology_server_id:
                raise HTTPException(400, "synology_server_id required for destination=synology_direct")
            sync_kwargs = {"sync_target": "synology", **_synology_sync_params(db, payload.synology_server_id)}

        db_cred = db.query(Credential).filter(
            Credential.server_id == server.id,
            Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        include_spfile = _has_spfile(server, db_cred) if db_cred else True

        bash, target = rman_templates.rman_online_full(
            oracle_home=server.oracle_home or settings.ORACLE_HOME,
            oracle_sid=server.oracle_sid or settings.ORACLE_SID,
            staging_path=settings.BACKUP_STAGING,
            parallelism=payload.parallelism,
            compression=payload.compression,
            include_archivelog=payload.include_archivelog,
            archivelog_delete_input=payload.archivelog_delete_input,
            include_spfile=include_spfile,
            job_id=job.id,
            **sync_kwargs,
        )
    else:
        bash, target = rman_templates.rman_incremental(
            oracle_home=server.oracle_home or settings.ORACLE_HOME,
            oracle_sid=server.oracle_sid or settings.ORACLE_SID,
            staging_path=settings.BACKUP_STAGING,
            level=payload.incremental_level,
            parallelism=payload.parallelism,
            job_id=job.id,
        )

    job.output_path = target
    db.commit()
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {"job_id": job.id, "status": "submitted", "target": target, "destination": payload.destination}


@router.get("/backup/online/preflight/{server_id}")
def online_preflight(server_id: int, db: Session = Depends(get_db)):
    """Read-only check before triggering an online backup: estimated DB size,
    plus connectivity + free space for local staging, MinIO, and Synology."""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server or server.role != "db":
        raise HTTPException(400, "Server is not DB")
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        raise HTTPException(400, "No SSH credential for DB server")

    result = {"db_size_estimate_bytes": None, "staging": None, "minio": None, "synology": None}

    try:
        with ssh_from_server(server, cred) as ssh:
            oracle_home = server.oracle_home or settings.ORACLE_HOME
            oracle_sid = server.oracle_sid or settings.ORACLE_SID
            size_cmd = (
                f"export ORACLE_HOME={oracle_home}; export ORACLE_SID={oracle_sid}; "
                f"export PATH=$ORACLE_HOME/bin:$PATH; sqlplus -s / as sysdba <<'SQLEOF'\n"
                f"SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF\n"
                f"SELECT NVL(SUM(bytes),0) FROM dba_data_files;\n"
                f"EXIT;\nSQLEOF"
            )
            r = ssh.run(size_cmd, timeout=30)
            try:
                result["db_size_estimate_bytes"] = int(float(r.stdout.strip()))
            except ValueError:
                pass

            try:
                r = ssh.run(f"df -B1 {settings.BACKUP_STAGING} | tail -1", timeout=10)
                parts = r.stdout.split()
                result["staging"] = {
                    "connected": True, "total_bytes": int(parts[1]), "used_bytes": int(parts[2]),
                    "available_bytes": int(parts[3]),
                }
            except Exception as e:
                result["staging"] = {"connected": False, "error": str(e)}

            minio_srv = db.query(Server).filter(Server.role == "minio", Server.enabled == True).first()  # noqa: E712
            if minio_srv:
                try:
                    p = _minio_sync_params(db, minio_srv.id)
                    alias = f"preflight{server_id}"
                    url = p["minio_endpoint"] if p["minio_endpoint"].startswith("http") else f"http://{p['minio_endpoint']}"
                    r = ssh.run(
                        f'mc alias set {alias} "{url}" "{p["minio_access_key"]}" "{p["minio_secret_key"]}" '
                        f'--api s3v4 >/dev/null && mc admin info {alias} --json 2>&1',
                        timeout=20,
                    )
                    info = json.loads(r.stdout)
                    drive = info["info"]["servers"][0]["drives"][0]
                    result["minio"] = {
                        "connected": True, "server_id": minio_srv.id, "name": minio_srv.name,
                        "total_bytes": drive["totalspace"], "used_bytes": drive["usedspace"],
                        "available_bytes": drive["availspace"],
                    }
                except Exception as e:
                    result["minio"] = {"connected": False, "server_id": minio_srv.id, "name": minio_srv.name, "error": str(e)}

        synology_srv = db.query(Server).filter(Server.role == "synology", Server.enabled == True).first()  # noqa: E712
        if synology_srv:
            syn_cred = db.query(Credential).filter(
                Credential.server_id == synology_srv.id,
                Credential.cred_type.in_(["ssh_password", "ssh_key"]),
            ).first()
            if not syn_cred:
                result["synology"] = {"connected": False, "server_id": synology_srv.id, "name": synology_srv.name, "error": "No SSH credential configured"}
            else:
                try:
                    with ssh_from_server(synology_srv, syn_cred) as syn_ssh:
                        r = syn_ssh.run(f"df -B1 {synology_srv.share_path} | tail -1", timeout=10)
                    parts = r.stdout.split()
                    result["synology"] = {
                        "connected": True, "server_id": synology_srv.id, "name": synology_srv.name,
                        "total_bytes": int(parts[1]), "used_bytes": int(parts[2]), "available_bytes": int(parts[3]),
                    }
                except Exception as e:
                    result["synology"] = {"connected": False, "server_id": synology_srv.id, "name": synology_srv.name, "error": str(e)}
    except Exception as e:
        raise HTTPException(500, f"Preflight check failed: {e}")

    return result


def _sync_existing_backup(db: Session, bg: BackgroundTasks, payload: SyncBackupIn, target: str):
    src_job = db.query(BackupJob).filter(BackupJob.id == payload.job_id).first()
    if not src_job or not src_job.output_path:
        raise HTTPException(404, "Source job not found or has no output")
    if src_job.status != "success":
        raise HTTPException(400, "Source job did not finish successfully")
    server = db.query(Server).filter(Server.id == src_job.target_server_id).first()

    sync_job = _create_job(db, f"db_sync_{target}", server.id,
                            {"source_job_id": src_job.id, "target_server_id": payload.target_server_id})
    manifest_dir = f"/tmp/ebs_sync_job_{sync_job.id}"
    backup_name = src_job.output_path.rstrip("/").split("/")[-1]

    if target == "minio":
        p = _minio_sync_params(db, payload.target_server_id)
        alias = f"syncnow{sync_job.id}"
        url = p["minio_endpoint"] if p["minio_endpoint"].startswith("http") else f"http://{p['minio_endpoint']}"
        dest = f"{alias}/{p['minio_bucket']}/db-tier/{backup_name}"
        transfer_cmd = (
            f'mc alias set {alias} "{url}" "{p["minio_access_key"]}" "{p["minio_secret_key"]}" --api s3v4 >/dev/null\n'
            f'mc mirror "{src_job.output_path}" {dest} 2>&1 | tail -30'
        )
        dest_desc = dest
    else:
        p = _synology_sync_params(db, payload.target_server_id)
        ssh_opts = f"-p {p['synology_port']} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
        dest_dir = f"{p['synology_share_path']}/database/full/{backup_name}"
        transfer_cmd = (
            f'ssh {ssh_opts} {p["synology_user"]}@{p["synology_host"]} "mkdir -p {dest_dir}"\n'
            f'tar cf - -C "{src_job.output_path}" . | ssh {ssh_opts} {p["synology_user"]}@{p["synology_host"]} "cd {dest_dir} && tar xf -"'
        )
        dest_desc = dest_dir

    script = f"""#!/bin/bash
set -e
mkdir -p "{manifest_dir}"
echo "[$(date)] === SYNC job #{src_job.id} output (job #{sync_job.id}) TO {target.upper()} ==="
{transfer_cmd}
echo "[$(date)] === SYNC SUCCESS: {dest_desc} ==="
cat > "{manifest_dir}/manifest.json" << MANIFEST
{{"job_id": {sync_job.id}, "job_type": "db_sync_{target}", "status": "success",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')", "destination": "{dest_desc}"}}
MANIFEST
exit 0
"""
    sync_job.output_path = manifest_dir
    db.commit()
    bg.add_task(_deploy_and_run, sync_job.id, script, manifest_dir)
    return {"job_id": sync_job.id, "status": "submitted", "destination": dest_desc}


@router.post("/backup/online/sync-minio")
def sync_online_to_minio(payload: SyncBackupIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    return _sync_existing_backup(db, bg, payload, "minio")


@router.post("/backup/online/sync-synology")
def sync_online_to_synology(payload: SyncBackupIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    return _sync_existing_backup(db, bg, payload, "synology")


@router.post("/backup/archivelog")
def trigger_archivelog(payload: BackupArchlogIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server:
        raise HTTPException(404)
    job = _create_job(db, "archivelog", server.id, payload.model_dump())
    bash, target = rman_templates.rman_archivelog(
        oracle_home=server.oracle_home or settings.ORACLE_HOME,
        oracle_sid=server.oracle_sid or settings.ORACLE_SID,
        staging_path=settings.BACKUP_STAGING,
        delete_input=payload.delete_input,
        job_id=job.id,
    )
    job.output_path = target
    db.commit()
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {"job_id": job.id, "status": "submitted", "target": target}


@router.post("/backup/offline")
def trigger_offline(payload: BackupOfflineIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    if payload.confirm_token != "SHUTDOWN_CONFIRMED":
        raise HTTPException(400, "Shutdown confirmation required (invalid confirm_token)")
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server:
        raise HTTPException(404)
    job = _create_job(db, "offline_cold", server.id, payload.model_dump())
    bash, target = rman_templates.cold_backup(
        oracle_home=server.oracle_home or settings.ORACLE_HOME,
        oracle_sid=server.oracle_sid or settings.ORACLE_SID,
        staging_path=settings.BACKUP_STAGING,
        data_paths=payload.data_paths,
        apps_base=server.apps_base if payload.stop_apps_first else None,
        fs_active=server.current_fs or "fs2",
        job_id=job.id,
    )
    job.output_path = target
    db.commit()
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {"job_id": job.id, "status": "submitted", "target": target}


@router.post("/backup/app")
def trigger_app(payload: BackupAppIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server or server.role != "app":
        raise HTTPException(400, "Server is not App")

    remote_host = None
    remote_user = None
    remote_port = 22
    if payload.remote_target_server_id:
        remote_srv = db.query(Server).filter(Server.id == payload.remote_target_server_id).first()
        if not remote_srv:
            raise HTTPException(400, "Remote target server not found")
        if remote_srv.role != "db":
            raise HTTPException(400, "Remote target must be DB server (to write to its /backup)")
        rcred = db.query(Credential).filter(
            Credential.server_id == remote_srv.id,
            Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        if not rcred:
            raise HTTPException(400, "DB target server has no SSH credential. Setup credential first in Setup tab.")
        remote_host = remote_srv.host
        remote_user = rcred.username
        remote_port = remote_srv.port or 22

    job = _create_job(db, "app_fs", server.id, payload.model_dump())
    bash, target = rman_templates.app_backup(
        apps_base=server.apps_base or settings.APPS_BASE,
        fs_to_backup=payload.fs_target,
        fs_ne_path=f"{server.apps_base or settings.APPS_BASE}/fs_ne",
        staging_path=settings.BACKUP_STAGING,
        include_inst_top=payload.include_inst_top,
        job_id=job.id,
        remote_host=remote_host,
        remote_user=remote_user,
        remote_port=remote_port,
    )
    job.output_path = target
    db.commit()
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {
        "job_id": job.id, "status": "submitted", "target": target,
        "mode": "remote_stream" if remote_host else "local", "remote_host": remote_host,
    }


def build_archivelog_sync_job(db: Session, payload: ArchiveLogSyncIn) -> tuple[BackupJob, str, str]:
    """Shared by the manual-trigger endpoint below and the schedule poller
    (services/ebs_backup/scheduler.py) so both paths build the exact same script."""
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server or server.role != "db":
        raise HTTPException(400, "Source server must be a DB server")

    minio_srv = db.query(Server).filter(Server.id == payload.minio_server_id).first()
    if not minio_srv or minio_srv.role != "minio":
        raise HTTPException(400, "Target server must be a MinIO server")
    if not minio_srv.endpoint_url or not minio_srv.bucket:
        raise HTTPException(400, "MinIO server is missing endpoint_url/bucket — set it in Setup tab")

    minio_cred = db.query(Credential).filter(
        Credential.server_id == minio_srv.id, Credential.cred_type == "minio",
    ).first()
    if not minio_cred:
        raise HTTPException(400, "No MinIO credential configured — set it in Setup tab")

    job = _create_job(db, "archivelog_sync", server.id, payload.model_dump())
    bash, target = rman_templates.archive_log_sync(
        source_dir=payload.source_dir,
        local_staging=payload.local_staging,
        minio_endpoint=minio_srv.endpoint_url,
        minio_access_key=minio_cred.username,
        minio_secret_key=vault.decrypt(minio_cred.secret_encrypted),
        minio_bucket=minio_srv.bucket,
        minio_prefix=payload.minio_prefix,
        retention_days=payload.retention_days,
        job_id=job.id,
    )
    job.output_path = target
    db.commit()
    return job, bash, target


@router.post("/backup/archivelog-sync")
def trigger_archivelog_sync(payload: ArchiveLogSyncIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    job, bash, target = build_archivelog_sync_job(db, payload)
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {"job_id": job.id, "status": "submitted", "target": target}


# ============================================================
# Jobs — history, live log, cancel/pause/resume
# ============================================================

PROGRESS_TOTAL_RE = re.compile(r"\[PROGRESS_TOTAL_BYTES\]\s+(\d+)")


def _resolve_remote_target(db: Session, job: BackupJob, source_server_id: int):
    params = json.loads(job.parameters) if job.parameters else {}
    remote_id = params.get("remote_target_server_id")
    if not remote_id or remote_id == source_server_id:
        return None, None
    remote_srv = db.query(Server).filter(Server.id == remote_id).first()
    if not remote_srv:
        return None, None
    remote_cred = db.query(Credential).filter(
        Credential.server_id == remote_id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not remote_cred:
        return None, None
    return remote_srv, remote_cred


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), limit: int = 50, status: str | None = None, job_type: str | None = None):
    q = db.query(BackupJob)
    if status:
        q = q.filter(BackupJob.status == status)
    if job_type:
        q = q.filter(BackupJob.job_type == job_type)
    rows = q.order_by(BackupJob.id.desc()).limit(limit).all()
    return [_serialize_job(j) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, tail_lines: int = 200, list_files: bool = False, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise HTTPException(404)

    live_log = ""
    is_alive = False
    progress_total_bytes = None
    progress_current_bytes = None
    output_files = None

    if job.status in ("running", "paused") and job.pid and job.log_path:
        try:
            server = db.query(Server).filter(Server.id == job.target_server_id).first()
            cred = db.query(Credential).filter(
                Credential.server_id == server.id,
                Credential.cred_type.in_(["ssh_password", "ssh_key"]),
            ).first()
            remote_srv, remote_cred = _resolve_remote_target(db, job, server.id)

            with ssh_from_server(server, cred) as ssh:
                is_alive = ssh.is_pid_alive(job.pid)
                live_log = ssh.tail_log(job.log_path, tail_lines)

                m = PROGRESS_TOTAL_RE.search(live_log)
                if m:
                    progress_total_bytes = int(m.group(1))

                if is_alive and job.output_path:
                    du_cmd = f'du -sb "{job.output_path}" 2>/dev/null | cut -f1 || echo 0'
                    try:
                        if remote_srv and remote_cred:
                            with ssh_from_server(remote_srv, remote_cred) as ssh2:
                                r = ssh2.run(du_cmd, timeout=10)
                        else:
                            r = ssh.run(du_cmd, timeout=10)
                        progress_current_bytes = int(r.stdout.strip() or 0)
                    except Exception:
                        progress_current_bytes = None

                if not is_alive:
                    manifest_path = f"{job.output_path}/manifest.json"
                    if remote_srv and remote_cred:
                        with ssh_from_server(remote_srv, remote_cred) as ssh2:
                            r = ssh2.run(f"cat {manifest_path} 2>/dev/null || echo '{{}}'")
                    else:
                        r = ssh.run(f"cat {manifest_path} 2>/dev/null || echo '{{}}'")

                    data = {}
                    try:
                        data = json.loads(r.stdout.strip())
                    except Exception:
                        data = {}

                    job.status = data.get("status") or "failed"
                    if data.get("total_size_bytes"):
                        job.total_size_bytes = data["total_size_bytes"]
                    if data.get("file_count"):
                        job.file_count = data["file_count"]
                    if not data.get("status"):
                        job.error_message = job.error_message or (
                            "Process ended without writing manifest.json — check log for the actual error."
                        )
                    job.finished_at = datetime.utcnow()
                    if job.started_at:
                        job.duration_sec = int((job.finished_at - job.started_at).total_seconds())
                    db.commit()
        except Exception as e:
            live_log = f"[Error reading log: {e}]"

    if list_files and job.output_path and job.status in ("success", "failed"):
        try:
            server = db.query(Server).filter(Server.id == job.target_server_id).first()
            cred = db.query(Credential).filter(
                Credential.server_id == server.id,
                Credential.cred_type.in_(["ssh_password", "ssh_key"]),
            ).first()
            remote_srv, remote_cred = _resolve_remote_target(db, job, server.id)
            list_cmd = f'ls -la "{job.output_path}" 2>/dev/null | tail -n +2'
            with ssh_from_server(remote_srv or server, remote_cred or cred) as ssh:
                r = ssh.run(list_cmd, timeout=15)
            output_files = []
            for line in r.stdout.strip().splitlines():
                parts = line.split(None, 8)
                if len(parts) < 9 or parts[-1] in (".", ".."):
                    continue
                output_files.append({"name": parts[-1], "size_bytes": int(parts[4])})
        except Exception:
            output_files = None

    progress_percent = None
    if progress_total_bytes and progress_current_bytes is not None:
        progress_percent = min(99.0, round(progress_current_bytes / progress_total_bytes * 100, 1))

    return {
        **_serialize_job(job),
        "pid_alive": is_alive,
        "live_log": live_log,
        "parameters_parsed": json.loads(job.parameters) if job.parameters else {},
        "progress_total_bytes": progress_total_bytes,
        "progress_current_bytes": progress_current_bytes,
        "progress_percent": progress_percent,
        "output_files": output_files,
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job or not job.pid:
        raise HTTPException(404, "Job or PID not found")
    if job.status not in ("running", "paused"):
        raise HTTPException(400, f"Cannot cancel a job in status '{job.status}'")

    server = db.query(Server).filter(Server.id == job.target_server_id).first()
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()

    with ssh_from_server(server, cred) as ssh:
        if job.status == "paused":
            ssh.resume_pid(job.pid)
        killed = ssh.kill_pid(job.pid, sig=15)

    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    return {"job_id": job_id, "killed": killed}


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job or not job.pid:
        raise HTTPException(404, "Job or PID not found")
    if job.status != "running":
        raise HTTPException(400, f"Cannot pause a job in status '{job.status}'")

    server = db.query(Server).filter(Server.id == job.target_server_id).first()
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()

    with ssh_from_server(server, cred) as ssh:
        if not ssh.is_pid_alive(job.pid):
            raise HTTPException(409, "Process is no longer running — refresh job status")
        paused = ssh.pause_pid(job.pid)
    if not paused:
        raise HTTPException(500, "Failed to pause process on server")

    job.status = "paused"
    db.commit()
    return {"job_id": job_id, "status": "paused"}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job or not job.pid:
        raise HTTPException(404, "Job or PID not found")
    if job.status != "paused":
        raise HTTPException(400, f"Cannot resume a job in status '{job.status}'")

    server = db.query(Server).filter(Server.id == job.target_server_id).first()
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()

    with ssh_from_server(server, cred) as ssh:
        resumed = ssh.resume_pid(job.pid)
    if not resumed:
        raise HTTPException(500, "Failed to resume process on server")

    job.status = "running"
    db.commit()
    return {"job_id": job_id, "status": "running"}


@router.post("/jobs/{job_id}/delete-output")
def delete_job_output(job_id: int, db: Session = Depends(get_db)):
    """Delete a finished job's local staging copy on demand. Never runs
    automatically; always an explicit user action."""
    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("success", "failed", "cancelled"):
        raise HTTPException(400, f"Cannot delete output for a job in status '{job.status}'")
    if not job.output_path or not job.output_path.startswith(settings.BACKUP_STAGING):
        raise HTTPException(400, "Job has no deletable staging output path")

    server = db.query(Server).filter(Server.id == job.target_server_id).first()
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        raise HTTPException(400, "No SSH credential for server")

    with ssh_from_server(server, cred) as ssh:
        r = ssh.run(f'rm -rf "{job.output_path}" && echo OK || echo FAIL', timeout=30)
    if "OK" not in r.stdout:
        raise HTTPException(500, f"Delete failed: {r.stdout} {r.stderr}")

    return {"job_id": job_id, "deleted_path": job.output_path}


def _serialize_job(j: BackupJob) -> dict:
    return {
        "id": j.id, "job_type": j.job_type, "status": j.status,
        "target_server_id": j.target_server_id, "triggered_by": j.triggered_by,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "duration_sec": j.duration_sec, "output_path": j.output_path, "log_path": j.log_path,
        "pid": j.pid, "total_size_bytes": j.total_size_bytes, "file_count": j.file_count,
        "rman_tag": j.rman_tag, "parameters": j.parameters, "error_message": j.error_message,
    }


# ============================================================
# Schedules — CRUD
# ============================================================

def _next_run(cron_expr: str) -> datetime | None:
    if not HAS_CRONITER:
        return None
    try:
        return croniter(cron_expr, datetime.utcnow()).get_next(datetime)
    except Exception:
        return None


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db)):
    rows = db.query(Schedule).order_by(Schedule.name).all()
    return [_serialize_schedule(s) for s in rows]


@router.post("/schedules")
def upsert_schedule(payload: ScheduleIn, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter(Schedule.name == payload.name).first()
    data = payload.model_dump()
    data["parameters"] = json.dumps(data.pop("parameters", {}))
    if not s:
        s = Schedule(**data)
        db.add(s)
    else:
        for k, v in data.items():
            setattr(s, k, v)
    s.next_run_at = _next_run(s.cron_expression)
    db.commit()
    db.refresh(s)
    return _serialize_schedule(s)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"deleted": True}


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404)
    s.enabled = not s.enabled
    if s.enabled:
        s.next_run_at = _next_run(s.cron_expression)
    db.commit()
    return _serialize_schedule(s)


def _serialize_schedule(s: Schedule) -> dict:
    return {
        "id": s.id, "name": s.name, "job_type": s.job_type, "cron_expression": s.cron_expression,
        "target_server_id": s.target_server_id,
        "parameters": json.loads(s.parameters) if s.parameters else {},
        "enabled": s.enabled,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_run_status": s.last_run_status, "last_run_job_id": s.last_run_job_id,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
    }


# ============================================================
# SSH Key Setup wizard
# ============================================================

class GenerateKeyIn(BaseModel):
    source_server_id: int
    key_type: str = "rsa"
    key_bits: int = 4096
    overwrite: bool = False


class CopyIdIn(BaseModel):
    source_server_id: int
    target_server_id: int
    target_username: str
    target_password: str
    target_port: Optional[int] = None


class TestSetupIn(BaseModel):
    source_server_id: int
    target_server_id: int
    target_username: str


def _get_ssh_from_id(server_id: int, db: Session) -> SSHExecutor:
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(404, f"Server {server_id} not found")
    cred = db.query(Credential).filter(
        Credential.server_id == server.id,
        Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        raise HTTPException(400, f"Server {server.name} has no SSH credential")
    return ssh_from_server(server, cred)


@router.post("/ssh-setup/generate-key")
def generate_key(payload: GenerateKeyIn, db: Session = Depends(get_db)):
    """Generate ~/.ssh/id_rsa (or id_ed25519) on source server. Returns public
    key for manual copy to destination."""
    src = db.query(Server).filter(Server.id == payload.source_server_id).first()
    if not src:
        raise HTTPException(404, "Source server not found")

    key_name = "id_rsa" if payload.key_type == "rsa" else "id_ed25519"

    try:
        with _get_ssh_from_id(src.id, db) as ssh:
            ssh.run("mkdir -p ~/.ssh && chmod 700 ~/.ssh")

            r = ssh.run(f"test -f ~/.ssh/{key_name} && echo EXIST || echo NOT_EXIST", timeout=5)
            key_exists = "EXIST" in r.stdout

            if key_exists and not payload.overwrite:
                pub = ssh.run(f"cat ~/.ssh/{key_name}.pub").stdout.strip()
                user_at_host = ssh.run("whoami; hostname").stdout.strip().replace("\n", "@")
                return {
                    "status": "already_exists",
                    "message": f"SSH key {key_name} already exists on {user_at_host}. Use overwrite=true to regenerate.",
                    "public_key": pub, "key_path_remote": f"~/.ssh/{key_name}",
                }

            if payload.key_type == "rsa":
                gen_cmd = (
                    f'ssh-keygen -t rsa -b {payload.key_bits} '
                    f'-f ~/.ssh/{key_name} -N "" -C "ckdo-dashboard-ebs-backup-$(date +%Y%m%d)"'
                )
            else:
                gen_cmd = (
                    f'ssh-keygen -t ed25519 '
                    f'-f ~/.ssh/{key_name} -N "" -C "ckdo-dashboard-ebs-backup-$(date +%Y%m%d)"'
                )

            if payload.overwrite:
                ssh.run(f"rm -f ~/.ssh/{key_name} ~/.ssh/{key_name}.pub")

            r = ssh.run(gen_cmd, timeout=30)
            if not r.ok:
                raise HTTPException(500, f"ssh-keygen failed: {r.stderr}")

            pub = ssh.run(f"cat ~/.ssh/{key_name}.pub").stdout.strip()
            user_at_host = ssh.run("whoami; hostname").stdout.strip().replace("\n", "@")

            return {
                "status": "generated",
                "message": f"New SSH key generated on {user_at_host}",
                "public_key": pub, "key_path_remote": f"~/.ssh/{key_name}",
                "manual_copy_command": (
                    f'# Manual copy to target server (run from source):\n'
                    f'echo "{pub}" | ssh USER@TARGET_HOST '
                    f'"mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
                    f'cat >> ~/.ssh/authorized_keys && '
                    f'chmod 600 ~/.ssh/authorized_keys"'
                ),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")


@router.post("/ssh-setup/copy-id")
def copy_id(payload: CopyIdIn, db: Session = Depends(get_db)):
    """Equivalent to `ssh-copy-id`: read the source server's public key, log
    into the target with a one-time password, append the key to
    authorized_keys. The target password is never stored."""
    src = db.query(Server).filter(Server.id == payload.source_server_id).first()
    tgt = db.query(Server).filter(Server.id == payload.target_server_id).first()
    if not src or not tgt:
        raise HTTPException(404, "Source or target server not found")

    if not payload.target_password:
        raise HTTPException(400, "Target password is empty")

    pub_key = None
    src_user = None
    try:
        with _get_ssh_from_id(src.id, db) as ssh:
            r = ssh.run(
                "cat ~/.ssh/id_rsa.pub 2>/dev/null || "
                "cat ~/.ssh/id_ed25519.pub 2>/dev/null || "
                "echo NO_KEY"
            )
            pub_key = r.stdout.strip()
            if "NO_KEY" in pub_key or not pub_key:
                raise HTTPException(400, "No public key exists on source server. Run generate-key first.")
            src_user_host = ssh.run("whoami && hostname").stdout.strip()
            src_user = src_user_host.split("\n")[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error reading key from source: {e}")

    tgt_port = payload.target_port or tgt.port or 22
    try:
        with SSHExecutor(
            host=tgt.host, port=tgt_port, username=payload.target_username, password=payload.target_password,
        ) as tssh:
            setup_cmd = (
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                "touch ~/.ssh/authorized_keys && "
                "chmod 600 ~/.ssh/authorized_keys"
            )
            r = tssh.run(setup_cmd, timeout=10)
            if not r.ok:
                raise HTTPException(500, f"Setup .ssh dir failed: {r.stderr}")

            key_signature = " ".join(pub_key.split()[:2])
            check_cmd = (
                f"grep -F '{key_signature}' ~/.ssh/authorized_keys >/dev/null "
                f"&& echo EXIST || echo NEW"
            )
            r = tssh.run(check_cmd, timeout=10)
            already_exists = "EXIST" in r.stdout

            if already_exists:
                tgt_host = tssh.run("hostname").stdout.strip()
                return {
                    "status": "already_authorized",
                    "message": (
                        f"Key from {src_user}@{src.host} already exists in "
                        f"authorized_keys {payload.target_username}@{tgt_host}. Skipped."
                    ),
                }

            append_cmd = (
                f"cat >> ~/.ssh/authorized_keys << 'PUBKEY_EOF'\n"
                f"{pub_key}\n"
                f"PUBKEY_EOF"
            )
            r = tssh.run(append_cmd, timeout=10)
            if not r.ok:
                raise HTTPException(500, f"Append key failed: {r.stderr}")

            tssh.run("chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh")
            tgt_user_host = tssh.run("whoami && hostname").stdout.strip()
            tgt_user = tgt_user_host.split("\n")[0]
            tgt_host_name = tgt_user_host.split("\n")[1] if "\n" in tgt_user_host else tgt.host

            return {
                "status": "key_installed",
                "message": f"Public key from {src_user}@{src.host} successfully added to {tgt_user}@{tgt_host_name}",
                "source": f"{src_user}@{src.host}", "target": f"{tgt_user}@{tgt_host_name}",
                "next_step": "Run /ssh-setup/test endpoint for verification.",
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Login to target failed (wrong password?): {e}")


@router.post("/ssh-setup/test")
def test_setup(payload: TestSetupIn, db: Session = Depends(get_db)):
    """Verify: from source server, can SSH to target user@host without password."""
    src = db.query(Server).filter(Server.id == payload.source_server_id).first()
    tgt = db.query(Server).filter(Server.id == payload.target_server_id).first()
    if not src or not tgt:
        raise HTTPException(404, "Server not found")

    try:
        with _get_ssh_from_id(src.id, db) as ssh:
            test_cmd = (
                f"ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "
                f"-o ConnectTimeout=10 "
                f"{payload.target_username}@{tgt.host} "
                f"'echo SSH_OK_$(whoami)_$(hostname)'"
            )
            r = ssh.run(test_cmd, timeout=20)
            if r.ok and "SSH_OK_" in r.stdout:
                return {"ok": True, "message": "SSH passwordless works", "output": r.stdout.strip()}
            else:
                return {
                    "ok": False, "message": "SSH passwordless FAILED", "stdout": r.stdout, "stderr": r.stderr,
                    "hint": (
                        "Check: (1) key already in target authorized_keys? "
                        "(2) permissions on ~/.ssh and ~/.ssh/authorized_keys on target correct? "
                        "(3) sshd on target allows PubkeyAuthentication?"
                    ),
                }
    except Exception as e:
        raise HTTPException(500, f"Error testing: {e}")


# ============================================================
# Storage — MinIO / Synology browser
# ============================================================

def _minio_client(minio_srv: Server, cred: Credential) -> Minio:
    endpoint = minio_srv.endpoint_url.replace("https://", "").replace("http://", "")
    secure = minio_srv.endpoint_url.startswith("https")
    return Minio(endpoint, access_key=cred.username, secret_key=vault.decrypt(cred.secret_encrypted), secure=secure)


def _get_minio_server(db: Session, server_id: int) -> tuple[Server, Credential]:
    srv = db.query(Server).filter(Server.id == server_id, Server.role == "minio").first()
    if not srv:
        raise HTTPException(404, "MinIO server not found")
    cred = db.query(Credential).filter(Credential.server_id == srv.id, Credential.cred_type == "minio").first()
    if not cred:
        raise HTTPException(400, "No MinIO credential configured — set it in Setup tab")
    return srv, cred


def _get_synology_server(db: Session, server_id: int) -> tuple[Server, Credential]:
    srv = db.query(Server).filter(Server.id == server_id, Server.role == "synology").first()
    if not srv:
        raise HTTPException(404, "Synology server not found")
    cred = db.query(Credential).filter(
        Credential.server_id == srv.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        raise HTTPException(400, "No SSH credential configured — set it in Setup tab")
    return srv, cred


@router.get("/storage/minio/{server_id}/usage")
def minio_usage(server_id: int, db: Session = Depends(get_db)):
    minio_srv, _ = _get_minio_server(db, server_id)
    db_server = db.query(Server).filter(Server.role == "db", Server.enabled == True).first()  # noqa: E712
    if not db_server:
        return {"connected": False, "error": "No DB server registered to relay the capacity check through"}
    relay_cred = db.query(Credential).filter(
        Credential.server_id == db_server.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not relay_cred:
        return {"connected": False, "error": "DB server has no SSH credential"}

    p = _minio_sync_params(db, minio_srv.id)
    alias = f"usage{server_id}"
    url = p["minio_endpoint"] if p["minio_endpoint"].startswith("http") else f"http://{p['minio_endpoint']}"
    try:
        with ssh_from_server(db_server, relay_cred) as ssh:
            r = ssh.run(
                f'mc alias set {alias} "{url}" "{p["minio_access_key"]}" "{p["minio_secret_key"]}" '
                f'--api s3v4 >/dev/null && mc admin info {alias} --json 2>&1',
                timeout=20,
            )
        info = json.loads(r.stdout)
        drive = info["info"]["servers"][0]["drives"][0]
        return {
            "connected": True, "total_bytes": drive["totalspace"], "used_bytes": drive["usedspace"],
            "available_bytes": drive["availspace"],
            "bucket_objects": info["info"].get("objects", {}).get("count"),
            "bucket_usage_bytes": info["info"].get("usage", {}).get("size"),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.get("/storage/minio/{server_id}/list")
def minio_list(server_id: int, prefix: str = "", db: Session = Depends(get_db)):
    minio_srv, cred = _get_minio_server(db, server_id)
    client = _minio_client(minio_srv, cred)
    try:
        items = []
        for obj in client.list_objects(minio_srv.bucket, prefix=prefix, recursive=False):
            items.append({
                "name": obj.object_name.rstrip("/").split("/")[-1] or obj.object_name,
                "key": obj.object_name, "is_dir": obj.is_dir,
                "size_bytes": None if obj.is_dir else obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
        items.sort(key=lambda x: (not x["is_dir"], x["name"]))
        return {"bucket": minio_srv.bucket, "prefix": prefix, "items": items}
    except Exception as e:
        raise HTTPException(500, f"Failed to list MinIO objects: {e}")


@router.post("/storage/minio/{server_id}/delete")
def minio_delete(server_id: int, payload: dict, db: Session = Depends(get_db)):
    keys = payload.get("keys") or []
    if not keys:
        raise HTTPException(400, "No keys provided")
    minio_srv, cred = _get_minio_server(db, server_id)
    client = _minio_client(minio_srv, cred)

    expanded = []
    for k in keys:
        if k.endswith("/"):
            expanded.extend(o.object_name for o in client.list_objects(minio_srv.bucket, prefix=k, recursive=True))
        else:
            expanded.append(k)
    if not expanded:
        return {"deleted": 0}

    errors = list(client.remove_objects(minio_srv.bucket, [DeleteObject(k) for k in expanded]))
    if errors:
        raise HTTPException(500, f"Some deletes failed: {[str(e) for e in errors]}")
    return {"deleted": len(expanded)}


@router.get("/storage/synology/{server_id}/usage")
def synology_usage(server_id: int, db: Session = Depends(get_db)):
    syn_srv, cred = _get_synology_server(db, server_id)
    try:
        with ssh_from_server(syn_srv, cred) as ssh:
            r = ssh.run(f'df -B1 "{syn_srv.share_path}" | tail -1', timeout=10)
        parts = r.stdout.split()
        return {"connected": True, "total_bytes": int(parts[1]), "used_bytes": int(parts[2]), "available_bytes": int(parts[3])}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _synology_resolve_path(ssh, share_path: str, rel_path: str) -> str:
    """Resolve rel_path under share_path and refuse anything that escapes it
    (via .. or symlinks) — this backs a delete endpoint, so it must be strict."""
    target = f"{share_path.rstrip('/')}/{rel_path.lstrip('/')}" if rel_path else share_path
    r = ssh.run(f'realpath "{target}" 2>&1', timeout=10)
    real = r.stdout.strip()
    share_real = ssh.run(f'realpath "{share_path}" 2>&1', timeout=10).stdout.strip()
    if not real or not (real == share_real or real.startswith(share_real.rstrip("/") + "/")):
        raise HTTPException(400, f"Path escapes share root: {rel_path}")
    return real


@router.get("/storage/synology/{server_id}/list")
def synology_list(server_id: int, path: str = "", db: Session = Depends(get_db)):
    syn_srv, cred = _get_synology_server(db, server_id)
    try:
        with ssh_from_server(syn_srv, cred) as ssh:
            real_path = _synology_resolve_path(ssh, syn_srv.share_path, path)
            r = ssh.run(f'ls -la --time-style=+%Y-%m-%dT%H:%M:%S "{real_path}" 2>&1 | tail -n +2', timeout=15)
        items = []
        for line in r.stdout.strip().splitlines():
            parts = line.split(None, 6)
            if len(parts) < 7:
                continue
            name = parts[6]
            if name in (".", "..") or name.startswith("@eaDir") or name == "#recycle":
                continue
            is_dir = parts[0].startswith("d")
            items.append({"name": name, "is_dir": is_dir, "size_bytes": None if is_dir else int(parts[4]), "modified": parts[5]})
        items.sort(key=lambda x: (not x["is_dir"], x["name"]))
        return {"path": path, "items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to list Synology path: {e}")


@router.post("/storage/synology/{server_id}/delete")
def synology_delete(server_id: int, payload: dict, db: Session = Depends(get_db)):
    paths = payload.get("paths") or []
    if not paths:
        raise HTTPException(400, "No paths provided")
    syn_srv, cred = _get_synology_server(db, server_id)
    deleted = []
    try:
        with ssh_from_server(syn_srv, cred) as ssh:
            for p in paths:
                real_path = _synology_resolve_path(ssh, syn_srv.share_path, p)
                if real_path == syn_srv.share_path.rstrip("/"):
                    raise HTTPException(400, "Refusing to delete the share root itself")
                r = ssh.run(f'rm -rf "{real_path}" && echo OK || echo FAIL', timeout=60)
                if "OK" not in r.stdout:
                    raise HTTPException(500, f"Failed to delete {p}: {r.stdout} {r.stderr}")
                deleted.append(p)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")
    return {"deleted": len(deleted)}


# ============================================================
# Restore — database-only restore of a PROD backup into a Dev server
# ============================================================

@router.get("/restore/preflight")
def restore_preflight(db: Session = Depends(get_db)):
    """Read-only: what backup would be used, and is the Dev target reachable
    with enough room for it. Nothing here changes any state."""
    latest = (
        db.query(BackupJob)
        .filter(BackupJob.job_type == "online_full", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc())
        .first()
    )
    source_backup = None
    if latest:
        source_backup = {
            "job_id": latest.id, "finished_at": latest.finished_at.isoformat() if latest.finished_at else None,
            "output_path": latest.output_path, "total_size_bytes": latest.total_size_bytes,
            "target_server_id": latest.target_server_id,
        }

    dev_servers = []
    for dev_srv in db.query(Server).filter(Server.role == "dev", Server.enabled == True).all():  # noqa: E712
        cred = db.query(Credential).filter(
            Credential.server_id == dev_srv.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        entry = {"id": dev_srv.id, "name": dev_srv.name, "host": dev_srv.host, "oracle_sid": dev_srv.oracle_sid, "connected": False}
        if cred:
            try:
                with ssh_from_server(dev_srv, cred) as ssh:
                    data_dir = f"{dev_srv.apps_base}/data"
                    r = ssh.run(f'df -B1 "{dev_srv.apps_base}" 2>/dev/null | tail -1', timeout=10)
                    parts = r.stdout.split()
                    entry["connected"] = True
                    entry["available_bytes"] = int(parts[3]) if len(parts) > 3 else None
                    entry["total_bytes"] = int(parts[1]) if len(parts) > 1 else None
                    entry["data_dir"] = data_dir

                    status = ssh.run(
                        f'export ORACLE_HOME={dev_srv.oracle_home}; export ORACLE_SID={dev_srv.oracle_sid}; '
                        f'export PATH=$ORACLE_HOME/bin:$PATH; sqlplus -s / as sysdba <<\'SQL\'\n'
                        f'SET PAGES 0 FEED OFF\nSELECT status FROM v$instance;\nEXIT;\nSQL',
                        timeout=15,
                    )
                    entry["current_db_status"] = status.stdout.strip() or "UNKNOWN"
            except Exception as e:
                entry["error"] = str(e)
        else:
            entry["error"] = "No SSH credential configured"
        dev_servers.append(entry)

    return {"source_backup": source_backup, "dev_servers": dev_servers}


@router.post("/restore/dev-database")
def restore_to_dev(payload: RestoreDevIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    src_job = db.query(BackupJob).filter(BackupJob.id == payload.source_job_id).first()
    if not src_job or src_job.job_type != "online_full" or src_job.status != "success":
        raise HTTPException(400, "source_job_id must reference a successful Online Full backup")
    if not src_job.output_path:
        raise HTTPException(400, "Source job has no output_path")

    source_server = db.query(Server).filter(Server.id == src_job.target_server_id).first()
    if not source_server:
        raise HTTPException(400, "Source backup's server no longer exists")
    source_cred = db.query(Credential).filter(
        Credential.server_id == source_server.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not source_cred:
        raise HTTPException(400, "Source DB server has no SSH credential")

    dev_srv = db.query(Server).filter(Server.id == payload.dev_server_id, Server.role == "dev").first()
    if not dev_srv:
        raise HTTPException(400, "Target must be a registered Dev server")
    if not dev_srv.oracle_home or not dev_srv.oracle_sid:
        raise HTTPException(400, "Dev server is missing oracle_home/oracle_sid — set in Setup tab")

    backup_name = src_job.output_path.rstrip("/").split("/")[-1]
    local_staging_dir = f"{dev_srv.apps_base.rstrip('/')}/restore_staging/{backup_name}"
    dev_data_dir = f"{dev_srv.apps_base.rstrip('/')}/data"

    job = _create_job(db, "restore_dev", dev_srv.id, payload.model_dump())
    bash, target = rman_templates.rman_restore_dev(
        dev_oracle_home=dev_srv.oracle_home, dev_oracle_sid=dev_srv.oracle_sid, dev_data_dir=dev_data_dir,
        backup_source_host=source_server.host, backup_source_user=source_cred.username,
        backup_source_port=source_server.port or 22, backup_source_dir=src_job.output_path,
        local_staging_dir=local_staging_dir, job_id=job.id,
    )
    job.output_path = target
    db.commit()
    bg.add_task(_deploy_and_run, job.id, bash, target)
    return {"job_id": job.id, "status": "submitted", "target": target}


# ============================================================
# Reports
# ============================================================

def _daily_archivelog_counts(db: Session, days: int) -> dict:
    server = db.query(Server).filter(Server.role == "db", Server.enabled == True).first()  # noqa: E712
    if not server:
        return {}
    cred = db.query(Credential).filter(
        Credential.server_id == server.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        return {}
    try:
        with ssh_from_server(server, cred) as ssh:
            cmd = (
                f'find {ARCHIVELOG_STAGING_PATH} -name "*.arc" -mtime -{days} '
                f'-printf "%TY-%Tm-%Td %s\\n" 2>/dev/null'
            )
            r = ssh.run(cmd, timeout=20)
    except Exception:
        return {}

    result = {}
    for line in r.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        date_str, size = parts
        entry = result.setdefault(date_str, {"file_count": 0, "total_size_bytes": 0})
        entry["file_count"] += 1
        try:
            entry["total_size_bytes"] += int(size)
        except ValueError:
            pass
    return result


@router.get("/reports/summary")
def reports_summary(days: int = 5, db: Session = Depends(get_db)):
    days = max(1, min(days, 30))
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    jobs = (
        db.query(BackupJob).filter(BackupJob.created_at >= since)
        .order_by(BackupJob.created_at.desc()).all()
    )
    archlog_daily = _daily_archivelog_counts(db, days)

    day_list = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    daily = {d: {"date": d, "jobs": [], "archivelog": archlog_daily.get(d)} for d in day_list}
    for j in jobs:
        d = j.created_at.strftime("%Y-%m-%d")
        if d in daily:
            daily[d]["jobs"].append({
                "id": j.id, "job_type": j.job_type, "status": j.status,
                "total_size_bytes": j.total_size_bytes, "duration_sec": j.duration_sec,
                "started_at": j.started_at.isoformat() if j.started_at else None,
            })

    total_jobs = len(jobs)
    success_jobs = sum(1 for j in jobs if j.status == "success")
    failed_jobs = sum(1 for j in jobs if j.status == "failed")
    total_bytes = sum(j.total_size_bytes or 0 for j in jobs)

    last_full = (
        db.query(BackupJob).filter(BackupJob.job_type == "online_full", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc()).first()
    )
    last_app = (
        db.query(BackupJob).filter(BackupJob.job_type == "app_fs", BackupJob.status == "success")
        .order_by(BackupJob.finished_at.desc()).first()
    )

    return {
        "period_days": days, "generated_at": now.isoformat(),
        "kpi": {
            "total_jobs": total_jobs, "success_jobs": success_jobs, "failed_jobs": failed_jobs,
            "success_rate_pct": round(success_jobs / total_jobs * 100, 1) if total_jobs else None,
            "total_bytes_backed_up": total_bytes,
            "last_full_backup_at": last_full.finished_at.isoformat() if last_full and last_full.finished_at else None,
            "last_app_backup_at": last_app.finished_at.isoformat() if last_app and last_app.finished_at else None,
        },
        "daily": [daily[d] for d in day_list],
    }


# ============================================================
# Inventory — recovery-readiness scanner
# ============================================================

JUNK_SIZE_BYTES = 10 * 1024 * 1024
VERY_STALE_DAYS = 730
STALE_DAYS = 180
KEEP_NEWEST_PER_TYPE = 2


def _classify(sample_files: list[str], size_bytes: int) -> tuple[str, str]:
    lowered = [f.lower() for f in sample_files]
    if size_bytes < JUNK_SIZE_BYTES:
        return "junk", "Empty / Failed Attempt"
    if any(f.startswith("db_full") or f.startswith("ctl_") or f.startswith("spfile_")
           or f.startswith("inc0") for f in lowered):
        return "rman_full", "Full Database Backup (RMAN)"
    if any(f.startswith("db_inc") or f.startswith("inc1") for f in lowered):
        return "rman_incremental", "Incremental Database Backup (RMAN)"
    if any(f.startswith("arch_") or f.startswith("arc_") for f in lowered):
        return "archive_log", "Archive Log Backup"
    if any(f.endswith(".arc") for f in lowered):
        return "archive_log_raw", "Archive Log (raw files)"
    if any(".tgz" in f and any(k in f for k in ("fs1", "fs2", "fs_ne", "app")) for f in lowered):
        return "app_tier", "Application Tier Backup"
    if any(".tgz" in f and "db" in f for f in lowered):
        return "cold_tar", "Cold/Tar Database Backup"
    return "unknown", "Unclassified Backup"


_DATE_RE = re.compile(r"(?<![0-9a-zA-Z])(20\d{2})[-_]?(\d{2})[-_]?(\d{2})(?![0-9a-zA-Z])")


def _guess_date(*texts: str) -> str | None:
    for t in texts:
        m = _DATE_RE.search(t)
        if m:
            try:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            except Exception:
                pass
    return None


def _drop_ancestor_dirs(paths: list[str]) -> list[str]:
    result = []
    for p in paths:
        p_norm = p.rstrip("/") + "/"
        is_ancestor_of_another = any(
            other != p and (other.rstrip("/") + "/").startswith(p_norm) for other in paths
        )
        if not is_ancestor_of_another:
            result.append(p)
    return result


def _age_days(date_str: str | None, fallback_epoch: float | None) -> int | None:
    try:
        if date_str:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        elif fallback_epoch:
            d = datetime.utcfromtimestamp(fallback_epoch)
        else:
            return None
        return (datetime.utcnow() - d).days
    except Exception:
        return None


def _scan_db_server(db: Session) -> tuple[list[dict], Server | None]:
    server = db.query(Server).filter(Server.role == "db", Server.enabled == True).first()  # noqa: E712
    if not server:
        return [], None
    cred = db.query(Credential).filter(
        Credential.server_id == server.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred:
        return [], server

    items = []
    try:
        with ssh_from_server(server, cred) as ssh:
            find_dirs = ssh.run(f'find {settings.BACKUP_ROOT} -mindepth 1 -maxdepth 4 -type d 2>/dev/null', timeout=20)
            candidates = []
            for d in find_dirs.stdout.strip().splitlines():
                if not d:
                    continue
                has_file = ssh.run(f'find "{d}" -maxdepth 1 -type f -print -quit 2>/dev/null', timeout=10)
                if has_file.stdout.strip():
                    candidates.append(d)

            for d in _drop_ancestor_dirs(candidates):
                size_r = ssh.run(f'du -sb "{d}" 2>/dev/null | cut -f1', timeout=20)
                try:
                    size_bytes = int(size_r.stdout.strip() or 0)
                except ValueError:
                    size_bytes = 0
                newest_r = ssh.run(f'find "{d}" -maxdepth 1 -type f -printf "%T@\\n" 2>/dev/null | sort -n | tail -1', timeout=10)
                try:
                    newest_epoch = float(newest_r.stdout.strip()) if newest_r.stdout.strip() else None
                except ValueError:
                    newest_epoch = None
                sample_r = ssh.run(f'find "{d}" -maxdepth 1 -type f -printf "%f\\n" 2>/dev/null | head -8', timeout=10)
                sample_files = [f for f in sample_r.stdout.strip().splitlines() if f]

                type_key, type_label = _classify(sample_files, size_bytes)
                date_str = _guess_date(d, " ".join(sample_files))
                items.append({
                    "name": d.rstrip("/").split("/")[-1], "path": d,
                    "location": "db_server", "location_label": f"{server.name} (local disk)", "server_id": server.id,
                    "size_bytes": size_bytes, "type": type_key, "type_label": type_label, "date": date_str,
                    "age_days": _age_days(date_str, newest_epoch), "sample_files": sample_files[:5],
                })
    except Exception:
        pass
    return items, server


def _scan_minio(db: Session) -> list[dict]:
    minio_srv = db.query(Server).filter(Server.role == "minio", Server.enabled == True).first()  # noqa: E712
    if not minio_srv:
        return []
    cred = db.query(Credential).filter(Credential.server_id == minio_srv.id, Credential.cred_type == "minio").first()
    if not cred or not minio_srv.bucket:
        return []

    items = []
    try:
        client = _minio_client(minio_srv, cred)
        top = [o for o in client.list_objects(minio_srv.bucket, recursive=False) if o.is_dir]
        for folder in top:
            objs = list(client.list_objects(minio_srv.bucket, prefix=folder.object_name, recursive=True))
            if not objs:
                continue
            size_bytes = sum(o.size or 0 for o in objs)
            newest = max((o.last_modified for o in objs if o.last_modified), default=None)
            sample_files = [o.object_name.split("/")[-1] for o in objs[:8]]
            type_key, type_label = _classify(sample_files, size_bytes)
            date_str = _guess_date(folder.object_name, " ".join(sample_files))
            items.append({
                "name": folder.object_name.rstrip("/"), "path": folder.object_name,
                "location": "minio", "location_label": f"{minio_srv.name} ({minio_srv.bucket})", "server_id": minio_srv.id,
                "size_bytes": size_bytes, "type": type_key, "type_label": type_label, "date": date_str,
                "age_days": _age_days(date_str, newest.timestamp() if newest else None), "sample_files": sample_files[:5],
            })
    except Exception:
        pass
    return items


def _scan_synology(db: Session) -> list[dict]:
    syn_srv = db.query(Server).filter(Server.role == "synology", Server.enabled == True).first()  # noqa: E712
    if not syn_srv:
        return []
    cred = db.query(Credential).filter(
        Credential.server_id == syn_srv.id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
    ).first()
    if not cred or not syn_srv.share_path:
        return []

    items = []
    try:
        with ssh_from_server(syn_srv, cred) as ssh:
            find_dirs = ssh.run(
                f'find "{syn_srv.share_path}" -mindepth 1 -maxdepth 4 -type d '
                f'-not -path "*/@eaDir*" -not -path "*/#recycle*" 2>/dev/null',
                timeout=20,
            )
            candidates = []
            for d in find_dirs.stdout.strip().splitlines():
                if not d:
                    continue
                has_file = ssh.run(f'find "{d}" -maxdepth 1 -type f -print -quit 2>/dev/null', timeout=10)
                if has_file.stdout.strip():
                    candidates.append(d)

            for d in _drop_ancestor_dirs(candidates):
                size_r = ssh.run(f'du -sb "{d}" 2>/dev/null | cut -f1', timeout=20)
                try:
                    size_bytes = int(size_r.stdout.strip() or 0)
                except ValueError:
                    size_bytes = 0
                newest_r = ssh.run(f'find "{d}" -maxdepth 1 -type f -printf "%T@\\n" 2>/dev/null | sort -n | tail -1', timeout=10)
                try:
                    newest_epoch = float(newest_r.stdout.strip()) if newest_r.stdout.strip() else None
                except ValueError:
                    newest_epoch = None
                sample_r = ssh.run(f'find "{d}" -maxdepth 1 -type f -printf "%f\\n" 2>/dev/null | head -8', timeout=10)
                sample_files = [f for f in sample_r.stdout.strip().splitlines() if f]

                type_key, type_label = _classify(sample_files, size_bytes)
                rel_path = d[len(syn_srv.share_path):].lstrip("/")
                date_str = _guess_date(d, " ".join(sample_files))
                items.append({
                    "name": d.rstrip("/").split("/")[-1], "path": rel_path,
                    "location": "synology", "location_label": f"{syn_srv.name} ({syn_srv.share_path})", "server_id": syn_srv.id,
                    "size_bytes": size_bytes, "type": type_key, "type_label": type_label, "date": date_str,
                    "age_days": _age_days(date_str, newest_epoch), "sample_files": sample_files[:5],
                })
    except Exception:
        pass
    return items


def _merge_redundant(items: list[dict]) -> list[dict]:
    """Group items across DIFFERENT locations that are almost certainly copies
    of the same backup: same type, size within 5%, and matching date when both
    are known. Never merges two items from the same location."""
    merged = []
    used = [False] * len(items)
    for i, item in enumerate(items):
        if used[i]:
            continue
        group = [item]
        used[i] = True
        group_locations = {item["location"]}
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            other = items[j]
            if other["location"] in group_locations:
                continue
            if other["type"] != item["type"] or item["size_bytes"] <= 0:
                continue
            if item.get("date") and other.get("date") and item["date"] != other["date"]:
                continue
            ratio = other["size_bytes"] / item["size_bytes"]
            if 0.95 <= ratio <= 1.05:
                group.append(other)
                used[j] = True
                group_locations.add(other["location"])
        best = max(group, key=lambda g: g["size_bytes"])
        merged.append({
            **best,
            "locations": [{"location": g["location"], "location_label": g["location_label"],
                          "path": g["path"], "server_id": g["server_id"]} for g in group],
        })
    return merged


def _recommend(items: list[dict]) -> list[dict]:
    by_type: dict[str, list[dict]] = {}
    for it in items:
        by_type.setdefault(it["type"], []).append(it)
    for t, group in by_type.items():
        group.sort(key=lambda g: (g["age_days"] if g["age_days"] is not None else 999999))

    for t, group in by_type.items():
        for rank, it in enumerate(group):
            age = it["age_days"]
            is_multi_location = len(it["locations"]) > 1
            if it["type"] == "junk":
                it["recommendation"] = "delete"
                it["reason"] = "Too small to be a real backup — looks like a failed or empty attempt."
            elif age is not None and age > VERY_STALE_DAYS:
                it["recommendation"] = "delete"
                it["reason"] = f"Over {age // 365} years old — long past any realistic recovery need."
            elif rank < KEEP_NEWEST_PER_TYPE:
                if is_multi_location:
                    it["recommendation"] = "keep"
                    it["reason"] = f"One of the {KEEP_NEWEST_PER_TYPE} most recent {it['type_label']} backups, already copied offsite."
                else:
                    it["recommendation"] = "move_offsite"
                    it["reason"] = f"One of the {KEEP_NEWEST_PER_TYPE} most recent {it['type_label']} backups, but only exists in one place — copy it to MinIO or Synology."
            elif age is not None and age > STALE_DAYS:
                it["recommendation"] = "delete"
                it["reason"] = f"{age} days old and superseded by {KEEP_NEWEST_PER_TYPE} newer {it['type_label']} backup(s)."
            else:
                it["recommendation"] = "review"
                it["reason"] = f"Superseded by newer {it['type_label']} backups, but recent enough to double-check before deleting."
    return items


@router.get("/inventory/scan")
def scan_inventory(db: Session = Depends(get_db)):
    db_items, _ = _scan_db_server(db)
    minio_items = _scan_minio(db)
    syn_items = _scan_synology(db)
    all_items = db_items + minio_items + syn_items

    merged = _merge_redundant(all_items)
    merged = _recommend(merged)
    merged.sort(key=lambda it: (it["age_days"] if it["age_days"] is not None else 999999))

    full_backups = [it for it in merged if it["type"] in ("rman_full", "cold_tar")]
    full_backups.sort(key=lambda it: (it["age_days"] if it["age_days"] is not None else 999999))
    best = full_backups[0] if full_backups else None

    if not best:
        readiness = {"status": "red", "message": "No usable full database backup found.", "best": None}
    else:
        offsite = len(best["locations"]) > 1
        if best["age_days"] is not None and best["age_days"] <= 1 and offsite:
            status = "green"
        elif best["age_days"] is not None and best["age_days"] <= 7:
            status = "green" if offsite else "amber"
        else:
            status = "amber" if (best["age_days"] or 0) <= 30 else "red"
        readiness = {
            "status": status,
            "best": {
                "name": best["name"], "date": best["date"], "age_days": best["age_days"],
                "size_bytes": best["size_bytes"], "type_label": best["type_label"],
                "locations": [l["location_label"] for l in best["locations"]], "offsite": offsite,
            },
            "message": f"Production can be restored to {best['date'] or 'an unknown date'} ({best['age_days']} day(s) ago).",
        }
        if not offsite:
            readiness.setdefault("warnings", []).append(
                "This backup only exists in one location — copy it to MinIO or Synology for real disaster protection."
            )

    total_bytes = sum(it["size_bytes"] for it in merged)
    delete_bytes = sum(it["size_bytes"] for it in merged if it["recommendation"] == "delete")

    return {
        "generated_at": datetime.utcnow().isoformat(), "readiness": readiness,
        "total_bytes": total_bytes, "reclaimable_bytes": delete_bytes, "items": merged,
    }


@router.post("/inventory/delete")
def delete_inventory_item(payload: dict, db: Session = Depends(get_db)):
    """Delete one copy of a backup at a specific location. The frontend calls
    this once per location for items that exist in multiple places."""
    location = payload.get("location")
    server_id = payload.get("server_id")
    path = payload.get("path")
    if not location or not server_id or not path:
        raise HTTPException(400, "location, server_id and path are required")

    if location == "db_server":
        if not path.startswith(settings.BACKUP_ROOT):
            raise HTTPException(400, "Refusing to delete a path outside the backup root")
        server = db.query(Server).filter(Server.id == server_id).first()
        cred = db.query(Credential).filter(
            Credential.server_id == server_id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        if not server or not cred:
            raise HTTPException(404, "Server or credential not found")
        with ssh_from_server(server, cred) as ssh:
            r = ssh.run(f'rm -rf "{path}" && echo OK || echo FAIL', timeout=60)
        if "OK" not in r.stdout:
            raise HTTPException(500, f"Delete failed: {r.stdout} {r.stderr}")
        return {"deleted": True}

    elif location == "minio":
        minio_srv = db.query(Server).filter(Server.id == server_id).first()
        cred = db.query(Credential).filter(Credential.server_id == server_id, Credential.cred_type == "minio").first()
        if not minio_srv or not cred:
            raise HTTPException(404, "MinIO server or credential not found")
        client = _minio_client(minio_srv, cred)
        prefix = path if path.endswith("/") else path + "/"
        objs = list(client.list_objects(minio_srv.bucket, prefix=prefix, recursive=True))
        if not objs:
            raise HTTPException(404, "No objects found under that prefix")
        errors = list(client.remove_objects(minio_srv.bucket, [DeleteObject(o.object_name) for o in objs]))
        if errors:
            raise HTTPException(500, f"Some deletes failed: {[str(e) for e in errors]}")
        return {"deleted": True, "objects_removed": len(objs)}

    elif location == "synology":
        syn_srv = db.query(Server).filter(Server.id == server_id).first()
        cred = db.query(Credential).filter(
            Credential.server_id == server_id, Credential.cred_type.in_(["ssh_password", "ssh_key"]),
        ).first()
        if not syn_srv or not cred:
            raise HTTPException(404, "Synology server or credential not found")
        with ssh_from_server(syn_srv, cred) as ssh:
            real_path = _synology_resolve_path(ssh, syn_srv.share_path, path)
            if real_path == syn_srv.share_path.rstrip("/"):
                raise HTTPException(400, "Refusing to delete the share root itself")
            r = ssh.run(f'rm -rf "{real_path}" && echo OK || echo FAIL', timeout=60)
        if "OK" not in r.stdout:
            raise HTTPException(500, f"Delete failed: {r.stdout} {r.stderr}")
        return {"deleted": True}

    raise HTTPException(400, "Unknown location")
