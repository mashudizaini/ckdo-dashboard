"""
E-Magazine Hotspots Router
Manages interactive clickable areas and their actions
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models.emagazine import EMagazineHotspot, EMagazineEdition


router = APIRouter(prefix="/api/emagazine/hotspots", tags=["hotspots"])


# ─────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────


class HotspotBase(BaseModel):
    page_number: int
    x_pos: float
    y_pos: float
    width: float
    height: float
    action_type: str  # link, contact, video, form, qrcode, profile
    action_data: dict
    tooltip: Optional[str] = None


class HotspotCreate(HotspotBase):
    edition_id: int


class HotspotUpdate(BaseModel):
    x_pos: Optional[float] = None
    y_pos: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    action_type: Optional[str] = None
    action_data: Optional[dict] = None
    tooltip: Optional[str] = None


class HotspotResponse(HotspotBase):
    id: int
    edition_id: int
    created_at: str

    class Config:
        from_attributes = True


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────


@router.get("/editions/{edition_id}")
async def get_edition_hotspots(
    edition_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[HotspotResponse]:
    """Get all hotspots for an edition"""
    stmt = select(EMagazineHotspot).where(
        EMagazineHotspot.edition_id == edition_id
    )
    result = await db.execute(stmt)
    hotspots = result.scalars().all()
    return hotspots


@router.get("/editions/{edition_id}/pages/{page_num}")
async def get_page_hotspots(
    edition_id: int,
    page_num: int,
    db: AsyncSession = Depends(get_db),
) -> List[HotspotResponse]:
    """Get hotspots for a specific page"""
    stmt = select(EMagazineHotspot).where(
        and_(
            EMagazineHotspot.edition_id == edition_id,
            EMagazineHotspot.page_number == page_num,
        )
    )
    result = await db.execute(stmt)
    hotspots = result.scalars().all()
    return hotspots


@router.get("/{hotspot_id}", response_model=HotspotResponse)
async def get_hotspot(
    hotspot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get single hotspot"""
    stmt = select(EMagazineHotspot).where(EMagazineHotspot.id == hotspot_id)
    result = await db.execute(stmt)
    hotspot = result.scalar_one_or_none()

    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    return hotspot


@router.post("", response_model=HotspotResponse)
async def create_hotspot(
    hotspot: HotspotCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create new hotspot"""
    # Verify edition exists
    edition_stmt = select(EMagazineEdition).where(
        EMagazineEdition.id == hotspot.edition_id
    )
    edition_result = await db.execute(edition_stmt)
    if not edition_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Edition not found")

    new_hotspot = EMagazineHotspot(
        edition_id=hotspot.edition_id,
        page_number=hotspot.page_number,
        x_pos=hotspot.x_pos,
        y_pos=hotspot.y_pos,
        width=hotspot.width,
        height=hotspot.height,
        action_type=hotspot.action_type,
        action_data=hotspot.action_data,
        tooltip=hotspot.tooltip,
    )

    db.add(new_hotspot)
    await db.commit()
    await db.refresh(new_hotspot)

    return new_hotspot


@router.put("/{hotspot_id}", response_model=HotspotResponse)
async def update_hotspot(
    hotspot_id: int,
    hotspot: HotspotUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update hotspot"""
    stmt = select(EMagazineHotspot).where(EMagazineHotspot.id == hotspot_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    # Update only provided fields
    update_data = hotspot.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)

    existing.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(existing)

    return existing


@router.delete("/{hotspot_id}")
async def delete_hotspot(
    hotspot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete hotspot"""
    stmt = select(EMagazineHotspot).where(EMagazineHotspot.id == hotspot_id)
    result = await db.execute(stmt)
    hotspot = result.scalar_one_or_none()

    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    await db.delete(hotspot)
    await db.commit()

    return {"status": "deleted"}


@router.post("/batch/editions/{edition_id}")
async def batch_create_hotspots(
    edition_id: int,
    hotspots: List[HotspotCreate],
    db: AsyncSession = Depends(get_db),
):
    """Create multiple hotspots at once"""
    # Verify edition exists
    edition_stmt = select(EMagazineEdition).where(
        EMagazineEdition.id == edition_id
    )
    edition_result = await db.execute(edition_stmt)
    if not edition_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Edition not found")

    new_hotspots = []
    for hs in hotspots:
        new_hotspot = EMagazineHotspot(
            edition_id=edition_id,
            page_number=hs.page_number,
            x_pos=hs.x_pos,
            y_pos=hs.y_pos,
            width=hs.width,
            height=hs.height,
            action_type=hs.action_type,
            action_data=hs.action_data,
            tooltip=hs.tooltip,
        )
        new_hotspots.append(new_hotspot)
        db.add(new_hotspot)

    await db.commit()

    # Refresh all hotspots
    for hs in new_hotspots:
        await db.refresh(hs)

    return new_hotspots
