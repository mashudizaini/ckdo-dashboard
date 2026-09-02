from sqlalchemy import Column, Integer, String, Date, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.database import Base


class EMagazineEdition(Base):
    __tablename__ = "emagazine_editions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True)
    edition_number = Column(Integer)
    published_date = Column(Date, index=True)
    total_pages = Column(Integer)
    pdf_path = Column(String(500))
    pdf_filename = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EMagazineContent(Base):
    __tablename__ = "emagazine_content"
    __table_args__ = (
        Index("idx_content_search", "searchable_text"),
        Index("idx_content_edition_page", "edition_id", "page_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    edition_id = Column(Integer, ForeignKey("emagazine_editions.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    section_name = Column(String(255), index=True)
    title = Column(String(255))
    content_type = Column(String(50))  # text, image, video, form, etc
    content_data = Column(JSONB)  # Flexible structure for different content types
    searchable_text = Column(Text)  # For full-text search
    image_path = Column(String(500))  # Path to extracted images
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EMagazineHotspot(Base):
    __tablename__ = "emagazine_hotspots"
    __table_args__ = (
        Index("idx_hotspot_edition_page", "edition_id", "page_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    edition_id = Column(Integer, ForeignKey("emagazine_editions.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    x_pos = Column(Float)  # X coordinate
    y_pos = Column(Float)  # Y coordinate
    width = Column(Float)  # Width of clickable area
    height = Column(Float)  # Height of clickable area
    action_type = Column(String(50))  # contact, link, video, form, qrcode
    action_data = Column(JSONB)  # Flexible action configuration
    tooltip = Column(String(255))  # Hover text
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EMagazineAnalytics(Base):
    __tablename__ = "emagazine_analytics"
    __table_args__ = (
        Index("idx_analytics_user_edition", "edition_id", "user_id"),
        Index("idx_analytics_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    edition_id = Column(Integer, ForeignKey("emagazine_editions.id"), nullable=False, index=True)
    user_id = Column(String(255), index=True)  # Keycloak user ID
    action_type = Column(String(50), index=True)  # page_view, click, search, download, print
    page_number = Column(Integer)
    hotspot_id = Column(Integer, ForeignKey("emagazine_hotspots.id"))
    search_query = Column(String(500))
    event_metadata = Column(JSONB)  # Device info, session duration, etc — named
    # event_metadata (not metadata): SQLAlchemy's Declarative API reserves the
    # `metadata` attribute name on every mapped class (it holds the table's
    # own MetaData registry) — using it as a column name crashes the entire
    # app at import time, before uvicorn can even start.
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
