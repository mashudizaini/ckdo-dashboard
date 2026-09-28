"""
ETL for finance close, Cash Management and Fixed Assets (library v2 12-13),
Oracle EBS -> core.fin_* / core.ce_* / core.fa_* / core.ar_interface_line ->
REFRESH mart.gl_period_status, sla_gl_gap, ar_autoinvoice_error,
so_shipped_not_invoiced, ce_unreconciled, fa_asset_register, fa_depreciation.

  etl_mart_close  hourly (06-20): period status of GL/AP/AR/PO, inventory
                  (org 121) and OPM costing; subledger -> GL gaps (XLA events
                  not accounted or in error, entries draft or not
                  transferred, GL journals not posted); AutoInvoice interface
                  lines and errors; unreconciled bank statement lines and
                  system transactions. All full snapshots: each is a list of
                  things still open, and something resolved must disappear.
  etl_mart_fa     daily: corporate-book assets with cost / reserve / NBV,
                  depreciation per asset × period (24 months), FA periods
                  (open/closed, depreciation run) into the period status.

Bank account numbers are never selected. Same conventions as
ebs_mart_tasks.py (eis.etl_job_log, advisory lock, refresh before success,
restart celery after deploying this file).
"""
import logging
from datetime import date

from app.database import get_oracle_connection
from app.services.ebs_mart.constants import (
    EBS_LEDGER_ID, EBS_OPERATING_UNIT_ID, EBS_PROCESS_ORG_ID, OPM_COST_METHOD,
)
from app.tasks.celery_app import celery_app
from app.tasks.ebs_mart_sa_tasks import _q, _replace
from app.tasks.ebs_mart_tasks import _BATCH, _Run, _int, _num, refresh_marts_for_job

logger = logging.getLogger(__name__)

_APP_BY_ID = {101: "GL", 200: "AP", 222: "AR", 201: "PO"}

# ── Period status ────────────────────────────────────────────────────────────

_GL_PS_SQL = """
    SELECT gps.application_id, gps.period_name, gps.period_year, gps.period_num, gps.start_date, gps.end_date,
           gps.closing_status, gps.last_update_date
      FROM gl_period_statuses gps
     WHERE gps.ledger_id = :ledger
       AND gps.application_id IN (101, 200, 222, 201)
       AND gps.period_year >= EXTRACT(YEAR FROM SYSDATE) - 1
       AND NVL(gps.adjustment_period_flag, 'N') = 'N'
"""
# Inventory periods of the process org (R12.2 OPM orgs use ORG_ACCT_PERIODS).
_INV_PS_SQL = """
    SELECT period_name, period_year, period_num, period_start_date, schedule_close_date, open_flag,
           period_close_date, last_update_date
      FROM org_acct_periods
     WHERE organization_id = :org
       AND period_year >= EXTRACT(YEAR FROM SYSDATE) - 1
"""
# OPM costing calendar of the cost method that values org 121 (CKDO_PMAC).
_OPM_PS_SQL = """
    SELECT gps.period_code, gps.start_date, gps.end_date, gps.period_status, gps.last_update_date
      FROM gmf_period_statuses gps
      JOIN cm_mthd_mst cmm ON cmm.cost_type_id = gps.cost_type_id
     WHERE cmm.cost_mthd_code = :method
       AND gps.end_date >= ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), -12)
"""

# ── Subledger -> GL gaps ─────────────────────────────────────────────────────

# Events not accounted (process U) or rejected by Create Accounting (E, I,
# R). Draft events are left to the header query below so nothing counts twice.
# xla.xla_transaction_entities: the APPS view of the same name is MO-secured.
_XLA_EVENT_SQL = """
    SELECT fa.application_short_name, e.event_id, e.event_date, e.event_type_code, e.process_status_code,
           te.entity_code, te.transaction_number
      FROM xla_events e
      JOIN xla.xla_transaction_entities te ON te.entity_id = e.entity_id AND te.application_id = e.application_id
      JOIN fnd_application fa              ON fa.application_id = e.application_id
     WHERE te.ledger_id = :ledger
       AND e.event_status_code IN ('U', 'I')
       AND e.process_status_code IN ('U', 'E', 'I', 'R')
       AND e.event_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -24)
       AND ROWNUM <= 50000
"""
_XLA_HEADER_SQL = """
    SELECT fa.application_short_name, h.ae_header_id, h.accounting_date, h.period_name, h.event_type_code,
           h.accounting_entry_status_code, NVL(h.gl_transfer_status_code, 'N'), te.entity_code, te.transaction_number,
           (SELECT SUM(NVL(l.accounted_dr, 0)) FROM xla_ae_lines l
             WHERE l.ae_header_id = h.ae_header_id AND l.application_id = h.application_id)
      FROM xla_ae_headers h
      JOIN xla.xla_transaction_entities te ON te.entity_id = h.entity_id AND te.application_id = h.application_id
      JOIN fnd_application fa              ON fa.application_id = h.application_id
     WHERE h.ledger_id = :ledger
       AND h.accounting_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -13)
       AND (h.accounting_entry_status_code <> 'F' OR NVL(h.gl_transfer_status_code, 'N') <> 'Y')
       AND ROWNUM <= 50000
"""
_GL_UNPOSTED_SQL = """
    SELECT jeh.je_header_id, jeh.period_name, jeh.default_effective_date, jst.user_je_source_name,
           jct.user_je_category_name, SUBSTR(jeh.name, 1, 240), jeh.status, jeh.running_total_accounted_dr
      FROM gl_je_headers jeh
      LEFT JOIN gl_je_sources_tl jst    ON jst.je_source_name = jeh.je_source AND jst.language = 'US'
      LEFT JOIN gl_je_categories_tl jct ON jct.je_category_name = jeh.je_category AND jct.language = 'US'
     WHERE jeh.ledger_id = :ledger
       AND jeh.actual_flag = 'A'
       AND jeh.status <> 'P'
       AND jeh.default_effective_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -13)
"""
_SHORT = {"SQLAP": "AP", "AR": "AR", "PO": "PO", "SQLGL": "GL", "OFA": "FA", "CE": "CE", "GMF": "OPM",
          "BOM": "Cost Mgmt", "CST": "Cost Mgmt", "INV": "INV"}

# ── AutoInvoice ──────────────────────────────────────────────────────────────

_AUTOINV_SQL = """
    SELECT ril.interface_line_id, ril.batch_source_name, ril.interface_line_context, ril.interface_line_attribute1,
           ril.interface_line_attribute6,
           (SELECT SUBSTR(hp.party_name, 1, 240) FROM hz_cust_accounts hca JOIN hz_parties hp ON hp.party_id = hca.party_id
             WHERE hca.cust_account_id = ril.orig_system_bill_customer_id),
           ril.trx_date, ril.gl_date, ril.currency_code, ril.amount, ril.conversion_rate, ril.interface_status,
           ril.request_id, ril.creation_date, SUBSTR(rie.message_text, 1, 500), SUBSTR(rie.invalid_value, 1, 240)
      FROM ra_interface_lines_all ril
      LEFT JOIN ra_interface_errors_all rie ON rie.interface_line_id = ril.interface_line_id
     WHERE ril.org_id = :org_id
"""

# ── Cash Management ──────────────────────────────────────────────────────────

_ORG_ACCOUNTS = "SELECT u.bank_account_id FROM ce_bank_acct_uses_all u WHERE u.org_id = :org_id"
_BANK_ACCT_SQL = f"""
    SELECT ba.bank_account_id, ba.bank_account_name,
           (SELECT SUBSTR(hp.party_name, 1, 240) FROM hz_parties hp WHERE hp.party_id = ba.bank_id),
           ba.currency_code,
           (SELECT MAX(sh.statement_number) KEEP (DENSE_RANK LAST ORDER BY sh.statement_date)
              FROM ce_statement_headers sh WHERE sh.bank_account_id = ba.bank_account_id),
           (SELECT MAX(sh.statement_date) FROM ce_statement_headers sh WHERE sh.bank_account_id = ba.bank_account_id)
      FROM ce_bank_accounts ba
     WHERE ba.bank_account_id IN ({_ORG_ACCOUNTS})
"""
_CE_LINE_SQL = f"""
    SELECT sl.statement_line_id, sh.bank_account_id, sh.statement_number, sl.line_number, sl.trx_date, sl.trx_type,
           sl.amount, sl.status, SUBSTR(sl.trx_text, 1, 200), sl.bank_trx_number
      FROM ce_statement_lines sl
      JOIN ce_statement_headers sh ON sh.statement_header_id = sl.statement_header_id
     WHERE sl.status IN ('UNRECONCILED', 'ERROR')
       AND sl.trx_date >= ADD_MONTHS(TRUNC(SYSDATE), -24)
       AND sh.bank_account_id IN ({_ORG_ACCOUNTS})
"""
# Payments still negotiable/issued: not yet cleared or reconciled against a
# statement line.
_CE_AP_SQL = """
    SELECT c.check_id, u.bank_account_id, TO_CHAR(c.check_number), c.check_date, c.currency_code, c.amount,
           NVL(c.base_amount, c.amount), c.status_lookup_code, SUBSTR(c.vendor_name, 1, 200)
      FROM ap_checks_all c
      JOIN ce_bank_acct_uses_all u ON u.bank_acct_use_id = c.ce_bank_acct_use_id
     WHERE c.org_id = :org_id
       AND c.check_date >= ADD_MONTHS(TRUNC(SYSDATE), -24)
       AND c.status_lookup_code IN ('NEGOTIABLE', 'ISSUED', 'STOP INITIATED')
"""
_CE_AR_SQL = """
    SELECT cr.cash_receipt_id, u.bank_account_id, cr.receipt_number, cr.receipt_date, cr.currency_code, cr.amount,
           cr.amount * NVL(cr.exchange_rate, 1), crh.status,
           (SELECT SUBSTR(hp.party_name, 1, 200) FROM hz_cust_accounts hca JOIN hz_parties hp ON hp.party_id = hca.party_id
             WHERE hca.cust_account_id = cr.pay_from_customer)
      FROM ar_cash_receipts_all cr
      JOIN ar_cash_receipt_history_all crh ON crh.cash_receipt_id = cr.cash_receipt_id AND crh.current_record_flag = 'Y'
      JOIN ce_bank_acct_uses_all u         ON u.bank_acct_use_id = cr.remit_bank_acct_use_id
     WHERE cr.org_id = :org_id
       AND cr.receipt_date >= ADD_MONTHS(TRUNC(SYSDATE), -24)
       AND crh.status IN ('REMITTED', 'CONFIRMED')
"""
_CE_CF_SQL = f"""
    SELECT cf.cashflow_id, cf.cashflow_bank_account_id, cf.cashflow_date, cf.cashflow_currency_code,
           cf.cashflow_amount, NVL(cf.base_amount, cf.cashflow_amount), cf.cashflow_status_code, cf.cashflow_direction,
           SUBSTR(cf.description, 1, 200)
      FROM ce_cashflows cf
     WHERE cf.cashflow_status_code = 'CREATED'
       AND cf.cashflow_date >= ADD_MONTHS(TRUNC(SYSDATE), -24)
       AND cf.cashflow_bank_account_id IN ({_ORG_ACCOUNTS})
"""
_DEBIT_TYPES = {"DEBIT", "MISC_DEBIT", "NSF", "REJECTED", "STOP", "SWEEP_OUT"}


def _fx(cur) -> dict:
    cur.execute("SELECT currency_code, rate FROM core.dim_fx_rate")
    return {c: float(r) for c, r in cur.fetchall() if r}


def _idr(amount, currency, fx):
    if amount is None:
        return None
    if not currency or currency == "IDR":
        return float(amount)
    rate = fx.get(currency)
    return float(amount) * rate if rate else None


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_close")
def etl_mart_close(year: int = None, month: int = None, full_refresh: bool = False,
                   trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_close"
    run = _Run(job, trigger_type, triggered_by, {"ledger_id": EBS_LEDGER_ID})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_loaded = 0
    try:
        cur = run.cur
        led, org = {"ledger": EBS_LEDGER_ID}, {"org_id": EBS_OPERATING_UNIT_ID}
        ora = get_oracle_connection()
        try:
            co = ora.cursor()
            co.arraysize = _BATCH
            gl_ps = _q(co, "gl_period_statuses", _GL_PS_SQL, led)
            inv_ps = _q(co, "org_acct_periods", _INV_PS_SQL, {"org": EBS_PROCESS_ORG_ID})
            opm_ps = _q(co, "gmf_period_statuses", _OPM_PS_SQL, {"method": OPM_COST_METHOD})
            events = _q(co, "xla_events", _XLA_EVENT_SQL, led)
            headers = _q(co, "xla_ae_headers", _XLA_HEADER_SQL, led)
            unposted = _q(co, "gl_je_headers", _GL_UNPOSTED_SQL, led)
            autoinv = _q(co, "ra_interface_lines_all", _AUTOINV_SQL, org)
            accounts = _q(co, "ce_bank_accounts", _BANK_ACCT_SQL, org)
            ce_lines = _q(co, "ce_statement_lines", _CE_LINE_SQL, org)
            ce_ap = _q(co, "ap_checks_all", _CE_AP_SQL, org)
            ce_ar = _q(co, "ar_cash_receipts_all", _CE_AR_SQL, org)
            ce_cf = _q(co, "ce_cashflows", _CE_CF_SQL, org)
        finally:
            ora.close()
        rows_read = sum(map(len, (gl_ps, inv_ps, opm_ps, events, headers, unposted, autoinv, accounts, ce_lines,
                                  ce_ap, ce_ar, ce_cf)))
        fx = _fx(cur)

        # Period status (FA rows belong to etl_mart_fa and are left alone).
        ps = []
        gl_by_start = {}
        for r in gl_ps:
            app = _APP_BY_ID.get(int(r[0]))
            ps.append((f"{app}||{r[1]}", app, None, r[1], _int(r[2]), _int(r[3]), r[4], r[5], r[6], None, r[7]))
            if app == "GL":
                gl_by_start[r[4].date() if hasattr(r[4], "date") else r[4]] = (r[1], _int(r[2]), _int(r[3]))
        for r in inv_ps:
            code = {"Y": "O", "P": "P"}.get(r[5], "C" if r[6] else "F")
            ps.append((f"INV||{r[0]}", "INV", None, r[0], _int(r[1]), _int(r[2]), r[3], r[4], code, None, r[7]))
        for r in opm_ps:
            start = r[1].date() if hasattr(r[1], "date") else r[1]
            name, yr, num = gl_by_start.get(start, (r[0], None, None))
            ps.append((f"OPM||{r[0]}", "OPM", None, name, yr, num, r[1], r[2], r[3], None, r[4]))
        cur.execute("DELETE FROM core.fin_period_status WHERE application <> 'FA'")
        n = _replace_rows(cur, "core.fin_period_status",
                          ["row_key", "application", "book_type_code", "period_name", "period_year", "period_num",
                           "start_date", "end_date", "status_code", "deprn_run", "last_update_date"], ps)

        # Subledger -> GL gaps. The period of an event is the GL period its
        # date falls in.
        cur.execute("""SELECT period_name, start_date, end_date FROM core.fin_period_status
                        WHERE application = 'GL'""")
        periods = cur.fetchall()

        def period_of(d):
            d = d.date() if hasattr(d, "date") else d
            for name, s, e in periods:
                if s and e and s <= d <= e:
                    return name
            return d.strftime("%b-%y").upper() if d else None

        gap = []
        for r in events:
            kind = "UNACCOUNTED" if r[4] == "U" else "ACCOUNTING_ERROR"
            gap.append((f"EV|{int(r[1])}", kind, _SHORT.get(r[0], r[0]), period_of(r[2]), r[2], r[3], r[5], r[6],
                        None, f"process_status={r[4]}"))
        for r in headers:
            if r[5] == "F":
                kind = "NOT_TRANSFERRED"
            elif r[5] == "D":
                kind = "DRAFT"
            else:
                kind = "ACCOUNTING_ERROR"
            gap.append((f"AE|{int(r[1])}", kind, _SHORT.get(r[0], r[0]), r[3], r[2], r[4], r[7], r[8], _num(r[9]),
                        f"entry_status={r[5]}, gl_transfer={r[6]}"))
        for r in unposted:
            gap.append((f"JE|{int(r[0])}", "GL_UNPOSTED", "GL", r[1], r[2], r[4], r[3], r[5], _num(r[7]),
                        f"status={r[6]}"))
        n += _replace(cur, "core.fin_sla_gap",
                      ["row_key", "kind", "application", "period_name", "txn_date", "event_type", "entity_code",
                       "transaction_number", "amount_idr", "detail"], gap)

        # interface_line_id is only filled when AutoInvoice picks a line up,
        # so lines still waiting are keyed by position in this snapshot.
        ai = []
        for i, r in enumerate(autoinv):
            so_line = _int(r[4]) if r[4] and str(r[4]).isdigit() else None
            rate = float(r[10]) if r[10] else None
            amt_idr = float(r[9]) * rate if (r[9] is not None and rate) else _idr(r[9], r[8], fx)
            ai.append((f"{_int(r[0]) or 'new'}|{i}", _int(r[0]), r[1], r[2], r[3], so_line, r[5], r[6], r[7], r[8], _num(r[9]),
                       amt_idr, r[11], _int(r[12]), r[13], r[14], r[15]))
        n += _replace(cur, "core.ar_interface_line",
                      ["row_key", "interface_line_id", "batch_source_name", "line_context", "so_number", "so_line_id",
                       "customer_name", "trx_date", "gl_date", "currency_code", "amount", "amount_idr",
                       "interface_status", "request_id", "created_date", "error_message", "invalid_value"], ai)

        n += _replace(cur, "core.ce_bank_account",
                      ["bank_account_id", "bank_account_name", "bank_name", "currency_code", "last_statement_number",
                       "last_statement_date"],
                      [(_int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in accounts])
        acct_ccy = {int(r[0]): r[3] for r in accounts}
        ce = []
        for r in ce_lines:
            sign = -1 if (r[5] or "").upper() in _DEBIT_TYPES else 1
            ccy = acct_ccy.get(int(r[1]))
            amt = float(r[6]) * sign if r[6] is not None else None
            ce.append((f"SL|{int(r[0])}", "BANK", "Statement line", _int(r[1]), r[9] or f"{r[2]}/{r[3]}", r[4], ccy,
                       amt, _idr(amt, ccy, fx), r[7], r[8], r[2]))
        for r in ce_ap:
            ce.append((f"AP|{int(r[0])}", "SYSTEM", "AP Payment", _int(r[1]), r[2], r[3], r[4],
                       -float(r[5] or 0), -float(r[6] or 0), r[7], r[8], None))
        for r in ce_ar:
            ce.append((f"AR|{int(r[0])}", "SYSTEM", "AR Receipt", _int(r[1]), r[2], r[3], r[4],
                       float(r[5] or 0), float(r[6] or 0), r[7], r[8], None))
        for r in ce_cf:
            sign = -1 if (r[7] or "").upper() == "PAYMENT" else 1
            ce.append((f"CF|{int(r[0])}", "SYSTEM", "Bank Transfer", _int(r[1]), str(int(r[0])), r[2], r[3],
                       sign * float(r[4] or 0), sign * float(r[5] or 0), r[6], r[8], None))
        n += _replace(cur, "core.ce_unreconciled",
                      ["row_key", "side", "source", "bank_account_id", "doc_number", "trx_date", "currency_code",
                       "amount_entered", "amount_idr", "status", "description", "statement_number"], ce)
        rows_loaded = n

        run.pg.commit()
        refresh_marts_for_job(job)
        run.finish("success", rows_read, rows_loaded)
        logger.info("[%s] read=%s loaded=%s gaps=%s autoinvoice=%s ce=%s", job, rows_read, rows_loaded, len(gap),
                    len(ai), len(ce))
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_loaded, error=str(e))
        run.close()
        raise
    run.close()
    return {"status": "success", "rows_read": rows_read, "rows_loaded": rows_loaded}


def _replace_rows(cur, table, columns, rows):
    """Insert without the DELETE of _replace — the caller already removed
    only its own rows (period status is shared by two jobs)."""
    from psycopg2.extras import execute_values
    if rows:
        execute_values(cur, f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s", rows, page_size=_BATCH)
    return len(rows)


# ── Fixed Assets ─────────────────────────────────────────────────────────────

_FA_BOOK_SQL = """
    SELECT book_type_code FROM fa_book_controls
     WHERE book_class = 'CORPORATE' AND set_of_books_id = :ledger AND date_ineffective IS NULL
"""
_FA_ASSET_SQL = """
    SELECT ad.asset_id, bk.book_type_code, ad.asset_number, SUBSTR(adt.description, 1, 240), ad.asset_type,
           ad.tag_number,
           cat.segment1 || NVL2(cat.segment2, '.' || cat.segment2, '') || NVL2(cat.segment3, '.' || cat.segment3, ''),
           SUBSTR(catt.description, 1, 240),
           (SELECT MIN(loc.segment1 || NVL2(loc.segment2, '.' || loc.segment2, '') || NVL2(loc.segment3, '.' || loc.segment3, ''))
              FROM fa_distribution_history dh JOIN fa_locations loc ON loc.location_id = dh.location_id
             WHERE dh.asset_id = ad.asset_id AND dh.book_type_code = bk.book_type_code AND dh.date_ineffective IS NULL),
           bk.date_placed_in_service, bk.cost, bk.original_cost, bk.salvage_value, bk.life_in_months,
           bk.deprn_method_code, ad.current_units,
           CASE WHEN bk.period_counter_fully_retired IS NOT NULL THEN 'Y' ELSE 'N' END,
           ds.deprn_reserve, ds.ytd_deprn, dp.period_name
      FROM fa_additions_b ad
      JOIN fa_additions_tl adt       ON adt.asset_id = ad.asset_id AND adt.language = 'US'
      JOIN fa_books bk               ON bk.asset_id = ad.asset_id AND bk.book_type_code = :book
                                    AND bk.date_ineffective IS NULL
      JOIN fa_categories_b cat       ON cat.category_id = ad.asset_category_id
      LEFT JOIN fa_categories_tl catt ON catt.category_id = cat.category_id AND catt.language = 'US'
      LEFT JOIN (SELECT asset_id, MAX(period_counter) AS pc FROM fa_deprn_summary
                  WHERE book_type_code = :book GROUP BY asset_id) lds ON lds.asset_id = ad.asset_id
      LEFT JOIN fa_deprn_summary ds  ON ds.asset_id = lds.asset_id AND ds.book_type_code = :book
                                    AND ds.period_counter = lds.pc
      LEFT JOIN fa_deprn_periods dp  ON dp.book_type_code = :book AND dp.period_counter = ds.period_counter
"""
_FA_DEPRN_SQL = """
    SELECT ds.asset_id, ds.period_counter, dp.period_name, dp.calendar_period_open_date, ds.deprn_amount,
           ds.ytd_deprn, ds.deprn_reserve
      FROM fa_deprn_summary ds
      JOIN fa_deprn_periods dp ON dp.book_type_code = ds.book_type_code AND dp.period_counter = ds.period_counter
     WHERE ds.book_type_code = :book
       AND ds.deprn_source_code = 'DEPRN'
       AND dp.calendar_period_open_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -24)
"""
_FA_PERIOD_SQL = """
    SELECT period_name, period_counter, fiscal_year, period_num, calendar_period_open_date,
           calendar_period_close_date, period_close_date, deprn_run
      FROM fa_deprn_periods
     WHERE book_type_code = :book
       AND calendar_period_open_date >= ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), -12)
"""


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_fa")
def etl_mart_fa(year: int = None, month: int = None, full_refresh: bool = False,
                trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_fa"
    run = _Run(job, trigger_type, triggered_by, {"ledger_id": EBS_LEDGER_ID})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_loaded = 0
    try:
        cur = run.cur
        ora = get_oracle_connection()
        try:
            co = ora.cursor()
            co.arraysize = _BATCH
            books = [r[0] for r in _q(co, "fa_book_controls", _FA_BOOK_SQL, {"ledger": EBS_LEDGER_ID})]
            assets, deprn, periods = [], [], []
            for b in books:
                assets += _q(co, f"fa_books[{b}]", _FA_ASSET_SQL, {"book": b})
                deprn += [(b, *r) for r in _q(co, f"fa_deprn_summary[{b}]", _FA_DEPRN_SQL, {"book": b})]
                periods += [(b, *r) for r in _q(co, f"fa_deprn_periods[{b}]", _FA_PERIOD_SQL, {"book": b})]
        finally:
            ora.close()
        if not books:
            raise RuntimeError(f"Tidak ada buku FA CORPORATE untuk ledger {EBS_LEDGER_ID} di FA_BOOK_CONTROLS.")
        rows_read = len(assets) + len(deprn) + len(periods)

        n = _replace(cur, "core.fa_asset",
                     ["asset_id", "book_type_code", "asset_number", "description", "asset_type", "tag_number",
                      "category", "category_desc", "location", "date_placed_in_service", "cost", "original_cost",
                      "salvage_value", "life_in_months", "deprn_method", "units", "is_retired", "deprn_reserve",
                      "ytd_deprn", "last_deprn_period"],
                     [(_int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], _num(r[10]), _num(r[11]),
                       _num(r[12]), _int(r[13]), r[14], _num(r[15]), r[16] == "Y", _num(r[17]), _num(r[18]), r[19])
                      for r in assets])
        n += _replace(cur, "core.fa_deprn",
                      ["asset_id", "book_type_code", "period_counter", "period_name", "period_start", "deprn_amount",
                       "ytd_deprn", "deprn_reserve"],
                      [(_int(r[1]), r[0], _int(r[2]), r[3], r[4], _num(r[5]), _num(r[6]), _num(r[7])) for r in deprn])
        cur.execute("DELETE FROM core.fin_period_status WHERE application = 'FA'")
        n += _replace_rows(cur, "core.fin_period_status",
                           ["row_key", "application", "book_type_code", "period_name", "period_year", "period_num",
                            "start_date", "end_date", "status_code", "deprn_run", "last_update_date"],
                           [(f"FA|{r[0]}|{r[1]}", "FA", r[0], r[1], _int(r[3]), _int(r[4]), r[5], r[6],
                             "C" if r[7] else "O", r[8], None) for r in periods])
        rows_loaded = n
        run.pg.commit()
        refresh_marts_for_job(job)
        run.finish("success", rows_read, rows_loaded)
        logger.info("[%s] books=%s assets=%s deprn=%s", job, books, len(assets), len(deprn))
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_loaded, error=str(e))
        run.close()
        raise
    run.close()
    return {"status": "success", "rows_read": rows_read, "rows_loaded": rows_loaded, "at": str(date.today())}
