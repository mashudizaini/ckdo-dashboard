from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, Text, UniqueConstraint
from app.database import Base


class BudgetLine(Base):
    """
    Baris anggaran per akun per bulan — data dari Oracle modul Budget.

    Kolom penting:
      budget_amount   : anggaran rencana original
      available_amount: saldo tersedia (open budget dari Oracle)
      reclass_amount  : jumlah reklasifikasi masuk (positif = tambah, negatif = kurang)
      reclass_note    : keterangan reklasifikasi

    Total Actual dihitung dari SUM(BudgetItem.amount) saat query.
    Remain = available_amount + reclass_amount - total_actual
    """
    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("year", "month", "account_code", name="uq_budget_line"),
    )

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    year             = Column(Integer,    nullable=False, index=True)
    month            = Column(Integer,    nullable=False, index=True)
    account_code     = Column(String(50), nullable=False, index=True)
    account_name     = Column(String(200), nullable=False)
    budget_amount    = Column(BigInteger,  default=0)    # rencana anggaran
    available_amount = Column(BigInteger,  default=0)    # saldo tersedia dari Oracle
    reclass_amount   = Column(BigInteger,  default=0)    # reklasifikasi (+/-)
    reclass_note     = Column(Text)                      # keterangan reclass
    upload_batch_id  = Column(String(50), index=True)
    uploaded_at      = Column(DateTime,   default=datetime.utcnow)


class BudgetItem(Base):
    """
    Rincian transaksi realisasi per akun per bulan — data dari Oracle modul AP Invoice.
    Setiap baris = 1 invoice / 1 transaksi pengeluaran.
    """
    __tablename__ = "budget_items"

    id              = Column(Integer,    primary_key=True, autoincrement=True)
    year            = Column(Integer,    nullable=False, index=True)
    month           = Column(Integer,    nullable=False, index=True)
    account_code    = Column(String(50), nullable=False, index=True)
    description     = Column(String(300))   # nama transaksi, mis: "Spec meal Jan 2026"
    amount          = Column(BigInteger, default=0)
    invoice_date    = Column(Date)
    notes           = Column(Text)
    upload_batch_id = Column(String(50), index=True)
    uploaded_at     = Column(DateTime,   default=datetime.utcnow)


class BudgetUploadLog(Base):
    __tablename__ = "budget_upload_logs"

    id          = Column(Integer,    primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    filename    = Column(String(255))
    sheet_type  = Column(String(20))   # "Budget" atau "Actual"
    year        = Column(Integer)
    total_rows  = Column(Integer, default=0)
    upserted    = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
