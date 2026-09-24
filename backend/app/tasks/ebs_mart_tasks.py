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
    OPM_COST_HISTORY_MONTHS, OPM_COST_METHOD, PR_DUMMY_USERS,
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
#
# Invoice and supplier come straight from AP_INVOICES_ALL here rather than
# only from core.fact_ap_payment_schedule: a held invoice that was never
# validated has no payment schedule yet, so on the first prod run two of five
# holds showed with no supplier and no invoice number.
_AP_HOLD_SQL = """
    SELECT ah.hold_id, ah.invoice_id, ah.hold_lookup_code, ahc.description, SUBSTR(ah.hold_reason, 1, 240),
           ah.hold_date,
           ai.invoice_num, ai.invoice_type_lookup_code, ai.invoice_date, sup.segment1, sup.vendor_name,
           ai.invoice_currency_code, ai.invoice_amount, NVL(ai.base_amount, ai.invoice_amount), ai.cancelled_date
      FROM ap_holds_all ah
      LEFT JOIN ap_hold_codes ahc ON ahc.hold_lookup_code = ah.hold_lookup_code
      LEFT JOIN ap_invoices_all ai ON ai.invoice_id = ah.invoice_id
      LEFT JOIN ap_suppliers sup   ON sup.vendor_id = ai.vendor_id
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
                """INSERT INTO core.fact_ap_hold (hold_id, invoice_id, hold_code, hold_desc, hold_reason, hold_date,
                       invoice_num, invoice_type, invoice_date, vendor_num, vendor_name, invoice_currency_code,
                       invoice_amount, invoice_amount_idr, cancelled_date) VALUES %s""",
                [(int(h[0]), int(h[1]), h[2], h[3], h[4], h[5], h[6], h[7], h[8], h[9], h[10], h[11],
                  _num(h[12]), _num(h[13]), h[14]) for h in holds],
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


# ── Phase 2: PO / PR ─────────────────────────────────────────────────────────

def _po_rate_case() -> str:
    """IDR rate per PO: the PO's own rate when it has one, else the
    Corporate daily rate at PO creation (etl_po_lines' expression, so PO
    values here match Purchasing History)."""
    from app.tasks.eis_etl_tasks import _PO_LINE_RATE_CASE
    return f"CASE WHEN poh.currency_code = 'IDR' THEN 1 ELSE NVL(poh.rate, {_PO_LINE_RATE_CASE}) END"


# Composite watermark: header, line, shipment and release. A receipt changes
# PO_LINE_LOCATIONS_ALL (quantity_received) but not the header; GREATEST over
# all of them is what makes a receipt against a year-old PO show up — the
# trap blueprint section 12 names ("watermark hanya dari header").
# NVL on the release: GREATEST with a NULL argument is NULL in Oracle.
_PO_SHIPMENT_WM = ("GREATEST(poh.last_update_date, pol.last_update_date, poll.last_update_date, "
                   "NVL(por.last_update_date, poll.last_update_date))")

_PO_SHIPMENT_SQL = """
    SELECT poll.line_location_id, poh.po_header_id, pol.po_line_id, poh.segment1, poh.type_lookup_code,
           NVL(por.authorization_status, poh.authorization_status), poh.creation_date,
           NVL(por.approved_date, poh.approved_date),
           sup.segment1, sup.vendor_name, pvs.vendor_site_code, buyer.full_name, poh.currency_code,
           {rate},
           pol.line_num, poll.shipment_num, por.release_num, pol.item_id, msi.segment1,
           NVL(pol.item_description, msi.description), pol.unit_meas_lookup_code, poll.ship_to_organization_id,
           poll.need_by_date, poll.promised_date, NVL(poll.price_override, pol.unit_price),
           poll.quantity, poll.quantity_received, poll.quantity_accepted, poll.quantity_rejected,
           poll.quantity_billed, poll.quantity_cancelled, poll.closed_code, poll.cancel_flag, pol.cancel_flag,
           poll.match_option, poll.receipt_required_flag, poll.inspection_required_flag,
           {wm_expr}
      FROM po_headers_all poh
      JOIN po_lines_all pol           ON pol.po_header_id = poh.po_header_id
      JOIN po_line_locations_all poll ON poll.po_line_id = pol.po_line_id
      LEFT JOIN po_releases_all por   ON por.po_release_id = poll.po_release_id
      JOIN ap_suppliers sup           ON sup.vendor_id = poh.vendor_id
      LEFT JOIN ap_supplier_sites_all pvs ON pvs.vendor_site_id = poh.vendor_site_id
      LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = pol.item_id
                                      AND msi.organization_id = poll.ship_to_organization_id
      LEFT JOIN per_all_people_f buyer ON buyer.person_id = poh.agent_id
                                      AND SYSDATE BETWEEN buyer.effective_start_date AND buyer.effective_end_date
     WHERE poh.org_id = :org_id
       AND poll.shipment_type IN ('STANDARD', 'BLANKET', 'SCHEDULED')
       {wm}
"""
_PO_SHIPMENT_COLS = [
    "line_location_id", "po_header_id", "po_line_id", "po_number", "po_type", "po_status", "po_date",
    "approved_date", "vendor_num", "vendor_name", "vendor_site_code", "buyer_name", "currency_code", "rate_idr",
    "line_num", "shipment_num", "release_num", "item_id", "item_code", "item_desc", "uom", "ship_to_org_id",
    "need_by_date", "promised_date", "unit_price", "quantity", "quantity_received", "quantity_accepted",
    "quantity_rejected", "quantity_billed", "quantity_cancelled", "closed_code", "cancel_flag",
    "line_cancel_flag", "match_option", "receipt_required", "inspection_required", "src_last_update",
]

_PO_DIST_WM = "GREATEST(pod.last_update_date, poll.last_update_date, poh.last_update_date)"

# AP matching updates PO_DISTRIBUTIONS_ALL.quantity_billed, so the
# distribution's own last_update_date carries billing into the watermark.
# The invoice subquery only names which invoices matched.
_PO_DIST_SQL = """
    SELECT pod.po_distribution_id, pod.line_location_id, pod.distribution_num, pod.quantity_ordered,
           pod.quantity_delivered, pod.quantity_billed, pod.quantity_cancelled, pod.amount_billed,
           gcc.segment4, pod.destination_type_code,
           inv.invoice_count, inv.last_invoice_num, inv.last_invoice_date,
           {wm_expr}
      FROM po_distributions_all pod
      JOIN po_line_locations_all poll ON poll.line_location_id = pod.line_location_id
      JOIN po_headers_all poh         ON poh.po_header_id = pod.po_header_id
      LEFT JOIN gl_code_combinations gcc ON gcc.code_combination_id = pod.code_combination_id
      LEFT JOIN (
          SELECT aid.po_distribution_id,
                 COUNT(DISTINCT ai.invoice_id)                                              AS invoice_count,
                 MAX(ai.invoice_num) KEEP (DENSE_RANK LAST ORDER BY ai.invoice_date, ai.invoice_id) AS last_invoice_num,
                 MAX(ai.invoice_date)                                                       AS last_invoice_date
            FROM ap_invoice_distributions_all aid
            JOIN ap_invoices_all ai ON ai.invoice_id = aid.invoice_id
           WHERE aid.po_distribution_id IS NOT NULL
             AND ai.cancelled_date IS NULL
             AND NVL(aid.reversal_flag, 'N') <> 'Y'
           GROUP BY aid.po_distribution_id
      ) inv ON inv.po_distribution_id = pod.po_distribution_id
     WHERE poh.org_id = :org_id
       AND poll.shipment_type IN ('STANDARD', 'BLANKET', 'SCHEDULED')
       {wm}
"""
_PO_DIST_COLS = [
    "po_distribution_id", "line_location_id", "distribution_num", "quantity_ordered", "quantity_delivered",
    "quantity_billed", "quantity_cancelled", "amount_billed", "charge_account", "destination_type",
    "invoice_count", "last_invoice_num", "last_invoice_date", "src_last_update",
]

# Approved requisition lines not yet on a PO (line_location_id IS NULL),
# purchase (VENDOR-sourced) only — internal requisitions are filled from
# stock, not by Purchasing. Approval date from PO_ACTION_HISTORY, as the
# Dashboard's Open PR report does; dummy users excluded the same way.
_PR_PENDING_SQL = """
    SELECT prl.requisition_line_id, prh.requisition_header_id, prh.segment1, prh.type_lookup_code,
           prh.creation_date, appr.approved_date, fu.user_name, req.full_name,
           SUBSTR(prh.description, 1, 240), prl.line_num, prl.item_id, msi.segment1,
           prl.item_description, prl.unit_meas_lookup_code,
           NVL(prl.quantity, 0) - NVL(prl.quantity_cancelled, 0),
           prl.unit_price, NVL(prl.currency_code, 'IDR'), prl.currency_unit_price,
           prl.need_by_date, prl.suggested_vendor_name, prl.destination_organization_id
      FROM po_requisition_headers_all prh
      JOIN po_requisition_lines_all prl ON prl.requisition_header_id = prh.requisition_header_id
      LEFT JOIN mtl_system_items_b msi  ON msi.inventory_item_id = prl.item_id
                                       AND msi.organization_id = prl.destination_organization_id
      LEFT JOIN fnd_user fu             ON fu.user_id = prh.created_by
      LEFT JOIN per_all_people_f req    ON req.person_id = prl.to_person_id
                                       AND SYSDATE BETWEEN req.effective_start_date AND req.effective_end_date
      LEFT JOIN (
          SELECT pah.object_id, MAX(pah.action_date) AS approved_date
            FROM po_action_history pah
           WHERE pah.action_code = 'APPROVE' AND pah.object_type_code = 'REQUISITION'
           GROUP BY pah.object_id
      ) appr ON appr.object_id = prh.requisition_header_id
     WHERE prh.org_id = :org_id
       AND prh.authorization_status = 'APPROVED'
       AND prl.line_location_id IS NULL
       AND prl.source_type_code = 'VENDOR'
       AND NVL(prl.cancel_flag, 'N') = 'N'
       AND NVL(prl.modified_by_agent_flag, 'N') = 'N'
       AND NVL(prl.closed_code, 'OPEN') NOT IN ('CLOSED', 'FINALLY CLOSED')
       AND NVL(prh.closed_code, 'OPEN') NOT IN ('CLOSED', 'FINALLY CLOSED')
       AND NVL(prl.quantity, 0) - NVL(prl.quantity_cancelled, 0) > 0
       AND NOT (UPPER(NVL(fu.user_name, '-')) IN ({dummy})
                OR (UPPER(NVL(fu.user_name, '-')) = 'SHERLIN'
                    AND UPPER(NVL(prl.suggested_vendor_name, '-')) = 'ELLVIN'))
"""
_PR_PENDING_COLS = [
    "requisition_line_id", "requisition_header_id", "pr_number", "pr_type", "pr_date", "approved_date",
    "preparer", "requester", "pr_description", "line_num", "item_id", "item_code", "item_desc", "uom",
    "quantity", "unit_price", "currency_code", "currency_unit_price", "need_by_date", "suggested_vendor",
    "destination_org_id",
]


def _int(v):
    return int(v) if v is not None else None


def _extract_po(cur_ora, sql: str, wm_expr: str, watermark, full: bool, **fmt):
    params = {"org_id": EBS_OPERATING_UNIT_ID}
    if full or watermark is None:
        clause = ""
    else:
        params["wm"] = watermark
        clause = f"AND {wm_expr} >= :wm - 1/24"
    cur_ora.execute(sql.format(wm=clause, wm_expr=wm_expr, **fmt), params)
    return cur_ora.fetchall()


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_po")
def etl_mart_po(year: int = None, month: int = None, full_refresh: bool = False,
                trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    """PO shipments and distributions (incremental, composite watermark,
    weekly full reload) plus the pending-requisition snapshot (full)."""
    job = "etl_mart_po"
    run = _Run(job, trigger_type, triggered_by, {"full_refresh": full_refresh})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_upserted = 0
    wm_from = wm_to = None
    try:
        cur = run.cur
        wm_ship = _get_watermark(cur, job, "shipments")
        wm_dist = _get_watermark(cur, job, "distributions")
        wm_from = None if full_refresh else min((w for w in (wm_ship, wm_dist) if w), default=None)

        ora = get_oracle_connection()
        try:
            cur_ora = ora.cursor()
            cur_ora.arraysize = _BATCH
            ships = _extract_po(cur_ora, _PO_SHIPMENT_SQL, _PO_SHIPMENT_WM, wm_ship, full_refresh,
                                rate=_po_rate_case())
            dists = _extract_po(cur_ora, _PO_DIST_SQL, _PO_DIST_WM, wm_dist, full_refresh)
            dummy = ", ".join(f"'{u}'" for u in PR_DUMMY_USERS)
            cur_ora.execute(_PR_PENDING_SQL.format(dummy=dummy), {"org_id": EBS_OPERATING_UNIT_ID})
            prs = cur_ora.fetchall()
        finally:
            ora.close()
        rows_read = len(ships) + len(dists) + len(prs)

        if full_refresh:
            cur.execute("TRUNCATE core.fact_po_shipment, core.fact_po_distribution")

        ship_rows = [
            (_int(r[0]), _int(r[1]), _int(r[2]), r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12],
             _num(r[13]), _int(r[14]), _int(r[15]), _int(r[16]), _int(r[17]), r[18], r[19], r[20], _int(r[21]),
             r[22], r[23], _num(r[24]), _num(r[25]), _num(r[26]), _num(r[27]), _num(r[28]), _num(r[29]),
             _num(r[30]), r[31], r[32], r[33], r[34], r[35], r[36], r[37])
            for r in ships
        ]
        dist_rows = [
            (_int(r[0]), _int(r[1]), _int(r[2]), _num(r[3]), _num(r[4]), _num(r[5]), _num(r[6]), _num(r[7]),
             r[8], r[9], _int(r[10]), r[11], r[12], r[13])
            for r in dists
        ]
        rows_upserted += _upsert(cur, "core.fact_po_shipment", _PO_SHIPMENT_COLS, ["line_location_id"], ship_rows)
        rows_upserted += _upsert(cur, "core.fact_po_distribution", _PO_DIST_COLS, ["po_distribution_id"], dist_rows)

        cur.execute("TRUNCATE core.snap_pr_pending")
        if prs:
            execute_values(
                cur,
                f"INSERT INTO core.snap_pr_pending ({', '.join(_PR_PENDING_COLS)}) VALUES %s",
                [(_int(r[0]), _int(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], _int(r[9]), _int(r[10]),
                  r[11], r[12], r[13], _num(r[14]), _num(r[15]), r[16], _num(r[17]), r[18], r[19], _int(r[20]))
                 for r in prs],
                page_size=_BATCH,
            )
            rows_upserted += len(prs)

        new_ship = max((r[-1] for r in ship_rows if r[-1]), default=None)
        new_dist = max((r[-1] for r in dist_rows if r[-1]), default=None)
        _set_watermark(cur, job, "shipments", new_ship)
        _set_watermark(cur, job, "distributions", new_dist)
        wm_to = max([w for w in (new_ship, new_dist, wm_ship, wm_dist) if w], default=None)
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


# ── Phase 2: OPM item cost (PMAC) ────────────────────────────────────────────

# Component cost rows summed per item, period and component class; the
# per-item total is the unit cost. cm_cmpt_mst_b names the component class
# (material, overhead, ...), kept as JSON so a question about "komponen
# biaya" can be answered without another extract.
_ITEM_COST_SQL = """
    SELECT ccd.inventory_item_id, gps.period_id, gps.period_code, gps.start_date, gps.end_date,
           gps.period_status, cmm.cost_mthd_code, NVL(ccm.cost_cmpntcls_code, TO_CHAR(ccd.cost_cmpntcls_id)),
           SUM(ccd.cmpnt_cost)
      FROM cm_cmpt_dtl ccd
      JOIN gmf_period_statuses gps ON gps.period_id = ccd.period_id
      JOIN cm_mthd_mst cmm         ON cmm.cost_type_id = ccd.cost_type_id
      LEFT JOIN cm_cmpt_mst_b ccm  ON ccm.cost_cmpntcls_id = ccd.cost_cmpntcls_id
     WHERE ccd.organization_id = :org
       AND cmm.cost_mthd_code = :method
       AND NVL(ccd.delete_mark, 0) = 0
       AND gps.end_date >= ADD_MONTHS(TRUNC(SYSDATE), -:months)
     GROUP BY ccd.inventory_item_id, gps.period_id, gps.period_code, gps.start_date, gps.end_date,
              gps.period_status, cmm.cost_mthd_code, NVL(ccm.cost_cmpntcls_code, TO_CHAR(ccd.cost_cmpntcls_id))
"""

# When the method above finds nothing, say what does exist instead of
# reporting a silent success with zero rows: which organizations and cost
# methods actually carry component costs.
_ITEM_COST_DIAG_SQL = """
    SELECT ccd.organization_id, cmm.cost_mthd_code, COUNT(*)
      FROM cm_cmpt_dtl ccd
      JOIN cm_mthd_mst cmm         ON cmm.cost_type_id = ccd.cost_type_id
      JOIN gmf_period_statuses gps ON gps.period_id = ccd.period_id
     WHERE gps.end_date >= ADD_MONTHS(TRUNC(SYSDATE), -:months)
     GROUP BY ccd.organization_id, cmm.cost_mthd_code
     ORDER BY 3 DESC
"""


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_item_cost")
def etl_mart_item_cost(year: int = None, month: int = None,
                       trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_item_cost"
    run = _Run(job, trigger_type, triggered_by, {"organization_id": EBS_PROCESS_ORG_ID, "method": OPM_COST_METHOD})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_loaded = 0
    note = None
    try:
        ora = get_oracle_connection()
        try:
            cur_ora = ora.cursor()
            cur_ora.arraysize = _BATCH
            cur_ora.execute(_ITEM_COST_SQL, {"org": EBS_PROCESS_ORG_ID, "method": OPM_COST_METHOD,
                                             "months": OPM_COST_HISTORY_MONTHS})
            rows = cur_ora.fetchall()
            if not rows:
                cur_ora.execute(_ITEM_COST_DIAG_SQL, {"months": OPM_COST_HISTORY_MONTHS})
                found = ", ".join(f"org {r[0]}/{r[1]}: {r[2]} baris" for r in cur_ora.fetchall()[:10])
                note = (f"Tidak ada biaya {OPM_COST_METHOD} untuk org {EBS_PROCESS_ORG_ID}. "
                        f"Yang tersedia: {found or 'tidak ada sama sekali'}")
        finally:
            ora.close()
        rows_read = len(rows)

        costs: dict[tuple, dict] = {}
        for item_id, period_id, code, start, end, status, method, cmpnt, amount in rows:
            key = (int(item_id), int(period_id))
            c = costs.setdefault(key, {"code": code, "start": start, "end": end, "status": status,
                                        "method": method, "total": 0.0, "components": {}})
            amt = float(amount or 0)
            c["total"] += amt
            c["components"][cmpnt] = round(c["components"].get(cmpnt, 0.0) + amt, 6)

        cur = run.cur
        cur.execute("TRUNCATE core.fact_item_cost")
        if costs:
            execute_values(cur, """
                INSERT INTO core.fact_item_cost (inventory_item_id, period_id, period_code, period_start_date,
                    period_end_date, period_status, cost_method, unit_cost, cost_components)
                VALUES %s
            """, [(k[0], k[1], v["code"], v["start"], v["end"], v["status"], v["method"], round(v["total"], 6),
                   json.dumps(v["components"])) for k, v in costs.items()], page_size=_BATCH)
        rows_loaded = len(costs)
        run.pg.commit()
        run.finish("success", rows_read, rows_loaded, error=note)
        logger.info("[%s] read=%s items×periods=%s %s", job, rows_read, rows_loaded, note or "")
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_loaded, error=str(e))
        run.close()
        raise
    run.close()
    _refresh_after(job)
    return {"status": "success", "rows_read": rows_read, "items_periods": rows_loaded, "note": note}


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
