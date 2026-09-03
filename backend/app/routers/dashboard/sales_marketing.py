"""
Sales & Marketing Dashboard Router
Route prefix : /api/v1/dashboard/sales

No dedicated Keycloak role exists for this team yet — open to any
authenticated user, same convention as general.py, until one is set up
(see Sidebar.jsx's NAV_ITEMS comment for the Sales & Marketing entry).
"""
from typing import Optional
from fastapi import APIRouter, Query, Depends
from app.dependencies import get_current_user, CurrentUser
from app.services.sales_marketing_service import SalesMarketingService

router = APIRouter()
service = SalesMarketingService()


@router.get("/years")
async def get_years(user: CurrentUser = Depends(get_current_user)):
    return await service.get_years()


@router.get("/trend")
async def get_trend(
    year: int = Query(...),
    business_type: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    """Serves both the Sales Trend and Sales vs Budget tabs — same data,
    charted two different ways on the frontend."""
    data = await service.get_trend(year, business_type)
    return {"success": True, "data": data}


@router.get("/open-orders")
async def get_open_orders(
    customer_name: Optional[str] = Query(None),
    business_type: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    return await service.get_open_orders(customer_name, business_type, item_code)
