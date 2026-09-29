"""
IT Dashboard Router
─────────────────────────────────────────
Route prefix : /api/v1/dashboard/it
Required role: it_staff OR admin

Endpoints:
  GET  /summary                       — KPI cards
  GET  /server-monitoring/servers     — every server in Server Control
  GET  /server-monitoring/test        — Test SSH connection (?server_id=)
  GET  /server-monitoring/metrics     — CPU / Memory / Load / Uptime (?server_id=)
  GET  /server-monitoring/top-processes — top processes by CPU / memory (?server_id=)
  GET  /tablespace-usage              — Top-5 tablespace (Oracle)
  GET  /tablespace-datafiles          — Existing datafiles for a tablespace
  POST /tablespace-add-datafile       — ALTER TABLESPACE ADD DATAFILE
  GET  /disk-usage                    — Disk usage via SSH df (?server_id=)
  GET  /pending-jobs                  — Concurrent requests Oracle
"""

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.dependencies import require_role, CurrentUser, Roles
from app.services.it_service import ITService, OracleITService, ServerMonitorService

router = APIRouter()


# ── Legacy / summary ────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.IT))):
    return await ITService().get_summary()


@router.get("/servers")
async def get_servers(user: CurrentUser = Depends(require_role(Roles.IT))):
    return await ITService().get_server_status()


@router.get("/tickets")
async def get_tickets(user: CurrentUser = Depends(require_role(Roles.IT))):
    return await ITService().get_ticket_summary()


@router.get("/weekly-report")
async def get_weekly_report(user: CurrentUser = Depends(require_role(Roles.IT))):
    return await ITService().get_weekly_report_data()


# ── Server Process Monitoring ────────────────────────────────────────────────
# Hosts and SSH logins come from Server Control (entries with monitoring on);
# every reading is also stored for CoChat — see app.services.it_monitoring_store.

@router.get("/server-monitoring/servers")
async def get_monitored_servers(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Every server in Server Control (no secrets); `problem` says why one can't be polled."""
    servers = await run_in_threadpool(ServerMonitorService().servers_public)
    return {"success": True, "data": servers}


@router.get("/server-monitoring/test")
async def test_connection(server_id: Optional[int] = None, user: CurrentUser = Depends(require_role(Roles.IT))):
    """Test the SSH login Server Control holds for this server."""
    return await ServerMonitorService().test_connection(server_id)


@router.get("/server-monitoring/metrics")
async def get_metrics(server_id: Optional[int] = None, auto: bool = False,
                      user: CurrentUser = Depends(require_role(Roles.IT))):
    """CPU / Memory / Load / Uptime / Swap / CPU-count via SSH. auto=true marks an
    auto-refresh tick, whose stored rows are throttled to one per minute."""
    return await ServerMonitorService().get_metrics(server_id, auto)


@router.get("/server-monitoring/top-processes")
async def get_top_processes(server_id: Optional[int] = None, auto: bool = False,
                            user: CurrentUser = Depends(require_role(Roles.IT))):
    """Top 8 processes by CPU and by Memory via SSH ps."""
    return await ServerMonitorService().get_top_processes(server_id, auto)


# ── Tablespace ───────────────────────────────────────────────────────────────

class AddDatafileIn(BaseModel):
    tablespace_name: str
    file_path: str
    size_value: float
    size_unit: str        # "MB" or "GB"
    autoextend: bool = False


class ResizeDatafileIn(BaseModel):
    file_path: str
    add_value: float      # amount to add (not the new total)
    add_unit: str         # "MB" or "GB"


@router.get("/tablespace-usage")
async def get_tablespace(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Top-5 tablespace usage from Oracle DBA_TABLESPACE_USAGE_METRICS."""
    return await OracleITService().get_tablespace()


@router.get("/tablespace-datafiles")
async def get_tablespace_datafiles(
    tablespace_name: str,
    user: CurrentUser = Depends(require_role(Roles.IT)),
):
    """Existing datafiles for a tablespace (DBA_DATA_FILES) — for location reference."""
    return await OracleITService().get_tablespace_datafiles(tablespace_name)


@router.post("/tablespace-add-datafile")
async def add_tablespace_datafile(
    body: AddDatafileIn,
    user: CurrentUser = Depends(require_role(Roles.IT)),
):
    """Execute ALTER TABLESPACE … ADD DATAFILE to extend a tablespace."""
    return await OracleITService().add_tablespace_datafile(
        body.tablespace_name, body.file_path, body.size_value, body.size_unit, body.autoextend
    )


@router.post("/tablespace-resize-datafile")
async def resize_tablespace_datafile(
    body: ResizeDatafileIn,
    user: CurrentUser = Depends(require_role(Roles.IT)),
):
    """Extend an existing datafile by <add_value><add_unit> via ALTER DATABASE DATAFILE … RESIZE."""
    return await OracleITService().resize_tablespace_datafile(
        body.file_path, body.add_value, body.add_unit
    )


# ── Oracle Sessions ──────────────────────────────────────────────────────────

class KillSessionIn(BaseModel):
    sid: int
    serial_num: int


@router.get("/oracle-sessions")
async def get_oracle_sessions(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Active Oracle user sessions from v$session + v$session_wait."""
    return await OracleITService().get_oracle_sessions()


@router.post("/oracle-kill-session")
async def kill_oracle_session(
    body: KillSessionIn,
    user: CurrentUser = Depends(require_role(Roles.IT)),
):
    """Kill Oracle session via ALTER SYSTEM DISCONNECT SESSION 'sid,serial#' IMMEDIATE."""
    return await OracleITService().kill_oracle_session(body.sid, body.serial_num)


# ── Disk Usage ───────────────────────────────────────────────────────────────

@router.get("/disk-usage")
async def get_disk_usage(server_id: Optional[int] = None, user: CurrentUser = Depends(require_role(Roles.IT))):
    """Disk usage per mount point — SSH df -P on one Server Control server."""
    return await ServerMonitorService().get_disk_usage(server_id)


# ── Pending Jobs ─────────────────────────────────────────────────────────────

@router.get("/pending-jobs")
async def get_pending_jobs(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Concurrent requests from Oracle FND_CONCURRENT_REQUESTS."""
    return await OracleITService().get_pending_jobs()
