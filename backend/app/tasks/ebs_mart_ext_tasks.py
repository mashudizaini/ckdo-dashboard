"""
ETL for the rest of the library v2 catalog (ext_sql.py): etl_mart_ext,
hourly 06-20. Every stream is a full snapshot — each is a list of things
still open (documents waiting for approval, holds, interface rows) or a
small, bounded window (withholding 24 months, GL budget two years), and a
resolved item must disappear.

  documents waiting for approval  PO_HEADERS_ALL / PO_REQUISITION_HEADERS_ALL
                                  In Process, Pre-Approved, Requires
                                  Reapproval, Incomplete; the approver waited
                                  on is PO_ACTION_HISTORY's open row
  SO holds                        OE_ORDER_HOLDS_ALL not released
  AP withholding                  AWT distributions, 24 months
  GL budget / encumbrance         GL_BALANCES actual_flag B and E, ledger 2022
  interface rows (IT)             AP, GL, INV (MTI + MMTT), receiving

Same conventions as ebs_mart_tasks.py. Restart celery after deploying.
"""
import logging

from app.database import get_oracle_connection
from app.services.ebs_mart.constants import EBS_LEDGER_ID, EBS_OPERATING_UNIT_ID, EBS_PROCESS_ORG_ID
from app.tasks.celery_app import celery_app
from app.tasks.ebs_mart_fin_tasks import _fx, _idr
from app.tasks.ebs_mart_sa_tasks import _q, _replace
from app.tasks.ebs_mart_tasks import _BATCH, _Run, _int, _num, refresh_marts_for_job

logger = logging.getLogger(__name__)

_PENDING_STATUSES = "('IN PROCESS', 'PRE-APPROVED', 'REQUIRES REAPPROVAL', 'INCOMPLETE')"
# The approver a document waits on: the open (action_code NULL) row of its
# action history.
_APPROVER = """(SELECT MAX(papf.full_name)
                  FROM po_action_history pah
                  JOIN per_all_people_f papf ON papf.person_id = pah.employee_id
                                            AND TRUNC(SYSDATE) BETWEEN papf.effective_start_date AND papf.effective_end_date
                 WHERE pah.object_id = {id} AND pah.object_type_code = '{typ}' AND pah.action_code IS NULL)"""
_LAST_ACTION = """(SELECT MAX(pah.action_code) KEEP (DENSE_RANK LAST ORDER BY pah.sequence_num)
                     FROM po_action_history pah
                    WHERE pah.object_id = {id} AND pah.object_type_code = '{typ}' AND pah.action_code IS NOT NULL)"""
_LAST_ACTION_DATE = """(SELECT MAX(pah.action_date) FROM po_action_history pah
                         WHERE pah.object_id = {id} AND pah.object_type_code = '{typ}' AND pah.action_code IS NOT NULL)"""

_PO_PENDING_SQL = f"""
    SELECT 'PO', ph.po_header_id, ph.segment1, ph.type_lookup_code, ph.authorization_status, ph.creation_date,
           {_LAST_ACTION_DATE.format(id='ph.po_header_id', typ='PO')},
           {_LAST_ACTION.format(id='ph.po_header_id', typ='PO')},
           {_APPROVER.format(id='ph.po_header_id', typ='PO')},
           (SELECT MAX(p.full_name) FROM per_all_people_f p WHERE p.person_id = ph.agent_id
               AND TRUNC(SYSDATE) BETWEEN p.effective_start_date AND p.effective_end_date),
           SUBSTR(sup.vendor_name, 1, 240), ph.currency_code,
           (SELECT SUM(pl.quantity * pl.unit_price) FROM po_lines_all pl
             WHERE pl.po_header_id = ph.po_header_id AND NVL(pl.cancel_flag, 'N') = 'N'),
           NVL(ph.rate, 1), SUBSTR(ph.comments, 1, 240)
      FROM po_headers_all ph
      LEFT JOIN ap_suppliers sup ON sup.vendor_id = ph.vendor_id
     WHERE ph.org_id = :org_id
       AND ph.authorization_status IN {_PENDING_STATUSES}
       AND NVL(ph.cancel_flag, 'N') = 'N'
       AND NVL(ph.closed_code, 'OPEN') <> 'FINALLY CLOSED'
"""
_REQ_PENDING_SQL = f"""
    SELECT 'PR', prh.requisition_header_id, prh.segment1, prh.type_lookup_code, prh.authorization_status,
           prh.creation_date,
           {_LAST_ACTION_DATE.format(id='prh.requisition_header_id', typ='REQUISITION')},
           {_LAST_ACTION.format(id='prh.requisition_header_id', typ='REQUISITION')},
           {_APPROVER.format(id='prh.requisition_header_id', typ='REQUISITION')},
           (SELECT MAX(p.full_name) FROM per_all_people_f p WHERE p.person_id = prh.preparer_id
               AND TRUNC(SYSDATE) BETWEEN p.effective_start_date AND p.effective_end_date),
           NULL, 'IDR',
           (SELECT SUM(prl.quantity * prl.unit_price) FROM po_requisition_lines_all prl
             WHERE prl.requisition_header_id = prh.requisition_header_id AND NVL(prl.cancel_flag, 'N') = 'N'),
           1, SUBSTR(prh.description, 1, 240)
      FROM po_requisition_headers_all prh
     WHERE prh.org_id = :org_id
       AND prh.authorization_status IN {_PENDING_STATUSES}
       AND NVL(prh.cancel_flag, 'N') = 'N'
       AND NVL(prh.closed_code, 'OPEN') <> 'FINALLY CLOSED'
"""

_SO_HOLD_SQL = """
    SELECT oh.order_hold_id, ooh.header_id, TO_CHAR(ooh.order_number),
           (SELECT SUBSTR(t.name, 1, 120) FROM oe_transaction_types_tl t
             WHERE t.transaction_type_id = ooh.order_type_id AND t.language = 'US'),
           oh.line_id,
           (SELECT ool.line_number || '.' || ool.shipment_number FROM oe_order_lines_all ool WHERE ool.line_id = oh.line_id),
           (SELECT SUBSTR(hp.party_name, 1, 240) FROM hz_cust_accounts hca JOIN hz_parties hp ON hp.party_id = hca.party_id
             WHERE hca.cust_account_id = ooh.sold_to_org_id),
           SUBSTR(hd.name, 1, 120), hd.type_code, oh.creation_date, hs.hold_until_date, SUBSTR(hs.hold_comment, 1, 500),
           (SELECT fu.user_name FROM fnd_user fu WHERE fu.user_id = oh.created_by),
           (SELECT SUM(ool.ordered_quantity * ool.unit_selling_price) FROM oe_order_lines_all ool
             WHERE ool.header_id = ooh.header_id AND NVL(ool.cancelled_flag, 'N') = 'N'),
           ooh.transactional_curr_code
      FROM oe_order_holds_all oh
      JOIN oe_hold_sources_all hs    ON hs.hold_source_id = oh.hold_source_id
      JOIN oe_hold_definitions hd    ON hd.hold_id = hs.hold_id
      JOIN oe_order_headers_all ooh  ON ooh.header_id = oh.header_id
     WHERE oh.org_id = :org_id
       AND NVL(oh.released_flag, 'N') = 'N'
"""

_AWT_SQL = """
    SELECT aid.invoice_distribution_id, ai.invoice_id, ai.invoice_num, ai.invoice_date, aid.accounting_date,
           aid.period_name, sup.segment1, SUBSTR(sup.vendor_name, 1, 240),
           (SELECT atr.tax_name FROM ap_awt_tax_rates_all atr WHERE atr.tax_rate_id = aid.awt_tax_rate_id),
           (SELECT atr.tax_rate FROM ap_awt_tax_rates_all atr WHERE atr.tax_rate_id = aid.awt_tax_rate_id),
           ai.invoice_currency_code, -aid.amount, -NVL(aid.base_amount, aid.amount), gcc.segment4
      FROM ap_invoice_distributions_all aid
      JOIN ap_invoices_all ai            ON ai.invoice_id = aid.invoice_id
      JOIN ap_suppliers sup              ON sup.vendor_id = ai.vendor_id
      LEFT JOIN gl_code_combinations gcc ON gcc.code_combination_id = aid.dist_code_combination_id
     WHERE ai.org_id = :org_id
       AND aid.line_type_lookup_code = 'AWT'
       AND ai.cancelled_date IS NULL
       AND NVL(aid.reversal_flag, 'N') <> 'Y'
       AND aid.accounting_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -24)
"""

# Budget (B) and encumbrance (E) balances. Same filters as the actual
# extract in etl_mart_gl (summary accounts double count otherwise).
_BUDGET_SQL = """
    SELECT gb.actual_flag,
           (SELECT bv.budget_name FROM gl_budget_versions bv WHERE bv.budget_version_id = gb.budget_version_id),
           (SELECT et.encumbrance_type FROM gl_encumbrance_types et WHERE et.encumbrance_type_id = gb.encumbrance_type_id),
           gb.code_combination_id, gb.period_name, gp.period_year, gp.period_num, gp.start_date,
           gcc.segment3, gcc.segment4, gcc.account_type,
           NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)
      FROM gl_balances gb
      JOIN gl_code_combinations gcc ON gcc.code_combination_id = gb.code_combination_id
      JOIN gl_ledgers gl            ON gl.ledger_id = gb.ledger_id
      JOIN gl_periods gp            ON gp.period_set_name = gl.period_set_name AND gp.period_name = gb.period_name
     WHERE gb.ledger_id = :ledger
       AND gb.actual_flag IN ('B', 'E')
       AND gb.currency_code = 'IDR'
       AND gb.template_id IS NULL
       AND gcc.summary_flag = 'N'
       AND NVL(gp.adjustment_period_flag, 'N') = 'N'
       AND gp.period_year >= EXTRACT(YEAR FROM SYSDATE) - 1
       AND (NVL(gb.period_net_dr, 0) <> 0 OR NVL(gb.period_net_cr, 0) <> 0)
"""

# ── Interface rows (IT) ──────────────────────────────────────────────────────

_AP_INTF_SQL = """
    SELECT aii.invoice_id, aii.source, aii.invoice_num, NVL(aii.status, 'NEW'), air.reject_lookup_code,
           SUBSTR(NVL(flv.meaning, air.reject_lookup_code), 1, 240), aii.invoice_date, aii.creation_date,
           aii.invoice_amount, aii.request_id, SUBSTR(aii.vendor_name, 1, 120), air.parent_table
      FROM ap_invoices_interface aii
      LEFT JOIN ap_interface_rejections air
             ON (air.parent_table = 'AP_INVOICES_INTERFACE' AND air.parent_id = aii.invoice_id)
             OR (air.parent_table = 'AP_INVOICE_LINES_INTERFACE' AND air.parent_id IN
                    (SELECT l.invoice_line_id FROM ap_invoice_lines_interface l WHERE l.invoice_id = aii.invoice_id))
      LEFT JOIN fnd_lookup_values flv ON flv.lookup_type = 'REJECT CODE' AND flv.lookup_code = air.reject_lookup_code
                                     AND flv.language = 'US' AND flv.view_application_id = 200
     WHERE NVL(aii.status, 'NEW') <> 'PROCESSED'
       AND (aii.org_id = :org_id OR aii.org_id IS NULL)
"""
# GL interface: grouped — journal import rows come in thousands per group.
_GL_INTF_SQL = """
    SELECT gi.status, gi.user_je_source_name, gi.user_je_category_name, TRUNC(gi.accounting_date), gi.group_id,
           gi.request_id, MIN(gi.date_created), COUNT(*),
           SUM(NVL(gi.accounted_dr, NVL(gi.entered_dr, 0))), SUM(NVL(gi.accounted_cr, NVL(gi.entered_cr, 0)))
      FROM gl_interface gi
     WHERE gi.ledger_id = :ledger
     GROUP BY gi.status, gi.user_je_source_name, gi.user_je_category_name, TRUNC(gi.accounting_date), gi.group_id,
              gi.request_id
"""
_MTI_SQL = """
    SELECT mti.transaction_interface_id, mti.source_code,
           (SELECT mtt.transaction_type_name FROM mtl_transaction_types mtt WHERE mtt.transaction_type_id = mti.transaction_type_id),
           mti.process_flag, SUBSTR(mti.error_code, 1, 240), SUBSTR(mti.error_explanation, 1, 500),
           mti.transaction_date, mti.creation_date, mti.transaction_quantity, msi.segment1, mti.request_id
      FROM mtl_transactions_interface mti
      LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = mti.inventory_item_id
                                      AND msi.organization_id = mti.organization_id
     WHERE mti.organization_id = :org
"""
# Pending transactions in MMTT (not yet processed) — they block closing the
# inventory period.
_MMTT_SQL = """
    SELECT mmtt.transaction_temp_id, mmtt.source_code,
           (SELECT mtt.transaction_type_name FROM mtl_transaction_types mtt WHERE mtt.transaction_type_id = mmtt.transaction_type_id),
           mmtt.process_flag, SUBSTR(mmtt.error_code, 1, 240), SUBSTR(mmtt.error_explanation, 1, 500),
           mmtt.transaction_date, mmtt.creation_date, mmtt.transaction_quantity, msi.segment1
      FROM mtl_material_transactions_temp mmtt
      LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = mmtt.inventory_item_id
                                      AND msi.organization_id = mmtt.organization_id
     WHERE mmtt.organization_id = :org
"""
_RTI_SQL = """
    SELECT rti.interface_transaction_id, rti.transaction_type, rti.processing_status_code, rti.transaction_status_code,
           (SELECT SUBSTR(MAX(pie.error_message), 1, 500) FROM po_interface_errors pie
             WHERE pie.interface_line_id = rti.interface_transaction_id),
           rti.transaction_date, rti.creation_date, rti.quantity,
           (SELECT ph.segment1 FROM po_headers_all ph WHERE ph.po_header_id = rti.po_header_id),
           (SELECT msi.segment1 FROM mtl_system_items_b msi WHERE msi.inventory_item_id = rti.item_id
               AND msi.organization_id = rti.to_organization_id),
           rti.request_id
      FROM rcv_transactions_interface rti
     WHERE (rti.to_organization_id = :org OR rti.org_id = :org_id)
"""


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_ext")
def etl_mart_ext(year: int = None, month: int = None, full_refresh: bool = False,
                 trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    job = "etl_mart_ext"
    run = _Run(job, trigger_type, triggered_by, {"org_id": EBS_OPERATING_UNIT_ID, "ledger_id": EBS_LEDGER_ID})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_loaded = 0
    try:
        cur = run.cur
        org, led, inv = {"org_id": EBS_OPERATING_UNIT_ID}, {"ledger": EBS_LEDGER_ID}, {"org": EBS_PROCESS_ORG_ID}
        ora = get_oracle_connection()
        try:
            co = ora.cursor()
            co.arraysize = _BATCH
            pending = _q(co, "po_headers_all (approval)", _PO_PENDING_SQL, org)
            pending += _q(co, "po_requisition_headers_all (approval)", _REQ_PENDING_SQL, org)
            holds = _q(co, "oe_order_holds_all", _SO_HOLD_SQL, org)
            awt = _q(co, "ap_invoice_distributions_all (AWT)", _AWT_SQL, org)
            budget = _q(co, "gl_balances (budget/encumbrance)", _BUDGET_SQL, led)
            ap_intf = _q(co, "ap_invoices_interface", _AP_INTF_SQL, org)
            gl_intf = _q(co, "gl_interface", _GL_INTF_SQL, led)
            mti = _q(co, "mtl_transactions_interface", _MTI_SQL, inv)
            mmtt = _q(co, "mtl_material_transactions_temp", _MMTT_SQL, inv)
            rti = _q(co, "rcv_transactions_interface", _RTI_SQL, {**org, **inv})
        finally:
            ora.close()
        rows_read = sum(map(len, (pending, holds, awt, budget, ap_intf, gl_intf, mti, mmtt, rti)))
        fx = _fx(cur)

        n = _replace(cur, "core.doc_approval_pending",
                     ["row_key", "doc_type", "doc_id", "doc_number", "doc_subtype", "authorization_status",
                      "created_date", "submitted_date", "last_action", "pending_approver", "preparer", "vendor_name",
                      "currency_code", "amount_entered", "amount_idr", "description"],
                     [(f"{r[0]}|{int(r[1])}", r[0], _int(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
                       r[11], _num(r[12]), (float(r[12]) * float(r[13] or 1)) if r[12] is not None else None, r[14])
                      for r in pending])
        n += _replace(cur, "core.so_hold",
                      ["order_hold_id", "header_id", "order_number", "order_type", "line_id", "line_number",
                       "customer_name", "hold_name", "hold_type", "applied_date", "hold_until_date", "hold_comment",
                       "applied_by", "order_amount_idr"],
                      [(_int(r[0]), _int(r[1]), r[2], r[3], _int(r[4]), r[5], r[6], r[7], r[8], r[9], r[10], r[11],
                        r[12], _idr(r[13], r[14], fx)) for r in holds])
        n += _replace(cur, "core.ap_withholding",
                      ["invoice_distribution_id", "invoice_id", "invoice_num", "invoice_date", "accounting_date",
                       "period_name", "vendor_num", "vendor_name", "tax_name", "tax_rate", "currency_code",
                       "amount_entered", "amount_idr", "account_code"],
                      [(_int(r[0]), _int(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], _num(r[9]), r[10],
                        _num(r[11]), _num(r[12]), r[13]) for r in awt])
        n += _replace(cur, "core.fact_gl_budget",
                      ["row_key", "kind", "budget_name", "encumbrance_type", "code_combination_id", "period_name",
                       "period_year", "period_num", "period_start_date", "segment3", "segment4", "account_type",
                       "period_net"],
                      [(f"{r[0]}|{r[1] or r[2] or ''}|{int(r[3])}|{r[4]}", "BUDGET" if r[0] == "B" else "ENCUMBRANCE",
                        r[1], r[2], _int(r[3]), r[4], _int(r[5]), _int(r[6]), r[7], r[8], r[9], r[10], _num(r[11]))
                       for r in budget])

        intf = []
        for i, r in enumerate(ap_intf):
            intf.append((f"AP|{_int(r[0])}|{i}", "AP", r[1], r[2],
                         "ERROR" if r[3] == "REJECTED" or r[4] else r[3], r[4], r[5], r[6], r[7], _num(r[8]), None,
                         None, _int(r[9]), 1))
        for i, r in enumerate(gl_intf):
            status = r[0] or "NEW"
            intf.append((f"GL|{i}|{status}|{r[4]}|{r[3]}", "GL", r[1], f"group {r[4] or '-'} · {r[2] or ''}",
                         "PENDING" if status == "NEW" else ("PROCESSED" if status == "P" else "ERROR"), status, None,
                         r[3], r[6], _num(r[8]), None, None, _int(r[5]), _int(r[7])))
        for r in mti:
            flag = str(r[3]) if r[3] is not None else ""
            intf.append((f"INV-MTI|{int(r[0])}", "INV", r[1], r[2], "ERROR" if flag == "3" or r[4] else "PENDING",
                         r[4], r[5], r[6], r[7], None, _num(r[8]), r[9], _int(r[10]), 1))
        for r in mmtt:
            flag = str(r[3]) if r[3] is not None else ""
            intf.append((f"INV-MMTT|{int(r[0])}", "INV (pending MMTT)", r[1], r[2],
                         "ERROR" if flag == "E" or r[4] else "PENDING", r[4], r[5], r[6], r[7], None, _num(r[8]), r[9],
                         None, 1))
        for r in rti:
            intf.append((f"RCV|{int(r[0])}", "RCV", r[1], r[8],
                         "ERROR" if (r[2] == "ERROR" or r[3] == "ERROR" or r[4]) else (r[2] or "PENDING"), r[3], r[4],
                         r[5], r[6], None, _num(r[7]), r[9], _int(r[10]), 1))
        n += _replace(cur, "core.it_interface_row",
                      ["row_key", "interface_name", "source", "doc_ref", "status", "error_code", "error_message",
                       "txn_date", "created_date", "amount", "quantity", "item_code", "request_id", "row_count"], intf)
        rows_loaded = n

        run.pg.commit()
        refresh_marts_for_job(job)
        run.finish("success", rows_read, rows_loaded)
        logger.info("[%s] pending=%s holds=%s awt=%s budget=%s interface=%s", job, len(pending), len(holds), len(awt),
                    len(budget), len(intf))
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_loaded, error=str(e))
        run.close()
        raise
    run.close()
    return {"status": "success", "rows_read": rows_read, "rows_loaded": rows_loaded}
