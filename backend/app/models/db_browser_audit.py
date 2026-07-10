from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.database import Base


class DbBrowserAuditLog(Base):
    """Audit trail for every statement executed through the IT Database Browser's
    SQL console and row-delete action — accountability for an admin tool that can
    run arbitrary DDL/DML against the app's own PostgreSQL database."""
    __tablename__ = "db_browser_audit_log"

    id             = Column(Integer, primary_key=True)
    executed_by    = Column(String(150))
    executed_at    = Column(DateTime, default=datetime.utcnow, index=True)
    statement_type = Column(String(20))
    sql_text       = Column(Text)
    success        = Column(Boolean, default=True)
    error_message  = Column(Text, nullable=True)
    rows_affected  = Column(Integer, nullable=True)
    duration_ms    = Column(Integer, nullable=True)
