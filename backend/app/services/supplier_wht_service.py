"""
Supplier WHT (Withholding Tax / PPh) Master Service
────────────────────────────────────────────────────
Answers "what PPh rate applies to this supplier?" — needed by AP
Autoinvoice to compute the WHT deduction shown before Total.

There's no automatic-withholding configuration anywhere in this Oracle
instance to read that from (AP_SUPPLIERS.AWT_GROUP_ID is null for every
supplier, and the seeded AP_AWT type/rate master tables the automatic
mechanism would use are empty) — but AP staff DO already record WHT
manually as its own invoice line (LINE_TYPE_LOOKUP_CODE = 'AWT',
5,426 real lines as of 2026-09-09, covering 456 distinct suppliers),
tagged with a real AWT_GROUP_ID (AP_AWT_GROUPS — populated, e.g. group
11023 = "PPh23-2%-104"). seed_from_oracle() reads that actual transaction
history — each supplier's most recently used AWT group — to build this
master, rather than a nonexistent configuration table.
"""

import psycopg2
import re
from datetime import datetime
from typing import Optional

from app.config import get_settings
from app.database import get_oracle_connection

settings = get_settings()


def _get_pg():
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {settings.database_url}")
    return psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                             user=m.group(1), password=m.group(2))


def ensure_table():
    try:
        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS supplier_wht_master (
                id              SERIAL PRIMARY KEY,
                vendor_id       BIGINT NOT NULL UNIQUE,
                vendor_name     VARCHAR(240),
                awt_group_id    BIGINT,
                awt_group_name  VARCHAR(240),
                tax_rate        NUMERIC,
                last_used_date  TIMESTAMP,
                source          VARCHAR(20) DEFAULT 'oracle' NOT NULL,
                updated_by      VARCHAR(100),
                created_at      TIMESTAMP DEFAULT NOW(),
                updated_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


def seed_from_oracle(updated_by: str = "oracle-sync") -> dict:
    """Upserts every supplier's most-recently-used AWT group/rate, read
    straight from their real AWT-type invoice lines. Only touches rows
    whose source is 'oracle' — a manual override (source='manual') is left
    alone even if that supplier also has Oracle history, since a human
    already made a deliberate call for them."""
    ora = get_oracle_connection()
    try:
        cur = ora.cursor()
        cur.execute("""
            SELECT vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date
            FROM (
                SELECT ai.vendor_id, aps.vendor_name, ail.awt_group_id, ag.name AS awt_group_name,
                       tr.tax_rate, ail.creation_date AS last_used_date,
                       ROW_NUMBER() OVER (PARTITION BY ai.vendor_id ORDER BY ail.creation_date DESC) AS rn
                FROM ap_invoice_lines_all ail
                JOIN ap_invoices_all ai ON ai.invoice_id = ail.invoice_id
                JOIN ap_suppliers aps ON aps.vendor_id = ai.vendor_id
                JOIN AP.AP_AWT_GROUPS ag ON ag.group_id = ail.awt_group_id
                LEFT JOIN AP.AP_AWT_GROUP_TAXES_ALL agt ON agt.group_id = ag.group_id AND agt.rank = 1
                LEFT JOIN AP.AP_AWT_TAX_RATES_ALL tr ON tr.tax_name = agt.tax_name
                WHERE ail.line_type_lookup_code = 'AWT'
            )
            WHERE rn = 1
        """)
        rows = cur.fetchall()
    finally:
        ora.close()

    pg = _get_pg()
    try:
        cur = pg.cursor()
        upserted = 0
        for vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date in rows:
            cur.execute("""
                INSERT INTO supplier_wht_master
                    (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate,
                     last_used_date, source, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'oracle', %s, NOW())
                ON CONFLICT (vendor_id) DO UPDATE SET
                    vendor_name = EXCLUDED.vendor_name,
                    awt_group_id = EXCLUDED.awt_group_id,
                    awt_group_name = EXCLUDED.awt_group_name,
                    tax_rate = EXCLUDED.tax_rate,
                    last_used_date = EXCLUDED.last_used_date,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                WHERE supplier_wht_master.source = 'oracle'
            """, (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date, updated_by))
            upserted += cur.rowcount
        pg.commit()
    finally:
        pg.close()

    return {"suppliers_found_in_oracle": len(rows), "upserted": upserted, "synced_at": datetime.utcnow().isoformat()}


def list_wht_master(search: Optional[str] = None) -> list[dict]:
    pg = _get_pg()
    try:
        cur = pg.cursor()
        sql = """
            SELECT id, vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate,
                   TO_CHAR(last_used_date, 'DD/MM/YYYY'), source, updated_by,
                   TO_CHAR(updated_at, 'DD/MM/YYYY HH24:MI')
            FROM supplier_wht_master
        """
        params = ()
        if search:
            sql += " WHERE vendor_name ILIKE %s OR awt_group_name ILIKE %s"
            params = (f"%{search}%", f"%{search}%")
        sql += " ORDER BY vendor_name"
        cur.execute(sql, params)
        cols = ["id", "vendor_id", "vendor_name", "awt_group_id", "awt_group_name", "tax_rate",
                "last_used_date", "source", "updated_by", "updated_at"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            if r["tax_rate"] is not None:
                r["tax_rate"] = float(r["tax_rate"])
        return rows
    finally:
        pg.close()


def upsert_wht_master(vendor_id: int, vendor_name: str, awt_group_name: str,
                       tax_rate: float, updated_by: str, awt_group_id: Optional[int] = None) -> dict:
    """Manual add/edit — source is always 'manual' here, so a later
    seed_from_oracle() run never silently overwrites a human's deliberate
    entry for this supplier."""
    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("""
            INSERT INTO supplier_wht_master
                (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, source, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'manual', %s, NOW())
            ON CONFLICT (vendor_id) DO UPDATE SET
                vendor_name = EXCLUDED.vendor_name,
                awt_group_id = EXCLUDED.awt_group_id,
                awt_group_name = EXCLUDED.awt_group_name,
                tax_rate = EXCLUDED.tax_rate,
                source = 'manual',
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING id
        """, (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, updated_by))
        new_id = cur.fetchone()[0]
        pg.commit()
        return {"id": new_id, "vendor_id": vendor_id}
    finally:
        pg.close()


def delete_wht_master(id_: int):
    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("DELETE FROM supplier_wht_master WHERE id = %s", (id_,))
        deleted = cur.rowcount
        pg.commit()
        return deleted
    finally:
        pg.close()


def get_wht_for_vendor(vendor_id: int) -> Optional[dict]:
    """Lookup used by AP Autoinvoice to auto-suggest a WHT rate for a
    matched vendor."""
    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("""
            SELECT vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate
            FROM supplier_wht_master WHERE vendor_id = %s
        """, (vendor_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "vendor_id": row[0], "vendor_name": row[1], "awt_group_id": row[2],
            "awt_group_name": row[3], "tax_rate": float(row[4]) if row[4] is not None else None,
        }
    finally:
        pg.close()
