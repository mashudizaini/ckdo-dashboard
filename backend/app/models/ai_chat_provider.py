from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class AiChatProviderSetting(Base):
    """
    Per-provider on/off switch for the AI Chatbot's 3 chat modes (Policy/
    Oracle/General) — a usage/cost control lever for IT/admin (e.g.
    temporarily turning off Claude company-wide instead of relying on
    every user remembering not to pick it), separate from Keycloak roles.
    Scoped to the chatbot only — does NOT affect other features that also
    call onprem/anthropic/gemini internally (CV Screening, JD Generator,
    AP Invoice OCR, Meeting Notes, PAC Business Plan Outlook, etc.), which
    have no dependency on this table.

    No row for a provider means enabled — the opposite default from
    UserMenuAccess (app/models/menu_access.py) deliberately: that one
    gates brand-new modules that should start locked down, while this one
    toggles providers already live in production, so shipping this
    feature must not silently disable anything.
    """
    __tablename__ = "ai_chat_provider_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    provider   = Column(String(30), nullable=False, unique=True, index=True)
    enabled    = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiChatDefaultProvider(Base):
    """Which provider each of the AI Chatbot's 3 modes (Policy/Oracle/
    General) starts on for a user who hasn't picked one yet this session —
    admin-configurable via Setup > AI > Model Access instead of the
    hardcoded DEFAULT_PROVIDER_BY_TAB constant that used to live in
    Chatbot.jsx/ChatWidget.jsx. No row for a mode means the original
    hardcoded default still applies (see ai_chat_provider_service.py's
    DEFAULT_FALLBACK) — shipping this feature must not change anyone's
    current experience until IT/admin actually changes a value."""
    __tablename__ = "ai_chat_default_providers"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    mode       = Column(String(20), nullable=False, unique=True, index=True)
    provider   = Column(String(30), nullable=False)
    updated_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
