"""
ETL Admin — IT dashboard control tab for the EIS data warehouse's Oracle EBS
extraction jobs. Moved here from the EIS dashboard (was under "EIS > ETL
Admin") since running/monitoring ETL jobs is an IT/ops concern, same
reasoning as EBS Backup Recovery and VPN/HikCentral living here rather than
under the business-facing dashboards.

  GET  /status              — recent job run history (eis.etl_job_log)
  POST /trigger/{job_name}   — manually run a job for a given year/month
  POST /stop/{job_name}      — revoke a running job
  GET  /job-data/{job_name}  — preview of imported rows (destination, eis.fact_*)
  GET  /schedule             — job cadence + Oracle source / Postgres destination tables
  GET  /source/{job_name}    — the job's actual Python/SQL extraction code
                                (read live via inspect.getsource — always exactly
                                what's really running, never a stale hand-copied
                                summary)

Role-gated at the router level in main.py (require_role(Roles.IT)).
"""
import inspect
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
from app.eis_database import get_eis_db as get_db

router = APIRouter()

# In-memory map: job_name → latest celery task_id (survives until backend restart)
_active_task_ids: dict[str, str] = {}


class TriggerParams(BaseModel):
    year: Optional[int] = None
    month: Optional[int] = None


@router.get("/status")
async def etl_status(limit: int = Query(10), db: AsyncSession = Depends(get_db)):
    q = text("""
        SELECT id, job_name, status, started_at, finished_at,
               records_processed, error_message, run_params,
               EXTRACT(EPOCH FROM (COALESCE(finished_at, NOW()) - started_at))::int AS duration_secs
        FROM eis.etl_job_log
        ORDER BY started_at DESC
        LIMIT :limit
    """)
    result = await db.execute(q, {"limit": limit})
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.post("/trigger/{job_name}")
async def trigger_etl(job_name: str, params: TriggerParams):
    from app.tasks.celery_app import celery_app
    valid_jobs = [
        "etl_sales", "etl_cogs", "etl_production", "etl_financial",
        "etl_employee", "etl_inventory", "etl_ar_ap", "etl_budget", "etl_po",
    ]
    if job_name not in valid_jobs:
        raise HTTPException(status_code=400, detail=f"Unknown job. Valid: {valid_jobs}")

    result = celery_app.send_task(
        f"app.tasks.etl_tasks.{job_name}",
        kwargs={"year": params.year, "month": params.month},
    )
    _active_task_ids[job_name] = result.id
    return {"message": f"Job {job_name} triggered", "task_id": result.id}


@router.post("/stop/{job_name}")
async def stop_etl(job_name: str, db: AsyncSession = Depends(get_db)):
    """Revoke the running Celery task and mark the log entry as stopped."""
    import asyncio
    from app.tasks.celery_app import celery_app

    task_id = _active_task_ids.pop(job_name, None)
    if task_id:
        try:
            # Run blocking Celery control call in thread pool to avoid blocking async loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM", reply=False),
            )
        except Exception:
            pass  # revoke failure should not prevent DB update

    # Mark the most recent running log entry as stopped
    await db.execute(text("""
        UPDATE eis.etl_job_log
           SET status = 'stopped',
               finished_at = NOW(),
               error_message = 'Dihentikan oleh user'
         WHERE id = (
             SELECT id FROM eis.etl_job_log
              WHERE job_name = :job AND status = 'running'
              ORDER BY started_at DESC
              LIMIT 1
         )
    """), {"job": job_name})
    await db.commit()
    return {"message": f"Job {job_name} dihentikan"}


@router.get("/job-data/{job_name}")
async def get_job_data(
    job_name: str,
    year: int = Query(...),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return last imported rows from the fact table for the given job."""
    period_filter = "AND per.period_num = :month" if month else ""
    params: dict = {"year": year}
    if month:
        params["month"] = month

    queries: dict[str, str] = {
        "etl_cogs": f"""
            SELECT p.product_code, p.product_name, p.business_type,
                   per.period_name, per.period_num,
                   ROUND(c.sales_amount::numeric, 2)  AS sales_amount,
                   ROUND(c.cogs_total::numeric, 2)    AS cogs_total,
                   ROUND(c.ebit_amount::numeric, 2)   AS ebit_amount,
                   CASE WHEN c.sales_amount > 0
                        THEN ROUND((c.ebit_amount / c.sales_amount * 100)::numeric, 1)
                        ELSE 0 END                    AS ebit_pct
            FROM eis.fact_cogs c
            JOIN eis.dim_period  per ON c.period_id  = per.id
            JOIN eis.dim_product p   ON c.product_id = p.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY c.sales_amount DESC
            LIMIT 50
        """,
        "etl_sales": f"""
            SELECT per.period_name, per.period_num, s.business_type,
                   ROUND(s.bp_amount::numeric, 2)     AS bp_amount,
                   ROUND(s.actual_amount::numeric, 2)  AS actual_amount,
                   CASE WHEN s.bp_amount > 0
                        THEN ROUND((s.actual_amount / s.bp_amount * 100)::numeric, 1)
                        ELSE 0 END                     AS achievement_pct
            FROM eis.fact_sales s
            JOIN eis.dim_period per ON s.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
              AND s.product_id IS NULL
            ORDER BY per.period_num, s.business_type
        """,
        "etl_production": f"""
            SELECT per.period_name, per.period_num, p.segment,
                   ROUND(p.bp_qty::numeric, 0)     AS bp_qty,
                   ROUND(p.actual_qty::numeric, 0)  AS actual_qty,
                   ROUND(p.batch_size::numeric, 0)  AS batch_size,
                   ROUND(p.yield_qty::numeric, 0)   AS yield_qty,
                   CASE WHEN p.batch_size > 0
                        THEN ROUND((p.yield_qty / p.batch_size * 100)::numeric, 1)
                        ELSE 0 END                  AS yield_pct
            FROM eis.fact_production p
            JOIN eis.dim_period per ON p.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num, p.segment
        """,
        "etl_financial": f"""
            SELECT per.period_name, per.period_num,
                   ROUND(f.net_profit_actual::numeric, 2)            AS net_profit_actual,
                   ROUND(f.net_profit_bp::numeric, 2)                AS net_profit_bp,
                   ROUND(f.net_profit_actual_cumulative::numeric, 2) AS profit_ytd,
                   ROUND(f.cf_ending_balance_actual::numeric, 2)     AS cashflow_actual,
                   ROUND(f.cf_ending_balance_bp::numeric, 2)         AS cashflow_bp
            FROM eis.fact_financial f
            JOIN eis.dim_period per ON f.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num
        """,
        "etl_employee": f"""
            SELECT per.period_name, per.period_num, e.dept_group,
                   e.headcount, e.plan_headcount,
                   e.resigned_cumulative
            FROM eis.fact_employee e
            JOIN eis.dim_period per ON e.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num, e.dept_group
        """,
        "etl_ar_ap": f"""
            SELECT per.period_name, per.period_num,
                   ROUND(r.dso_ar_avg::numeric, 2)  AS ar_balance,
                   ROUND(r.dso_days::numeric, 1)    AS dso_days,
                   ROUND(r.dpo_ap_avg::numeric, 2)  AS ap_balance,
                   ROUND(r.dpo_days::numeric, 1)    AS dpo_days,
                   ROUND((r.dso_days + COALESCE(r.dio_days,0) - r.dpo_days)::numeric, 1) AS nwc_days
            FROM eis.fact_financial_ratio r
            JOIN eis.dim_period per ON r.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num
        """,
        "etl_inventory": f"""
            SELECT per.period_name, per.period_num,
                   ROUND(r.dio_inv_avg::numeric, 2) AS inventory_value,
                   ROUND(r.dio_cogs::numeric, 2)    AS cogs_amount,
                   ROUND(r.dio_days::numeric, 1)    AS dio_days
            FROM eis.fact_financial_ratio r
            JOIN eis.dim_period per ON r.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
              AND r.dio_days IS NOT NULL
            ORDER BY per.period_num
        """,
        "etl_budget": f"""
            SELECT per.period_name, per.period_num, b.dept_group,
                   ROUND(b.bp_amount::numeric, 2)     AS budget,
                   ROUND(b.actual_amount::numeric, 2) AS actual,
                   CASE WHEN b.bp_amount > 0
                        THEN ROUND((b.actual_amount / b.bp_amount * 100)::numeric, 1)
                        ELSE 0 END                    AS absorption_pct
            FROM eis.fact_budget b
            JOIN eis.dim_period per ON b.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num, b.dept_group
        """,
        "etl_po": f"""
            SELECT per.period_name, per.period_num, p.material_type,
                   p.po_count,
                   ROUND(p.po_value::numeric, 2) AS po_value
            FROM eis.fact_purchasing p
            JOIN eis.dim_period per ON p.period_id = per.id
            WHERE per.fiscal_year = :year {period_filter}
            ORDER BY per.period_num, p.material_type
        """,
    }

    sql = queries.get(job_name)
    if not sql:
        raise HTTPException(status_code=400, detail=f"No data preview for job: {job_name}")

    result = await db.execute(text(sql), params)
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows, "columns": list(rows[0].keys()) if rows else []}


# Oracle EBS source tables + Postgres (eis schema) destination table, one
# entry per job — curated by hand against eis_etl_tasks.py rather than
# regex-scraped from the SQL (date-arithmetic expressions like
# `EXTRACT(... FROM x.due_date)` look like false-positive "FROM table"
# matches to a naive scanner). The /source endpoint below is the
# always-accurate complement — read straight from the running code.
_JOB_META = {
    "etl_sales":      {"frequency": "Daily",  "schedule": "02:00 AM WIB", "source": "Oracle OE (Sales Order)",
                        "oracle_tables": ["oe_order_headers_all", "oe_order_lines_all", "oe_transaction_types_tl"],
                        "destination_table": "eis.fact_sales"},
    "etl_cogs":       {"frequency": "Daily",  "schedule": "02:15 AM WIB", "source": "Oracle OE (Product & COGS)",
                        "oracle_tables": ["oe_order_headers_all", "oe_order_lines_all", "oe_transaction_types_tl"],
                        "destination_table": "eis.fact_cogs, eis.dim_product"},
    "etl_ar_ap":      {"frequency": "Daily",  "schedule": "02:30 AM WIB", "source": "Oracle AR/AP",
                        "oracle_tables": ["ar_payment_schedules_all", "ap_invoices_all", "ap_payment_schedules_all"],
                        "destination_table": "eis.fact_financial_ratio"},
    "etl_inventory":  {"frequency": "Daily",  "schedule": "03:00 AM WIB", "source": "Oracle INV",
                        "oracle_tables": ["mtl_onhand_quantities_detail", "cst_item_costs"],
                        "destination_table": "eis.fact_financial_ratio"},
    "etl_production": {"frequency": "Daily",  "schedule": "03:15 AM WIB", "source": "Oracle WIP / GME",
                        "oracle_tables": ["gme_batch_header", "gme_material_details", "wip_discrete_jobs"],
                        "destination_table": "eis.fact_production"},
    "etl_employee":   {"frequency": "Weekly", "schedule": "Mon 02:00 AM", "source": "Oracle HR",
                        "oracle_tables": ["per_all_people_f", "per_all_assignments_f", "hr_all_organization_units"],
                        "destination_table": "eis.fact_employee"},
    "etl_financial":  {"frequency": "Daily",  "schedule": "04:00 AM WIB", "source": "Oracle GL",
                        "oracle_tables": ["gl_balances", "gl_code_combinations"],
                        "destination_table": "eis.fact_financial"},
    "etl_budget":     {"frequency": "Daily",  "schedule": "04:30 AM WIB", "source": "Oracle GL (OPEX)",
                        "oracle_tables": ["gl_balances", "gl_code_combinations"],
                        "destination_table": "eis.fact_budget"},
    "etl_po":         {"frequency": "Daily",  "schedule": "05:00 AM WIB", "source": "Oracle PO (Purchase Order)",
                        "oracle_tables": ["po_headers_all", "po_lines_all", "po_line_locations_all"],
                        "destination_table": "eis.fact_purchasing"},
}


@router.get("/schedule")
async def etl_schedule():
    return {"data": [{"job": job, **meta} for job, meta in _JOB_META.items()]}


@router.get("/source/{job_name}")
async def get_etl_source(job_name: str):
    """The job's real Oracle extraction code, read live from eis_etl_tasks.py
    via inspect.getsource() — this is the single source of truth for "what
    query/table is actually used", guaranteed to never drift out of sync
    with what's really running (unlike a hand-maintained description)."""
    if job_name not in _JOB_META:
        raise HTTPException(400, f"Unknown job: {job_name}")
    from app.tasks import eis_etl_tasks
    fn = getattr(eis_etl_tasks, job_name, None)
    if fn is None:
        raise HTTPException(404, f"No source found for job: {job_name}")
    return {"job": job_name, "source": inspect.getsource(fn)}
