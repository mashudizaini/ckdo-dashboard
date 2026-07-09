from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey
from app.database import Base


class CvScreeningJob(Base):
    """A screening job = one open position with its requirements/config."""
    __tablename__ = "cv_screening_jobs"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    position_title          = Column(String(300), nullable=False)
    required_skills         = Column(Text)    # JSON list
    min_experience          = Column(Integer, default=0)
    education_keywords      = Column(Text)    # JSON list
    certification_keywords  = Column(Text)    # JSON list
    weight_skills           = Column(Integer, default=40)
    weight_experience       = Column(Integer, default=30)
    weight_education        = Column(Integer, default=20)
    weight_certification    = Column(Integer, default=10)
    created_by              = Column(String(100))
    created_at               = Column(DateTime, default=datetime.utcnow)


class CvScreeningCandidate(Base):
    """One screened CV result, tied to a job."""
    __tablename__ = "cv_screening_candidates"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    job_id                  = Column(Integer, ForeignKey("cv_screening_jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    filename                = Column(String(500))
    name                    = Column(String(200))
    email                   = Column(String(200))
    phone                   = Column(String(50))
    education                = Column(String(300))
    experience_years         = Column(Integer, default=0)
    total_experience_years   = Column(Integer, default=0)
    positions                 = Column(Text)   # JSON list of {title, company, duration, relevant}
    skills_found              = Column(Text)   # JSON list
    missing_skills             = Column(Text)  # JSON list
    additional_relevant_skills  = Column(Text) # JSON list
    certifications                = Column(Text)  # JSON list of {name, year, relevant}
    skills_score                = Column(Float, default=0)
    experience_score             = Column(Float, default=0)
    education_score               = Column(Float, default=0)
    certification_score            = Column(Float, default=0)
    total_score                     = Column(Float, default=0, index=True)
    recommendation                   = Column(String(50), index=True)
    confidence                        = Column(String(20))
    reasoning                          = Column(Text)
    interview_focus                     = Column(Text)  # JSON list
    red_flags                           = Column(Text)  # JSON list
    strengths                            = Column(Text) # JSON list
    error                                 = Column(Text)
    screened_at                           = Column(DateTime, default=datetime.utcnow)
