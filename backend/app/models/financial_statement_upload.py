from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class FinancialStatementUpload(Base):
    """Excel-sourced snapshot for one Financial Statement report, used as an
    alternative to the live Oracle EBS GL_BALANCES query while the client
    transitions from manual Excel reporting to Oracle. One row per
    report_type, replaced wholesale on each re-upload (no history kept) --
    `content` mirrors the shape the matching Oracle-mode service method
    returns, keyed by whatever fiscal years / date labels were found in the
    uploaded file, so the API layer can serve either source through the
    same response contract."""
    __tablename__ = "financial_statement_uploads"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    # balance_sheet | profit_loss | profit_loss_monthly
    report_type       = Column(String(30), nullable=False, unique=True, index=True)
    content           = Column(JSONB, nullable=False)
    original_filename = Column(String(255), default="")
    uploaded_by       = Column(String(100), default="")
    uploaded_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
