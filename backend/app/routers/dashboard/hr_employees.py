"""
HR Employee Router
Route prefix : /api/v1/dashboard/hr/employees
Upload file Excel karyawan → UPSERT ke PostgreSQL.
"""
import io
from datetime import datetime, date
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.employee import Employee, EmployeeUploadLog

router = APIRouter()

# ── Mapping kolom Excel → field model ─────────────────────────────────────────
# Index berdasarkan posisi kolom di baris 8 (0-based)
COL = {
    "user_id":                  1,
    "full_name":                2,
    "sex":                      3,
    "level":                    4,
    "department":               5,
    "division":                 6,
    "team":                     7,
    "job_title":                8,
    "work_placement":           9,
    "status":                   10,
    "date_of_joining":          11,
    "retire_date":              15,
    "pkwt_ke":                  16,
    "starting_pkwt":            17,
    "end_pkwt":                 18,
    "permanent_date":           19,
    "resign_date":              20,
    "place_of_birth":           21,
    "date_of_birth":            23,
    "no_bpjs_health":           27,
    "no_bpjs_employee":         28,
    "education_degree":         29,
    "education_school":         30,
    "education_major":          31,
    "employee_grade":           32,
    "working_experience_years": 33,
    "previous_company":         34,
    "address":                  38,
    "marital_status":           41,
    "phone_number":             42,
    "emergency_phone":          43,
    "religion":                 44,
    "blood_type":               45,
    "npwp_number":              47,
    "bank_account_bca":         52,
    "bank_account_name":        53,
    "personal_email":           79,
    "company_email":            80,
}

DATE_FIELDS = {"date_of_joining", "retire_date", "starting_pkwt", "end_pkwt",
               "permanent_date", "resign_date", "date_of_birth"}


def _to_str(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "-", "None") else s


def _to_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    return None


def _parse_row(row: tuple, batch_id: str) -> Optional[dict]:
    """Ubah satu baris Excel → dict field. Return None jika baris kosong."""
    user_id = _to_str(row[COL["user_id"]])
    if not user_id:
        return None

    data = {"upload_batch_id": batch_id, "uploaded_at": datetime.utcnow()}
    for field, col_idx in COL.items():
        if col_idx >= len(row):
            data[field] = None
            continue
        val = row[col_idx]
        if field in DATE_FIELDS:
            data[field] = _to_date(val)
        else:
            data[field] = _to_str(val)
    return data


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_employees(
    file:     UploadFile = File(...),
    notes:    str        = Form(""),
    db:       AsyncSession = Depends(get_db),
    user:     CurrentUser  = Depends(require_role(Roles.HR)),
):
    """
    Upload file Excel karyawan (format sesuai template ckdo employee.xlsx).
    Header di baris 8, data mulai baris 10.
    Logic: UPSERT berdasarkan user_id — insert baru atau update jika sudah ada.
    """
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="File harus berformat .xlsx atau .xlsm")

    contents = await file.read()
    batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File Excel tidak valid: {e}")

    if "Employee Data" not in wb.sheetnames:
        # Coba sheet pertama jika nama sheet berbeda
        ws = wb.active
    else:
        ws = wb["Employee Data"]

    inserted = 0
    updated  = 0
    skipped  = 0
    rows_parsed = []

    for row in ws.iter_rows(min_row=10, values_only=True):
        parsed = _parse_row(row, batch_id)
        if parsed is None:
            continue
        rows_parsed.append(parsed)

    if not rows_parsed:
        raise HTTPException(status_code=422, detail="Tidak ada data karyawan ditemukan di file. "
                            "Pastikan format file sesuai template (header di baris 8, data mulai baris 10).")

    # Cek user_id mana yang sudah ada
    existing_ids_result = await db.execute(
        select(Employee.user_id)
    )
    existing_ids = {r[0] for r in existing_ids_result.fetchall()}

    for data in rows_parsed:
        uid = data["user_id"]
        if uid in existing_ids:
            # UPDATE — semua field kecuali id
            await db.execute(
                update(Employee)
                .where(Employee.user_id == uid)
                .values(**{k: v for k, v in data.items()})
            )
            updated += 1
        else:
            db.add(Employee(**data))
            inserted += 1

    await db.flush()

    # Simpan log upload
    log = EmployeeUploadLog(
        batch_id    = batch_id,
        filename    = file.filename,
        total_rows  = len(rows_parsed),
        inserted    = inserted,
        updated     = updated,
        skipped     = skipped,
        uploaded_by = user.username or "unknown",
        notes       = notes or None,
    )
    db.add(log)

    return {
        "batch_id":   batch_id,
        "filename":   file.filename,
        "total_rows": len(rows_parsed),
        "inserted":   inserted,
        "updated":    updated,
        "skipped":    skipped,
        "message":    f"Upload berhasil: {inserted} karyawan baru, {updated} diperbarui.",
    }


# ── Query endpoints ────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_employee_summary(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Statistik ringkasan untuk KPI cards."""
    total_q   = await db.execute(select(func.count()).select_from(Employee))
    total     = total_q.scalar() or 0

    perm_q    = await db.execute(
        select(func.count()).select_from(Employee).where(Employee.status == "Permanent")
    )
    permanent = perm_q.scalar() or 0

    contract_q = await db.execute(
        select(func.count()).select_from(Employee).where(Employee.status != "Permanent").where(Employee.status != None)
    )
    contract  = contract_q.scalar() or 0

    by_dept_q = await db.execute(
        select(Employee.department, func.count().label("total"))
        .group_by(Employee.department)
        .order_by(func.count().desc())
    )
    by_dept = [{"department": r[0] or "—", "total": r[1]} for r in by_dept_q.fetchall()]

    by_level_q = await db.execute(
        select(Employee.level, func.count().label("total"))
        .group_by(Employee.level)
        .order_by(func.count().desc())
    )
    by_level = [{"level": r[0] or "—", "total": r[1]} for r in by_level_q.fetchall()]

    by_sex_q = await db.execute(
        select(Employee.sex, func.count().label("total"))
        .group_by(Employee.sex)
    )
    by_sex = {r[0]: r[1] for r in by_sex_q.fetchall()}

    return {
        "total":     total,
        "permanent": permanent,
        "contract":  contract,
        "by_dept":   by_dept,
        "by_level":  by_level,
        "male":      by_sex.get("M", 0),
        "female":    by_sex.get("F", 0),
    }


@router.get("")
async def list_employees(
    search:     str           = Query(""),
    department: Optional[str] = Query(None),
    status:     Optional[str] = Query(None),
    level:      Optional[str] = Query(None),
    team:       Optional[str] = Query(None),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(25, ge=1, le=100),
    db:         AsyncSession  = Depends(get_db),
    user:       CurrentUser   = Depends(require_role(Roles.HR)),
):
    """List karyawan dengan search, filter, dan pagination."""
    q = select(Employee)

    if search:
        term = f"%{search}%"
        q = q.where(
            Employee.full_name.ilike(term)  |
            Employee.user_id.ilike(term)    |
            Employee.job_title.ilike(term)
        )
    if department:
        q = q.where(Employee.department == department)
    if status:
        q = q.where(Employee.status == status)
    if level:
        q = q.where(Employee.level == level)
    if team:
        q = q.where(Employee.team == team)

    # Total count
    count_q  = await db.execute(select(func.count()).select_from(q.subquery()))
    total    = count_q.scalar() or 0

    # Paginated result
    q        = q.order_by(Employee.department, Employee.full_name)
    q        = q.offset((page - 1) * page_size).limit(page_size)
    result   = await db.execute(q)
    employees = result.scalars().all()

    def _emp_dict(e: Employee) -> dict:
        return {
            "id":              e.id,
            "user_id":         e.user_id,
            "full_name":       e.full_name,
            "sex":             e.sex,
            "level":           e.level,
            "department":      e.department,
            "division":        e.division,
            "team":            e.team,
            "job_title":       e.job_title,
            "work_placement":  e.work_placement,
            "status":          e.status,
            "date_of_joining": str(e.date_of_joining) if e.date_of_joining else None,
            "date_of_birth":   str(e.date_of_birth)   if e.date_of_birth   else None,
            "retire_date":     str(e.retire_date)      if e.retire_date     else None,
            "end_pkwt":        str(e.end_pkwt)         if e.end_pkwt        else None,
            "marital_status":  e.marital_status,
            "religion":        e.religion,
            "education_degree":e.education_degree,
            "company_email":   e.company_email,
            "phone_number":    e.phone_number,
            "employee_grade":  e.employee_grade,
        }

    return {
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "pages":      (total + page_size - 1) // page_size,
        "employees":  [_emp_dict(e) for e in employees],
    }


@router.get("/upload-logs")
async def get_upload_logs(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Riwayat upload file Excel."""
    result = await db.execute(
        select(EmployeeUploadLog)
        .order_by(EmployeeUploadLog.uploaded_at.desc())
        .limit(20)
    )
    logs = result.scalars().all()
    return [
        {
            "batch_id":    l.batch_id,
            "filename":    l.filename,
            "total_rows":  l.total_rows,
            "inserted":    l.inserted,
            "updated":     l.updated,
            "uploaded_by": l.uploaded_by,
            "uploaded_at": l.uploaded_at.isoformat() if l.uploaded_at else None,
            "notes":       l.notes,
        }
        for l in logs
    ]


@router.get("/departments")
async def get_departments(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Daftar department untuk filter dropdown."""
    result = await db.execute(
        select(Employee.department).distinct().order_by(Employee.department)
    )
    return [r[0] for r in result.fetchall() if r[0]]


@router.get("/teams")
async def get_teams(
    department: Optional[str] = Query(None),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Daftar team untuk filter dropdown, opsional difilter per department."""
    q = select(Employee.team).distinct().order_by(Employee.team)
    if department:
        q = q.where(Employee.department == department)
    result = await db.execute(q)
    return [r[0] for r in result.fetchall() if r[0]]
