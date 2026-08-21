from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base


class DocumentGlossaryTerm(Base):
    """
    Shared term dictionary for Document Converter translation — the single
    source of truth for how a source term should read in each target
    language, injected into every translation prompt (see
    document_translation_service.build_glossary_block) so terms like 전결/
    기안/전표 stay consistent across every document and across time,
    instead of the LLM picking a plausible-but-different phrasing each run.
    A human correcting one row here fixes it for every future translation,
    without needing to re-translate anything already done.
    """
    __tablename__ = "document_glossary_terms"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    source_term  = Column(String(200), nullable=False, index=True)
    target_en    = Column(String(300))
    target_id    = Column(String(300))
    domain       = Column(String(30))   # pharma | finance | hr | general | ...
    notes        = Column(Text)
    created_by   = Column(String(100))
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
