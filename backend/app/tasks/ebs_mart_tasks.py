"""
ETL for the EBS Data Mart (blueprint section 3, "Aturan ETL"), phase 1: AP
and Inventory. Oracle EBS -> core.* -> REFRESH mart.*.

  etl_mart_ap         incremental on a composite watermark
                      GREATEST(header, child last_update_date) with a 1-hour
                      overlap; full_refresh=True reloads everything and is the
                      weekly delete reconciliation.
  etl_mart_inventory  full snapshot (on-hand is a balance, not a ledger — see
                      etl_inventory's docstring for what filtering it by date
                      did), plus the small masters: subinventory and item.
  refresh_ebs_marts   REFRESH every mart; scheduled daily because days_overdue
                      and days_to_expiry are computed at refresh time.

Every run is logged in eis.etl_job_log (read as meta.etl_run_log) with
trigger type, watermark range and rows upserted. A session advisory lock per
job keeps the manual button and the schedule from running the same job twice
at once (pg_try_advisory_lock): the second one is logged as skipped, not queued.

Task names use the app.tasks.etl_tasks.* prefix like every other ETL job, so
IT > ETL Admin's generic trigger endpoint reaches them unchanged.
"""
import json
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

from app.config import get_settings
from app.database import get_oracle_connection
from app.services.ebs_mart.constants import (
    EBS_OPERATING_UNIT_ID, EBS_PROCESS_ORG_ID, INVENTORY_CATEGORY_SET,
)
from app.services.ebs_mart.mart_sql import MARTS_BY_JOB
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

_BATCH = 2000


def _pg():
    return psycopg2.connect(settings.eis_database_url_rw)


class _Run:
    """One logged, locked ETL run."""

    def __init__(self, job: str, trigger_type: str, triggered_by: str | None, params: dict):
        self.job = job
        self.pg = _pg()
        self.cur = self.pg.cursor()
        self.cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"ebs_mart:{job}",))
        self.locked = self.cur.fetchone()[0]
        self.pg.commit()
        self.cur.execute(
            """INSERT INTO eis.etl_job_log (job_name, status, run_params, trigger_type, triggered_by)
               VALUES (%s, 'running', %s, %s, %s) RETURNING id""",
            (job, json.dumps(params), trigger_type, triggered_by),
        )
        self.log_id = self.cur.fetchone()[0]
        self.pg.commit()

    def finish(self, status: str, rows_read=0, rows_upserted=0, error=None, wm_from=None, wm_to=None):
        self.cur.execute(
            """UPDATE eis.etl_job_log
                  SET status = %s, finished_at = NOW(), records_processed = %s, rows_upserted = %s,
                      error_message = %s, watermark_from = %s, watermark_to = %s
                WHERE id = %s""",
            (status, rows_read, rows_upserted, error, wm_from, wm_to, self.log_id),
        )
        self.pg.commit()

    def close(self):
        try:
            if self.locked:
                self.cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"ebs_mart:{self.job}",))
                self.pg.commit()
        finally:
            self.pg.close()


def _get_watermark(cur, job: str, stream: str):
    cur.execute("SELECT watermark FROM meta.etl_watermark WHERE job_name = %s AND stream = %s", (job, stream))
    row = cur.fetchone()
    return row[0] if row else None


def _set_watermark(cur, job: str, stream: str, value):
    if value is None:
        return
    cur.execute(
        """INSERT INTO meta.etl_watermark (job_name, stream, watermark, updated_at) VALUES (%s, %s, %s, now())
           ON CONFLICT (job_name, stream) DO UPDATE
              SET watermark = GREATEST(meta.etl_watermark.watermark, EXCLUDED.watermark), updated_at = now()""",
        (job, stream, value),
    )


def _refresh_after(job: str):
    from app.services.ebs_mart.schema import refresh_marts
    marts = MARTS_BY_JOB.get(job)
    if marts:
        result = refresh_marts(marts)
        logger.info("[%s] mart refresh: %s", job, result)


def refresh_marts_for_job(job: str):
    """Hook for existing ETL jobs that feed a mart (etl_inventory_txn ->
    inv_movement_daily). Never raises: a refresh failure must not turn a
    successful load into a failed job."""
    try:
        _refresh_after(job)
    except Exception as e:
        logger.warning("[%s] mart refresh failed: %s", job, e)


def _upsert(cur, table: str, columns: list[str], key: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in key)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}, loaded_at = now()"
    )
    total = 0
    for i in range(0, len(rows), _BATCH):
        chunk = rows[i:i + _BATCH]
        execute_values(cur, sql, chunk, page_size=_BATCH)
        total += len(chunk)
    return total


def _num(v):
    return float(v) if v is not None else None


# ── AP ───────────────────────────────────────────────────────────────────────

# Blueprint 6.1, with two changes that keep the mart equal to the Dashboard's
# AP Outstanding report: IDR is invoice_amount's own base-amount ratio (what
# that report uses) rather than exchange_rate, and the liability account is
# carried so the mart can apply the same account whitelist. Cancelled invoices
# are extracted, not filtered: a cancellation is an update, and filtering it
# out here would leave the old open row in core forever.
_AP_SCHEDULE_SQL = """
    SELECT ai.invoice_id, aps.payment_num, ai.invoice_num, ai.invoice_type_lookup_code,
           ai.invoice_date, ai.gl_date, ai.invoice_currency_code, ai.invoice_amount,
           NVL(ai.base_amount, ai.invoice_amount)                                    AS invoice_amount_idr,
           SUBSTR(ai.description, 1, 240),
           sup.vendor_id, sup.segment1, sup.vendor_name, ss.vendor_site_code,
           gcc.segment4                                                              AS liability_account,
           aps.due_date, aps.gross_amount, aps.amount_remaining,
           aps.amount_remaining * NVL(ai.base_amount, ai.invoice_amount)
               / DECODE(ai.invoice_amount, 0, 1, ai.invoice_amount)                  AS amount_remaining_idr,
           aps.payment_status_flag, ai.cancelled_date,
           GREATEST(ai.last_update_date, aps.last_update_date)                       AS src_last_update
      FROM ap_invoices_all ai
      JOIN ap_suppliers sup              ON sup.vendor_id = ai.vendor_id
      LEFT JOIN ap_supplier_sites_all ss ON ss.vendor_site_id = ai.vendor_site_id
      JOIN ap_payment_schedules_all aps  ON aps.invoice_id = ai.invoice_id
      LEFT JOIN gl_code_combinations gcc ON gcc.code_combination_id = ai.accts_pay_code_combination_id
     WHERE ai.org_id = :org_id
       {wm}
"""
_AP_SCHEDULE_COLS = [
    "invoice_id", "payment_num", "invoice_num", "invoice_type", "invoice_date", "gl_date",
    "invoice_currency_code", "invoice_amount", "invoice_amount_idr", "description", "vendor_id",
    "vendor_num", "vendor_name", "vendor_site_code", "liability_account", "due_date", "gross_amount",
    "amount_remaining", "amount_remaining_idr", "payment_status_flag", "cancelled_date", "src_last_update",
]

# Payment applications. Watermark over both tables: voiding a check changes
# AP_CHECKS_ALL, not the application row.
_AP_PAYMENT_SQL = """
    SELECT aip.invoice_payment_id, aip.invoice_id, aip.payment_num, ac.check_id,
           TO_CHAR(ac.check_number), ac.check_date, aip.accounting_date,
           ac.payment_method_code, ac.bank_account_name, ac.status_lookup_code,
           aip.amount, NVL(aip.invoice_base_amount, aip.amount)                     AS amount_idr,
           aip.reversal_flag, ac.void_date,
           GREATEST(aip.last_update_date, ac.last_update_date)                      AS src_last_update
      FROM ap_invoice_payments_all aip
      JOIN ap_checks_all ac ON ac.check_id = aip.check_id
     WHERE aip.org_id = :org_id
       {wm}
"""
_AP_PAYMENT_COLS = [
    "invoice_payment_id", "invoice_id", "payment_num", "check_id", "payment_number", "payment_date",
    "accounting_date", "payment_method", "bank_account_name", "payment_status", "amount_entered",
    "amount_idr", "reversal_flag", "void_date", "src_last_update",
]

# Active holds only, reloaded whole each run: a release is an update that
# removes the row from "active", and the set is small.
_AP_HOLD_SQL = """
    SELECT ah.hold_id, ah.invoice_id, ah.hold_lookup_code, ahc.description, SUBSTR(ah.hold_reason, 1, 240),
           ah.hold_date
      FROM ap_holds_all ah
      LEFT JOIN ap_hold_codes ahc ON ahc.hold_lookup_code = ah.hold_lookup_code
     WHERE ah.org_id = :org_id
       AND ah.release_lookup_code IS NULL
"""


def _extract_incremental(cur_ora, sql: str, wm_col: str, watermark, full: bool):
    """Run an extract with the composite-watermark clause. Oracle date
    arithmetic: :wm - 1/24 is one hour of overlap, so a row committed with a
    last_update_date slightly older than a row we already saw is not missed."""
    params = {"org_id": EBS_OPERATING_UNIT_ID}
    if full or watermark is None:
        cur_ora.execute(sql.format(wm=""), params)
    else:
        params["wm"] = watermark
        cur_ora.execute(sql.format(wm=f"AND {wm_col} >= :wm - 1/24"), params)
    return cur_ora.fetchall()


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_ap")
def etl_mart_ap(year: int = None, month: int = None, full_refresh: bool = False,
                trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_ap"
    run = _Run(job, trigger_type, triggered_by, {"full_refresh": full_refresh})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_upserted = 0
    wm_from = wm_to = None
    try:
        cur = run.cur
        wm_sched = _get_watermark(cur, job, "schedules")
        wm_pay = _get_watermark(cur, job, "payments")
        wm_from = None if full_refresh else min((w for w in (wm_sched, wm_pay) if w), default=None)

        ora = get_oracle_connection()
        try:
            cur_ora = ora.cursor()
            cur_ora.arraysize = _BATCH
            sched = _extract_incremental(
                cur_ora, _AP_SCHEDULE_SQL, "GREATEST(ai.last_update_date, aps.last_update_date)", wm_sched, full_refresh)
            pays = _extract_incremental(
                cur_ora, _AP_PAYMENT_SQL, "GREATEST(aip.last_update_date, ac.last_update_date)", wm_pay, full_refresh)
            cur_ora.execute(_AP_HOLD_SQL, {"org_id": EBS_OPERATING_UNIT_ID})
            holds = cur_ora.fetchall()
        finally:
            ora.close()
        rows_read = len(sched) + len(pays) + len(holds)

        # Weekly reconciliation: a full load replaces core wholesale, which
        # is what removes rows deleted in Oracle (interface cleanups, purged
        # schedules). Same transaction as the reload, so readers of the mart
        # never see an empty core — the mart itself only changes at refresh.
        if full_refresh:
            cur.execute("TRUNCATE core.fact_ap_payment_schedule, core.fact_ap_payment")

        sched_rows = [
            (int(r[0]), int(r[1]), r[2], r[3], r[4], r[5], r[6], _num(r[7]), _num(r[8]), r[9], int(r[10]),
             r[11], r[12], r[13], r[14], r[15], _num(r[16]), _num(r[17]), _num(r[18]), r[19], r[20], r[21])
            for r in sched
        ]
        pay_rows = [
            (int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None, int(r[3]), r[4], r[5], r[6], r[7],
             r[8], r[9], _num(r[10]), _num(r[11]), r[12], r[13], r[14])
            for r in pays
        ]
        rows_upserted += _upsert(cur, "core.fact_ap_payment_schedule", _AP_SCHEDULE_COLS,
                                 ["invoice_id", "payment_num"], sched_rows)
        rows_upserted += _upsert(cur, "core.fact_ap_payment", _AP_PAYMENT_COLS, ["invoice_payment_id"], pay_rows)

        cur.execute("TRUNCATE core.fact_ap_hold")
        if holds:
            execute_values(
                cur,
                "INSERT INTO core.fact_ap_hold (hold_id, invoice_id, hold_code, hold_desc, hold_reason, hold_date) VALUES %s",
                [(int(h[0]), int(h[1]), h[2], h[3], h[4], h[5]) for h in holds],
            )
            rows_upserted += len(holds)

        new_sched = max((r[-1] for r in sched_rows if r[-1]), default=None)
        new_pay = max((r[-1] for r in pay_rows if r[-1]), default=None)
        _set_watermark(cur, job, "schedules", new_sched)
        _set_watermark(cur, job, "payments", new_pay)
        wm_to = max([w for w in (new_sched, new_pay, wm_sched, wm_pay) if w], default=None)
        run.pg.commit()

        run.finish("success", rows_read, rows_upserted, wm_from=wm_from, wm_to=wm_to)
        logger.info("[%s] read=%s upserted=%s full=%s", job, rows_read, rows_upserted, full_refresh)
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_upserted, error=str(e), wm_from=wm_from)
        run.close()
        raise
    run.close()
    _refresh_after(job)
    return {"status": "success", "rows_read": rows_read, "rows_upserted": rows_upserted}


# ── Inventory ────────────────────────────────────────────────────────────────

# Blueprint 6.3, plus locator name, lot status and origination date.
_ONHAND_SQL = """
    SELECT moqd.organization_id, mp.organization_code, moqd.inventory_item_id,
           msi.segment1, msi.description, msi.primary_uom_code,
           moqd.subinventory_code, moqd.locator_id, mil.concatenated_segments,
           moqd.lot_number, mms.status_code, mln.origination_date, mln.expiration_date,
           SUM(moqd.primary_transaction_quantity)
      FROM mtl_onhand_quantities_detail moqd
      JOIN mtl_system_items_b msi
           ON msi.inventory_item_id = moqd.inventory_item_id
          AND msi.organization_id   = moqd.organization_id
      JOIN mtl_parameters mp ON mp.organization_id = moqd.organization_id
      LEFT JOIN mtl_lot_numbers mln
           ON mln.inventory_item_id = moqd.inventory_item_id
          AND mln.organization_id   = moqd.organization_id
          AND mln.lot_number        = moqd.lot_number
      LEFT JOIN mtl_material_statuses_vl mms ON mms.status_id = mln.status_id
      LEFT JOIN mtl_item_locations_kfv mil
           ON mil.inventory_location_id = moqd.locator_id
          AND mil.organization_id       = moqd.organization_id
     WHERE moqd.organization_id = :org
     GROUP BY moqd.organization_id, mp.organization_code, moqd.inventory_item_id, msi.segment1,
              msi.description, msi.primary_uom_code, moqd.subinventory_code, moqd.locator_id,
              mil.concatenated_segments, moqd.lot_number, mms.status_code, mln.origination_date,
              mln.expiration_date
"""

_SUBINV_SQL = """
    SELECT secondary_inventory_name, organization_id, description, availability_type, disable_date
      FROM mtl_secondary_inventories
     WHERE organization_id = :org
"""

_ITEM_SQL = """
    SELECT msi.inventory_item_id, msi.segment1, msi.description, msi.primary_uom_code,
           MIN(mcb.segment1)
      FROM mtl_system_items_b msi
      LEFT JOIN mtl_item_categories_v miv
             ON miv.inventory_item_id = msi.inventory_item_id
            AND miv.organization_id   = msi.organization_id
            AND miv.category_set_name = :cat_set
      LEFT JOIN mtl_categories_b mcb ON mcb.category_id = miv.category_id
     WHERE msi.organization_id = :org
     GROUP BY msi.inventory_item_id, msi.segment1, msi.description, msi.primary_uom_code
"""


def guess_subinventory_type(code: str | None, description: str | None, availability_type) -> str:
    """Best guess until Warehouse/QA's official list is entered in
    meta.subinventory_class (which always wins in the mart). Name first —
    REJ/QUAR/KARANTINA are how these are conventionally named — then
    Oracle's own signal: a non-nettable subinventory (availability_type 2)
    is not stock the planner can use."""
    text = f"{code or ''} {description or ''}".upper()
    if any(k in text for k in ("REJ", "RJT", "DAMAGE", "RUSAK", "DESTROY", "MUSNAH")):
        return "REJECT"
    if any(k in text for k in ("QUAR", "KARANT", "QRT", "HOLD", "QC")):
        return "QUARANTINE"
    if availability_type is not None and int(availability_type) == 2:
        return "QUARANTINE"
    return "GOOD"


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_inventory")
def etl_mart_inventory(year: int = None, month: int = None,
                       trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_inventory"
    run = _Run(job, trigger_type, triggered_by, {"organization_id": EBS_PROCESS_ORG_ID})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_loaded = 0
    try:
        ora = get_oracle_connection()
        try:
            cur_ora = ora.cursor()
            cur_ora.arraysize = _BATCH
            cur_ora.execute(_ONHAND_SQL, {"org": EBS_PROCESS_ORG_ID})
            onhand = cur_ora.fetchall()
            cur_ora.execute(_SUBINV_SQL, {"org": EBS_PROCESS_ORG_ID})
            subinv = cur_ora.fetchall()
            cur_ora.execute(_ITEM_SQL, {"org": EBS_PROCESS_ORG_ID, "cat_set": INVENTORY_CATEGORY_SET})
            items = cur_ora.fetchall()
        finally:
            ora.close()
        rows_read = len(onhand) + len(subinv) + len(items)

        cur = run.cur
        # Snapshot tables are replaced whole inside one transaction: readers
        # of core see either the previous snapshot or the new one.
        cur.execute("TRUNCATE core.snap_onhand_lot, core.dim_subinventory, core.dim_item")

        onhand_rows = []
        for r in onhand:
            (org_id, org_code, item_id, item_code, item_desc, uom, subinv_code, locator_id, locator,
             lot, lot_status, orig_date, exp_date, qty) = r
            row_key = "|".join(str(x) for x in (item_id, subinv_code, locator_id or "", lot or ""))
            onhand_rows.append((
                row_key, int(org_id), org_code, int(item_id), item_code, item_desc, uom, subinv_code,
                int(locator_id) if locator_id is not None else None, locator, lot, lot_status,
                orig_date, exp_date, _num(qty),
            ))
        if onhand_rows:
            execute_values(cur, """
                INSERT INTO core.snap_onhand_lot
                    (row_key, organization_id, organization_code, inventory_item_id, item_code, item_desc, uom,
                     subinventory_code, locator_id, locator, lot_number, lot_status, origination_date,
                     expiration_date, onhand_qty)
                VALUES %s
            """, onhand_rows, page_size=_BATCH)

        if subinv:
            execute_values(cur, """
                INSERT INTO core.dim_subinventory
                    (subinventory_code, organization_id, description, availability_type, disable_date, guessed_type)
                VALUES %s
            """, [(s[0], int(s[1]), s[2], int(s[3]) if s[3] is not None else None, s[4],
                   guess_subinventory_type(s[0], s[2], s[3])) for s in subinv], page_size=_BATCH)

        if items:
            execute_values(cur, """
                INSERT INTO core.dim_item (inventory_item_id, item_code, item_desc, uom, item_category)
                VALUES %s
            """, [(int(i[0]), i[1], i[2], i[3], i[4]) for i in items], page_size=_BATCH)

        rows_loaded = len(onhand_rows) + len(subinv) + len(items)
        run.pg.commit()
        run.finish("success", rows_read, rows_loaded)
        logger.info("[%s] read=%s loaded=%s", job, rows_read, rows_loaded)
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_loaded, error=str(e))
        run.close()
        raise
    run.close()
    _refresh_after(job)
    return {"status": "success", "rows_read": rows_read, "rows_loaded": rows_loaded}


@celery_app.task(name="app.tasks.etl_tasks.refresh_ebs_marts")
def refresh_ebs_marts(year: int = None, month: int = None,
                      trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    """Daily refresh of every mart, independent of new data: days_overdue and
    days_to_expiry move with the calendar (blueprint 6.2)."""
    from app.services.ebs_mart.schema import refresh_marts
    job = "refresh_ebs_marts"
    run = _Run(job, trigger_type, triggered_by, {})
    try:
        result = refresh_marts()
        failed = {k: v for k, v in result.items() if v != "ok"}
        run.finish("failed" if failed else "success", len(result), len(result) - len(failed),
                   error=json.dumps(failed) if failed else None)
    except Exception as e:
        run.finish("failed", error=str(e))
        raise
    finally:
        run.close()
    return {"status": "success", "result": result, "at": datetime.now().isoformat()}
