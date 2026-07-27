from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from app.database import Base


class UserApiKey(Base):
    """Per-user API keys for opt-in external AI providers (e.g. Gemini) — lets
    each user use their own account/quota for the AI Chatbot instead of the
    shared company key in Settings. Encrypted at rest (see app/services/crypto.py);
    falls back to the shared company key when a user hasn't set one."""
    __tablename__ = "user_api_keys"
    __table_args__ = (UniqueConstraint("username", "provider", name="uq_user_api_key_username_provider"),)

    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String(100), nullable=False, index=True)
    provider      = Column(String(30), nullable=False)  # e.g. "gemini"
    encrypted_key = Column(String(1000), nullable=False)
    key_hint      = Column(String(20))  # masked display, e.g. "••••vSXM" — never the full key
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
