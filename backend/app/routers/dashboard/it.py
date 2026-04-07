"""
IT Dashboard Router
─────────────────────────────────────────
Route prefix : /api/v1/dashboard/it
Required role: it_staff OR admin

Endpoints:
  GET  /summary                       — KPI cards
  GET  /server-monitoring/config      — SSH config (password masked)
  POST /server-monitoring/config      — Save SSH config
  GET  /server-monitoring/test        — Test SSH connection
  GET  /server-monitoring/metrics     — CPU / Memory / Load / Uptime
  GET  /tablespace-usage              — Top-5 tablespace (Oracle)
  GET  /disk-usage                    — Disk usage via SSH df
  GET  /pending-jobs                  — Concurrent requests Oracle
  GET  /workflow-error                — Oracle Workflow errors
"""

from fastapi import APIRouter, Depends
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


# ── Server Monitoring ────────────────────────────────────────────────────────

class ServerConfigIn(BaseModel):
    ip: str
    port: int = 22
    username: str
    password: str


@router.get("/server-monitoring/config")
async def get_server_config(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Return current SSH config (password masked)."""
    return {"success": True, "data": ServerMonitorService().get_config_public()}


@router.post("/server-monitoring/config")
async def save_server_config(
    body: ServerConfigIn,
    user: CurrentUser = Depends(require_role(Roles.IT)),
):
    """Save SSH credentials to config file."""
    svc = ServerMonitorService()
    svc.save_config(body.model_dump())
    return {"success": True, "message": "Konfigurasi disimpan"}


@router.get("/server-monitoring/test")
async def test_connection(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Test SSH connection with saved config."""
    return await ServerMonitorService().test_connection()


@router.get("/server-monitoring/metrics")
async def get_metrics(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Get CPU / Memory / Load / Uptime from server via SSH."""
    return await ServerMonitorService().get_metrics()


# ── Tablespace ───────────────────────────────────────────────────────────────

@router.get("/tablespace-usage")
async def get_tablespace(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Top-5 tablespace usage from Oracle DBA_TABLESPACE_USAGE_METRICS."""
    return await OracleITService().get_tablespace()


# ── Disk Usage ───────────────────────────────────────────────────────────────

@router.get("/disk-usage")
async def get_disk_usage(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Disk usage per mount point — SSH df -P from DB (172.21.2.201) + App (172.21.2.202)."""
    return await ServerMonitorService().get_disk_usage_all()


# ── Pending Jobs ─────────────────────────────────────────────────────────────

@router.get("/pending-jobs")
async def get_pending_jobs(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Concurrent requests from Oracle FND_CONCURRENT_REQUESTS."""
    return await OracleITService().get_pending_jobs()


# ── Workflow Error ────────────────────────────────────────────────────────────

@router.get("/workflow-error")
async def get_workflow_error(user: CurrentUser = Depends(require_role(Roles.IT))):
    """Oracle Workflow error/pending items from WF_ITEM_ACTIVITY_STATUSES."""
    return await OracleITService().get_workflow_errors()
