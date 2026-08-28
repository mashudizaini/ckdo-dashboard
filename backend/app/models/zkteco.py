"""
ZKTeco Plant Attendance Integration — IT dashboard control tab.

Same pattern as hikcentral.py/vpn_monitor.py: a dedicated sync SQLAlchemy
engine against the same Postgres database (own `zkteco_` prefixed table),
rather than the app's shared async Base/AsyncSession, since device CRUD and
the "Test Connection" probe are simple blocking calls.

Unlike HikCentral (one config row, one device), Plant has up to 8 physical
terminals (Lobby, Loker Male, Loker Female, Server IT, Female Lab, Male Lab,
Mall, Office — confirmed live via the "Solution" management software,
2026-08-28) all feeding the same employees' attendance, so this is a table
of devices rather than a single row. Each is polled independently and their
events merged per employee/day — see zkteco_scheduler.py.

`password` is the device's numeric ZKTeco "comm key" (0 = none, confirmed
for the Office terminal: "admin tanpa password") — set via the device's own
menu or the "Solution" software, not a login credential in the usual sense,
so it's stored plain (not Fernet-encrypted like HikCentral's real HTTP
password) — same class of value as a card PIN, and visible on the device
itself to anyone with physical access.
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings

settings = get_settings()

zkteco_engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
ZKTecoSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=zkteco_engine)
ZKTecoBase = declarative_base()


class ZKTecoDevice(ZKTecoBase):
    __tablename__ = "zkteco_devices"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    name               = Column(String(100), nullable=False)   # "Office", "Lobby", ...
    ip                 = Column(String(50), nullable=False)
    port               = Column(Integer, default=4370, nullable=False)
    password           = Column(Integer, default=0, nullable=False)  # ZKTeco comm key
    enabled            = Column(Boolean, default=True, nullable=False)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by         = Column(String(100))


def init_zkteco_db():
    """Create zkteco_* tables idempotently — called from the app lifespan
    on every startup, mirroring init_hikcentral_db()."""
    ZKTecoBase.metadata.create_all(bind=zkteco_engine)


def get_zkteco_db():
    """FastAPI dependency — sync Session (routes using this must be plain
    `def`, not `async def`)."""
    db = ZKTecoSessionLocal()
    try:
        yield db
    finally:
        db.close()
