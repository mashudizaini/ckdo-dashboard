"""
process.py — Step-by-step AP Invoice processing

Step 1: Upload & Extract (handled by upload.py)
Step 2: POST /process/validate/{stg_id}        → Cek vendor/PO di Oracle (READ, non-blocking)
Step 3: GET  /process/preview/{stg_id}          → Preview data interface mapping
Step 4: POST /process/insert-interface/{stg_id} → INSERT ke AP Interface tables (Oracle WRITE)
Step 5: POST /process/run-import/{stg_id}       → Submit APXIIMPT concurrent (Oracle WRITE)

Staging data: PostgreSQL
Oracle EBS: READ for validation, WRITE hanya step 4 & 5
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pg_config import get_pg_connection
from config import get_oracle_connection, EBS_ORG_ID, EBS_SOURCE, EBS_USER_ID
from services.validator import lookup_vendor, lookup_po, check_duplicate_invoice
from services.ap_interface import insert_ap_interface, _parse_date
from services.oracle_request import submit_apxiimpt

router = APIRouter(prefix="/process", tags=["Process"])


# ── Helper ────────────────────────────────────────────────────────

def _update_stg(stg_id: int, **fields):
    sets = [f"{k} = %({k})s" for k in fields]
    fields["stg_id"] = stg_id
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE ap_invoice_stg SET {', '.join(sets)} WHERE stg_id = %(stg_id)s", fields)
        conn.commit()
    finally:
        conn.close()


def _get_stg(stg_id: int, columns: list[str]) -> dict:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(columns)} FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="STG_ID tidak ditemukan")
    return dict(zip(columns, row))


# ── Step 2: Validate (non-blocking) ─────────────────────────────

@router.post("/validate/{stg_id}")
def validate_invoice(stg_id: int):
    """
    Cek vendor & PO di Oracle EBS (READ-ONLY).
    Hasilnya berupa info/warnings — TIDAK menghentikan proses.
    Status selalu lanjut ke VALIDATED.
    """
    stg = _get_stg(stg_id, ["vendor_name", "po_number", "invoice_num", "status"])

    if stg["status"] not in ("NEW", "ERROR"):
        raise HTTPException(status_code=409, detail=f"Status '{stg['status']}', hanya NEW/ERROR bisa divalidasi")

    warnings = []
    vendor_info = None

    ora = get_oracle_connection()
    try:
        # Lookup vendor
        try:
            vendor_info = lookup_vendor(ora, stg["vendor_name"], EBS_ORG_ID)
            ebs_name = vendor_info.get("vendor_name_ebs", "")
            if ebs_name and ebs_name.upper().strip() != stg["vendor_name"].upper().strip():
                warnings.append({
                    "type": "info",
                    "message": f"Vendor matched: '{stg['vendor_name']}' → '{ebs_name}' (ID: {vendor_info['vendor_id']})"
                })
        except ValueError as e:
            warnings.append({"type": "warning", "message": str(e)})

        # Lookup PO
        if stg["po_number"]:
            try:
                po_info = lookup_po(ora, stg["po_number"], EBS_ORG_ID)
                # PO ditemukan dan valid — tambahkan info
            except ValueError as e:
                warnings.append({"type": "info", "message": str(e)})

        # Cek duplicate invoice
        if vendor_info:
            dup_id = check_duplicate_invoice(ora, stg["invoice_num"], vendor_info["vendor_id"], EBS_ORG_ID)
            if dup_id:
                warnings.append({
                    "type": "warning",
                    "message": f"Invoice '{stg['invoice_num']}' sudah ada di EBS (Invoice ID: {dup_id})"
                })
    finally:
        ora.close()

    # Update staging — selalu lanjut ke VALIDATED
    update_fields = {"status": "VALIDATED", "error_msg": None}
    if vendor_info:
        update_fields["vendor_id"] = vendor_info["vendor_id"]
        update_fields["vendor_site_id"] = vendor_info["vendor_site_id"]
        update_fields["vendor_site_code"] = vendor_info["vendor_site_code"]

    _update_stg(stg_id, **update_fields)

    return {
        "stg_id": stg_id,
        "status": "VALIDATED",
        "vendor": vendor_info,
        "warnings": warnings,
        "message": "Validasi selesai." if not warnings else "Validasi selesai dengan catatan.",
    }


# ── Step 3: Preview Interface ────────────────────────────────────

@router.get("/preview/{stg_id}")
def preview_interface(stg_id: int):
    """Preview data yang akan di-INSERT ke AP Interface. Tidak insert apapun."""
    cols = [
        "invoice_num", "invoice_date", "vendor_name", "vendor_id",
        "vendor_site_id", "vendor_site_code",
        "invoice_amount", "currency_code", "po_number", "so_number",
        "terms_date", "lines_json", "status", "subtotal", "tax_amount",
        "payment_terms", "tax_serial_number",
    ]
    stg = _get_stg(stg_id, cols)

    if stg["status"] != "VALIDATED":
        raise HTTPException(status_code=409, detail=f"Status harus VALIDATED, saat ini: '{stg['status']}'")

    invoice_date = _parse_date(stg["invoice_date"])
    gl_date = datetime.today()
    try:
        terms_date = _parse_date(stg["terms_date"]) if stg.get("terms_date") else invoice_date
    except ValueError:
        terms_date = invoice_date

    lines = json.loads(stg["lines_json"]) if isinstance(stg["lines_json"], str) else (stg["lines_json"] or [])

    header = {
        "INVOICE_NUM":              str(stg["invoice_num"]),
        "INVOICE_TYPE_LOOKUP_CODE": "STANDARD",
        "INVOICE_DATE":             invoice_date.strftime("%d/%m/%Y"),
        "VENDOR_ID":                stg["vendor_id"],
        "VENDOR_SITE_ID":           stg["vendor_site_id"],
        "VENDOR_SITE_CODE":         stg.get("vendor_site_code"),
        "INVOICE_AMOUNT":           float(stg["invoice_amount"] or 0),
        "INVOICE_CURRENCY_CODE":    stg.get("currency_code", "IDR"),
        "TERMS_NAME":               stg.get("payment_terms") or "30 Days",
        "TERMS_DATE":               terms_date.strftime("%d/%m/%Y"),
        "GL_DATE":                  gl_date.strftime("%d/%m/%Y"),
        "SOURCE":                   EBS_SOURCE,
        "ORG_ID":                   EBS_ORG_ID,
        "PO_NUMBER":                stg.get("po_number"),
        "DESCRIPTION":              f"Import PDF: {stg['invoice_num']}",
        "SO_NUMBER":                stg.get("so_number"),
        "TAX_SERIAL_NUMBER":        stg.get("tax_serial_number"),
        "CREATED_BY":               EBS_USER_ID,
    }

    po_number = stg.get("po_number")

    line_rows = []
    for ln in lines:
        line_rows.append({
            "LINE_NUMBER":            ln["line_num"],
            "LINE_TYPE_LOOKUP_CODE":  "ITEM",
            "AMOUNT":                 float(ln.get("line_amount", 0)),
            "QUANTITY_INVOICED":      float(ln.get("qty", 1)),
            "UNIT_PRICE":             float(ln.get("unit_price", 0)),
            "DESCRIPTION":            ln.get("description", ""),
            "PO_NUMBER":              None,
            "PO_LINE_NUMBER":         None,
            "MATCH_OPTION":           None,
            "BATCH_NO":               ln.get("batch_no"),
            "ITEM_CODE":              ln.get("item_code"),
            "ORG_ID":                 EBS_ORG_ID,
        })

    return {
        "stg_id": stg_id,
        "po_number": po_number,
        "header": header,
        "lines":  line_rows,
    }


# ── Step 4: Insert ke Interface ──────────────────────────────────

@router.post("/insert-interface/{stg_id}")
def insert_interface(stg_id: int, payload: dict = None):
    """
    INSERT data ke AP_INVOICES_INTERFACE + AP_INVOICE_LINES_INTERFACE.
    Menerima payload yang sudah di-edit user dari preview form.
    """
    stg = _get_stg(stg_id, ["status"])

    if stg["status"] != "VALIDATED":
        raise HTTPException(status_code=409, detail=f"Status harus VALIDATED, saat ini: '{stg['status']}'")

    if not payload or "header" not in payload or "lines" not in payload:
        raise HTTPException(status_code=400, detail="Payload header dan lines diperlukan")

    h = payload["header"]

    # Build stg_data format yang dibutuhkan ap_interface.insert_ap_interface
    stg_data = {
        "stg_id":          stg_id,
        "invoice_num":     h.get("INVOICE_NUM"),
        "invoice_date":    h.get("INVOICE_DATE"),
        "vendor_id":       h.get("VENDOR_ID"),
        "vendor_site_id":  h.get("VENDOR_SITE_ID"),
        "invoice_amount":  float(h.get("INVOICE_AMOUNT", 0)),
        "currency_code":   h.get("INVOICE_CURRENCY_CODE", "IDR"),
        "TERMS_NAME":      h.get("TERMS_NAME", "30 Days"),
        "po_number":       h.get("PO_NUMBER"),
        "so_number":       h.get("SO_NUMBER"),
        "terms_date":      h.get("TERMS_DATE"),
        "lines_json":      json.dumps(payload["lines"]),
    }

    _update_stg(stg_id, status="PROCESSING", error_msg=None, processed_date=datetime.now().isoformat())

    try:
        ora = get_oracle_connection()
        try:
            interface_invoice_id = insert_ap_interface(ora, stg_data)
        finally:
            ora.close()

        _update_stg(stg_id, status="INTERFACED", interface_invoice_id=interface_invoice_id)

        return {
            "stg_id": stg_id,
            "status": "INTERFACED",
            "interface_invoice_id": interface_invoice_id,
            "message": f"Berhasil insert ke AP Interface (ID: {interface_invoice_id}).",
        }
    except Exception as e:
        _update_stg(stg_id, status="ERROR", error_msg=f"Insert interface gagal: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Insert interface gagal: {str(e)}")


# ── Step 5: Run APXIIMPT ─────────────────────────────────────────

@router.post("/run-import/{stg_id}")
def run_import(stg_id: int):
    """Submit concurrent program APXIIMPT di Oracle."""
    stg = _get_stg(stg_id, ["status", "interface_invoice_id"])

    if stg["status"] != "INTERFACED":
        raise HTTPException(status_code=409, detail=f"Status harus INTERFACED, saat ini: '{stg['status']}'")

    try:
        ora = get_oracle_connection()
        try:
            req_id = submit_apxiimpt(ora)
        finally:
            ora.close()

        _update_stg(stg_id, conc_request_id=req_id, status="SUBMITTED")

        return {
            "stg_id": stg_id,
            "status": "SUBMITTED",
            "conc_request_id": req_id,
            "message": f"APXIIMPT submitted (Request ID: {req_id}). Pantau status di Tracker.",
        }
    except Exception as e:
        _update_stg(stg_id, status="ERROR", error_msg=f"Run import gagal: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Run import gagal: {str(e)}")


# ── Step 6: Attach PDF ────────────────────────────────────────────

@router.post("/attach/{stg_id}")
def attach_pdf(stg_id: int):
    """Attach PDF file ke AP Invoice di EBS. Auto-lookup ap_invoice_id jika belum ada."""
    import os
    from services.attachment import attach_pdf_to_invoice
    from services.ap_interface import check_import_result

    stg = _get_stg(stg_id, ["ap_invoice_id", "invoice_num", "vendor_id", "source_file", "status"])

    ap_invoice_id = stg.get("ap_invoice_id")

    # Auto-lookup dari Oracle jika belum ada
    if not ap_invoice_id:
        ora = get_oracle_connection()
        try:
            result = check_import_result(ora, stg["invoice_num"], stg.get("vendor_id"))
            if result["status"] == "IMPORTED":
                ap_invoice_id = result["invoice_id"]
                _update_stg(stg_id, ap_invoice_id=ap_invoice_id, status="IMPORTED")
        finally:
            ora.close()

    if not ap_invoice_id:
        raise HTTPException(
            status_code=409,
            detail=f"Invoice '{stg['invoice_num']}' belum ditemukan di ap_invoices_all. Pastikan APXIIMPT sudah selesai dan invoice berhasil di-import."
        )

    if not stg.get("source_file"):
        raise HTTPException(status_code=400, detail="Tidak ada source file untuk di-attach")

    pdf_path = os.path.join(os.getenv("UPLOAD_DIR", "./uploads"), stg["source_file"])
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"File tidak ditemukan: {stg['source_file']}")

    try:
        ora = get_oracle_connection()
        try:
            attach_pdf_to_invoice(ora, ap_invoice_id, pdf_path, stg["source_file"])
        finally:
            ora.close()

        return {
            "stg_id": stg_id,
            "ap_invoice_id": ap_invoice_id,
            "message": f"PDF berhasil di-attach ke Invoice ID {ap_invoice_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Attach gagal: {str(e)}")
