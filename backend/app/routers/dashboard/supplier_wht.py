"""
Supplier WHT Master Router
Route prefix: /api/v1/dashboard/accounting/supplier-wht
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.services import supplier_wht_service as svc

router = APIRouter()


class WhtUpsertRequest(BaseModel):
    vendor_id: int
    vendor_name: str
    awt_group_name: str
    tax_rate: float
    awt_group_id: Optional[int] = None
    updated_by: str = "manual"


class ActiveRequest(BaseModel):
    is_active: bool


@router.get("")
async def list_wht(search: Optional[str] = Query(None)):
    return {"items": svc.list_wht_master(search=search)}


@router.post("/sync")
async def sync_from_oracle(updated_by: str = Query("oracle-sync")):
    try:
        return svc.seed_from_oracle(updated_by=updated_by)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync gagal: {e}")


@router.post("")
async def upsert_wht(body: WhtUpsertRequest):
    try:
        return svc.upsert_wht_master(
            vendor_id=body.vendor_id, vendor_name=body.vendor_name,
            awt_group_name=body.awt_group_name, tax_rate=body.tax_rate,
            updated_by=body.updated_by, awt_group_id=body.awt_group_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simpan gagal: {e}")


@router.put("/{id_}/active")
async def set_active(id_: int, body: ActiveRequest):
    result = svc.set_active(id_, body.is_active)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return result


@router.delete("/{id_}")
async def delete_wht(id_: int):
    deleted = svc.delete_wht_master(id_)
    if not deleted:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return {"deleted": deleted}


@router.get("/vendor/{vendor_id}")
async def get_wht_for_vendor(vendor_id: int, vendor_name: Optional[str] = Query(None)):
    # vendor_id=0 is the "not yet known" sentinel — an invoice that hasn't
    # been Validated yet has no Oracle vendor_id at all, so the frontend
    # falls back to this path with the OCR'd vendor_name as the only clue.
    row = svc.get_wht_for_vendor(vendor_id if vendor_id else None, vendor_name)
    if not row:
        raise HTTPException(status_code=404, detail="Belum ada data WHT untuk supplier ini")
    return row
