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
