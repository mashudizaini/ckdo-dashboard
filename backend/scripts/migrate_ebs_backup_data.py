"""
One-off data migration: standalone ebs-backup-dashboard's SQLite database
(servers, credentials, job history, schedules) -> the new ebs_* Postgres
tables in the main CKDO Dashboard database.

This is NOT run automatically by the app — it's a manual, one-time step for
carrying forward whatever was already configured in the standalone instance
(servers, SSH/MinIO credentials, job/schedule history) instead of starting
from a clean slate. Run it once, by hand, after confirming the SQLite source
file and the OLD_MASTER_KEY are correct — it INSERTs into tables the app
already created (ebs_servers, ebs_credentials, ebs_backup_jobs, ebs_schedules,
ebs_replication_jobs), preserving the original row IDs, so re-running it
against a non-empty target will fail on the primary key / unique constraints
rather than silently duplicating data.

Credentials are decrypted with the *standalone app's* Fernet MASTER_KEY (from
its .env — never committed, must be supplied here explicitly) and
re-encrypted with THIS app's FIELD_ENCRYPTION_KEY (app/services/crypto.py),
so going forward every secret in this app — not just these — is encrypted
under one key.

Usage (from backend/, inside the backend container or a matching venv):
    OLD_MASTER_KEY='<standalone .env MASTER_KEY value>' \\
    python -m scripts.migrate_ebs_backup_data \\
        --sqlite-path /path/to/ebs_backup.db

Add --dry-run to see row counts without writing anything.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet  # noqa: E402
from sqlalchemy import text  # noqa: E402
from app.services import crypto  # noqa: E402
from app.models.ebs_backup import (  # noqa: E402
    EbsSessionLocal, EbsServer, EbsCredential, EbsBackupJob, EbsSchedule, EbsReplicationJob,
)

TABLES = ["servers", "credentials", "backup_jobs", "schedules", "replication_jobs"]


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite-path", required=True, help="Path to the standalone app's ebs_backup.db")
    ap.add_argument("--dry-run", action="store_true", help="Print row counts only, write nothing")
    args = ap.parse_args()

    old_master_key = os.environ.get("OLD_MASTER_KEY", "").strip()
    if not old_master_key:
        print("FATAL: set OLD_MASTER_KEY to the standalone app's Fernet MASTER_KEY (from its .env).")
        sys.exit(1)
    if not crypto.settings.field_encryption_key:
        print("FATAL: this app's FIELD_ENCRYPTION_KEY is not set — set it before migrating secrets.")
        sys.exit(1)

    old_fernet = Fernet(old_master_key.encode())

    def reencrypt(ciphertext: str) -> str:
        if not ciphertext:
            return ""
        plaintext = old_fernet.decrypt(ciphertext.encode()).decode()
        return crypto.encrypt(plaintext)

    src = sqlite3.connect(args.sqlite_path)
    src.row_factory = sqlite3.Row

    counts = {t: src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    print("Source row counts:", counts)
    if args.dry_run:
        print("--dry-run: stopping before any write.")
        return

    db = EbsSessionLocal()
    try:
        for row in src.execute("SELECT * FROM servers"):
            db.add(EbsServer(
                id=row["id"], name=row["name"], role=row["role"], host=row["host"], port=row["port"],
                oracle_sid=row["oracle_sid"], oracle_home=row["oracle_home"], apps_base=row["apps_base"],
                current_fs=row["current_fs"], endpoint_url=row["endpoint_url"], bucket=row["bucket"],
                region=row["region"], share_path=row["share_path"], protocol=row["protocol"],
                enabled=bool(row["enabled"]), notes=row["notes"],
                created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
                updated_at=_parse_dt(row["updated_at"]) or datetime.utcnow(),
            ))
        db.flush()
        print(f"Migrated {counts['servers']} servers")

        for row in src.execute("SELECT * FROM credentials"):
            db.add(EbsCredential(
                id=row["id"], server_id=row["server_id"], cred_type=row["cred_type"], username=row["username"],
                secret_encrypted=reencrypt(row["secret_encrypted"]),
                key_passphrase_encrypted=reencrypt(row["key_passphrase_encrypted"]) if row["key_passphrase_encrypted"] else None,
                created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
            ))
        db.flush()
        print(f"Migrated {counts['credentials']} credentials (re-encrypted)")

        for row in src.execute("SELECT * FROM backup_jobs"):
            db.add(EbsBackupJob(
                id=row["id"], job_type=row["job_type"], target_server_id=row["target_server_id"],
                triggered_by=row["triggered_by"], status=row["status"],
                started_at=_parse_dt(row["started_at"]), finished_at=_parse_dt(row["finished_at"]),
                duration_sec=row["duration_sec"], output_path=row["output_path"],
                total_size_bytes=row["total_size_bytes"], file_count=row["file_count"],
                rman_tag=row["rman_tag"], pid=row["pid"], log_path=row["log_path"],
                parameters=row["parameters"], error_message=row["error_message"],
                created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
            ))
        db.flush()
        print(f"Migrated {counts['backup_jobs']} backup job history rows")

        for row in src.execute("SELECT * FROM schedules"):
            db.add(EbsSchedule(
                id=row["id"], name=row["name"], job_type=row["job_type"], cron_expression=row["cron_expression"],
                target_server_id=row["target_server_id"], parameters=row["parameters"], enabled=bool(row["enabled"]),
                last_run_at=_parse_dt(row["last_run_at"]), last_run_status=row["last_run_status"],
                last_run_job_id=row["last_run_job_id"], next_run_at=_parse_dt(row["next_run_at"]),
                created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
                updated_at=_parse_dt(row["updated_at"]) or datetime.utcnow(),
            ))
        db.flush()
        print(f"Migrated {counts['schedules']} schedules")

        for row in src.execute("SELECT * FROM replication_jobs"):
            db.add(EbsReplicationJob(
                id=row["id"], source_backup_job_id=row["source_backup_job_id"], target_server_id=row["target_server_id"],
                method=row["method"], status=row["status"], source_path=row["source_path"], target_path=row["target_path"],
                bytes_transferred=row["bytes_transferred"], avg_speed_mbps=row["avg_speed_mbps"],
                started_at=_parse_dt(row["started_at"]), finished_at=_parse_dt(row["finished_at"]),
                duration_sec=row["duration_sec"], error_message=row["error_message"],
                checksum_verified=bool(row["checksum_verified"]),
                created_at=_parse_dt(row["created_at"]) or datetime.utcnow(),
            ))
        db.flush()
        print(f"Migrated {counts['replication_jobs']} replication job rows")

        # Postgres sequences don't auto-advance when IDs are inserted explicitly —
        # without this, the next INSERT without an explicit id (any normal
        # create-server/create-job call from the app) collides with a migrated row.
        for table, seq_col in [
            ("ebs_servers", "id"), ("ebs_credentials", "id"), ("ebs_backup_jobs", "id"),
            ("ebs_schedules", "id"), ("ebs_replication_jobs", "id"),
        ]:
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{seq_col}'), "
                f"COALESCE((SELECT MAX({seq_col}) FROM {table}), 1))"
            ))

        db.commit()
        print("Migration complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        src.close()


if __name__ == "__main__":
    main()
