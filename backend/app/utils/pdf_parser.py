"""
PDF Parser Utility for E-Magazine
Shared functions for extracting and parsing PDF content.
"""

import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.emagazine import EMagazineEdition, EMagazineContent


# Section mapping from TOC
SECTIONS = {
    "OPENING": "Opening",
    "COMPANY": "Company's News",
    "BEHIND THE ID CARD": "Behind The ID Card",
    "BIRTHDAY": "Employee Birthday",
    "COLLABORATION": "Collaboration Star",
    "VOICE OF MEMBER": "Voice of Member",
    "CLOSING": "Closing",
}


# Zoom factor for page image rendering — ~144 DPI equivalent (2x PDF's
# native 72 DPI unit). Good visual quality for a magazine reader at a
# reasonable JPEG file size; not tied to any particular page's physical
# dimensions since coordinates downstream are percentage-based, not pixel.
PAGE_IMAGE_ZOOM = 2.0


def render_pdf_pages(pdf_path: str) -> Dict:
    """Open the PDF once and extract, per page, both the raw text (for full-
    text search — see SearchBar/emagazineAPI.search) and a rendered image
    (for the actual visual viewer — see PageViewer.jsx, which shows the
    page image with a hotspot overlay on top, not reflowed text). Returns
    {"success": True, "pages": [{"page_number", "text", "image_bytes"}, ...]}
    or {"success": False, "error": ...}."""
    try:
        doc = fitz.open(pdf_path)
        matrix = fitz.Matrix(PAGE_IMAGE_ZOOM, PAGE_IMAGE_ZOOM)
        pages = []
        for i, page in enumerate(doc, start=1):
            pages.append({
                "page_number": i,
                "text": page.get_text(),
                "image_bytes": page.get_pixmap(matrix=matrix).tobytes("jpg"),
            })
        doc.close()
        return {"success": True, "pages": pages}
    except Exception as e:
        return {"success": False, "error": str(e)}


def identify_section(text: str) -> str:
    """Identify which section a text belongs to"""
    text_upper = text.upper()

    for keyword, section_name in SECTIONS.items():
        if keyword in text_upper:
            return section_name

    return "General"


def clean_text(text: str) -> str:
    """Clean extracted text"""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


PAGE_IMAGES_ROOT = Path("/app/magazine-uploads/pages")
# Public URL prefix for page images — /app/magazine-uploads is the same host
# folder (./e-magazine/magazines, see docker-compose.yml) nginx already
# serves directly at /e-magazine/magazines/, so anything written under
# PAGE_IMAGES_ROOT is immediately reachable with no new route. Relative (no
# host/port) so it resolves against whatever origin the page was loaded
# from — see emagazineApi.js's earlier localhost:8001 fix for why an
# absolute URL here would be wrong on every deployment but the original
# developer's own machine.
PAGE_IMAGES_URL_PREFIX = "/e-magazine/magazines/pages"


async def populate_database(
    edition_title: str,
    edition_number: int,
    published_date: str,
    pdf_path: str,
    pages: list,
    session: AsyncSession,
) -> EMagazineEdition:
    """Populate database with parsed content (text + rendered page images)
    and return created edition. `pages` is render_pdf_pages()'s
    {"page_number", "text", "image_bytes"} list."""

    # Create edition
    edition = EMagazineEdition(
        title=edition_title,
        edition_number=edition_number,
        published_date=datetime.strptime(published_date, "%Y-%m-%d").date(),
        total_pages=len(pages),
        pdf_path=pdf_path,
        pdf_filename=Path(pdf_path).name,
    )

    session.add(edition)
    await session.flush()  # need edition.id for the image folder/URL below

    edition_images_dir = PAGE_IMAGES_ROOT / f"edition_{edition.id}"
    edition_images_dir.mkdir(parents=True, exist_ok=True)

    # Create content entries for each page — always create the row even for
    # a text-light page (e.g. a magazine cover or section divider with
    # little/no extractable text but a real image): skipping those would
    # silently drop pages from the viewer while total_pages still counted
    # them, leaving unreachable page numbers.
    for page in pages:
        page_num = page["page_number"]
        cleaned_text = clean_text(page["text"])
        section = identify_section(page["text"])

        lines = cleaned_text.split("\n")
        title = lines[0][:255] if lines and lines[0] else f"Page {page_num}"

        image_filename = f"page_{page_num}.jpg"
        (edition_images_dir / image_filename).write_bytes(page["image_bytes"])
        image_path = f"{PAGE_IMAGES_URL_PREFIX}/edition_{edition.id}/{image_filename}"

        content = EMagazineContent(
            edition_id=edition.id,
            page_number=page_num,
            section_name=section,
            title=title,
            content_type="text",
            content_data={"raw_text": cleaned_text, "extracted_at": datetime.utcnow().isoformat()},
            searchable_text=cleaned_text,
            image_path=image_path,
        )

        session.add(content)

    await session.commit()
    return edition


async def check_edition_exists(edition_number: int, session: AsyncSession) -> bool:
    """Check if edition with given number already exists"""
    stmt = select(EMagazineEdition).where(
        EMagazineEdition.edition_number == edition_number
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
