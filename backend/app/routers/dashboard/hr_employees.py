"""
HR Employee Router
Route prefix : /api/v1/dashboard/hr/employees
Upload file Excel karyawan (export standar Talenta) → REPLACE seluruh data di PostgreSQL.
"""
import io
from datetime import datetime, date, timedelta
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.employee import Employee, EmployeeUploadLog

router = APIRouter()

# ── Mapping kolom Excel → field model ─────────────────────────────────────────
# Index berdasarkan posisi kolom di baris 1 (0-based), sesuai export standar Talenta
# (sheet "Employee Data", header di baris 1, data mulai baris 2).
COL = {
    "user_id":                  0,
    "full_name":                1,
    "sex":                      2,
    "level":                    3,
    "department":               4,
    "division":                 5,
    "team":                     6,
    "job_title":                7,
    "work_placement":           8,
    "status":                   9,
    "date_of_joining":          10,
    "retire_date":              14,
    "pkwt_ke":                  15,
    "starting_pkwt":            16,
    "end_pkwt":                 17,
    "permanent_date":           18,
    "resign_date":              19,
    "place_of_birth":           20,
    "date_of_birth":            22,
    "no_bpjs_health":           26,
    "no_bpjs_employee":         27,
    "education_degree":         28,   # "Master, Chung-Ang University" — dipecah jadi degree + school
    "education_major":          29,
    "employee_grade":           30,
    "working_experience_years": 31,
    "previous_company":         32,
    "address":                  36,
    "marital_status":           39,
    "phone_number":             40,
    "emergency_phone":          41,
    "religion":                 42,
    "blood_type":               43,
    "npwp_number":               45,
    "bank_account_bca":         50,
    "bank_account_name":        51,
    "personal_email":           77,
    "company_email":            78,
}

DATE_FIELDS = {"date_of_joining", "retire_date", "starting_pkwt", "end_pkwt",
               "permanent_date", "resign_date", "date_of_birth"}

# Panjang maksimum kolom String() di model Employee — dipakai untuk truncate defensif
# supaya upload tidak crash kalau data dari Talenta lebih panjang dari perkiraan.
MAXLEN = {
    "user_id": 20, "full_name": 200, "sex": 1, "level": 80, "department": 100,
    "division": 100, "team": 100, "job_title": 200, "work_placement": 100,
    "status": 50, "pkwt_ke": 30, "place_of_birth": 100, "no_bpjs_health": 50,
    "no_bpjs_employee": 50, "education_degree": 50, "education_school": 200,
    "education_major": 200, "employee_grade": 20, "working_experience_years": 20,
    "previous_company": 200, "marital_status": 50, "phone_number": 50,
    "emergency_phone": 50, "religion": 50, "blood_type": 5, "npwp_number": 50,
    "bank_account_bca": 50, "bank_account_name": 200, "personal_email": 200,
    "company_email": 200,
}

_EMPTY_MARKERS = ("", "-", "none", "n/a", "na", "null")


def _to_str(val, field: str = None) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, float) and val.is_integer():
        s = str(int(val))
    else:
        s = str(val).strip()
    if s.lower() in _EMPTY_MARKERS:
        return None
    max_len = MAXLEN.get(field) if field else None
    return s[:max_len] if max_len else s


def _to_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, (int, float)):
        # Excel serial date (1900 date system) — fallback untuk cell yang belum
        # ter-format sebagai tanggal saat file di-convert dari .xls lama.
        try:
            return (datetime(1899, 12, 30) + timedelta(days=val)).date()
        except (OverflowError, ValueError):
            return None
    s = str(val).strip()
    if s.lower() in _EMPTY_MARKERS:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_row(row: tuple, batch_id: str) -> Optional[dict]:
    """Ubah satu baris Excel → dict field. Return None jika baris kosong."""
    def cell(idx):
        return row[idx] if idx < len(row) else None

    user_id = _to_str(cell(COL["user_id"]), "user_id")
    if not user_id:
        return None

    data = {"upload_batch_id": batch_id, "uploaded_at": datetime.utcnow(), "user_id": user_id}
    for field, col_idx in COL.items():
        if field == "user_id":
            continue
        val = cell(col_idx)
        if field in DATE_FIELDS:
            data[field] = _to_date(val)
        elif field == "education_degree":
            # Talenta menggabungkan "Degree, School" dalam satu sel.
            raw = _to_str(val)
            if raw and "," in raw:
                degree, school = raw.split(",", 1)
                data["education_degree"] = degree.strip()[:MAXLEN["education_degree"]]
                data["education_school"] = school.strip()[:MAXLEN["education_school"]]
            else:
                data["education_degree"] = (raw or "")[:MAXLEN["education_degree"]] or None
                data["education_school"] = None
        else:
            data[field] = _to_str(val, field)
    return data


def _extract_rows(contents: bytes, filename: str) -> list:
    """Baca file Excel (.xls lama atau .xlsx/.xlsm) → list of row tuples, data mulai baris 2."""
    if filename.lower().endswith(".xls"):
        import xlrd
        wb = xlrd.open_workbook(file_contents=contents)
        sheet = wb.sheet_by_name("Employee Data") if "Employee Data" in wb.sheet_names() else wb.sheet_by_index(0)
        return [tuple(sheet.row_values(r)) for r in range(1, sheet.nrows)]

    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    ws = wb["Employee Data"] if "Employee Data" in wb.sheetnames else wb.active
    return list(ws.iter_rows(min_row=2, values_only=True))


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_employees(
    file:     UploadFile = File(...),
    notes:    str        = Form(""),
    db:       AsyncSession = Depends(get_db),
    user:     CurrentUser  = Depends(require_role(Roles.HR)),
):
    """
    Upload file Excel karyawan (export standar Talenta, sheet "Employee Data").
    Header di baris 1, data mulai baris 2.
    Logic: REPLACE — seluruh data karyawan lama dihapus, diganti data dari file baru.
    """
    if not file.filename.lower().endswith((".xls", ".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="File harus berformat .xls, .xlsx, atau .xlsm")

    contents = await file.read()
    batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        data_rows = _extract_rows(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File Excel tidak valid: {e}")

    rows_parsed = []
    seen_ids = set()
    skipped = 0
    try:
        for row in data_rows:
            parsed = _parse_row(row, batch_id)
            if parsed is None:
                continue
            if parsed["user_id"] in seen_ids:
                skipped += 1
                continue
            seen_ids.add(parsed["user_id"])
            rows_parsed.append(parsed)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Gagal membaca baris data: {e}")

    if not rows_parsed:
        raise HTTPException(status_code=422, detail="Tidak ada data karyawan ditemukan di file. "
                            "Pastikan sheet bernama 'Employee Data' dengan header di baris pertama.")

    try:
        # REPLACE — hapus seluruh data lama, ganti dengan data dari file baru
        deleted_result = await db.execute(delete(Employee))
        replaced_count = deleted_result.rowcount or 0

        db.add_all(Employee(**data) for data in rows_parsed)
        await db.flush()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Gagal menyimpan data ke database: {e}")

    # Simpan log upload
    log = EmployeeUploadLog(
        batch_id    = batch_id,
        filename    = file.filename,
        total_rows  = len(rows_parsed),
        inserted    = len(rows_parsed),
        updated     = 0,
        skipped     = skipped,
        uploaded_by = user.username or "unknown",
        notes       = notes or None,
    )
    db.add(log)

    return {
        "batch_id":          batch_id,
        "filename":          file.filename,
        "total_rows":        len(rows_parsed),
        "inserted":          len(rows_parsed),
        "updated":           0,
        "skipped":           skipped,
        "replaced_previous": replaced_count,
        "message":           f"Upload berhasil: {len(rows_parsed)} data karyawan menggantikan {replaced_count} data lama.",
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
