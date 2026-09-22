from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from app.database import Base


class DepartmentMaster(Base):
    """Canonical department/division/team hierarchy + display order — the
    single source of truth for how Employee Summary (and any other LOV that
    wants a curated, non-alphabetical order) lists department/division/team
    rows. Self-referencing so one table covers all three levels: a
    department row has parent_id NULL, a division row's parent_id points at
    its department, and a team row's parent_id points at its division (or
    straight at its department, for departments with no division layer).

    `name` values are matched against the *existing* raw Employee.department/
    division/team strings already in use elsewhere (e.g. "GA", "QA" — not
    "General Affair"/"Quality Assurance") — this table only curates ORDER,
    it isn't a display-label override, so it never needs to stay in lockstep
    with a separate rename of the underlying Employee data."""
    __tablename__ = "department_master"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(150), nullable=False)
    # "director" (the President Director singleton) | "department" | "division" | "team"
    type       = Column(String(20), nullable=False)
    parent_id  = Column(Integer, ForeignKey("department_master.id"), nullable=True, index=True)
    sequence   = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
