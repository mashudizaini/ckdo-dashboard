"""
upload.py — POST /upload
Terima file PDF, extract via Claude Vision, simpan ke PostgreSQL staging.
"""

import os
import json
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from config import UPLOAD_DIR
from pg_config import get_pg_connection
from services.pdf_extractor import extract_invoice

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/")
async def upload_invoice(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File harus berformat PDF")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        invoice = extract_invoice(file_path, file.filename)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Gagal extract PDF: {str(e)}")

    lines_json = json.dumps([l.model_dump() for l in invoice.lines])

    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ap_invoice_stg (
                    status, source_file,
                    invoice_num, invoice_date, vendor_name,
                    payment_terms, tax_serial_number, terms_date, po_number, so_number,
                    currency_code, invoice_amount, subtotal, tax_amount,
                    lines_json, created_date
                ) VALUES (
                    'NEW', %(source_file)s,
                    %(invoice_num)s, %(invoice_date)s, %(vendor_name)s,
                    %(payment_terms)s, %(tax_serial_number)s, %(terms_date)s, %(po_number)s, %(so_number)s,
                    %(currency_code)s, %(invoice_amount)s, %(subtotal)s, %(tax_amount)s,
                    %(lines_json)s, NOW()
                ) RETURNING stg_id
            """, {
                "source_file":    invoice.source_file,
                "invoice_num":    invoice.invoice_num,
                "invoice_date":   invoice.invoice_date,
                "vendor_name":    invoice.vendor_name,
                "payment_terms":  invoice.payment_terms,
                "tax_serial_number": invoice.tax_serial_number,
                "terms_date":     invoice.terms_date,
                "po_number":      invoice.po_number,
                "so_number":      invoice.so_number,
                "currency_code":  invoice.currency_code,
                "invoice_amount": invoice.invoice_amount,
                "subtotal":       invoice.subtotal,
                "tax_amount":     invoice.tax_amount,
                "lines_json":     lines_json,
            })
            stg_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal insert staging: {str(e)}")
    finally:
        conn.close()

    return JSONResponse(content={
        "stg_id":  stg_id,
        "status":  "NEW",
        "preview": invoice.model_dump(),
        "message": "PDF berhasil di-extract. Silakan review sebelum submit.",
    })
