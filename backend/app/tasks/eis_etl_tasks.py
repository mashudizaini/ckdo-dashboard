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

    Extracted product-level (same grouping/upsert pattern as etl_cogs, one
    Oracle round-trip) so fact_sales carries BOTH:
      - the existing period+business_type aggregate row (product_id NULL,
        market='All', bp_amount from eis.business_plan) — unchanged
        behaviour, still the sum of every line incl. ones with no resolved
        inventory_item_id;
      - one row per product actually resolved (product_id set, bp_amount=0
        — no per-SKU budget plan exists), so "sales per product" questions
        have real data instead of a single info-less aggregate row.

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

        # Export orders (SO-EXPORT) are priced in USD, not IDR — confirmed
        # live: 100% of 2026 Export orders carry transactional_curr_code
        # 'USD', Local is 100% 'IDR'. Without converting, Export revenue was
        # being treated as if it were already IDR, understating it by the
        # exchange rate (~17,000x — a 2026 export total of ~5.2M "IDR" was
        # actually ~5.2M USD). Same per-line "latest Corporate rate on or
        # before the transaction date" pattern etl_po already uses for
        # non-IDR POs.
        curr_conv_expr = """
            CASE WHEN ooh.transactional_curr_code = 'IDR' THEN 1
                 ELSE COALESCE((
                     SELECT gdr.conversion_rate FROM gl_daily_rates gdr
                     WHERE gdr.from_currency = ooh.transactional_curr_code
                       AND gdr.to_currency = 'IDR'
                       AND gdr.conversion_type = 'Corporate'
                       AND gdr.conversion_date = (
                           SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                           WHERE gdr2.from_currency = ooh.transactional_curr_code
                             AND gdr2.to_currency = 'IDR'
                             AND gdr2.conversion_type = 'Corporate'
                             AND gdr2.conversion_date <= TRUNC(ooh.ordered_date)
                       )
                 ), 1) END"""

        # ── Step 3: main query — product-level grouping (same shape as
        # etl_cogs), so a single Oracle round-trip yields both the
        # per-product breakdown and (summed in Python below) the existing
        # period+business_type aggregate. Rows with no resolved
        # inventory_item_id collapse into one NULL-product_code group per
        # period/business_type — still counted in the aggregate total,
        # just not turned into a dim_product/fact_sales product row. ──
        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ooh.ordered_date, 'YYYY-MM')                            AS period,
                TO_CHAR(ool.inventory_item_id)                                   AS product_code,
                TRIM(NVL(MAX(ool.ordered_item),
                         TO_CHAR(ool.inventory_item_id)))                        AS product_name,
                {case_expr}                                                       AS business_type,
                SUM(
                    NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_selling_price, 0)
                    * ({curr_conv_expr})
                ) AS actual_amount
            FROM oe_order_headers_all ooh
            JOIN oe_order_lines_all   ool ON ooh.header_id = ool.header_id
            WHERE ooh.order_type_id IN ({local_id}, {export_id})
              AND ooh.ordered_date >= :date_from
              AND ooh.ordered_date <  :date_to
              AND ool.flow_status_code <> 'CANCELLED'
            GROUP BY
                TO_CHAR(ooh.ordered_date, 'YYYY-MM'),
                TO_CHAR(ool.inventory_item_id),
                {case_expr}
            ORDER BY period
        """, {"date_from": d_from, "date_to": d_to})

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_sales] Extracted {records} product-level rows from Oracle OE (year={year}, month={month})")
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
        loaded_products = 0
        # (fiscal_year, ora_month, business_type) -> summed actual (millions IDR),
        # built from every row incl. ones with no resolved product_code —
        # keeps the aggregate row's total identical to the pre-per-product
        # behaviour.
        agg_totals: dict[tuple[int, int, str], float] = defaultdict(float)

        for period_str, product_code, product_name, biz_type, actual_amount in rows:
            try:
                ora_year, ora_month = int(period_str[:4]), int(period_str[5:7])
            except (ValueError, IndexError):
                logger.warning(f"[etl_sales] Cannot parse period: {period_str}")
                continue

            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                logger.warning(f"[etl_sales] No dim_period for {period_str}")
                continue

            # Oracle OE amounts are in full IDR; dashboard expects millions IDR
            act = float(actual_amount or 0) / 1_000_000
            agg_totals[(ora_year, ora_month, biz_type)] += act

            if product_code:
                # Upsert dim_product (product_code is UNIQUE) — same pattern as etl_cogs.
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

                # No per-SKU budget plan exists — bp_amount stays 0 for product rows
                # (matches fact_cogs, which doesn't carry a BP column at all).
                cur_pg.execute(
                    """INSERT INTO eis.fact_sales
                           (period_id, product_id, business_type, market, bp_amount, actual_amount)
                       VALUES (%s, %s, %s, 'All', 0, %s)
                       ON CONFLICT (period_id, product_id, business_type, market) DO UPDATE SET
                           actual_amount = EXCLUDED.actual_amount""",
                    (period_id, product_id, biz_type, act),
                )
                loaded_products += 1

        # Aggregate rows (product_id IS NULL) — DELETE-then-INSERT, not
        # ON CONFLICT: Postgres UNIQUE treats NULL as distinct, so a NULL
        # product_id can't be matched/deduped by ON CONFLICT.
        for (ora_year, ora_month, biz_type), act_total in agg_totals.items():
            period_id = _get_period_id(cur_pg, ora_year, ora_month)
            if not period_id:
                continue
            bp_amount = _get_bp(ora_year, ora_month, biz_type)
            cur_pg.execute(
                "DELETE FROM eis.fact_sales "
                "WHERE period_id=%s AND business_type=%s AND market='All' AND product_id IS NULL",
                (period_id, biz_type),
            )
            cur_pg.execute(
                """INSERT INTO eis.fact_sales
                       (period_id, product_id, business_type, market, bp_amount, actual_amount)
                   VALUES (%s, NULL, %s, 'All', %s, %s)""",
                (period_id, biz_type, bp_amount, act_total),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_sales] Loaded {loaded} aggregate rows + {loaded_products} product rows into fact_sales")
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
    Export orders are priced in USD (Local is IDR) — converted to IDR using
    gl_daily_rates (Corporate, latest rate on/before ordered_date), same as
    etl_sales/etl_po. Amounts stored in millions IDR (÷ 1,000,000).
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

        # Same USD->IDR conversion as etl_sales — see its comment for the
        # live-verified reasoning (Export orders are 100% USD, Local 100%
        # IDR). Applied to both sales_amount and cogs_amount so this job's
        # own product-level numbers stay consistent with fact_sales.
        curr_conv_expr = """
            CASE WHEN ooh.transactional_curr_code = 'IDR' THEN 1
                 ELSE COALESCE((
                     SELECT gdr.conversion_rate FROM gl_daily_rates gdr
                     WHERE gdr.from_currency = ooh.transactional_curr_code
                       AND gdr.to_currency = 'IDR'
                       AND gdr.conversion_type = 'Corporate'
                       AND gdr.conversion_date = (
                           SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                           WHERE gdr2.from_currency = ooh.transactional_curr_code
                             AND gdr2.to_currency = 'IDR'
                             AND gdr2.conversion_type = 'Corporate'
                             AND gdr2.conversion_date <= TRUNC(ooh.ordered_date)
                       )
                 ), 1) END"""

        # ── Step 3: product-level query (no TL join in main query) ─
        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ooh.ordered_date, 'YYYY-MM')                           AS period,
                TO_CHAR(ool.inventory_item_id)                                  AS product_code,
                TRIM(NVL(MAX(ool.ordered_item),
                         TO_CHAR(ool.inventory_item_id)))                       AS product_name,
                {case_biz}                                                       AS business_type,
                SUM(NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_selling_price, 0)
                    * ({curr_conv_expr}))                                       AS sales_amount,
                SUM(NVL(ool.shipped_quantity, ool.ordered_quantity)
                    * NVL(ool.unit_cost, 0)
                    * ({curr_conv_expr}))                                       AS cogs_amount
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
    """Extract inventory valuation from Oracle and load into fact_financial_ratio.

    mtl_onhand_quantities_detail is a CURRENT-balance table, not a ledger —
    a row's last_update_date is whenever that on-hand row last had a
    transaction, which for a slow-moving item can be years old even though
    the balance it holds is still today's real balance. Filtering it by
    "last_update_date falls in the requested year/month" (the original
    approach) silently excludes the balance of every item that hasn't moved
    recently — confirmed empirically: 100% of real cost-matched rows had
    last_update_date in 2019-2022, so that filter produced 0 rows against
    any 2026 period, every run. There's no historical on-hand ledger
    available here, so instead: always extract the current full snapshot,
    and load it against whichever period was requested (same "as of now"
    semantics the rest of this job already used for choosing ora_month).
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_inventory", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        cur_ora.execute("""
            SELECT
                moq.organization_id,
                SUM(moq.transaction_quantity * cic.item_cost) as inventory_value
            FROM mtl_onhand_quantities_detail moq
            JOIN cst_item_costs cic ON moq.inventory_item_id = cic.inventory_item_id
                AND moq.organization_id = cic.organization_id
                AND cic.cost_type_id = 2
            GROUP BY moq.organization_id
        """)
        rows = cur_ora.fetchall()
        records = len(rows)
        ora.close()

        # ── LOAD ──────────────────────────────────────────────────
        # Sum all organizations → total inventory value for the period.
        # Oracle amounts are in full IDR; dashboard/other fact tables
        # (fact_sales, fact_cogs) store amounts in millions IDR — match
        # that unit so dio_days below isn't off by 1,000,000x against
        # cogs_amt (which comes from fact_cogs/fact_financial/fact_sales,
        # all already in millions).
        total_inv = sum(float(r[1] or 0) for r in rows) / 1_000_000

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
    """Mirror the main app's own `employees` table (ckdo_dashboard DB,
    Excel-uploaded via Employee Data) into a complete employee roster
    (dim_employee) AND a monthly headcount trend (fact_employee) — NOT
    Oracle HR, despite this task living alongside the Oracle-sourced ETL
    jobs.

    Oracle EBS was the original source here, but was dropped: its own org
    hierarchy carries no usable department/division/team info in this
    instance (every active employee's hr_all_organization_units row is the
    exact same single top-level "CKDO BG" business group, and position
    titles are free text like "IT MANAGER" with nothing structured to key
    off). employees is already the company's real, actively-maintained HR
    source of truth — used everywhere else in the app (Attendance, Leave,
    Org Chart, Employee List) — with the classification already correct
    (Administration / Sales & Marketing / Strategy & Development / Plant
    are the 4 real departments; IT, HRGA, Purchasing etc. are TEAMS within
    Administration, not departments — see department_taxonomy.py). Mirroring
    it here is simpler and strictly more complete than re-deriving a worse
    copy from Oracle (division, for one, doesn't exist in Oracle's side at
    all).

    fact_employee (period-keyed): active-employee count per department for
    a given month, computed from date_of_joining/resign_date — "active on
    snap_date" = joined by snap_date AND (never resigned, or resigned
    after snap_date). Same limitation as any headcount-from-current-data
    approach: an employee's department reflects where they are NOW, not
    necessarily where they were in a past month, since employees carries
    no per-month history — accepted the same way hr_attendance.py's own
    department backfill already does.
    dim_employee (current snapshot, upserted every run regardless of the
    year/month params below): one row per employee, mirrored 1:1 — the
    "complete employee information" roster.
    """
    import calendar as _cal
    from datetime import date as _date
    from app.database import SessionLocal as MainSessionLocal
    from app.models.employee import Employee

    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_employee", year, month)
    records = 0

    try:
        main_db = MainSessionLocal()
        try:
            emp_rows = [
                (
                    e.user_id, e.full_name, e.sex, e.job_title,
                    e.department, e.division, e.team,
                    e.date_of_joining, e.resign_date, e.employment_status,
                )
                for e in main_db.query(
                    Employee.user_id, Employee.full_name, Employee.sex, Employee.job_title,
                    Employee.department, Employee.division, Employee.team,
                    Employee.date_of_joining, Employee.resign_date, Employee.employment_status,
                )
            ]
        finally:
            main_db.close()

        records = len(emp_rows)
        logger.info(f"[etl_employee] {records} employees from the employees table")

        cur_pg = pg.cursor()

        # ── Complete employee roster snapshot → dim_employee ─────────
        roster_loaded = 0
        for (user_id, full_name, sex, job_title, department, division, team,
             joined, resigned, emp_status) in emp_rows:
            cur_pg.execute(
                """INSERT INTO eis.dim_employee
                       (employee_number, full_name, sex, position_title,
                        department, division, team, hire_date, employment_status, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (employee_number) DO UPDATE SET
                       full_name         = EXCLUDED.full_name,
                       sex               = EXCLUDED.sex,
                       position_title    = EXCLUDED.position_title,
                       department        = EXCLUDED.department,
                       division          = EXCLUDED.division,
                       team              = EXCLUDED.team,
                       hire_date         = EXCLUDED.hire_date,
                       employment_status = EXCLUDED.employment_status,
                       updated_at        = now()""",
                (user_id, full_name, sex, job_title, department, division, team,
                 joined, emp_status),
            )
            roster_loaded += 1
        pg.commit()
        logger.info(f"[etl_employee] Upserted {roster_loaded} rows into dim_employee")

        # ── Monthly headcount trend → fact_employee ───────────────────
        months_to_process = [month] if month else list(range(1, 13))
        trend_loaded = 0

        for m in months_to_process:
            last_day = _cal.monthrange(year, m)[1]
            snap_date = _date(year, m, last_day)

            period_id = _get_period_id(cur_pg, year, m)
            if not period_id:
                logger.warning(f"[etl_employee] No dim_period for {year}/{m}")
                continue

            dept_totals: dict = defaultdict(int)
            for (_uid, _name, _sex, _job, department, _div, _team,
                 joined, resigned, _status) in emp_rows:
                if not joined or joined > snap_date:
                    continue
                if resigned and resigned <= snap_date:
                    continue
                dept_totals[department or "Unclassified"] += 1

            for department, headcount in dept_totals.items():
                cur_pg.execute(
                    """INSERT INTO eis.fact_employee
                           (period_id, dept_group, headcount, plan_headcount, resigned_cumulative)
                       VALUES (%s, %s, %s, 0, 0)
                       ON CONFLICT (period_id, dept_group) DO UPDATE SET
                           headcount = EXCLUDED.headcount""",
                    (period_id, department, headcount),
                )
                trend_loaded += 1

        pg.commit()
        logger.info(f"[etl_employee] Loaded {trend_loaded} fact_employee rows across {len(months_to_process)} months")

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


@celery_app.task(name="app.tasks.etl_tasks.etl_po")
def etl_po(year: int = None, month: int = None):
    """Extract monthly PO value/count from Oracle PO → fact_purchasing.

    Mirrors the Purchasing dashboard's live Monthly Spend report
    (purchasing_service.py get_monthly_spend) — same core join
    (po_headers_all/po_lines_all/po_line_locations_all), same STANDARD/
    BLANKET/CONTRACT + not-cancelled scoping, and the same
    CKDO_MTRL_TYPE_DIRECT_INDIRECT lookup for material_type classification
    and gl_daily_rates (Corporate) currency conversion to IDR — kept
    consistent so the two never quietly disagree on what counts as a PO.
    Unlike that live/on-demand report, this aggregates once per (period,
    material_type) into the EIS warehouse for fast executive trend display
    alongside Sales/COGS/Budget, instead of hitting Oracle on every request.

    material_type: 'Direct' / 'Indirect' / 'Unclassified' (no lookup match).
    """
    year = year or datetime.now().year
    pg = _get_pg()
    job_id = _log_start(pg, "etl_po", year, month)
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

        cur_ora.execute("""
            SELECT
                EXTRACT(YEAR  FROM poh.creation_date)  AS ora_year,
                EXTRACT(MONTH FROM poh.creation_date)  AS ora_month,
                NVL(lv_mt.tag, 'Unclassified')          AS material_type,
                COUNT(DISTINCT poh.po_header_id)        AS po_count,
                SUM(pol.quantity * pol.unit_price *
                    CASE WHEN poh.currency_code = 'IDR' THEN 1
                         ELSE COALESCE((
                             SELECT gdr.conversion_rate FROM gl_daily_rates gdr
                             WHERE gdr.from_currency = poh.currency_code
                               AND gdr.to_currency = 'IDR'
                               AND gdr.conversion_type = 'Corporate'
                               AND gdr.conversion_date = (
                                   SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                                   WHERE gdr2.from_currency = poh.currency_code
                                     AND gdr2.to_currency = 'IDR'
                                     AND gdr2.conversion_type = 'Corporate'
                                     AND gdr2.conversion_date <= TRUNC(poh.creation_date)
                               )
                         ), 1) END
                )                                        AS po_value_idr
            FROM po_headers_all poh
            JOIN po_lines_all pol           ON pol.po_header_id = poh.po_header_id
            JOIN po_line_locations_all poll ON poll.po_line_id  = pol.po_line_id
            LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = pol.item_id
                                             AND msi.organization_id   = poll.ship_to_organization_id
            LEFT JOIN fnd_lookup_values_vl lv_mt
                                             ON lv_mt.lookup_code         = msi.item_type
                                            AND lv_mt.view_application_id = 700
                                            AND lv_mt.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
            WHERE poh.type_lookup_code IN ('STANDARD','BLANKET','CONTRACT')
              AND poh.authorization_status NOT IN ('CANCELLED','INCOMPLETE')
              AND NVL(pol.cancel_flag,'N') = 'N'
              AND poh.creation_date >= :date_from
              AND poh.creation_date <  :date_to
            GROUP BY EXTRACT(YEAR FROM poh.creation_date),
                     EXTRACT(MONTH FROM poh.creation_date),
                     NVL(lv_mt.tag, 'Unclassified')
        """, {"date_from": d_from, "date_to": d_to})

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_po] Extracted {records} rows from Oracle PO (year={year}, month={month})")
        ora.close()

        cur_pg = pg.cursor()
        loaded = 0
        for ora_year, ora_month, material_type, po_count, po_value in rows:
            period_id = _get_period_id(cur_pg, int(ora_year), int(ora_month))
            if not period_id:
                logger.warning(f"[etl_po] No dim_period for {int(ora_year)}/{int(ora_month)}")
                continue
            cur_pg.execute(
                """INSERT INTO eis.fact_purchasing (period_id, material_type, po_count, po_value)
                       VALUES (%s, %s, %s, %s)
                   ON CONFLICT (period_id, material_type) DO UPDATE SET
                       po_count = EXCLUDED.po_count,
                       po_value = EXCLUDED.po_value""",
                (period_id, material_type, int(po_count or 0), float(po_value or 0)),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_po] Loaded {loaded} rows into fact_purchasing")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_po] Failed: {e}")
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


# Shared PO-line extraction SQL — ported verbatim from
# purchasing_service.py's _PH_FROM/_ph_where/_RATE_CASE, which power
# Purchase History (detail/by-item/by-supplier) and Price Analysis. Those
# 4 live-Oracle report methods all query this exact same grain (one row
# per PO line) with different GROUP BY/pivoting on top — so extracting it
# once here into eis.fact_po_line lets the migrated Postgres versions of
# all 4 reuse the same table instead of needing their own ETL jobs.
# Structural filters only (type/status/cancel_flag) — user-adjustable
# filters (item, vendor, category, date range, etc.) apply in Postgres at
# read time, not here.
_PO_LINE_FROM = """
    po_headers_all poh
    JOIN po_lines_all          pol  ON pol.po_header_id     = poh.po_header_id
    JOIN po_line_locations_all poll ON poll.po_line_id      = pol.po_line_id
    LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = pol.item_id
                                   AND msi.organization_id   = poll.ship_to_organization_id
    LEFT JOIN (
        SELECT miv2.inventory_item_id, miv2.organization_id,
               MIN(mcb2.segment1) AS segment1
        FROM mtl_item_categories_v miv2
        JOIN mtl_categories_b      mcb2 ON mcb2.category_id = miv2.category_id
        WHERE miv2.category_set_name = 'CKDO Inventory'
        GROUP BY miv2.inventory_item_id, miv2.organization_id
    ) mcb ON mcb.inventory_item_id = msi.inventory_item_id
         AND mcb.organization_id   = msi.organization_id
    JOIN ap_suppliers          aps  ON aps.vendor_id         = poh.vendor_id
    LEFT JOIN per_all_people_f buyer_p
                                    ON buyer_p.person_id     = poh.agent_id
                                   AND SYSDATE BETWEEN buyer_p.effective_start_date
                                                    AND buyer_p.effective_end_date
    LEFT JOIN (
        SELECT item_id, manufacturer_name, country_of_origin
        FROM (
            SELECT item_id, manufacturer_name, country_of_origin,
                   ROW_NUMBER() OVER (
                       PARTITION BY item_id
                       ORDER BY NVL(last_update_date, creation_date) DESC
                   ) AS rn
            FROM xxckdo_manufacturer_master
        )
        WHERE rn = 1
    ) mfr ON mfr.item_id = msi.inventory_item_id
    LEFT JOIN hr_all_organization_units hou
                                    ON hou.organization_id   = msi.organization_id
    LEFT JOIN fnd_lookup_values_vl  lv_mt
                                    ON  lv_mt.lookup_code         = msi.item_type
                                    AND lv_mt.view_application_id = 700
                                    AND lv_mt.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
"""

_PO_LINE_RATE_CASE = """
    CASE WHEN poh.currency_code = 'IDR' THEN 1
    ELSE COALESCE((
        SELECT gdr.conversion_rate FROM gl_daily_rates gdr
        WHERE  gdr.from_currency   = poh.currency_code
          AND  gdr.to_currency     = 'IDR'
          AND  gdr.conversion_type = 'Corporate'
          AND  gdr.conversion_date = (
              SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
              WHERE  gdr2.from_currency   = poh.currency_code
                AND  gdr2.to_currency     = 'IDR'
                AND  gdr2.conversion_type = 'Corporate'
                AND  gdr2.conversion_date <= TRUNC(poh.creation_date)
          )
    ), 1) END
"""


@celery_app.task(name="app.tasks.etl_tasks.etl_po_lines")
def etl_po_lines(year: int = None, month: int = None, full_refresh: bool = False):
    """Extract PO line-item detail from Oracle PO → eis.fact_po_line.

    Feeds the migrated (Postgres-backed) Purchasing History and Price
    Analysis reports in purchasing_service.py — see _PO_LINE_FROM's
    docstring above. IDR conversion always uses the 'Corporate' rate
    (matches every call site's actual default); the live report's
    exchange_rate_type filter for a non-Corporate rate isn't reproduced
    here — a known, deliberately accepted gap, since no observed caller
    used anything else.

    Incremental by default: only PO lines created in the last 30 days
    (covers edits/new lines; older closed lines don't change). Pass
    year=<YYYY> (month optional) to instead pull everything from that
    year forward — used for the initial backfill.
    """
    pg = _get_pg()
    job_id = _log_start(pg, "etl_po_lines", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        from datetime import date as _date, timedelta as _timedelta
        if full_refresh:
            date_clause, date_params = "", {}
        elif year:
            d_from = _date(year, month or 1, 1)
            date_clause = "AND poh.creation_date >= :d_from"
            date_params = {"d_from": d_from}
        else:
            d_from = _date.today() - _timedelta(days=30)
            date_clause = "AND poh.creation_date >= :d_from"
            date_params = {"d_from": d_from}

        cur_ora.execute(f"""
            SELECT
                poh.segment1                                             AS po_number,
                pol.line_num                                             AS line_num,
                NVL(msi.segment1, TO_CHAR(pol.item_id))                  AS item_code,
                NVL(pol.item_description, msi.description)               AS item_description,
                NVL(mcb.segment1, '-')                                   AS category,
                NVL(msi.item_type, '-')                                  AS item_type,
                lv_mt.tag                                                AS material_type,
                NVL(msi.organization_id, poll.ship_to_organization_id)   AS organization_id,
                NVL(hou.name, TO_CHAR(poll.ship_to_organization_id))     AS organization_name,
                aps.vendor_name                                          AS supplier_name,
                buyer_p.full_name                                        AS buyer_name,
                mfr.manufacturer_name                                    AS manufacturer_name,
                COALESCE(mfr.country_of_origin, 'UNKNOWN')               AS country_of_origin,
                poh.currency_code,
                NVL(msi.primary_uom_code, pol.unit_meas_lookup_code)     AS uom,
                pol.quantity                                             AS quantity,
                pol.unit_price                                           AS unit_price,
                ROUND(pol.unit_price * ({_PO_LINE_RATE_CASE}), 4)        AS unit_price_idr,
                ROUND(pol.quantity * pol.unit_price, 2)                  AS amount_orig,
                ROUND(pol.quantity * pol.unit_price * ({_PO_LINE_RATE_CASE}), 2) AS amount_idr,
                NVL(poll.quantity_received, 0)                           AS received_qty,
                poh.creation_date                                        AS creation_date,
                poh.closed_code                                          AS closure_status
            FROM {_PO_LINE_FROM}
            WHERE poh.type_lookup_code IN ('STANDARD','BLANKET','CONTRACT')
              AND poh.authorization_status NOT IN ('CANCELLED','INCOMPLETE')
              AND NVL(pol.cancel_flag,'N') = 'N'
              {date_clause}
        """, date_params)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_po_lines] Extracted {records} PO line rows from Oracle PO")
        ora.close()

        cur_pg = pg.cursor()
        loaded = 0
        for (po_number, line_num, item_code, item_description, category, item_type, material_type,
             organization_id, organization_name, supplier_name, buyer_name, manufacturer_name,
             country_of_origin, currency_code, uom, quantity, unit_price, unit_price_idr, amount_orig,
             amount_idr, received_qty, creation_date, closure_status) in rows:
            cur_pg.execute(
                """INSERT INTO eis.fact_po_line
                       (po_number, line_num, item_code, item_description, category, item_type,
                        material_type, organization_id, organization_name, supplier_name, buyer_name,
                        manufacturer_name, country_of_origin, currency_code, uom, quantity, unit_price,
                        unit_price_idr, amount_orig, amount_idr, received_qty, creation_date, closure_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (po_number, line_num) DO UPDATE SET
                       item_code = EXCLUDED.item_code, item_description = EXCLUDED.item_description,
                       category = EXCLUDED.category, item_type = EXCLUDED.item_type,
                       material_type = EXCLUDED.material_type, organization_id = EXCLUDED.organization_id,
                       organization_name = EXCLUDED.organization_name, supplier_name = EXCLUDED.supplier_name,
                       buyer_name = EXCLUDED.buyer_name, manufacturer_name = EXCLUDED.manufacturer_name,
                       country_of_origin = EXCLUDED.country_of_origin, currency_code = EXCLUDED.currency_code,
                       uom = EXCLUDED.uom, quantity = EXCLUDED.quantity, unit_price = EXCLUDED.unit_price,
                       unit_price_idr = EXCLUDED.unit_price_idr,
                       amount_orig = EXCLUDED.amount_orig, amount_idr = EXCLUDED.amount_idr,
                       received_qty = EXCLUDED.received_qty, closure_status = EXCLUDED.closure_status,
                       updated_at = now()""",
                (po_number, line_num, item_code, item_description, category, item_type, material_type,
                 float(organization_id) if organization_id is not None else None, organization_name,
                 supplier_name, buyer_name, manufacturer_name, country_of_origin, currency_code, uom,
                 float(quantity or 0), float(unit_price or 0), float(unit_price_idr or 0),
                 float(amount_orig or 0), float(amount_idr or 0),
                 float(received_qty or 0), creation_date, closure_status),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_po_lines] Loaded {loaded} rows into fact_po_line")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_po_lines] Failed: {e}")
        pg.rollback()  # a failed INSERT mid-loop leaves the connection unusable until rolled back
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


_PR_LINE_RATE_CASE = """
    CASE WHEN prl.currency_code = 'IDR' THEN 1
    ELSE COALESCE((
        SELECT gdr.conversion_rate FROM gl_daily_rates gdr
        WHERE  gdr.from_currency   = prl.currency_code
          AND  gdr.to_currency     = 'IDR'
          AND  gdr.conversion_type = 'Corporate'
          AND  gdr.conversion_date = (
              SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
              WHERE  gdr2.from_currency   = prl.currency_code
                AND  gdr2.to_currency     = 'IDR'
                AND  gdr2.conversion_type = 'Corporate'
                AND  gdr2.conversion_date <= TRUNC(prh.creation_date)
          )
    ), 1) END
"""


@celery_app.task(name="app.tasks.etl_tasks.etl_open_pr")
def etl_open_pr(year: int = None, month: int = None):
    """Extract PR Approval Status ("Open PR") from Oracle PO →
    eis.fact_open_pr — ported verbatim from purchasing_service.py's
    get_open_pr (approval-history joins, fuzzy+real PO linkage,
    last-purchase-price lookup, split-PR/dummy-data exclusions all kept
    exactly as documented there).

    Unlike the other ETL jobs, this is a full TRUNCATE + reload every run,
    not incremental — a PR that's no longer open must disappear from this
    table, which an upsert alone wouldn't do. Scheduled every 15 minutes
    (see celery_app.py) specifically because "open" status is a live,
    fast-changing concept, unlike the daily-batch jobs — the migrated
    get_open_pr() surfaces this run's finished_at as "data_as_of" so
    staleness between runs is visible rather than silent. Working-day
    aging is deliberately NOT stored here — computed at read time in
    purchasing_service.py against today's date, so it stays accurate even
    between ETL runs.

    year/month accepted for trigger-API consistency with every other job
    but unused — this job always does a full current-state refresh.
    """
    pg = _get_pg()
    job_id = _log_start(pg, "etl_open_pr", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        cur_ora.execute(f"""
            SELECT
                prh.segment1                                                AS pr_number,
                po_link.po_number                                          AS po_number,
                prl.line_num                                                AS line_num,
                NVL(msi.segment1, '-')                                     AS item_code,
                prl.item_description                                        AS item_description,
                NVL(mcb.segment1, '-')                                      AS category_code,
                NVL(mcb.description, prl.item_description)                  AS category_name,
                lv_mt.tag                                                   AS material_type,
                fu.user_name                                                AS requestor,
                NVL(prl.unit_meas_lookup_code, '-')                        AS uom,
                ROUND(prl.quantity, 4)                                      AS quantity,
                NVL(prl.currency_code, 'IDR')                              AS currency_code,
                ROUND(NVL(prl.unit_price, 0), 4)                           AS unit_price_orig,
                ROUND(NVL(prl.unit_price, 0) * ({_PR_LINE_RATE_CASE}), 4)  AS unit_price_idr,
                ROUND(NVL(prl.quantity, 0) * NVL(prl.unit_price, 0), 2)    AS total_value_orig,
                ROUND(NVL(prl.quantity, 0) * NVL(prl.unit_price, 0)
                      * ({_PR_LINE_RATE_CASE}), 2)                         AS total_value_idr,
                prh.authorization_status                                    AS pr_status,
                prh.creation_date                                           AS creation_date,
                prl.need_by_date                                            AS due_date,
                NVL(po_appr.approved_date, NVL(appr.approved_date, prh.creation_date)) AS aging_basis_date,
                NVL(aps.vendor_name,
                    NVL(lastpo.last_supplier_name,
                        NVL(prl.suggested_vendor_name, '-')))              AS supplier_name,
                NVL(trm.name, '-')                                         AS payment_terms,
                lastpo.last_price                                          AS last_purchase_price,
                lastpo.last_currency                                       AS last_purchase_currency
            FROM po_requisition_headers_all prh
            JOIN po_requisition_lines_all prl
                ON prl.requisition_header_id = prh.requisition_header_id
            LEFT JOIN mtl_system_items_b msi
                ON  msi.inventory_item_id = prl.item_id
                AND msi.organization_id   = prl.destination_organization_id
            LEFT JOIN mtl_categories_b mcb
                ON  mcb.category_id = prl.category_id
            LEFT JOIN fnd_lookup_values_vl lv_mt
                ON  lv_mt.lookup_code         = msi.item_type
                AND lv_mt.view_application_id = 700
                AND lv_mt.lookup_type         = 'CKDO_MTRL_TYPE_DIRECT_INDIRECT'
            LEFT JOIN fnd_user fu
                ON  fu.user_id = prh.created_by
            LEFT JOIN ap_suppliers aps
                ON  aps.vendor_id = prl.vendor_id
            LEFT JOIN ap_terms_tl trm
                ON  trm.term_id  = aps.terms_id
                AND trm.language = USERENV('LANG')
            LEFT JOIN (
                SELECT pah.object_id, MAX(pah.action_date) AS approved_date
                FROM po_action_history pah
                WHERE pah.action_code      = 'APPROVE'
                  AND pah.object_type_code = 'REQUISITION'
                GROUP BY pah.object_id
            ) appr ON appr.object_id = prh.requisition_header_id
            LEFT JOIN (
                SELECT requisition_line_id, po_number, po_header_id
                FROM (
                    SELECT prd.requisition_line_id,
                           poh2.segment1 AS po_number,
                           poh2.po_header_id AS po_header_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY prd.requisition_line_id
                               ORDER BY poh2.creation_date DESC
                           ) AS rn
                    FROM po_req_distributions_all prd
                    JOIN po_distributions_all pd   ON pd.req_distribution_id = prd.distribution_id
                    JOIN po_headers_all        poh2 ON poh2.po_header_id     = pd.po_header_id
                    WHERE poh2.authorization_status NOT IN ('CANCELLED')
                )
                WHERE rn = 1
            ) po_link ON po_link.requisition_line_id = prl.requisition_line_id
            LEFT JOIN (
                SELECT pah.object_id, MAX(pah.action_date) AS approved_date
                FROM po_action_history pah
                WHERE pah.action_code      = 'APPROVE'
                  AND pah.object_type_code = 'PO'
                GROUP BY pah.object_id
            ) po_appr ON po_appr.object_id = po_link.po_header_id
            LEFT JOIN (
                SELECT item_desc_key, unit_price AS last_price,
                       currency_code AS last_currency, vendor_name AS last_supplier_name
                FROM (
                    SELECT UPPER(plx.item_description)                     AS item_desc_key,
                           plx.unit_price, phx.currency_code, apsx.vendor_name,
                           ROW_NUMBER() OVER (
                               PARTITION BY UPPER(plx.item_description)
                               ORDER BY phx.creation_date DESC
                           )                                               AS rn
                    FROM po_lines_all plx
                    JOIN po_headers_all phx  ON phx.po_header_id = plx.po_header_id
                    JOIN ap_suppliers   apsx ON apsx.vendor_id   = phx.vendor_id
                    WHERE phx.type_lookup_code      IN ('STANDARD','BLANKET','CONTRACT')
                      AND phx.authorization_status  NOT IN ('CANCELLED','INCOMPLETE')
                )
                WHERE rn = 1
            ) lastpo ON lastpo.item_desc_key = UPPER(prl.item_description)
            WHERE NVL(prl.cancel_flag, 'N') = 'N'
              AND prh.authorization_status NOT IN ('CANCELLED')
              AND NVL(prl.modified_by_agent_flag, 'N') = 'N'
              AND NOT (
                  UPPER(fu.user_name) IN ('ELLVIN', 'AFNI')
                  OR (
                      UPPER(fu.user_name) = 'SHERLIN'
                      AND UPPER(NVL(aps.vendor_name,
                              NVL(lastpo.last_supplier_name,
                                  NVL(prl.suggested_vendor_name, '-')))) = 'ELLVIN'
                  )
              )
        """)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_open_pr] Extracted {records} open PR line rows from Oracle PO")
        ora.close()

        cur_pg = pg.cursor()
        cur_pg.execute("TRUNCATE TABLE eis.fact_open_pr")
        loaded = 0
        for (pr_number, po_number, line_num, item_code, item_description, category_code, category_name,
             material_type, requestor, uom, quantity, currency_code, unit_price_orig, unit_price_idr,
             total_value_orig, total_value_idr, pr_status, creation_date, due_date, aging_basis_date,
             supplier_name, payment_terms, last_purchase_price, last_purchase_currency) in rows:
            cur_pg.execute(
                """INSERT INTO eis.fact_open_pr
                       (pr_number, po_number, line_num, item_code, item_description, category_code,
                        category_name, material_type, requestor, uom, quantity, currency_code,
                        unit_price_orig, unit_price_idr, total_value_orig, total_value_idr, pr_status,
                        creation_date, due_date, aging_basis_date, supplier_name, payment_terms,
                        last_purchase_price, last_purchase_currency)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (pr_number, line_num) DO UPDATE SET
                       po_number = EXCLUDED.po_number, item_code = EXCLUDED.item_code,
                       item_description = EXCLUDED.item_description, category_code = EXCLUDED.category_code,
                       category_name = EXCLUDED.category_name, material_type = EXCLUDED.material_type,
                       requestor = EXCLUDED.requestor, uom = EXCLUDED.uom, quantity = EXCLUDED.quantity,
                       currency_code = EXCLUDED.currency_code, unit_price_orig = EXCLUDED.unit_price_orig,
                       unit_price_idr = EXCLUDED.unit_price_idr, total_value_orig = EXCLUDED.total_value_orig,
                       total_value_idr = EXCLUDED.total_value_idr, pr_status = EXCLUDED.pr_status,
                       due_date = EXCLUDED.due_date, aging_basis_date = EXCLUDED.aging_basis_date,
                       supplier_name = EXCLUDED.supplier_name, payment_terms = EXCLUDED.payment_terms,
                       last_purchase_price = EXCLUDED.last_purchase_price,
                       last_purchase_currency = EXCLUDED.last_purchase_currency, updated_at = now()""",
                (pr_number, po_number, line_num, item_code, item_description, category_code, category_name,
                 material_type, requestor, uom, float(quantity or 0), currency_code, float(unit_price_orig or 0),
                 float(unit_price_idr or 0), float(total_value_orig or 0), float(total_value_idr or 0),
                 pr_status, creation_date, due_date, aging_basis_date, supplier_name, payment_terms,
                 float(last_purchase_price) if last_purchase_price is not None else None, last_purchase_currency),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_open_pr] Loaded {loaded} rows into fact_open_pr")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_open_pr] Failed: {e}")
        pg.rollback()  # a failed INSERT mid-loop leaves the connection unusable until rolled back
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_sales_orders")
def etl_sales_orders(year: int = None, month: int = None, full_refresh: bool = False):
    """Extract sales order line-item detail from Oracle OM →
    eis.fact_sales_order — foundation table for the Sales & Marketing
    dashboard (Open Sales Order now; Top Customers, Price Realization,
    On-Time Delivery etc. later per the blueprint, all reading from this
    same table instead of each needing their own ETL). Mirrors
    etl_po_lines's approach: same Local/Export/CMO classification and
    USD->IDR conversion as etl_sales/etl_cogs (reused verbatim, not
    reinvented), customer name resolved via hz_cust_accounts/hz_parties
    (same join pattern accounting_service.py's AR reports already use).

    Deliberately does NOT exclude CANCELLED/CLOSED rows at extraction
    time (unlike etl_open_pr) — this table needs the full status
    distribution for future modules (Order Status Funnel, Cancellation
    Rate), not just "currently open"; the Open Sales Order endpoint
    filters to open rows itself at read time.

    Incremental by default (30-day lookback); pass year=<YYYY> (month
    optional) for a full backfill from that year forward.
    """
    pg = _get_pg()
    job_id = _log_start(pg, "etl_sales_orders", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

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
            raise ValueError(f"TRX_TYPE IDs not found — SO-LOCAL={local_id}, SO-EXPORT={export_id}")

        from datetime import date as _date, timedelta as _timedelta
        if full_refresh:
            date_clause, date_params = "", {}
        elif year:
            d_from = _date(year, month or 1, 1)
            date_clause = "AND ooh.ordered_date >= :d_from"
            date_params = {"d_from": d_from}
        else:
            d_from = _date.today() - _timedelta(days=30)
            date_clause = "AND ooh.ordered_date >= :d_from"
            date_params = {"d_from": d_from}

        cmo_when = f"WHEN ooh.order_type_id = {local_id} AND ool.line_type_id = {cmo_ln_id} THEN 'CMO'" if cmo_ln_id else ""
        case_biz = f"""
            CASE
                WHEN ooh.order_type_id = {export_id} THEN 'Export'
                {cmo_when}
                ELSE 'Local'
            END"""
        curr_conv_expr = """
            CASE WHEN ooh.transactional_curr_code = 'IDR' THEN 1
                 ELSE COALESCE((
                     SELECT gdr.conversion_rate FROM gl_daily_rates gdr
                     WHERE gdr.from_currency = ooh.transactional_curr_code
                       AND gdr.to_currency = 'IDR'
                       AND gdr.conversion_type = 'Corporate'
                       AND gdr.conversion_date = (
                           SELECT MAX(gdr2.conversion_date) FROM gl_daily_rates gdr2
                           WHERE gdr2.from_currency = ooh.transactional_curr_code
                             AND gdr2.to_currency = 'IDR'
                             AND gdr2.conversion_type = 'Corporate'
                             AND gdr2.conversion_date <= TRUNC(ooh.ordered_date)
                       )
                 ), 1) END"""

        cur_ora.execute(f"""
            SELECT
                TO_CHAR(ooh.order_number)                                AS order_number,
                ool.line_number                                          AS line_num,
                NVL(ool.shipment_number, 1)                               AS shipment_num,
                NVL(msi.segment1, TO_CHAR(ool.inventory_item_id))        AS item_code,
                NVL(msi.description, ool.ordered_item)                   AS item_description,
                {case_biz}                                                AS business_type,
                hp.party_name                                             AS customer_name,
                hou.name                                                  AS organization_name,
                ooh.transactional_curr_code                               AS currency_code,
                NVL(msi.primary_uom_code, ool.order_quantity_uom)         AS uom,
                ool.ordered_quantity                                      AS quantity,
                ool.unit_selling_price                                    AS unit_selling_price,
                ool.unit_list_price                                       AS unit_list_price,
                ROUND(ool.ordered_quantity * ool.unit_selling_price, 2)   AS amount_orig,
                ROUND(ool.ordered_quantity * ool.unit_selling_price * ({curr_conv_expr}), 2) AS amount_idr,
                ool.schedule_ship_date                                    AS schedule_ship_date,
                ool.actual_shipment_date                                  AS actual_shipment_date,
                ool.flow_status_code                                      AS flow_status_code,
                ooh.ordered_date                                          AS ordered_date,
                ooh.salesrep_id                                           AS salesrep_id,
                ooh.sold_to_org_id                                        AS sold_to_org_id,
                ool.ship_from_org_id                                      AS ship_from_org_id
            FROM oe_order_headers_all ooh
            JOIN oe_order_lines_all   ool ON ool.header_id = ooh.header_id
            LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = ool.inventory_item_id
                                             AND msi.organization_id   = ool.ship_from_org_id
            LEFT JOIN hz_cust_accounts hca ON hca.cust_account_id = ooh.sold_to_org_id
            LEFT JOIN hz_parties       hp  ON hp.party_id = hca.party_id
            LEFT JOIN hr_all_organization_units hou ON hou.organization_id = ool.ship_from_org_id
            WHERE ooh.order_type_id IN ({local_id}, {export_id})
              {date_clause}
        """, date_params)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_sales_orders] Extracted {records} sales order line rows from Oracle OM")
        ora.close()

        cur_pg = pg.cursor()
        loaded = 0
        for (order_number, line_num, shipment_num, item_code, item_description, business_type, customer_name,
             organization_name, currency_code, uom, quantity, unit_selling_price, unit_list_price,
             amount_orig, amount_idr, schedule_ship_date, actual_shipment_date, flow_status_code,
             ordered_date, salesrep_id, sold_to_org_id, ship_from_org_id) in rows:
            cur_pg.execute(
                """INSERT INTO eis.fact_sales_order
                       (order_number, line_num, shipment_num, item_code, item_description, business_type,
                        customer_name, organization_name, currency_code, uom, quantity,
                        unit_selling_price, unit_list_price, amount_orig, amount_idr,
                        schedule_ship_date, actual_shipment_date, flow_status_code, ordered_date,
                        salesrep_id, sold_to_org_id, ship_from_org_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (order_number, line_num, shipment_num) DO UPDATE SET
                       item_code = EXCLUDED.item_code, item_description = EXCLUDED.item_description,
                       business_type = EXCLUDED.business_type, customer_name = EXCLUDED.customer_name,
                       organization_name = EXCLUDED.organization_name, currency_code = EXCLUDED.currency_code,
                       uom = EXCLUDED.uom, quantity = EXCLUDED.quantity,
                       unit_selling_price = EXCLUDED.unit_selling_price, unit_list_price = EXCLUDED.unit_list_price,
                       amount_orig = EXCLUDED.amount_orig, amount_idr = EXCLUDED.amount_idr,
                       schedule_ship_date = EXCLUDED.schedule_ship_date, actual_shipment_date = EXCLUDED.actual_shipment_date,
                       flow_status_code = EXCLUDED.flow_status_code, salesrep_id = EXCLUDED.salesrep_id,
                       sold_to_org_id = EXCLUDED.sold_to_org_id, ship_from_org_id = EXCLUDED.ship_from_org_id,
                       updated_at = now()""",
                (order_number, line_num, shipment_num, item_code, item_description, business_type, customer_name,
                 organization_name, currency_code, uom, float(quantity or 0), float(unit_selling_price or 0),
                 float(unit_list_price or 0), float(amount_orig or 0), float(amount_idr or 0),
                 schedule_ship_date, actual_shipment_date, flow_status_code, ordered_date,
                 float(salesrep_id) if salesrep_id is not None else None,
                 float(sold_to_org_id) if sold_to_org_id is not None else None,
                 float(ship_from_org_id) if ship_from_org_id is not None else None),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_sales_orders] Loaded {loaded} rows into fact_sales_order")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_sales_orders] Failed: {e}")
        pg.rollback()
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


@celery_app.task(name="app.tasks.etl_tasks.etl_inventory_txn")
def etl_inventory_txn(year: int = None, month: int = None, full_refresh: bool = False):
    """Extract inventory movement detail from Oracle INV
    (mtl_material_transactions) -> eis.fact_inventory_txn — foundation
    table for the PPWH dashboard (Inventory In, Inventory Out, Kartu
    Stok). Unlike Sales Orders/PO Lines, this table keys on Oracle's own
    single-column transaction_id, so there's no composite-key grain risk
    (see the shipment_number bug found and fixed in etl_sales_orders).

    direction ('IN'/'OUT') is derived from the sign of
    transaction_quantity, not from a hardcoded transaction-type list —
    some types (e.g. Subinventory Transfer) legitimately appear on either
    side depending on which leg of the movement a row represents.

    Incremental by default (30-day lookback); pass year=<YYYY> (month
    optional) for a full backfill from that year forward.
    """
    pg = _get_pg()
    job_id = _log_start(pg, "etl_inventory_txn", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        from datetime import date as _date, timedelta as _timedelta
        if full_refresh:
            date_clause, date_params = "", {}
        elif year:
            d_from = _date(year, month or 1, 1)
            date_clause = "AND mmt.transaction_date >= :d_from"
            date_params = {"d_from": d_from}
        else:
            d_from = _date.today() - _timedelta(days=30)
            date_clause = "AND mmt.transaction_date >= :d_from"
            date_params = {"d_from": d_from}

        cur_ora.execute(f"""
            SELECT
                mmt.transaction_id                                       AS transaction_id,
                mmt.transaction_date                                     AS transaction_date,
                CASE WHEN mmt.transaction_quantity >= 0 THEN 'IN' ELSE 'OUT' END AS direction,
                mtt.transaction_type_name                                AS transaction_type_name,
                NVL(msi.segment1, TO_CHAR(mmt.inventory_item_id))        AS item_code,
                msi.description                                          AS item_description,
                mp.organization_code                                     AS organization_code,
                hou.name                                                 AS organization_name,
                mmt.subinventory_code                                    AS subinventory_code,
                msub.description                                         AS subinventory_name,
                mmt.transaction_quantity                                 AS quantity,
                mmt.transaction_uom                                      AS uom,
                mmt.transaction_reference                                AS transaction_reference,
                mmt.transaction_source_type_id                           AS source_type_id,
                mmt.transaction_source_id                                AS source_id
            FROM mtl_material_transactions mmt
            JOIN mtl_transaction_types mtt ON mtt.transaction_type_id = mmt.transaction_type_id
            LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = mmt.inventory_item_id
                                             AND msi.organization_id   = mmt.organization_id
            LEFT JOIN mtl_parameters mp ON mp.organization_id = mmt.organization_id
            LEFT JOIN hr_all_organization_units hou ON hou.organization_id = mmt.organization_id
            LEFT JOIN mtl_secondary_inventories msub ON msub.secondary_inventory_name = mmt.subinventory_code
                                                      AND msub.organization_id = mmt.organization_id
            WHERE mmt.transaction_quantity IS NOT NULL
              AND mmt.transaction_quantity <> 0
              {date_clause}
        """, date_params)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_inventory_txn] Extracted {records} inventory transaction rows from Oracle INV")
        ora.close()

        cur_pg = pg.cursor()
        loaded = 0
        for (transaction_id, transaction_date, direction, transaction_type_name, item_code,
             item_description, organization_code, organization_name, subinventory_code,
             subinventory_name, quantity, uom, transaction_reference, source_type_id,
             source_id) in rows:
            cur_pg.execute(
                """INSERT INTO eis.fact_inventory_txn
                       (transaction_id, transaction_date, direction, transaction_type_name,
                        item_code, item_description, organization_code, organization_name,
                        subinventory_code, subinventory_name, quantity, uom,
                        transaction_reference, source_type_id, source_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (transaction_id) DO UPDATE SET
                       transaction_date = EXCLUDED.transaction_date, direction = EXCLUDED.direction,
                       transaction_type_name = EXCLUDED.transaction_type_name, item_code = EXCLUDED.item_code,
                       item_description = EXCLUDED.item_description, organization_code = EXCLUDED.organization_code,
                       organization_name = EXCLUDED.organization_name, subinventory_code = EXCLUDED.subinventory_code,
                       subinventory_name = EXCLUDED.subinventory_name, quantity = EXCLUDED.quantity,
                       uom = EXCLUDED.uom, transaction_reference = EXCLUDED.transaction_reference,
                       source_type_id = EXCLUDED.source_type_id, source_id = EXCLUDED.source_id,
                       updated_at = now()""",
                (float(transaction_id), transaction_date, direction, transaction_type_name, item_code,
                 item_description, organization_code, organization_name, subinventory_code,
                 subinventory_name, float(quantity or 0), uom, transaction_reference,
                 float(source_type_id) if source_type_id is not None else None,
                 float(source_id) if source_id is not None else None),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_inventory_txn] Loaded {loaded} rows into fact_inventory_txn")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_inventory_txn] Failed: {e}")
        pg.rollback()
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}


_BATCH_STATUS_NAMES = {-1: "Cancelled", 1: "Pending", 2: "WIP", 3: "Completed", 4: "Closed"}


@celery_app.task(name="app.tasks.etl_tasks.etl_batches")
def etl_batches(year: int = None, month: int = None, full_refresh: bool = False):
    """Extract OPM batch production detail from Oracle
    (gme_batch_header + its produced-item line from gme_material_details)
    -> eis.fact_batch — foundation table for the Production dashboard
    (Batch Status, Batch Yield, Schedule Adherence).

    This company runs Oracle Process Manufacturing (OPM), not discrete
    WIP — confirmed live: gme_batch_header has rows, wip_discrete_jobs
    does not. gme_batch_steps' native yield columns (planned_step_yield/
    actual_step_yield) were checked and found unpopulated (always 0) in
    this instance, so yield is derived instead from
    gme_material_details WHERE line_type = 1 (the produced/output line,
    confirmed live against a real batch: plan_qty 1500, actual_qty 1070
    matched exactly what this query extracts) vs line_type = -1
    (consumed ingredients/components — not extracted here, out of scope
    for these 3 batch-level modules).

    Incremental filters on last_update_date (not plan_start_date) so a
    batch that started weeks ago but only closes/changes status today
    still gets re-synced. Incremental by default (30-day lookback); pass
    year=<YYYY> (month optional) for a full backfill from that year
    forward.
    """
    pg = _get_pg()
    job_id = _log_start(pg, "etl_batches", year, month)
    records = 0
    try:
        ora = get_oracle_connection()
        cur_ora = ora.cursor()

        from datetime import date as _date, timedelta as _timedelta
        if full_refresh:
            date_clause, date_params = "", {}
        elif year:
            d_from = _date(year, month or 1, 1)
            date_clause = "AND gbh.last_update_date >= :d_from"
            date_params = {"d_from": d_from}
        else:
            d_from = _date.today() - _timedelta(days=30)
            date_clause = "AND gbh.last_update_date >= :d_from"
            date_params = {"d_from": d_from}

        cur_ora.execute(f"""
            SELECT
                gbh.batch_id                AS batch_id,
                TO_CHAR(gbh.batch_no)       AS batch_no,
                gbh.organization_id         AS organization_id,
                hou.name                    AS organization_name,
                gbh.batch_status            AS batch_status,
                gbh.formula_id              AS formula_id,
                gbh.plan_start_date         AS plan_start_date,
                gbh.actual_start_date       AS actual_start_date,
                gbh.due_date                AS due_date,
                gbh.plan_cmplt_date         AS plan_cmplt_date,
                gbh.actual_cmplt_date       AS actual_cmplt_date,
                prod.item_code              AS item_code,
                prod.item_description       AS item_description,
                prod.uom                    AS uom,
                prod.plan_qty               AS plan_qty,
                prod.actual_qty             AS actual_qty
            FROM gme_batch_header gbh
            LEFT JOIN hr_all_organization_units hou ON hou.organization_id = gbh.organization_id
            LEFT JOIN (
                SELECT gmd.batch_id,
                       MIN(msi.segment1) KEEP (DENSE_RANK FIRST ORDER BY gmd.line_no)    AS item_code,
                       MIN(msi.description) KEEP (DENSE_RANK FIRST ORDER BY gmd.line_no) AS item_description,
                       MIN(gmd.item_um) KEEP (DENSE_RANK FIRST ORDER BY gmd.line_no)     AS uom,
                       SUM(gmd.plan_qty)   AS plan_qty,
                       SUM(gmd.actual_qty) AS actual_qty
                FROM gme_material_details gmd
                LEFT JOIN mtl_system_items_b msi ON msi.inventory_item_id = gmd.inventory_item_id
                                                 AND msi.organization_id   = gmd.organization_id
                WHERE gmd.line_type = 1
                GROUP BY gmd.batch_id
            ) prod ON prod.batch_id = gbh.batch_id
            WHERE gbh.delete_mark = 0
              {date_clause}
        """, date_params)

        rows = cur_ora.fetchall()
        records = len(rows)
        logger.info(f"[etl_batches] Extracted {records} batch rows from Oracle OPM")
        ora.close()

        cur_pg = pg.cursor()
        loaded = 0
        for (batch_id, batch_no, organization_id, organization_name, batch_status, formula_id,
             plan_start_date, actual_start_date, due_date, plan_cmplt_date, actual_cmplt_date,
             item_code, item_description, uom, plan_qty, actual_qty) in rows:
            batch_status_name = _BATCH_STATUS_NAMES.get(int(batch_status) if batch_status is not None else None, "Unknown")
            cur_pg.execute(
                """INSERT INTO eis.fact_batch
                       (batch_id, batch_no, organization_id, organization_name, batch_status,
                        batch_status_name, formula_id, product_item_code, product_item_description,
                        product_uom, product_plan_qty, product_actual_qty, plan_start_date,
                        actual_start_date, due_date, plan_cmplt_date, actual_cmplt_date)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (batch_id) DO UPDATE SET
                       batch_no = EXCLUDED.batch_no, organization_id = EXCLUDED.organization_id,
                       organization_name = EXCLUDED.organization_name, batch_status = EXCLUDED.batch_status,
                       batch_status_name = EXCLUDED.batch_status_name, formula_id = EXCLUDED.formula_id,
                       product_item_code = EXCLUDED.product_item_code,
                       product_item_description = EXCLUDED.product_item_description,
                       product_uom = EXCLUDED.product_uom, product_plan_qty = EXCLUDED.product_plan_qty,
                       product_actual_qty = EXCLUDED.product_actual_qty, plan_start_date = EXCLUDED.plan_start_date,
                       actual_start_date = EXCLUDED.actual_start_date, due_date = EXCLUDED.due_date,
                       plan_cmplt_date = EXCLUDED.plan_cmplt_date, actual_cmplt_date = EXCLUDED.actual_cmplt_date,
                       updated_at = now()""",
                (float(batch_id), batch_no, float(organization_id) if organization_id is not None else None,
                 organization_name, float(batch_status) if batch_status is not None else None, batch_status_name,
                 float(formula_id) if formula_id is not None else None, item_code, item_description, uom,
                 float(plan_qty) if plan_qty is not None else None, float(actual_qty) if actual_qty is not None else None,
                 plan_start_date, actual_start_date, due_date, plan_cmplt_date, actual_cmplt_date),
            )
            loaded += 1

        pg.commit()
        logger.info(f"[etl_batches] Loaded {loaded} rows into fact_batch")

        _log_end(pg, job_id, "success", records)

    except Exception as e:
        logger.error(f"[etl_batches] Failed: {e}")
        pg.rollback()
        _log_end(pg, job_id, "failed", records, str(e))
        raise
    finally:
        pg.close()

    return {"status": "success", "records": records}
