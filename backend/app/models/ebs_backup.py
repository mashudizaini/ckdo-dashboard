"""
Oracle EBS Backup & Recovery — ported from the standalone `ebs-backup-dashboard`
app (was running separately on port 28200/28201) into a tab under Dashboard IT.

Kept as sync SQLAlchemy against a dedicated engine (not the app's shared async
Base/AsyncSession) — this mirrors the standalone almost verbatim, which matters
because the actual "work" here (Paramiko SSH to Oracle EBS servers, including a
restore path) is blocking I/O the standalone always ran in plain sync FastAPI
route handlers. Keeping that as-is (FastAPI auto-threadpools sync `def` routes)
avoids rewriting tested backup/restore orchestration logic to async for no
functional benefit. Tables live in the same Postgres database as the rest of
the app, just under their own `ebs_` prefix.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Boolean,
    Text, ForeignKey, BigInteger,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.config import get_settings

settings = get_settings()

# settings.database_url is a plain "postgresql://..." string (see app/database.py,
# which derives the asyncpg URL from it) — exactly what SQLAlchemy's sync
# psycopg2 driver expects by default.
ebs_engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
EbsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ebs_engine)
EbsBackupBase = declarative_base()


class EbsServer(EbsBackupBase):
    __tablename__ = "ebs_servers"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    role = Column(String(32), nullable=False)   # db | app | synology | minio | dev
    host = Column(String(128), nullable=False)
    port = Column(Integer, default=22)

    # Oracle/EBS-specific
    oracle_sid = Column(String(16))
    oracle_home = Column(String(255))
    apps_base = Column(String(255))
    current_fs = Column(String(8))               # fs1 | fs2

    # MinIO-specific
    endpoint_url = Column(String(255))
    bucket = Column(String(128))
    region = Column(String(32))

    # Synology-specific
    share_path = Column(String(255))
    protocol = Column(String(16))                # rsync_ssh | smb | nfs

    enabled = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    credentials = relationship("EbsCredential", back_populates="server",
                                cascade="all, delete-orphan")


class EbsCredential(EbsBackupBase):
    __tablename__ = "ebs_credentials"

    id = Column(Integer, primary_key=True)
    server_id = Column(Integer, ForeignKey("ebs_servers.id"), nullable=False)
    cred_type = Column(String(32), nullable=False)
    # ssh_password | ssh_key | minio
    username = Column(String(128))
    secret_encrypted = Column(Text, nullable=False)
    key_passphrase_encrypted = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    server = relationship("EbsServer", back_populates="credentials")


class EbsBackupJob(EbsBackupBase):
    __tablename__ = "ebs_backup_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(32), nullable=False)
    # online_full | online_incremental | offline_cold | archivelog | app_fs |
    # archivelog_sync | db_sync_minio | db_sync_synology | restore_dev

    target_server_id = Column(Integer, ForeignKey("ebs_servers.id"))
    triggered_by = Column(String(64), default="manual")
    status = Column(String(16), default="pending")
    # pending | running | paused | success | failed | cancelled

    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    duration_sec = Column(Integer)

    output_path = Column(String(512))
    total_size_bytes = Column(BigInteger)
    file_count = Column(Integer)
    rman_tag = Column(String(64))
    pid = Column(Integer)
    log_path = Column(String(512))

    parameters = Column(Text)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


class EbsSchedule(EbsBackupBase):
    __tablename__ = "ebs_schedules"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    job_type = Column(String(32), nullable=False)
    cron_expression = Column(String(64), nullable=False)
    target_server_id = Column(Integer, ForeignKey("ebs_servers.id"))

    parameters = Column(Text)
    enabled = Column(Boolean, default=True)

    last_run_at = Column(DateTime)
    last_run_status = Column(String(16))
    last_run_job_id = Column(Integer)
    next_run_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EbsReplicationJob(EbsBackupBase):
    __tablename__ = "ebs_replication_jobs"

    id = Column(Integer, primary_key=True)
    source_backup_job_id = Column(Integer, ForeignKey("ebs_backup_jobs.id"))
    target_server_id = Column(Integer, ForeignKey("ebs_servers.id"), nullable=False)

    method = Column(String(16), nullable=False)   # rsync | mc | aws_s3
    status = Column(String(16), default="pending")

    source_path = Column(String(512))
    target_path = Column(String(512))
    bytes_transferred = Column(BigInteger)
    avg_speed_mbps = Column(Float)

    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    duration_sec = Column(Integer)
    error_message = Column(Text)
    checksum_verified = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


def init_ebs_db():
    """Create ebs_* tables idempotently — called from the app lifespan
    (dev only), mirroring how the rest of app/main.py bootstraps schema."""
    EbsBackupBase.metadata.create_all(bind=ebs_engine)


def get_ebs_db():
    """FastAPI dependency — sync Session (routes using this must be plain
    `def`, not `async def`, so FastAPI runs them in its threadpool)."""
    db = EbsSessionLocal()
    try:
        yield db
    finally:
        db.close()
