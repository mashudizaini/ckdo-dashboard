"""
invoices.py — GET /invoices
CRUD staging table di PostgreSQL + status tracker.
"""

import json
from fastapi import APIRouter, HTTPException
from pg_config import get_pg_connection
from config import get_oracle_connection
from models.schemas import InvoiceListResponse

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get("/", response_model=list[InvoiceListResponse])
def list_invoices():
    """Ambil semua invoice di staging (PostgreSQL), order by terbaru."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stg_id, invoice_num, vendor_name,
                       invoice_date, invoice_amount, status,
                       error_msg, source_file,
                       TO_CHAR(created_date,   'DD/MM/YYYY HH24:MI:SS'),
                       TO_CHAR(processed_date,  'DD/MM/YYYY HH24:MI:SS'),
                       ap_invoice_id
                FROM   ap_invoice_stg
                ORDER  BY created_date DESC
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    cols = ["stg_id","invoice_num","vendor_name","invoice_date",
            "invoice_amount","status","error_msg","source_file",
            "created_date","processed_date","ap_invoice_id"]

    return [InvoiceListResponse(**dict(zip(cols, r))) for r in rows]


@router.get("/{stg_id}")
def get_invoice(stg_id: int):
    """Detail 1 invoice dari staging (PostgreSQL) termasuk line items."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stg_id, status, error_msg, source_file,
                       TO_CHAR(created_date,   'DD/MM/YYYY HH24:MI:SS'),
                       TO_CHAR(processed_date,  'DD/MM/YYYY HH24:MI:SS'),
                       invoice_num, invoice_date, vendor_name, vendor_id,
                       vendor_site_id, vendor_site_code, payment_terms,
                       terms_date, po_number, so_number, currency_code,
                       invoice_amount, subtotal, tax_amount,
                       lines_json, interface_invoice_id, ap_invoice_id,
                       conc_request_id
                FROM   ap_invoice_stg
                WHERE  stg_id = %s
            """, (stg_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"STG_ID {stg_id} tidak ditemukan")

    cols = [
        "stg_id","status","error_msg","source_file",
        "created_date","processed_date",
        "invoice_num","invoice_date","vendor_name","vendor_id",
        "vendor_site_id","vendor_site_code","payment_terms",
        "terms_date","po_number","so_number","currency_code",
        "invoice_amount","subtotal","tax_amount",
        "lines_json","interface_invoice_id","ap_invoice_id",
        "conc_request_id",
    ]
    data = dict(zip(cols, row))

    if data.get("lines_json"):
        data["lines"] = json.loads(data["lines_json"])
    del data["lines_json"]

    # Convert Decimal to float for JSON serialization
    for key in ("invoice_amount", "subtotal", "tax_amount"):
        if data.get(key) is not None:
            data[key] = float(data[key])

    return data


@router.put("/{stg_id}")
def update_invoice(stg_id: int, payload: dict):
    """Update field header di staging (PostgreSQL) sebelum submit."""
    allowed_fields = {
        "invoice_num", "invoice_date", "vendor_name", "terms_date",
        "po_number", "so_number", "currency_code", "invoice_amount",
        "subtotal", "tax_amount", "lines_json",
    }
    update_pairs = {k: v for k, v in payload.items() if k in allowed_fields}
    if not update_pairs:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")

    set_clause = ", ".join(f"{k} = %({k})s" for k in update_pairs)
    update_pairs["stg_id"] = stg_id

    sql = f"""
        UPDATE ap_invoice_stg
        SET    {set_clause}, status = 'NEW'
        WHERE  stg_id = %(stg_id)s
          AND  status IN ('NEW','VALIDATED','ERROR')
    """
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, update_pairs)
            if cur.rowcount == 0:
                raise HTTPException(
                    status_code=409,
                    detail="Update gagal: record tidak ditemukan atau status tidak mengizinkan edit"
                )
        conn.commit()
    finally:
        conn.close()

    return {"message": "Staging updated", "stg_id": stg_id}


@router.get("/{stg_id}/request-status")
def get_request_status(stg_id: int):
    """Cek status concurrent request APXIIMPT dari Oracle (READ-ONLY)."""
    from services.oracle_request import check_request_status
    from services.ap_interface import check_import_result

    # Read staging from PostgreSQL
    pg = get_pg_connection()
    try:
        with pg.cursor() as cur:
            cur.execute("""
                SELECT conc_request_id, invoice_num, vendor_id, status, source_file
                FROM   ap_invoice_stg
                WHERE  stg_id = %s
            """, (stg_id,))
            row = cur.fetchone()
    finally:
        pg.close()

    if not row:
        raise HTTPException(status_code=404, detail="STG_ID tidak ditemukan")

    conc_req_id, invoice_num, vendor_id, stg_status, source_file = row
    result = {"stg_status": stg_status}

    # Read from Oracle (READ-ONLY)
    ora = get_oracle_connection()
    try:
        if conc_req_id:
            result["concurrent"] = check_request_status(ora, conc_req_id)

        if stg_status in ("INTERFACED", "SUBMITTED", "IMPORTED"):
            import_result = check_import_result(ora, invoice_num, vendor_id)
            result["import"] = import_result

            # Update status + attach PDF when IMPORTED
            if import_result["status"] == "IMPORTED" and stg_status != "IMPORTED":
                ap_inv_id = import_result["invoice_id"]

                # Attach PDF to invoice
                if source_file:
                    try:
                        from services.attachment import attach_pdf_to_invoice
                        from config import UPLOAD_DIR
                        import os
                        pdf_path = os.path.join(UPLOAD_DIR, source_file)
                        if os.path.exists(pdf_path):
                            attach_pdf_to_invoice(ora, ap_inv_id, pdf_path, source_file)
                            result["attachment"] = "PDF attached"
                    except Exception as e:
                        result["attachment_error"] = str(e)

                pg2 = get_pg_connection()
                try:
                    with pg2.cursor() as cur:
                        cur.execute("""
                            UPDATE ap_invoice_stg
                            SET    status = 'IMPORTED',
                                   ap_invoice_id = %s,
                                   processed_date = NOW()
                            WHERE  stg_id = %s
                        """, (ap_inv_id, stg_id))
                    pg2.commit()
                finally:
                    pg2.close()
                result["stg_status"] = "IMPORTED"
    finally:
        ora.close()

    return result
