"""
DDL for the meta / core / mart schemas (blueprint sections 3 and 5), applied
on every backend startup. They sit next to schema eis in the main dashboard
Postgres (database ckdo_dashboard) — the standalone eis_dashboard database is
retired, and EIS_DATABASE_URL* point here on both hosts.

Everything here is idempotent. Mart views are recreated only when their SQL
text changes (tracked by hash in meta.mart_definition), so a restart never
throws away a populated view for nothing.
"""
import hashlib
import logging

import psycopg2

from app.config import get_settings
from app.services.ebs_mart.catalog_seed import COLUMN_CATALOG, GOLDEN_QUERIES
from app.services.ebs_mart.constants import MARTS
from app.services.ebs_mart.mart_sql import MART_EXTRA_INDEXES, MART_SQL, MART_UNIQUE_INDEX

logger = logging.getLogger(__name__)
settings = get_settings()

# Roles that read marts. llm_ro is the blueprint's dedicated role for the
# tool server (see backend/scripts/sql/ebs_mart_llm_ro.sql); chat_readonly and
# ebs_chat_reader are the two existing chat roles, granted the same so the
# tool server keeps working on a host where llm_ro has not been created yet.
# None of them gets core.*, eis.* beyond what they already had, or
# meta.chat_query_log (other users' questions).
READER_ROLES = ("llm_ro", "chat_readonly", "ebs_chat_reader")


def _rw():
    return psycopg2.connect(settings.eis_database_url_rw)


# Schemas themselves come from _ensure_schemas(): CREATE SCHEMA IF NOT EXISTS
# checks the database CREATE privilege before it checks existence, so it
# cannot live here.
_META_DDL = [
    """
    CREATE TABLE IF NOT EXISTS meta.column_catalog (
        mart_name      text,
        column_name    text,
        data_type      text,
        description_id text,
        synonyms       text[] NOT NULL DEFAULT '{}',
        sample_values  text[] NOT NULL DEFAULT '{}',
        domain         text,
        updated_by     text,
        updated_at     timestamptz DEFAULT now(),
        PRIMARY KEY (mart_name, column_name)
    )
    """,
    # question_id follows the blueprint's naming: *_id is the Indonesian text
    # (like description_id), not an identifier.
    """
    CREATE TABLE IF NOT EXISTS meta.golden_query (
        id           serial PRIMARY KEY,
        domain       text,
        question_id  text NOT NULL UNIQUE,
        sql_text     text NOT NULL,
        verified_by  text,
        verified_at  date,
        created_by   text,
        created_at   timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta.chat_query_log (
        id          bigserial PRIMARY KEY,
        user_email  text,
        chat_id     text,
        source      text,
        groups      text[],
        tool_name   text,
        tool_args   jsonb,
        question    text,
        sql_text    text,
        marts       text[],
        row_count   int,
        truncated   boolean,
        duration_ms int,
        status      text,
        error_msg   text,
        created_at  timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_query_log_created ON meta.chat_query_log (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_query_log_user ON meta.chat_query_log (user_email, created_at DESC)",
    # Composite watermark per job and stream (blueprint "Aturan ETL"): the
    # highest GREATEST(last_update_date) seen from header and child tables.
    """
    CREATE TABLE IF NOT EXISTS meta.etl_watermark (
        job_name   text,
        stream     text,
        watermark  timestamp,
        updated_at timestamptz DEFAULT now(),
        PRIMARY KEY (job_name, stream)
    )
    """,
    # The blueprint's open decision "klasifikasi subinventory GOOD/REJECT/
    # QUARANTINE: daftar resmi dari Gudang/QA" — this is where that list goes.
    """
    CREATE TABLE IF NOT EXISTS meta.subinventory_class (
        subinventory_code text PRIMARY KEY,
        subinventory_type text NOT NULL CHECK (subinventory_type IN ('GOOD','REJECT','QUARANTINE')),
        notes             text,
        updated_by        text,
        updated_at        timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta.mart_definition (
        mart_name  text PRIMARY KEY,
        sql_hash   text NOT NULL,
        created_at timestamptz DEFAULT now()
    )
    """,
]

_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS core.fact_ap_payment_schedule (
        invoice_id            bigint,
        payment_num           int,
        invoice_num           text,
        invoice_type          text,
        invoice_date          date,
        gl_date               date,
        invoice_currency_code text,
        invoice_amount        numeric,
        invoice_amount_idr    numeric,
        description           text,
        vendor_id             bigint,
        vendor_num            text,
        vendor_name           text,
        vendor_site_code      text,
        liability_account     text,
        due_date              date,
        gross_amount          numeric,
        amount_remaining      numeric,
        amount_remaining_idr  numeric,
        payment_status_flag   text,
        cancelled_date        date,
        src_last_update       timestamp,
        loaded_at             timestamptz DEFAULT now(),
        PRIMARY KEY (invoice_id, payment_num)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.fact_ap_payment (
        invoice_payment_id bigint PRIMARY KEY,
        invoice_id         bigint,
        payment_num        int,
        check_id           bigint,
        payment_number     text,
        payment_date       date,
        accounting_date    date,
        payment_method     text,
        bank_account_name  text,
        payment_status     text,
        amount_entered     numeric,
        amount_idr         numeric,
        reversal_flag      text,
        void_date          date,
        src_last_update    timestamp,
        loaded_at          timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_ap_payment_invoice ON core.fact_ap_payment (invoice_id)",
    """
    CREATE TABLE IF NOT EXISTS core.fact_ap_hold (
        hold_id     bigint PRIMARY KEY,
        invoice_id  bigint,
        hold_code   text,
        hold_desc   text,
        hold_reason text,
        hold_date   timestamp,
        loaded_at   timestamptz DEFAULT now()
    )
    """,
    # Invoice attributes carried on the hold itself (see _AP_HOLD_SQL in
    # ebs_mart_tasks.py). ALTER rather than in the CREATE above: the table
    # already exists on both hosts, and CREATE TABLE IF NOT EXISTS never adds
    # a column to an existing table.
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_num text",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_type text",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_date date",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS vendor_num text",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS vendor_name text",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_currency_code text",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_amount numeric",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS invoice_amount_idr numeric",
    "ALTER TABLE core.fact_ap_hold ADD COLUMN IF NOT EXISTS cancelled_date date",
    """
    CREATE TABLE IF NOT EXISTS core.snap_onhand_lot (
        row_key           text PRIMARY KEY,
        organization_id   bigint,
        organization_code text,
        inventory_item_id bigint,
        item_code         text,
        item_desc         text,
        uom               text,
        subinventory_code text,
        locator_id        bigint,
        locator           text,
        lot_number        text,
        lot_status        text,
        origination_date  date,
        expiration_date   date,
        onhand_qty        numeric,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.dim_subinventory (
        subinventory_code text PRIMARY KEY,
        organization_id   bigint,
        description       text,
        availability_type int,
        disable_date      date,
        guessed_type      text,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.dim_item (
        inventory_item_id bigint PRIMARY KEY,
        item_code         text,
        item_desc         text,
        uom               text,
        item_category     text,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
]

# eis.etl_job_log already records every ETL run and is what IT > ETL Admin
# shows. The blueprint's meta.etl_run_log is a view over it rather than a
# second log, so the same run is never recorded twice with two chances to
# disagree. The columns below are what the blueprint adds.
_ETL_LOG_COLUMNS = [
    "ALTER TABLE eis.etl_job_log ADD COLUMN IF NOT EXISTS trigger_type text",
    "ALTER TABLE eis.etl_job_log ADD COLUMN IF NOT EXISTS triggered_by text",
    "ALTER TABLE eis.etl_job_log ADD COLUMN IF NOT EXISTS watermark_from timestamp",
    "ALTER TABLE eis.etl_job_log ADD COLUMN IF NOT EXISTS watermark_to timestamp",
    "ALTER TABLE eis.etl_job_log ADD COLUMN IF NOT EXISTS rows_upserted int",
]

def create_etl_run_log_view(cur):
    """meta.etl_run_log over eis.etl_job_log. Columns the ALTERs above could
    not add (another role owns the table on some host) read as NULL, so the
    view — and the as_of every tool answer depends on — exists regardless."""
    cur.execute(
        """SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'eis' AND table_name = 'etl_job_log'"""
    )
    have = {r[0] for r in cur.fetchall()}

    def col(name, cast):
        return name if name in have else f"NULL::{cast}"

    cur.execute(f"""
        CREATE OR REPLACE VIEW meta.etl_run_log AS
        SELECT id                                                  AS run_id,
               job_name,
               COALESCE({col('trigger_type', 'text')}, 'SCHEDULE') AS trigger_type,
               {col('triggered_by', 'text')}                       AS triggered_by,
               {col('watermark_from', 'timestamp')}                AS watermark_from,
               {col('watermark_to', 'timestamp')}                  AS watermark_to,
               records_processed                                   AS rows_read,
               {col('rows_upserted', 'int')}                       AS rows_upserted,
               CASE status WHEN 'success' THEN 'OK'
                           WHEN 'running' THEN 'RUNNING'
                           WHEN 'failed'  THEN 'FAILED'
                           ELSE UPPER(status) END                  AS status,
               error_message                                       AS error_msg,
               started_at,
               finished_at
          FROM eis.etl_job_log
    """)


def _exec_each(cur, statements, label):
    for sql in statements:
        cur.execute(sql)
    logger.info("[ebs_mart] %s ok", label)


def _mart_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM pg_matviews WHERE schemaname = 'mart' AND matviewname = %s", (name,)
    )
    return cur.fetchone() is not None


def ensure_marts(cur):
    """Create each built mart, or recreate it when its SQL changed."""
    for name, sql in MART_SQL.items():
        digest = hashlib.sha256(sql.encode()).hexdigest()
        cur.execute("SELECT sql_hash FROM meta.mart_definition WHERE mart_name = %s", (name,))
        row = cur.fetchone()
        if row and row[0] == digest and _mart_exists(cur, name):
            continue

        cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS mart.{name} CASCADE")
        cur.execute(f"CREATE MATERIALIZED VIEW mart.{name} AS {sql}")
        cols = ", ".join(MART_UNIQUE_INDEX[name])
        cur.execute(f"CREATE UNIQUE INDEX uq_mart_{name} ON mart.{name} ({cols})")
        for col in MART_EXTRA_INDEXES.get(name, []):
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mart_{name}_{col} ON mart.{name} ({col})")
        cur.execute(
            """INSERT INTO meta.mart_definition (mart_name, sql_hash, created_at) VALUES (%s, %s, now())
               ON CONFLICT (mart_name) DO UPDATE SET sql_hash = EXCLUDED.sql_hash, created_at = now()""",
            (name, digest),
        )
        logger.info("[ebs_mart] (re)created mart.%s", name)


def mart_columns(cur, name: str) -> list[tuple[str, str]]:
    """(column, type) of a materialized view. Matviews are absent from
    information_schema.columns, hence pg_attribute."""
    cur.execute(
        """
        SELECT a.attname, format_type(a.atttypid, a.atttypmod)
          FROM pg_attribute a
          JOIN pg_class c     ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'mart' AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY a.attnum
        """,
        (name,),
    )
    return cur.fetchall()


def sync_catalog(cur):
    """One catalog row per live mart column: type always synced, seed text
    only where nothing has been written yet, rows for dropped columns removed."""
    for name in MART_SQL:
        cols = mart_columns(cur, name)
        live = [c for c, _ in cols]
        seed = COLUMN_CATALOG.get(name, {})
        domain = MARTS[name]["domain"]
        for col, dtype in cols:
            desc, syn = seed.get(col, (None, []))
            cur.execute(
                """
                INSERT INTO meta.column_catalog (mart_name, column_name, data_type, description_id, synonyms, domain)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (mart_name, column_name) DO UPDATE SET
                    data_type      = EXCLUDED.data_type,
                    domain         = EXCLUDED.domain,
                    description_id = COALESCE(meta.column_catalog.description_id, EXCLUDED.description_id),
                    synonyms       = CASE WHEN cardinality(meta.column_catalog.synonyms) = 0
                                          THEN EXCLUDED.synonyms ELSE meta.column_catalog.synonyms END
                """,
                (name, col, dtype, desc, syn, domain),
            )
        if live:
            cur.execute(
                "DELETE FROM meta.column_catalog WHERE mart_name = %s AND NOT (column_name = ANY(%s))",
                (name, live),
            )


def seed_golden_queries(cur):
    for domain, question, sql in GOLDEN_QUERIES:
        cur.execute(
            """INSERT INTO meta.golden_query (domain, question_id, sql_text, created_by)
               VALUES (%s, %s, %s, 'seed') ON CONFLICT (question_id) DO NOTHING""",
            (domain, question, sql),
        )


def grant_readers(cur):
    """SELECT on mart.* and the readable meta objects for each reader role
    that exists. Objects are listed from the catalog rather than hard-coded,
    so one missing view cannot make the whole GRANT fail."""
    cur.execute(
        """SELECT quote_ident(n.nspname) || '.' || quote_ident(c.relname)
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE (n.nspname = 'mart' AND c.relkind IN ('m', 'v', 'r'))
               OR (n.nspname = 'meta' AND c.relname IN ('column_catalog', 'golden_query', 'etl_run_log'))"""
    )
    objects = [r[0] for r in cur.fetchall()]
    for role in READER_ROLES:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if not cur.fetchone():
            continue
        cur.execute(f"GRANT USAGE ON SCHEMA mart, meta TO {role}")
        if objects:
            cur.execute(f"GRANT SELECT ON {', '.join(objects)} TO {role}")


_SCHEMAS = ("meta", "core", "mart")


def _ensure_schemas():
    """Create meta/core/mart owned by the EIS read-write role.

    That role cannot create schemas itself: on both hosts the EIS tables live
    in the ckdo_dashboard database, owned by postgres, and eis_user has no
    CREATE on it (found on first dev deploy, 2026-09-24). The backend's own
    DATABASE_URL connects to that same database as its owner, so the schemas
    are created there with AUTHORIZATION set to the EIS role — which then
    owns everything inside and can grant on it. Doing it here rather than as
    a runbook GRANT is deliberate: a manual step is the one that gets missed
    on the next host."""
    rw = _rw()
    try:
        with rw.cursor() as cur:
            cur.execute("SELECT current_user, current_database()")
            eis_role, eis_db = cur.fetchone()
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (list(_SCHEMAS),))
            missing = [s for s in _SCHEMAS if s not in {r[0] for r in cur.fetchall()}]
            if not missing:
                return
            try:
                for s in missing:
                    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
                rw.commit()
                return
            except psycopg2.errors.InsufficientPrivilege:
                rw.rollback()
    finally:
        rw.close()

    owner = psycopg2.connect(settings.database_url)
    try:
        with owner.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != eis_db:
                raise RuntimeError(
                    f"{eis_role} cannot create schemas in {eis_db} and DATABASE_URL points elsewhere — "
                    f"run: CREATE SCHEMA meta AUTHORIZATION {eis_role}; (same for core, mart)"
                )
            for s in missing:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS {s} AUTHORIZATION "{eis_role}"')
        owner.commit()
        logger.info("[ebs_mart] created schemas %s owned by %s", missing, eis_role)
    finally:
        owner.close()


def ensure_mart_schema():
    """Startup entry point. Each step commits on its own, so a failure in a
    later step (say, the ETL log ALTER on a host where another role owns
    eis.etl_job_log) cannot roll back the schemas the tool server needs."""
    try:
        _ensure_schemas()
    except Exception as e:
        logger.warning("[ebs_mart] schema creation failed: %s", e)
    steps = [
        ("meta/core schemas", lambda cur: _exec_each(cur, _META_DDL + _CORE_DDL, "meta/core ddl")),
        ("etl_job_log columns", lambda cur: _exec_each(cur, _ETL_LOG_COLUMNS, "etl_job_log columns")),
        ("etl_run_log view", create_etl_run_log_view),
        ("marts", ensure_marts),
        ("catalog", sync_catalog),
        ("golden queries", seed_golden_queries),
        ("grants", grant_readers),
    ]
    conn = _rw()
    try:
        for label, step in steps:
            try:
                with conn.cursor() as cur:
                    step(cur)
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.warning("[ebs_mart] step %s failed: %s", label, e)
    finally:
        conn.close()


def refresh_marts(names: list[str] | None = None) -> dict[str, str]:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY for the given (default: all
    built) marts, then refresh catalog sample values. Returns name -> "ok" or
    the error text; one failing mart does not stop the others."""
    names = names or list(MART_SQL)
    out: dict[str, str] = {}
    conn = _rw()
    try:
        for name in names:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY mart.{name}")
                conn.commit()
                out[name] = "ok"
            except Exception as e:
                conn.rollback()
                out[name] = str(e).splitlines()[0]
                logger.warning("[ebs_mart] refresh mart.%s failed: %s", name, e)
        try:
            with conn.cursor() as cur:
                update_sample_values(cur, names)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning("[ebs_mart] sample values failed: %s", e)
    finally:
        conn.close()
    return out


def update_sample_values(cur, names: list[str]):
    """Distinct values of low-cardinality text columns into
    column_catalog.sample_values, so the model writes WHERE aging_bucket =
    '>90' instead of guessing '90+'. Codes, names and free text are skipped:
    too many values to help, and sample rows of names would leak data into
    the catalog."""
    keep_codes = {"currency_code", "hold_code", "organization_code"}
    for name in names:
        for col, dtype in mart_columns(cur, name):
            if not dtype.startswith(("text", "character varying")) or col in ("row_key", "description"):
                continue
            if col.endswith(("_name", "_desc", "_num", "_code", "_number")) and col not in keep_codes:
                continue
            cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM mart.{name}")
            if (cur.fetchone()[0] or 0) > 25:
                continue
            cur.execute(f"SELECT DISTINCT {col} FROM mart.{name} WHERE {col} IS NOT NULL ORDER BY 1 LIMIT 25")
            values = [r[0] for r in cur.fetchall()]
            cur.execute(
                "UPDATE meta.column_catalog SET sample_values = %s WHERE mart_name = %s AND column_name = %s",
                (values, name, col),
            )
