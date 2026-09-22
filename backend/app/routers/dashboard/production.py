"""
Production Dashboard Router — Batch Status / Batch Yield / Schedule Adherence
Route prefix : /api/v1/dashboard/production

No dedicated Keycloak role exists for this team yet — open to any
authenticated user, same convention as general.py / sales_marketing.py /
ppwh.py.
"""
from typing import Optional
from fastapi import APIRouter, Query, Depends
from app.dependencies import get_current_user, CurrentUser
from app.services.production_service import ProductionService

router = APIRouter()
service = ProductionService()


@router.get("/organizations")
async def get_organizations(user: CurrentUser = Depends(get_current_user)):
    return await service.get_organizations()


@router.get("/status-overview")
async def get_status_overview(
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_status_overview(date_from, date_to, organization_id)


@router.get("/yield")
async def get_yield(
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_id: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_yield(date_from, date_to, organization_id, product_code)


@router.get("/schedule-adherence")
async def get_schedule_adherence(
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_schedule_adherence(date_from, date_to, organization_id)
