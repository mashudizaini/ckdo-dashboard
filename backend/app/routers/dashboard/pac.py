"""
PAC Dashboard Router
Route prefix : /api/v1/dashboard/pac
Required role: pac_staff OR admin

Endpoints:
  GET  /summary
  GET  /budget-usage              — Actual vs Budget per period/cost-center
  GET  /lov/ledgers               — GL ledger LOV
  GET  /business-plans            — List business plan documents
  GET  /business-plans/{id}       — Get single document
  POST /business-plans            — Create / update document (upsert)
  DELETE /business-plans/{id}     — Delete document
"""
import asyncio
from fastapi import APIRouter, Depends, Query
from typing import Optional
from pydantic import BaseModel
from app.dependencies import require_role, CurrentUser, Roles
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pac_service import PACService
from app.services.business_plan_service import BusinessPlanService
from app.services import exchange_rate_service

router = APIRouter()


@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.PAC))):
    return {"module": "pac", "status": "ready"}


@router.get("/budget-usage")
async def get_budget_usage(
    year:         Optional[int] = Query(None),
    month:        Optional[int] = Query(None),
    cost_center:  Optional[str] = Query(None),
    account_type: Optional[str] = Query(None),
    ledger_id:    Optional[int] = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Actual vs Business Plan (Budget) per cost center per GL period."""
    filters = dict(year=year, month=month, cost_center=cost_center,
                   account_type=account_type, ledger_id=ledger_id)
    return await PACService().get_budget_usage(filters)


@router.get("/lov/ledgers")
async def get_ledgers(user: CurrentUser = Depends(require_role(Roles.PAC))):
    return await PACService().get_ledgers()


# ── Business Plan ─────────────────────────────────────────────────────────────

class BusinessPlanPayload(BaseModel):
    id:          Optional[int]  = None
    doc_type:    str            = "strategy_plan"   # managerial_obj | strategy_plan
    plan_year:   int
    department:  Optional[str]  = "ALL"
    team_code:   Optional[str]  = ""
    team_name:   Optional[str]  = ""
    plan_role:   Optional[str]  = ""
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/business-plans")
async def list_business_plans(
    plan_year:  Optional[int] = Query(None),
    doc_type:   Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().list_plans(db, plan_year, doc_type, department)


@router.get("/business-plans/{plan_id}")
async def get_business_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().get_plan(db, plan_id)


@router.post("/business-plans")
async def upsert_business_plan(
    body: BusinessPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().upsert_plan(db, body.model_dump(), user.username)


@router.delete("/business-plans/{plan_id}")
async def delete_business_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    return await BusinessPlanService().delete_plan(db, plan_id)


# ── Exchange Rates ─────────────────────────────────────────────────────────────

@router.get("/exchange-rates")
async def get_exchange_rates(
    refresh: bool = Query(False, description="Force re-scrape even if cache is fresh"),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Kurs Transaksi Bank Indonesia — scraped daily, cached 4 hours."""
    return await asyncio.to_thread(exchange_rate_service.get_rates, refresh)
