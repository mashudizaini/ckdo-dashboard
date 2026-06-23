"""
upload.py — POST /upload
Terima file PDF, extract, simpan ke staging table.
"""

import os
import json
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.config import get_connection, UPLOAD_DIR
from services.pdf_extractor import extract_invoice

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/")
async def upload_invoice(file: UploadFile = File(...)):
    """
    Upload PDF invoice supplier → extract → insert ke XXCKD_AP_INVOICE_STG.
    Return: stg_id dan preview data hasil extract.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File harus berformat PDF")

    # Simpan file PDF ke disk
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract dari PDF
    try:
        invoice = extract_invoice(file_path, file.filename)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Gagal extract PDF: {str(e)}")

    # Insert ke staging
    sql = """
        INSERT INTO XXCKD_AP_INVOICE_STG (
            STG_ID, STATUS, SOURCE_FILE,
            INVOICE_NUM, INVOICE_DATE, VENDOR_NAME,
            TERMS_DATE, PO_NUMBER, SO_NUMBER,
            CURRENCY_CODE, INVOICE_AMOUNT, SUBTOTAL, TAX_AMOUNT,
            LINES_JSON, CREATED_DATE
        ) VALUES (
            XXCKD_AP_INVOICE_STG_S.NEXTVAL, 'NEW', :source_file,
            :invoice_num, :invoice_date, :vendor_name,
            :terms_date, :po_number, :so_number,
            :currency_code, :invoice_amount, :subtotal, :tax_amount,
            :lines_json, SYSDATE
        ) RETURNING STG_ID INTO :stg_id
    """
    lines_json = json.dumps([l.model_dump() for l in invoice.lines])

    conn = get_connection()
    try:
        stg_id_var = conn.cursor().var(int)
        with conn.cursor() as cur:
            cur.execute(sql, {
                "source_file":    invoice.source_file,
                "invoice_num":    invoice.invoice_num,
                "invoice_date":   invoice.invoice_date,
                "vendor_name":    invoice.vendor_name,
                "terms_date":     invoice.terms_date,
                "po_number":      invoice.po_number,
                "so_number":      invoice.so_number,
                "currency_code":  invoice.currency_code,
                "invoice_amount": invoice.invoice_amount,
                "subtotal":       invoice.subtotal,
                "tax_amount":     invoice.tax_amount,
                "lines_json":     lines_json,
                "stg_id":         stg_id_var,
            })
        conn.commit()
        stg_id = stg_id_var.getvalue()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal insert staging: {str(e)}")
    finally:
        conn.close()

    return {
        "stg_id":   stg_id,
        "status":   "NEW",
        "preview":  invoice.model_dump(),
        "message":  "PDF berhasil di-extract. Silakan review sebelum submit.",
    }
