from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text
from app.database import Base


class OutlookMaterial(Base):
    """Reference source files (economic reports, market data, etc.) that
    inform the Business Plan Outlook write-up — uploaded ahead of, and
    separate from, the actual Outlook generation step."""
    __tablename__ = "outlook_materials"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    plan_year     = Column(Integer, nullable=False, index=True)
    # "material" = source data (economic reports, market data, etc.) that
    # informs the Outlook write-up. "format" = example/template files that
    # define the desired output format/structure of the generated report.
    category      = Column(String(20), nullable=False, default="material", server_default="material", index=True)
    filename      = Column(String(255), nullable=False)   # stored name on disk
    original_name = Column(String(255), nullable=False)
    content_type  = Column(String(100))
    file_size     = Column(BigInteger)
    uploaded_by   = Column(String(100))
    created_at    = Column(DateTime, default=datetime.utcnow)

    # ── Convert stage: file -> structured point-form brief, done once and
    # reused on every Outlook generation instead of re-reading the raw file
    # each time (cheaper, faster, and consistent across regenerations). ──
    brief_status  = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)  # pending | converting | done | failed
    brief_text    = Column(Text)     # AI-generated Markdown bullet brief
    brief_error   = Column(Text)
    converted_at  = Column(DateTime)
