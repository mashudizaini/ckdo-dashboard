from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class SpeakerVoiceprint(Base):
    """
    An enrolled voice — one row per person, holding the embedding vector
    produced by the ai-engine diarization service's /embed endpoint (see
    app/services/speaker_id_service.py). Used to match unnamed speaker
    clusters detected in a meeting recording back to real names.
    """
    __tablename__ = "speaker_voiceprints"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    name              = Column(String(100), nullable=False)
    gender            = Column(String(10))
    position          = Column(String(200))
    team              = Column(String(100))
    embedding         = Column(JSONB, nullable=False)  # list[float]
    sample_filename   = Column(String(255))  # original enrollment clip name, kept for reference/re-enroll

    created_by        = Column(String(100))
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
