"""
AP Invoice Auto-Import Service
Upload PDF supplier → Claude Vision extract → staging → Oracle EBS AP Interface → APXIIMPT
"""

import os
import json
import base64
import re
import shutil
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF
import anthropic

from app.config import get_settings
from app.database import get_oracle_connection

settings = get_settings()

EBS_ORG_ID = 81
EBS_SOURCE = "XXCKD_PDF_IMPORT"
EBS_USER_ID = 1110
EBS_RESP_ID = 50738
EBS_RESP_APPL_ID = 200

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "ap_invoices")
os.makedirs(UPLOAD_DIR, exist_ok=True)


EXTRACT_PROMPT = """This PDF contains multiple pages from a supplier document package.
Pages may include: Invoice, Faktur Pajak (tax invoice), Delivery Order (DO/Surat Jalan), Purchase Order (PO), or receipt stamps.

Extract all relevant data and return ONLY a valid JSON object, no explanation.

Required JSON structure:
{
  "invoice_num": "invoice number string",
  "invoice_date": "DD/MM/YYYY - printed date on the invoice page",
  "received_date": "DD/MM/YYYY - handwritten date on RECEIVED stamp/cap, or null",
  "vendor_name": "supplier company name issuing the invoice",
  "payment_terms": "payment terms from PURCHASE ORDER page (e.g. IMMEDIATE, 30 Days, Net 30, COD) or null",
  "terms_date": "payment due date DD/MM/YYYY or null",
  "po_number": "PO/Purchase Order number or null",
  "so_number": "SO/Sales Order number or null",
  "tax_serial_number": "nomor seri faktur pajak from FAKTUR PAJAK page or null",
  "currency": "IDR",
  "subtotal": 0.0,
  "tax": 0.0,
  "total": 0.0,
  "lines": [
    {
      "line_num": 1,
      "item_code": "item code or null",
      "description": "item description",
      "qty": 1.0,
      "unit_price": 0.0,
      "amount": 0.0,
      "batch": "batch number or null"
    }
  ]
}

IMPORTANT extraction rules:
- vendor_name: the company ISSUING the invoice (usually top-left header), NOT PT. CKD OTTO Pharmaceuticals (the buyer)
- received_date: look carefully for handwritten date near a rubber stamp that says "RECEIVED BY" or "DITERIMA". If not found, set null.
- payment_terms: look for "Payment Terms", "Terms", "Syarat Pembayaran" on the PURCHASE ORDER page. If not found, set null.
- tax_serial_number: from FAKTUR PAJAK page, look for "Kode dan Nomor Seri Faktur Pajak". If no Faktur Pajak page, set null.
- invoice_date: the printed/typed date on the invoice document itself
- All numeric values as plain numbers without thousand separators
- Return ONLY the JSON, no markdown, no explanation"""


def _pdf_to_images_base64(pdf_path: str) -> list[str]:
    doc = fitz.open(pdf_path)
    images = []
    mat = fitz.Matrix(2.0, 2.0)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        images.append(base64.standard_b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


def _call_claude_vision(images: list[str]) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    content = []
    for i, img in enumerate(images):
        content.append({"type": "text", "text": f"--- Page {i+1} of {len(images)} ---"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}})
    content.append({"type": "text", "text": EXTRACT_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Format tanggal tidak dikenali: '{date_str}'")


def _clean_vendor_name(name: str) -> str:
    name = name.upper().strip()
    name = re.sub(r'^(PT\.?|CV\.?|UD\.?|TB\.?)\s*', '', name)
    return name.strip('. ')


# ── Public Service Functions ──────────────────────────────────────

def extract_pdf(file_path: str, filename: str) -> dict:
    images = _pdf_to_images_base64(file_path)
    data = _call_claude_vision(images)

    invoice_date = data.get("received_date") or data.get("invoice_date") or datetime.today().strftime("%d/%m/%Y")

    lines = []
    for i, ln in enumerate(data.get("lines", []), start=1):
        qty = float(ln.get("qty", 1) or 1)
        price = float(ln.get("unit_price", 0) or 0)
        amount = float(ln.get("amount", 0) or 0) or (qty * price)
        lines.append({
            "line_num": ln.get("line_num", i),
            "item_code": ln.get("item_code"),
            "description": ln.get("description", ""),
            "qty": qty,
            "unit_price": price,
            "line_amount": amount,
            "batch_no": ln.get("batch"),
        })

    subtotal = float(data.get("subtotal", 0) or 0)
    tax_amount = float(data.get("tax", 0) or 0)
    invoice_amount = float(data.get("total", 0) or 0) or (subtotal + tax_amount)

    return {
        "invoice_num": data.get("invoice_num", "").strip(),
        "invoice_date": invoice_date,
        "vendor_name": data.get("vendor_name", "").strip(),
        "payment_terms": data.get("payment_terms") or "30 Days",
        "terms_date": data.get("terms_date"),
        "po_number": data.get("po_number"),
        "so_number": data.get("so_number"),
        "currency_code": data.get("currency", "IDR"),
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "invoice_amount": invoice_amount,
        "tax_serial_number": data.get("tax_serial_number"),
        "source_file": filename,
        "lines": lines,
    }


def save_to_staging(db_conn, invoice_data: dict) -> int:
    from psycopg2.extras import Json
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO ap_invoice_stg (
            invoice_num, invoice_date, vendor_name, payment_terms,
            terms_date, po_number, so_number, currency_code,
            subtotal, tax_amount, invoice_amount, tax_serial_number,
            source_file, lines_json, status, created_date
        ) VALUES (
            %(invoice_num)s, %(invoice_date)s, %(vendor_name)s, %(payment_terms)s,
            %(terms_date)s, %(po_number)s, %(so_number)s, %(currency_code)s,
            %(subtotal)s, %(tax_amount)s, %(invoice_amount)s, %(tax_serial_number)s,
            %(source_file)s, %(lines_json)s, 'NEW', NOW()
        ) RETURNING stg_id
    """, {
        **invoice_data,
        "lines_json": json.dumps(invoice_data["lines"]),
    })
    stg_id = cur.fetchone()[0]
    db_conn.commit()
    return stg_id


def list_invoices(db_conn) -> list[dict]:
    cur = db_conn.cursor()
    cur.execute("""
        SELECT stg_id, invoice_num, vendor_name, invoice_date,
               invoice_amount, status, error_msg, source_file,
               TO_CHAR(created_date, 'DD/MM/YYYY HH24:MI:SS'),
               TO_CHAR(processed_date, 'DD/MM/YYYY HH24:MI:SS'),
               ap_invoice_id
        FROM ap_invoice_stg
        ORDER BY created_date DESC
    """)
    cols = ["stg_id", "invoice_num", "vendor_name", "invoice_date",
            "invoice_amount", "status", "error_msg", "source_file",
            "created_date", "processed_date", "ap_invoice_id"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_invoice_detail(db_conn, stg_id: int) -> Optional[dict]:
    cur = db_conn.cursor()
    cur.execute("""
        SELECT stg_id, status, error_msg, source_file,
               TO_CHAR(created_date, 'DD/MM/YYYY HH24:MI:SS'),
               TO_CHAR(processed_date, 'DD/MM/YYYY HH24:MI:SS'),
               invoice_num, invoice_date, vendor_name, vendor_id,
               vendor_site_id, vendor_site_code, payment_terms,
               terms_date, po_number, so_number, currency_code,
               invoice_amount, subtotal, tax_amount,
               lines_json, interface_invoice_id, ap_invoice_id,
               conc_request_id
        FROM ap_invoice_stg WHERE stg_id = %s
    """, (stg_id,))
    row = cur.fetchone()
    if not row:
        return None
    cols = ["stg_id", "status", "error_msg", "source_file",
            "created_date", "processed_date",
            "invoice_num", "invoice_date", "vendor_name", "vendor_id",
            "vendor_site_id", "vendor_site_code", "payment_terms",
            "terms_date", "po_number", "so_number", "currency_code",
            "invoice_amount", "subtotal", "tax_amount",
            "lines_json", "interface_invoice_id", "ap_invoice_id",
            "conc_request_id"]
    data = dict(zip(cols, row))
    if data.get("lines_json"):
        data["lines"] = json.loads(data["lines_json"])
    data.pop("lines_json", None)
    for key in ("invoice_amount", "subtotal", "tax_amount"):
        if data.get(key) is not None:
            data[key] = float(data[key])
    return data


def validate_invoice(db_conn, ora_conn, stg_id: int) -> dict:
    cur = db_conn.cursor()
    cur.execute("SELECT vendor_name, po_number, invoice_num, status FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("STG_ID tidak ditemukan")

    vendor_name, po_number, invoice_num, status = row
    if status not in ("NEW", "ERROR"):
        raise ValueError(f"Status '{status}', hanya NEW/ERROR bisa divalidasi")

    warnings = []
    vendor_info = None

    with ora_conn.cursor() as oc:
        # Lookup vendor
        base_sql = """
            SELECT s.vendor_id, ss.vendor_site_id, ss.vendor_site_code, s.vendor_name
            FROM ap_suppliers s
            JOIN ap_supplier_sites_all ss ON ss.vendor_id = s.vendor_id AND ss.org_id = :org_id
            WHERE {where_clause}
              AND ss.inactive_date IS NULL
              AND NVL(s.end_date_active, SYSDATE+1) > SYSDATE
            ORDER BY ss.primary_pay_site_flag DESC NULLS LAST, ss.vendor_site_id ASC
            FETCH FIRST 1 ROWS ONLY
        """
        # Exact match
        oc.execute(base_sql.format(where_clause="UPPER(TRIM(s.vendor_name)) = UPPER(TRIM(:vn))"),
                   {"org_id": EBS_ORG_ID, "vn": vendor_name})
        vrow = oc.fetchone()

        if not vrow:
            clean = _clean_vendor_name(vendor_name)
            keywords = [w for w in clean.split() if len(w) >= 3]
            if keywords:
                pattern = '%' + '%'.join(keywords) + '%'
                oc.execute(base_sql.format(where_clause="UPPER(s.vendor_name) LIKE :pattern"),
                           {"org_id": EBS_ORG_ID, "pattern": pattern})
                vrow = oc.fetchone()

        if vrow:
            vendor_info = {"vendor_id": vrow[0], "vendor_site_id": vrow[1], "vendor_site_code": vrow[2], "vendor_name_ebs": vrow[3]}
            if vrow[3].upper().strip() != vendor_name.upper().strip():
                warnings.append({"type": "info", "message": f"Vendor matched: '{vendor_name}' → '{vrow[3]}' (ID: {vrow[0]})"})
        else:
            warnings.append({"type": "warning", "message": f"Vendor '{vendor_name}' tidak ditemukan di EBS"})

        # Check duplicate
        if vendor_info:
            oc.execute("""
                SELECT invoice_id FROM ap_invoices_all
                WHERE invoice_num = :inv AND vendor_id = :vid AND org_id = :oid AND cancelled_date IS NULL
                FETCH FIRST 1 ROWS ONLY
            """, {"inv": invoice_num, "vid": vendor_info["vendor_id"], "oid": EBS_ORG_ID})
            dup = oc.fetchone()
            if dup:
                warnings.append({"type": "warning", "message": f"Invoice '{invoice_num}' sudah ada di EBS (ID: {dup[0]})"})

    update_sql = "UPDATE ap_invoice_stg SET status = 'VALIDATED', error_msg = NULL"
    params = {"stg_id": stg_id}
    if vendor_info:
        update_sql += ", vendor_id = %(vendor_id)s, vendor_site_id = %(vendor_site_id)s, vendor_site_code = %(vendor_site_code)s"
        params.update(vendor_info)
    update_sql += " WHERE stg_id = %(stg_id)s"
    cur.execute(update_sql, params)
    db_conn.commit()

    return {"stg_id": stg_id, "status": "VALIDATED", "vendor": vendor_info, "warnings": warnings}


def insert_to_interface(db_conn, ora_conn, stg_id: int, header: dict, lines: list) -> dict:
    with ora_conn.cursor() as oc:
        oc.execute("SELECT AP_INVOICES_INTERFACE_S.NEXTVAL FROM DUAL")
        iid = oc.fetchone()[0]

        invoice_date = _parse_date(header["INVOICE_DATE"])
        gl_date = datetime.today()
        try:
            terms_date = _parse_date(header.get("TERMS_DATE", "")) if header.get("TERMS_DATE") else invoice_date
        except ValueError:
            terms_date = invoice_date

        oc.execute("""
            INSERT INTO AP_INVOICES_INTERFACE (
                INVOICE_ID, INVOICE_NUM, INVOICE_TYPE_LOOKUP_CODE,
                INVOICE_DATE, VENDOR_ID, VENDOR_SITE_ID,
                INVOICE_AMOUNT, INVOICE_CURRENCY_CODE,
                TERMS_NAME, TERMS_DATE, GL_DATE, SOURCE, ORG_ID,
                PO_NUMBER, DESCRIPTION,
                ATTRIBUTE1, ATTRIBUTE2,
                CREATION_DATE, CREATED_BY
            ) VALUES (
                :iid, :inv_num, 'STANDARD',
                :inv_date, :vid, :vsid,
                :inv_amt, :curr,
                :terms, :terms_date, :gl_date, :source, :org_id,
                :po, :descr,
                :attr1, :attr2,
                SYSDATE, 1110
            )
        """, {
            "iid": iid, "inv_num": header["INVOICE_NUM"],
            "inv_date": invoice_date, "vid": header["VENDOR_ID"], "vsid": header["VENDOR_SITE_ID"],
            "inv_amt": float(header["INVOICE_AMOUNT"]), "curr": header.get("INVOICE_CURRENCY_CODE", "IDR"),
            "terms": header.get("TERMS_NAME", "30 Days"), "terms_date": terms_date,
            "gl_date": gl_date, "source": EBS_SOURCE, "org_id": EBS_ORG_ID,
            "po": header.get("PO_NUMBER"), "descr": f"Import PDF: {header['INVOICE_NUM']}",
            "attr1": header.get("SO_NUMBER"), "attr2": header.get("TAX_SERIAL_NUMBER"),
        })

        for line in lines:
            oc.execute("""
                INSERT INTO AP_INVOICE_LINES_INTERFACE (
                    INVOICE_ID, INVOICE_LINE_ID, LINE_NUMBER,
                    LINE_TYPE_LOOKUP_CODE, AMOUNT, QUANTITY_INVOICED,
                    UNIT_PRICE, DESCRIPTION, PO_NUMBER, PO_LINE_NUMBER,
                    ATTRIBUTE1, ATTRIBUTE2, ORG_ID
                ) VALUES (
                    :iid, AP_INVOICE_LINES_INTERFACE_S.NEXTVAL, :ln,
                    'ITEM', :amt, :qty, :price, :descr, :po, :po_ln,
                    :batch, :item_code, :org_id
                )
            """, {
                "iid": iid, "ln": line.get("LINE_NUMBER", line.get("line_num")),
                "amt": float(line.get("AMOUNT", line.get("line_amount", 0))),
                "qty": float(line.get("QUANTITY_INVOICED", line.get("qty", 1))),
                "price": float(line.get("UNIT_PRICE", line.get("unit_price", 0))),
                "descr": line.get("DESCRIPTION", line.get("description", "")),
                "po": line.get("PO_NUMBER"), "po_ln": line.get("PO_LINE_NUMBER"),
                "batch": line.get("BATCH_NO", line.get("batch_no")),
                "item_code": line.get("ITEM_CODE", line.get("item_code")),
                "org_id": EBS_ORG_ID,
            })

        ora_conn.commit()

    cur = db_conn.cursor()
    cur.execute("UPDATE ap_invoice_stg SET status = 'INTERFACED', interface_invoice_id = %s WHERE stg_id = %s", (iid, stg_id))
    db_conn.commit()

    return {"stg_id": stg_id, "status": "INTERFACED", "interface_invoice_id": iid}


def run_apxiimpt(db_conn, ora_conn, stg_id: int) -> dict:
    plsql = """
        DECLARE v_req_id NUMBER := 0;
        BEGIN
            FND_GLOBAL.APPS_INITIALIZE(:uid, :rid, :raid);
            MO_GLOBAL.SET_POLICY_CONTEXT('S', :oid);
            v_req_id := FND_REQUEST.SUBMIT_REQUEST(
                'SQLAP','APXIIMPT',NULL,NULL,FALSE,
                TO_CHAR(:oid),:source,NULL,NULL,NULL,NULL,NULL,'N','N'
            );
            COMMIT;
            :req_id := v_req_id;
        END;
    """
    req_var = ora_conn.cursor().var(int)
    with ora_conn.cursor() as oc:
        oc.execute(plsql, {
            "uid": EBS_USER_ID, "rid": EBS_RESP_ID, "raid": EBS_RESP_APPL_ID,
            "oid": EBS_ORG_ID, "source": EBS_SOURCE, "req_id": req_var,
        })
    ora_conn.commit()
    req_id = req_var.getvalue()
    if not req_id or req_id == 0:
        raise RuntimeError("FND_REQUEST.SUBMIT_REQUEST returned 0")

    cur = db_conn.cursor()
    cur.execute("UPDATE ap_invoice_stg SET conc_request_id = %s, status = 'SUBMITTED' WHERE stg_id = %s", (req_id, stg_id))
    db_conn.commit()

    return {"stg_id": stg_id, "status": "SUBMITTED", "conc_request_id": req_id}


def check_request_status(ora_conn, request_id: int) -> dict:
    sql = """
        SELECT fcr.phase_code, fcr.status_code, fcr.completion_text,
               fpl.meaning AS phase_meaning, fsl.meaning AS status_meaning
        FROM   fnd_concurrent_requests fcr
        JOIN   fnd_lookups fpl ON fpl.lookup_type = 'CP_PHASE_CODE' AND fpl.lookup_code = fcr.phase_code
        JOIN   fnd_lookups fsl ON fsl.lookup_type = 'CP_STATUS_CODE' AND fsl.lookup_code = fcr.status_code
        WHERE  fcr.request_id = :rid
    """
    with ora_conn.cursor() as oc:
        oc.execute(sql, {"rid": request_id})
        row = oc.fetchone()
    if not row:
        return {"phase": "UNKNOWN", "status": "UNKNOWN", "completion_text": None}
    return {"phase": row[3], "status": row[4], "phase_code": row[0], "status_code": row[1], "completion_text": row[2]}


def check_import_result(ora_conn, invoice_num: str, vendor_id=None) -> dict:
    if vendor_id:
        sql = """
            SELECT invoice_id FROM ap_invoices_all
            WHERE invoice_num = :inv AND vendor_id = :vid AND org_id = :oid AND cancelled_date IS NULL
            FETCH FIRST 1 ROWS ONLY
        """
        params = {"inv": invoice_num, "vid": vendor_id, "oid": EBS_ORG_ID}
    else:
        sql = """
            SELECT invoice_id FROM ap_invoices_all
            WHERE invoice_num = :inv AND org_id = :oid AND cancelled_date IS NULL
            FETCH FIRST 1 ROWS ONLY
        """
        params = {"inv": invoice_num, "oid": EBS_ORG_ID}

    with ora_conn.cursor() as oc:
        oc.execute(sql, params)
        row = oc.fetchone()
    if row:
        return {"status": "IMPORTED", "invoice_id": row[0]}

    sql2 = """
        SELECT status FROM ap_invoices_interface
        WHERE invoice_num = :inv AND org_id = :oid
        FETCH FIRST 1 ROWS ONLY
    """
    with ora_conn.cursor() as oc:
        oc.execute(sql2, {"inv": invoice_num, "oid": EBS_ORG_ID})
        row = oc.fetchone()
    if row and row[0] == "REJECTED":
        return {"status": "ERROR", "invoice_id": None, "error_msg": "APXIIMPT REJECTED"}

    return {"status": "PENDING", "invoice_id": None}


def attach_pdf_to_invoice(ora_conn, ap_invoice_id: int, pdf_path: str, filename: str):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    with ora_conn.cursor() as cur:
        try:
            cur.execute("""
                SELECT category_id FROM fnd_document_categories_tl
                WHERE user_name = 'From Supplier' AND language = USERENV('LANG') AND ROWNUM = 1
            """)
            row = cur.fetchone()
            category_id = row[0] if row else None
        except Exception:
            category_id = None

        if not category_id:
            cur.execute("SELECT category_id FROM fnd_document_categories WHERE name = 'Miscellaneous' AND ROWNUM = 1")
            category_id = cur.fetchone()[0]

        cur.execute("SELECT fnd_lobs_s.NEXTVAL FROM DUAL")
        media_id = cur.fetchone()[0]
        cur.execute("SELECT fnd_documents_s.NEXTVAL FROM DUAL")
        document_id = cur.fetchone()[0]
        cur.execute("SELECT fnd_attached_documents_s.NEXTVAL FROM DUAL")
        attached_doc_id = cur.fetchone()[0]

        cur.execute("""
            SELECT NVL(MAX(seq_num), 0) + 10
            FROM fnd_attached_documents
            WHERE entity_name = 'AP_INVOICES' AND pk1_value = :pk1
        """, {"pk1": str(ap_invoice_id)})
        seq_num = cur.fetchone()[0]

        import oracledb
        lob = ora_conn.createlob(oracledb.DB_TYPE_BLOB)
        lob.write(pdf_bytes)

        cur.execute("""
            INSERT INTO fnd_lobs (
                file_id, file_name, file_content_type, file_data,
                upload_date, file_format, language, oracle_charset, program_name
            ) VALUES (
                :media_id, :filename, 'application/pdf', :file_data,
                SYSDATE, 'binary', 'US', 'UTF8', 'FNDATTCH'
            )
        """, {"media_id": media_id, "filename": filename, "file_data": lob})

        cur.execute("""
            INSERT INTO fnd_documents (
                document_id, creation_date, created_by, last_update_date, last_updated_by,
                datatype_id, category_id, security_type, publish_flag, media_id, usage_type, file_name
            ) VALUES (
                :doc_id, SYSDATE, :uid, SYSDATE, :uid,
                6, :cat_id, 1, 'Y', :media_id, 'O', :filename
            )
        """, {"doc_id": document_id, "uid": EBS_USER_ID, "cat_id": category_id, "media_id": media_id, "filename": filename})

        cur.execute("""
            INSERT INTO fnd_documents_tl (
                document_id, creation_date, created_by, last_update_date, last_updated_by,
                language, source_lang, description, file_name, media_id
            ) VALUES (
                :doc_id, SYSDATE, :uid, SYSDATE, :uid,
                'US', 'US', :descr, :filename, :media_id
            )
        """, {"doc_id": document_id, "uid": EBS_USER_ID, "descr": filename, "filename": filename, "media_id": media_id})

        cur.execute("""
            INSERT INTO fnd_attached_documents (
                attached_document_id, document_id, creation_date, created_by,
                last_update_date, last_updated_by, seq_num, entity_name, pk1_value,
                automatically_added_flag
            ) VALUES (
                :att_id, :doc_id, SYSDATE, :uid, SYSDATE, :uid,
                :seq, 'AP_INVOICES', :pk1, 'N'
            )
        """, {"att_id": attached_doc_id, "doc_id": document_id, "uid": EBS_USER_ID, "seq": seq_num, "pk1": str(ap_invoice_id)})

    ora_conn.commit()


def check_and_update_status(db_conn, ora_conn, stg_id: int) -> dict:
    cur = db_conn.cursor()
    cur.execute("""
        SELECT conc_request_id, invoice_num, vendor_id, status, source_file
        FROM ap_invoice_stg WHERE stg_id = %s
    """, (stg_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("STG_ID tidak ditemukan")

    conc_req_id, invoice_num, vendor_id, stg_status, source_file = row
    result = {"stg_status": stg_status}

    if conc_req_id:
        result["concurrent"] = check_request_status(ora_conn, conc_req_id)

    if stg_status in ("SUBMITTED", "INTERFACED"):
        import_res = check_import_result(ora_conn, invoice_num, vendor_id)
        result["import"] = import_res

        if import_res["status"] == "IMPORTED":
            ap_inv_id = import_res["invoice_id"]

            # Attach PDF to the created invoice
            if source_file:
                pdf_path = os.path.join(UPLOAD_DIR, source_file)
                if os.path.exists(pdf_path):
                    try:
                        attach_pdf_to_invoice(ora_conn, ap_inv_id, pdf_path, source_file)
                        result["attachment"] = "PDF attached"
                    except Exception as e:
                        result["attachment_error"] = str(e)

            cur.execute("""
                UPDATE ap_invoice_stg SET status = 'IMPORTED', ap_invoice_id = %s, processed_date = NOW()
                WHERE stg_id = %s
            """, (ap_inv_id, stg_id))
            db_conn.commit()
            result["stg_status"] = "IMPORTED"
        elif import_res["status"] == "ERROR":
            cur.execute("""
                UPDATE ap_invoice_stg SET status = 'ERROR', error_msg = %s
                WHERE stg_id = %s
            """, (import_res.get("error_msg", "Import rejected"), stg_id))
            db_conn.commit()
            result["stg_status"] = "ERROR"

    return result
