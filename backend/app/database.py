import os
import oracledb
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()


# ─────────────────────────────────────────
# POSTGRESQL — SQLAlchemy Async
# ─────────────────────────────────────────

# Convert sync URL to async for asyncpg
async_db_url = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace("postgresql+psycopg2://", "postgresql+asyncpg://")

async_engine = create_async_engine(
    async_db_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a PostgreSQL session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────
# ORACLE EBS — oracledb Thick Mode
# ─────────────────────────────────────────

_oracle_initialized = False


def _prepare_oracle_lib_dir(source_dir: str) -> str:
    """
    Oracle Instant Client 12.x ships libclntsh.so.12.1 but NOT libclntsh.so.
    When the bind-mount filesystem is read-only (Windows NTFS via Docker),
    we create symlinks in /tmp/oracle_ic/ that point to the actual .so files.
    Returns the directory to pass to init_oracle_client().
    """
    import glob
    import re

    # If generic name already exists in source, use source directly
    if os.path.exists(os.path.join(source_dir, "libclntsh.so")):
        return source_dir

    tmp_dir = "/tmp/oracle_ic"
    os.makedirs(tmp_dir, exist_ok=True)

    # Create symlinks: libX.so.VER  → (actual file)
    #                  libX.so      → (same actual file)
    for so_file in glob.glob(os.path.join(source_dir, "*.so*")):
        basename = os.path.basename(so_file)
        lnk = os.path.join(tmp_dir, basename)
        if not os.path.lexists(lnk):
            os.symlink(so_file, lnk)
        # Generic name: strip version suffix
        generic = re.sub(r"\.so\..*$", ".so", basename)
        if generic != basename:
            generic_lnk = os.path.join(tmp_dir, generic)
            if not os.path.lexists(generic_lnk):
                os.symlink(so_file, generic_lnk)

    return tmp_dir if os.path.exists(os.path.join(tmp_dir, "libclntsh.so")) else source_dir


def init_oracle_client():
    """Initialize Oracle Thick Mode once at startup."""
    global _oracle_initialized
    if not _oracle_initialized:
        try:
            lib_dir = _prepare_oracle_lib_dir(settings.oracle_instant_client)
            oracledb.init_oracle_client(lib_dir=lib_dir)
            _oracle_initialized = True
            logger.info("Oracle Instant Client initialized (thick mode)", lib_dir=lib_dir)
        except Exception as e:
            logger.warning("Oracle client init failed — Oracle features disabled", error=str(e))


def get_oracle_connection():
    """
    Returns a synchronous Oracle connection.
    Use inside services/tasks only — not directly in async routes.
    Always use as context manager:

        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            ...
    """
    init_oracle_client()  # idempotent — re-runs after uvicorn hot-reload resets module state
    return oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=f"{settings.oracle_host}:{settings.oracle_port}/{settings.oracle_service}",
    )
