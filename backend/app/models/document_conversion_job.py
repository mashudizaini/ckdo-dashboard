from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base


class DocumentConversionJob(Base):
    """
    A Document Converter conversion job. Dispatched to the Celery worker so
    the actual (slow — ~73s/page measured on a real scanned PDF) docling
    conversion keeps running server-side regardless of whether the browser
    tab that started it is still open, and survives a logout/re-login.

    Previously this ran entirely inline in a single SSE-streamed request —
    closing the tab (or a JWT expiring mid-stream) cancelled the connection,
    and because the actual docling call ran in a plain OS thread
    (asyncio.to_thread), cancelling the await did NOT stop that thread; it
    kept burning CPU to produce a result nobody was listening for anymore,
    while the request handler's `finally` block deleted the temp file out
    from under it. This table + celery task fixes both problems: the job
    survives independent of any HTTP connection, and its progress/result is
    polled from here rather than streamed.
    """
    __tablename__ = "document_conversion_jobs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    filename         = Column(String(255), nullable=False)
    stored_path      = Column(String(500), nullable=False)  # persistent copy on disk (uploads/doc_converter_jobs/), removed once the job finishes or errors
    ext              = Column(String(10), nullable=False)
    language         = Column(String(20), default="auto")  # "auto" (default RapidOCR pipeline) | "korean" (Tesseract+kor — RapidOCR has no real Korean model, see document_converter_service.py)
    status           = Column(String(20), default="pending")  # pending -> processing -> done -> error -> stopped
    total_pages      = Column(Integer)
    current_page     = Column(Integer, default=0)
    progress_percent = Column(Integer, default=0)
    status_message   = Column(String(300))
    markdown         = Column(Text)
    error_message    = Column(Text)
    celery_task_id   = Column(String(100))

    created_by       = Column(String(100))
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
