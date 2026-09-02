"""
E-Magazine Router
Provides endpoints for e-magazine content, search, and analytics
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from pathlib import Path
import shutil
import os

from app.database import get_db
from app.models.emagazine import (
    EMagazineEdition,
    EMagazineContent,
    EMagazineHotspot,
    EMagazineAnalytics,
)
from app.utils.pdf_parser import (
    render_pdf_pages,
    populate_database,
    check_edition_exists,
    PAGE_IMAGES_ROOT,
)


router = APIRouter(prefix="/api/emagazine", tags=["emagazine"])


# ─────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────


class ContentResponse(BaseModel):
    id: int
    page_number: int
    section_name: str
    title: str
    content_type: str
    searchable_text: Optional[str]
    image_path: Optional[str] = None

    class Config:
        from_attributes = True


class EditionResponse(BaseModel):
    id: int
    title: str
    edition_number: int
    # date/datetime (not str) — these endpoints return the ORM object
    # directly and let from_attributes serialize it; with str fields,
    # Pydantic v2 rejects the actual date/datetime values FastAPI hands it
    # instead of silently stringifying them, which 500'd every call to
    # list/get editions (upload's own response model avoided this only
    # because it builds the response explicitly with str()/.isoformat()
    # rather than serializing the ORM object directly).
    published_date: date
    total_pages: int
    created_at: datetime

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    edition_id: Optional[int] = None


class SearchResult(BaseModel):
    content_id: int
    page_number: int
    section_name: str
    title: str
    snippet: str


class AnalyticsTrack(BaseModel):
    action_type: str  # page_view, click, search, download, print
    page_number: Optional[int] = None
    hotspot_id: Optional[int] = None
    search_query: Optional[str] = None
    metadata: Optional[dict] = None


class UploadEditionRequest(BaseModel):
    title: str
    edition_number: int
    published_date: str  # Format: YYYY-MM-DD


class UploadEditionResponse(BaseModel):
    id: int
    title: str
    edition_number: int
    published_date: str
    total_pages: int
    created_at: str
    message: str

    class Config:
        from_attributes = True


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────


@router.get("/editions", response_model=List[EditionResponse])
async def list_editions(db: AsyncSession = Depends(get_db)):
    """List all e-magazine editions"""
    stmt = select(EMagazineEdition).order_by(EMagazineEdition.published_date.desc())
    result = await db.execute(stmt)
    editions = result.scalars().all()
    return editions


@router.get("/editions/{edition_id}", response_model=EditionResponse)
async def get_edition(edition_id: int, db: AsyncSession = Depends(get_db)):
    """Get specific edition"""
    stmt = select(EMagazineEdition).where(EMagazineEdition.id == edition_id)
    result = await db.execute(stmt)
    edition = result.scalar_one_or_none()

    if not edition:
        raise HTTPException(status_code=404, detail="Edition not found")

    return edition


@router.get("/editions/{edition_id}/pages/{page_num}", response_model=ContentResponse)
async def get_page(edition_id: int, page_num: int, db: AsyncSession = Depends(get_db)):
    """Get single page content"""
    stmt = select(EMagazineContent).where(
        and_(
            EMagazineContent.edition_id == edition_id,
            EMagazineContent.page_number == page_num,
        )
    )
    result = await db.execute(stmt)
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(status_code=404, detail="Page not found")

    return content


@router.post("/search", response_model=List[SearchResult])
async def search_content(
    req: SearchRequest,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Full-text search across e-magazine content"""
    query_text = req.query.strip()

    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # PostgreSQL full-text search
    stmt = select(EMagazineContent).where(
        and_(
            EMagazineContent.searchable_text.ilike(f"%{query_text}%"),
            EMagazineContent.edition_id == req.edition_id if req.edition_id else True,
        )
    )

    result = await db.execute(stmt)
    contents = result.scalars().all()[:limit]

    # Build results with snippet
    results = []
    for content in contents:
        text = content.searchable_text or ""
        # Extract snippet around query
        idx = text.lower().find(query_text.lower())
        start = max(0, idx - 50)
        end = min(len(text), idx + len(query_text) + 50)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        results.append(
            SearchResult(
                content_id=content.id,
                page_number=content.page_number,
                section_name=content.section_name,
                title=content.title,
                snippet=snippet,
            )
        )

    return results


@router.get("/editions/{edition_id}/toc")
async def get_table_of_contents(edition_id: int, db: AsyncSession = Depends(get_db)):
    """Get table of contents (grouped by section)"""
    stmt = select(EMagazineContent).where(
        EMagazineContent.edition_id == edition_id
    ).order_by(EMagazineContent.page_number)

    result = await db.execute(stmt)
    contents = result.scalars().all()

    toc = {}
    for content in contents:
        section = content.section_name or "General"
        if section not in toc:
            toc[section] = []
        toc[section].append({
            "page": content.page_number,
            "title": content.title,
            "id": content.id,
        })

    return toc


@router.post("/editions/upload", response_model=UploadEditionResponse)
async def upload_edition(
    title: str = Form(...),
    edition_number: int = Form(...),
    published_date: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and parse a new PDF edition"""

    # Validate file is PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Check edition doesn't already exist
    if await check_edition_exists(edition_number, db):
        raise HTTPException(
            status_code=400,
            detail=f"Edition number {edition_number} already exists"
        )

    # Validate published_date format
    try:
        datetime.strptime(published_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Published date must be in YYYY-MM-DD format"
        )

    # Create upload directory if it doesn't exist — /app/magazine-uploads is
    # the persistent bind mount for this (./e-magazine/magazines on the host,
    # see docker-compose.yml), not an arbitrary path: anything saved outside
    # a declared volume lives only in the container's own writable layer and
    # is silently lost on the next rebuild/restart.
    upload_dir = Path("/app/magazine-uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    try:
        file_path = upload_dir / f"emagazine_edition_{edition_number}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Extract text + render page images
    try:
        render_result = render_pdf_pages(str(file_path))
        if not render_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract PDF text: {render_result['error']}"
            )

        # Populate database (text + saved page images)
        edition = await populate_database(
            title,
            edition_number,
            published_date,
            str(file_path),
            render_result["pages"],
            db,
        )

        return UploadEditionResponse(
            id=edition.id,
            title=edition.title,
            edition_number=edition.edition_number,
            published_date=str(edition.published_date),
            total_pages=edition.total_pages,
            created_at=edition.created_at.isoformat(),
            message=f"Edition uploaded successfully. {edition.total_pages} pages parsed and indexed."
        )

    except HTTPException:
        raise
    except Exception as e:
        # Clean up file on error
        try:
            file_path.unlink()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")


@router.delete("/editions/{edition_id}")
async def delete_edition(edition_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an edition: its content/hotspot/analytics rows, the uploaded
    PDF, and its rendered page images. No cascade is configured at the
    DB/ORM level (models are plain Columns, no relationship()s), so child
    rows have to be deleted explicitly before the edition row itself, or
    the FK constraints on edition_id would reject the delete."""
    stmt = select(EMagazineEdition).where(EMagazineEdition.id == edition_id)
    result = await db.execute(stmt)
    edition = result.scalar_one_or_none()
    if not edition:
        raise HTTPException(status_code=404, detail="Edition not found")

    title = edition.title
    pdf_path = edition.pdf_path

    await db.execute(delete(EMagazineAnalytics).where(EMagazineAnalytics.edition_id == edition_id))
    await db.execute(delete(EMagazineHotspot).where(EMagazineHotspot.edition_id == edition_id))
    await db.execute(delete(EMagazineContent).where(EMagazineContent.edition_id == edition_id))
    await db.delete(edition)
    await db.commit()

    # File cleanup is best-effort — the DB rows are already gone, so a
    # leftover file on disk isn't worth failing the request over.
    try:
        if pdf_path and Path(pdf_path).exists():
            Path(pdf_path).unlink()
    except Exception:
        pass
    try:
        images_dir = PAGE_IMAGES_ROOT / f"edition_{edition_id}"
        if images_dir.exists():
            shutil.rmtree(images_dir)
    except Exception:
        pass

    return {"message": f"Edition '{title}' deleted successfully"}


@router.post("/analytics")
async def track_analytics(
    edition_id: int,
    track: AnalyticsTrack,
    user_id: str = "anonymous",
    db: AsyncSession = Depends(get_db),
):
    """Track user interactions with e-magazine"""
    analytics = EMagazineAnalytics(
        edition_id=edition_id,
        user_id=user_id,
        action_type=track.action_type,
        page_number=track.page_number,
        hotspot_id=track.hotspot_id,
        search_query=track.search_query,
        event_metadata=track.metadata or {},
    )

    db.add(analytics)
    await db.commit()

    return {"status": "ok"}


@router.get("/analytics/{edition_id}/summary")
async def get_analytics_summary(edition_id: int, db: AsyncSession = Depends(get_db)):
    """Get analytics summary for edition"""
    # Total page views
    page_views_stmt = select(func.count(EMagazineAnalytics.id)).where(
        and_(
            EMagazineAnalytics.edition_id == edition_id,
            EMagazineAnalytics.action_type == "page_view",
        )
    )
    page_views = await db.scalar(page_views_stmt)

    # Unique users
    unique_users_stmt = select(func.count(func.distinct(EMagazineAnalytics.user_id))).where(
        EMagazineAnalytics.edition_id == edition_id
    )
    unique_users = await db.scalar(unique_users_stmt)

    # Popular pages
    popular_pages_stmt = (
        select(
            EMagazineAnalytics.page_number,
            func.count(EMagazineAnalytics.id).label("views"),
        )
        .where(
            and_(
                EMagazineAnalytics.edition_id == edition_id,
                EMagazineAnalytics.page_number.isnot(None),
            )
        )
        .group_by(EMagazineAnalytics.page_number)
        .order_by(func.count(EMagazineAnalytics.id).desc())
        .limit(10)
    )
    popular_pages = await db.execute(popular_pages_stmt)
    popular = [{"page": p[0], "views": p[1]} for p in popular_pages.all()]

    return {
        "edition_id": edition_id,
        "total_page_views": page_views or 0,
        "unique_users": unique_users or 0,
        "popular_pages": popular,
    }
