"""
Definitions of the phase-1 marts (blueprint sections 5 and 6).

Each mart is a MATERIALIZED VIEW over core.*, refreshed CONCURRENTLY after
its ETL succeeds and once a day regardless (days_overdue and days_to_expiry
are computed at refresh time, so a mart that is not refreshed for a day
reports yesterday's ages — blueprint 6.2).

Conventions (blueprint "Konvensi kolom mart"):
  - English snake_case column names; Indonesian descriptions and synonyms
    live in meta.column_catalog, not here.
  - Every amount has *_idr for aggregation and *_entered + currency_code
    for display.
  - Codes are already translated (aging_bucket, subinventory_type, status).
  - Periods carry period_name (JUL-26) and period_start_date.

schema.ensure_marts() hashes each SQL text and drops/recreates the view when
the text changes, so editing a definition here is a deploy, not a migration.
"""
from app.services.ebs_mart.constants import AP_COA_WHITELIST, AP_LEGACY_PAID_CUTOFF

_COA_LIST = ", ".join(f"'{c}'" for c in AP_COA_WHITELIST)

# One row per invoice with its header attributes, from the schedule table
# (which repeats them per payment_num).
_AP_INVOICE_HEADER = """
    SELECT DISTINCT ON (invoice_id)
           invoice_id, invoice_num, invoice_type, invoice_date, gl_date,
           invoice_currency_code, invoice_amount, invoice_amount_idr,
           vendor_num, vendor_name, vendor_site_code, liability_account, cancelled_date
      FROM core.fact_ap_payment_schedule
     ORDER BY invoice_id, payment_num
"""

MART_SQL: dict[str, str] = {
    # Same population as the Dashboard's AP Outstanding report
    # (accounting_service.get_ap_outstanding): liability accounts in the AP
    # whitelist, schedules still unpaid or partially paid, invoices after the
    # legacy cutoff, not cancelled, GL date not in the future.
    "ap_open_invoice": f"""
        SELECT s.invoice_id,
               s.payment_num,
               s.vendor_num,
               s.vendor_name,
               s.vendor_site_code,
               s.invoice_num,
               s.invoice_type,
               s.invoice_date,
               s.gl_date,
               UPPER(TO_CHAR(s.gl_date, 'MON-YY'))           AS gl_period_name,
               DATE_TRUNC('month', s.gl_date)::date          AS gl_period_start_date,
               s.due_date,
               s.invoice_currency_code                       AS currency_code,
               s.gross_amount                                AS gross_amount_entered,
               s.amount_remaining                            AS amount_remaining_entered,
               s.amount_remaining_idr,
               s.liability_account,
               (CURRENT_DATE - s.due_date)                   AS days_overdue,
               CASE WHEN s.due_date >= CURRENT_DATE          THEN 'Current'
                    WHEN CURRENT_DATE - s.due_date <= 30     THEN '1-30'
                    WHEN CURRENT_DATE - s.due_date <= 60     THEN '31-60'
                    WHEN CURRENT_DATE - s.due_date <= 90     THEN '61-90'
                    ELSE '>90' END                           AS aging_bucket,
               CASE WHEN s.due_date >= CURRENT_DATE          THEN 0
                    WHEN CURRENT_DATE - s.due_date <= 30     THEN 1
                    WHEN CURRENT_DATE - s.due_date <= 60     THEN 2
                    WHEN CURRENT_DATE - s.due_date <= 90     THEN 3
                    ELSE 4 END                               AS aging_bucket_order,
               s.description
          FROM core.fact_ap_payment_schedule s
         WHERE s.amount_remaining <> 0
           AND s.cancelled_date IS NULL
           AND s.payment_status_flag IN ('N', 'P')
           AND s.gl_date <= CURRENT_DATE
           AND s.invoice_date > DATE '{AP_LEGACY_PAID_CUTOFF}'
           AND s.liability_account IN ({_COA_LIST})
    """,

    # Reversed payment lines come in pairs (original + negative), both
    # flagged; dropping both leaves the net. Voided checks are not payments.
    "ap_payment_history": f"""
        SELECT p.invoice_payment_id,
               p.check_id,
               p.payment_number,
               p.payment_date,
               p.accounting_date,
               UPPER(TO_CHAR(p.accounting_date, 'MON-YY'))   AS period_name,
               DATE_TRUNC('month', p.accounting_date)::date  AS period_start_date,
               p.payment_method,
               p.bank_account_name,
               p.payment_status,
               i.invoice_currency_code                       AS currency_code,
               p.amount_entered,
               p.amount_idr,
               p.invoice_id,
               i.invoice_num,
               i.invoice_type,
               i.invoice_date,
               i.vendor_num,
               i.vendor_name,
               i.vendor_site_code
          FROM core.fact_ap_payment p
          LEFT JOIN ({_AP_INVOICE_HEADER}) i ON i.invoice_id = p.invoice_id
         WHERE COALESCE(p.reversal_flag, 'N') <> 'Y'
           AND p.void_date IS NULL
    """,

    "ap_invoice_hold": f"""
        SELECT h.hold_id,
               h.invoice_id,
               i.invoice_num,
               i.invoice_type,
               i.invoice_date,
               i.vendor_num,
               i.vendor_name,
               i.invoice_currency_code                       AS currency_code,
               i.invoice_amount                              AS invoice_amount_entered,
               i.invoice_amount_idr,
               h.hold_code,
               h.hold_desc,
               h.hold_reason,
               h.hold_date,
               (CURRENT_DATE - h.hold_date::date)            AS days_on_hold
          FROM core.fact_ap_hold h
          LEFT JOIN ({_AP_INVOICE_HEADER}) i ON i.invoice_id = h.invoice_id
         WHERE i.cancelled_date IS NULL
    """,

    # Blueprint 6.4. subinventory_type comes from meta.subinventory_class when
    # an administrator has classified the subinventory (the blueprint's open
    # decision: the official list belongs to Warehouse/QA), otherwise from a
    # name heuristic — see core.dim_subinventory.guessed_type.
    "inv_onhand_lot": """
        SELECT o.row_key,
               o.organization_code,
               o.item_code,
               o.item_desc,
               o.uom,
               c.item_category,
               o.subinventory_code,
               s.description                                         AS subinventory_desc,
               COALESCE(sc.subinventory_type, s.guessed_type, 'GOOD') AS subinventory_type,
               o.locator,
               o.lot_number,
               o.lot_status,
               o.origination_date,
               o.expiration_date,
               (o.expiration_date - CURRENT_DATE)                    AS days_to_expiry,
               CASE WHEN o.expiration_date IS NULL                THEN 'No ED'
                    WHEN o.expiration_date < CURRENT_DATE         THEN 'Expired'
                    WHEN o.expiration_date - CURRENT_DATE <= 90   THEN '<=90 hari'
                    WHEN o.expiration_date - CURRENT_DATE <= 180  THEN '91-180 hari'
                    ELSE '>180 hari' END                             AS expiry_bucket,
               o.onhand_qty
          FROM core.snap_onhand_lot o
          LEFT JOIN core.dim_subinventory s  ON s.subinventory_code = o.subinventory_code
          LEFT JOIN meta.subinventory_class sc ON sc.subinventory_code = o.subinventory_code
          LEFT JOIN core.dim_item c          ON c.inventory_item_id = o.inventory_item_id
         WHERE o.onhand_qty <> 0
    """,

    # Built on eis.fact_inventory_txn, which etl_inventory_txn already loads
    # incrementally from MTL_MATERIAL_TRANSACTIONS for the PPWH dashboard —
    # the same rows the Kartu Stok shows, so the numbers agree.
    #
    # All inventory organizations, not only 121: that table carries
    # organization_code but not organization_id. organization_code is a
    # column here so a question about one org can filter on it.
    "inv_movement_daily": """
        SELECT MD5(CONCAT_WS('|', t.organization_code, t.item_code, t.transaction_date::date,
                             t.transaction_type_name, t.subinventory_code, t.uom))  AS row_key,
               t.transaction_date::date                              AS txn_date,
               UPPER(TO_CHAR(t.transaction_date, 'MON-YY'))          AS period_name,
               DATE_TRUNC('month', t.transaction_date)::date         AS period_start_date,
               t.organization_code,
               t.item_code,
               MAX(t.item_description)                               AS item_desc,
               t.uom,
               t.subinventory_code,
               t.transaction_type_name                               AS transaction_type,
               SUM(CASE WHEN t.quantity > 0 THEN t.quantity ELSE 0 END)  AS qty_in,
               SUM(CASE WHEN t.quantity < 0 THEN -t.quantity ELSE 0 END) AS qty_out,
               SUM(t.quantity)                                       AS net_qty,
               COUNT(*)                                              AS txn_count
          FROM eis.fact_inventory_txn t
         GROUP BY t.organization_code, t.item_code, t.transaction_date::date,
                  UPPER(TO_CHAR(t.transaction_date, 'MON-YY')),
                  DATE_TRUNC('month', t.transaction_date)::date,
                  t.transaction_type_name, t.subinventory_code, t.uom
    """,
}

# Unique index per mart: required by REFRESH MATERIALIZED VIEW CONCURRENTLY,
# which is what lets chat keep reading the old rows while a refresh runs.
MART_UNIQUE_INDEX: dict[str, list[str]] = {
    "ap_open_invoice": ["invoice_id", "payment_num"],
    "ap_payment_history": ["invoice_payment_id"],
    "ap_invoice_hold": ["hold_id"],
    "inv_onhand_lot": ["row_key"],
    "inv_movement_daily": ["row_key"],
}

MART_EXTRA_INDEXES: dict[str, list[str]] = {
    "ap_open_invoice": ["vendor_name", "due_date", "aging_bucket"],
    "ap_payment_history": ["vendor_name", "payment_date", "invoice_num"],
    "ap_invoice_hold": ["vendor_name"],
    "inv_onhand_lot": ["item_code", "expiration_date", "subinventory_code"],
    "inv_movement_daily": ["item_code", "txn_date"],
}

# Which marts to refresh after which job succeeds.
MARTS_BY_JOB: dict[str, list[str]] = {
    "etl_mart_ap": ["ap_open_invoice", "ap_payment_history", "ap_invoice_hold"],
    "etl_mart_inventory": ["inv_onhand_lot"],
    "etl_inventory_txn": ["inv_movement_daily"],
}
