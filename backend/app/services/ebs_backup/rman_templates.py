"""
RMAN & tar script templates for Oracle 12.1 + EBS R12.2.

Each template returns complete bash script that:
  1. Sets Oracle environment
  2. Creates target directory
  3. Writes RMAN command file inline (heredoc)
  4. Executes RMAN / tar
  5. Writes manifest.json at the end for dashboard to parse results
"""
from datetime import datetime


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================
# 1. RMAN ONLINE FULL BACKUP (Hot Backup)
# ============================================================
def rman_online_full(
    oracle_home: str,
    oracle_sid: str,
    staging_path: str,
    parallelism: int = 4,
    compression: bool = True,
    include_archivelog: bool = True,
    archivelog_delete_input: bool = False,
    include_spfile: bool = True,
    job_id: int = 0,
    # ----- Optional post-backup sync (RMAN can only write local/NFS disk, so
    # "backup direct to MinIO/Synology" really means: backup to local staging
    # as always, then immediately push it out as part of the same job) -----
    sync_target: str | None = None,        # None | "minio" | "synology"
    minio_endpoint: str | None = None,
    minio_access_key: str | None = None,
    minio_secret_key: str | None = None,
    minio_bucket: str | None = None,
    minio_prefix: str = "db-tier",
    synology_host: str | None = None,
    synology_user: str | None = None,
    synology_port: int = 22,
    synology_share_path: str | None = None,
) -> tuple[str, str]:
    """Return (bash_script, target_dir)."""
    ts = _timestamp()
    target_dir = f"{staging_path}/database/full/{oracle_sid}_{ts}"
    compress = "AS COMPRESSED BACKUPSET" if compression else "AS BACKUPSET"

    sync_block = ""
    if sync_target == "minio":
        minio_alias = f"dbsync{job_id}"
        minio_url = minio_endpoint if minio_endpoint.startswith("http") else f"http://{minio_endpoint}"
        minio_dest = f"{minio_alias}/{minio_bucket}/{minio_prefix}/{oracle_sid}_{ts}"
        sync_block = f"""
    echo "[$(date)] === SYNC TO MINIO ==="
    mc alias set {minio_alias} "{minio_url}" "{minio_access_key}" "{minio_secret_key}" --api s3v4 >/dev/null
    mc mirror "$TARGET_DIR" {minio_dest} 2>&1 | tail -30
    echo "[$(date)] Sync to MinIO complete: {minio_dest}"
"""
    elif sync_target == "synology":
        # tar-over-SSH, not rsync: this Synology's DSM rejects `rsync --server`
        # for this account (some rsync-specific ACL) even though the account
        # has full shell + filesystem access over SSH otherwise — confirmed
        # by testing directly. tar avoids that restriction entirely.
        syn_ssh_opts = f"-p {synology_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
        syn_dest_dir = f"{synology_share_path}/database/full/{oracle_sid}_{ts}"
        sync_block = f"""
    echo "[$(date)] === SYNC TO SYNOLOGY ==="
    ssh {syn_ssh_opts} {synology_user}@{synology_host} "mkdir -p {syn_dest_dir}"
    tar cf - -C "$TARGET_DIR" . | ssh {syn_ssh_opts} {synology_user}@{synology_host} "cd {syn_dest_dir} && tar xf -"
    echo "[$(date)] Sync to Synology complete: {syn_dest_dir}"
"""

    channels = "\n".join([
        f"  ALLOCATE CHANNEL ch{i+1} DEVICE TYPE DISK "
        f"FORMAT '{target_dir}/DB_FULL_{oracle_sid}_{ts}_%U.bkp';"
        for i in range(parallelism)
    ])
    release = "\n".join([f"  RELEASE CHANNEL ch{i+1};"
                          for i in range(parallelism)])

    archlog_block = ""
    if include_archivelog:
        del_input = "DELETE INPUT" if archivelog_delete_input else ""
        archlog_block = f"""
  BACKUP {compress}
    FORMAT '{target_dir}/ARCH_{oracle_sid}_{ts}_%U.bkp'
    ARCHIVELOG ALL {del_input};
"""

    rman_cmd = f"""RUN {{
  CONFIGURE CONTROLFILE AUTOBACKUP ON;
  CONFIGURE CONTROLFILE AUTOBACKUP FORMAT FOR DEVICE TYPE DISK TO '{target_dir}/CTL_{oracle_sid}_{ts}_%F.bkp';
  CONFIGURE SNAPSHOT CONTROLFILE NAME TO '{target_dir}/snapcf_{oracle_sid}.f';

{channels}

  BACKUP {compress}
    FORMAT '{target_dir}/DB_FULL_{oracle_sid}_{ts}_%U.bkp'
    DATABASE
    PLUS ARCHIVELOG;
{archlog_block}
  BACKUP CURRENT CONTROLFILE FORMAT '{target_dir}/CTL_{oracle_sid}_{ts}_%U.bkp';
{"  BACKUP SPFILE FORMAT '" + target_dir + "/SPFILE_" + oracle_sid + "_" + ts + "_%U.bkp';" if include_spfile else "  -- BACKUP SPFILE skipped: instance is started with a PFILE, not an SPFILE"}

{release}

  CROSSCHECK BACKUP;
}}

LIST BACKUP SUMMARY;
REPORT SCHEMA;
EXIT;
"""

    bash = f"""#!/bin/bash
# RMAN ONLINE FULL — Job {job_id}
set -e
export ORACLE_HOME={oracle_home}
export ORACLE_SID={oracle_sid}
export PATH=$ORACLE_HOME/bin:$PATH
export NLS_DATE_FORMAT='YYYY-MM-DD HH24:MI:SS'

TARGET_DIR="{target_dir}"
RCV="$TARGET_DIR/rman_cmd.rcv"
LOG="$TARGET_DIR/rman_session.log"

echo "[$(date)] === RMAN ONLINE FULL START ==="
echo "[$(date)] DB: $ORACLE_SID  HOME: $ORACLE_HOME"
echo "[$(date)] Target: $TARGET_DIR"

mkdir -p "$TARGET_DIR"

echo "[$(date)] Estimating source database size..."
DB_SIZE_RAW=$(sqlplus -s / as sysdba <<'SQLEOF'
SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF
SELECT NVL(SUM(bytes),0) FROM dba_data_files;
EXIT;
SQLEOF
)
DB_SIZE_BYTES=$(awk -v n="$DB_SIZE_RAW" 'BEGIN{{printf "%.0f", n}}' 2>/dev/null || echo 0)
echo "[$(date)] Estimated DB size: $DB_SIZE_BYTES bytes"
echo "[PROGRESS_TOTAL_BYTES] $DB_SIZE_BYTES"

cat > "$RCV" << 'RMAN_EOF'
{rman_cmd}
RMAN_EOF

set +e
rman target / cmdfile="$RCV" log="$LOG" append
RC=$?
set -e
echo "[$(date)] RMAN exit code: $RC"

if [ $RC -eq 0 ]; then
    cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "online_full",
  "oracle_sid": "$ORACLE_SID",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$TARGET_DIR",
  "total_size_bytes": $(du -sb "$TARGET_DIR" | cut -f1),
  "file_count": $(ls -1 "$TARGET_DIR"/*.bkp 2>/dev/null | wc -l),
  "sync_target": "{sync_target or 'none'}",
  "status": "success"
}}
MANIFEST
{sync_block}
    echo "[$(date)] === SUCCESS ==="
    exit 0
else
    cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{"job_id": {job_id}, "status": "failed", "exit_code": $RC}}
MANIFEST
    echo "[$(date)] === FAILED ==="
    exit $RC
fi
"""
    return bash, target_dir


# ============================================================
# 2. RMAN INCREMENTAL (Level 0 baseline or Level 1)
# ============================================================
def rman_incremental(
    oracle_home: str,
    oracle_sid: str,
    staging_path: str,
    level: int = 1,
    parallelism: int = 4,
    job_id: int = 0,
) -> tuple[str, str]:
    ts = _timestamp()
    target_dir = f"{staging_path}/database/incremental/{oracle_sid}_L{level}_{ts}"

    channels = "\n".join([f"  ALLOCATE CHANNEL ch{i+1} DEVICE TYPE DISK;"
                          for i in range(parallelism)])
    release = "\n".join([f"  RELEASE CHANNEL ch{i+1};"
                          for i in range(parallelism)])

    rman_cmd = f"""RUN {{
{channels}
  BACKUP AS COMPRESSED BACKUPSET
    INCREMENTAL LEVEL {level}
    FORMAT '{target_dir}/DB_INC{level}_{oracle_sid}_{ts}_%U.bkp'
    DATABASE
    PLUS ARCHIVELOG;
{release}
}}
LIST BACKUP SUMMARY;
EXIT;
"""

    bash = f"""#!/bin/bash
# RMAN INCREMENTAL L{level} — Job {job_id}
set -e
export ORACLE_HOME={oracle_home}
export ORACLE_SID={oracle_sid}
export PATH=$ORACLE_HOME/bin:$PATH

TARGET_DIR="{target_dir}"
RCV="$TARGET_DIR/rman_cmd.rcv"
LOG="$TARGET_DIR/rman_session.log"

echo "[$(date)] === RMAN INCREMENTAL L{level} START ==="
mkdir -p "$TARGET_DIR"

cat > "$RCV" << 'RMAN_EOF'
{rman_cmd}
RMAN_EOF

set +e
rman target / cmdfile="$RCV" log="$LOG" append
RC=$?
set -e

if [ $RC -eq 0 ]; then
    cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "online_incremental",
  "level": {level},
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$TARGET_DIR",
  "total_size_bytes": $(du -sb "$TARGET_DIR" | cut -f1),
  "file_count": $(ls -1 "$TARGET_DIR"/*.bkp 2>/dev/null | wc -l),
  "status": "success"
}}
MANIFEST
fi
exit $RC
"""
    return bash, target_dir


# ============================================================
# 3. ARCHIVELOG-ONLY BACKUP
# ============================================================
def rman_archivelog(
    oracle_home: str,
    oracle_sid: str,
    staging_path: str,
    delete_input: bool = True,
    job_id: int = 0,
) -> tuple[str, str]:
    ts = _timestamp()
    target_dir = f"{staging_path}/database/archivelog/{datetime.now().strftime('%Y%m%d')}"
    del_clause = "DELETE INPUT" if delete_input else ""

    rman_cmd = f"""RUN {{
  ALLOCATE CHANNEL ch1 DEVICE TYPE DISK;
  ALLOCATE CHANNEL ch2 DEVICE TYPE DISK;
  BACKUP AS COMPRESSED BACKUPSET
    FORMAT '{target_dir}/ARCH_{oracle_sid}_{ts}_%U.bkp'
    ARCHIVELOG ALL {del_clause};
  BACKUP CURRENT CONTROLFILE FORMAT '{target_dir}/CTL_{oracle_sid}_{ts}_%U.bkp';
  RELEASE CHANNEL ch1;
  RELEASE CHANNEL ch2;
}}
EXIT;
"""

    bash = f"""#!/bin/bash
# ARCHIVELOG BACKUP — Job {job_id}
set -e
export ORACLE_HOME={oracle_home}
export ORACLE_SID={oracle_sid}
export PATH=$ORACLE_HOME/bin:$PATH

TARGET_DIR="{target_dir}"
RCV="$TARGET_DIR/rman_cmd_{ts}.rcv"
LOG="$TARGET_DIR/rman_session_{ts}.log"

echo "[$(date)] === ARCHIVELOG BACKUP START ==="
mkdir -p "$TARGET_DIR"

cat > "$RCV" << 'RMAN_EOF'
{rman_cmd}
RMAN_EOF

set +e
rman target / cmdfile="$RCV" log="$LOG" append
RC=$?
set -e

if [ $RC -eq 0 ]; then
    cat > "$TARGET_DIR/manifest_{ts}.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "archivelog",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$TARGET_DIR",
  "total_size_bytes": $(du -sb "$TARGET_DIR" | cut -f1),
  "file_count": $(ls -1 "$TARGET_DIR"/*.bkp 2>/dev/null | wc -l),
  "status": "success"
}}
MANIFEST
fi
# Also write to manifest.json (latest)
cp "$TARGET_DIR/manifest_{ts}.json" "$TARGET_DIR/manifest.json" 2>/dev/null || true
exit $RC
"""
    return bash, target_dir


# ============================================================
# 4. OFFLINE COLD BACKUP — Shutdown EBS, shutdown DB, tar, startup
# ============================================================
def cold_backup(
    oracle_home: str,
    oracle_sid: str,
    staging_path: str,
    data_paths: list[str],
    apps_base: str | None = None,
    fs_active: str = "fs2",
    job_id: int = 0,
) -> tuple[str, str]:
    """⚠️ Will SHUTDOWN database. Only for maintenance window."""
    ts = _timestamp()
    target_dir = f"{staging_path}/database/cold/{oracle_sid}_{ts}"

    tar_cmds = "\n".join([
        f'echo "[$(date)] Tar {dp}..."; '
        f'tar czf "$TARGET_DIR/COLD_{oracle_sid}_$(basename {dp})_{ts}.tgz" '
        f'-C "$(dirname {dp})" "$(basename {dp})" 2>&1 | tail -10'
        for dp in data_paths
    ])

    apps_section = ""
    if apps_base:
        env_script = f"{apps_base}/EBSapps.env"
        apps_section = f"""
echo "[$(date)] === Stop EBS apps tier ({fs_active}) ==="
# Note: must run as applmgr user and have APPS password
# Recommended: setup wallet, or create separate tested script
su - applmgr -c "source {env_script} {fs_active.upper()} && \\
    \\$ADMIN_SCRIPTS_HOME/adstpall.sh apps/PASSWORD_TO_BE_REPLACED" || \\
    echo "WARN: adstpall returned non-zero (may already be down)"
"""
        apps_startup = f"""
echo "[$(date)] === Start EBS apps tier ==="
su - applmgr -c "source {env_script} {fs_active.upper()} && \\
    \\$ADMIN_SCRIPTS_HOME/adstrtal.sh apps/PASSWORD_TO_BE_REPLACED" || \\
    echo "WARN: adstrtal returned non-zero"
"""
    else:
        apps_startup = ""

    bash = f"""#!/bin/bash
# ⚠️ COLD BACKUP — Job {job_id}
set -e
export ORACLE_HOME={oracle_home}
export ORACLE_SID={oracle_sid}
export PATH=$ORACLE_HOME/bin:$PATH

TARGET_DIR="{target_dir}"
LOG_FILE="$TARGET_DIR/cold_backup.log"
mkdir -p "$TARGET_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] === COLD BACKUP START ==="
{apps_section}

echo "[$(date)] === Shutdown database ==="
sqlplus -s / as sysdba << 'SQL_EOF'
SHUTDOWN IMMEDIATE
EXIT
SQL_EOF

if [ $? -ne 0 ]; then
    echo "[$(date)] FATAL: shutdown failed"
    cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{"job_id": {job_id}, "status": "failed", "stage": "shutdown"}}
MANIFEST
    exit 10
fi

echo "[$(date)] === DB DOWN. Starting cold tar ==="
{tar_cmds}

echo "[$(date)] === Startup database ==="
sqlplus -s / as sysdba << 'SQL_EOF'
STARTUP
EXIT
SQL_EOF

{apps_startup}

cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "offline_cold",
  "oracle_sid": "$ORACLE_SID",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$TARGET_DIR",
  "total_size_bytes": $(du -sb "$TARGET_DIR" | cut -f1),
  "file_count": $(ls -1 "$TARGET_DIR"/*.tgz 2>/dev/null | wc -l),
  "status": "success"
}}
MANIFEST

echo "[$(date)] === COLD BACKUP SUCCESS ==="
exit 0
"""
    return bash, target_dir


# ============================================================
# 5. APPLICATION BACKUP — FS1/FS2 (R12.2)
# ============================================================
def app_backup(
    apps_base: str,
    fs_to_backup: str,
    fs_ne_path: str,
    staging_path: str,
    include_inst_top: bool = True,
    exclude_logs: bool = True,
    job_id: int = 0,
    # ----- REMOTE TARGET (optional): stream tar output via SSH to another server -----
    remote_host: str | None = None,       # e.g. "ckd-db" or IP
    remote_user: str | None = None,       # e.g. "oraprod"
    remote_port: int = 22,
    remote_ssh_key: str | None = None,    # path to private key on App server (for SSH to DB)
) -> tuple[str, str]:
    """
    Backup EBS application tier (FS1/FS2/both).

    Mode:
    - LOCAL (default): tar written to {staging_path}/application/... on App server
    - REMOTE (if remote_host set): tar streamed via SSH pipe to remote server.
      Pattern: tar czf - <fs> | ssh user@remote "cat > /backup/.../APP.tgz"
      Useful when App server disk is full or no backup partition available.
    """
    ts = _timestamp()
    target_dir = f"{staging_path}/application/{fs_to_backup}/PROD_{ts}"
    is_remote = bool(remote_host)

    exclude_patterns = [
        "--exclude=*/logs/*", "--exclude=*/log/*",
        "--exclude=*/tmp/*", "--exclude=*/temp/*",
        "--exclude=*.listener_*.log",
    ] if exclude_logs else []
    exclude_str = " ".join(exclude_patterns)

    fs_list = []
    if fs_to_backup in ("fs1", "both"):
        fs_list.append("fs1")
    if fs_to_backup in ("fs2", "both"):
        fs_list.append("fs2")

    # SSH option string for remote mode
    # StrictHostKeyChecking=no (bukan accept-new) supaya kompatibel dengan OpenSSH lama
    # (accept-new baru ada sejak OpenSSH 7.6 — banyak server EBS masih pakai versi lebih tua).
    ssh_opts = f"-p {remote_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
    if remote_ssh_key:
        ssh_opts += f" -i {remote_ssh_key}"
    ssh_dest = f"{remote_user}@{remote_host}" if is_remote else ""

    tar_cmds = []
    for fs in fs_list:
        tgz_name = f"APP_PROD_{fs.upper()}_{ts}.tgz"
        if is_remote:
            # Stream via SSH pipe
            tar_cmds.append(
                f'echo "[$(date)] Stream tar {fs} → {ssh_dest}:{target_dir}/{tgz_name}"; '
                f'tar cf - {exclude_str} -C "{apps_base}" {fs} '
                f'| gzip -c '
                f'| ssh {ssh_opts} {ssh_dest} '
                f'"cat > {target_dir}/{tgz_name}"'
            )
        else:
            tar_cmds.append(
                f'echo "[$(date)] Tar {fs}..."; '
                f'tar czf "$TARGET_DIR/{tgz_name}" '
                f'{exclude_str} -C "{apps_base}" {fs} 2>&1 | tail -20'
            )

    # Estimate total source size up front so the dashboard can show a real
    # percentage instead of just a spinner (du walks the same tree tar will).
    progress_calc_lines = ["SRC_TOTAL_BYTES=0"]
    for fs in fs_list:
        progress_calc_lines.append(
            f'SRC_TOTAL_BYTES=$((SRC_TOTAL_BYTES + $(du -sb "{apps_base}/{fs}" 2>/dev/null | cut -f1 || echo 0)))'
        )
    if include_inst_top:
        progress_calc_lines.append(
            f'SRC_TOTAL_BYTES=$((SRC_TOTAL_BYTES + $(du -sb "{fs_ne_path}" 2>/dev/null | cut -f1 || echo 0)))'
        )
    progress_calc_lines.append('echo "[$(date)] Source size: $SRC_TOTAL_BYTES bytes"')
    progress_calc_lines.append('echo "[PROGRESS_TOTAL_BYTES] $SRC_TOTAL_BYTES"')
    progress_calc_block = "\n".join(progress_calc_lines)

    if include_inst_top:
        tgz_name = f"APP_PROD_FS_NE_{ts}.tgz"
        if is_remote:
            tar_cmds.append(
                f'echo "[$(date)] Stream tar fs_ne → {ssh_dest}:{target_dir}/{tgz_name}"; '
                f'tar cf - {exclude_str} -C "$(dirname {fs_ne_path})" "$(basename {fs_ne_path})" '
                f'| gzip -c | ssh {ssh_opts} {ssh_dest} '
                f'"cat > {target_dir}/{tgz_name}"'
            )
        else:
            tar_cmds.append(
                f'echo "[$(date)] Tar fs_ne..."; '
                f'tar czf "$TARGET_DIR/{tgz_name}" '
                f'{exclude_str} -C "$(dirname {fs_ne_path})" "$(basename {fs_ne_path})" 2>&1 | tail -20'
            )

    # --------------------- BUILD BASH ---------------------
    if is_remote:
        # REMOTE mode: target dir created ON DB SERVER via SSH first, manifest also there,
        # but local log saved to /tmp on App server for dashboard polling.
        bash = f"""#!/bin/bash
# APP BACKUP (REMOTE STREAM) — Job {job_id}  Target: {fs_to_backup}
# Source: this server (app tier)
# Destination: {ssh_dest}:{target_dir}
set -e
LOG_FILE="/tmp/ebs_backup_job_{job_id}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] === APP BACKUP START (REMOTE MODE) ==="
echo "[$(date)] APPS_BASE: {apps_base}"
echo "[$(date)] FS: {fs_to_backup}"
echo "[$(date)] Remote dest: {ssh_dest}:{target_dir}"

# Create target dir on DB server
ssh {ssh_opts} {ssh_dest} "mkdir -p {target_dir}"

# Test connection once (early-fail if key/network issue)
ssh {ssh_opts} {ssh_dest} "echo SSH_OK_$(hostname)" || {{
    echo "[$(date)] FATAL: SSH to {ssh_dest} failed. Check key/network."
    exit 11
}}

{progress_calc_block}

# Execute all tar streams
{chr(10).join(tar_cmds)}

# Write manifest on DB server
REMOTE_SIZE=$(ssh {ssh_opts} {ssh_dest} "du -sb {target_dir} | cut -f1")
REMOTE_COUNT=$(ssh {ssh_opts} {ssh_dest} "ls -1 {target_dir}/*.tgz 2>/dev/null | wc -l")
MANIFEST_JSON="{{\\"job_id\\": {job_id}, \\"job_type\\": \\"app_fs\\", \\"fs_target\\": \\"{fs_to_backup}\\", \\"mode\\": \\"remote_stream\\", \\"finished_at\\": \\"$(date '+%Y-%m-%d %H:%M:%S')\\", \\"target_dir\\": \\"{target_dir}\\", \\"source_host\\": \\"$(hostname)\\", \\"target_host\\": \\"{remote_host}\\", \\"total_size_bytes\\": $REMOTE_SIZE, \\"file_count\\": $REMOTE_COUNT, \\"status\\": \\"success\\"}}"
ssh {ssh_opts} {ssh_dest} "echo '$MANIFEST_JSON' > {target_dir}/manifest.json"

echo "[$(date)] === APP BACKUP SUCCESS ==="
echo "[$(date)] Size: $REMOTE_SIZE bytes ($((REMOTE_SIZE/1024/1024/1024)) GB)"
echo "[$(date)] Files: $REMOTE_COUNT"
exit 0
"""
    else:
        # LOCAL mode (original)
        bash = f"""#!/bin/bash
# APP BACKUP — Job {job_id}  Target: {fs_to_backup}
set -e
TARGET_DIR="{target_dir}"
LOG_FILE="$TARGET_DIR/app_backup.log"
mkdir -p "$TARGET_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] === APP BACKUP START ==="
echo "[$(date)] APPS_BASE: {apps_base}"
echo "[$(date)] FS: {fs_to_backup}"

{progress_calc_block}

{chr(10).join(tar_cmds)}

cat > "$TARGET_DIR/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "app_fs",
  "fs_target": "{fs_to_backup}",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$TARGET_DIR",
  "total_size_bytes": $(du -sb "$TARGET_DIR" | cut -f1),
  "file_count": $(ls -1 "$TARGET_DIR"/*.tgz 2>/dev/null | wc -l),
  "status": "success"
}}
MANIFEST

echo "[$(date)] === APP BACKUP SUCCESS ==="
exit 0
"""
    return bash, target_dir


# ============================================================
# 6. RSYNC to Synology (replication)
# ============================================================
def rsync_replication(
    source_path: str,
    target_host: str,
    target_user: str,
    target_path: str,
    target_port: int = 22,
    bandwidth_limit_kbps: int = 0,
    job_id: int = 0,
) -> tuple[str, str]:
    """Generate rsync command to sync to Synology via SSH."""
    ts = _timestamp()
    log_dir = f"/tmp/ebs_repl_{job_id}"
    bw = f"--bwlimit={bandwidth_limit_kbps}" if bandwidth_limit_kbps > 0 else ""

    bash = f"""#!/bin/bash
# RSYNC REPLICATION — Job {job_id}
set -e
mkdir -p {log_dir}
LOG="{log_dir}/rsync_{ts}.log"

echo "[$(date)] === RSYNC START ==="
echo "[$(date)] Source: {source_path}"
echo "[$(date)] Target: {target_user}@{target_host}:{target_path}"

rsync -avz --progress {bw} \\
    -e "ssh -p {target_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \\
    --stats \\
    "{source_path}/" \\
    "{target_user}@{target_host}:{target_path}/" 2>&1 | tee "$LOG"

RC=${{PIPESTATUS[0]}}

cat > "{log_dir}/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "replication_rsync",
  "source": "{source_path}",
  "target": "{target_user}@{target_host}:{target_path}",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "status": "$([ $RC -eq 0 ] && echo success || echo failed)",
  "exit_code": $RC
}}
MANIFEST

exit $RC
"""
    return bash, log_dir


# ============================================================
# 7. MinIO replication (via mc client)
# ============================================================
def minio_replication(
    source_path: str,
    minio_alias: str,
    bucket: str,
    target_prefix: str,
    job_id: int = 0,
) -> tuple[str, str]:
    """Sync local folder to MinIO bucket. Assumes mc already configured on server."""
    ts = _timestamp()
    log_dir = f"/tmp/ebs_minio_{job_id}"

    bash = f"""#!/bin/bash
# MINIO REPLICATION — Job {job_id}
set -e
mkdir -p {log_dir}
LOG="{log_dir}/mc_{ts}.log"

echo "[$(date)] === MINIO MIRROR START ==="
echo "[$(date)] Source: {source_path}"
echo "[$(date)] Target: {minio_alias}/{bucket}/{target_prefix}"

# Assumes mc alias already set:
#   mc alias set {minio_alias} https://endpoint ACCESS SECRET
mc mirror --overwrite \\
    "{source_path}" \\
    "{minio_alias}/{bucket}/{target_prefix}" 2>&1 | tee "$LOG"

RC=${{PIPESTATUS[0]}}

cat > "{log_dir}/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "replication_minio",
  "source": "{source_path}",
  "target": "{minio_alias}/{bucket}/{target_prefix}",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "status": "$([ $RC -eq 0 ] && echo success || echo failed)",
  "exit_code": $RC
}}
MANIFEST

exit $RC
"""
    return bash, log_dir


# ============================================================
# 9. RESTORE PROD BACKUP INTO DEV — database-only, restore-in-place
# ============================================================
def rman_restore_dev(
    dev_oracle_home: str,
    dev_oracle_sid: str,
    dev_data_dir: str,          # e.g. /d01/DEV/data — where restored datafiles land
    backup_source_host: str,    # DB server that holds the backup pieces (pulled FROM here)
    backup_source_user: str,
    backup_source_port: int,
    backup_source_dir: str,     # e.g. /backup/staging/database/full/PROD_20260804_201422
    local_staging_dir: str,     # e.g. /d01/restore_staging/PROD_20260804_201422
    job_id: int = 0,
) -> tuple[str, str]:
    """
    ⚠️ DESTRUCTIVE to the Dev instance: this OVERWRITES dev_oracle_sid's current
    database with a restored copy of the source backup. Database-only — the EBS
    application tier on Dev (autoconfig, FND_NODES, etc.) is NOT touched; that is
    a separate, much larger Rapid Clone procedure and out of scope here.

    Runs entirely ON the Dev server, which pulls the backup pieces from the DB
    server itself (tar-over-SSH — same mechanism as the Synology sync, chosen
    for the same reason: no dependency on rsync being permitted). Requires
    passwordless SSH from Dev to the DB server to be set up first — this script
    does NOT set that up; it will simply fail at the pull step if missing.

    Steps performed (in order — see manifest.json / live log for how far it got):
      1. Pull backup pieces from the source DB server to local staging on Dev.
      2. SHUTDOWN the Dev instance, STARTUP NOMOUNT.
      3. RESTORE CONTROLFILE from the backup's controlfile piece.
      4. MOUNT, then CATALOG the local staging dir into RMAN's repository.
      5. RESTORE DATABASE with datafiles redirected to dev_data_dir.
      6. RESTORE ARCHIVELOG ALL + RECOVER DATABASE.
      7. ALTER DATABASE OPEN RESETLOGS.
    """
    ssh_opts = (
        f"-p {backup_source_port} -o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null -o BatchMode=yes"
    )

    bash = f"""#!/bin/bash
# RESTORE PROD BACKUP -> DEV (database-only) — Job {job_id}
set -e
export ORACLE_HOME={dev_oracle_home}
export ORACLE_SID={dev_oracle_sid}
export PATH=$ORACLE_HOME/bin:$PATH
export NLS_DATE_FORMAT='YYYY-MM-DD HH24:MI:SS'

LOCAL_STAGING="{local_staging_dir}"
LOG_FILE="$LOCAL_STAGING/restore_job_{job_id}.log"
mkdir -p "$LOCAL_STAGING"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] === RESTORE TO DEV START ==="
echo "[$(date)] Source: {backup_source_user}@{backup_source_host}:{backup_source_dir}"
echo "[$(date)] Dev SID: $ORACLE_SID  HOME: $ORACLE_HOME  Target data dir: {dev_data_dir}"

echo "[$(date)] Step 1/7: estimate backup size"
SRC_TOTAL_BYTES=$(ssh {ssh_opts} {backup_source_user}@{backup_source_host} \\
    'du -sb "{backup_source_dir}" 2>/dev/null | cut -f1' || echo 0)
echo "[PROGRESS_TOTAL_BYTES] $SRC_TOTAL_BYTES"

echo "[$(date)] Step 2/7: pull backup pieces from source DB server"
ssh {ssh_opts} {backup_source_user}@{backup_source_host} \\
    'tar cf - -C "{backup_source_dir}" .' | tar xf - -C "$LOCAL_STAGING"

CTL_FILE=$(ls "$LOCAL_STAGING"/CTL_*.bkp 2>/dev/null | head -1)
if [ -z "$CTL_FILE" ]; then
    echo "[$(date)] FATAL: no controlfile backup piece (CTL_*.bkp) found in pulled backup"
    exit 20
fi
echo "[$(date)] Controlfile piece: $CTL_FILE"

echo "[$(date)] Step 3/7: shutdown Dev instance, startup nomount"
sqlplus -s / as sysdba << SQL_EOF1 || true
SHUTDOWN IMMEDIATE;
SQL_EOF1
sqlplus -s / as sysdba << SQL_EOF2
STARTUP NOMOUNT;
EXIT;
SQL_EOF2

echo "[$(date)] Step 4/7: restore controlfile, mount, catalog backup pieces"
set +e
rman target / << RMAN_EOF1
RESTORE CONTROLFILE FROM '$CTL_FILE';
ALTER DATABASE MOUNT;
CATALOG START WITH '$LOCAL_STAGING/' NOPROMPT;
RMAN_EOF1
RC=$?
set -e
if [ $RC -ne 0 ]; then
    echo "[$(date)] FATAL: restore controlfile / mount / catalog failed (RC=$RC)"
    cat > "$LOCAL_STAGING/manifest.json" << MANIFEST
{{"job_id": {job_id}, "status": "failed", "stage": "restore_controlfile", "exit_code": $RC}}
MANIFEST
    exit $RC
fi

echo "[$(date)] Step 5/7: restore database (datafiles -> {dev_data_dir})"
echo "[$(date)] Step 6/7: restore archivelog + recover"
set +e
rman target / << RMAN_EOF2
RUN {{
  SET NEWNAME FOR DATABASE TO '{dev_data_dir}/%b';
  RESTORE DATABASE;
  SWITCH DATAFILE ALL;
}}
RESTORE ARCHIVELOG ALL;
RECOVER DATABASE;
RMAN_EOF2
RC=$?
set -e
if [ $RC -ne 0 ]; then
    echo "[$(date)] FATAL: restore/recover database failed (RC=$RC)"
    cat > "$LOCAL_STAGING/manifest.json" << MANIFEST
{{"job_id": {job_id}, "status": "failed", "stage": "restore_recover", "exit_code": $RC}}
MANIFEST
    exit $RC
fi

echo "[$(date)] Step 7/7: open resetlogs"
sqlplus -s / as sysdba << SQL_EOF3
ALTER DATABASE OPEN RESETLOGS;
EXIT;
SQL_EOF3

cat > "$LOCAL_STAGING/manifest.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "restore_dev",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$LOCAL_STAGING",
  "total_size_bytes": $(du -sb "$LOCAL_STAGING" 2>/dev/null | cut -f1),
  "status": "success"
}}
MANIFEST

echo "[$(date)] === RESTORE TO DEV SUCCESS — database open ==="
exit 0
"""
    return bash, local_staging_dir


# ============================================================
# 8. ARCHIVE LOG SYNC → MinIO (rsync source → local staging → mc mirror,
#    with retention cleanup on both staging and MinIO)
# ============================================================
def archive_log_sync(
    source_dir: str,
    local_staging: str,
    minio_endpoint: str,
    minio_access_key: str,
    minio_secret_key: str,
    minio_bucket: str,
    minio_prefix: str = "archive-logs",
    retention_days: int = 30,
    job_id: int = 0,
) -> tuple[str, str]:
    """
    Copy new archived redo logs (*.arc) to local staging, mirror staging to
    MinIO, then purge anything older than retention_days from BOTH the
    staging folder and MinIO. This only manages the staging/MinIO copies —
    RMAN's own cleanup of the original archive destination on the DB server
    is a separate, unrelated concern and is left untouched.
    """
    minio_alias = f"dash{job_id}"
    minio_url = minio_endpoint if minio_endpoint.startswith("http") else f"http://{minio_endpoint}"
    minio_target = f"{minio_alias}/{minio_bucket}/{minio_prefix}"

    bash = f"""#!/bin/bash
# ARCHIVE LOG SYNC -> MinIO — Job {job_id}
set -e
LOCAL_STAGING="{local_staging}"
mkdir -p "$LOCAL_STAGING"
LOG_FILE="$LOCAL_STAGING/archive_sync_job_{job_id}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] === ARCHIVE LOG SYNC START ==="
echo "[$(date)] Source: {source_dir}"
echo "[$(date)] Staging: $LOCAL_STAGING"
echo "[$(date)] MinIO target: {minio_target}"
echo "[$(date)] Retention: {retention_days} days"

echo "[$(date)] Step 1/4: rsync new archive logs to staging"
rsync -av --ignore-existing "{source_dir}"/*.arc "$LOCAL_STAGING/" 2>&1 | tail -30 || true

echo "[$(date)] Step 2/4: configure mc alias"
mc alias set {minio_alias} "{minio_url}" "{minio_access_key}" "{minio_secret_key}" --api s3v4 >/dev/null

echo "[$(date)] Step 3/4: mirror staging to MinIO"
mc mirror --exclude "*.log" --exclude "*.json" "$LOCAL_STAGING" {minio_target} 2>&1 | tail -30

echo "[$(date)] Step 4/4: purge entries older than {retention_days} days"
mc rm --recursive --force --older-than {retention_days}d {minio_target} 2>&1 | tail -20 || true
find "$LOCAL_STAGING" -name '*.arc' -mtime +{retention_days} -delete 2>&1 || true

STAGING_SIZE=$(du -sb "$LOCAL_STAGING" 2>/dev/null | cut -f1)
STAGING_COUNT=$(find "$LOCAL_STAGING" -name '*.arc' | wc -l)
MINIO_COUNT=$(mc ls --recursive {minio_target} 2>/dev/null | wc -l)

cat > "$LOCAL_STAGING/manifest_job_{job_id}.json" << MANIFEST
{{
  "job_id": {job_id},
  "job_type": "archivelog_sync",
  "finished_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "target_dir": "$LOCAL_STAGING",
  "total_size_bytes": $STAGING_SIZE,
  "file_count": $STAGING_COUNT,
  "minio_object_count": $MINIO_COUNT,
  "status": "success"
}}
MANIFEST
cp "$LOCAL_STAGING/manifest_job_{job_id}.json" "$LOCAL_STAGING/manifest.json"

echo "[$(date)] === ARCHIVE LOG SYNC SUCCESS ==="
echo "[$(date)] Staging: $STAGING_COUNT files, $STAGING_SIZE bytes. MinIO objects: $MINIO_COUNT"
exit 0
"""
    return bash, local_staging