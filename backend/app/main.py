from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog

from app.config import get_settings
from app.database import async_engine, Base, init_oracle_client
from app.dependencies import require_role, Roles
import app.models.employee    # noqa: F401 — register models ke Base.metadata
import app.models.attendance   # noqa: F401 — register models ke Base.metadata
import app.models.leave        # noqa: F401
import app.models.working_calendar  # noqa: F401
import app.models.hrga_task    # noqa: F401
import app.models.cv_screening  # noqa: F401
import app.models.business_plan  # noqa: F401
import app.models.business_plan_setup  # noqa: F401
import app.models.sales_plan  # noqa: F401
import app.models.purchase_plan  # noqa: F401
import app.models.personnel_plan  # noqa: F401
import app.models.manufacture_plan  # noqa: F401
import app.models.investment_plan  # noqa: F401
import app.models.opex_plan  # noqa: F401
import app.models.db_browser_audit  # noqa: F401
import app.models.org_structure  # noqa: F401
import app.models.user_api_key  # noqa: F401
import app.models.meeting_recording  # noqa: F401
import app.models.outlook_material  # noqa: F401

# ── Dashboard Routers ──
from app.routers.dashboard import it, it_db_browser, hr, pac, accounting, purchasing, ap_invoice, financial_statement
from app.routers.dashboard import (
    eis_summary, eis_performance, eis_production, eis_expansion, eis_administration,
    eis_business_plan, eis_daily_sales, eis_data_upload, eis_etl_admin,
)

# ── Coretax Router ──
from app.routers.coretax_router import coretax_router

# ── AI Tools Routers ──
from app.routers.ai_tools import chatbot, meeting_notes, user_settings, document_converter

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

    # Create RAG chatbot schema (pgvector extension + company_documents table)
    from app.services import rag_service
    rag_service.ensure_schema()

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
# GLOBAL EXCEPTION HANDLER
# ─────────────────────────────────────────
# FastAPI only JSON-ifies HTTPException / validation errors by default — any
# other unhandled exception falls through to Starlette's plain-text 500,
# which breaks every frontend `res.json()` call ("Unexpected token '<'/'I'...").
# This guarantees every response is valid JSON.

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}" if settings.environment == "development" else "Internal server error"},
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
app.include_router(it_db_browser.router, prefix=f"{API_PREFIX}/dashboard/it/db-browser", tags=["Dashboard - IT DB Browser"])
app.include_router(hr.router,         prefix=f"{API_PREFIX}/dashboard/hr",         tags=["Dashboard - HR"])
app.include_router(pac.router,        prefix=f"{API_PREFIX}/dashboard/pac",        tags=["Dashboard - PAC"])
app.include_router(accounting.router, prefix=f"{API_PREFIX}/dashboard/accounting", tags=["Dashboard - Accounting"])
app.include_router(ap_invoice.router,  prefix=f"{API_PREFIX}/dashboard/accounting/ap-invoice", tags=["Dashboard - AP Invoice"])
app.include_router(financial_statement.router, prefix=f"{API_PREFIX}/dashboard/accounting/financial-statement", tags=["Dashboard - Financial Statement"])
app.include_router(purchasing.router, prefix=f"{API_PREFIX}/dashboard/purchasing", tags=["Dashboard - Purchasing"])

# EIS Dashboard — ported from the standalone eis-dashboard-v2 app.
# Viewing/editing gated to management (+ admin, always implicitly allowed by
# require_role); ETL Admin is gated separately to it_staff on its own routes
# since triggering/monitoring ETL jobs is an IT/ops concern, not a management
# viewing one.
_eis_mgmt = [Depends(require_role(Roles.MANAGEMENT))]
app.include_router(eis_summary.router,        prefix=f"{API_PREFIX}/dashboard/eis/summary",     tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_performance.router,    prefix=f"{API_PREFIX}/dashboard/eis/performance", tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_production.router,     prefix=f"{API_PREFIX}/dashboard/eis/production",  tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_expansion.router,      prefix=f"{API_PREFIX}/dashboard/eis/expansion",   tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_administration.router, prefix=f"{API_PREFIX}/dashboard/eis/admin",       tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_business_plan.router,  prefix=f"{API_PREFIX}/dashboard/eis/bp",          tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_daily_sales.router,    prefix=f"{API_PREFIX}/dashboard/eis/daily-sales", tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_data_upload.router,    prefix=f"{API_PREFIX}/dashboard/eis/data-upload", tags=["Dashboard - EIS"], dependencies=_eis_mgmt)
app.include_router(eis_etl_admin.router,      prefix=f"{API_PREFIX}/dashboard/eis/etl",         tags=["Dashboard - EIS"])

# AI Tools
app.include_router(chatbot.router,       prefix=f"{API_PREFIX}/ai/chatbot",       tags=["AI - Chatbot"])
app.include_router(meeting_notes.router, prefix=f"{API_PREFIX}/ai/meeting-notes", tags=["AI - Meeting Notes"])
app.include_router(user_settings.router, prefix=f"{API_PREFIX}/ai/settings",       tags=["AI - User Settings"])
app.include_router(document_converter.router, prefix=f"{API_PREFIX}/ai/document-converter", tags=["AI - Document Converter"])

# Coretax Bulk Downloader (prefix already set in router: /api/coretax)
app.include_router(coretax_router)
