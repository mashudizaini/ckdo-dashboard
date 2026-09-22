"""
AP Withholding Tax Listing Report Service
─────────────────────────────────────────
Read-only report mirroring an existing Oracle EBS AP/GL SQL report
(withholding tax per accounting period, GL account segment4 IN
213111..213117 — the WHT payable accounts) that Accounting & Tax
already runs manually via QP5/TOAD. Unlike the VAT In report, a single
AP invoice can carry the WHT for a *different* originating purchase
invoice (Oracle records the AWT liability as its own separate invoice,
"AWT" type, linked back to the original via
AP_INVOICE_DISTRIBUTIONS_ALL.AWT_INVOICE_ID) — the source query already
resolves this via its `inv2` sub-select and a CASE that prefers
inv2.invoice_id (the original invoice) over aia.invoice_id (the AWT
wrapper invoice) wherever a match exists.

On top of the original query this adds 3 "ADDITIONAL" columns the
finance team tracks by hand today (see
sumber/Witholding Tax Listing - Output.xlsx):
  - coa_full / coa_segment4: the GL account hit by the *originating*
    invoice's own ITEM distribution — using the same "effective invoice
    id" CASE the source query already applies for line_total_amount/
    awt_amount, so the lookup follows the AWT->original link correctly
    (verified live: querying the AWT wrapper invoice's own id directly,
    without this CASE, returns the wrong/unrelated account). The 114207
    VAT-input account is explicitly excluded so it never gets mistaken
    for "the" business account when an invoice has both a VAT line and
    an expense/asset line.
  - coa_description: the matched Purchase Order line's ITEM_DESCRIPTION
    (AP_INVOICE_DISTRIBUTIONS_ALL.PO_DISTRIBUTION_ID -> PO_DISTRIBUTIONS_ALL
    -> PO_LINES_ALL) — only populated when that distribution is PO-matched.
Only ROWNUM=1 per invoice is used (no secondary ordering — an earlier
attempt at "pick the largest by amount" via a nested ORDER BY broke the
correlation to the outer query and returned the same wrong account for
every row; simple ROWNUM=1 correlates correctly). A rare multi-distribution
invoice just gets one of its non-VAT ITEM accounts, consistent with this
being a "which account/PO was this for" lookup rather than a financial
total — the report's own Gross/WHT amount totals are unaffected either way.
"""
import asyncio

import structlog

from app.database import get_oracle_connection

logger = structlog.get_logger()

_SQL = """
  SELECT ROW_NUMBER () OVER (ORDER BY invoice_no) AS nomor,
         inv.invoice_id,
         inv.period,
         inv.journal_category,
         inv.posted_date,
         inv.faktur_pajak,
         inv.supplier_tax_invoice_date,
         inv.invoice_date,
         inv.inv_sequence_no,
         inv.description,
         inv.invoice_type,
         inv.npwp,
         inv.supplier_name,
         inv.invoice_currency_code,
         inv.exchange_rate,
         inv.awt_group_name,
         inv.tax_rate,
         inv.invoice_no,
         inv.coa_full,
         inv.coa_segment4,
         inv.coa_description,
         inv.line_total_amount,
         inv.tax_amount,
         CASE
            WHEN NVL (inv.awt_amount, 0) = 0 THEN inv.line_total_amount
            ELSE inv.awt_amount * -1
         END
            AS awt_amount,
         inv.payment_date
    FROM (  SELECT gjl.period_name period,
                   aia.invoice_id,
                   gjh.je_category journal_category,
                   gjh.posted_date,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_num
                      ELSE aia.invoice_num
                   END
                      AS invoice_no,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_date
                      ELSE aia.invoice_date
                   END
                      invoice_date,
                   TO_CHAR (aia.doc_sequence_value) inv_sequence_no,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.description
                      ELSE aia.description
                   END
                      AS description,
                   aia.invoice_type_lookup_code invoice_type,
                   inv2.supplier_tax_invoice_number faktur_pajak,
                   inv2.supplier_tax_invoice_date,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.vendor_name
                      ELSE aps.vendor_name
                   END
                      AS supplier_name,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.npwp
                      ELSE aps.vat_registration_num
                   END
                      AS NPWP,
                   aia.exchange_rate,
                   aia.invoice_currency_code,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL
                      THEN
                         inv2.tax_rate
                      ELSE
                         (SELECT aatra.tax_rate
                            FROM ap_invoice_distributions_all aida,
                                 ap_awt_tax_rates_all aatra
                           WHERE     aida.invoice_id = aia.invoice_id
                                 AND aatra.tax_rate_id = aida.awt_tax_rate_id
                                 AND aida.line_type_lookup_code = 'AWT'
                                 AND ROWNUM = 1)
                   END
                      AS tax_rate,
                   CASE
                      WHEN aia.invoice_type_lookup_code = 'AWT'
                           AND inv2.invoice_num IS NOT NULL
                      THEN
                         inv2.awt_group_name
                      ELSE
                         (SELECT aag.name
                            FROM ap_invoice_distributions_all aida,
                                 ap_awt_groups aag
                           WHERE     aida.invoice_id = aia.invoice_id
                                 AND aag.GROUP_ID = aida.awt_origin_group_id
                                 AND aida.line_type_lookup_code = 'AWT'
                                 AND ROWNUM = 1)
                   END
                      AS awt_group_name,
                   SUM (NVL (xal.accounted_dr, 0) - NVL (xal.accounted_cr, 0))
                      AS je_amount,
                   (SELECT SUM (NVL (aila.amount, 0))
                      FROM ap_invoice_lines_all aila
                     WHERE aila.invoice_id =
                              CASE
                                 WHEN inv2.invoice_num IS NOT NULL
                                 THEN
                                    inv2.invoice_id
                                 ELSE
                                    aia.invoice_id
                              END
                           AND aila.line_type_lookup_code = 'ITEM')
                      line_total_amount,
                   NVL (aia.total_tax_amount, 0) tax_amount,
                   NVL (
                      (SELECT SUM (NVL (aila.amount, 0))
                         FROM ap_invoice_lines_all aila
                        WHERE aila.invoice_id =
                                 CASE
                                    WHEN inv2.invoice_num IS NOT NULL
                                    THEN
                                       inv2.invoice_id
                                    ELSE
                                       aia.invoice_id
                                 END
                              AND aila.line_type_lookup_code = 'AWT'
                              AND aila.awt_group_id =
                                     CASE
                                        WHEN aia.invoice_type_lookup_code = 'AWT'
                                             AND inv2.invoice_num IS NOT NULL
                                        THEN
                                           inv2.awt_group_id
                                        ELSE
                                           (SELECT aag.GROUP_ID
                                              FROM ap_invoice_distributions_all aida,
                                                   ap_awt_groups aag
                                             WHERE aida.invoice_id =
                                                      aia.invoice_id
                                                   AND aag.GROUP_ID =
                                                          aida.
                                                           awt_origin_group_id
                                                   AND aida.line_type_lookup_code =
                                                          'AWT'
                                                   AND ROWNUM = 1)
                                     END),
                      0)
                      awt_amount,
                   (SELECT SUM (NVL (aila.amount, 0))
                      FROM ap_invoice_lines_all aila
                     WHERE aila.invoice_id = aia.invoice_id)
                      invoice_total_amount,
                   (SELECT aca.check_date
                      FROM ap_invoice_payments_all aipa, ap_checks_all aca
                     WHERE aipa.check_id = aca.check_id
                           AND aca.status_lookup_code = 'RECONCILED'
                           AND aipa.invoice_id =
                                  CASE
                                     WHEN inv2.invoice_num IS NOT NULL
                                     THEN
                                        inv2.invoice_id
                                     ELSE
                                        aia.invoice_id
                                  END
                           AND ROWNUM = 1)
                      payment_date,
                   (SELECT gcc2.concatenated_segments
                      FROM ap_invoice_distributions_all aida2, gl_code_combinations_kfv gcc2
                     WHERE aida2.invoice_id =
                              CASE WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_id ELSE aia.invoice_id END
                           AND aida2.line_type_lookup_code = 'ITEM'
                           AND aida2.dist_code_combination_id = gcc2.code_combination_id
                           AND gcc2.segment4 != '114207'
                           AND ROWNUM = 1) coa_full,
                   (SELECT gcc2.segment4
                      FROM ap_invoice_distributions_all aida2, gl_code_combinations_kfv gcc2
                     WHERE aida2.invoice_id =
                              CASE WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_id ELSE aia.invoice_id END
                           AND aida2.line_type_lookup_code = 'ITEM'
                           AND aida2.dist_code_combination_id = gcc2.code_combination_id
                           AND gcc2.segment4 != '114207'
                           AND ROWNUM = 1) coa_segment4,
                   (SELECT pol.item_description
                      FROM ap_invoice_distributions_all aida2, po_distributions_all pda2, po_lines_all pol
                     WHERE aida2.invoice_id =
                              CASE WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_id ELSE aia.invoice_id END
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
                   gl_code_combinations_kfv gcc,
                   (SELECT aia2.invoice_num,
                           aia2.invoice_id,
                           aida2.awt_invoice_id,
                           aps2.vendor_name,
                           aps2.vat_registration_num npwp,
                           aia2.supplier_tax_invoice_number,
                           aia2.supplier_tax_invoice_date,
                           aia2.invoice_date,
                           aia2.description,
                           (SELECT aatra.tax_rate
                              FROM ap_awt_tax_rates_all aatra
                             WHERE     1 = 1
                                   AND aatra.tax_rate_id = aida2.awt_tax_rate_id
                                   AND ROWNUM = 1)
                              AS tax_rate,
                           (SELECT aag.GROUP_ID
                              FROM ap_awt_groups aag
                             WHERE     1 = 1
                                   AND aag.GROUP_ID = aida2.awt_origin_group_id
                                   AND ROWNUM = 1)
                              AS awt_group_id,
                           (SELECT aag.name
                              FROM ap_awt_groups aag
                             WHERE     1 = 1
                                   AND aag.GROUP_ID = aida2.awt_origin_group_id
                                   AND ROWNUM = 1)
                              AS awt_group_name
                      FROM ap_invoices_all aia2,
                           ap_invoice_distributions_all aida2,
                           ap_suppliers aps2
                     WHERE     1 = 1
                           AND aia2.invoice_id = aida2.invoice_id
                           AND aia2.vendor_id = aps2.vendor_id
                           AND aida2.line_type_lookup_code = 'AWT') inv2
             WHERE     1 = 1
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
                   AND inv2.awt_invoice_id(+) = aia.invoice_id
                   AND gcc.segment4 IN
                          ('213111',
                           '213112',
                           '213113',
                           '213114',
                           '213115',
                           '213116',
                           '213117')
          GROUP BY gjl.period_name,
                   gjh.je_category,
                   gjh.posted_date,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_num
                      ELSE aia.invoice_num
                   END,
                   aia.invoice_num,
                   inv2.invoice_id,
                   aia.doc_sequence_value,
                   aia.invoice_type_lookup_code,
                   inv2.supplier_tax_invoice_number,
                   inv2.supplier_tax_invoice_date,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.vendor_name
                      ELSE aps.vendor_name
                   END,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.npwp
                      ELSE aps.vat_registration_num
                   END,
                   inv2.invoice_num,
                   aia.invoice_amount,
                   aia.total_tax_amount,
                   inv2.tax_rate,
                   inv2.awt_group_name,
                   inv2.awt_group_id,
                   aia.invoice_id,
                   aia.exchange_rate,
                   aia.invoice_currency_code,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.invoice_date
                      ELSE aia.invoice_date
                   END,
                   CASE
                      WHEN inv2.invoice_num IS NOT NULL THEN inv2.description
                      ELSE aia.description
                   END) inv
   WHERE inv.period = :p_period AND je_amount != 0
ORDER BY inv.invoice_no
"""

# Display order for both the JSON table and the Excel export — matches
# sumber/Witholding Tax Listing - Output.xlsx's column layout.
COLUMNS = [
    ("nomor",                     "No"),
    ("invoice_no",                "Invoice No"),
    ("invoice_date",              "Invoice Date"),
    ("supplier_name",             "Supplier Name"),
    ("npwp",                      "ID Tax Number (NPWP)"),
    ("faktur_pajak",              "Supplier Tax Invoice No"),
    ("coa_full",                  "COA"),
    ("coa_segment4",              "COA Segment 4"),
    ("coa_description",           "COA Segment 4 Description"),
    ("supplier_tax_invoice_date", "Supplier Tax Invoice Date"),
    ("awt_group_name",            "Awt Group Name"),
    ("tax_rate",                  "Tax Rate"),
    ("line_total_amount",         "Gross Amount"),
    ("awt_amount",                "WHT Amount"),
    ("description",               "Description"),
    ("payment_date",              "Payment Date"),
]
_TOTAL_FIELDS = ("line_total_amount", "awt_amount")


def _query(sql: str, params: dict) -> list[dict]:
    with get_oracle_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


async def get_ap_wht_listing(period: str) -> dict:
    """period: Oracle GL period name, e.g. 'JAN-26'."""
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
        logger.error("ap_wht_listing_error", period=period, error=str(e))
        return {"success": False, "error": str(e), "data": []}
