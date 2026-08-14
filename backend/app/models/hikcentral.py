"""
HikCentral OpenAPI integration — IT dashboard control tab.

Same pattern as vpn_monitor.py: a dedicated sync SQLAlchemy engine against
the same Postgres database (own `hikcentral_` prefixed table), rather than
the app's shared async Base/AsyncSession, since config edits and the
"Test Connection" probe are simple blocking calls.

HikCentralConfig is a single editable row (falls back to the .env values in
app/config.py when no row exists yet) — the point is letting IT staff
rotate the AppKey/AppSecret or fix the base URL from the dashboard UI
instead of needing an SSH session + .env edit + backend restart, which was
the slow, error-prone loop the initial integration setup went through.
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings

settings = get_settings()

hikcentral_engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
HikCentralSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=hikcentral_engine)
HikCentralBase = declarative_base()


class HikCentralConfig(HikCentralBase):
    """Always at most one row. `app_secret_encrypted` is Fernet-encrypted via
    app.services.crypto, same primitive vpn_monitor's VpnCredential uses."""
    __tablename__ = "hikcentral_config"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    base_url              = Column(String(255))
    app_key               = Column(String(100))
    app_secret_encrypted  = Column(Text)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by            = Column(String(100))


def init_hikcentral_db():
    """Create hikcentral_* tables idempotently — called from the app
    lifespan on every startup, mirroring init_vpn_db()."""
    HikCentralBase.metadata.create_all(bind=hikcentral_engine)


def get_hikcentral_db():
    """FastAPI dependency — sync Session (routes using this must be plain
    `def`, not `async def`)."""
    db = HikCentralSessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_effective_config(db) -> dict:
    """DB row (if fully set) overrides the .env defaults — lets a UI-saved
    config take effect immediately, without a backend restart. Falls back
    field-by-field so a partially-filled DB row doesn't silently blank out
    a working .env value."""
    from app.services import crypto

    row = db.query(HikCentralConfig).first()
    base_url = (row.base_url if row and row.base_url else None) or settings.hikcentral_base_url
    app_key = (row.app_key if row and row.app_key else None) or settings.hikcentral_app_key
    if row and row.app_secret_encrypted:
        app_secret = crypto.decrypt(row.app_secret_encrypted)
    else:
        app_secret = settings.hikcentral_app_secret
    source = "database" if (row and row.base_url and row.app_key and row.app_secret_encrypted) else (
        "env" if (settings.hikcentral_base_url and settings.hikcentral_app_key and settings.hikcentral_app_secret) else "none"
    )
    return {"base_url": base_url, "app_key": app_key, "app_secret": app_secret, "source": source}
