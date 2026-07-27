from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class MeetingRecording(Base):
    """
    A meeting audio recording (live-recorded in-browser or uploaded) plus its
    transcript and generated Minutes of Meeting. Recorded and uploaded audio
    both flow through the same /transcribe endpoint and land in this single
    table, so History shows one unified list regardless of source — and the
    audio file itself is kept on disk (not deleted after transcription, unlike
    the older reference implementation) so it can be re-downloaded later.
    """
    __tablename__ = "meeting_recordings"

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    filename                 = Column(String(255), nullable=False)  # stored filename on disk (uploads/meeting_notes/)
    original_name            = Column(String(255))
    source                   = Column(String(20), nullable=False)  # "recorded" | "uploaded"
    status                   = Column(String(20), default="uploaded")  # uploaded -> transcribing -> transcribed -> error
    error_message            = Column(Text)

    meeting_title            = Column(String(300))
    participants             = Column(String(500))

    transcript               = Column(Text)
    transcript_language      = Column(String(10))
    audio_duration_seconds   = Column(Float)
    processing_time_seconds  = Column(Float)

    mom_meta                 = Column(JSONB)  # {date, time, venue, agenda}
    mom_json                 = Column(JSONB)  # {departments: [...]}  — the editable MOM structure, persisted so it can be reopened

    created_by               = Column(String(100))
    created_at               = Column(DateTime, default=datetime.utcnow)
    updated_at               = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
