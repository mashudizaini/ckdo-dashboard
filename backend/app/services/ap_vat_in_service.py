"""
AP VAT In Listing Report Service
─────────────────────────────────────────
Read-only report mirroring an existing Oracle EBS AP/GL SQL report (VAT
input per accounting period, GL account segment4 = '114207' — the VAT
In / input-tax clearing account) that Accounting & Tax already runs
manually via QP5/TOAD. Two legs, same shape as the source query:
  1. AP invoices posted through Payables ('Purchase Invoices' je_category)
  2. Uninvoiced receipts accrued through Cost Management ('Receiving')

On top of the original query this adds 3 "ADDITIONAL" columns the
finance team tracks by hand today (see
sumber/CUSTOM-ADDITIONAL COA DESCPT IN VAT MONTHLY REPORT.xlsx):
  - coa_full / coa_segment4: the GL account actually hit by the
    invoice's own ITEM distribution (AP_INVOICE_DISTRIBUTIONS_ALL.
    DIST_CODE_COMBINATION_ID) — present for both PO- and non-PO-matched
    invoices, since every distribution posts to some account.
  - coa_description: the account's business meaning, sourced from the
    matched Purchase Order line's ITEM_DESCRIPTION (not the GL account's
    own static description) — only populated when the distribution is
    PO-matched (AP_INVOICE_DISTRIBUTIONS_ALL.PO_DISTRIBUTION_ID ->
    PO_DISTRIBUTIONS_ALL -> PO_LINES_ALL), same sparsity as the finance
    team's own manual report.
Only the ITEM distribution is used (ROWNUM=1 per invoice) — invoices
with a single ITEM distribution (the overwhelming majority here) get an
unambiguous match; a rare multi-distribution invoice just gets one of
them, consistent with this being a "which account/PO was this for"
lookup column rather than a financial total.
"""
import asyncio

import structlog

from app.database import get_oracle_connection

logger = structlog.get_logger()

_SQL = """
SELECT inv.period,
       inv.journal_category,
       inv.posted_date,
       inv.faktur_pajak,
       inv.invoice_no,
       inv.inv_sequence_no,
       inv.description,
       inv.invoice_type,
       inv.npwp,
       inv.supplier_tax_invoice_date,
       inv.supplier_name,
       inv.invoice_currency_code,
       inv.exchange_rate,
       inv.je_amount je_amount,
       inv.coa_full,
       inv.coa_segment4,
       inv.coa_description,
       CASE
          WHEN inv.invoice_currency_code != 'IDR'
          THEN inv.line_total_amount * NVL(inv.exchange_rate, 0)
          ELSE inv.line_total_amount
       END AS line_total_amount,
       CASE
          WHEN inv.invoice_currency_code != 'IDR'
          THEN inv.tax_amount * NVL(inv.exchange_rate, 0)
          ELSE inv.tax_amount
       END AS tax_amount,
       CASE
          WHEN inv.invoice_currency_code != 'IDR'
          THEN inv.awt_amount * NVL(inv.exchange_rate, 0)
          ELSE inv.awt_amount
       END AS awt_amount,
       CASE
          WHEN inv.invoice_currency_code != 'IDR'
          THEN inv.invoice_total_amount * NVL(inv.exchange_rate, 0)
          ELSE inv.invoice_total_amount
       END AS invoice_total_amount
  FROM (
        SELECT gjl.period_name period,
               gjh.je_category journal_category,
               gjh.posted_date,
               aia.invoice_num invoice_no,
               TO_CHAR(aia.doc_sequence_value) inv_sequence_no,
               aia.description,
               aia.invoice_type_lookup_code invoice_type,
               aia.supplier_tax_invoice_number faktur_pajak,
               aia.supplier_tax_invoice_date,
               aps.vendor_name supplier_name,
               aps.vat_registration_num NPWP,
               aia.exchange_rate,
               aia.invoice_currency_code,
               SUM(NVL(xal.accounted_dr, 0) - NVL(xal.accounted_cr, 0)) AS je_amount,
               (SELECT SUM(NVL(aila.amount, 0))
                  FROM ap_invoice_lines_all aila
                 WHERE aila.invoice_id = aia.invoice_id
                       AND aila.line_type_lookup_code = 'ITEM') line_total_amount,
               NVL(aia.total_tax_amount, 0) tax_amount,
               NVL((SELECT SUM(NVL(aila.amount, 0))
                      FROM ap_invoice_lines_all aila
                     WHERE aila.invoice_id = aia.invoice_id
                           AND aila.line_type_lookup_code = 'AWT'), 0) awt_amount,
               (SELECT SUM(NVL(aila.amount, 0))
                  FROM ap_invoice_lines_all aila
                 WHERE aila.invoice_id = aia.invoice_id) invoice_total_amount,
               (SELECT gcc2.concatenated_segments
                  FROM ap_invoice_distributions_all aida2, gl_code_combinations_kfv gcc2
                 WHERE aida2.invoice_id = aia.invoice_id
                       AND aida2.line_type_lookup_code = 'ITEM'
                       AND aida2.dist_code_combination_id = gcc2.code_combination_id
                       AND ROWNUM = 1) coa_full,
               (SELECT gcc2.segment4
                  FROM ap_invoice_distributions_all aida2, gl_code_combinations_kfv gcc2
                 WHERE aida2.invoice_id = aia.invoice_id
                       AND aida2.line_type_lookup_code = 'ITEM'
                       AND aida2.dist_code_combination_id = gcc2.code_combination_id
                       AND ROWNUM = 1) coa_segment4,
               (SELECT pol.item_description
                  FROM ap_invoice_distributions_all aida2, po_distributions_all pda2, po_lines_all pol
                 WHERE aida2.invoice_id = aia.invoice_id
                       AND aida2.line_type_lookup_code = 'ITEM'
                       AND aida2.po_distribution_id = pda2.po_distribution_id
                       AND pda2.po_line_id = pol.po_line_id
                       AND ROWNUM = 1) coa_description
          FROM gl_je_headers gjh,
               gl_je_lines gjl,
               gl_import_references gir,
               xla_ae_lines xal,
               xla_ae_headers xah,
               xla.xla_transaction_entities xte,
               ap_invoices_all aia,
               ap_suppliers aps,
               gl_code_combinations_kfv gcc
         WHERE 1 = 1
               AND gjh.je_source = 'Payables'
               AND gjh.je_category = 'Purchase Invoices'
               AND gjh.je_header_id = gjl.je_header_id
               AND gjl.je_line_num = gir.je_line_num
               AND gjh.je_header_id = gir.je_header_id
               AND gir.gl_sl_link_id = xal.gl_sl_link_id
               AND gir.gl_sl_link_table = xal.gl_sl_link_table
               AND xal.ae_header_id = xah.ae_header_id
               AND xah.entity_id = xte.entity_id
               AND xte.source_id_int_1 = aia.invoice_id
               AND aia.vendor_id = aps.vendor_Id
               AND gcc.code_combination_id = xal.code_combination_id
               AND gcc.segment4 = '114207'
        GROUP BY gjl.period_name,
                 gjh.je_category,
                 gjh.posted_date,
                 aia.invoice_num,
                 aia.doc_sequence_value,
                 aia.invoice_type_lookup_code,
                 aia.supplier_tax_invoice_number,
                 aia.supplier_tax_invoice_date,
                 aps.vendor_name,
                 aps.vat_registration_num,
                 aia.invoice_amount,
                 aia.total_tax_amount,
                 aia.invoice_id,
                 aia.exchange_rate,
                 aia.invoice_currency_code,
                 aia.description
        UNION ALL
        SELECT gjl.period_name period,
               gjh.je_category journal_category,
               gjh.posted_date,
               rsh.receipt_num invoice_no,
               NULL inv_sequence_no,
               NULL description,
               'Receiving' invoice_type,
               NULL faktur_pajak,
               NULL supplier_tax_invoice_date,
               aps.vendor_name supplier_name,
               aps.vat_registration_num NPWP,
               rt.currency_conversion_rate exchange_rate,
               rt.currency_code,
               SUM(NVL(xal.accounted_dr, 0) - NVL(xal.accounted_cr, 0)) je_amount,
               SUM(NVL(rt.quantity, 0) * NVL(rt.po_unit_price, 0)) AS dpp,
               0 tax_amount,
               0 awt_amount,
               SUM(NVL(rt.quantity, 0) * NVL(rt.po_unit_price, 0)) AS invoice_total_amount,
               NULL coa_full,
               NULL coa_segment4,
               NULL coa_description
          FROM gl_je_headers gjh,
               gl_je_lines gjl,
               gl_import_references gir,
               xla_ae_lines xal,
               xla_ae_headers xah,
               xla.xla_transaction_entities xte,
               rcv_transactions rt,
               rcv_shipment_headers rsh,
               ap_suppliers aps,
               gl_code_combinations gcc
         WHERE 1 = 1
               AND gjh.je_source = 'Cost Management'
               AND gjh.je_category = 'Receiving'
               AND xal.accounting_class_code = 'CHARGE'
               AND gjh.je_header_id = gjl.je_header_id
               AND gjl.je_line_num = gir.je_line_num
               AND gjh.je_header_id = gir.je_header_id
               AND gir.gl_sl_link_id = xal.gl_sl_link_id
               AND gir.gl_sl_link_table = xal.gl_sl_link_table
               AND xal.ae_header_id = xah.ae_header_id
               AND xah.entity_id = xte.entity_id
               AND xte.source_id_int_1 = rt.transaction_id
               AND rt.vendor_id = aps.vendor_Id
               AND rt.shipment_header_id = rsh.shipment_header_id
               AND xal.code_combination_id = gcc.code_combination_id
               AND gcc.segment4 = '114207'
        GROUP BY gjl.period_name,
                 rt.currency_code,
                 gjh.je_category,
                 gjh.posted_date,
                 rsh.receipt_num,
                 aps.vendor_name,
                 aps.vat_registration_num,
                 rt.currency_conversion_rate
       ) inv
 WHERE inv.period = :p_period
   AND je_amount != 0
"""

# Display order for both the JSON table and the Excel export — matches
# sumber/CUSTOM-ADDITIONAL COA DESCPT IN VAT MONTHLY REPORT.xlsx's column
# layout (its two blank spacer columns are dropped; its typos "Descrpition"/
# "VAT Amout"/"Awt Amount" are corrected).
COLUMNS = [
    ("journal_category",          "Journal Category"),
    ("period",                    "Period"),
    ("posted_date",               "Posted Date"),
    ("faktur_pajak",              "Faktur Pajak"),
    ("invoice_no",                "Invoice No"),
    ("inv_sequence_no",           "Inv Sequence No"),
    ("invoice_type",              "Invoice Type"),
    ("description",               "Description"),
    ("npwp",                      "NPWP"),
    ("supplier_tax_invoice_date", "Supplier Tax Invoice Date"),
    ("coa_full",                  "COA"),
    ("coa_segment4",              "COA Segment 4"),
    ("coa_description",           "COA Segment 4 Description"),
    ("supplier_name",             "Supplier Name"),
    ("je_amount",                 "VAT Amount"),
    ("line_total_amount",         "Line Total Amount"),
    ("tax_amount",                "Tax Amount"),
    ("awt_amount",                "AWT Amount"),
    ("invoice_total_amount",      "Invoice Total Amount"),
]
_TOTAL_FIELDS = ("je_amount", "line_total_amount", "tax_amount", "awt_amount", "invoice_total_amount")


def _query(sql: str, params: dict) -> list[dict]:
    with get_oracle_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


async def get_ap_vat_in_listing(period: str) -> dict:
    """period: Oracle GL period name, e.g. 'AUG-26'."""
    try:
        rows = await asyncio.to_thread(_query, _SQL, {"p_period": period.upper()})
        clean = []
        for r in rows:
            row = {}
            for k, v in r.items():
                if hasattr(v, "__float__") and not isinstance(v, (int, float, str, type(None), bool)):
                    v = float(v)
                elif hasattr(v, "isoformat"):
                    v = v.isoformat()
                row[k] = v
            clean.append(row)

        totals = {f: sum((r.get(f) or 0) for r in clean) for f in _TOTAL_FIELDS}
        return {"success": True, "count": len(clean), "data": clean, "totals": totals}
    except Exception as e:
        logger.error("ap_vat_in_listing_error", period=period, error=str(e))
        return {"success": False, "error": str(e), "data": []}
