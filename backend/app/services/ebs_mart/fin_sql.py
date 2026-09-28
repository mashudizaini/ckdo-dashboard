"""
Finance close, Cash Management and Fixed Assets (library v2 sections 12-13,
blueprint 4.5): the data behind the EBS Finance Controller model and the
ebs-ce-fa / ebs-period-close skills.

  gl_period_status        status of each period per application (GL, AP, AR,
                          PO, INV org 121, OPM costing, FA) — "sudah boleh
                          closing?" starts here
  sla_gl_gap              what keeps subledgers and GL apart: events not yet
                          accounted, draft/final entries not transferred,
                          unposted GL journals
  ar_autoinvoice_error    RA_INTERFACE lines waiting in / rejected by AutoInvoice
  so_shipped_not_invoiced SO lines shipped but without an AR invoice
  ce_unreconciled         bank statement lines and system transactions (AP
                          payments, AR receipts, bank transfers) not reconciled
  fa_asset_register       assets in the corporate book with cost, reserve, NBV
  fa_depreciation         depreciation per asset × FA period (24 months)

mart_sql.py merges these into its registries. Bank account numbers are never
extracted (blueprint 4.5: "CE_BANK_ACCOUNTS (nama saja)").
"""
from app.services.ebs_mart.constants import SO_CMO_LINE_TYPE, SO_EXPORT_TYPE, SO_ORDER_TYPES

TODAY = "(now() AT TIME ZONE 'Asia/Jakarta')::date"

FIN_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS core.fin_period_status (
        row_key          text PRIMARY KEY,
        application      text,
        book_type_code   text,
        period_name      text,
        period_year      int,
        period_num       int,
        start_date       date,
        end_date         date,
        status_code      text,
        deprn_run        text,
        last_update_date timestamp,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.fin_sla_gap (
        row_key            text PRIMARY KEY,
        kind               text,
        application        text,
        period_name        text,
        txn_date           date,
        event_type         text,
        entity_code        text,
        transaction_number text,
        amount_idr         numeric,
        detail             text,
        loaded_at          timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.ar_interface_line (
        row_key           text PRIMARY KEY,
        interface_line_id bigint,
        batch_source_name text,
        line_context      text,
        so_number         text,
        so_line_id        bigint,
        customer_name     text,
        trx_date          date,
        gl_date           date,
        currency_code     text,
        amount            numeric,
        amount_idr        numeric,
        interface_status  text,
        request_id        bigint,
        created_date      timestamp,
        error_message     text,
        invalid_value     text,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.ce_bank_account (
        bank_account_id       bigint PRIMARY KEY,
        bank_account_name     text,
        bank_name             text,
        currency_code         text,
        last_statement_number text,
        last_statement_date   date,
        loaded_at             timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.ce_unreconciled (
        row_key          text PRIMARY KEY,
        side             text,
        source           text,
        bank_account_id  bigint,
        doc_number       text,
        trx_date         date,
        currency_code    text,
        amount_entered   numeric,
        amount_idr       numeric,
        status           text,
        description      text,
        statement_number text,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.fa_asset (
        asset_id               bigint,
        book_type_code         text,
        asset_number           text,
        description            text,
        asset_type             text,
        tag_number             text,
        category               text,
        category_desc          text,
        location               text,
        date_placed_in_service date,
        cost                   numeric,
        original_cost          numeric,
        salvage_value          numeric,
        life_in_months         int,
        deprn_method           text,
        units                  numeric,
        is_retired             boolean,
        deprn_reserve          numeric,
        ytd_deprn              numeric,
        last_deprn_period      text,
        loaded_at              timestamptz DEFAULT now(),
        PRIMARY KEY (asset_id, book_type_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.fa_deprn (
        asset_id       bigint,
        book_type_code text,
        period_counter bigint,
        period_name    text,
        period_start   date,
        deprn_amount   numeric,
        ytd_deprn      numeric,
        deprn_reserve  numeric,
        loaded_at      timestamptz DEFAULT now(),
        PRIMARY KEY (asset_id, book_type_code, period_counter)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_fa_deprn_period ON core.fa_deprn (period_name)",
]

_BUSINESS_TYPE = (
    f"(CASE WHEN l.order_type = '{SO_EXPORT_TYPE}' THEN 'Export' "
    f"WHEN l.line_type = '{SO_CMO_LINE_TYPE}' THEN 'CMO' ELSE 'Local' END)"
)
_SO_TYPES = ", ".join(f"'{t}'" for t in SO_ORDER_TYPES)

# Order of applications in a close checklist (library 13: PO/AP → OM/AR →
# INV/OPM → CE/FA → GL).
_APP_ORDER = ("CASE p.application WHEN 'PO' THEN 1 WHEN 'AP' THEN 2 WHEN 'AR' THEN 3 WHEN 'INV' THEN 4 "
              "WHEN 'OPM' THEN 5 WHEN 'FA' THEN 6 WHEN 'GL' THEN 7 ELSE 8 END")

FIN_MART_SQL: dict[str, str] = {
    "gl_period_status": f"""
        SELECT p.row_key,
               p.application,
               {_APP_ORDER}                                        AS application_order,
               p.book_type_code,
               p.period_name,
               p.period_year,
               p.period_num,
               p.start_date,
               p.end_date,
               p.status_code,
               CASE WHEN p.application IN ('GL', 'AP', 'AR', 'PO') THEN
                        CASE p.status_code WHEN 'O' THEN 'Open' WHEN 'C' THEN 'Closed' WHEN 'F' THEN 'Future-Entry'
                             WHEN 'N' THEN 'Never Opened' WHEN 'P' THEN 'Permanently Closed'
                             WHEN 'W' THEN 'Close Pending' ELSE p.status_code END
                    WHEN p.application = 'OPM' THEN
                        CASE p.status_code WHEN 'O' THEN 'Open' WHEN 'F' THEN 'Frozen' WHEN 'C' THEN 'Closed'
                             ELSE p.status_code END
                    ELSE CASE p.status_code WHEN 'O' THEN 'Open' WHEN 'C' THEN 'Closed' WHEN 'P' THEN 'Close Pending'
                              WHEN 'F' THEN 'Future' ELSE p.status_code END
               END                                                 AS status,
               p.deprn_run,
               p.last_update_date
          FROM core.fin_period_status p
    """,

    "sla_gl_gap": f"""
        SELECT g.row_key,
               g.kind,
               CASE g.kind WHEN 'UNACCOUNTED' THEN 'Event belum di-account'
                           WHEN 'ACCOUNTING_ERROR' THEN 'Accounting error'
                           WHEN 'DRAFT' THEN 'Entry draft (belum final)'
                           WHEN 'NOT_TRANSFERRED' THEN 'Final, belum transfer ke GL'
                           WHEN 'GL_UNPOSTED' THEN 'Jurnal GL belum posting'
                           ELSE g.kind END                         AS kind_desc,
               g.application,
               g.period_name,
               g.txn_date,
               {TODAY} - g.txn_date                                AS age_days,
               g.event_type,
               g.entity_code,
               g.transaction_number,
               g.amount_idr,
               g.detail
          FROM core.fin_sla_gap g
    """,

    "ar_autoinvoice_error": f"""
        SELECT a.row_key,
               a.interface_line_id,
               a.batch_source_name,
               a.so_number,
               a.so_line_id,
               a.customer_name,
               a.trx_date,
               a.gl_date,
               a.currency_code,
               a.amount,
               a.amount_idr,
               CASE WHEN a.error_message IS NOT NULL THEN 'Error'
                    WHEN a.interface_status IS NULL THEN 'Menunggu AutoInvoice'
                    ELSE a.interface_status END                    AS status,
               a.error_message,
               a.invalid_value,
               a.request_id,
               a.created_date,
               {TODAY} - a.created_date::date                      AS age_days
          FROM core.ar_interface_line a
         -- interface_status P = already processed into an invoice; the rows
         -- stay in the interface table until purged and are not pending work.
         WHERE COALESCE(a.interface_status, '-') <> 'P'
    """,

    # Shipped, not cancelled, and no AR invoice line points back to it (nor
    # has OM recorded it invoiced). AutoInvoice errors for the line, if any,
    # ride along — "kenapa belum jadi invoice?" is the next question.
    "so_shipped_not_invoiced": f"""
        SELECT l.line_id,
               l.order_number,
               l.line_number,
               l.shipment_number,
               l.order_type,
               {_BUSINESS_TYPE}                                     AS business_type,
               l.line_status,
               l.customer_num,
               l.customer_name,
               l.item_code,
               l.item_desc,
               l.uom,
               l.shipped_qty,
               COALESCE(l.invoiced_qty, 0)                          AS invoiced_qty,
               l.actual_shipment_date,
               {TODAY} - l.actual_shipment_date                     AS days_since_ship,
               l.currency_code,
               l.shipped_qty * l.unit_selling_price                 AS amount_entered,
               l.shipped_qty * l.unit_selling_price * COALESCE(l.rate_idr, 1) AS amount_idr,
               e.errors                                             AS autoinvoice_errors,
               e.lines_in_interface
          FROM core.fact_so_line l
          LEFT JOIN (SELECT so_line_id, COUNT(DISTINCT interface_line_id) AS lines_in_interface,
                            STRING_AGG(DISTINCT error_message, '; ') AS errors
                       FROM core.ar_interface_line WHERE COALESCE(interface_status, '-') <> 'P'
                      GROUP BY so_line_id) e ON e.so_line_id = l.line_id
         WHERE COALESCE(l.shipped_qty, 0) > 0
           AND COALESCE(l.cancelled_flag, 'N') <> 'Y'
           AND l.order_type IN ({_SO_TYPES})
           AND COALESCE(l.invoiced_qty, 0) < l.shipped_qty
           AND NOT EXISTS (SELECT 1 FROM core.fact_ar_invoice_line i WHERE i.so_line_id = l.line_id)
    """,

    "ce_unreconciled": f"""
        SELECT u.row_key,
               u.side,
               CASE u.side WHEN 'BANK' THEN 'Di rekening koran, belum ada di sistem'
                           ELSE 'Di sistem, belum muncul di rekening koran' END AS side_desc,
               u.source,
               b.bank_account_name,
               b.bank_name,
               u.doc_number,
               u.trx_date,
               {TODAY} - u.trx_date                                AS age_days,
               u.currency_code,
               u.amount_entered,
               u.amount_idr,
               u.status,
               u.description,
               u.statement_number,
               b.last_statement_date,
               b.last_statement_number
          FROM core.ce_unreconciled u
          LEFT JOIN core.ce_bank_account b ON b.bank_account_id = u.bank_account_id
    """,

    "fa_asset_register": """
        SELECT MD5(CONCAT_WS('|', a.asset_id, a.book_type_code))   AS row_key,
               a.asset_id,
               a.book_type_code,
               a.asset_number,
               a.description,
               a.asset_type,
               a.tag_number,
               a.category,
               a.category_desc,
               a.location,
               a.date_placed_in_service,
               a.cost,
               a.original_cost,
               a.salvage_value,
               COALESCE(a.deprn_reserve, 0)                        AS accumulated_depreciation,
               a.cost - COALESCE(a.deprn_reserve, 0)               AS nbv,
               a.ytd_deprn,
               a.last_deprn_period,
               a.life_in_months,
               a.deprn_method,
               a.units,
               CASE WHEN a.is_retired THEN 'Retired'
                    WHEN a.asset_type = 'CIP' THEN 'CIP'
                    WHEN a.cost <> 0 AND a.cost - COALESCE(a.deprn_reserve, 0) <= COALESCE(a.salvage_value, 0)
                         THEN 'Fully reserved'
                    ELSE 'Aktif' END                               AS asset_status
          FROM core.fa_asset a
    """,

    "fa_depreciation": """
        SELECT MD5(CONCAT_WS('|', d.asset_id, d.book_type_code, d.period_counter)) AS row_key,
               d.asset_id,
               a.asset_number,
               a.description,
               a.category,
               a.category_desc,
               a.location,
               d.book_type_code,
               d.period_name,
               d.period_counter,
               d.period_start,
               d.deprn_amount,
               d.ytd_deprn,
               d.deprn_reserve
          FROM core.fa_deprn d
          LEFT JOIN core.fa_asset a ON a.asset_id = d.asset_id AND a.book_type_code = d.book_type_code
    """,
}

FIN_UNIQUE_INDEX: dict[str, list[str]] = {
    "gl_period_status": ["row_key"],
    "sla_gl_gap": ["row_key"],
    "ar_autoinvoice_error": ["row_key"],
    "so_shipped_not_invoiced": ["line_id"],
    "ce_unreconciled": ["row_key"],
    "fa_asset_register": ["row_key"],
    "fa_depreciation": ["row_key"],
}

FIN_EXTRA_INDEXES: dict[str, list[str]] = {
    "gl_period_status": ["period_name"],
    "sla_gl_gap": ["application", "period_name"],
    "ar_autoinvoice_error": ["so_number"],
    "so_shipped_not_invoiced": ["order_number", "customer_name"],
    "ce_unreconciled": ["bank_account_name", "trx_date"],
    "fa_asset_register": ["asset_number", "category"],
    "fa_depreciation": ["period_name", "category"],
}

FIN_MARTS_BY_JOB: dict[str, list[str]] = {
    "etl_mart_close": ["gl_period_status", "sla_gl_gap", "ar_autoinvoice_error", "so_shipped_not_invoiced",
                       "ce_unreconciled"],
    "etl_mart_fa": ["gl_period_status", "fa_asset_register", "fa_depreciation"],
}
