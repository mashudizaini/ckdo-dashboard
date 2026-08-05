"""
PURCHASING Dashboard Router
─────────────────────────────────────────
Route prefix : /api/v1/dashboard/purchasing
Required role: purchasing_staff OR admin

Endpoints:
  GET  /summary
  GET  /open-po
  GET  /monthly-spend
  GET  /active-suppliers

  GET  /purchase-history/detail       — Output 1: aggregated per item/year
  GET  /purchase-history/by-item      — Output 2: pivot by year per item
  GET  /purchase-history/by-supplier  — Output 3: pivot by year per supplier

  GET  /manufacturer-master           — list all records
  POST /manufacturer-master           — create new record
  DELETE /manufacturer-master/{id}    — delete record

  GET  /lov/organizations             — LOV: all active organizations
  GET  /lov/items?org_id=&search=     — LOV: items for an org (max 50)
  GET  /lov/categories                — LOV: purchasing categories
  GET  /lov/currencies                — LOV: currencies used in PO
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional
import httpx, os
from app.dependencies import require_role, CurrentUser, Roles
from app.services.purchasing_service import PurchasingService

# ── Metals.dev in-memory cache ────────────────────────────────────────────────
from datetime import datetime, timedelta
_metals_cache: dict = {}
_metals_history: list = []

router = APIRouter()


# ── Summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    return {"success": True, "data": {}}


# ── Section stubs (TODO: Oracle queries) ─────────────────────────────────────

@router.get("/open-pr")
async def get_open_pr(
    pr_status:          Optional[str] = Query(None),
    pr_number:          Optional[str] = Query(None),
    item_code:          Optional[str] = Query(None),
    item_desc:          Optional[str] = Query(None),
    requestor:          Optional[str] = Query(None),
    currency_code:      Optional[str] = Query(None),
    material_type:      Optional[str] = Query(None),
    date_from:          Optional[str] = Query(None),
    date_to:            Optional[str] = Query(None),
    exchange_rate_type: Optional[str] = Query("Corporate"),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """PR Approval Status report — from PO_REQUISITION_HEADERS/LINES_ALL."""
    filters = dict(
        pr_status=pr_status, pr_number=pr_number, item_code=item_code,
        item_desc=item_desc, requestor=requestor, currency_code=currency_code,
        material_type=material_type, date_from=date_from, date_to=date_to,
        exchange_rate_type=exchange_rate_type,
    )
    return await PurchasingService().get_open_pr(filters)



@router.get("/monthly-spend")
async def get_monthly_spend(
    org_id:             Optional[int] = Query(None),
    year_from:          Optional[int] = Query(None),
    year_to:            Optional[int] = Query(None),
    currency_code:      Optional[str] = Query(None),
    material_type:      Optional[str] = Query(None),
    exchange_rate_type: Optional[str] = Query("Corporate"),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    filters = dict(org_id=org_id, year_from=year_from, year_to=year_to,
                   currency_code=currency_code, material_type=material_type,
                   exchange_rate_type=exchange_rate_type)
    return await PurchasingService().get_monthly_spend(filters)


@router.get("/active-suppliers")
async def get_active_suppliers(
    org_id:             Optional[int] = Query(None),
    year_from:          Optional[int] = Query(None),
    year_to:            Optional[int] = Query(None),
    vendor_name:        Optional[str] = Query(None),
    material_type:      Optional[str] = Query(None),
    exchange_rate_type: Optional[str] = Query("Corporate"),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    filters = dict(org_id=org_id, year_from=year_from, year_to=year_to,
                   vendor_name=vendor_name, material_type=material_type,
                   exchange_rate_type=exchange_rate_type)
    return await PurchasingService().get_active_suppliers(filters)


# ── Purchase History ─────────────────────────────────────────────────────────

@router.get("/purchase-history/detail")
async def ph_detail(
    org_id:              Optional[int]   = Query(None),
    exchange_rate_type:  Optional[str]   = Query("Corporate"),
    date_from:           Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    date_to:             Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    item_code:           Optional[str]   = Query(None),
    item_desc:           Optional[str]   = Query(None),
    vendor_name:         Optional[str]   = Query(None),
    manufacturer:        Optional[str]   = Query(None),
    country_of_origin:   Optional[str]   = Query(None),
    category:            Optional[str]   = Query(None),
    currency_code:       Optional[str]   = Query(None),
    material_type:       Optional[str]   = Query(None),
    po_number:           Optional[str]   = Query(None),
    buyer:               Optional[str]   = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    filters = dict(org_id=org_id, exchange_rate_type=exchange_rate_type,
                   date_from=date_from, date_to=date_to, item_code=item_code,
                   item_desc=item_desc, vendor_name=vendor_name, manufacturer=manufacturer,
                   country_of_origin=country_of_origin, category=category,
                   currency_code=currency_code, material_type=material_type,
                   po_number=po_number, buyer=buyer)
    return await PurchasingService().get_purchase_history_detail(filters)


@router.get("/purchase-history/by-item")
async def ph_by_item(
    org_id:              Optional[int]   = Query(None),
    exchange_rate_type:  Optional[str]   = Query("Corporate"),
    date_from:           Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    date_to:             Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    item_code:           Optional[str]   = Query(None),
    item_desc:           Optional[str]   = Query(None),
    vendor_name:         Optional[str]   = Query(None),
    manufacturer:        Optional[str]   = Query(None),
    country_of_origin:   Optional[str]   = Query(None),
    category:            Optional[str]   = Query(None),
    currency_code:       Optional[str]   = Query(None),
    material_type:       Optional[str]   = Query(None),
    po_number:           Optional[str]   = Query(None),
    buyer:               Optional[str]   = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    filters = dict(org_id=org_id, exchange_rate_type=exchange_rate_type,
                   date_from=date_from, date_to=date_to, item_code=item_code,
                   item_desc=item_desc, vendor_name=vendor_name, manufacturer=manufacturer,
                   country_of_origin=country_of_origin, category=category,
                   currency_code=currency_code, material_type=material_type,
                   po_number=po_number, buyer=buyer)
    return await PurchasingService().get_purchase_history_by_item(filters)


@router.get("/purchase-history/by-supplier")
async def ph_by_supplier(
    org_id:              Optional[int]   = Query(None),
    exchange_rate_type:  Optional[str]   = Query("Corporate"),
    date_from:           Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    date_to:             Optional[str]   = Query(None, description="YYYY-MM-DD, based on PO Date"),
    item_code:           Optional[str]   = Query(None),
    item_desc:           Optional[str]   = Query(None),
    vendor_name:         Optional[str]   = Query(None),
    manufacturer:        Optional[str]   = Query(None),
    country_of_origin:   Optional[str]   = Query(None),
    category:            Optional[str]   = Query(None),
    currency_code:       Optional[str]   = Query(None),
    material_type:       Optional[str]   = Query(None),
    po_number:           Optional[str]   = Query(None),
    buyer:               Optional[str]   = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    filters = dict(org_id=org_id, exchange_rate_type=exchange_rate_type,
                   date_from=date_from, date_to=date_to, item_code=item_code,
                   item_desc=item_desc, vendor_name=vendor_name, manufacturer=manufacturer,
                   country_of_origin=country_of_origin, category=category,
                   currency_code=currency_code, material_type=material_type,
                   po_number=po_number, buyer=buyer)
    return await PurchasingService().get_purchase_history_by_supplier(filters)


# ── LOV ───────────────────────────────────────────────────────────────────────

@router.get("/lov/organizations")
async def get_organizations(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    """List of active Oracle organizations."""
    return await PurchasingService().get_organizations()


@router.get("/lov/items")
async def get_items(
    org_id: int = Query(..., description="Organization ID"),
    search: Optional[str] = Query(None, description="Item code search string"),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Search items in MTL_SYSTEM_ITEMS_B for given org (max 50 rows)."""
    return await PurchasingService().get_items(org_id, search or "")


@router.get("/lov/categories")
async def get_categories(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    return await PurchasingService().get_categories()


@router.get("/lov/currencies")
async def get_currencies(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    return await PurchasingService().get_currencies()


@router.get("/lov/material-types")
async def get_material_types(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    return await PurchasingService().get_material_types()


@router.get("/lov/requestors")
async def get_requestors(user: CurrentUser = Depends(require_role(Roles.PURCHASING))):
    """LOV: distinct Open PR requestors, for the multi-select checkbox filter."""
    return await PurchasingService().get_requestors()


# ── Manufacturer Master ───────────────────────────────────────────────────────

class ManufacturerIn(BaseModel):
    item_id: int
    organization_id: int
    item_code: str
    item_description: Optional[str] = ""
    manufacturer_name: str
    country_of_origin: Optional[str] = ""


@router.get("/manufacturer-master")
async def get_manufacturer_list(
    org_id:             Optional[int] = Query(None),
    item_code:          Optional[str] = Query(None),
    item_desc:          Optional[str] = Query(None),
    manufacturer_name:  Optional[str] = Query(None),
    country_of_origin:  Optional[str] = Query(None),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """List XXCKDO_MANUFACTURER_MASTER records, optionally filtered."""
    filters = dict(org_id=org_id, item_code=item_code, item_desc=item_desc,
                   manufacturer_name=manufacturer_name, country_of_origin=country_of_origin)
    return await PurchasingService().get_manufacturer_list(filters)


@router.post("/manufacturer-master")
async def create_manufacturer(
    body: ManufacturerIn,
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Insert a new row into XXCKDO_MANUFACTURER_MASTER."""
    username = user.username or user.id or "unknown"
    return await PurchasingService().create_manufacturer(body.model_dump(), username)


@router.put("/manufacturer-master/{manufacturer_id}")
async def update_manufacturer(
    manufacturer_id: int,
    body: ManufacturerIn,
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Update an existing row in XXCKDO_MANUFACTURER_MASTER."""
    username = user.username or user.id or "unknown"
    return await PurchasingService().update_manufacturer(manufacturer_id, body.model_dump(), username)


@router.delete("/manufacturer-master/{manufacturer_id}")
async def delete_manufacturer(
    manufacturer_id: int,
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Delete a row from XXCKDO_MANUFACTURER_MASTER."""
    return await PurchasingService().delete_manufacturer(manufacturer_id)


# ── Price Analysis ────────────────────────────────────────────────────────────

@router.get("/price-analysis")
async def get_price_analysis(
    org_id:             Optional[int]   = Query(None),
    year_from:          Optional[int]   = Query(None),
    year_to:            Optional[int]   = Query(None),
    item_code:          Optional[str]   = Query(None),
    item_desc:          Optional[str]   = Query(None),
    vendor_name:        Optional[str]   = Query(None),
    manufacturer:       Optional[str]   = Query(None),
    country_of_origin:  Optional[str]   = Query(None),
    category:           Optional[str]   = Query(None),
    currency_code:      Optional[str]   = Query(None),
    material_type:      Optional[str]   = Query(None),
    exchange_rate_type: Optional[str]   = Query("Corporate"),
    max_rows:           Optional[int]   = Query(10, ge=1, le=500),
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Price trend per supplier per year for a selected item."""
    filters = {
        "org_id": org_id, "year_from": year_from, "year_to": year_to,
        "item_code": item_code, "item_desc": item_desc,
        "vendor_name": vendor_name, "manufacturer": manufacturer,
        "country_of_origin": country_of_origin, "category": category,
        "currency_code": currency_code, "material_type": material_type,
        "exchange_rate_type": exchange_rate_type, "max_rows": max_rows,
    }
    return await PurchasingService().get_price_analysis(filters)


# ── Metals.dev proxy ──────────────────────────────────────────────────────────

@router.get("/metals/latest")
async def get_metals_latest(
    user: CurrentUser = Depends(require_role(Roles.PURCHASING)),
):
    """Proxy metals.dev API — returns latest platinum price, cached 1 hour."""
    global _metals_cache, _metals_history

    api_key = os.getenv("METALS_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "METALS_API_KEY not configured"}

    # Return cache if still fresh (< 1 hour)
    if _metals_cache:
        cached_at = datetime.fromisoformat(_metals_cache["updated_at"])
        if datetime.utcnow() - cached_at < timedelta(hours=1):
            return {"success": True, "data": _metals_cache["data"], "from_cache": True}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.metals.dev/v1/latest",
                params={"api_key": api_key, "currency": "USD", "unit": "troy_oz"},
            )
            resp.raise_for_status()
            raw = resp.json()

        metals = raw.get("metals", {})
        now    = datetime.utcnow()

        # Keep last 24 history points
        _metals_history.append({"time": now.strftime("%H:%M"), "platinum": round(metals.get("platinum", 0), 2)})
        if len(_metals_history) > 24:
            _metals_history = _metals_history[-24:]

        data = {
            "platinum":    round(metals.get("platinum", 0), 2),
            "palladium":   round(metals.get("palladium", 0), 2),
            "gold":        round(metals.get("gold", 0), 2),
            "silver":      round(metals.get("silver", 0), 2),
            "currency":    "USD",
            "updated_at":  now.isoformat(),
            "history":     _metals_history,
        }
        _metals_cache = {"updated_at": now.isoformat(), "data": data}
        return {"success": True, "data": data, "from_cache": False}

    except Exception as e:
        if _metals_cache:
            return {"success": True, "data": _metals_cache["data"], "from_cache": True, "warning": str(e)}
        return {"success": False, "error": str(e)}
