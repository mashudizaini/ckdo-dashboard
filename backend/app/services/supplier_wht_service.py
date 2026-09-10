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
        # is_active — some suppliers have more than one Oracle vendor_id for
        # what's really the same company (duplicate/legacy registrations).
        # Each still gets its own row here (AP Autoinvoice looks WHT up by
        # the exact vendor_id an invoice matched to), but only one per
        # duplicate group is flagged active by default — see
        # seed_from_oracle()'s dedup/tie-break logic.
        try:
            cur.execute("ALTER TABLE supplier_wht_master ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL")
        except Exception:
            conn.rollback()
        conn.commit()
        conn.close()
    except Exception:
        pass


def seed_from_oracle(updated_by: str = "oracle-sync") -> dict:
    """Upserts every supplier's most-recently-used AWT group/rate, read
    straight from their real AWT-type invoice lines. Only touches rows
    whose source is 'oracle' — a manual override (source='manual') is left
    alone even if that supplier also has Oracle history, since a human
    already made a deliberate call for them.

    Excludes vendor_type_lookup_code='EMPLOYEE' — Oracle's own
    classification for employees registered as AP suppliers (expense
    reimbursements etc.), i.e. internal, not a commercial supplier subject
    to the same PPh-on-purchase withholding this master tracks.

    Some real suppliers have more than one Oracle vendor_id (duplicate or
    legacy registrations under the same company name). Two rules handle
    that: if the duplicates' PPh group + rate are identical, they're pure
    noise — keep just one (the most recently used). If they genuinely
    differ, keep a row per vendor_id (AP Autoinvoice looks WHT up by the
    exact vendor_id an invoice matched to) but flag only one — the most
    recently used — as is_active, so the master's own list shows a single
    clear default per supplier name rather than looking like unresolved
    duplicates."""
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
                  AND (aps.vendor_type_lookup_code IS NULL OR aps.vendor_type_lookup_code <> 'EMPLOYEE')
            )
            WHERE rn = 1
        """)
        rows = cur.fetchall()

        cur.execute("SELECT vendor_id FROM ap_suppliers WHERE vendor_type_lookup_code = 'EMPLOYEE'")
        employee_vendor_ids = [r[0] for r in cur.fetchall()]
    finally:
        ora.close()

    # Group by normalized supplier name to find duplicate vendor_id registrations.
    by_name = {}
    for vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date in rows:
        key = (vendor_name or "").strip().upper()
        by_name.setdefault(key, []).append({
            "vendor_id": vendor_id, "vendor_name": vendor_name,
            "awt_group_id": awt_group_id, "awt_group_name": awt_group_name,
            "tax_rate": tax_rate, "last_used_date": last_used_date,
        })

    to_upsert = []       # (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date, is_active)
    collapsed_vendor_ids = []  # duplicate vendor_ids whose row we deliberately did NOT keep
    for entries in by_name.values():
        entries.sort(key=lambda e: e["last_used_date"] or datetime.min, reverse=True)
        deduped = []
        seen_group_rate = set()
        for e in entries:
            gr_key = (e["awt_group_id"], float(e["tax_rate"]) if e["tax_rate"] is not None else None)
            if gr_key in seen_group_rate:
                collapsed_vendor_ids.append(e["vendor_id"])  # same group+rate as one already kept — redundant
                continue
            seen_group_rate.add(gr_key)
            deduped.append(e)
        for i, e in enumerate(deduped):
            to_upsert.append((
                e["vendor_id"], e["vendor_name"], e["awt_group_id"], e["awt_group_name"],
                e["tax_rate"], e["last_used_date"], i == 0,
            ))

    pg = _get_pg()
    try:
        cur = pg.cursor()
        upserted = 0
        for vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date, is_active in to_upsert:
            cur.execute("""
                INSERT INTO supplier_wht_master
                    (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate,
                     last_used_date, source, updated_by, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'oracle', %s, %s, NOW())
                ON CONFLICT (vendor_id) DO UPDATE SET
                    vendor_name = EXCLUDED.vendor_name,
                    awt_group_id = EXCLUDED.awt_group_id,
                    awt_group_name = EXCLUDED.awt_group_name,
                    tax_rate = EXCLUDED.tax_rate,
                    last_used_date = EXCLUDED.last_used_date,
                    updated_by = EXCLUDED.updated_by,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
                WHERE supplier_wht_master.source = 'oracle'
            """, (vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate, last_used_date, updated_by, is_active))
            upserted += cur.rowcount

        removed_employees = 0
        if employee_vendor_ids:
            cur.execute("""
                DELETE FROM supplier_wht_master
                WHERE source = 'oracle' AND vendor_id = ANY(%s)
            """, (employee_vendor_ids,))
            removed_employees = cur.rowcount

        removed_duplicates = 0
        if collapsed_vendor_ids:
            cur.execute("""
                DELETE FROM supplier_wht_master
                WHERE source = 'oracle' AND vendor_id = ANY(%s)
            """, (collapsed_vendor_ids,))
            removed_duplicates = cur.rowcount
        pg.commit()
    finally:
        pg.close()

    return {
        "suppliers_found_in_oracle": len(rows), "upserted": upserted,
        "internal_employee_suppliers_excluded": removed_employees,
        "duplicate_entries_collapsed": removed_duplicates,
        "synced_at": datetime.utcnow().isoformat(),
    }


def list_wht_master(search: Optional[str] = None) -> list[dict]:
    pg = _get_pg()
    try:
        cur = pg.cursor()
        sql = """
            SELECT id, vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate,
                   TO_CHAR(last_used_date, 'DD/MM/YYYY'), source, updated_by,
                   TO_CHAR(updated_at, 'DD/MM/YYYY HH24:MI'), is_active
            FROM supplier_wht_master
        """
        params = ()
        if search:
            sql += " WHERE vendor_name ILIKE %s OR awt_group_name ILIKE %s"
            params = (f"%{search}%", f"%{search}%")
        sql += " ORDER BY vendor_name, is_active DESC"
        cur.execute(sql, params)
        cols = ["id", "vendor_id", "vendor_name", "awt_group_id", "awt_group_name", "tax_rate",
                "last_used_date", "source", "updated_by", "updated_at", "is_active"]
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


def set_active(id_: int, is_active: bool) -> dict:
    """Manually flip which of a duplicate-supplier group's rows is the
    active one — e.g. an admin overriding seed_from_oracle()'s
    most-recently-used tie-break."""
    pg = _get_pg()
    try:
        cur = pg.cursor()
        cur.execute("UPDATE supplier_wht_master SET is_active = %s, updated_at = NOW() WHERE id = %s", (is_active, id_))
        updated = cur.rowcount
        pg.commit()
        return {"id": id_, "is_active": is_active, "updated": updated}
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


_LEGAL_ENTITY_TOKENS = re.compile(r"\b(PT|CV|TBK|PERSERO|LTD|INC|CORP|LLC|CO)\b")
_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def _normalize_company_name(name: Optional[str]) -> str:
    """Strips legal-entity suffixes/prefixes (PT, CV, Tbk, ...) and all
    punctuation/whitespace/case so "GOLD GRAFIKA INDONESIA" and "GOLD
    GRAFIKA INDONESIA, PT" (or "PT GOLD GRAFIKA INDONESIA") normalize to
    the same string, regardless of comma/word-order convention."""
    if not name:
        return ""
    s = _LEGAL_ENTITY_TOKENS.sub(" ", name.upper())
    return _NON_ALNUM.sub("", s)


def get_wht_for_vendor(vendor_id: Optional[int], vendor_name: Optional[str] = None) -> Optional[dict]:
    """Lookup used by AP Autoinvoice to auto-suggest a WHT rate for a
    matched vendor. Tries the exact vendor_id first (the normal case,
    once Validate has resolved the invoice's real Oracle vendor_id) —
    but an invoice not yet Validated has no vendor_id at all, and even a
    validated one can carry a differently-registered vendor_id than
    whichever one seed_from_oracle() happened to pick for the master (see
    is_active — duplicate registrations under the same company name are a
    known real case). Either way, fall back to matching on the OCR'd
    vendor_name itself, tolerant of "PT" placement/punctuation, restricted
    to is_active rows so a stale duplicate is never silently preferred."""
    pg = _get_pg()
    try:
        cur = pg.cursor()
        if vendor_id:
            cur.execute("""
                SELECT vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate
                FROM supplier_wht_master WHERE vendor_id = %s
            """, (vendor_id,))
            row = cur.fetchone()
            if row:
                return {
                    "vendor_id": row[0], "vendor_name": row[1], "awt_group_id": row[2],
                    "awt_group_name": row[3], "tax_rate": float(row[4]) if row[4] is not None else None,
                }

        if vendor_name:
            target = _normalize_company_name(vendor_name)
            if target:
                cur.execute("""
                    SELECT vendor_id, vendor_name, awt_group_id, awt_group_name, tax_rate
                    FROM supplier_wht_master WHERE is_active = TRUE
                """)
                for row in cur.fetchall():
                    if _normalize_company_name(row[1]) == target:
                        return {
                            "vendor_id": row[0], "vendor_name": row[1], "awt_group_id": row[2],
                            "awt_group_name": row[3], "tax_rate": float(row[4]) if row[4] is not None else None,
                        }
        return None
    finally:
        pg.close()
