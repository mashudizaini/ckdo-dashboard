"""
Oracle EBS Network Monitoring — why EBS is slow from HO, measured from
three vantage points no single one of which sees the whole path:

  - the dashboard server (Plant LAN, same subnet as EBS): scheduled TCP/HTTP
    probes to HO devices (= the HO<->Plant tunnel), Plant LAN, the EBS web
    tier and DB listener, and the internet; plus read-only SSH to the two
    FortiGates (SD-WAN SLA, IPsec tunnels) and an EBS/DB health query.
  - the HO laptop's browser: an in-page RTT / jitter / throughput test
    against this backend, i.e. across the same tunnel EBS traffic takes.
  - the HO laptop itself: a generated PowerShell agent (ping gateway + EBS,
    path MTU, Wi-Fi, CPU/RAM, Java, proxy) that posts its result back.

Same pattern as vpn_monitor.py: a dedicated sync SQLAlchemy engine with its
own `ebsnet_` tables, created idempotently at startup — never touched by
sync_schema.py, so prod needs no migration step for a new table here.
"""
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

ebsnet_engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
EbsNetSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ebsnet_engine)
EbsNetBase = declarative_base()


class EbsNetTarget(EbsNetBase):
    """One thing the server probes every 5 minutes. `segment` places it on
    the HO -> Plant path (see SEGMENTS in services/ebs_netmon/analysis.py);
    `check_type` is "tcp" (connect timing to host:port) or "http" (TTFB of
    `url`). No ICMP: the backend container has no ping binary and no
    CAP_NET_RAW, and a TCP handshake is one RTT anyway."""
    __tablename__ = "ebsnet_targets"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(120), nullable=False)
    segment    = Column(String(30), nullable=False, default="plant_lan")
    check_type = Column(String(10), nullable=False, default="tcp")
    host       = Column(String(255))
    port       = Column(Integer)
    url        = Column(String(500))
    enabled    = Column(Boolean, nullable=False, default=True)
    sequence   = Column(Integer, nullable=False, default=0)
    notes      = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EbsNetProbeLog(EbsNetBase):
    """One probe run of one target: `samples` attempts, summarised."""
    __tablename__ = "ebsnet_probe_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    target_id  = Column(Integer, ForeignKey("ebsnet_targets.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    samples    = Column(Integer)
    ok_count   = Column(Integer)
    loss_pct   = Column(Float)
    rtt_min    = Column(Float)
    rtt_avg    = Column(Float)
    rtt_max    = Column(Float)
    jitter_ms  = Column(Float)
    http_status = Column(Integer)
    error      = Column(Text)


class EbsNetSnapshot(EbsNetBase):
    """Point-in-time state of something that is not a simple probe:
    kind="fortigate" (one row per FortiGate, `source` = its name) or
    kind="ebs" (DB/app-tier health). `summary` is the parsed JSON the UI
    renders; `raw` keeps the CLI/query output for when a parser is wrong."""
    __tablename__ = "ebsnet_snapshots"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    kind       = Column(String(20), nullable=False, index=True)
    source     = Column(String(120))
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    ok         = Column(Boolean, nullable=False, default=True)
    summary    = Column(Text)
    raw        = Column(Text)
    error      = Column(Text)


class EbsNetClientReport(EbsNetBase):
    """A measurement taken on an HO laptop — from the in-browser test
    (source="browser") or the PowerShell agent (source="agent"). Headline
    numbers are columns so the list and fleet comparison can query them;
    everything else stays in `detail` JSON."""
    __tablename__ = "ebsnet_client_reports"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
    source        = Column(String(10), nullable=False)
    reported_by   = Column(String(150))
    hostname      = Column(String(150))
    location      = Column(String(30), default="HO")
    connection    = Column(String(30))           # LAN / Wi-Fi / VPN / unknown
    ebs_condition = Column(String(20))           # Normal / Slow / Hang / Restart
    note          = Column(Text)
    gw_rtt_avg    = Column(Float)
    gw_loss_pct   = Column(Float)
    ebs_rtt_avg   = Column(Float)
    ebs_rtt_max   = Column(Float)
    ebs_loss_pct  = Column(Float)
    ebs_jitter_ms = Column(Float)
    http_ttfb_ms  = Column(Float)
    down_mbps     = Column(Float)
    up_mbps       = Column(Float)
    path_mtu      = Column(Integer)
    cpu_pct       = Column(Float)
    ram_avail_pct = Column(Float)
    disk_pct      = Column(Float)
    wifi_signal   = Column(Integer)
    verdict       = Column(String(10))           # A / B / C / D / OK
    codes         = Column(String(200))          # comma-separated NET-01,CLI-06…
    detail        = Column(Text)


class EbsNetIncident(EbsNetBase):
    """Incident record (section 16 of the diagnostic script). `snapshot` is
    the server-side state captured when the incident was logged, so the
    correlation the script asks for ("match the timestamp against firewall,
    VPN, app server, DB") is already attached instead of reconstructed."""
    __tablename__ = "ebsnet_incidents"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    started_at        = Column(DateTime, nullable=False, index=True)
    ended_at          = Column(DateTime)
    status            = Column(String(20), nullable=False, default="open")
    user_name         = Column(String(150))
    laptop            = Column(String(150))
    location          = Column(String(30), default="HO")
    ebs_module        = Column(String(100))
    transaction       = Column(String(200))
    symptom           = Column(Text)
    root_cause_code   = Column(String(20))
    root_cause        = Column(Text)
    corrective_action = Column(Text)
    client_report_id  = Column(Integer)
    snapshot          = Column(Text)
    created_by        = Column(String(150))
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EbsNetAgentToken(EbsNetBase):
    """Lets a generated PowerShell agent post its result without a Keycloak
    login (it runs on a user's laptop, outside the browser). Random, expires,
    and only authorises POSTing one kind of report — nothing else."""
    __tablename__ = "ebsnet_agent_tokens"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    token      = Column(String(64), nullable=False, unique=True, index=True)
    label      = Column(String(150))
    created_by = Column(String(150))
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    uses       = Column(Integer, nullable=False, default=0)


class EbsNetSetting(EbsNetBase):
    """Key/value JSON settings — see DEFAULT_SETTINGS in services/ebs_netmon/settings.py."""
    __tablename__ = "ebsnet_settings"

    key        = Column(String(80), primary_key=True)
    value      = Column(Text)
    updated_by = Column(String(150))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_ebsnet_db():
    """Create ebsnet_* tables and seed the default targets once."""
    EbsNetBase.metadata.create_all(bind=ebsnet_engine)
    from app.services.ebs_netmon.settings import seed_defaults
    seed_defaults()


def get_ebsnet_db():
    """FastAPI dependency — sync Session (routes using it must be plain `def`)."""
    db = EbsNetSessionLocal()
    try:
        yield db
    finally:
        db.close()
