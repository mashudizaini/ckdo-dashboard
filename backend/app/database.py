import os
import oracledb
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
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

# Sync engine on the same main DB — for APScheduler background jobs, which
# run in a plain thread (not the asyncio event loop) and follow the sync
# SessionLocal pattern already used by vpn_monitor_scheduler.py /
# ebs_backup/scheduler.py (those poll their own dedicated DBs; this is the
# equivalent for jobs that need to write to the main DB, e.g. AttendanceRecord).
sync_engine = create_engine(settings.database_url, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=sync_engine)


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


def ensure_oracle_env_table():
    """Single-row table holding which Oracle instance the whole app is
    currently pointed at — Production or Development. One shared flag (not
    per-user): the backend's Oracle connection is one resource, so the
    toggle in the sidebar switches it for everyone at once."""
    try:
        with sync_engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS oracle_env_setting (
                    id          INTEGER PRIMARY KEY DEFAULT 1,
                    environment VARCHAR(20) NOT NULL DEFAULT 'production',
                    updated_by  VARCHAR(100),
                    updated_at  TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT single_row CHECK (id = 1)
                )
            """))
            conn.execute(text("""
                INSERT INTO oracle_env_setting (id, environment)
                VALUES (1, 'production')
                ON CONFLICT (id) DO NOTHING
            """))
    except Exception as e:
        logger.warning("Failed to ensure oracle_env_setting table", error=str(e))


def get_oracle_environment() -> dict:
    """Returns {"environment": "production"|"development", "updated_by":
    ..., "updated_at": ...}. Defaults to production on any failure — never
    silently fail open to Development, which could mask why real Oracle
    submissions aren't appearing."""
    try:
        with sync_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT environment, updated_by, updated_at FROM oracle_env_setting WHERE id = 1"
            )).fetchone()
        if row:
            return {"environment": row[0], "updated_by": row[1], "updated_at": row[2].isoformat() if row[2] else None}
    except Exception as e:
        logger.warning("Failed to read oracle_env_setting — defaulting to production", error=str(e))
    return {"environment": "production", "updated_by": None, "updated_at": None}


def set_oracle_environment(environment: str, updated_by: str) -> dict:
    if environment not in ("production", "development"):
        raise ValueError("environment must be 'production' or 'development'")
    with sync_engine.begin() as conn:
        conn.execute(text("""
            UPDATE oracle_env_setting
            SET environment = :env, updated_by = :by, updated_at = NOW()
            WHERE id = 1
        """), {"env": environment, "by": updated_by})
    return get_oracle_environment()


def get_oracle_connection():
    """
    Returns a synchronous Oracle connection to whichever instance
    (Production or Development) is currently selected via the sidebar
    toggle — re-read on every call, so a switch takes effect on the very
    next Oracle-backed request without a backend restart.
    Use inside services/tasks only — not directly in async routes.
    Always use as context manager:

        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            ...
    """
    init_oracle_client()  # idempotent — re-runs after uvicorn hot-reload resets module state
    env = get_oracle_environment()["environment"]
    if env == "development":
        host, port, service, user, password = (
            settings.oracle_dev_host, settings.oracle_dev_port, settings.oracle_dev_service,
            settings.oracle_dev_user, settings.oracle_dev_password,
        )
    else:
        host, port, service, user, password = (
            settings.oracle_prod_host, settings.oracle_prod_port, settings.oracle_prod_service,
            settings.oracle_prod_user, settings.oracle_prod_password,
        )
    return oracledb.connect(
        user=user,
        password=password,
        dsn=f"{host}:{port}/{service}",
    )
