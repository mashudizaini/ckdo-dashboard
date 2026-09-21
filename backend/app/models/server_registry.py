"""
Server Control — centralized inventory of the company's own infrastructure
(hypervisors, DB/App servers, network gear, SaaS admin consoles, etc.) plus
their access credentials, encrypted at rest. Replaces the informal Excel
sheet IT was keeping for this (server name/IP/username/password columns) —
the login secrets get the same field-level encryption already used for VPN
gateway credentials and per-user AI API keys (see app/services/crypto.py),
NOT stored as plain text like the spreadsheet had them.

Every credential reveal is logged (ServerCredentialAccessLog) — who looked
at which server's credential and when — since this table is, by design, a
single high-value target once centralized; the audit trail is the tradeoff
that makes centralizing it defensible.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class ServerEntry(Base):
    """One row per physical/virtual server, network device, or admin
    console — category is free text on purpose (the source spreadsheet's
    own groupings — Hypervisor, Database, Application, Network, Storage,
    Mail, SaaS, VM — don't need to be a rigid enum; an admin can type
    whatever grouping makes sense as the inventory grows)."""
    __tablename__ = "server_registry_entries"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(150), nullable=False)
    category   = Column(String(50), nullable=False, default="Other")
    address    = Column(String(300))  # IP / hostname / URL
    notes      = Column(Text)
    sequence   = Column(Integer, nullable=False, default=0)
    created_by = Column(String(150))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServerCredential(Base):
    """A username/password pair for one server. One server can have
    several (the source spreadsheet had e.g. 4 separate mail accounts
    under one "MAIL" row) — label distinguishes them in the UI
    ("Local Admin", "Domain Admin", a person's name, etc.)."""
    __tablename__ = "server_registry_credentials"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    server_id        = Column(Integer, ForeignKey("server_registry_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    label            = Column(String(100))
    username         = Column(String(150))
    secret_encrypted = Column(Text, nullable=False)
    notes            = Column(Text)
    created_by       = Column(String(150))
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServerCredentialAccessLog(Base):
    """Append-only audit trail of every credential reveal. Deliberately NOT
    foreign-keyed to ServerCredential (no ON DELETE behavior to reason
    about) — server_name/credential_label are captured as a snapshot at
    access time so the log stays meaningful even after the credential
    itself is edited or deleted."""
    __tablename__ = "server_registry_access_log"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    credential_id     = Column(Integer, nullable=False, index=True)
    server_name       = Column(String(150))
    credential_label  = Column(String(150))
    accessed_by       = Column(String(150), nullable=False)
    accessed_at       = Column(DateTime, default=datetime.utcnow, index=True)
