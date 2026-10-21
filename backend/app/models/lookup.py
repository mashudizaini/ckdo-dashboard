from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from app.database import Base


class LookupType(Base):
    """Common lookup — one row per list of small master data, modelled on
    Oracle EBS FND_LOOKUP_TYPES. `lookup_type` is the code callers ask for
    (e.g. "EIS_MARKET_BUSINESS_TYPE"); its values live in lookup_values."""
    __tablename__ = "lookup_types"

    lookup_type = Column(String(60), primary_key=True)
    meaning     = Column(String(150), nullable=False)
    description = Column(Text)
    module      = Column(String(50))          # owning area, e.g. "EIS"
    created_by  = Column(String(100))
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_by  = Column(String(100))
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LookupValue(Base):
    """One value of a lookup type, modelled on Oracle EBS FND_LOOKUP_VALUES:
    `lookup_code` is the stable key, `meaning` the display text, `tag` a
    short attribute for mapping lookups (Oracle uses TAG the same way — e.g.
    the business type a sales market belongs to). A value is in effect when
    enabled_flag is true and today falls within start/end_date_active
    (either end may be NULL = open)."""
    __tablename__ = "lookup_values"
    __table_args__ = (UniqueConstraint("lookup_type", "lookup_code", name="uq_lookup_values_type_code"),)

    id                = Column(Integer, primary_key=True, autoincrement=True)
    lookup_type       = Column(String(60), ForeignKey("lookup_types.lookup_type", ondelete="CASCADE"),
                               nullable=False, index=True)
    lookup_code       = Column(String(80), nullable=False)
    meaning           = Column(String(150), nullable=False)
    description       = Column(Text)
    tag               = Column(String(150))
    display_sequence  = Column(Integer, default=0)
    enabled_flag      = Column(Boolean, nullable=False, default=True)
    start_date_active = Column(Date)
    end_date_active   = Column(Date)
    created_by        = Column(String(100))
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_by        = Column(String(100))
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
