from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from app.database import Base


class OutlookMaterial(Base):
    """Reference source files (economic reports, market data, etc.) that
    inform the Business Plan Outlook write-up — uploaded ahead of, and
    separate from, the actual Outlook generation step."""
    __tablename__ = "outlook_materials"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    plan_year     = Column(Integer, nullable=False, index=True)
    filename      = Column(String(255), nullable=False)   # stored name on disk
    original_name = Column(String(255), nullable=False)
    content_type  = Column(String(100))
    file_size     = Column(BigInteger)
    uploaded_by   = Column(String(100))
    created_at    = Column(DateTime, default=datetime.utcnow)
