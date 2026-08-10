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
