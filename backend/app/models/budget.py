from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, Text, UniqueConstraint
from app.database import Base


class BudgetLine(Base):
    """Baris anggaran per akun per bulan."""
    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("year", "month", "account_code", name="uq_budget_line"),
    )

    id             = Column(Integer,   primary_key=True, autoincrement=True)
    year           = Column(Integer,   nullable=False, index=True)
    month          = Column(Integer,   nullable=False, index=True)
    account_code   = Column(String(50),  nullable=False, index=True)
    account_name   = Column(String(200), nullable=False)
    budget_amount  = Column(BigInteger,  default=0)
    actual_amount  = Column(BigInteger,  default=0)
    notes          = Column(Text)
    upload_batch_id = Column(String(50), index=True)
    uploaded_at    = Column(DateTime, default=datetime.utcnow)


class BudgetItem(Base):
    """Rincian item realisasi per akun per bulan."""
    __tablename__ = "budget_items"

    id             = Column(Integer,    primary_key=True, autoincrement=True)
    year           = Column(Integer,    nullable=False, index=True)
    month          = Column(Integer,    nullable=False, index=True)
    account_code   = Column(String(50), nullable=False, index=True)
    item_name      = Column(String(200))
    amount         = Column(BigInteger, default=0)
    item_date      = Column(Date)
    notes          = Column(Text)
    upload_batch_id = Column(String(50), index=True)


class BudgetUploadLog(Base):
    __tablename__ = "budget_upload_logs"

    id          = Column(Integer,    primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    filename    = Column(String(255))
    year        = Column(Integer)
    total_rows  = Column(Integer, default=0)
    upserted    = Column(Integer, default=0)
    items_added = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
