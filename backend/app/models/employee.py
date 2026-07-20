from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(String(20),  unique=True, nullable=False, index=True)
    full_name       = Column(String(200))
    sex             = Column(String(1))
    level           = Column(String(80))
    department      = Column(String(100))
    division        = Column(String(100))
    team            = Column(String(100))
    job_title       = Column(String(200))
    work_placement  = Column(String(100))
    status          = Column(String(50))       # Permanent / Contract
    date_of_joining = Column(Date)
    retire_date     = Column(Date)
    pkwt_ke         = Column(String(30))
    starting_pkwt   = Column(Date)
    end_pkwt        = Column(Date)
    permanent_date  = Column(Date)
    resign_date     = Column(Date)
    place_of_birth  = Column(String(100))
    date_of_birth   = Column(Date)
    no_bpjs_health  = Column(String(50))
    no_bpjs_employee= Column(String(50))
    education_degree= Column(String(50))
    education_school= Column(String(200))
    education_major = Column(String(200))
    employee_grade  = Column(String(20))
    supervisor_id   = Column(String(20), index=True)  # NIK atasan langsung — dipakai untuk Organization Chart
    working_experience_years = Column(String(20))
    previous_company= Column(String(200))
    address         = Column(Text)
    marital_status  = Column(String(50))
    phone_number    = Column(String(50))
    emergency_phone = Column(String(50))
    religion        = Column(String(50))
    blood_type      = Column(String(5))
    npwp_number     = Column(String(50))
    bank_account_bca= Column(String(50))
    bank_account_name=Column(String(200))
    personal_email  = Column(String(200))
    company_email   = Column(String(200))

    # Upload metadata
    upload_batch_id = Column(String(50), index=True)
    uploaded_at     = Column(DateTime, default=datetime.utcnow)


class EmployeeUploadLog(Base):
    """Riwayat setiap kali file Excel diupload."""
    __tablename__ = "employee_upload_logs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    batch_id       = Column(String(50), unique=True, nullable=False)
    filename       = Column(String(255))
    total_rows     = Column(Integer, default=0)
    inserted       = Column(Integer, default=0)
    updated        = Column(Integer, default=0)
    skipped        = Column(Integer, default=0)
    uploaded_by    = Column(String(100))
    uploaded_at    = Column(DateTime, default=datetime.utcnow)
    notes          = Column(Text)
