"""
VPN Access Monitoring — reachability + active-session monitoring for the
office FortiClient SSL-VPN gateway. New module, no prior art in this repo.

Follows the same pattern as ebs_backup.py: a dedicated sync SQLAlchemy
engine against the same Postgres database (own `vpn_` prefixed tables),
not the app's shared async Base/AsyncSession — the actual work here is
blocking I/O (a raw TCP reachability probe, Paramiko SSH to the FortiGate
CLI), which plain sync `def` FastAPI routes handle via auto-threadpooling
without needing to rewrite anything async.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings

settings = get_settings()

vpn_engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
VpnSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=vpn_engine)
VpnMonitorBase = declarative_base()


class VpnGateway(VpnMonitorBase):
    """One FortiGate SSL-VPN endpoint to monitor. `public_host`/`public_port`
    is what FortiClient users actually connect to (reachability probe target);
    `ssh_host`/`ssh_port` is the FortiGate's own admin CLI, used to query
    active sessions — often the same host but almost always a different port."""
    __tablename__ = "vpn_gateways"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(100), nullable=False)
    public_host = Column(String(255), nullable=False)
    public_port = Column(Integer, nullable=False, default=443)
    ssh_host    = Column(String(255))
    ssh_port    = Column(Integer, default=22)
    enabled     = Column(Boolean, default=True)
    notes       = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VpnCredential(VpnMonitorBase):
    """SSH admin credential for a gateway's FortiGate CLI. One per gateway —
    upsert replaces it. `secret_encrypted` holds the password, Fernet-encrypted
    via app.services.crypto (same primitive ebs_backup's vault_shim wraps)."""
    __tablename__ = "vpn_credentials"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    gateway_id       = Column(Integer, ForeignKey("vpn_gateways.id"), nullable=False, index=True)
    username         = Column(String(100), nullable=False)
    secret_encrypted = Column(Text, nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow)


class VpnCheckLog(VpnMonitorBase):
    """One row per reachability/session check (manual "Check Now" or the
    5-minute background poll) — powers the uptime history strip."""
    __tablename__ = "vpn_check_logs"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    gateway_id         = Column(Integer, ForeignKey("vpn_gateways.id"), nullable=False, index=True)
    checked_at         = Column(DateTime, default=datetime.utcnow, index=True)
    reachable          = Column(Boolean, nullable=False)
    latency_ms         = Column(Float)
    error              = Column(Text)
    active_user_count  = Column(Integer)


def init_vpn_db():
    """Create vpn_* tables idempotently — called from the app lifespan on
    every startup (not gated to dev only, mirroring init_ebs_db())."""
    VpnMonitorBase.metadata.create_all(bind=vpn_engine)


def get_vpn_db():
    """FastAPI dependency — sync Session (routes using this must be plain
    `def`, not `async def`, so FastAPI runs them in its threadpool)."""
    db = VpnSessionLocal()
    try:
        yield db
    finally:
        db.close()
