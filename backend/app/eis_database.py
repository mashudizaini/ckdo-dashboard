"""
EIS Postgres — SQLAlchemy Async connection for schema `eis`, which lives in
the main ckdo_dashboard database (moved there from the standalone
eis_dashboard database, now retired). A separate engine from
app/database.py because it connects as the EIS role (eis_user), not as the
database owner — see app/services/eis_tools.py for the read-only role the
Oracle EBS tool-calling chat uses.

Ported from eis-dashboard-v2/backend/app/database.py.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import get_settings

settings = get_settings()

eis_async_db_url = settings.eis_database_url_rw.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace("postgresql+psycopg2://", "postgresql+asyncpg://")

eis_async_engine = create_async_engine(
    eis_async_db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

EisAsyncSessionLocal = async_sessionmaker(
    eis_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_eis_db() -> AsyncSession:
    """FastAPI dependency — yields an EIS Postgres session."""
    async with EisAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ensure_upload_log_table():
    """Create eis.upload_log if missing — called once from the app lifespan.
    Same self-provisioning pattern as rag_service.ensure_schema(): the eis
    schema itself is bootstrapped externally (see sumber/eis-dashboard-v2/
    postgres/init.sql), but this table has no such precedent there, so the
    app creates it on its own rather than requiring a manual migration."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.upload_log (
                id             SERIAL PRIMARY KEY,
                upload_type    VARCHAR(50) NOT NULL,
                filename       VARCHAR(255),
                fiscal_year    INTEGER,
                rows_loaded    INTEGER,
                status         VARCHAR(20) NOT NULL DEFAULT 'success',
                error_message  TEXT,
                uploaded_by    VARCHAR(150),
                uploaded_at    TIMESTAMP DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_eis_upload_log_type_date "
            "ON eis.upload_log (upload_type, uploaded_at DESC)"
        ))


async def ensure_purchasing_table():
    """Create eis.fact_purchasing if missing — same self-provisioning
    reasoning as ensure_upload_log_table(): the eis schema's other fact_*
    tables were bootstrapped externally, but this one has no such
    precedent, so the app creates it on its own. Schema mirrors
    fact_budget's shape (period_id + one grouping dimension), populated by
    app.tasks.eis_etl_tasks.etl_po."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_purchasing (
                id             SERIAL PRIMARY KEY,
                period_id      INTEGER NOT NULL REFERENCES eis.dim_period(id),
                material_type  VARCHAR(30) NOT NULL,
                po_count       INTEGER DEFAULT 0,
                po_value       NUMERIC(18,2) DEFAULT 0,
                created_at     TIMESTAMPTZ DEFAULT now(),
                UNIQUE (period_id, material_type)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_purchasing_period "
            "ON eis.fact_purchasing (period_id)"
        ))


async def ensure_employee_dim_table():
    """Create eis.dim_employee if missing — a current-snapshot employee
    roster (one row per employee, mirrored 1:1 from the main app's own
    employees table on every etl_employee run), not a period-keyed fact
    table like fact_employee. Sourced from employees (ckdo_dashboard DB,
    Excel-uploaded via Employee Data) rather than Oracle HR — Oracle's own
    org hierarchy carries no usable department/division/team info in this
    instance (every employee's hr_all_organization_units row is the same
    single top-level "CKDO BG" business group, and position titles are
    free text with nothing structured to key off), whereas employees
    already has the correct, already-migrated classification the rest of
    the app relies on (see app/services/department_taxonomy.py)."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.dim_employee (
                id                 SERIAL PRIMARY KEY,
                employee_number    VARCHAR(30) NOT NULL UNIQUE,
                full_name          VARCHAR(200),
                sex                VARCHAR(10),
                position_title     VARCHAR(200),
                department         VARCHAR(50),
                division           VARCHAR(100),
                team               VARCHAR(100),
                hire_date          DATE,
                employment_status  VARCHAR(20),
                updated_at         TIMESTAMPTZ DEFAULT now()
            )
        """))
        # Pre-existing deployments (created before `division` was added)
        # need this backfilled explicitly — CREATE TABLE IF NOT EXISTS is a
        # no-op once the table already exists.
        await conn.execute(text(
            "ALTER TABLE eis.dim_employee ADD COLUMN IF NOT EXISTS division VARCHAR(100)"
        ))
        # resign_date/resign_reason: added after a user caught EBS Chat
        # claiming "the system doesn't store resign dates" — it does, in
        # employees.resign_date, but dim_employee never mirrored it.
        await conn.execute(text(
            "ALTER TABLE eis.dim_employee ADD COLUMN IF NOT EXISTS resign_date DATE"
        ))
        await conn.execute(text(
            "ALTER TABLE eis.dim_employee ADD COLUMN IF NOT EXISTS resign_reason TEXT"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_dim_employee_department "
            "ON eis.dim_employee (department)"
        ))


async def ensure_purchasing_migration_tables():
    """Create eis.fact_po_line and eis.fact_open_pr if missing — same
    self-provisioning pattern as the others above. Backs the migrated
    (Postgres-instead-of-live-Oracle) Purchasing History, Price Analysis
    and Open PR reports in purchasing_service.py; populated by
    app.tasks.eis_etl_tasks.etl_po_lines / etl_open_pr."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_po_line (
                id                 SERIAL PRIMARY KEY,
                po_number          VARCHAR(30) NOT NULL,
                line_num           INTEGER NOT NULL,
                item_code          VARCHAR(60),
                item_description   VARCHAR(500),
                category           VARCHAR(60),
                item_type          VARCHAR(30),
                material_type      VARCHAR(30),
                organization_id    NUMERIC,
                organization_name  VARCHAR(200),
                supplier_name      VARCHAR(200),
                buyer_name         VARCHAR(200),
                manufacturer_name  VARCHAR(200),
                country_of_origin  VARCHAR(100),
                currency_code      VARCHAR(10),
                uom                VARCHAR(20),
                quantity           NUMERIC(18,4),
                unit_price         NUMERIC(18,4),
                unit_price_idr     NUMERIC(18,4),
                amount_orig        NUMERIC(18,2),
                amount_idr         NUMERIC(18,2),
                received_qty       NUMERIC(18,4),
                creation_date      DATE,
                closure_status     VARCHAR(30),
                pr_number          VARCHAR(30),
                pr_date            DATE,
                requestor          VARCHAR(100),
                delivery_date      DATE,
                receipt_number     VARCHAR(30),
                receipt_date       TIMESTAMP,
                qty_outstanding    NUMERIC(18,4),
                payment_term       VARCHAR(60),
                updated_at         TIMESTAMPTZ DEFAULT now(),
                UNIQUE (po_number, line_num)
            )
        """))
        # Migration for tables created before the PR/receiving/payment-term
        # columns existed (see etl_po_lines's docstring for the full
        # sourcing/verification trail).
        for _col_sql in (
            "ADD COLUMN IF NOT EXISTS pr_number VARCHAR(30)",
            "ADD COLUMN IF NOT EXISTS pr_date DATE",
            "ADD COLUMN IF NOT EXISTS requestor VARCHAR(100)",
            "ADD COLUMN IF NOT EXISTS delivery_date DATE",
            "ADD COLUMN IF NOT EXISTS receipt_number VARCHAR(30)",
            "ADD COLUMN IF NOT EXISTS receipt_date TIMESTAMP",
            "ADD COLUMN IF NOT EXISTS qty_outstanding NUMERIC(18,4)",
            "ADD COLUMN IF NOT EXISTS payment_term VARCHAR(60)",
        ):
            await conn.execute(text(f"ALTER TABLE eis.fact_po_line {_col_sql}"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_po_line_creation_date "
            "ON eis.fact_po_line (creation_date)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_po_line_item_code "
            "ON eis.fact_po_line (item_code)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_po_line_supplier "
            "ON eis.fact_po_line (supplier_name)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_open_pr (
                id                     SERIAL PRIMARY KEY,
                pr_number              VARCHAR(30) NOT NULL,
                line_num               INTEGER NOT NULL,
                po_number              VARCHAR(30),
                item_code              VARCHAR(60),
                item_description       VARCHAR(500),
                category_code          VARCHAR(60),
                category_name          VARCHAR(500),
                material_type          VARCHAR(30),
                requestor              VARCHAR(300),
                uom                    VARCHAR(20),
                quantity               NUMERIC(18,4),
                currency_code          VARCHAR(10),
                unit_price_orig        NUMERIC(18,4),
                unit_price_idr         NUMERIC(18,4),
                total_value_orig       NUMERIC(18,2),
                total_value_idr        NUMERIC(18,2),
                pr_status              VARCHAR(30),
                creation_date          DATE,
                due_date               DATE,
                aging_basis_date       DATE,
                supplier_name          VARCHAR(300),
                payment_terms          VARCHAR(300),
                last_purchase_price    NUMERIC(18,4),
                last_purchase_currency VARCHAR(10),
                updated_at             TIMESTAMPTZ DEFAULT now(),
                UNIQUE (pr_number, line_num)
            )
        """))
        # Pre-existing deployments (created before these columns were
        # widened, e.g. category_name past a real Oracle description
        # exceeding 200 chars) need this applied explicitly — CREATE TABLE
        # IF NOT EXISTS is a no-op once the table already exists.
        for col, width in (("category_name", 500), ("requestor", 300), ("supplier_name", 300), ("payment_terms", 300)):
            await conn.execute(text(f"ALTER TABLE eis.fact_open_pr ALTER COLUMN {col} TYPE VARCHAR({width})"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_open_pr_requestor "
            "ON eis.fact_open_pr (requestor)"
        ))


async def ensure_sales_order_table():
    """Create eis.fact_sales_order if missing — foundation table for the
    Sales & Marketing dashboard (see the "Blueprint Sales & Marketing"
    plan: Open Sales Order now, Top Customers/Price Realization/On-Time
    Delivery etc. later, all reading from this same table). Populated by
    app.tasks.eis_etl_tasks.etl_sales_orders."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_sales_order (
                id                    SERIAL PRIMARY KEY,
                order_number          VARCHAR(30) NOT NULL,
                line_num              INTEGER NOT NULL,
                shipment_num          INTEGER NOT NULL DEFAULT 1,
                item_code             VARCHAR(60),
                item_description      VARCHAR(500),
                business_type         VARCHAR(20),
                customer_name         VARCHAR(300),
                organization_name     VARCHAR(200),
                currency_code         VARCHAR(10),
                uom                   VARCHAR(20),
                quantity              NUMERIC(18,4),
                unit_selling_price    NUMERIC(18,4),
                unit_list_price       NUMERIC(18,4),
                amount_orig           NUMERIC(18,2),
                amount_idr            NUMERIC(18,2),
                schedule_ship_date    DATE,
                actual_shipment_date  DATE,
                flow_status_code      VARCHAR(30),
                ordered_date          DATE,
                salesrep_id           NUMERIC,
                sold_to_org_id        NUMERIC,
                ship_from_org_id      NUMERIC,
                updated_at            TIMESTAMPTZ DEFAULT now(),
                UNIQUE (order_number, line_num, shipment_num)
            )
        """))
        # Migration for tables created before shipment_num existed: Oracle
        # OM splits one order line into multiple oe_order_lines_all rows
        # sharing the same line_number when it ships in partial batches,
        # distinguished only by shipment_number. The old (order_number,
        # line_num) key collapsed those into one upserted row, silently
        # discarding the other shipments' amount — found live as a ~25%
        # undercount on Local orders for April 2026 vs fact_sales.
        await conn.execute(text(
            "ALTER TABLE eis.fact_sales_order "
            "ADD COLUMN IF NOT EXISTS shipment_num INTEGER NOT NULL DEFAULT 1"
        ))
        await conn.execute(text(
            "ALTER TABLE eis.fact_sales_order "
            "DROP CONSTRAINT IF EXISTS fact_sales_order_order_number_line_num_key"
        ))
        # Plain ADD CONSTRAINT has no IF NOT EXISTS form in Postgres — a
        # bare version of this crashed app startup on the second restart
        # after it was first added, since the constraint already existed
        # by then (DuplicateTableError, non-idempotent = the whole
        # backend went down). Guard it explicitly instead.
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fact_sales_order_order_number_line_num_shipment_num_key'
                ) THEN
                    ALTER TABLE eis.fact_sales_order
                    ADD CONSTRAINT fact_sales_order_order_number_line_num_shipment_num_key
                    UNIQUE (order_number, line_num, shipment_num);
                END IF;
            END $$;
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_sales_order_ordered_date "
            "ON eis.fact_sales_order (ordered_date)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_sales_order_status "
            "ON eis.fact_sales_order (flow_status_code)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_sales_order_customer "
            "ON eis.fact_sales_order (customer_name)"
        ))


async def ensure_inventory_txn_table():
    """Create eis.fact_inventory_txn if missing — foundation table for the
    PPWH dashboard (Inventory In, Inventory Out, Kartu Stok). Populated by
    app.tasks.eis_etl_tasks.etl_inventory_txn. Keys on Oracle's own
    transaction_id — no composite-key grain risk like fact_sales_order
    had before its shipment_num fix."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_inventory_txn (
                id                     SERIAL PRIMARY KEY,
                transaction_id         NUMERIC NOT NULL UNIQUE,
                transaction_date       TIMESTAMP,
                direction              VARCHAR(3),
                transaction_type_name  VARCHAR(100),
                item_code              VARCHAR(60),
                item_description       VARCHAR(500),
                organization_code      VARCHAR(20),
                organization_name      VARCHAR(200),
                subinventory_code      VARCHAR(30),
                subinventory_name      VARCHAR(200),
                quantity               NUMERIC(18,4),
                uom                    VARCHAR(20),
                transaction_reference  VARCHAR(300),
                source_type_id         NUMERIC,
                source_id              NUMERIC,
                updated_at             TIMESTAMPTZ DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_inventory_txn_date "
            "ON eis.fact_inventory_txn (transaction_date)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_inventory_txn_item "
            "ON eis.fact_inventory_txn (item_code)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_inventory_txn_direction "
            "ON eis.fact_inventory_txn (direction)"
        ))


async def ensure_batch_table():
    """Create eis.fact_batch if missing — foundation table for the
    Production dashboard (Batch Status, Batch Yield, Schedule Adherence).
    Populated by app.tasks.eis_etl_tasks.etl_batches. Keys on Oracle's
    own batch_id — no composite-key grain risk."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_batch (
                id                         SERIAL PRIMARY KEY,
                batch_id                   NUMERIC NOT NULL UNIQUE,
                batch_no                   VARCHAR(50),
                organization_id            NUMERIC,
                organization_name          VARCHAR(200),
                batch_status               NUMERIC,
                batch_status_name          VARCHAR(30),
                formula_id                 NUMERIC,
                product_item_code          VARCHAR(60),
                product_item_description   VARCHAR(500),
                product_uom                VARCHAR(20),
                product_plan_qty           NUMERIC(18,4),
                product_actual_qty         NUMERIC(18,4),
                plan_start_date            TIMESTAMP,
                actual_start_date          TIMESTAMP,
                due_date                   TIMESTAMP,
                plan_cmplt_date            TIMESTAMP,
                actual_cmplt_date          TIMESTAMP,
                updated_at                 TIMESTAMPTZ DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_batch_plan_start "
            "ON eis.fact_batch (plan_start_date)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_batch_status "
            "ON eis.fact_batch (batch_status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_batch_product "
            "ON eis.fact_batch (product_item_code)"
        ))


async def ensure_daily_sales_table():
    """Create eis.fact_daily_sales if missing.

    Daily Sales is the one EIS dataset with no Oracle source: it is uploaded
    as Excel and kept as app/data/daily_sales.json, shaped for the dashboard
    grid rather than for querying. app.tasks.eis_etl_tasks.etl_daily_sales
    flattens it to one row per (year, month, working day) so a chat tool can
    ask for a single month.

    The unique key is the grain itself, which makes a re-run idempotent even
    though the job reloads wholesale."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_daily_sales (
                id           SERIAL PRIMARY KEY,
                fiscal_year  INTEGER NOT NULL,
                month_num    INTEGER NOT NULL,
                month_name   VARCHAR(12) NOT NULL,
                working_day  INTEGER NOT NULL,
                sales        NUMERIC(18,4),
                acc          NUMERIC(18,4),
                target       NUMERIC(18,4),
                as_of        VARCHAR(40),
                updated_at   TIMESTAMPTZ DEFAULT now(),
                CONSTRAINT uq_fact_daily_sales UNIQUE (fiscal_year, month_num, working_day)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_daily_sales_period "
            "ON eis.fact_daily_sales (fiscal_year, month_num, working_day)"
        ))
        for role in ("chat_readonly", "ebs_chat_reader"):
            await conn.execute(text(f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        GRANT USAGE ON SCHEMA eis TO {role};
                        GRANT SELECT ON eis.fact_daily_sales TO {role};
                    END IF;
                END
                $$;
            """))


async def ensure_it_monitoring_tables():
    """Create the eis.fact_it_* snapshot tables if missing.

    These are the only eis tables whose source is not Oracle EBS business
    data: they hold periodic snapshots of infrastructure health (Oracle
    tablespace headroom, server CPU/memory, filesystem usage, active Oracle
    sessions and pending concurrent requests), written by
    app.tasks.eis_etl_tasks.etl_it_monitoring and read by eis_tools' IT
    tools so CoChat can answer questions like "tablespace mana yang di atas
    90%".

    They live here rather than being queried live per question for two
    reasons. The tool contract in eis_tools is one predefined SELECT against
    this database — reaching out to Oracle or SSH from inside a tool-calling
    loop would put production load behind an LLM that may call a tool
    several times per answer. And snapshots answer the questions live
    queries cannot: which tablespace is growing fastest, when a mount
    started filling up. Same reasoning, and same 15-minute cadence, as
    etl_open_pr.

    Every table is append-only and carries captured_at; the tools read the
    newest snapshot by default. Retention is left to a later decision rather
    than assumed — at 15-minute granularity these grow slowly (a few hundred
    rows a day) and the history is the point."""
    from sqlalchemy import text
    async with eis_async_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_it_tablespace (
                id                SERIAL PRIMARY KEY,
                captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                tablespace_name   VARCHAR(60) NOT NULL,
                used_pct          NUMERIC(6,2),
                used_gb           NUMERIC(14,2),
                allocated_gb      NUMERIC(14,2),
                max_gb            NUMERIC(14,2),
                autoextensible    BOOLEAN,
                status            VARCHAR(20),
                contents          VARCHAR(20)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_tablespace_captured "
            "ON eis.fact_it_tablespace (captured_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_tablespace_name "
            "ON eis.fact_it_tablespace (tablespace_name, captured_at DESC)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_it_server_metrics (
                id             SERIAL PRIMARY KEY,
                captured_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                server_key     VARCHAR(20) NOT NULL,
                server_label   VARCHAR(60),
                server_ip      VARCHAR(45),
                status         VARCHAR(20),
                cpu_pct        NUMERIC(6,2),
                cpu_count      INTEGER,
                memory_pct     NUMERIC(6,2),
                memory_used_gb NUMERIC(10,2),
                memory_total_gb NUMERIC(10,2),
                swap_pct       NUMERIC(6,2),
                load_1         NUMERIC(8,2),
                uptime         VARCHAR(120),
                error_message  TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_server_metrics_captured "
            "ON eis.fact_it_server_metrics (server_key, captured_at DESC)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_it_disk_usage (
                id            SERIAL PRIMARY KEY,
                captured_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                server_key    VARCHAR(20) NOT NULL,
                server_label  VARCHAR(60),
                mount_point   VARCHAR(200) NOT NULL,
                filesystem    VARCHAR(200),
                size_gb       NUMERIC(14,2),
                used_gb       NUMERIC(14,2),
                avail_gb      NUMERIC(14,2),
                used_pct      NUMERIC(6,2)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_disk_captured "
            "ON eis.fact_it_disk_usage (captured_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_disk_mount "
            "ON eis.fact_it_disk_usage (server_key, mount_point, captured_at DESC)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eis.fact_it_oracle_activity (
                id                 SERIAL PRIMARY KEY,
                captured_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
                active_sessions    INTEGER,
                inactive_sessions  INTEGER,
                blocked_sessions   INTEGER,
                pending_requests   INTEGER,
                running_requests   INTEGER,
                top_wait_event     VARCHAR(120)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fact_it_oracle_activity_captured "
            "ON eis.fact_it_oracle_activity (captured_at DESC)"
        ))

        # Read grants for the two chat roles, applied here rather than left to
        # the runbook. The tables are created by this app on every startup, so
        # a grant that lives only in a separate manual step is a grant that
        # will be missing the first time anyone deploys this somewhere new —
        # which is exactly how it failed on dev: the model picked the right
        # tool, called it correctly, and got "permission denied".
        #
        # chat_readonly serves the Dashboard's own internal EBS chat,
        # ebs_chat_reader serves CoChat. Both are SELECT-only by design (see
        # eis_tools' module docstring); nothing here widens that.
        #
        # Guarded on pg_roles because neither role is guaranteed to exist in
        # every environment, and a missing role must not abort startup.
        # fact_it_grants
        for role in ("chat_readonly", "ebs_chat_reader"):
            await conn.execute(text(f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        GRANT USAGE ON SCHEMA eis TO {role};
                        GRANT SELECT ON eis.fact_it_tablespace,
                                        eis.fact_it_server_metrics,
                                        eis.fact_it_disk_usage,
                                        eis.fact_it_oracle_activity
                              TO {role};
                    END IF;
                END
                $$;
            """))
