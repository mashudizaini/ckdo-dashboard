from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from app.database import Base


class OrgStructureNode(Base):
    """One position/employee in the (manually curated) organization chart —
    separate from the Employee table's auto-derived level/department-based
    supervisor_id, since HR needs to hand-correct the reporting lines directly."""
    __tablename__ = "org_structure_nodes"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    full_name      = Column(String(200), nullable=False)
    position       = Column(String(200))
    department     = Column(String(100))   # top-level branch, e.g. Sales & Marketing
    division       = Column(String(100))
    sub_team       = Column(String(100))
    join_date      = Column(Date)
    supervisor_id  = Column(Integer, ForeignKey("org_structure_nodes.id"), nullable=True, index=True)
    # Controls left-to-right / top-to-bottom order among siblings under the same
    # supervisor. Import assigns this from department order + original row order;
    # manual adds append to the end of their sibling group by default.
    sort_order     = Column(Integer, default=0)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrgStructureUploadLog(Base):
    """Riwayat setiap kali struktur organisasi diimpor dari Excel."""
    __tablename__ = "org_structure_upload_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), unique=True, nullable=False)
    filename    = Column(String(255))
    total_rows  = Column(Integer, default=0)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(Text)
