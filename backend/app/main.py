from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from app.config import get_settings
from app.database import async_engine, Base, init_oracle_client
import app.models.employee    # noqa: F401 — register models ke Base.metadata
import app.models.attendance   # noqa: F401 — register models ke Base.metadata

# ── Dashboard Routers ──
from app.routers.dashboard import it, hr, pac, accounting, purchasing, ap_invoice

# ── Coretax Router ──
from app.routers.coretax_router import coretax_router

# ── AI Tools Routers ──
from app.routers.ai_tools import chatbot, meeting_notes

# ── Util Routers ──
from app.routers import health

logger = structlog.get_logger()
settings = get_settings()


# ─────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting CKDO Dashboard API", environment=settings.environment)

    # Create PostgreSQL tables (dev only — use Alembic in production)
    if settings.environment == "development":
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Initialize Oracle Thick Mode
    init_oracle_client()

    # Create AP Invoice staging table (psycopg2 sync)
    from app.routers.dashboard.ap_invoice import ensure_staging_table
    ensure_staging_table()

    yield

    logger.info("Shutting down CKDO Dashboard API")
    await async_engine.dispose()


# ─────────────────────────────────────────
# APP INSTANCE
# ─────────────────────────────────────────

app = FastAPI(
    title="CKDO Dashboard API",
    version="2.0.0",
    description="PT CKD OTTO Pharmaceuticals — Internal Dashboard API",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None,
    lifespan=lifespan,
)


# ─────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# ROUTERS
# ─────────────────────────────────────────
# Pattern: /api/v1/{domain}/{resource}
#
# Untuk menambahkan modul baru:
#   1. Buat file router di app/routers/dashboard/nama_modul.py
#   2. Buat service di app/services/nama_modul_service.py
#   3. Daftarkan di sini dengan prefix & tags yang sesuai
# ─────────────────────────────────────────

API_PREFIX = "/api/v1"

# Health check (public)
app.include_router(health.router, prefix=API_PREFIX, tags=["Health"])

# Dashboard modules
app.include_router(it.router,         prefix=f"{API_PREFIX}/dashboard/it",         tags=["Dashboard - IT"])
app.include_router(hr.router,         prefix=f"{API_PREFIX}/dashboard/hr",         tags=["Dashboard - HR"])
app.include_router(pac.router,        prefix=f"{API_PREFIX}/dashboard/pac",        tags=["Dashboard - PAC"])
app.include_router(accounting.router, prefix=f"{API_PREFIX}/dashboard/accounting", tags=["Dashboard - Accounting"])
app.include_router(ap_invoice.router,  prefix=f"{API_PREFIX}/dashboard/accounting/ap-invoice", tags=["Dashboard - AP Invoice"])
app.include_router(purchasing.router, prefix=f"{API_PREFIX}/dashboard/purchasing", tags=["Dashboard - Purchasing"])

# AI Tools
app.include_router(chatbot.router,       prefix=f"{API_PREFIX}/ai/chatbot",       tags=["AI - Chatbot"])
app.include_router(meeting_notes.router, prefix=f"{API_PREFIX}/ai/meeting-notes", tags=["AI - Meeting Notes"])

# Coretax Bulk Downloader (prefix already set in router: /api/coretax)
app.include_router(coretax_router)
