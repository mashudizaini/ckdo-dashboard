"""
IT Service
─────────────────────────────────────────
Business logic untuk IT Dashboard.
"""
import asyncio
import json
import os
from datetime import datetime
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()

# Config stored in /app/data/server_config.json (persisted via Docker volume)
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CONFIG_FILE = os.path.join(CONFIG_DIR, "server_config.json")

DEFAULT_CONFIG = {
    "ip": "172.21.2.201",
    "port": 22,
    "username": "",
    "password": "",
}


class ITService:

    async def get_summary(self) -> dict:
        return {
            "success": True,
            "data": {
                "tickets": {"open": 0, "in_progress": 0, "resolved_this_week": 0},
                "servers": {"total": 0, "online": 0, "offline": 0},
                "uptime_avg_percent": 0.0,
            },
        }

    async def get_server_status(self) -> dict:
        return {"success": True, "data": []}

    async def get_ticket_summary(self) -> dict:
        return {"success": True, "data": []}

    async def get_weekly_report_data(self) -> dict:
        return {
            "success": True,
            "data": {"period": "", "activities": [], "next_week_plan": []},
        }

    def _run_oracle_query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


class OracleITService:
    """Oracle EBS queries for IT Dashboard — tablespace, jobs, workflow."""

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(columns, row)))
            return rows

    # ── Tablespace ───────────────────────────────────────────────────────────

    async def get_tablespace(self) -> dict:
        sql = """
            SELECT
                tablespace_name,
                ROUND(used_percent, 2)                                AS usage_percent,
                ROUND(used_space * 8192 / 1024 / 1024 / 1024, 2)    AS used_gb,
                ROUND(tablespace_size * 8192 / 1024 / 1024 / 1024, 2) AS total_gb
            FROM dba_tablespace_usage_metrics
            WHERE tablespace_name NOT LIKE '%UNDO%'
              AND tablespace_name NOT LIKE '%TEMP%'
            ORDER BY used_percent DESC
            FETCH FIRST 5 ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            # Add status label
            for r in rows:
                pct = float(r.get("usage_percent", 0))
                r["status"] = "Critical" if pct >= 90 else "Warning" if pct >= 70 else "Normal"
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("tablespace_query_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Tablespace Datafiles ─────────────────────────────────────────────────

    async def get_tablespace_datafiles(self, tablespace_name: str) -> dict:
        """List existing datafiles for a tablespace — shown as reference in the Add Datafile form."""
        sql = """
            SELECT
                file_name,
                ROUND(bytes / 1024 / 1024, 2)           AS size_mb,
                ROUND(bytes / 1024 / 1024 / 1024, 2)    AS size_gb,
                autoextensible,
                status
            FROM dba_data_files
            WHERE tablespace_name = :ts_name
            ORDER BY file_id
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, {"ts_name": tablespace_name})
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("tablespace_datafiles_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def resize_tablespace_datafile(
        self,
        file_path: str,
        add_value: float,
        add_unit: str,
    ) -> dict:
        """
        Extend an existing datafile by a given amount.
        Calculates new_size = current_size + add_amount, then runs
        ALTER DATABASE DATAFILE '<path>' RESIZE <new_size>M
        """
        if add_unit not in ("MB", "GB"):
            return {"success": False, "error": "Unit harus MB atau GB"}
        if add_value <= 0 or add_value > 102400:
            return {"success": False, "error": "Tambahan ukuran tidak valid (1 – 102400)"}

        # Fetch current size in MB
        size_sql = """
            SELECT ROUND(bytes / 1024 / 1024, 2) AS size_mb
            FROM dba_data_files
            WHERE file_name = :fp
        """
        try:
            rows = await asyncio.to_thread(self._query, size_sql, {"fp": file_path})
        except Exception as e:
            logger.error("resize_fetch_size_error", error=str(e))
            return {"success": False, "error": f"Gagal membaca ukuran file: {str(e)}"}

        if not rows:
            return {"success": False, "error": f"Datafile tidak ditemukan: {file_path}"}

        current_mb  = float(rows[0]["size_mb"])
        add_mb      = add_value * 1024 if add_unit == "GB" else add_value
        new_total_mb = current_mb + add_mb

        ddl = f"ALTER DATABASE DATAFILE '{file_path}' RESIZE {int(new_total_mb)}M"

        try:
            def _exec():
                with get_oracle_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(ddl)
                    conn.commit()

            await asyncio.to_thread(_exec)
            return {
                "success": True,
                "message": (
                    f"Datafile berhasil di-resize: {current_mb:.0f} MB → {new_total_mb:.0f} MB"
                    f" (+{add_mb:.0f} MB)"
                ),
                "ddl":          ddl,
                "current_mb":   current_mb,
                "add_mb":       add_mb,
                "new_total_mb": new_total_mb,
            }
        except Exception as e:
            logger.error("resize_tablespace_datafile_error", error=str(e), ddl=ddl)
            return {"success": False, "error": str(e)}

    async def add_tablespace_datafile(
        self,
        tablespace_name: str,
        file_path: str,
        size_value: float,
        size_unit: str,
        autoextend: bool = False,
    ) -> dict:
        """Execute ALTER TABLESPACE … ADD DATAFILE to extend a tablespace."""
        import re
        if not re.match(r"^[A-Z0-9_\$#]+$", tablespace_name.upper()):
            return {"success": False, "error": "Nama tablespace tidak valid"}
        if size_unit not in ("MB", "GB"):
            return {"success": False, "error": "Unit harus MB atau GB"}
        if size_value <= 0 or size_value > 102400:
            return {"success": False, "error": "Ukuran tidak valid (1 – 102400)"}

        ddl = (
            f"ALTER TABLESPACE {tablespace_name} ADD DATAFILE '{file_path}'"
            f" SIZE {int(size_value) if size_value == int(size_value) else size_value}{size_unit}"
        )
        if autoextend:
            ddl += " AUTOEXTEND ON NEXT 100M MAXSIZE UNLIMITED"

        try:
            def _exec():
                with get_oracle_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(ddl)
                    conn.commit()

            await asyncio.to_thread(_exec)
            return {
                "success": True,
                "message": f"Datafile berhasil ditambahkan ke tablespace {tablespace_name}",
                "ddl": ddl,
            }
        except Exception as e:
            logger.error("add_tablespace_datafile_error", error=str(e), ddl=ddl)
            return {"success": False, "error": str(e)}

    # ── Pending Jobs ─────────────────────────────────────────────────────────

    async def get_pending_jobs(self) -> dict:
        sql = """
            SELECT
                fcr.request_id,
                fcp.user_concurrent_program_name                          AS program_name,
                fu.user_name,
                TO_CHAR(fcr.request_date, 'DD-MON-YYYY HH24:MI:SS')     AS request_date,
                ROUND((SYSDATE - fcr.request_date) * 24 * 60, 0)        AS wait_time_minutes,
                CASE
                    WHEN fcr.phase_code = 'P' THEN 'Pending'
                    WHEN fcr.phase_code = 'R' THEN 'Running'
                    ELSE fcr.phase_code
                END AS phase_display,
                CASE
                    WHEN fcr.status_code = 'Q' THEN 'Waiting'
                    WHEN fcr.status_code = 'I' THEN 'Normal'
                    WHEN fcr.status_code = 'R' THEN 'Running'
                    WHEN fcr.status_code = 'E' THEN 'Error'
                    ELSE fcr.status_code
                END AS status_display
            FROM fnd_concurrent_requests fcr
            INNER JOIN fnd_concurrent_programs_vl fcp
                ON fcr.concurrent_program_id = fcp.concurrent_program_id
            INNER JOIN fnd_user fu
                ON fcr.requested_by = fu.user_id
            WHERE fcr.phase_code IN ('P', 'R')
              AND fcr.request_date >= SYSDATE - 1
            ORDER BY fcr.request_date DESC
            FETCH FIRST 10 ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("pending_jobs_query_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Workflow Error ────────────────────────────────────────────────────────

    async def get_workflow_errors(self) -> dict:
        detail_sql = """
            SELECT
                wias.item_type,
                wias.item_key,
                b.activity_name,
                wias.activity_status,
                wias.error_message,
                TO_CHAR(wias.begin_date, 'DD-MON-YYYY HH24:MI') AS begin_date,
                ROUND(SYSDATE - wias.begin_date, 0)              AS days_pending
            FROM apps.wf_item_activity_statuses wias,
                 apps.wf_process_activities b
            WHERE ROWNUM < 11
              AND wias.process_activity = b.instance_id
              AND b.process_item_type = wias.item_type
              AND wias.activity_status IN ('ERROR', 'SUSPENDED', 'NOTIFIED')
              AND wias.begin_date >= SYSDATE - 30
            ORDER BY
                CASE
                    WHEN wias.activity_status = 'ERROR'     THEN 1
                    WHEN wias.activity_status = 'SUSPENDED' THEN 2
                    WHEN wias.activity_status = 'NOTIFIED'  THEN 3
                    ELSE 4
                END,
                wias.begin_date DESC
            FETCH FIRST 10 ROWS ONLY
        """
        summary_sql = """
            SELECT
                SUM(CASE WHEN activity_status = 'ERROR'     THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN activity_status = 'SUSPENDED' THEN 1 ELSE 0 END) AS suspended_count,
                SUM(CASE WHEN activity_status = 'NOTIFIED'  THEN 1 ELSE 0 END) AS notified_count
            FROM apps.wf_item_activity_statuses
            WHERE activity_status IN ('ERROR', 'SUSPENDED', 'NOTIFIED')
              AND begin_date >= SYSDATE - 30
        """
        try:
            rows    = await asyncio.to_thread(self._query, detail_sql)
            summary = await asyncio.to_thread(self._query, summary_sql)
            s = summary[0] if summary else {}
            return {
                "success": True,
                "count": len(rows),
                "data": rows,
                "summary": {
                    "error":     int(s.get("error_count", 0) or 0),
                    "suspended": int(s.get("suspended_count", 0) or 0),
                    "notified":  int(s.get("notified_count", 0) or 0),
                },
            }
        except Exception as e:
            logger.error("workflow_error_query_error", error=str(e))
            return {
                "success": False, "error": str(e), "data": [],
                "summary": {"error": 0, "suspended": 0, "notified": 0},
            }


    # ── Oracle Sessions ──────────────────────────────────────────────────────

    async def get_oracle_sessions(self) -> dict:
        """Active user sessions from v$session + v$session_wait, ordered by idle time desc."""
        sql = """
            SELECT
                s.sid,
                s.serial#                               AS serial_num,
                NVL(s.username, '(background)')         AS username,
                s.status,
                SUBSTR(NVL(s.machine, '-'), 1, 40)      AS machine,
                SUBSTR(NVL(s.program, '-'), 1, 40)      AS program,
                NVL(s.sql_id, '-')                      AS sql_id,
                NVL(s.last_call_et, 0)                  AS idle_seconds,
                NVL(w.event, '-')                       AS event,
                NVL(w.wait_class, '-')                  AS wait_class,
                NVL(w.seconds_in_wait, 0)               AS seconds_in_wait,
                NVL(w.state, '-')                       AS state
            FROM v$session s
            LEFT JOIN v$session_wait w ON s.sid = w.sid
            WHERE s.username IS NOT NULL
              AND s.type = 'USER'
            ORDER BY
                CASE WHEN s.status = 'ACTIVE' THEN 0 ELSE 1 END,
                NVL(w.seconds_in_wait, 0) DESC
            FETCH FIRST 50 ROWS ONLY
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "count": len(rows), "data": rows}
        except Exception as e:
            logger.error("oracle_sessions_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    async def kill_oracle_session(self, sid: int, serial_num: int) -> dict:
        """Execute ALTER SYSTEM DISCONNECT SESSION 'sid,serial#' IMMEDIATE."""
        if not (1 <= sid <= 99999) or not (1 <= serial_num <= 9999999):
            return {"success": False, "error": "Invalid SID or serial number"}
        ddl = f"ALTER SYSTEM DISCONNECT SESSION '{sid},{serial_num}' IMMEDIATE"
        try:
            def _exec():
                with get_oracle_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(ddl)
            await asyncio.to_thread(_exec)
            return {
                "success": True,
                "message": f"Session SID {sid} (Serial# {serial_num}) disconnected successfully",
                "ddl": ddl,
            }
        except Exception as e:
            logger.error("kill_session_error", error=str(e), sid=sid, serial=serial_num)
            return {"success": False, "error": str(e)}


class ServerMonitorService:
    """SSH-based server monitoring — mirrors CKDO_DASHBOARD monitor_bp logic."""

    # ── Config ──────────────────────────────────────────────────────────────

    def load_config(self) -> dict:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def save_config(self, config: dict) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

    def get_config_public(self) -> dict:
        """Return config with password masked."""
        cfg = self.load_config()
        return {
            "ip": cfg.get("ip", ""),
            "port": cfg.get("port", 22),
            "username": cfg.get("username", ""),
            "has_password": bool(cfg.get("password")),
        }

    # ── SSH ─────────────────────────────────────────────────────────────────

    def _ssh(self, command: str, config: dict | None = None) -> str:
        import paramiko

        cfg = config or self.load_config()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            cfg["ip"],
            port=int(cfg.get("port", 22)),
            username=cfg["username"],
            password=cfg["password"],
            timeout=8,
        )
        _, stdout, stderr = client.exec_command(command)
        out = stdout.read().decode("utf-8").strip()
        err = stderr.read().decode("utf-8").strip()
        client.close()
        if err:
            raise Exception(err)
        return out

    def _ssh_multi(self, commands: list[str], config: dict | None = None) -> list[str]:
        """Run multiple commands on ONE SSH connection — avoids repeated auth handshakes."""
        import paramiko
        cfg = config or self.load_config()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            cfg["ip"],
            port=int(cfg.get("port", 22)),
            username=cfg["username"],
            password=cfg["password"],
            timeout=8,
        )
        results = []
        try:
            for cmd in commands:
                _, stdout, _ = client.exec_command(cmd)
                results.append(stdout.read().decode("utf-8").strip())
        finally:
            client.close()
        return results

    # ── Test connection ──────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {"success": False, "error": "Username/password belum dikonfigurasi"}
        try:
            result = await asyncio.to_thread(self._ssh, 'echo "Connection OK"')
            return {"success": True, "message": "Koneksi berhasil", "response": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Server Metrics ───────────────────────────────────────────────────────

    def _fetch_metrics(self) -> dict:
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {
                "status": "not_configured",
                "error": "Username/password belum dikonfigurasi",
                "cpu": 0, "memory_percent": 0,
                "memory_used": 0, "memory_total": 0,
                "load": "0.0", "uptime": "-",
                "swap_percent": 0, "swap_used_mb": 0, "swap_total_mb": 0,
                "cpu_count": 4,
            }

        # All 6 commands in ONE SSH connection (was 4 separate connections before)
        cpu_raw, mem_raw, swap_raw, load_raw, uptime_raw, ncpu_raw = self._ssh_multi([
            "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1",
            "free -g | grep Mem | awk '{print $3,$2}'",
            "free -m | grep Swap | awk '{print $2,$3}'",
            "cat /proc/loadavg | awk '{print $1}'",
            "uptime -p",
            "nproc 2>/dev/null || grep -c processor /proc/cpuinfo 2>/dev/null || echo 4",
        ], cfg)

        mem_parts   = mem_raw.split()
        mem_used    = float(mem_parts[0]) if mem_parts else 0
        mem_total   = float(mem_parts[1]) if len(mem_parts) > 1 else 1
        mem_pct     = round((mem_used / mem_total) * 100, 1) if mem_total > 0 else 0

        swap_parts  = swap_raw.split()
        swap_total  = float(swap_parts[0]) if swap_parts else 0
        swap_used   = float(swap_parts[1]) if len(swap_parts) > 1 else 0
        swap_pct    = round((swap_used / swap_total) * 100, 1) if swap_total > 0 else 0

        cpu_count   = int(ncpu_raw) if (ncpu_raw or "").strip().isdigit() else 4

        return {
            "status":       "online",
            "cpu":          round(float(cpu_raw or 0), 1),
            "memory_percent": mem_pct,
            "memory_used":  round(mem_used, 2),
            "memory_total": round(mem_total, 2),
            "load":         load_raw or "0.0",
            "uptime":       uptime_raw or "-",
            "swap_percent": swap_pct,
            "swap_used_mb": round(swap_used, 0),
            "swap_total_mb": round(swap_total, 0),
            "cpu_count":    cpu_count,
            "timestamp":    datetime.now().isoformat(),
        }

    # ── Top Processes ────────────────────────────────────────────────────────

    def _fetch_top_processes(self) -> dict:
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {"status": "not_configured", "cpu": [], "mem": []}

        cpu_raw, mem_raw = self._ssh_multi([
            "ps -eo user:15,pid:7,pcpu:6,pmem:6,comm:20 --no-headers --sort=-%cpu 2>/dev/null | head -8",
            "ps -eo user:15,pid:7,pcpu:6,pmem:6,comm:20 --no-headers --sort=-%mem 2>/dev/null | head -8",
        ], cfg)

        def parse(raw: str) -> list[dict]:
            rows = []
            for line in (raw or "").strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    rows.append({
                        "user":    parts[0],
                        "pid":     parts[1],
                        "cpu":     parts[2],
                        "mem":     parts[3],
                        "command": parts[4],
                    })
            return rows

        return {"status": "online", "cpu": parse(cpu_raw), "mem": parse(mem_raw)}

    async def get_top_processes(self) -> dict:
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {"success": False, "error": "SSH credentials not configured", "cpu": [], "mem": []}
        try:
            data = await asyncio.to_thread(self._fetch_top_processes)
            return {"success": True, **data}
        except Exception as e:
            logger.error("top_processes_error", error=str(e))
            return {"success": False, "error": str(e), "cpu": [], "mem": []}

    # ── Disk Usage (both servers) ────────────────────────────────────────────

    _DISK_SERVERS = [
        {"key": "db",  "label": "DB Server",  "ip": "172.21.2.201"},
        {"key": "app", "label": "App Server", "ip": "172.21.2.202"},
    ]

    def _fetch_disk(self, server: dict, cfg: dict) -> dict:
        """Run `df -P` on one server and return parsed mount-point rows."""
        import paramiko

        server_cfg = {**cfg, "ip": server["ip"]}
        try:
            # Use a direct SSH call here so we can ignore df's non-fatal stderr
            # (e.g. bind mounts / squashfs generate warnings that aren't errors)
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                server_cfg["ip"],
                port=int(server_cfg.get("port", 22)),
                username=server_cfg["username"],
                password=server_cfg["password"],
                timeout=8,
            )
            _, stdout, _ = client.exec_command("df -P 2>/dev/null | grep -v '^Filesystem'")
            raw = stdout.read().decode("utf-8").strip()
            client.close()

            rows = []
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) < 6:
                    continue
                filesystem  = parts[0]
                blocks      = parts[1]
                used        = parts[2]
                available   = parts[3]
                capacity    = parts[4]
                mountpoint  = parts[5]
                cap_str = capacity.replace("%", "")
                pct      = int(cap_str)     if cap_str.isdigit()  else 0
                used_gb  = round(int(used)      / 1024 / 1024, 2) if used.isdigit()      else 0
                total_gb = round(int(blocks)    / 1024 / 1024, 2) if blocks.isdigit()    else 0
                free_gb  = round(int(available) / 1024 / 1024, 2) if available.isdigit() else 0
                if total_gb < 0.1:   # skip virtual/tiny fs
                    continue
                rows.append({
                    "server_key":    server["key"],
                    "server_label":  server["label"],
                    "server_ip":     server["ip"],
                    "filesystem":    filesystem,
                    "mountpoint":    mountpoint,
                    "used_gb":       used_gb,
                    "free_gb":       free_gb,
                    "total_gb":      total_gb,
                    "usage_percent": pct,
                    "status": "Critical" if pct >= 90 else "Warning" if pct >= 70 else "Normal",
                })
            return {"key": server["key"], "label": server["label"], "ip": server["ip"],
                    "status": "online", "rows": rows}
        except Exception as e:
            return {"key": server["key"], "label": server["label"], "ip": server["ip"],
                    "status": "error", "error": str(e), "rows": []}

    async def get_disk_usage_all(self) -> dict:
        """Fetch df -P from DB (172.21.2.201) and App (172.21.2.202) in parallel."""
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {
                "success": False,
                "error": "SSH credentials not configured. Go to Server Monitoring → Settings.",
                "servers": [],
            }
        results = await asyncio.gather(
            *[asyncio.to_thread(self._fetch_disk, s, cfg) for s in self._DISK_SERVERS],
            return_exceptions=False,
        )
        servers = list(results)
        all_rows = [r for s in servers for r in s.get("rows", [])]
        return {"success": True, "servers": servers, "data": all_rows}

    async def get_metrics(self) -> dict:
        cfg = self.load_config()
        if not cfg.get("username") or not cfg.get("password"):
            return {
                "success": True,
                "data": {
                    "status": "not_configured",
                    "error": "Username/password belum dikonfigurasi",
                    "cpu": 0, "memory_percent": 0,
                    "memory_used": 0, "memory_total": 0,
                    "load": "0.0", "uptime": "-",
                },
            }
        try:
            data = await asyncio.to_thread(self._fetch_metrics)
            return {"success": True, "data": data}
        except Exception as e:
            logger.error("server_metrics_error", error=str(e))
            return {
                "success": True,
                "data": {
                    "status": "error",
                    "error": str(e),
                    "cpu": 0, "memory_percent": 0,
                    "memory_used": 0, "memory_total": 0,
                    "load": "0.0", "uptime": "Error",
                },
            }
