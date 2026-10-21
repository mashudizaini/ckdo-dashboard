"""
Common Lookup Router
Route prefix : /api/v1/lookups

Small master data lists (Oracle EBS FND_LOOKUP_* style) — see
app/services/lookup_service.py. Reading is open to any signed-in user
(modules use these as LOVs and mappings); creating or changing values is
admin / IT only.

  GET    /types                        — every lookup type, with its value count
  GET    /{lookup_type}                — its values (?all=true includes disabled / expired)
  POST   /{lookup_type}                — add a value
  PUT    /{lookup_type}/{value_id}     — change a value
  DELETE /{lookup_type}/{value_id}     — remove a value (prefer enabled_flag=false to retire one)
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, Roles, get_current_user, require_role
from app.models.lookup import LookupType, LookupValue
from app.services import lookup_service

router = APIRouter()


class ValueIn(BaseModel):
    lookup_code: str
    meaning: str
    description: Optional[str] = None
    tag: Optional[str] = None
    display_sequence: int = 0
    enabled_flag: bool = True
    start_date_active: Optional[date] = None
    end_date_active: Optional[date] = None


@router.get("/types")
async def list_types(db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    counts = dict((await db.execute(
        select(LookupValue.lookup_type, func.count()).group_by(LookupValue.lookup_type)
    )).all())
    types = (await db.execute(select(LookupType).order_by(LookupType.lookup_type))).scalars().all()
    return {"data": [lookup_service.type_dict(t, counts.get(t.lookup_type, 0)) for t in types]}


@router.get("/{lookup_type}")
async def list_values(
    lookup_type: str, all: bool = Query(False, description="include disabled / out-of-date values"),
    db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(get_current_user),
):
    t = await db.get(LookupType, lookup_type.upper())
    if not t:
        raise HTTPException(404, f"Lookup type {lookup_type} not found")
    values = await lookup_service.get_values(db, t.lookup_type, active_only=not all)
    return {"type": lookup_service.type_dict(t), "data": [lookup_service.value_dict(v) for v in values]}


def _check(body: ValueIn):
    if not body.lookup_code.strip() or not body.meaning.strip():
        raise HTTPException(422, "lookup_code and meaning are required")
    if body.start_date_active and body.end_date_active and body.end_date_active < body.start_date_active:
        raise HTTPException(422, "end_date_active is before start_date_active")


@router.post("/{lookup_type}")
async def add_value(
    lookup_type: str, body: ValueIn,
    db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(require_role(Roles.IT)),
):
    t = await db.get(LookupType, lookup_type.upper())
    if not t:
        raise HTTPException(404, f"Lookup type {lookup_type} not found")
    _check(body)
    code = body.lookup_code.strip().upper()
    if await db.scalar(select(LookupValue.id).where(LookupValue.lookup_type == t.lookup_type,
                                                    LookupValue.lookup_code == code)):
        raise HTTPException(409, f"{code} already exists in {t.lookup_type}")
    v = LookupValue(lookup_type=t.lookup_type, **{**body.model_dump(), "lookup_code": code},
                    created_by=user.username, updated_by=user.username)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return {"data": lookup_service.value_dict(v)}


@router.put("/{lookup_type}/{value_id}")
async def update_value(
    lookup_type: str, value_id: int, body: ValueIn,
    db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(require_role(Roles.IT)),
):
    v = await db.get(LookupValue, value_id)
    if not v or v.lookup_type != lookup_type.upper():
        raise HTTPException(404, "Lookup value not found")
    _check(body)
    code = body.lookup_code.strip().upper()
    clash = await db.scalar(select(LookupValue.id).where(LookupValue.lookup_type == v.lookup_type,
                                                         LookupValue.lookup_code == code,
                                                         LookupValue.id != v.id))
    if clash:
        raise HTTPException(409, f"{code} already exists in {v.lookup_type}")
    for k, val in {**body.model_dump(), "lookup_code": code}.items():
        setattr(v, k, val)
    v.updated_by = user.username
    await db.commit()
    await db.refresh(v)
    return {"data": lookup_service.value_dict(v)}


@router.delete("/{lookup_type}/{value_id}")
async def delete_value(
    lookup_type: str, value_id: int,
    db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(require_role(Roles.IT)),
):
    v = await db.get(LookupValue, value_id)
    if not v or v.lookup_type != lookup_type.upper():
        raise HTTPException(404, "Lookup value not found")
    await db.delete(v)
    await db.commit()
    return {"success": True}
