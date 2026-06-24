"""
AP Auto Invoice Router
Route prefix: /api/v1/dashboard/accounting/ap-invoice
"""

import os
import shutil
import json
import psycopg2
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import get_settings
from app.database import get_oracle_connection
from app.services import ap_invoice_service as svc

router = APIRouter()
settings = get_settings()


def _get_pg():
    url = settings.database_url
    import re
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {url}")
    return psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                            user=m.group(1), password=m.group(2))


def ensure_staging_table():
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ap_invoice_stg (
                stg_id              SERIAL PRIMARY KEY,
                status              VARCHAR(20) DEFAULT 'NEW' NOT NULL,
                error_msg           TEXT,
                source_file         VARCHAR(500) NOT NULL,
                created_date        TIMESTAMP DEFAULT NOW(),
                processed_date      TIMESTAMP,
                invoice_num         VARCHAR(50) NOT NULL,
                invoice_date        VARCHAR(20),
                vendor_name         VARCHAR(240),
                vendor_id           BIGINT,
                vendor_site_id      BIGINT,
                vendor_site_code    VARCHAR(50),
                payment_terms       VARCHAR(50),
                terms_date          VARCHAR(20),
                po_number           VARCHAR(50),
                so_number           VARCHAR(50),
                currency_code       VARCHAR(15) DEFAULT 'IDR',
                invoice_amount      NUMERIC,
                subtotal            NUMERIC,
                tax_amount          NUMERIC,
                tax_serial_number   VARCHAR(100),
                lines_json          TEXT,
                interface_invoice_id BIGINT,
                ap_invoice_id       BIGINT,
                conc_request_id     BIGINT
            )
        """)
        # Migrate existing table: INTEGER → BIGINT
        for col in ('vendor_id', 'vendor_site_id', 'interface_invoice_id', 'ap_invoice_id', 'conc_request_id'):
            try:
                cur.execute(f"ALTER TABLE ap_invoice_stg ALTER COLUMN {col} TYPE BIGINT")
            except Exception:
                conn.rollback()
        conn.commit()
        conn.close()
    except Exception:
        pass


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "File harus berformat PDF")

    file_path = os.path.join(svc.UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        invoice_data = svc.extract_pdf(file_path, file.filename)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(422, f"Gagal extract PDF: {str(e)}")

    if not invoice_data.get("invoice_num"):
        os.remove(file_path)
        raise HTTPException(422, "Invoice Number tidak ditemukan dalam PDF")

    conn = _get_pg()
    try:
        stg_id = svc.save_to_staging(conn, invoice_data)
    except Exception as e:
        conn.close()
        raise HTTPException(500, f"Gagal simpan ke staging: {str(e)}")
    conn.close()

    return {"stg_id": stg_id, "status": "NEW", "preview": invoice_data}


@router.get("/invoices")
async def get_invoices():
    conn = _get_pg()
    try:
        result = svc.list_invoices(conn)
    finally:
        conn.close()
    return result


@router.get("/invoices/{stg_id}")
async def get_invoice(stg_id: int):
    conn = _get_pg()
    try:
        result = svc.get_invoice_detail(conn, stg_id)
    finally:
        conn.close()
    if not result:
        raise HTTPException(404, "Invoice tidak ditemukan")
    return result


@router.post("/validate/{stg_id}")
async def validate(stg_id: int):
    pg = _get_pg()
    ora = get_oracle_connection()
    try:
        result = svc.validate_invoice(pg, ora, stg_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    finally:
        ora.close()
        pg.close()
    return result


@router.post("/insert-interface/{stg_id}")
async def insert_interface(stg_id: int, payload: dict):
    if "header" not in payload or "lines" not in payload:
        raise HTTPException(400, "Payload header dan lines diperlukan")

    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("SELECT status FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "STG_ID tidak ditemukan")
        if row[0] not in ("VALIDATED", "PROCESSING", "ERROR"):
            raise HTTPException(409, f"Status harus VALIDATED, saat ini: '{row[0]}'")

        cur.execute("UPDATE ap_invoice_stg SET status = 'PROCESSING', error_msg = NULL, processed_date = NOW() WHERE stg_id = %s", (stg_id,))
        pg.commit()
    except HTTPException:
        pg.close()
        raise
    except Exception as e:
        pg.close()
        raise HTTPException(500, str(e))

    ora = None
    try:
        ora = get_oracle_connection()
        result = svc.insert_to_interface(pg, ora, stg_id, payload["header"], payload["lines"])
        return result
    except Exception as e:
        try:
            pg2 = _get_pg()
            pg2.cursor().execute("UPDATE ap_invoice_stg SET status = 'ERROR', error_msg = %s WHERE stg_id = %s",
                                 (f"Insert interface gagal: {str(e)}", stg_id))
            pg2.commit()
            pg2.close()
        except Exception:
            pass
        raise HTTPException(500, f"Insert interface gagal: {str(e)}")
    finally:
        if ora:
            ora.close()
        pg.close()


@router.post("/run-import/{stg_id}")
async def run_import(stg_id: int):
    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("SELECT status FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "STG_ID tidak ditemukan")
        if row[0] not in ("INTERFACED", "ERROR"):
            raise HTTPException(409, f"Status harus INTERFACED, saat ini: '{row[0]}'")
    except HTTPException:
        pg.close()
        raise

    ora = None
    try:
        ora = get_oracle_connection()
        result = svc.run_apxiimpt(pg, ora, stg_id)
        return result
    except Exception as e:
        try:
            pg2 = _get_pg()
            pg2.cursor().execute("UPDATE ap_invoice_stg SET status = 'ERROR', error_msg = %s WHERE stg_id = %s",
                                 (f"Run import gagal: {str(e)}", stg_id))
            pg2.commit()
            pg2.close()
        except Exception:
            pass
        raise HTTPException(500, f"Run import gagal: {str(e)}")
    finally:
        if ora:
            ora.close()
        pg.close()


@router.put("/invoices/{stg_id}")
async def update_invoice(stg_id: int, payload: dict):
    allowed = {"invoice_num", "invoice_date", "vendor_name", "terms_date",
               "po_number", "so_number", "currency_code", "invoice_amount",
               "subtotal", "tax_amount", "lines_json"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Tidak ada field valid untuk diupdate")

    pg = _get_pg()
    cur = pg.cursor()
    sets = ", ".join(f"{k} = %({k})s" for k in updates)
    updates["stg_id"] = stg_id
    cur.execute(f"UPDATE ap_invoice_stg SET {sets}, status = 'NEW' WHERE stg_id = %(stg_id)s AND status IN ('NEW','VALIDATED','ERROR')", updates)
    if cur.rowcount == 0:
        pg.close()
        raise HTTPException(409, "Update gagal: record tidak ditemukan atau status tidak mengizinkan edit")
    pg.commit()
    pg.close()
    return {"message": "Updated", "stg_id": stg_id}


@router.delete("/invoices/{stg_id}")
async def delete_invoice(stg_id: int):
    pg = _get_pg()
    cur = pg.cursor()
    cur.execute("SELECT status, source_file FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
    row = cur.fetchone()
    if not row:
        pg.close()
        raise HTTPException(404, "Invoice tidak ditemukan")
    if row[0] not in ("NEW", "VALIDATED", "ERROR"):
        pg.close()
        raise HTTPException(409, f"Tidak bisa dihapus, status: '{row[0]}'")

    cur.execute("DELETE FROM ap_invoice_stg WHERE stg_id = %s", (stg_id,))
    pg.commit()
    pg.close()

    if row[1]:
        filepath = os.path.join(svc.UPLOAD_DIR, row[1])
        if os.path.exists(filepath):
            os.remove(filepath)

    return {"message": "Deleted", "stg_id": stg_id}
