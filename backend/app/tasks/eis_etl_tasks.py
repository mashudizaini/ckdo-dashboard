"""
EIS ETL Tasks — ported from the standalone eis-dashboard-v2 app into
ckdo-dashboard-v2's own Celery worker. Extracts from Oracle EBS (via the
same get_oracle_connection() the rest of this app already uses) and loads
into the eis_dashboard Postgres database (schema `eis`), read by
routers/dashboard/eis_*.py. Task names are kept identical to the original
("app.tasks.etl_tasks.*") so eis_etl_admin.py's send_task() calls work
unchanged.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
from app.tasks.celery_app import celery_app
from app.config import get_settings
from app.database import get_oracle_connection
import psycopg2

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_pg():
    return psycopg2.connect(settings.eis_database_url_rw)


def _log_start(pg, job_name, year, month):
    run_params = json.dumps({"year": year, "month": month})
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO eis.etl_job_log (job_name, status, run_params) VALUES (%s, 'running', %s) RETURNING id",
        (job_name, run_params),
    )
    pg.commit()
    return cur.fetchone()[0]


def _log_end(pg, job_id, status, records=0, error=None):
    cur = pg.cursor()
    cur.execute(
        "UPDATE eis.etl_job_log SET status=%s, finished_at=NOW(), records_processed=%s, error_message=%s WHERE id=%s",
        (status, records, error, job_id),
    )
    pg.commit()


def _month_filter_gl(year, month):
    """Return Oracle GL period_name filter clause and params."""
    if month:
        # Oracle GL period_name format: 'MMM-YY' e.g. 'JAN-26'
        month_abbr = datetime(year, month, 1).strftime('%b').upper()
        year_short = str(year)[-2:]
        period = f"{month_abbr}-{year_short}"
        return "AND gb.period_name = :period_name AND gb.period_year = :year", {
            "period_name": period, "year": year,
        }
    return "AND gb.period_year = :year", {"year": year}


def _parse_gl_period(period_name_ora):
    """Parse Oracle GL period_name 'MMM-YY' → (year, month). Returns None on error."""
    try:
        month_abbr = period_name_ora[:3]
        year_short = int(period_name_ora[4:])
        ora_year = 2000 + year_short
        ora_month = datetime.strptime(month_abbr, '%b').month
        return ora_year, ora_month
    except (ValueError, IndexError):
        return None


def _get_period_id(cur_pg, year, month):
    """Lookup period_id from dim_period. Returns None if not found."""
    cur_pg.execute(
        "SELECT id FROM eis.dim_period WHERE fiscal_year=%s AND period_num=%s",
        (year, month),
    )
    row = cur_pg.fetchone()
    return row[0] if row else None


@celery_app.task(name="app.tasks.etl_tasks.etl_sales")
def etl_sales(year: int = None, month: int = None):
    """Extract sales actuals from Oracle OE (Order Management) → fact_sales.

    Segment classification (from OE transaction types):
      LOCAL  : TRX_TYPE = 'SO-LOCAL'  (LINE_TYPE ≠ 'SO-TOLL IN-LOCAL')
      CMO    : TRX_TYPE = 'SO-LOCAL'   LINE_TYPE = 'SO-TOLL IN-LOCAL'
      EXPORT : TRX_TYPE = 'SO-EXPORT'

    BP amounts sourced from eis.business_plan (plan_type = 'Sales').
    Amounts stored in millions IDR (Oracle OE raw IDR ÷ 1,000,000).
    BP amounts from eis.business_plan are already in millions IDR.
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_sales", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        # ── Step 1: lookup transaction_type_ids (tiny table, fast) ──
        # Avoids joining oe_transaction_types_tl inside the main query,
        # which forces Oracle to evaluate USERENV('LANG') per row and
        # often causes full table scans on the large OE header/line tables.
        cur_ora.execute(
            "SELECT transaction_type_id, name "
            "FROM oe_transaction_types_tl "
            "WHERE name IN ('SO-LOCAL', 'SO-EXPORT', 'SO-TOLL IN-LOCAL') "
            "AND language = 'US'"
        )
        type_map = {name: tid for tid, name in cur_ora.fetchall()}

        local_id  = type_map.get('SO-LOCAL')
        export_id = type_map.get('SO-EXPORT')
        cmo_ln_id = type_map.get('SO-TOLL IN-LOCAL')

        if not local_id or not export_id:
            raise ValueError(
                f"TRX_TYPE IDs not found — SO-LOCAL={local_id}, SO-EXPORT={export_id}. "
                "Check oe_transaction_types_tl language='US'."
            )

        # ── Step 2: build date-range filter (allows Oracle to use index) ──
        from datetime import date as _date
        if month:
            d_from = _date(year, month, 1)
            d_to   = _date(year + 1, 1, 1) if month == 12 else _date(year, month + 1, 1)
        else:
            d_from = _date(year, 1, 1)
            d_to   = _date(year + 1, 1, 1)

        # CMO condition: SO-LOCAL header + SO-TOLL IN-LOCAL line type
        if cmo_ln_id:
            cmo_when = f"WHEN ooh.order_type_id = {local_id} AND ool.line_type_id = {cmo_ln_id} THEN 'CMO'"
        else:
            cmo_when = ""   # no CMO type found → all SO-LOCAL treated as Local

        case_expr = f"""
            CASE
                WHEN ooh.order_type_id = {export_id} THEN 'Export'
                {cmo_when}
                ELSE 'Local'
            END"""

        # ── Step 3: main query — no TL joins, uses index on ordered_date ──
        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ooh.ordered_date, 'YYYY-MM') AS period,
                {case_expr}                           AS business_type,
                SUM(
                    NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_selling_price, 0)
                ) AS actual_amount
            FROM oe_order_headers_all ooh
            JOIN oe_order_lines_all   ool ON ooh.header_id = ool.header_id
            WHERE ooh.order_type_id IN ({local_id}, {export_id})
              AND ooh.ordered_date >= :date_from
              AND ooh.ordered_date <  :date_to
              AND ool.flow_status_code <> 'CANCELLED'
            GROUP BY
                TO_CHAR(ooh.ordered_date, 'YYYY-MM'),
                {case_expr}
            ORDER BY period
        """, {"date_from": d_from, "date_to": d_to})

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_sales] Extracted {records} rows from Oracle OE (year={year}, month={month})")
        ora.close()

        # ── LOAD ──────────────────────────────────────────────────
        cur_pg = pg.cursor()

        # One-time check: does business_plan have a business_type column?
        cur_pg.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'eis' AND table_name = 'business_plan'
              AND column_name = 'business_type'
        """)
        _has_biz_type_col = cur_pg.fetchone() is not None

        MONTH_COLS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                      'jul', 'aug', 'sep', 'oct', 'nov', '"dec"']

        def _get_bp(fiscal_year: int, ora_month: int, biz_type: str) -> float:
            """Lookup BP sales amount. Uses SAVEPOINTs so a failed query does NOT
            abort the outer PostgreSQL transaction."""
            col = MONTH_COLS[ora_month - 1]

            # Try per-segment BP if the column exists
            if _has_biz_type_col:
                try:
                    cur_pg.execute("SAVEPOINT bp_seg")
                    cur_pg.execute(
                        f"SELECT {col} FROM eis.business_plan "
                        f"WHERE fiscal_year=%s AND plan_type='Sales' AND business_type=%s LIMIT 1",
                        (fiscal_year, biz_type),
                    )
                    row = cur_pg.fetchone()
                    cur_pg.execute("RELEASE SAVEPOINT bp_seg")
                    if row and row[0] is not None:
                        return float(row[0])
                except Exception:
                    cur_pg.execute("ROLLBACK TO SAVEPOINT bp_seg")

            # Fallback: total Sales BP divided equally across 3 segments
            try:
                cur_pg.execute("SAVEPOINT bp_total")
                cur_pg.execute(
                    f"SELECT {col} FROM eis.business_plan "
                    f"WHERE fiscal_year=%s AND plan_type='Sales' LIMIT 1",
                    (fiscal_year,),
                )
                row = cur_pg.fetchone()
                cur_pg.execute("RELEASE SAVEPOINT bp_total")
                if row and row[0] is not None:
                    return round(float(row[0]) / 3, 2)
            except Exception:
                cur_pg.execute("ROLLBACK TO SAVEPOINT bp_total")

            return 0.0

        loaded = 0
        for period_str, biz_type, actual_amount in rows:
            try:
                ora_year, ora_month = int(period_str[:4]), int(period_str[5:7])
            except (ValueError, IndexError):
                logger.warning(f"[etl_sales] Cannot parse period: {period_str}")
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_sales] No dim_period for {period_str}")
                continue

            bp_amount = _get_bp(ora_year, ora_month, biz_type)
            # Oracle OE amounts are in full IDR; dashboard expects millions IDR
            act = float(actual_amount or 0) / 1_000_000

            cur_pg.execute(
                "DELETE FROM eis.fact_sales "
                "WHERE period_id=%s AND business_type=%s AND market='All' AND product_id IS NULL",
                (period_id, biz_type),
            )
            cur_pg.execute(
                """INSERT INTO eis.fact_sales
                       (period_id, product_id, business_type, market, bp_amount, actual_amount)
                   VALUES (%s, NULL, %s, 'All', %s, %s)""",
                (period_id, biz_type, bp_amount, act),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_sales] Loaded {loaded} rows into fact_sales")
        # ──────────────────────────────────────────────────────────

        _log_end(pg, job_id, "success", records)
        logger.info(f"[etl_sales] Completed: {records} extracted, {loaded} loaded")

    except Exception as e:
        logger.error(f"[etl_sales] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_cogs")
def etl_cogs(year: int = None, month: int = None):
    """Extract product-level sales & COGS from Oracle OE → dim_product + fact_cogs.

    Uses the same OE transaction type classification as etl_sales:
      LOCAL  : TRX_TYPE = SO-LOCAL (LINE_TYPE ≠ SO-TOLL IN-LOCAL)
      CMO    : TRX_TYPE = SO-LOCAL + LINE_TYPE = SO-TOLL IN-LOCAL
      EXPORT : TRX_TYPE = SO-EXPORT

    product_code = inventory_item_id (string)
    product_name = ordered_item (item number / description as entered in OE)
    EBIT         = sales_amount − cogs_amount  (unit_cost from OE line)
    Amounts stored in millions IDR (Oracle OE raw IDR ÷ 1,000,000).
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_cogs", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        # ── Step 1: lookup type IDs (same as etl_sales) ──────────
        cur_ora.execute(
            "SELECT transaction_type_id, name "
            "FROM oe_transaction_types_tl "
            "WHERE name IN ('SO-LOCAL', 'SO-EXPORT', 'SO-TOLL IN-LOCAL') "
            "AND language = 'US'"
        )
        type_map = {name: tid for tid, name in cur_ora.fetchall()}

        local_id  = type_map.get('SO-LOCAL')
        export_id = type_map.get('SO-EXPORT')
        cmo_ln_id = type_map.get('SO-TOLL IN-LOCAL')

        if not local_id or not export_id:
            raise ValueError(
                f"TRX_TYPE IDs not found — SO-LOCAL={local_id}, SO-EXPORT={export_id}"
            )

        # ── Step 2: date range ────────────────────────────────────
        from datetime import date as _date
        if month:
            d_from = _date(year, month, 1)
            d_to   = _date(year + 1, 1, 1) if month == 12 else _date(year, month + 1, 1)
        else:
            d_from = _date(year, 1, 1)
            d_to   = _date(year + 1, 1, 1)

        cmo_when = (
            f"WHEN ooh.order_type_id = {local_id} AND ool.line_type_id = {cmo_ln_id} THEN 'CMO'"
            if cmo_ln_id else ""
        )
        case_biz = f"""
            CASE
                WHEN ooh.order_type_id = {export_id} THEN 'Export'
                {cmo_when}
                ELSE 'Local'
            END"""

        # ── Step 3: product-level query (no TL join in main query) ─
        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ooh.ordered_date, 'YYYY-MM')                           AS period,
                TO_CHAR(ool.inventory_item_id)                                  AS product_code,
                TRIM(NVL(MAX(ool.ordered_item),
                         TO_CHAR(ool.inventory_item_id)))                       AS product_name,
                {case_biz}                                                       AS business_type,
                SUM(NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_selling_price, 0))                           AS sales_amount,
                SUM(NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_cost, 0))                                    AS cogs_amount
            FROM oe_order_headers_all ooh
            JOIN oe_order_lines_all   ool ON ooh.header_id = ool.header_id
            WHERE ooh.order_type_id IN ({local_id}, {export_id})
              AND ooh.ordered_date >= :date_from
              AND ooh.ordered_date <  :date_to
              AND ool.flow_status_code <> 'CANCELLED'
              AND ool.inventory_item_id IS NOT NULL
            GROUP BY
                TO_CHAR(ooh.ordered_date, 'YYYY-MM'),
                TO_CHAR(ool.inventory_item_id),
                {case_biz}
            ORDER BY sales_amount DESC
        """, {"date_from": d_from, "date_to": d_to})

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_cogs] Extracted {records} product rows from Oracle OE")
        ora.close()

        # ── Step 4: LOAD ──────────────────────────────────────────
        cur_pg = pg.cursor()
        loaded = 0

        for period_str, product_code, product_name, biz_type, sales_amt, cogs_amt in rows:
            try:
                ora_year, ora_month = int(period_str[:4]), int(period_str[5:7])
            except (ValueError, IndexError):
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_cogs] No dim_period for {period_str}")
                continue

            # Oracle OE amounts are in full IDR; dashboard expects millions IDR
            sales = float(sales_amt or 0) / 1_000_000
            cogs  = float(cogs_amt  or 0) / 1_000_000
            ebit  = sales - cogs

            # Upsert dim_product (product_code is UNIQUE)
            cur_pg.execute(
                """INSERT INTO eis.dim_product
                       (product_code, product_name, business_type, market)
                   VALUES (%s, %s, %s, 'All')
                   ON CONFLICT (product_code) DO UPDATE SET
                       product_name  = EXCLUDED.product_name,
                       business_type = EXCLUDED.business_type""",
                (product_code[:20], (product_name or product_code)[:150], biz_type),
            )
            cur_pg.execute(
                "SELECT id FROM eis.dim_product WHERE product_code = %s",
                (product_code[:20],),
            )
            product_id = cur_pg.fetchone()[0]

            # Upsert fact_cogs (UNIQUE period_id, product_id)
            cur_pg.execute(
                """INSERT INTO eis.fact_cogs
                       (period_id, product_id, sales_amount, cogs_total, ebit_amount)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (period_id, product_id) DO UPDATE SET
                       sales_amount = EXCLUDED.sales_amount,
                       cogs_total   = EXCLUDED.cogs_total,
                       ebit_amount  = EXCLUDED.ebit_amount""",
                (period_id, product_id, sales, cogs, ebit),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_cogs] Loaded {loaded} rows into fact_cogs")

        _log_end(pg, job_id, "success", records)
        logger.info(f"[etl_cogs] Completed: {records} extracted, {loaded} loaded")

    except Exception as e:
        logger.error(f"[etl_cogs] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_ar_ap")
def etl_ar_ap(year: int = None, month: int = None):
    """Extract AR/AP balances from Oracle and load into fact_financial_ratio."""
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_ar_ap", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        if month:
            date_filter = "AND EXTRACT(YEAR FROM ps.due_date) = :year AND EXTRACT(MONTH FROM ps.due_date) = :month"
            date_params_ar = {"year": year, "month": month}
            date_filter_ap = "AND EXTRACT(YEAR FROM i.invoice_date) = :year AND EXTRACT(MONTH FROM i.invoice_date) = :month"
            date_params_ap = {"year": year, "month": month}
        else:
            date_filter = "AND EXTRACT(YEAR FROM ps.due_date) = :year"
            date_params_ar = {"year": year}
            date_filter_ap = "AND EXTRACT(YEAR FROM i.invoice_date) = :year"
            date_params_ap = {"year": year}

        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ps.due_date, 'YYYY-MM') as period,
                SUM(ps.amount_due_remaining) as ar_balance
            FROM ar_payment_schedules_all ps
            WHERE ps.status = 'OP'
              {date_filter}
            GROUP BY TO_CHAR(ps.due_date, 'YYYY-MM')
            ORDER BY period
        """, date_params_ar)
        ar_rows = cur_ora.fetchall()

        cur_ora.execute(f"""
            SELECT
                TO_CHAR(i.invoice_date, 'YYYY-MM') as period,
                SUM(ps.amount_remaining) as ap_balance
            FROM ap_invoices_all i
            JOIN ap_payment_schedules_all ps ON i.invoice_id = ps.invoice_id
            WHERE ps.payment_status_flag != 'Y'
              {date_filter_ap}
            GROUP BY TO_CHAR(i.invoice_date, 'YYYY-MM')
            ORDER BY period
        """, date_params_ap)
        ap_rows = cur_ora.fetchall()

        records = len(ar_rows) + len(ap_rows)
        ora.close()

        # ── LOAD ──────────────────────────────────────────────────
        # Map period 'YYYY-MM' → period_id, collect AR and AP averages
        ar_map = {row[0]: float(row[1] or 0) for row in ar_rows}
        ap_map = {row[0]: float(row[1] or 0) for row in ap_rows}

        all_periods = set(ar_map.keys()) | set(ap_map.keys())
        cur_pg = pg.cursor()
        loaded = 0

        for period_str in all_periods:
            try:
                ora_year, ora_month = int(period_str[:4]), int(period_str[5:7])
            except (ValueError, IndexError):
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_ar_ap] No dim_period for {period_str}")
                continue

            ar_avg = ar_map.get(period_str, 0.0)
            ap_avg = ap_map.get(period_str, 0.0)

            # Sales from fact_sales for DSO
            cur_pg.execute(
                "SELECT COALESCE(SUM(actual_amount), 0) FROM eis.fact_sales WHERE period_id=%s",
                (period_id,),
            )
            sales_amt = float(cur_pg.fetchone()[0] or 0)

            # COGS: prefer fact_cogs; fall back to total expenses from fact_financial
            cur_pg.execute(
                "SELECT COALESCE(SUM(cogs_total), 0) FROM eis.fact_cogs WHERE period_id=%s",
                (period_id,),
            )
            cogs_amt = float(cur_pg.fetchone()[0] or 0)
            if cogs_amt == 0:
                cur_pg.execute(
                    """SELECT COALESCE(ABS(net_profit_actual - 0), 0),
                              COALESCE(cf_cash_out_actual, 0)
                       FROM eis.fact_financial WHERE period_id=%s""",
                    (period_id,),
                )
                fin_row = cur_pg.fetchone()
                if fin_row:
                    # Use cash_out as COGS proxy (cost of goods/services paid)
                    cogs_amt = float(fin_row[1] or 0)
                    if cogs_amt == 0:
                        # Last resort: derive from sales (assume 60% COGS ratio)
                        cogs_amt = sales_amt * 0.60

            # DSO = AR / (Sales/30), DPO = AP / (COGS/30)
            dso_days = round(ar_avg / (sales_amt / 30), 2) if sales_amt > 0 else 0.0
            dpo_days = round(ap_avg / (cogs_amt / 30), 2) if cogs_amt > 0 else 0.0

            cur_pg.execute(
                """INSERT INTO eis.fact_financial_ratio
                       (period_id, dso_ar_avg, dso_sales, dso_days,
                        dpo_ap_avg, dpo_cogs, dpo_days)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (period_id) DO UPDATE SET
                       dso_ar_avg = EXCLUDED.dso_ar_avg,
                       dso_sales  = EXCLUDED.dso_sales,
                       dso_days   = EXCLUDED.dso_days,
                       dpo_ap_avg = EXCLUDED.dpo_ap_avg,
                       dpo_cogs   = EXCLUDED.dpo_cogs,
                       dpo_days   = EXCLUDED.dpo_days""",
                (period_id, ar_avg, sales_amt, dso_days, ap_avg, cogs_amt, dpo_days),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_ar_ap] Loaded {loaded} rows into fact_financial_ratio")
        # ──────────────────────────────────────────────────────────

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_ar_ap] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_inventory")
def etl_inventory(year: int = None, month: int = None):
    """Extract inventory valuation from Oracle and load into fact_financial_ratio."""
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_inventory", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        if month:
            date_filter = "AND EXTRACT(YEAR FROM moq.last_update_date) = :year AND EXTRACT(MONTH FROM moq.last_update_date) = :month"
            date_params = {"year": year, "month": month}
        else:
            date_filter = "AND EXTRACT(YEAR FROM moq.last_update_date) = :year"
            date_params = {"year": year}

        cur_ora.execute(f"""
            SELECT
                moq.organization_id,
                SUM(moq.transaction_quantity * cic.item_cost) as inventory_value
            FROM mtl_onhand_quantities_detail moq
            JOIN cst_item_costs cic ON moq.inventory_item_id = cic.inventory_item_id
                AND moq.organization_id = cic.organization_id
                AND cic.cost_type_id = 1
            WHERE 1=1
              {date_filter}
            GROUP BY moq.organization_id
        """, date_params)
        rows = cur_ora.fetchall()
        records = len(rows)
        ora.close()

        # ── LOAD ──────────────────────────────────────────────────
        # Sum all organizations → total inventory value for the period
        total_inv = sum(float(r[1] or 0) for r in rows)

        if total_inv > 0:
            cur_pg = pg.cursor()
            ora_month = month or 12  # if full-year, use December as snapshot month

            period_id = _get_period_id(cur_pg, year, ora_month)
            if period_id:
                # COGS: prefer fact_cogs; fall back to cash_out from fact_financial
                cur_pg.execute(
                    "SELECT COALESCE(SUM(cogs_total), 0) FROM eis.fact_cogs WHERE period_id=%s",
                    (period_id,),
                )
                cogs_amt = float(cur_pg.fetchone()[0] or 0)
                if cogs_amt == 0:
                    cur_pg.execute(
                        "SELECT COALESCE(cf_cash_out_actual, 0) FROM eis.fact_financial WHERE period_id=%s",
                        (period_id,),
                    )
                    fin_row = cur_pg.fetchone()
                    if fin_row:
                        cogs_amt = float(fin_row[0] or 0)
                    if cogs_amt == 0:
                        # Last resort: derive from sales (assume 60% COGS ratio)
                        cur_pg.execute(
                            "SELECT COALESCE(SUM(actual_amount), 0) FROM eis.fact_sales WHERE period_id=%s",
                            (period_id,),
                        )
                        sales_amt = float(cur_pg.fetchone()[0] or 0)
                        cogs_amt = sales_amt * 0.60
                dio_days = round(total_inv / (cogs_amt / 30), 2) if cogs_amt > 0 else 0.0

                cur_pg.execute(
                    """INSERT INTO eis.fact_financial_ratio
                           (period_id, dio_inv_avg, dio_cogs, dio_days)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (period_id) DO UPDATE SET
                           dio_inv_avg = EXCLUDED.dio_inv_avg,
                           dio_cogs    = EXCLUDED.dio_cogs,
                           dio_days    = EXCLUDED.dio_days""",
                    (period_id, total_inv, cogs_amt, dio_days),
                )
                pg.commit()
                logger.info(f"[etl_inventory] Loaded inventory {total_inv:,.0f} into period_id={period_id}")
            else:
                logger.warning(f"[etl_inventory] No dim_period for {year}/{ora_month}")
        # ──────────────────────────────────────────────────────────

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_inventory] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_production")
def etl_production(year: int = None, month: int = None):
    """Extract production data from Oracle → fact_production.

    Tries Oracle Process Manufacturing (OPM) first via gme_batch_header.
    Falls back to WIP Discrete (wip_discrete_jobs) if OPM returns no rows.

    OPM  batch_status : 3=Completed, 4=Closed
    WIP  status_type  : 3=Complete, 4=Complete-No Charges, 12=Closed
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_production", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        from datetime import date as _date
        if month:
            d_from = _date(year, month, 1)
            d_to   = _date(year + 1, 1, 1) if month == 12 else _date(year, month + 1, 1)
        else:
            d_from = _date(year, 1, 1)
            d_to   = _date(year + 1, 1, 1)

        rows = []

        # Build month clause for EXTRACT-based filter (confirmed working in TOAD)
        month_clause = "AND EXTRACT(MONTH FROM gbh.actual_cmplt_date) = :month" if month else ""
        wip_month_clause = "AND EXTRACT(MONTH FROM COALESCE(wdj.date_completed, wdj.last_update_date)) = :month" if month else ""
        extract_params = {"year": year, "month": month} if month else {"year": year}

        # ── Strategy 1: OPM via gme_batch_header + gme_material_details ──
        # plan_qty / actual_qty are on the OUTPUT lines (line_type=1),
        # not on the batch header itself (confirmed by diagnostic).
        try:
            logger.info(f"[etl_production] Trying OPM (header+material_details) year={year} month={month}")
            cur_ora.execute(f"""
                SELECT
                    TO_CHAR(gbh.actual_cmplt_date, 'YYYY-MM')  AS period,
                    SUM(NVL(gmd.plan_qty,   0))                 AS planned_qty,
                    SUM(NVL(gmd.actual_qty, 0))                 AS actual_qty
                FROM gme_batch_header     gbh
                JOIN gme_material_details gmd
                    ON gbh.batch_id = gmd.batch_id
                WHERE gbh.batch_status IN (3, 4)
                  AND gbh.actual_cmplt_date IS NOT NULL
                  AND gmd.line_type = 1
                  AND EXTRACT(YEAR FROM gbh.actual_cmplt_date) = :year
                  {month_clause}
                GROUP BY TO_CHAR(gbh.actual_cmplt_date, 'YYYY-MM')
                ORDER BY period
            """, extract_params)
            rows = cur_ora.fetchall()
            logger.info(f"[etl_production] OPM returned {len(rows)} period rows")
        except Exception as e_opm:
            logger.warning(f"[etl_production] OPM query failed: {e_opm!r} — trying WIP fallback")

        # ── Strategy 2: WIP Discrete fallback ────────────────────
        if not rows:
            try:
                logger.info(f"[etl_production] Trying WIP wip_discrete_jobs year={year} month={month}")
                cur_ora.execute(f"""
                    SELECT
                        TO_CHAR(COALESCE(wdj.date_completed, wdj.last_update_date), 'YYYY-MM') AS period,
                        SUM(NVL(wdj.start_quantity, 0))      AS planned_qty,
                        SUM(NVL(wdj.quantity_completed, 0))  AS actual_qty
                    FROM wip_discrete_jobs wdj
                    WHERE wdj.status_type IN (3, 4, 12)
                      AND EXTRACT(YEAR FROM COALESCE(wdj.date_completed, wdj.last_update_date)) = :year
                      {wip_month_clause}
                    GROUP BY TO_CHAR(COALESCE(wdj.date_completed, wdj.last_update_date), 'YYYY-MM')
                    ORDER BY period
                """, extract_params)
                rows = cur_ora.fetchall()
                logger.info(f"[etl_production] WIP returned {len(rows)} period rows")
            except Exception as e_wip:
                logger.error(f"[etl_production] WIP query also failed: {e_wip!r}")
                raise

        records = len(rows)
        ora.close()

        if records == 0:
            logger.warning(
                f"[etl_production] No production data found for {year}"
                + (f"/{month}" if month else "") +
                ". Check Oracle OPM (gme_batch_header) and WIP (wip_discrete_jobs) tables."
            )

        # ── LOAD ──────────────────────────────────────────────────
        cur_pg = pg.cursor()
        loaded = 0

        for period_str, planned_qty, actual_qty in rows:
            if not period_str:
                continue
            try:
                ora_year, ora_month = int(period_str[:4]), int(period_str[5:7])
            except (ValueError, IndexError):
                logger.warning(f"[etl_production] Cannot parse period: {period_str}")
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_production] No dim_period for {period_str}")
                continue

            plan = float(planned_qty or 0)
            act  = float(actual_qty  or 0)

            cur_pg.execute(
                """INSERT INTO eis.fact_production
                       (period_id, segment, bp_qty, actual_qty, batch_size, yield_qty)
                   VALUES (%s, 'Local', %s, %s, %s, %s)
                   ON CONFLICT (period_id, segment) DO UPDATE SET
                       bp_qty     = EXCLUDED.bp_qty,
                       actual_qty = EXCLUDED.actual_qty,
                       batch_size = EXCLUDED.batch_size,
                       yield_qty  = EXCLUDED.yield_qty""",
                (period_id, plan, act, plan, act),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_production] Loaded {loaded} rows into fact_production")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_production] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_employee")
def etl_employee(year: int = None, month: int = None):
    """Extract monthly employee headcount from Oracle HR → fact_employee.

    Uses end-of-month date as snapshot to capture all active employees.
    Date format YYYY-MM-DD is NLS-independent.
    When month is None, iterates all 12 months of the year.
    """
    import calendar as _cal
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_employee", year, month)
    records = 0

    def _map_dept(dept_name: str) -> str:
        n = str(dept_name).upper()
        if any(k in n for k in ('SALES', 'MARKETING', 'MARKET')):
            return 'SM'
        if any(k in n for k in ('SUPPLY', 'DISTRIBUT', 'LOGISTIC', 'WAREHOUSE')):
            return 'SD'
        if any(k in n for k in ('PRODUCTION', 'QC', 'QUALITY CONTROL', 'MANUFACT')):
            return 'Plant Direct'
        if any(k in n for k in ('ENGINEERING', 'MAINTENANCE', 'FACILITY')):
            return 'Plant Indirect'
        if 'PLANT' in n:
            return 'Plant'
        return 'Admin'

    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()
        cur_pg = pg.cursor()

        months_to_process = [month] if month else list(range(1, 13))
        loaded = 0

        for m in months_to_process:
            # End-of-month snapshot: NLS-independent YYYY-MM-DD format
            last_day = _cal.monthrange(year, m)[1]
            snap_date = f"{year}-{m:02d}-{last_day:02d}"

            cur_ora.execute("""
                SELECT
                    haou.name                       AS department,
                    COUNT(DISTINCT papf.person_id)  AS headcount
                FROM per_all_people_f     papf
                JOIN per_all_assignments_f paaf
                    ON papf.person_id = paaf.person_id
                JOIN hr_all_organization_units haou
                    ON paaf.organization_id = haou.organization_id
                WHERE TO_DATE(:snap, 'YYYY-MM-DD')
                          BETWEEN papf.effective_start_date AND papf.effective_end_date
                  AND TO_DATE(:snap, 'YYYY-MM-DD')
                          BETWEEN paaf.effective_start_date AND paaf.effective_end_date
                  AND paaf.assignment_type = 'E'
                  AND paaf.primary_flag    = 'Y'
                GROUP BY haou.name
                ORDER BY haou.name
            """, {"snap": snap_date})

            dept_rows = cur_ora.fetchall()
            records += len(dept_rows)
            logger.info(f"[etl_employee] {year}/{m:02d} snapshot {snap_date}: {len(dept_rows)} dept rows")

            if not dept_rows:
                logger.warning(f"[etl_employee] No HR data for {snap_date} — skipping period {m}")
                continue

            period_id = _get_period_id(cur_pg, year, m)
            if not period_id:
                logger.warning(f"[etl_employee] No dim_period for {year}/{m}")
                continue

            # Aggregate to dept_group
            dept_totals: dict = defaultdict(int)
            for dept_name, headcount in dept_rows:
                dept_totals[_map_dept(dept_name)] += int(headcount or 0)

            for dept_group, headcount in dept_totals.items():
                cur_pg.execute(
                    """INSERT INTO eis.fact_employee
                           (period_id, dept_group, headcount, plan_headcount, resigned_cumulative)
                       VALUES (%s, %s, %s, 0, 0)
                       ON CONFLICT (period_id, dept_group) DO UPDATE SET
                           headcount = EXCLUDED.headcount""",
                    (period_id, dept_group, headcount),
                )
                loaded += 1

        pg.commit()
        logger.info(f"[etl_employee] Loaded {loaded} rows across {len(months_to_process)} months")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_employee] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_financial")
def etl_financial(year: int = None, month: int = None):
    """Extract financial P&L and cashflow from Oracle GL into fact_financial.

    Actual net profit  → Oracle GL actual_flag='A' (revenue − expenses)
    BP net profit      → eis.business_plan WHERE plan_type='Financial Target'
    Actual cashflow    → Oracle GL actual_flag='A', cash/bank accounts (segment3 10000-14999)
    BP cashflow        → eis.business_plan WHERE plan_type='Cashflow'
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_financial", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()
        period_clause, period_params = _month_filter_gl(year, month)

        # ── 1. Actual P&L ─────────────────────────────────────────
        cur_ora.execute(f"""
            SELECT
                gb.period_name,
                gb.period_year,
                gb.period_num,
                SUM(CASE WHEN gcc.account_type = 'R'
                    THEN NVL(gb.period_net_cr, 0) - NVL(gb.period_net_dr, 0)
                    ELSE 0 END) as revenue,
                SUM(CASE WHEN gcc.account_type = 'E'
                    THEN NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)
                    ELSE 0 END) as expenses
            FROM gl_balances gb
            JOIN gl_code_combinations gcc ON gb.code_combination_id = gcc.code_combination_id
            WHERE gb.actual_flag = 'A'
              AND gb.currency_code = 'IDR'
              {period_clause}
            GROUP BY gb.period_name, gb.period_year, gb.period_num
            ORDER BY gb.period_year, gb.period_num
        """, period_params)
        pl_rows = cur_ora.fetchall()
        records += len(pl_rows)

        # ── 2. Actual cashflow (net movement of cash/bank accounts) ──
        # Segment3 10000-14999 = Cash & Bank accounts (adjust to your COA)
        cur_ora.execute(f"""
            SELECT
                gb.period_name,
                gb.period_year,
                gb.period_num,
                SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) as cash_in,
                SUM(NVL(gb.period_net_cr, 0) - NVL(gb.period_net_dr, 0)) as cash_out
            FROM gl_balances gb
            JOIN gl_code_combinations gcc ON gb.code_combination_id = gcc.code_combination_id
            WHERE gb.actual_flag = 'A'
              AND gb.currency_code = 'IDR'
              AND gcc.segment3 BETWEEN '10000' AND '14999'
              {period_clause}
            GROUP BY gb.period_name, gb.period_year, gb.period_num
            ORDER BY gb.period_year, gb.period_num
        """, period_params)
        cf_rows = cur_ora.fetchall()
        records += len(cf_rows)
        ora.close()

        # ── 3. BP net profit from business_plan table (PostgreSQL) ──
        # plan_type='Financial Target', category='Net Profit'
        # month columns: jan feb mar apr may jun jul aug sep oct nov dec
        _MONTH_COLS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                       'jul', 'aug', 'sep', 'oct', 'nov', '"dec"']
        cur_pg = pg.cursor()
        cur_pg.execute(
            """SELECT jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,"dec"
               FROM eis.business_plan
               WHERE fiscal_year=%s
                 AND plan_type='Financial Target'
                 AND LOWER(category) LIKE '%%net profit%%'
               LIMIT 1""",
            (year,),
        )
        bp_profit_row = cur_pg.fetchone()

        # Fallback: sum all 'Financial Target' rows if no 'net profit' row
        if not bp_profit_row:
            cur_pg.execute(
                """SELECT jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,"dec"
                   FROM eis.business_plan
                   WHERE fiscal_year=%s AND plan_type='Financial Target'
                   LIMIT 1""",
                (year,),
            )
            bp_profit_row = cur_pg.fetchone()

        # bp_profit_by_month[month_num] = bp_amount (1-indexed)
        bp_profit_by_month = {}
        if bp_profit_row:
            for i, val in enumerate(bp_profit_row):
                bp_profit_by_month[i + 1] = float(val or 0)

        # ── 4. BP cashflow from business_plan table ──────────────
        cur_pg.execute(
            """SELECT jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,"dec"
               FROM eis.business_plan
               WHERE fiscal_year=%s AND plan_type='Cashflow'
               LIMIT 1""",
            (year,),
        )
        bp_cf_row = cur_pg.fetchone()
        bp_cf_by_month = {}
        if bp_cf_row:
            for i, val in enumerate(bp_cf_row):
                bp_cf_by_month[i + 1] = float(val or 0)

        # ── 5. Build cashflow lookup by (year, month) ────────────
        cf_map = {}  # (year, month) → (cash_in, cash_out)
        for period_name_ora, period_year, period_num, cash_in, cash_out in cf_rows:
            cf_map[(int(period_year), int(period_num))] = (
                float(cash_in or 0), float(cash_out or 0),
            )

        # ── 6. LOAD ───────────────────────────────────────────────
        loaded = 0
        cumulative_profit_actual = 0.0
        cumulative_profit_bp = 0.0
        cf_ending_actual = 0.0  # running ending balance

        for period_name_ora, period_year, period_num, revenue, expenses in pl_rows:
            ora_year = int(period_year)
            ora_month = int(period_num)

            # Only process matching month when filtering
            if month and ora_month != month:
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_financial] No dim_period for {ora_year}/{ora_month}")
                continue

            rev = float(revenue or 0)
            exp = float(expenses or 0)
            net_profit_actual = rev - exp
            cumulative_profit_actual += net_profit_actual

            net_profit_bp = bp_profit_by_month.get(ora_month, 0.0)
            cumulative_profit_bp += net_profit_bp

            cash_in, cash_out = cf_map.get((ora_year, ora_month), (0.0, 0.0))
            cf_ending_actual += (cash_in - cash_out)
            cf_ending_bp = bp_cf_by_month.get(ora_month, 0.0)

            cur_pg.execute(
                """INSERT INTO eis.fact_financial
                       (period_id,
                        net_profit_actual, net_profit_actual_cumulative,
                        net_profit_bp, net_profit_bp_cumulative,
                        cf_cash_in_actual, cf_cash_out_actual,
                        cf_ending_balance_actual, cf_ending_balance_bp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (period_id) DO UPDATE SET
                       net_profit_actual            = EXCLUDED.net_profit_actual,
                       net_profit_actual_cumulative = EXCLUDED.net_profit_actual_cumulative,
                       net_profit_bp                = EXCLUDED.net_profit_bp,
                       net_profit_bp_cumulative     = EXCLUDED.net_profit_bp_cumulative,
                       cf_cash_in_actual            = EXCLUDED.cf_cash_in_actual,
                       cf_cash_out_actual           = EXCLUDED.cf_cash_out_actual,
                       cf_ending_balance_actual     = EXCLUDED.cf_ending_balance_actual,
                       cf_ending_balance_bp         = EXCLUDED.cf_ending_balance_bp""",
                (period_id,
                 net_profit_actual, cumulative_profit_actual,
                 net_profit_bp, cumulative_profit_bp,
                 cash_in, cash_out,
                 cf_ending_actual, cf_ending_bp),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_financial] Loaded {loaded} rows into fact_financial")
        # ──────────────────────────────────────────────────────────

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_financial] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_budget")
def etl_budget(year: int = None, month: int = None):
    """Extract departmental OPEX budget vs actual from Oracle GL into fact_budget."""
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_budget", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        period_clause, period_params = _month_filter_gl(year, month)

        # Extract expense accounts (account_type='E') grouped by period + cost center (segment2)
        # actual_flag: 'A' = actual spending, 'B' = budget (business plan)
        cur_ora.execute(f"""
            SELECT
                gb.period_name,
                gb.period_year,
                gb.period_num,
                gcc.segment2 as cost_center,
                gb.actual_flag,
                SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) as amount
            FROM gl_balances gb
            JOIN gl_code_combinations gcc ON gb.code_combination_id = gcc.code_combination_id
            WHERE gb.actual_flag IN ('A', 'B')
              AND gcc.account_type = 'E'
              AND gb.currency_code = 'IDR'
              {period_clause}
            GROUP BY gb.period_name, gb.period_year, gb.period_num,
                     gcc.segment2, gb.actual_flag
            ORDER BY gb.period_year, gb.period_num, gcc.segment2
        """, period_params)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_budget] Extracted {records} rows from Oracle GL (year={year}, month={month})")
        ora.close()

        # ── LOAD ──────────────────────────────────────────────────
        # Map Oracle cost center segment → dept_group
        def _map_cost_center(segment):
            """Map GL segment2 (cost center code) to dept_group."""
            s = str(segment or '').strip().upper()
            # Adjust these ranges to match your actual Oracle COA cost center codes
            if s.startswith('1'):      # e.g. 1xxx = Sales & Marketing
                return 'SM'
            if s.startswith('2'):      # e.g. 2xxx = Supply & Distribution
                return 'SD'
            if s.startswith('3'):      # e.g. 3xxx = Plant Direct
                return 'Plant Direct'
            if s.startswith('4'):      # e.g. 4xxx = Plant Indirect
                return 'Plant Indirect'
            return 'Admin'

        # Aggregate per (period, dept_group, actual_flag)
        agg = defaultdict(lambda: {'A': 0.0, 'B': 0.0})
        for period_name_ora, period_year, period_num, cost_center, actual_flag, amount in rows:
            dept_group = _map_cost_center(cost_center)
            key = (int(period_year), int(period_num), dept_group)
            if actual_flag in ('A', 'B'):
                agg[key][actual_flag] += float(amount or 0)

        cur_pg = pg.cursor()
        loaded = 0
        for (ora_year, ora_month, dept_group), amounts in agg.items():
            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_budget] No dim_period for {ora_year}/{ora_month}")
                continue

            cur_pg.execute(
                """INSERT INTO eis.fact_budget
                       (period_id, dept_group, bp_amount, actual_amount)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (period_id, dept_group) DO UPDATE SET
                       bp_amount     = EXCLUDED.bp_amount,
                       actual_amount = EXCLUDED.actual_amount""",
                (period_id, dept_group, amounts['B'], amounts['A']),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_budget] Loaded {loaded} rows into fact_budget")
        # ──────────────────────────────────────────────────────────

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_budget] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}
