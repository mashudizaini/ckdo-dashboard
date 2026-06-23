"""
validator.py
Lookup vendor_id, vendor_site_id, dan validasi PO di EBS sebelum interface.
"""

import oracledb
from typing import Optional


def _clean_vendor_name(name: str) -> str:
    """Hapus prefix PT./CV./UD. dan karakter non-alfanumerik untuk fuzzy match."""
    import re
    name = name.upper().strip()
    name = re.sub(r'^(PT\.?|CV\.?|UD\.?|TB\.?)\s*', '', name)
    name = name.strip('. ')
    return name


def lookup_vendor(conn: oracledb.Connection, vendor_name: str, org_id: int) -> dict:
    """
    Cari VENDOR_ID dari AP_SUPPLIERS + AP_SUPPLIER_SITES_ALL.
    Strategi: exact match dulu, lalu LIKE fallback.
    Return dict: {vendor_id, vendor_site_id, vendor_site_code, vendor_name_ebs}
    """
    base_sql = """
        SELECT s.vendor_id,
               ss.vendor_site_id,
               ss.vendor_site_code,
               s.vendor_name
        FROM   ap_suppliers            s
        JOIN   ap_supplier_sites_all   ss ON ss.vendor_id = s.vendor_id
                                         AND ss.org_id    = :org_id
        WHERE  {where_clause}
          AND  ss.inactive_date IS NULL
          AND  NVL(s.end_date_active, SYSDATE+1) > SYSDATE
        ORDER BY ss.primary_pay_site_flag DESC NULLS LAST,
                 ss.vendor_site_id ASC
        FETCH FIRST 1 ROWS ONLY
    """

    # 1. Exact match
    sql = base_sql.format(where_clause="UPPER(TRIM(s.vendor_name)) = UPPER(TRIM(:vendor_name))")
    with conn.cursor() as cur:
        cur.execute(sql, {"org_id": org_id, "vendor_name": vendor_name})
        row = cur.fetchone()

    # 2. LIKE match — cari keyword utama dari nama vendor
    if not row:
        clean = _clean_vendor_name(vendor_name)
        keywords = [w for w in clean.split() if len(w) >= 3]
        if keywords:
            like_pattern = '%' + '%'.join(keywords) + '%'
            sql = base_sql.format(where_clause="UPPER(s.vendor_name) LIKE :pattern")
            with conn.cursor() as cur:
                cur.execute(sql, {"org_id": org_id, "pattern": like_pattern})
                row = cur.fetchone()

    # 3. Partial LIKE — pakai keyword terpanjang saja
    if not row and keywords:
        longest = max(keywords, key=len)
        like_pattern = '%' + longest + '%'
        sql = base_sql.format(where_clause="UPPER(s.vendor_name) LIKE :pattern")
        with conn.cursor() as cur:
            cur.execute(sql, {"org_id": org_id, "pattern": like_pattern})
            row = cur.fetchone()

    if not row:
        raise ValueError(f"Vendor '{vendor_name}' tidak ditemukan di EBS")

    return {
        "vendor_id":        row[0],
        "vendor_site_id":   row[1],
        "vendor_site_code": row[2],
        "vendor_name_ebs":  row[3],
    }


def lookup_po(conn: oracledb.Connection, po_number: str, org_id: int) -> dict:
    """
    Cari PO_HEADER_ID dan validasi PO masih open.
    Return dict: {po_header_id, po_status} atau raise jika tidak ketemu.
    """
    sql = """
        SELECT po_header_id,
               authorization_status,
               closed_code,
               segment1
        FROM   po_headers_all
        WHERE  segment1 = :po_number
          AND  org_id   = :org_id
        FETCH FIRST 1 ROWS ONLY
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"po_number": po_number, "org_id": org_id})
        row = cur.fetchone()

    if not row:
        raise ValueError(f"PO Number '{po_number}' tidak ditemukan di EBS")

    po_header_id, auth_status, closed_code, segment1 = row

    if auth_status != "APPROVED":
        raise ValueError(f"PO {segment1} belum di-approve (status: {auth_status})")
    if closed_code in ("CLOSED", "FINALLY CLOSED"):
        raise ValueError(f"PO {segment1} sudah ditutup ({closed_code})")

    return {
        "po_header_id": po_header_id,
        "po_status":    auth_status,
    }


def check_duplicate_invoice(conn: oracledb.Connection,
                             invoice_num: str,
                             vendor_id: int,
                             org_id: int) -> Optional[int]:
    """
    Cek apakah invoice_num + vendor_id sudah ada di ap_invoices_all.
    Return invoice_id jika duplicate, None jika aman.
    """
    sql = """
        SELECT invoice_id
        FROM   ap_invoices_all
        WHERE  invoice_num = :invoice_num
          AND  vendor_id   = :vendor_id
          AND  org_id      = :org_id
          AND  cancelled_date IS NULL
        FETCH FIRST 1 ROWS ONLY
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "invoice_num": invoice_num,
            "vendor_id":   vendor_id,
            "org_id":      org_id,
        })
        row = cur.fetchone()

    return row[0] if row else None
