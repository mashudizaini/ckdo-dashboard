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
        select(func.count()).select_from(Employee).where(Employee.status == "Contract")
    )
    contract  = contract_q.scalar() or 0

    probation_q = await db.execute(
        select(func.count()).select_from(Employee).where(Employee.status == "Probation")
    )
    probation = probation_q.scalar() or 0

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
        "probation": probation,
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
    sex:        Optional[str] = Query(None),
    sort_by:    str           = Query("full_name"),
    sort_dir:   str           = Query("asc"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(25, ge=1, le=100),
    db:         AsyncSession  = Depends(get_db),
    user:       CurrentUser   = Depends(require_role(Roles.HR)),
):
    """List karyawan dengan search, filter, pagination, dan sorting."""
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
    if sex:
        q = q.where(Employee.sex == sex)
    if status:
        q = q.where(Employee.status == status)
    if level:
        q = q.where(Employee.level == level)
    if team:
        q = q.where(Employee.team == team)

    # Total count
    count_q  = await db.execute(select(func.count()).select_from(q.subquery()))
    total    = count_q.scalar() or 0

    # Dynamic sort
    _SORT_COLS = {
        "user_id":          Employee.user_id,
        "full_name":        Employee.full_name,
        "level":            Employee.level,
        "department":       Employee.department,
        "division":         Employee.division,
        "job_title":        Employee.job_title,
        "work_placement":   Employee.work_placement,
        "status":           Employee.status,
        "sex":              Employee.sex,
        "employee_grade":   Employee.employee_grade,
        "education_degree": Employee.education_degree,
        "marital_status":   Employee.marital_status,
        "date_of_joining":  Employee.date_of_joining,
        "end_pkwt":         Employee.end_pkwt,
    }
    sort_col = _SORT_COLS.get(sort_by, Employee.full_name)
    q        = q.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())
    q        = q.offset((page - 1) * page_size).limit(page_size)
    result   = await db.execute(q)
    employees = result.scalars().all()

    def _emp_dict(e: Employee) -> dict:
        return {
            "id":               e.id,
            "user_id":          e.user_id,
            "full_name":        e.full_name,
            "sex":              e.sex,
            "level":            e.level,
            "department":       e.department,
            "division":         e.division,
            "team":             e.team,
            "job_title":        e.job_title,
            "work_placement":   e.work_placement,
            "status":           e.status,
            "employee_grade":   e.employee_grade,
            "education_degree": e.education_degree,
            "education_school": e.education_school,
            "education_major":  e.education_major,
            "marital_status":   e.marital_status,
            "religion":         e.religion,
            "blood_type":       e.blood_type,
            "phone_number":     e.phone_number,
            "company_email":    e.company_email,
            "personal_email":   e.personal_email,
            "date_of_joining":  str(e.date_of_joining)  if e.date_of_joining  else None,
            "date_of_birth":    str(e.date_of_birth)    if e.date_of_birth    else None,
            "retire_date":      str(e.retire_date)       if e.retire_date      else None,
            "end_pkwt":         str(e.end_pkwt)          if e.end_pkwt         else None,
            "starting_pkwt":    str(e.starting_pkwt)     if e.starting_pkwt    else None,
            "pkwt_ke":          e.pkwt_ke,
            "permanent_date":   str(e.permanent_date)    if e.permanent_date   else None,
            "resign_date":      str(e.resign_date)        if e.resign_date      else None,
        }

    return {
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "pages":      (total + page_size - 1) // page_size,
        "employees":  [_emp_dict(e) for e in employees],
    }


@router.get("/monthly-summary")
async def get_monthly_summary(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Monthly headcount trend + demographic breakdowns."""
    import traceback
    from datetime import date
    from calendar import monthrange
    from sqlalchemy import and_, cast, String

    MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    try:
        # Monthly joinings map — cast date to text for grouping
        joins_q = await db.execute(
            select(
                func.to_char(Employee.date_of_joining, "YYYY-MM").label("month"),
                func.count().label("cnt"),
            )
            .where(Employee.date_of_joining.isnot(None))
            .group_by(func.to_char(Employee.date_of_joining, "YYYY-MM"))
        )
        joins_map = {r[0]: r[1] for r in joins_q.fetchall()}
    except Exception as e:
        raise HTTPException(500, f"joins_q error: {e}\n{traceback.format_exc()}")

    try:
        # All join/resign pairs for cumulative headcount
        emps_q = await db.execute(
            select(Employee.date_of_joining, Employee.resign_date)
            .where(Employee.date_of_joining.isnot(None))
        )
        emps = [(r[0], r[1]) for r in emps_q.fetchall()]
    except Exception as e:
        raise HTTPException(500, f"emps_q error: {e}")

    today = date.today()

    def _month_back(base_year, base_month, n):
        m = base_month - n
        y = base_year
        while m <= 0:
            m += 12
            y -= 1
        return y, m

    # Headcount trend — last 36 months
    headcount_trend = []
    for i in range(35, -1, -1):
        y, m = _month_back(today.year, today.month, i)
        last_day  = date(y, m, monthrange(y, m)[1])
        first_day = date(y, m, 1)
        cnt = sum(
            1 for join, resign in emps
            if join <= last_day and (resign is None or resign >= first_day)
        )
        headcount_trend.append({"month": f"{y}-{m:02d}", "label": f"{MN[m-1]} '{str(y)[2:]}", "count": cnt})

    # Monthly joinings — last 24 months
    monthly_joins = []
    for i in range(23, -1, -1):
        y, m = _month_back(today.year, today.month, i)
        key = f"{y}-{m:02d}"
        monthly_joins.append({"month": key, "label": f"{MN[m-1]} '{str(y)[2:]}", "joins": joins_map.get(key, 0)})

    # Generic breakdown helper — explicit AND to avoid any dialect issues
    async def _bd(col):
        try:
            q = await db.execute(
                select(col, func.count().label("total"))
                .where(and_(col.isnot(None), col != ""))
                .group_by(col)
                .order_by(func.count().desc())
            )
            return [{"name": r[0], "total": r[1]} for r in q.fetchall()]
        except Exception:
            return []

    by_dept    = await _bd(Employee.department)
    by_level   = await _bd(Employee.level)
    by_edu     = await _bd(Employee.education_degree)
    by_marital = await _bd(Employee.marital_status)
    by_status  = await _bd(Employee.status)
    by_grade   = await _bd(Employee.employee_grade)
    by_religion= await _bd(Employee.religion)

    try:
        sex_q   = await db.execute(select(Employee.sex, func.count().label("t")).group_by(Employee.sex))
        sex_map = {r[0]: r[1] for r in sex_q.fetchall()}
    except Exception:
        sex_map = {}

    by_gender = [
        {"name": "Laki-laki", "total": sex_map.get("M", 0)},
        {"name": "Perempuan", "total": sex_map.get("F", 0)},
    ]

    return {
        "headcount_trend": headcount_trend,
        "monthly_joins":   monthly_joins,
        "by_dept":         by_dept,
        "by_level":        by_level,
        "by_education":    by_edu,
        "by_marital":      by_marital,
        "by_status":       by_status,
        "by_grade":        by_grade,
        "by_religion":     by_religion,
        "by_gender":       by_gender,
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
