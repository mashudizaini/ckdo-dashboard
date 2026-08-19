from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class FinancialStatementUpload(Base):
    """Excel-sourced snapshot for one Financial Statement report, used as an
    alternative to the live Oracle EBS GL_BALANCES query while the client
    transitions from manual Excel reporting to Oracle. `content` mirrors
    the shape the matching Oracle-mode service method returns, keyed by
    whatever fiscal years / date labels were found in the uploaded file,
    so the API layer can serve either source through the same response
    contract.

    Every report_type except profit_loss_monthly still behaves as
    originally designed: exactly one row, replaced wholesale on each
    re-upload (no history), identified by period_month/period_year both
    NULL. profit_loss_monthly is the one exception — it supports multiple
    stored snapshots, one per calendar month (period_month/period_year
    populated, derived from the uploaded file's own row-7 "date_this"
    label), so a Month+Year picker in the UI can select between them
    instead of only ever seeing whatever was uploaded last. This is
    enforced in application code (FinancialStatementUploadService.
    save_upload), not a DB constraint — Postgres unique indexes treat
    NULL as distinct-from-NULL, so a composite unique constraint
    couldn't enforce "at most one NULL/NULL row" anyway."""
    __tablename__ = "financial_statement_uploads"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    # balance_sheet | profit_loss | profit_loss_monthly | cash_flow
    report_type       = Column(String(30), nullable=False, index=True)
    # profit_loss_monthly only — NULL for every other report_type.
    period_month      = Column(Integer, nullable=True)
    period_year       = Column(Integer, nullable=True)
    content           = Column(JSONB, nullable=False)
    original_filename = Column(String(255), default="")
    uploaded_by       = Column(String(100), default="")
    uploaded_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
