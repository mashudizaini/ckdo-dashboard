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
import json
from fastapi import APIRouter, Depends, Query
from typing import Optional
from pydantic import BaseModel
from app.dependencies import require_role, CurrentUser, Roles
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pac_service import PACService
from app.services.business_plan_service import BusinessPlanService
from app.services.business_plan_setup_service import BusinessPlanSetupService
from app.services.sales_plan_service import SalesPlanService
from app.services.ai_service import AIService
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


# ── Business Plan Setup (Schedule / Guideline / Outlook) ───────────────────────

class SetupPayload(BaseModel):
    id:           Optional[int]  = None
    setup_module: str            = "schedule"   # schedule | guideline | outlook
    plan_year:    int
    content:      dict           = {}
    status:       Optional[str]  = "draft"


@router.get("/setup-modules")
async def list_setup_modules(
    setup_module: Optional[str] = Query(None),
    plan_year:    Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List setup modules (schedule, guideline, outlook) filtered by year/module."""
    return await BusinessPlanSetupService().list_setup(db, setup_module, plan_year)


@router.get("/setup-modules/{setup_id}")
async def get_setup_module(
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single setup module document."""
    return await BusinessPlanSetupService().get_setup(db, setup_id)


@router.post("/setup-modules")
async def upsert_setup_module(
    body: SetupPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update setup module document."""
    return await BusinessPlanSetupService().upsert_setup(db, body.model_dump(), user.username)


@router.delete("/setup-modules/{setup_id}")
async def delete_setup_module(
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete setup module document."""
    return await BusinessPlanSetupService().delete_setup(db, setup_id)


class GenerateOutlookRequest(BaseModel):
    year: int
    context: Optional[str] = None


@router.post("/setup-modules/generate-outlook")
async def generate_outlook(
    body: GenerateOutlookRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """
    Generate Business Plan Outlook content using AI based on the selected year.
    Returns structured outlook data that can be saved via upsert.
    """
    ai = AIService()
    prompt = f"""Generate a comprehensive Business Plan Outlook for PT CKD OTTO Pharmaceuticals for year {body.year}.
{f'Additional context: {body.context}' if body.context else ''}

Return ONLY valid JSON with this exact structure:
{{
  "global_economic": {{
    "title": "I. Global Economic Outlook",
    "items": [
      {{"label": "Global GDP Forecast", "value": "..."}},
      {{"label": "Key Factor 1", "value": "..."}},
      {{"label": "Key Factor 2", "value": "..."}},
      {{"label": "Fed Interest Rate", "value": "..."}},
      {{"label": "Global Inflation", "value": "..."}}
    ]
  }},
  "indonesia_economic": {{
    "title": "II. Indonesia Economic Outlook",
    "items": [
      {{"label": "GDP Forecast", "value": "..."}},
      {{"label": "Inflation", "value": "..."}},
      {{"label": "Interest Rate", "value": "..."}},
      {{"label": "Exchange Rate", "value": "..."}},
      {{"label": "Government Focus", "value": "..."}}
    ]
  }},
  "pharmaceutical": {{
    "title": "III. Pharmaceutical Industry",
    "items": [
      {{"label": "Global Market", "value": "..."}},
      {{"label": "Indonesia Market", "value": "..."}},
      {{"label": "Oncology", "value": "..."}},
      {{"label": "CKD OTTO Strategy", "value": "..."}}
    ]
  }}
}}

Make it realistic for {body.year} with specific numbers and trends. Keep values concise but informative."""

    try:
        response = await ai.generate_chat_completion([
            {"role": "system", "content": "You are a business analyst. Return only valid JSON, no markdown, no explanations."},
            {"role": "user", "content": prompt}
        ])
        content = json.loads(response)
        return {"success": True, "data": {"setup_module": "outlook", "plan_year": body.year, "content": content, "status": "draft"}}
    except Exception as e:
        return {"success": False, "error": f"Failed to generate outlook: {str(e)}", "data": None}


# ── Sales Plan ────────────────────────────────────────────────────────────────

class SalesPlanPayload(BaseModel):
    id:          Optional[int]  = None
    plan_year:   int
    department:  str            = ""
    team_code:   str            = ""
    team_name:   str            = ""
    plan_type:   str            = "value"   # value | unit
    content:     dict           = {}
    status:      Optional[str]  = "draft"


@router.get("/sales-plans")
async def list_sales_plans(
    plan_year:  Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    team_code:  Optional[str] = Query(None),
    plan_type:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """List sales plans filtered by year/department/team/type."""
    return await SalesPlanService().list_sales_plans(db, plan_year, department, team_code, plan_type)


@router.get("/sales-plans/{plan_id}")
async def get_sales_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Get single sales plan."""
    return await SalesPlanService().get_sales_plan(db, plan_id)


@router.post("/sales-plans")
async def upsert_sales_plan(
    body: SalesPlanPayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Create / update sales plan."""
    return await SalesPlanService().upsert_sales_plan(db, body.model_dump(), user.username)


@router.delete("/sales-plans/{plan_id}")
async def delete_sales_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Delete sales plan."""
    return await SalesPlanService().delete_sales_plan(db, plan_id)


@router.post("/sales-plans/{plan_id}/export")
async def export_sales_plan_excel(
    plan_id: int,
    plan_type: str = Query(..., description="value atau unit"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Export Sales Plan ke Excel (S1 Value atau S2 Unit)."""
    return await SalesPlanService().export_excel(db, plan_id, plan_type, user.username)


# ── Exchange Rates ─────────────────────────────────────────────────────────────

@router.get("/exchange-rates")
async def get_exchange_rates(
    refresh: bool = Query(False, description="Force re-scrape even if cache is fresh"),
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """Kurs Transaksi Bank Indonesia — scraped daily, cached 4 hours."""
    return await asyncio.to_thread(exchange_rate_service.get_rates, refresh)


class PushToEBSRequest(BaseModel):
    rate_date:   str        # "2026-07-03"
    rate_type:   str        = "Corporate"       # Corporate | Spot | user-defined
    rate_source: str        = "tengah"          # jual | beli | tengah
    currencies:  list[str]  = ["USD", "EUR", "SGD", "JPY", "GBP", "AUD", "CNY", "MYR"]


@router.post("/exchange-rates/push-to-ebs")
async def push_exchange_rates_to_ebs(
    body: PushToEBSRequest,
    user: CurrentUser = Depends(require_role(Roles.PAC)),
):
    """
    Push Kurs Transaksi BI ke Oracle EBS GL Daily Rates menggunakan
    GL_DAILY_RATES_API.INSERT_RATE / UPDATE_RATE.
    """
    # Get current cached rates (don't re-scrape unless cache is empty)
    cached = await asyncio.to_thread(exchange_rate_service.get_rates, False)
    if not cached.get("rates"):
        return {"success": False, "error": "Tidak ada data kurs — ambil data dari BI terlebih dahulu", "results": []}

    results = await asyncio.to_thread(
        exchange_rate_service.push_rates_to_ebs,
        cached["rates"],
        body.rate_date,
        body.rate_type,
        body.rate_source,
        body.currencies,
    )

    success_count = sum(1 for r in results if r["status"] == "success")
    error_count   = sum(1 for r in results if r["status"] == "error")
    return {
        "success":       error_count == 0,
        "rate_date":     body.rate_date,
        "rate_type":     body.rate_type,
        "rate_source":   body.rate_source,
        "total":         len(results),
        "success_count": success_count,
        "error_count":   error_count,
        "results":       results,
    }
