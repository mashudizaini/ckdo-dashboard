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
