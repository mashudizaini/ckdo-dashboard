"""
PPWH Dashboard Router — Inventory In / Inventory Out / Kartu Stok
Route prefix : /api/v1/dashboard/ppwh

No dedicated Keycloak role exists for this team yet — open to any
authenticated user, same convention as general.py / sales_marketing.py.
"""
from typing import Optional
from fastapi import APIRouter, Query, Depends
from app.dependencies import get_current_user, CurrentUser
from app.services.ppwh_service import PPWHService

router = APIRouter()
service = PPWHService()


@router.get("/organizations")
async def get_organizations(user: CurrentUser = Depends(get_current_user)):
    return await service.get_organizations()


@router.get("/inbound")
async def get_inbound(
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_code: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_inbound(date_from, date_to, organization_code)


@router.get("/outbound")
async def get_outbound(
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_code: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_outbound(date_from, date_to, organization_code)


@router.get("/items")
async def search_items(
    q: str = Query(..., min_length=1),
    user: CurrentUser = Depends(get_current_user),
):
    data = await service.search_items(q)
    return {"success": True, "data": data}


@router.get("/stock-card")
async def get_stock_card(
    item_code: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_code: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_stock_card(item_code, date_from, date_to, organization_code)
