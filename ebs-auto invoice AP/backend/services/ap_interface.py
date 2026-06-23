"""
ap_interface.py
Insert data dari staging ke AP_INVOICES_INTERFACE + AP_INVOICE_LINES_INTERFACE.
Menerima data yang sudah di-edit user dari preview form.
"""

import oracledb
import json
from datetime import datetime
from config import EBS_ORG_ID, EBS_SOURCE


def _parse_date(date_str: str) -> datetime:
    """DD/MM/YYYY → datetime"""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Format tanggal tidak dikenali: '{date_str}'")


def get_next_invoice_id(conn: oracledb.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT AP_INVOICES_INTERFACE_S.NEXTVAL FROM DUAL")
        return cur.fetchone()[0]


def insert_ap_interface(conn: oracledb.Connection, stg_row: dict) -> int:
    """
    Insert 1 invoice ke AP_INVOICES_INTERFACE + AP_INVOICE_LINES_INTERFACE.
    stg_row bisa berisi field dari staging original ATAU dari edited preview.
    Return: interface_invoice_id.
    """
    interface_invoice_id = get_next_invoice_id(conn)

    invoice_date = _parse_date(stg_row["invoice_date"])
    gl_date = datetime.today()

    try:
        terms_date = _parse_date(stg_row["terms_date"]) if stg_row.get("terms_date") else invoice_date
    except ValueError:
        terms_date = invoice_date

    # ── Insert Header ─────────────────────────────────────────────
    header_sql = """
        INSERT INTO AP_INVOICES_INTERFACE (
            INVOICE_ID, INVOICE_NUM, INVOICE_TYPE_LOOKUP_CODE,
            INVOICE_DATE, VENDOR_ID, VENDOR_SITE_ID,
            INVOICE_AMOUNT, INVOICE_CURRENCY_CODE,
            TERMS_NAME, TERMS_DATE, GL_DATE, SOURCE, ORG_ID,
            PO_NUMBER, DESCRIPTION,
            ATTRIBUTE1, ATTRIBUTE2,
            CREATION_DATE, CREATED_BY
        ) VALUES (
            :invoice_id, :invoice_num, 'STANDARD',
            :invoice_date, :vendor_id, :vendor_site_id,
            :invoice_amount, :currency_code,
            :terms_name, :terms_date, :gl_date, :source, :org_id,
            :po_number, :description,
            :attribute1, :attribute2,
            SYSDATE, 1110
        )
    """
    with conn.cursor() as cur:
        cur.execute(header_sql, {
            "invoice_id":      interface_invoice_id,
            "invoice_num":     stg_row["invoice_num"],
            "invoice_date":    invoice_date,
            "vendor_id":       stg_row["vendor_id"],
            "vendor_site_id":  stg_row["vendor_site_id"],
            "invoice_amount":  stg_row["invoice_amount"],
            "currency_code":   stg_row.get("currency_code", "IDR"),
            "terms_name":      stg_row.get("payment_terms") or stg_row.get("TERMS_NAME") or "30 Days",
            "terms_date":      terms_date,
            "gl_date":         gl_date,
            "source":          EBS_SOURCE,
            "org_id":          EBS_ORG_ID,
            "po_number":       stg_row.get("po_number"),
            "description":     f"Import PDF: {stg_row['invoice_num']}",
            "attribute1":      stg_row.get("so_number") or stg_row.get("SO_NUMBER"),
            "attribute2":      stg_row.get("tax_serial_number") or stg_row.get("TAX_SERIAL_NUMBER"),
        })

    # ── Insert Lines ──────────────────────────────────────────────
    lines = json.loads(stg_row["lines_json"]) if isinstance(stg_row["lines_json"], str) \
            else stg_row["lines_json"]

    line_sql = """
        INSERT INTO AP_INVOICE_LINES_INTERFACE (
            INVOICE_ID, INVOICE_LINE_ID, LINE_NUMBER,
            LINE_TYPE_LOOKUP_CODE, AMOUNT, QUANTITY_INVOICED,
            UNIT_PRICE, DESCRIPTION, PO_NUMBER, PO_LINE_NUMBER,
            MATCH_OPTION,
            ATTRIBUTE1, ATTRIBUTE2, ORG_ID
        ) VALUES (
            :invoice_id, AP_INVOICE_LINES_INTERFACE_S.NEXTVAL, :line_number,
            'ITEM', :amount, :quantity,
            :unit_price, :description, :po_number, :po_line_number,
            :match_option,
            :batch_no, :item_code, :org_id
        )
    """
    with conn.cursor() as cur:
        for line in lines:
            po_line_num = line.get("PO_LINE_NUMBER", line.get("po_line_number"))
            if po_line_num is not None and str(po_line_num).strip():
                po_line_num = int(po_line_num)
            else:
                po_line_num = None

            match_opt = line.get("MATCH_OPTION") or None

            cur.execute(line_sql, {
                "invoice_id":     interface_invoice_id,
                "line_number":    line.get("LINE_NUMBER", line.get("line_num")),
                "amount":         float(line.get("AMOUNT", line.get("line_amount", 0))),
                "quantity":       float(line.get("QUANTITY_INVOICED", line.get("qty", 1))),
                "unit_price":     float(line.get("UNIT_PRICE", line.get("unit_price", 0))),
                "description":    line.get("DESCRIPTION", line.get("description", "")),
                "po_number":      line.get("PO_NUMBER") or None,
                "po_line_number": po_line_num,
                "match_option":   match_opt,
                "batch_no":       line.get("BATCH_NO", line.get("batch_no")),
                "item_code":      line.get("ITEM_CODE", line.get("item_code")),
                "org_id":         EBS_ORG_ID,
            })

    conn.commit()
    return interface_invoice_id


def check_import_result(conn: oracledb.Connection,
                         invoice_num: str,
                         vendor_id: int = None) -> dict:
    if vendor_id:
        sql_success = """
            SELECT invoice_id
            FROM   ap_invoices_all
            WHERE  invoice_num = :invoice_num
              AND  vendor_id   = :vendor_id
              AND  org_id      = :org_id
            FETCH FIRST 1 ROWS ONLY
        """
        params = {"invoice_num": invoice_num, "vendor_id": vendor_id, "org_id": EBS_ORG_ID}
    else:
        sql_success = """
            SELECT invoice_id
            FROM   ap_invoices_all
            WHERE  invoice_num = :invoice_num
              AND  org_id      = :org_id
            FETCH FIRST 1 ROWS ONLY
        """
        params = {"invoice_num": invoice_num, "org_id": EBS_ORG_ID}

    with conn.cursor() as cur:
        cur.execute(sql_success, params)
        row = cur.fetchone()

    if row:
        return {"status": "IMPORTED", "invoice_id": row[0], "error_msg": None}

    sql_intf = """
        SELECT status, reject_lookup_code
        FROM   ap_invoices_interface
        WHERE  invoice_num = :invoice_num
          AND  org_id      = :org_id
        FETCH FIRST 1 ROWS ONLY
    """
    with conn.cursor() as cur:
        cur.execute(sql_intf, {
            "invoice_num": invoice_num,
            "org_id":      EBS_ORG_ID,
        })
        row = cur.fetchone()

    if row:
        intf_status = row[0]
        reject_code = row[1]
        if intf_status == "REJECTED":
            return {"status": "ERROR", "invoice_id": None, "error_msg": f"APXIIMPT REJECTED: {reject_code}"}
        return {"status": "INTERFACED", "invoice_id": None, "error_msg": None}

    return {"status": "INTERFACED", "invoice_id": None, "error_msg": None}
