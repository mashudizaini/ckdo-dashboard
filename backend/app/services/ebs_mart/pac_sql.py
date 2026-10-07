"""
PAC Business Plan as a mart — the plan side of "plan vs actual".

Unlike every other mart this one is not extracted from Oracle: PAC's yearly
"<year> Business plan.xlsx" is read by business_plan_kb.workbook_figures
(the same parser that feeds the Knowledge Base text, so text and numbers
agree) and loaded by scripts/ingest_business_plan.py into
core.pac_bp_figure, one row per value cell. Re-importing a year replaces
that year. The import is logged in eis.etl_job_log as job
import_business_plan, so as_of on every answer says when the workbook was
last loaded.

Why its own table and not the PAC module's sales_plans / opex_plans / …:
those hold the dashboard's input forms (JSONB per team, draft/final) for
the next plan being written; the approved workbook is a different, finished
document, and loading it there would overwrite what teams are typing.

Access: business plan figures (P&L, margins, COGS) are confidential to PAC.
The mart is marked explicit_grant in constants.MARTS, so the management
role's all_access does not reach it — a role must be granted it in the
matrix (Setup > AI > EBS Chat Access). Role ebs-pac is seeded with full
access to it and to invoiced sales (PAC_SEED_GRANTS).
"""

PAC_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS core.pac_bp_figure (
        row_key        text PRIMARY KEY,
        plan_year      int  NOT NULL,
        sheet_name     text NOT NULL,
        sheet_title    text,
        section        text,
        row_no         int,
        col_no         int,
        line_path      text,
        line_label     text,
        line_level     int,
        column_header  text,
        unit           text,
        period_type    text,
        period_year    int,
        period_month   int,
        period_quarter int,
        scenario       text,
        measure        text,
        amount_in_unit numeric,
        amount_idr     numeric,
        quantity       numeric,
        pct            numeric,
        keterangan     text,
        source_file    text,
        loaded_at      timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_pac_bp_figure_year ON core.pac_bp_figure (plan_year)",
]

PAC_MART_SQL: dict[str, str] = {
    "pac_business_plan": """
        SELECT row_key, plan_year, section, sheet_title, sheet_name,
               line_path, line_label, line_level, column_header, unit,
               period_type, period_year, period_month, period_quarter,
               CASE WHEN period_type = 'month' THEN make_date(period_year, period_month, 1) END AS period_start_date,
               -- Whole rupiah: "mil Rp" x 1e6 carries spreadsheet decimals
               -- (200,343.25282157 -> 200343252821.57), which a model then
               -- formats with the decimals read as more digits.
               scenario, measure, ROUND(amount_idr) AS amount_idr, amount_in_unit, quantity,
               ROUND(pct, 2) AS pct, keterangan,
               row_no, col_no, source_file, loaded_at
          FROM core.pac_bp_figure
    """,
}

PAC_UNIQUE_INDEX: dict[str, list[str]] = {
    "pac_business_plan": ["row_key"],
}

PAC_EXTRA_INDEXES: dict[str, list[str]] = {
    "pac_business_plan": ["plan_year", "section", "period_start_date"],
}

IMPORT_JOB = "import_business_plan"

PAC_MARTS_BY_JOB: dict[str, list[str]] = {
    IMPORT_JOB: ["pac_business_plan"],
}

# Seeded once; an admin may change or remove the grants afterwards and a
# restart will not put them back (the grants are only inserted when the role
# itself is new). Invoiced sales come with it because the point of the
# figures is plan vs actual (pac_get_sales_plan_vs_actual reads both).
PAC_SEED_GRANTS = ("pac_business_plan", "sales_by_customer_item_month")
PAC_ROLE = "ebs-pac"
PAC_ROLE_LABEL = "PAC — Business Plan (rencana P&L, sales, COGS, produksi, pembelian, investasi, personel, cashflow)"


def seed_pac_role(cur):
    cur.execute(
        """INSERT INTO meta.access_role (role_code, label, all_access, updated_by)
           VALUES (%s, %s, false, 'seed') ON CONFLICT (role_code) DO NOTHING RETURNING role_code""",
        (PAC_ROLE, PAC_ROLE_LABEL),
    )
    if cur.fetchone():
        for mart in PAC_SEED_GRANTS:
            cur.execute(
                """INSERT INTO meta.access_grant (role_code, mart_name, level, updated_by)
                   VALUES (%s, %s, 'full', 'seed') ON CONFLICT DO NOTHING""",
                (PAC_ROLE, mart),
            )


_COLUMNS = ("row_key", "plan_year", "sheet_name", "sheet_title", "section", "row_no", "col_no", "line_path",
            "line_label", "line_level", "column_header", "unit", "period_type", "period_year", "period_month",
            "period_quarter", "scenario", "measure", "amount_in_unit", "amount_idr", "quantity", "pct",
            "keterangan", "source_file")


def load_year(year: int, figures: list[dict], source_file: str, triggered_by: str) -> dict:
    """Replace one plan year in core.pac_bp_figure, refresh the mart, and
    log the run as IMPORT_JOB (as_of for every answer from this mart).
    One transaction for the replace: a failed load leaves the previous
    import of that year in place."""
    import json

    from psycopg2.extras import execute_values

    from app.services.ebs_mart.query import _rw
    from app.services.ebs_mart.schema import refresh_marts

    conn = _rw()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO eis.etl_job_log (job_name, status, run_params, trigger_type, triggered_by)
               VALUES (%s, 'running', %s, 'manual', %s) RETURNING id""",
            (IMPORT_JOB, json.dumps({"year": year, "file": source_file}), triggered_by),
        )
        log_id = cur.fetchone()[0]
        conn.commit()
        try:
            cur.execute("DELETE FROM core.pac_bp_figure WHERE plan_year = %s", (year,))
            deleted = cur.rowcount
            rows = []
            for f in figures:
                key = f"{year}|{f['sheet_name']}|{f['row_no']}|{f['col_no']}"
                rows.append(tuple(key if c == "row_key" else source_file if c == "source_file" else f.get(c)
                                  for c in _COLUMNS))
            execute_values(cur, f"INSERT INTO core.pac_bp_figure ({', '.join(_COLUMNS)}) VALUES %s", rows,
                           page_size=2000)
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.execute("UPDATE eis.etl_job_log SET status = 'failed', finished_at = NOW(), error_message = %s "
                        "WHERE id = %s", (str(e)[:2000], log_id))
            conn.commit()
            raise
        refreshed = refresh_marts(PAC_MARTS_BY_JOB[IMPORT_JOB])
        ok = all(v == "ok" for v in refreshed.values())
        cur.execute(
            """UPDATE eis.etl_job_log SET status = %s, finished_at = NOW(), records_processed = %s,
                      rows_upserted = %s, error_message = %s WHERE id = %s""",
            ("success" if ok else "failed", len(rows), len(rows),
             None if ok else json.dumps(refreshed), log_id),
        )
        conn.commit()
        return {"deleted": deleted, "inserted": len(rows), "refresh": refreshed}
    finally:
        conn.close()
