"""
Definitions of the built marts (blueprint sections 5 and 6): phase 1 (AP,
stock per lot, movement), phase 2 (PO, PR, inventory valuation), phase 3
(sales orders, shipping, invoiced sales, AR aging, receipts) and phase 4 (OPM
batches: status, yield, material usage by lot).

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
from app.services.ebs_mart.constants import (
    AP_COA_WHITELIST, AP_LEGACY_PAID_CUTOFF, SO_CMO_LINE_TYPE, SO_EXPORT_TYPE,
)

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

_PO_OUTSTANDING_QTY = (
    "(COALESCE(s.quantity, 0) - COALESCE(s.quantity_cancelled, 0) - COALESCE(s.quantity_received, 0))"
)
_DIST_ORDERED = "(COALESCE(d.quantity_ordered, 0) - COALESCE(d.quantity_cancelled, 0))"
_MATCH_TYPE = (
    "(CASE WHEN s.inspection_required = 'Y' THEN '4-way' "
    "WHEN s.receipt_required = 'Y' THEN '3-way' ELSE '2-way' END)"
)
# Same rule as mart.inv_onhand_lot: an administrator's classification wins,
# then the name heuristic, then GOOD.
_SUBINV_TYPE = "COALESCE(sc.subinventory_type, s.guessed_type, 'GOOD')"

# Business type exactly as the Dashboard's sales ETL derives it.
_BUSINESS_TYPE = (
    f"(CASE WHEN l.order_type = '{SO_EXPORT_TYPE}' THEN 'Export' "
    f"WHEN l.line_type = '{SO_CMO_LINE_TYPE}' THEN 'CMO' ELSE 'Local' END)"
)
_SO_OPEN_QTY = "GREATEST(COALESCE(l.ordered_qty, 0) - COALESCE(l.shipped_qty, 0), 0)"
_SO_DUE = "COALESCE(l.schedule_ship_date, l.promise_date, l.request_date)"

_BATCH_STATUS_DESC = (
    "CASE {c} WHEN 1 THEN 'Pending' WHEN 2 THEN 'WIP' WHEN 3 THEN 'Completed' WHEN 4 THEN 'Closed' "
    "WHEN -1 THEN 'Cancelled' ELSE 'Status ' || {c} END"
)

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
               COALESCE(h.invoice_num, i.invoice_num)                       AS invoice_num,
               COALESCE(h.invoice_type, i.invoice_type)                     AS invoice_type,
               COALESCE(h.invoice_date, i.invoice_date)                     AS invoice_date,
               COALESCE(h.vendor_num, i.vendor_num)                         AS vendor_num,
               COALESCE(h.vendor_name, i.vendor_name)                       AS vendor_name,
               COALESCE(h.invoice_currency_code, i.invoice_currency_code)   AS currency_code,
               COALESCE(h.invoice_amount, i.invoice_amount)                 AS invoice_amount_entered,
               COALESCE(h.invoice_amount_idr, i.invoice_amount_idr)         AS invoice_amount_idr,
               h.hold_code,
               h.hold_desc,
               h.hold_reason,
               h.hold_date,
               (CURRENT_DATE - h.hold_date::date)            AS days_on_hold,
               -- FALSE = the hold points at an invoice that no longer exists
               -- in AP_INVOICES_ALL (found on prod: two holds from 2021/2022).
               COALESCE(h.invoice_num, i.invoice_num) IS NOT NULL           AS invoice_found
          FROM core.fact_ap_hold h
          LEFT JOIN ({_AP_INVOICE_HEADER}) i ON i.invoice_id = h.invoice_id
         WHERE COALESCE(h.cancelled_date, i.cancelled_date) IS NULL
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

    # ── Phase 2 ─────────────────────────────────────────────────────────────

    # Blueprint 4.1: outstanding = quantity - cancelled - received, on the
    # shipment. Shipments closed for receiving are not outstanding even if
    # short-received: someone decided the rest will not come.
    "po_outstanding": f"""
        SELECT s.line_location_id,
               s.po_number,
               s.release_num,
               s.line_num,
               s.shipment_num,
               s.po_type,
               s.po_date,
               UPPER(TO_CHAR(s.po_date, 'MON-YY'))                     AS po_period_name,
               s.approved_date,
               s.vendor_num,
               s.vendor_name,
               s.vendor_site_code,
               s.buyer_name,
               s.item_code,
               s.item_desc,
               c.item_category,
               s.uom,
               s.currency_code,
               s.unit_price                                            AS unit_price_entered,
               s.quantity                                              AS qty_ordered,
               COALESCE(s.quantity_cancelled, 0)                       AS qty_cancelled,
               COALESCE(s.quantity_received, 0)                        AS qty_received,
               {_PO_OUTSTANDING_QTY}                                   AS qty_outstanding,
               {_PO_OUTSTANDING_QTY} * s.unit_price                    AS amount_outstanding_entered,
               {_PO_OUTSTANDING_QTY} * s.unit_price * COALESCE(s.rate_idr, 1) AS amount_outstanding_idr,
               s.need_by_date,
               s.promised_date,
               COALESCE(s.promised_date, s.need_by_date)               AS due_date,
               CURRENT_DATE - COALESCE(s.promised_date, s.need_by_date) AS days_late,
               CASE WHEN COALESCE(s.promised_date, s.need_by_date) IS NULL           THEN 'Tanpa tanggal'
                    WHEN COALESCE(s.promised_date, s.need_by_date) < CURRENT_DATE    THEN 'Terlambat'
                    WHEN COALESCE(s.promised_date, s.need_by_date) <= CURRENT_DATE + 7 THEN 'Jatuh tempo 7 hari'
                    ELSE 'Belum jatuh tempo' END                       AS delivery_status,
               COALESCE(s.closed_code, 'OPEN')                         AS closed_code
          FROM core.fact_po_shipment s
          LEFT JOIN core.dim_item c ON c.inventory_item_id = s.item_id
         WHERE s.po_status = 'APPROVED'
           AND COALESCE(s.cancel_flag, 'N') = 'N'
           AND COALESCE(s.line_cancel_flag, 'N') = 'N'
           AND COALESCE(s.closed_code, 'OPEN') NOT IN ('CLOSED', 'FINALLY CLOSED', 'CLOSED FOR RECEIVING')
           AND {_PO_OUTSTANDING_QTY} > 0
    """,

    # Blueprint 4.1: matching is on po_distribution_id. quantity_delivered
    # is what reached the destination (received and delivered); quantity_billed
    # is what AP matched. The match type comes from the shipment's receipt /
    # inspection flags: 2-way needs no receipt, so billed > received is
    # normal there and is not reported as a problem.
    "po_receipt_vs_invoice": f"""
        SELECT d.po_distribution_id,
               s.line_location_id,
               s.po_number,
               s.release_num,
               s.line_num,
               s.shipment_num,
               d.distribution_num,
               s.po_date,
               UPPER(TO_CHAR(s.po_date, 'MON-YY'))                     AS po_period_name,
               s.vendor_num,
               s.vendor_name,
               s.item_code,
               s.item_desc,
               c.item_category,
               s.uom,
               s.currency_code,
               s.unit_price                                            AS unit_price_entered,
               {_DIST_ORDERED}                                         AS qty_ordered,
               COALESCE(d.quantity_delivered, 0)                       AS qty_received,
               COALESCE(d.quantity_billed, 0)                          AS qty_billed,
               GREATEST({_DIST_ORDERED} - COALESCE(d.quantity_delivered, 0), 0) AS qty_not_received,
               GREATEST(COALESCE(d.quantity_delivered, 0) - COALESCE(d.quantity_billed, 0), 0) AS qty_received_not_billed,
               GREATEST(COALESCE(d.quantity_billed, 0) - COALESCE(d.quantity_delivered, 0), 0) AS qty_billed_not_received,
               GREATEST(COALESCE(d.quantity_delivered, 0) - COALESCE(d.quantity_billed, 0), 0)
                   * s.unit_price * COALESCE(s.rate_idr, 1)            AS amount_received_not_billed_idr,
               COALESCE(d.amount_billed, 0)                            AS amount_billed_entered,
               COALESCE(d.amount_billed, 0) * COALESCE(s.rate_idr, 1)  AS amount_billed_idr,
               {_MATCH_TYPE}                                           AS match_type,
               CASE WHEN {_DIST_ORDERED} <= 0 THEN 'Dibatalkan'
                    WHEN COALESCE(d.quantity_delivered, 0) = 0 AND COALESCE(d.quantity_billed, 0) = 0
                         THEN 'Belum diterima, belum ditagih'
                    WHEN COALESCE(d.quantity_billed, 0) > COALESCE(d.quantity_delivered, 0)
                         THEN CASE WHEN {_MATCH_TYPE} = '2-way' THEN 'Ditagih (2-way, tanpa penerimaan)'
                                   ELSE 'Ditagih melebihi penerimaan' END
                    WHEN COALESCE(d.quantity_delivered, 0) > COALESCE(d.quantity_billed, 0)
                         THEN 'Diterima, belum ditagih penuh'
                    WHEN COALESCE(d.quantity_delivered, 0) >= {_DIST_ORDERED}
                         THEN 'Lengkap (diterima & ditagih)'
                    ELSE 'Sebagian (diterima = ditagih)' END            AS match_status,
               d.invoice_count,
               d.last_invoice_num,
               d.last_invoice_date,
               d.charge_account,
               COALESCE(s.closed_code, 'OPEN')                         AS closed_code
          FROM core.fact_po_distribution d
          JOIN core.fact_po_shipment s ON s.line_location_id = d.line_location_id
          LEFT JOIN core.dim_item c ON c.inventory_item_id = s.item_id
         WHERE s.po_status = 'APPROVED'
           AND COALESCE(s.cancel_flag, 'N') = 'N'
           AND COALESCE(s.line_cancel_flag, 'N') = 'N'
    """,

    "pr_pending": """
        SELECT p.requisition_line_id,
               p.pr_number,
               p.line_num,
               p.pr_type,
               p.pr_date,
               p.approved_date,
               CURRENT_DATE - COALESCE(p.approved_date, p.pr_date)     AS days_waiting,
               p.preparer,
               p.requester,
               p.pr_description,
               p.item_code,
               p.item_desc,
               c.item_category,
               p.uom,
               p.quantity,
               p.currency_code,
               COALESCE(p.currency_unit_price, p.unit_price)           AS unit_price_entered,
               p.quantity * COALESCE(p.currency_unit_price, p.unit_price) AS amount_entered,
               p.quantity * p.unit_price                               AS amount_idr,
               p.need_by_date,
               CASE WHEN p.need_by_date < CURRENT_DATE THEN TRUE ELSE FALSE END AS need_by_passed,
               p.suggested_vendor
          FROM core.snap_pr_pending p
          LEFT JOIN core.dim_item c ON c.inventory_item_id = p.item_id
    """,

    # Blueprint 4.3 trap: org 121 is a process (OPM) org, so value comes from
    # CM_CMPT_DTL under the PMAC cost method, never CST_ITEM_COSTS. Quantity
    # is today's on-hand (core.snap_onhand_lot), priced at each item's most
    # recent costing period — a current valuation, not a period-close one;
    # reconcile against the OPM Inventory Valuation Report of that period.
    # Built on core.*, not on mart.inv_onhand_lot, so the refresh order of
    # the two views never matters.
    "inv_valuation": f"""
        WITH latest_cost AS (
            SELECT DISTINCT ON (inventory_item_id)
                   inventory_item_id, period_code, period_end_date, period_status, unit_cost, cost_components
              FROM core.fact_item_cost
             ORDER BY inventory_item_id, period_end_date DESC
        ), stock AS (
            SELECT o.inventory_item_id,
                   MAX(o.item_code)                                     AS item_code,
                   MAX(o.item_desc)                                     AS item_desc,
                   MAX(o.uom)                                           AS uom,
                   {_SUBINV_TYPE}                                       AS subinventory_type,
                   SUM(o.onhand_qty)                                    AS onhand_qty,
                   COUNT(*)                                             AS lot_rows
              FROM core.snap_onhand_lot o
              LEFT JOIN core.dim_subinventory s    ON s.subinventory_code = o.subinventory_code
              LEFT JOIN meta.subinventory_class sc ON sc.subinventory_code = o.subinventory_code
             WHERE o.onhand_qty <> 0
             GROUP BY o.inventory_item_id, {_SUBINV_TYPE}
        )
        SELECT MD5(st.inventory_item_id || '|' || st.subinventory_type) AS row_key,
               st.item_code,
               st.item_desc,
               c.item_category,
               st.uom,
               st.subinventory_type,
               st.onhand_qty,
               lc.unit_cost                                            AS unit_cost_idr,
               st.onhand_qty * lc.unit_cost                            AS value_idr,
               lc.period_code                                          AS cost_period_code,
               lc.period_end_date                                      AS cost_period_end_date,
               lc.period_status                                        AS cost_period_status,
               lc.cost_components,
               lc.unit_cost IS NOT NULL                                AS has_cost
          FROM stock st
          LEFT JOIN latest_cost lc ON lc.inventory_item_id = st.inventory_item_id
          LEFT JOIN core.dim_item c ON c.inventory_item_id = st.inventory_item_id
    """,

    # ── Phase 3 ─────────────────────────────────────────────────────────────

    # Blueprint 4.2: open = open_flag 'Y' and cancelled_flag 'N'. qty_to_ship
    # is what has not left the warehouse yet; a shipped line stays open until
    # it is invoiced and closed, so it can be in the backlog with nothing
    # left to ship (line_status tells which).
    "so_backlog": f"""
        SELECT l.line_id,
               l.order_number,
               l.line_number,
               l.shipment_number,
               l.order_type,
               {_BUSINESS_TYPE}                                       AS business_type,
               l.ordered_date,
               UPPER(TO_CHAR(l.ordered_date, 'MON-YY'))               AS ordered_period_name,
               l.header_status,
               l.line_status,
               l.customer_num,
               l.customer_name,
               l.item_code,
               l.item_desc,
               c.item_category,
               l.uom,
               l.ordered_qty,
               COALESCE(l.shipped_qty, 0)                             AS shipped_qty,
               COALESCE(l.invoiced_qty, 0)                            AS invoiced_qty,
               {_SO_OPEN_QTY}                                         AS qty_to_ship,
               l.currency_code,
               l.unit_selling_price                                   AS unit_price_entered,
               {_SO_OPEN_QTY} * l.unit_selling_price                  AS amount_to_ship_entered,
               {_SO_OPEN_QTY} * l.unit_selling_price * COALESCE(l.rate_idr, 1) AS amount_to_ship_idr,
               l.ordered_qty * l.unit_selling_price * COALESCE(l.rate_idr, 1)  AS amount_ordered_idr,
               l.request_date,
               l.schedule_ship_date,
               l.promise_date,
               {_SO_DUE}                                              AS due_date,
               CASE WHEN {_SO_OPEN_QTY} > 0 THEN CURRENT_DATE - {_SO_DUE} END AS days_late,
               CASE WHEN {_SO_OPEN_QTY} = 0                     THEN 'Sudah dikirim, belum ditutup'
                    WHEN {_SO_DUE} IS NULL                      THEN 'Tanpa tanggal'
                    WHEN {_SO_DUE} < CURRENT_DATE               THEN 'Terlambat'
                    WHEN {_SO_DUE} <= CURRENT_DATE + 7          THEN 'Jadwal kirim 7 hari'
                    ELSE 'Belum jadwal kirim' END                     AS delivery_status
          FROM core.fact_so_line l
          LEFT JOIN core.dim_item c ON c.inventory_item_id = l.item_id
         WHERE COALESCE(l.open_flag, 'N') = 'Y'
           AND COALESCE(l.cancelled_flag, 'N') = 'N'
    """,

    # Blueprint 4.2: released_status C shipped, Y staged, B backordered,
    # R ready to release; plus S released to warehouse, N not ready,
    # I interfaced (shipped and passed on), D cancelled. Shipped counts both
    # C and I. The line's status is its least advanced delivery detail.
    "so_shipment_status": f"""
        SELECT l.line_id,
               l.order_number,
               l.line_number,
               l.shipment_number,
               {_BUSINESS_TYPE}                                       AS business_type,
               l.ordered_date,
               l.customer_num,
               l.customer_name,
               l.item_code,
               l.item_desc,
               l.uom,
               l.ordered_qty,
               l.line_status,
               l.schedule_ship_date,
               SUM(d.requested_qty) FILTER (WHERE d.released_status IN ('C', 'I')) AS qty_shipped,
               SUM(d.requested_qty) FILTER (WHERE d.released_status = 'Y')        AS qty_staged,
               SUM(d.requested_qty) FILTER (WHERE d.released_status = 'S')        AS qty_released_to_warehouse,
               SUM(d.requested_qty) FILTER (WHERE d.released_status = 'R')        AS qty_ready_to_release,
               SUM(d.requested_qty) FILTER (WHERE d.released_status = 'B')        AS qty_backordered,
               SUM(d.requested_qty) FILTER (WHERE d.released_status = 'N')        AS qty_not_ready,
               CASE WHEN BOOL_OR(d.released_status = 'B') THEN 'Backorder'
                    WHEN BOOL_OR(d.released_status IN ('N', 'R')) THEN 'Belum dirilis ke gudang'
                    WHEN BOOL_OR(d.released_status = 'S') THEN 'Dirilis ke gudang (picking)'
                    WHEN BOOL_OR(d.released_status = 'Y') THEN 'Staged (siap kirim)'
                    WHEN BOOL_AND(d.released_status IN ('C', 'I', 'D')) THEN 'Terkirim'
                    ELSE 'Lainnya' END                                AS shipment_status,
               STRING_AGG(DISTINCT d.delivery_name, ', ')             AS delivery_names,
               MAX(d.confirm_date)                                    AS last_ship_confirm_date,
               STRING_AGG(DISTINCT d.lot_number, ', ')                AS lot_numbers
          FROM core.fact_so_line l
          JOIN core.fact_so_delivery_detail d ON d.source_line_id = l.line_id
         WHERE COALESCE(l.cancelled_flag, 'N') = 'N'
           AND d.released_status <> 'D'
         GROUP BY l.line_id, l.order_number, l.line_number, l.shipment_number, l.order_type, l.line_type,
                  l.ordered_date, l.customer_num, l.customer_name, l.item_code, l.item_desc, l.uom,
                  l.ordered_qty, l.line_status, l.schedule_ship_date
    """,

    # Invoiced sales (blueprint: RA_CUSTOMER_TRX_LINES_ALL), by GL month of
    # the invoice. Credit memos are negative lines of the same shape, so a
    # return reduces the month it is credited in. Business type comes from
    # the order line the invoice line was raised from; lines without one
    # (manual invoices) are "Non-SO".
    "sales_by_customer_item_month": """
        SELECT MD5(CONCAT_WS('|', a.customer_num, a.item_code, a.period_start_date, a.currency_code, a.business_type)) AS row_key,
               a.*
          FROM (
            SELECT i.customer_num,
                   MAX(i.customer_name)                                AS customer_name,
                   COALESCE(i.item_code, '(tanpa item)')               AS item_code,
                   MAX(i.item_desc)                                    AS item_desc,
                   MAX(c.item_category)                                AS item_category,
                   MAX(i.uom)                                          AS uom,
                   DATE_TRUNC('month', i.gl_date)::date                AS period_start_date,
                   UPPER(TO_CHAR(i.gl_date, 'MON-YY'))                 AS period_name,
                   EXTRACT(YEAR FROM i.gl_date)::int                   AS fiscal_year,
                   i.currency_code,
                   CASE WHEN s.line_id IS NULL THEN 'Non-SO'
                        WHEN s.order_type = '""" + SO_EXPORT_TYPE + """' THEN 'Export'
                        WHEN s.line_type = '""" + SO_CMO_LINE_TYPE + """' THEN 'CMO'
                        ELSE 'Local' END                               AS business_type,
                   SUM(i.quantity)                                     AS quantity,
                   SUM(i.extended_amount)                              AS amount_entered,
                   SUM(i.extended_amount * COALESCE(i.exchange_rate, 1)) AS amount_idr,
                   SUM(i.extended_amount * COALESCE(i.exchange_rate, 1)) FILTER (WHERE i.class = 'CM') AS credit_memo_idr,
                   COUNT(DISTINCT i.customer_trx_id)                   AS invoice_count
              FROM core.fact_ar_invoice_line i
              LEFT JOIN core.fact_so_line s ON s.line_id = i.so_line_id
              LEFT JOIN core.dim_item c     ON c.inventory_item_id = i.item_id
             WHERE i.gl_date IS NOT NULL
             GROUP BY i.customer_num, COALESCE(i.item_code, '(tanpa item)'), DATE_TRUNC('month', i.gl_date)::date,
                      UPPER(TO_CHAR(i.gl_date, 'MON-YY')), EXTRACT(YEAR FROM i.gl_date)::int, i.currency_code,
                      CASE WHEN s.line_id IS NULL THEN 'Non-SO'
                           WHEN s.order_type = '""" + SO_EXPORT_TYPE + """' THEN 'Export'
                           WHEN s.line_type = '""" + SO_CMO_LINE_TYPE + """' THEN 'CMO'
                           ELSE 'Local' END
          ) a
    """,

    # Same population and conversion as the Dashboard's AR Outstanding report
    # (accounting_service.get_ar_outstanding): classes INV/DM/CM, Oracle
    # status OP, invoices after the legacy cutoff, and IDR at the LATEST
    # Corporate rate rather than the invoice's own rate. Credit memos stay
    # in (negative) so totals net them exactly as the report's summary does.
    "ar_aging": f"""
        SELECT s.payment_schedule_id,
               s.customer_trx_id,
               s.customer_num,
               s.customer_name,
               s.trx_number,
               s.trx_type,
               s.class,
               s.trx_date,
               s.gl_date,
               UPPER(TO_CHAR(s.gl_date, 'MON-YY'))                 AS gl_period_name,
               s.due_date,
               s.so_number,
               s.currency_code,
               s.amount_due_original                               AS amount_original_entered,
               s.amount_due_remaining                              AS amount_remaining_entered,
               s.amount_due_remaining * CASE WHEN s.currency_code = 'IDR' THEN 1 ELSE COALESCE(fx.rate, 1) END
                                                                   AS amount_remaining_idr,
               s.amount_due_remaining * COALESCE(s.exchange_rate, 1) AS amount_remaining_idr_invoice_rate,
               CASE WHEN s.currency_code = 'IDR' THEN 1 ELSE fx.rate END AS fx_rate_used,
               fx.rate_date                                        AS fx_rate_date,
               (CURRENT_DATE - s.due_date)                         AS days_overdue,
               CASE WHEN s.due_date >= CURRENT_DATE      THEN 'Current'
                    WHEN CURRENT_DATE - s.due_date <= 30 THEN '1-30'
                    WHEN CURRENT_DATE - s.due_date <= 60 THEN '31-60'
                    WHEN CURRENT_DATE - s.due_date <= 90 THEN '61-90'
                    ELSE '>90' END                                 AS aging_bucket,
               CASE WHEN s.due_date >= CURRENT_DATE      THEN 0
                    WHEN CURRENT_DATE - s.due_date <= 30 THEN 1
                    WHEN CURRENT_DATE - s.due_date <= 60 THEN 2
                    WHEN CURRENT_DATE - s.due_date <= 90 THEN 3
                    ELSE 4 END                                     AS aging_bucket_order
          FROM core.fact_ar_schedule s
          LEFT JOIN core.dim_fx_rate fx ON fx.currency_code = s.currency_code
         WHERE s.status = 'OP'
           AND s.class IN ('INV', 'DM', 'CM')
           AND s.trx_date > DATE '{AP_LEGACY_PAID_CUTOFF}'
    """,

    # One row per receipt, application status and applied invoice. Applied
    # (APP) amounts net reversals because both legs are rows; UNAPP rows are
    # likewise recorded and reversed as money is applied, so their sum is
    # what is still unapplied. IDR: acctd_amount_applied_from, the receipt's
    # own accounted amount.
    "ar_receipt": """
        WITH inv AS (
            SELECT DISTINCT ON (customer_trx_id) customer_trx_id, trx_number, trx_date, due_date
              FROM core.fact_ar_schedule
             ORDER BY customer_trx_id, payment_schedule_id
        )
        SELECT MD5(CONCAT_WS('|', r.cash_receipt_id, a.status, COALESCE(a.applied_customer_trx_id, 0))) AS row_key,
               r.cash_receipt_id,
               r.receipt_number,
               r.receipt_date,
               UPPER(TO_CHAR(r.receipt_date, 'MON-YY'))            AS receipt_period_name,
               DATE_TRUNC('month', r.receipt_date)::date           AS receipt_period_start_date,
               r.deposit_date,
               r.receipt_type,
               r.status                                            AS receipt_status,
               r.reversal_date,
               r.reversal_date IS NOT NULL                         AS is_reversed,
               r.customer_num,
               r.customer_name,
               r.receipt_method,
               r.currency_code,
               r.amount                                            AS receipt_amount_entered,
               r.amount * COALESCE(r.exchange_rate, 1)             AS receipt_amount_idr,
               a.status                                            AS application_status,
               CASE a.status WHEN 'APP'   THEN 'Diaplikasikan ke invoice'
                             WHEN 'UNAPP' THEN 'Belum diaplikasikan'
                             WHEN 'ACC'   THEN 'On account'
                             WHEN 'UNID'  THEN 'Tidak teridentifikasi'
                             ELSE 'Lainnya (' || a.status || ')' END AS application_status_desc,
               inv.trx_number                                      AS applied_invoice_num,
               inv.trx_date                                        AS applied_invoice_date,
               inv.due_date                                        AS applied_invoice_due_date,
               SUM(a.amount_applied)                               AS amount_entered,
               SUM(a.acctd_amount_applied)                         AS amount_idr,
               MAX(a.gl_date)                                      AS last_application_gl_date
          FROM core.fact_ar_receipt r
          JOIN core.fact_ar_application a ON a.cash_receipt_id = r.cash_receipt_id
          LEFT JOIN inv ON inv.customer_trx_id = a.applied_customer_trx_id
         GROUP BY r.cash_receipt_id, r.receipt_number, r.receipt_date, r.deposit_date, r.receipt_type, r.status,
                  r.reversal_date, r.customer_num, r.customer_name, r.receipt_method, r.currency_code, r.amount,
                  r.exchange_rate, a.status, a.applied_customer_trx_id, inv.trx_number, inv.trx_date, inv.due_date
        HAVING SUM(a.amount_applied) <> 0
    """,

    # ── Phase 4 ─────────────────────────────────────────────────────────────

    # One row per batch. Product = the batch's product lines (line_type 1),
    # first line's item as the batch product and all product lines' qty
    # summed — the Dashboard's Production ETL does the same. Yield and "on
    # time" follow the Production dashboard: yield only for Completed/Closed,
    # on time when actual completion <= planned completion.
    "batch_status": f"""
        WITH b AS (
            SELECT batch_id,
                   MAX(batch_no)                         AS batch_no,
                   MAX(batch_status)                     AS batch_status,
                   MAX(formula_no)                       AS formula_no,
                   MAX(formula_vers)                     AS formula_vers,
                   MAX(plan_start_date)                  AS plan_start_date,
                   MAX(actual_start_date)                AS actual_start_date,
                   MAX(due_date)                         AS due_date,
                   MAX(plan_cmplt_date)                  AS plan_cmplt_date,
                   MAX(actual_cmplt_date)                AS actual_cmplt_date,
                   MAX(batch_close_date)                 AS batch_close_date,
                   (ARRAY_AGG(item_code ORDER BY line_no) FILTER (WHERE line_type = 1))[1] AS product_code,
                   (ARRAY_AGG(item_desc ORDER BY line_no) FILTER (WHERE line_type = 1))[1] AS product_desc,
                   (ARRAY_AGG(COALESCE(uom, primary_uom) ORDER BY line_no) FILTER (WHERE line_type = 1))[1] AS product_uom,
                   SUM(plan_qty)   FILTER (WHERE line_type = 1) AS product_plan_qty,
                   SUM(actual_qty) FILTER (WHERE line_type = 1) AS product_actual_qty,
                   COUNT(*) FILTER (WHERE line_type = -1)       AS ingredient_lines
              FROM core.fact_batch_material
             GROUP BY batch_id
        )
        SELECT b.batch_id,
               b.batch_no,
               b.batch_status,
               {_BATCH_STATUS_DESC.format(c='b.batch_status')}      AS batch_status_desc,
               b.formula_no || COALESCE(' v' || b.formula_vers, '')  AS formula,
               b.product_code,
               b.product_desc,
               b.product_uom,
               b.product_plan_qty,
               b.product_actual_qty,
               CASE WHEN b.batch_status IN (3, 4) AND b.product_plan_qty > 0
                    THEN ROUND(100.0 * b.product_actual_qty / b.product_plan_qty, 1) END AS yield_pct,
               b.plan_start_date,
               b.actual_start_date,
               b.due_date,
               b.plan_cmplt_date,
               b.actual_cmplt_date,
               b.batch_close_date,
               UPPER(TO_CHAR(b.plan_start_date, 'MON-YY'))          AS plan_period_name,
               DATE_TRUNC('month', b.plan_start_date)::date         AS plan_period_start_date,
               ROUND((EXTRACT(EPOCH FROM (b.actual_start_date - b.plan_start_date)) / 86400.0)::numeric, 1)
                                                                    AS start_delay_days,
               ROUND((EXTRACT(EPOCH FROM (COALESCE(b.actual_cmplt_date,
                          CASE WHEN b.batch_status IN (1, 2) THEN now()::timestamp END) - b.plan_cmplt_date)) / 86400.0)::numeric, 1)
                                                                    AS completion_delay_days,
               (b.actual_cmplt_date IS NOT NULL AND b.plan_cmplt_date IS NOT NULL
                AND b.actual_cmplt_date <= b.plan_cmplt_date)       AS on_time,
               CASE WHEN b.batch_status = -1 THEN 'Dibatalkan'
                    WHEN b.actual_cmplt_date IS NOT NULL AND b.plan_cmplt_date IS NULL THEN 'Selesai (tanpa rencana)'
                    WHEN b.actual_cmplt_date IS NOT NULL AND b.actual_cmplt_date <= b.plan_cmplt_date THEN 'Selesai tepat waktu'
                    WHEN b.actual_cmplt_date IS NOT NULL THEN 'Selesai terlambat'
                    WHEN b.batch_status IN (1, 2) AND b.plan_cmplt_date < now()::timestamp THEN 'Belum selesai, lewat rencana'
                    WHEN b.batch_status IN (1, 2) THEN 'Berjalan sesuai rencana'
                    ELSE 'Lainnya' END                              AS schedule_status,
               ROUND((EXTRACT(EPOCH FROM (b.actual_cmplt_date - b.actual_start_date)) / 86400.0)::numeric, 1)
                                                                    AS cycle_time_days,
               b.ingredient_lines
          FROM b
    """,

    "batch_yield_variance": f"""
        SELECT m.material_detail_id,
               m.batch_id,
               m.batch_no,
               m.batch_status,
               {_BATCH_STATUS_DESC.format(c='m.batch_status')}      AS batch_status_desc,
               m.line_type,
               CASE m.line_type WHEN 1 THEN 'Produk' WHEN 2 THEN 'By-product' END AS line_type_desc,
               m.item_code,
               m.item_desc,
               COALESCE(m.uom, m.primary_uom)                       AS uom,
               m.plan_qty,
               m.original_qty                                       AS standard_qty,
               m.actual_qty,
               m.actual_qty - m.plan_qty                            AS variance_qty,
               CASE WHEN m.plan_qty > 0 THEN ROUND(100.0 * m.actual_qty / m.plan_qty, 1) END AS yield_pct,
               m.plan_start_date,
               m.actual_cmplt_date,
               UPPER(TO_CHAR(m.plan_start_date, 'MON-YY'))          AS plan_period_name,
               DATE_TRUNC('month', m.plan_start_date)::date         AS plan_period_start_date
          FROM core.fact_batch_material m
         WHERE m.line_type IN (1, 2)
    """,

    # Ingredient lines × lots actually issued. Line-level quantities are in
    # the line's uom and repeat on every lot row of the line; lot quantities
    # are in the item's primary uom (lot_uom) and are what was consumed —
    # issues are negative in Oracle, so the sign is flipped. A line with no
    # issue transaction yet has one row with no lot.
    "batch_material_usage": f"""
        SELECT m.material_detail_id || '|' || COALESCE(l.lot_number, '(belum ada transaksi)') AS row_key,
               m.material_detail_id,
               m.batch_id,
               m.batch_no,
               m.batch_status,
               {_BATCH_STATUS_DESC.format(c='m.batch_status')}      AS batch_status_desc,
               (SELECT p.item_code FROM core.fact_batch_material p
                 WHERE p.batch_id = m.batch_id AND p.line_type = 1 ORDER BY p.line_no LIMIT 1) AS product_code,
               m.item_code,
               m.item_desc,
               c.item_category,
               COALESCE(m.uom, m.primary_uom)                       AS uom,
               m.original_qty                                       AS line_standard_qty,
               m.plan_qty                                           AS line_plan_qty,
               m.actual_qty                                         AS line_actual_qty,
               CASE WHEN m.original_qty > 0 AND m.batch_status IN (3, 4)
                    THEN ROUND(100.0 * (m.actual_qty - m.original_qty) / m.original_qty, 1) END AS line_variance_pct,
               l.lot_number,
               -l.qty                                               AS lot_qty_consumed,
               m.primary_uom                                        AS lot_uom,
               l.last_txn_date,
               m.plan_start_date
          FROM core.fact_batch_material m
          LEFT JOIN core.fact_batch_lot l ON l.material_detail_id = m.material_detail_id
          LEFT JOIN core.dim_item c       ON c.inventory_item_id = m.item_id
         WHERE m.line_type = -1
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
    "po_outstanding": ["line_location_id"],
    "po_receipt_vs_invoice": ["po_distribution_id"],
    "pr_pending": ["requisition_line_id"],
    "inv_valuation": ["row_key"],
    "so_backlog": ["line_id"],
    "so_shipment_status": ["line_id"],
    "sales_by_customer_item_month": ["row_key"],
    "ar_aging": ["payment_schedule_id"],
    "ar_receipt": ["row_key"],
    "batch_status": ["batch_id"],
    "batch_yield_variance": ["material_detail_id"],
    "batch_material_usage": ["row_key"],
}

MART_EXTRA_INDEXES: dict[str, list[str]] = {
    "ap_open_invoice": ["vendor_name", "due_date", "aging_bucket"],
    "ap_payment_history": ["vendor_name", "payment_date", "invoice_num"],
    "ap_invoice_hold": ["vendor_name"],
    "inv_onhand_lot": ["item_code", "expiration_date", "subinventory_code"],
    "inv_movement_daily": ["item_code", "txn_date"],
    "po_outstanding": ["vendor_name", "po_number", "item_code", "due_date"],
    "po_receipt_vs_invoice": ["po_number", "vendor_name", "match_status"],
    "pr_pending": ["pr_number", "item_code"],
    "inv_valuation": ["item_code"],
    "so_backlog": ["customer_name", "order_number", "item_code"],
    "so_shipment_status": ["order_number", "customer_name"],
    "sales_by_customer_item_month": ["customer_name", "item_code", "period_start_date"],
    "ar_aging": ["customer_name", "due_date", "aging_bucket"],
    "ar_receipt": ["customer_name", "receipt_date", "receipt_number"],
    "batch_status": ["batch_no", "product_code", "plan_start_date"],
    "batch_yield_variance": ["batch_no", "item_code"],
    "batch_material_usage": ["batch_no", "item_code", "lot_number"],
}

# Which marts to refresh after which job succeeds.
MARTS_BY_JOB: dict[str, list[str]] = {
    "etl_mart_ap": ["ap_open_invoice", "ap_payment_history", "ap_invoice_hold"],
    "etl_mart_inventory": ["inv_onhand_lot", "inv_valuation"],
    "etl_inventory_txn": ["inv_movement_daily"],
    "etl_mart_po": ["po_outstanding", "po_receipt_vs_invoice", "pr_pending"],
    "etl_mart_item_cost": ["inv_valuation"],
    "etl_mart_om": ["so_backlog", "so_shipment_status", "sales_by_customer_item_month"],
    "etl_mart_ar": ["ar_aging", "ar_receipt", "sales_by_customer_item_month"],
    "etl_mart_opm": ["batch_status", "batch_yield_variance", "batch_material_usage"],
}
