"""
EIS Postgres — SQLAlchemy Async connection to the `eis_dashboard` database
(schema `eis`), separate from the main ckdo_dashboard database. This is the
same database the standalone eis-dashboard-v2 app and the Oracle EBS
tool-calling chat both use — see app/services/eis_tools.py for the
read-only connection used there.

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
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_dim_employee_department "
            "ON eis.dim_employee (department)"
        ))
