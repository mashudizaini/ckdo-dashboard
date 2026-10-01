"""
Rest of the library v2 tool catalog (section 3): the marts behind
lookup_master, po_get_document, po_get_pending_approval, ap_get_invoice,
ap_get_due_forecast, ap_get_withholding, so_get_order, so_get_holds,
opm_get_item_cost, gl_get_account_movement, gl_get_budget_vs_actual and
it_get_interface_errors.

Most are views over core tables other jobs already fill (all AP invoices,
all PO shipments, all SO lines, OPM item costs, GL balances). Four need new
extracts, loaded by etl_mart_ext (ebs_mart_ext_tasks.py): documents waiting
for approval, SO holds, AP withholding distributions, GL budget and
encumbrance balances — plus interface rows for sa_interface_error, which is
an sa_* mart on purpose: interface errors are IT's (library 3.2b moves
it_get_interface_errors to the allowlist), so it inherits the llm_sa_ro fence.
"""
TODAY = "(now() AT TIME ZONE 'Asia/Jakarta')::date"

EXT_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS core.doc_approval_pending (
        row_key          text PRIMARY KEY,
        doc_type         text,
        doc_id           bigint,
        doc_number       text,
        doc_subtype      text,
        authorization_status text,
        created_date     timestamp,
        submitted_date   timestamp,
        last_action      text,
        pending_approver text,
        preparer         text,
        vendor_name      text,
        currency_code    text,
        amount_entered   numeric,
        amount_idr       numeric,
        description      text,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.so_hold (
        order_hold_id    bigint PRIMARY KEY,
        header_id        bigint,
        order_number     text,
        order_type       text,
        line_id          bigint,
        line_number      text,
        customer_name    text,
        hold_name        text,
        hold_type        text,
        applied_date     timestamp,
        hold_until_date  date,
        hold_comment     text,
        applied_by       text,
        order_amount_idr numeric,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.ap_withholding (
        invoice_distribution_id bigint PRIMARY KEY,
        invoice_id       bigint,
        invoice_num      text,
        invoice_date     date,
        accounting_date  date,
        period_name      text,
        vendor_num       text,
        vendor_name      text,
        tax_name         text,
        tax_rate         numeric,
        currency_code    text,
        amount_entered   numeric,
        amount_idr       numeric,
        account_code     text,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.fact_gl_budget (
        row_key          text PRIMARY KEY,
        kind             text,
        budget_name      text,
        encumbrance_type text,
        code_combination_id bigint,
        period_name      text,
        period_year      int,
        period_num       int,
        period_start_date date,
        segment3         text,
        segment4         text,
        account_type     text,
        period_net       numeric,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
    # Encumbrance is a balance (reserved, then relieved across periods and
    # years), so its opening balance is kept next to the period movement.
    "ALTER TABLE core.fact_gl_budget ADD COLUMN IF NOT EXISTS begin_balance numeric",
    """
    CREATE TABLE IF NOT EXISTS core.it_interface_row (
        row_key        text PRIMARY KEY,
        interface_name text,
        source         text,
        doc_ref        text,
        status         text,
        error_code     text,
        error_message  text,
        txn_date       date,
        created_date   timestamp,
        amount         numeric,
        quantity       numeric,
        item_code      text,
        request_id     bigint,
        row_count      int,
        loaded_at      timestamptz DEFAULT now()
    )
    """,
]

EXT_MART_SQL: dict[str, str] = {
    # One searchable list of codes and names, so a partial name ("mannitol",
    # "kyongbo", "biaya listrik") becomes the exact code the other tools want.
    "master_lookup": """
        SELECT MD5(t.type || '|' || t.code) AS row_key, t.type, t.code, t.name, t.extra
          FROM (
            SELECT 'item' AS type, item_code AS code, MAX(item_desc) AS name,
                   MAX(CONCAT_WS(' · ', uom, item_category)) AS extra
              FROM core.dim_item WHERE item_code IS NOT NULL GROUP BY item_code
            UNION ALL
            SELECT 'supplier', vendor_num, MAX(vendor_name), NULL
              FROM (SELECT vendor_num, vendor_name FROM core.fact_ap_payment_schedule
                    UNION SELECT vendor_num, vendor_name FROM core.fact_po_shipment) s
             WHERE vendor_num IS NOT NULL GROUP BY vendor_num
            UNION ALL
            SELECT 'customer', customer_num, MAX(customer_name), NULL
              FROM (SELECT customer_num, customer_name FROM core.fact_ar_schedule
                    UNION SELECT customer_num, customer_name FROM core.fact_so_line) c
             WHERE customer_num IS NOT NULL GROUP BY customer_num
            UNION ALL
            SELECT 'account', m.account_code, MAX(COALESCE(m.account_desc, d.description)),
                   MAX(CONCAT_WS(' · ', m.statement, m.section, m.line))
              FROM meta.gl_account_map m
              LEFT JOIN core.dim_gl_segment_value d ON d.segment_column = 'SEGMENT4' AND d.value = m.account_code
             GROUP BY m.account_code
            UNION ALL
            SELECT 'department', value, MAX(description), NULL
              FROM core.dim_gl_segment_value WHERE segment_column = 'SEGMENT3' GROUP BY value
          ) t
    """,

    # Every AP invoice (paid, open, cancelled) with its payments and holds.
    "ap_invoice": f"""
        WITH inv AS (
            SELECT invoice_id,
                   MIN(invoice_num) AS invoice_num, MIN(invoice_type) AS invoice_type,
                   MIN(invoice_date) AS invoice_date, MIN(gl_date) AS gl_date,
                   MIN(vendor_num) AS vendor_num, MIN(vendor_name) AS vendor_name,
                   MIN(vendor_site_code) AS vendor_site_code, MIN(invoice_currency_code) AS currency_code,
                   MIN(invoice_amount) AS invoice_amount_entered, MIN(invoice_amount_idr) AS invoice_amount_idr,
                   SUM(amount_remaining) AS amount_remaining_entered, SUM(amount_remaining_idr) AS amount_remaining_idr,
                   MIN(due_date) FILTER (WHERE amount_remaining <> 0) AS next_due_date,
                   MIN(due_date) AS first_due_date,
                   MIN(description) AS description, MIN(liability_account) AS liability_account,
                   MIN(cancelled_date) AS cancelled_date
              FROM core.fact_ap_payment_schedule GROUP BY invoice_id
        ), pay AS (
            SELECT invoice_id, COUNT(*) AS payment_count, SUM(amount_idr) AS paid_amount_idr,
                   MAX(payment_date) AS last_payment_date,
                   STRING_AGG(DISTINCT payment_number, ', ') AS payment_numbers
              FROM core.fact_ap_payment
             WHERE void_date IS NULL AND COALESCE(reversal_flag, 'N') <> 'Y'
             GROUP BY invoice_id
        ), hld AS (
            SELECT invoice_id, COUNT(*) AS active_holds, STRING_AGG(DISTINCT hold_code, ', ') AS hold_codes
              FROM core.fact_ap_hold GROUP BY invoice_id
        )
        SELECT i.*,
               CASE WHEN i.cancelled_date IS NOT NULL THEN 'Cancelled'
                    WHEN COALESCE(i.amount_remaining_entered, 0) = 0 THEN 'Lunas'
                    WHEN i.amount_remaining_entered <> i.invoice_amount_entered THEN 'Sebagian dibayar'
                    ELSE 'Belum dibayar' END                        AS payment_status,
               CASE WHEN i.amount_remaining_entered <> 0 THEN {TODAY} - i.next_due_date END AS days_overdue,
               COALESCE(p.payment_count, 0) AS payment_count, p.paid_amount_idr, p.last_payment_date, p.payment_numbers,
               COALESCE(h.active_holds, 0) AS active_holds, h.hold_codes
          FROM inv i
          LEFT JOIN pay p ON p.invoice_id = i.invoice_id
          LEFT JOIN hld h ON h.invoice_id = i.invoice_id
    """,

    # Every PO shipment, open or closed, for "tampilkan PO X".
    "po_shipment": """
        SELECT s.line_location_id, s.po_header_id, s.po_number, s.release_num, s.po_type, s.po_status, s.po_date,
               s.approved_date, s.vendor_num, s.vendor_name, s.vendor_site_code, s.buyer_name, s.currency_code,
               s.line_num, s.shipment_num, s.item_code, s.item_desc, s.uom, s.unit_price AS unit_price_entered,
               s.quantity AS qty_ordered, s.quantity_received AS qty_received, s.quantity_billed AS qty_billed,
               s.quantity_cancelled AS qty_cancelled,
               s.quantity * s.unit_price                                  AS amount_entered,
               s.quantity * s.unit_price * COALESCE(s.rate_idr, 1)        AS amount_idr,
               s.need_by_date, s.promised_date, s.closed_code, s.cancel_flag, s.line_cancel_flag, s.match_option,
               s.payment_term, c.item_category, s.material_type, s.country_of_origin, s.organization_name,
               s.pr_number, s.requestor, s.receipt_number, s.receipt_date,
               COALESCE(s.quantity, 0) - COALESCE(s.quantity_received, 0)
                   - COALESCE(s.quantity_cancelled, 0)                  AS qty_outstanding
          FROM core.fact_po_shipment s
          LEFT JOIN core.dim_item c ON c.inventory_item_id = s.item_id
    """,

    "po_approval_pending": f"""
        SELECT row_key, doc_type, doc_number, doc_subtype, authorization_status, preparer, pending_approver,
               last_action, submitted_date, created_date,
               {TODAY} - COALESCE(submitted_date, created_date)::date AS days_waiting,
               vendor_name, currency_code, amount_entered, amount_idr, description
          FROM core.doc_approval_pending
    """,

    "ap_withholding": """
        SELECT invoice_distribution_id, invoice_id, invoice_num, invoice_date, accounting_date,
               UPPER(period_name) AS period_name, vendor_num, vendor_name, COALESCE(tax_name, '(tanpa kode)') AS tax_name,
               tax_rate, currency_code, amount_entered, amount_idr, account_code
          FROM core.ap_withholding
    """,

    # Every SO line with its delivery and invoice references.
    "so_order_line": """
        SELECT l.line_id, l.order_number, l.order_type, l.line_type, l.ordered_date, l.header_status, l.line_status,
               l.customer_num, l.customer_name, l.line_number, l.shipment_number, l.item_code, l.item_desc, l.uom,
               l.ordered_qty, l.shipped_qty, l.invoiced_qty, l.cancelled_qty, l.unit_selling_price, l.currency_code,
               l.ordered_qty * l.unit_selling_price * COALESCE(l.rate_idr, 1) AS amount_ordered_idr,
               l.request_date, l.schedule_ship_date, l.actual_shipment_date,
               d.delivery_names, d.lot_numbers, i.invoice_numbers
          FROM core.fact_so_line l
          LEFT JOIN (SELECT source_line_id, STRING_AGG(DISTINCT delivery_name, ', ') AS delivery_names,
                            STRING_AGG(DISTINCT lot_number, ', ') AS lot_numbers
                       FROM core.fact_so_delivery_detail GROUP BY source_line_id) d ON d.source_line_id = l.line_id
          LEFT JOIN (SELECT so_line_id, STRING_AGG(DISTINCT trx_number, ', ') AS invoice_numbers
                       FROM core.fact_ar_invoice_line GROUP BY so_line_id) i ON i.so_line_id = l.line_id
    """,

    "so_hold": f"""
        SELECT order_hold_id, order_number, order_type, line_number, customer_name, hold_name, hold_type,
               applied_date, {TODAY} - applied_date::date AS days_on_hold, hold_until_date, hold_comment, applied_by,
               order_amount_idr, CASE WHEN line_id IS NULL THEN 'Order' ELSE 'Line' END AS hold_level
          FROM core.so_hold
    """,

    "opm_item_cost": """
        SELECT MD5(CONCAT_WS('|', c.inventory_item_id, c.period_id)) AS row_key,
               i.item_code, i.item_desc, i.uom, i.item_category,
               c.period_code, c.period_start_date, c.period_end_date, c.period_status, c.cost_method,
               c.unit_cost, c.cost_components::text AS cost_components
          FROM core.fact_item_cost c
          LEFT JOIN core.dim_item i ON i.inventory_item_id = c.inventory_item_id
    """,

    # Long format — one row per kind: BUDGET (per budget name), ENCUMBRANCE
    # (per encumbrance type), ACTUAL. Tools pivot, so an actual amount is
    # never repeated once per budget version. Amounts use the statement's
    # sign (expense and revenue positive), like pl_monthly.
    "gl_budget_vs_actual": """
        WITH src AS (
            SELECT kind, COALESCE(budget_name, encumbrance_type) AS version_name, period_name, period_year,
                   period_num, period_start_date, segment3, segment4, account_type, period_net,
                   COALESCE(begin_balance, 0) + period_net AS end_balance
              FROM core.fact_gl_budget
            UNION ALL
            SELECT 'ACTUAL', NULL, period_name, period_year, period_num, period_start_date, segment3, segment4,
                   account_type, period_net_dr - period_net_cr,
                   begin_balance_dr - begin_balance_cr + period_net_dr - period_net_cr
              FROM core.fact_gl_balance
             WHERE account_type IN ('E', 'R') AND NOT is_adjustment
               AND period_year >= COALESCE((SELECT MIN(period_year) FROM core.fact_gl_budget),
                                           EXTRACT(YEAR FROM now())::int - 1)
        )
        SELECT MD5(CONCAT_WS('|', s.kind, s.version_name, s.period_name, s.segment3, s.segment4)) AS row_key,
               s.kind, s.version_name, s.period_name, s.period_year, s.period_num, MIN(s.period_start_date) AS period_start_date,
               s.segment4 AS account_code, MAX(COALESCE(m.account_desc, a.description)) AS account_desc,
               MAX(s.account_type) AS account_type, MAX(m.section) AS pl_section, MAX(m.line) AS pl_line,
               s.segment3 AS dept_code, MAX(d.description) AS dept_desc,
               FALSE AS is_adjustment,
               SUM(s.period_net) * COALESCE(MAX(m.sign), CASE WHEN MAX(s.account_type) = 'R' THEN -1 ELSE 1 END) AS amount,
               SUM(s.end_balance) * COALESCE(MAX(m.sign), CASE WHEN MAX(s.account_type) = 'R' THEN -1 ELSE 1 END) AS end_balance
          FROM src s
          LEFT JOIN meta.gl_account_map m       ON m.account_code = s.segment4
          LEFT JOIN core.dim_gl_segment_value a ON a.segment_column = 'SEGMENT4' AND a.value = s.segment4
          LEFT JOIN core.dim_gl_segment_value d ON d.segment_column = 'SEGMENT3' AND d.value = s.segment3
         GROUP BY s.kind, s.version_name, s.period_name, s.period_year, s.period_num, s.segment3, s.segment4
        HAVING SUM(s.period_net) <> 0 OR SUM(s.end_balance) <> 0
    """,

    # IT only (sa_ prefix → llm_sa_ro, allowlist). AR comes from the AutoInvoice
    # rows etl_mart_close already loads.
    "sa_interface_error": f"""
        SELECT row_key, interface_name, source, doc_ref, status, error_code, error_message, txn_date, created_date,
               {TODAY} - created_date::date AS age_days, amount, quantity, item_code, request_id, row_count
          FROM core.it_interface_row
        UNION ALL
        SELECT 'AR|' || row_key, 'AR', batch_source_name, so_number,
               CASE WHEN error_message IS NOT NULL THEN 'ERROR' ELSE 'PENDING' END, NULL, error_message, trx_date,
               created_date, {TODAY} - created_date::date, amount, NULL, NULL, request_id, 1
          FROM core.ar_interface_line
         WHERE COALESCE(interface_status, '-') <> 'P'
    """,
}

EXT_UNIQUE_INDEX: dict[str, list[str]] = {
    "master_lookup": ["row_key"],
    "ap_invoice": ["invoice_id"],
    "po_shipment": ["line_location_id"],
    "po_approval_pending": ["row_key"],
    "ap_withholding": ["invoice_distribution_id"],
    "so_order_line": ["line_id"],
    "so_hold": ["order_hold_id"],
    "opm_item_cost": ["row_key"],
    "gl_budget_vs_actual": ["row_key"],
    "sa_interface_error": ["row_key"],
}

EXT_EXTRA_INDEXES: dict[str, list[str]] = {
    "master_lookup": ["type", "code"],
    "ap_invoice": ["invoice_num", "vendor_name", "next_due_date"],
    "po_shipment": ["po_number", "vendor_name"],
    "ap_withholding": ["period_name", "tax_name"],
    "so_order_line": ["order_number", "customer_name"],
    "so_hold": ["order_number"],
    "opm_item_cost": ["item_code", "period_start_date"],
    "gl_budget_vs_actual": ["period_name", "account_code", "dept_code"],
    "sa_interface_error": ["interface_name"],
}

# Views over core tables other jobs fill are refreshed by those jobs too.
EXT_MARTS_BY_JOB: dict[str, list[str]] = {
    "etl_mart_ext": ["po_approval_pending", "so_hold", "ap_withholding", "gl_budget_vs_actual", "sa_interface_error",
                     "master_lookup"],
}
EXT_EXTRA_REFRESH: dict[str, list[str]] = {
    "etl_mart_ap": ["ap_invoice", "master_lookup"],
    "etl_mart_po": ["po_shipment", "master_lookup"],
    "etl_mart_om": ["so_order_line", "master_lookup"],
    "etl_mart_ar": ["so_order_line", "master_lookup"],
    "etl_mart_item_cost": ["opm_item_cost"],
    "etl_mart_inventory": ["master_lookup"],
    "etl_mart_gl": ["gl_budget_vs_actual", "master_lookup"],
    "etl_mart_close": ["sa_interface_error"],
}
