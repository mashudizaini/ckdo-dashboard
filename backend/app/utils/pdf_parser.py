"""
PDF Parser Utility for E-Magazine
Shared functions for extracting and parsing PDF content.
"""

import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple
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


def extract_text_from_pdf(pdf_path: str) -> Dict:
    """Extract text from PDF using PyMuPDF — already a dependency elsewhere
    in this app (see chatbot.py's Knowledge Base PDF ingest) rather than
    shelling out to the poppler-utils `pdftotext` binary, which isn't
    installed in this image and would need a Docker rebuild to add.
    Joins pages with a form-feed character to match split_text_by_pages()'s
    expected page-separator convention (pdftotext's own output convention,
    kept the same here so downstream parsing didn't need to change)."""
    try:
        doc = fitz.open(pdf_path)
        pages_text = [page.get_text() for page in doc]
        doc.close()
        return {"success": True, "text": "\f".join(pages_text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def split_text_by_pages(text: str) -> Dict[int, str]:
    """
    Split text by pages using form feed character (PDF page breaks).
    """
    pages = {}
    page_sections = text.split("\f")

    for idx, page_text in enumerate(page_sections, 1):
        pages[idx] = page_text.strip()

    return pages


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


async def populate_database(
    edition_title: str,
    edition_number: int,
    published_date: str,
    pdf_path: str,
    pages_content: Dict[int, str],
    session: AsyncSession,
) -> EMagazineEdition:
    """Populate database with parsed content and return created edition"""

    # Create edition
    edition = EMagazineEdition(
        title=edition_title,
        edition_number=edition_number,
        published_date=datetime.strptime(published_date, "%Y-%m-%d").date(),
        total_pages=len(pages_content),
        pdf_path=pdf_path,
        pdf_filename=Path(pdf_path).name,
    )

    session.add(edition)
    await session.flush()

    # Create content entries for each page
    for page_num, page_text in pages_content.items():
        if not page_text.strip():
            continue

        section = identify_section(page_text)
        cleaned_text = clean_text(page_text)

        lines = cleaned_text.split("\n")
        title = lines[0][:255] if lines else "Untitled"

        content = EMagazineContent(
            edition_id=edition.id,
            page_number=page_num,
            section_name=section,
            title=title,
            content_type="text",
            content_data={"raw_text": cleaned_text, "extracted_at": datetime.utcnow().isoformat()},
            searchable_text=cleaned_text,
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
