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
from pydantic import BaseModel
from sqlalchemy import func, select, delete, extract, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, get_current_user, CurrentUser, Roles
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

# Talenta exports mix Indonesian and English marital-status values depending on
# who entered the data — normalize to English so the dashboard is consistent
# (this is a foreign company, all UI/data labels must read in English).
_MARITAL_MAP = {
    "menikah": "Married",
    "belum menikah": "Single",
    "cerai": "Divorced",
    "cerai hidup": "Divorced",
    "cerai mati": "Widow",
    "duda": "Widower",
    "janda": "Widow",
}


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
        elif field == "marital_status":
            raw = _to_str(val, field)
            data["marital_status"] = _MARITAL_MAP.get(raw.lower(), raw) if raw else None
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


# ── Organization Chart — derive "reports to" from level/department/division/team ──
# Talenta's export has no "Direct Supervisor" column, so instead of leaving every
# employee's supervisor blank after each REPLACE upload, infer it from the existing
# level/department/division/team fields: within each (department, division, team)
# group the most senior `level` becomes that group's lead, everyone else in the group
# reports to the lead, and each group's lead reports to the lead of its parent group
# (team → division → department → President Director). HR can still correct any one
# employee's supervisor afterward via PATCH /{user_id}/supervisor.
_LEVEL_RANK = {
    "Director": 0, "General Manager": 1, "Senior Manager": 2, "Manager": 3,
    "Assistant Manager": 4, "Supervisor": 5, "Senior Staff": 6,
    "Officer": 7, "Staff": 7, "Operator / Clerk": 8,
}


def _assign_supervisors(rows: list) -> None:
    """Mutates each row dict in `rows`, setting row['supervisor_id']. No-op if no
    'President Director' row is found (nothing recognizable to anchor the chart to)."""
    def rank(row):
        return _LEVEL_RANK.get(row.get("level"), 9)

    root = next((r for r in rows if (r.get("job_title") or "").strip().lower() == "president director"), None)
    if root is None:
        return
    root["supervisor_id"] = None

    # Plant's Director sits in a separate "Director" pseudo-department alongside the
    # President Director rather than in a (department="Plant", division="", team="")
    # bucket of its own, so it's keyed onto department "Plant" by hand.
    plant_director = next((r for r in rows if (r.get("job_title") or "").strip().lower() == "plant director"), None)
    dept_head_override = {}
    if plant_director:
        plant_director["supervisor_id"] = root["user_id"]
        dept_head_override["Plant"] = plant_director

    others = [r for r in rows if r is not root and r is not plant_director]

    def group_key(r):
        return (r.get("department") or "", r.get("division") or "", r.get("team") or "")

    groups: dict = {}
    for r in others:
        groups.setdefault(group_key(r), []).append(r)

    def leader_of(key):
        members = groups.get(key)
        return min(members, key=rank) if members else None

    for key, members in groups.items():
        dept, div, team = key
        leader = leader_of(key)
        for r in members:
            if r is not leader:
                r["supervisor_id"] = leader["user_id"]

        if team:
            parent_key = (dept, div, "")
        elif div:
            parent_key = (dept, "", "")
        else:
            parent_key = None  # this bucket already IS the department-head bucket

        if parent_key is None:
            leader["supervisor_id"] = root["user_id"]
        else:
            parent_leader = leader_of(parent_key) or dept_head_override.get(dept)
            leader["supervisor_id"] = (parent_leader or root)["user_id"]


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
        raise HTTPException(status_code=400, detail="File must be .xls, .xlsx, or .xlsm format")

    contents = await file.read()
    batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        data_rows = _extract_rows(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

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
        raise HTTPException(status_code=422, detail=f"Failed to read data rows: {e}")

    if not rows_parsed:
        raise HTTPException(status_code=422, detail="No employee data found in file. "
                            "Make sure the sheet is named 'Employee Data' with headers in the first row.")

    _assign_supervisors(rows_parsed)

    try:
        # REPLACE — delete all previous data, replace with the new file's data
        deleted_result = await db.execute(delete(Employee))
        replaced_count = deleted_result.rowcount or 0

        db.add_all(Employee(**data) for data in rows_parsed)
        await db.flush()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to save data to database: {e}")

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
        "message":           f"Upload successful: {len(rows_parsed)} employee records replaced {replaced_count} previous records.",
    }


# ── Query endpoints ────────────────────────────────────────────────────────────

@router.get("/birthdays-this-month")
async def get_birthdays_this_month(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(get_current_user),
):
    """Active employees whose birthday falls in the current month — powers the
    Application Center's Announcement panel. Open to any authenticated user
    (not just HR), unlike the rest of this router."""
    today = date.today()
    q = await db.execute(
        select(Employee.full_name, Employee.department, Employee.job_title, Employee.date_of_birth)
        .where(
            Employee.date_of_birth.isnot(None),
            extract("month", Employee.date_of_birth) == today.month,
            or_(Employee.resign_date.is_(None), Employee.resign_date > today),
        )
        .order_by(extract("day", Employee.date_of_birth))
    )
    return [
        {
            "name":       r[0],
            "department": r[1],
            "job_title":  r[2],
            "day":        r[3].day,
            "date":       r[3].isoformat(),
            "is_today":   r[3].month == today.month and r[3].day == today.day,
        }
        for r in q.fetchall()
    ]


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
        "supervisor_id":    e.supervisor_id,
        "education_degree": e.education_degree,
        "education_school": e.education_school,
        "education_major":  e.education_major,
        "marital_status":   e.marital_status,
        "religion":         e.religion,
        "blood_type":       e.blood_type,
        "phone_number":     e.phone_number,
        "emergency_phone":  e.emergency_phone,
        "company_email":    e.company_email,
        "personal_email":   e.personal_email,
        "date_of_joining":  str(e.date_of_joining)  if e.date_of_joining  else None,
        "date_of_birth":    str(e.date_of_birth)    if e.date_of_birth    else None,
        "place_of_birth":   e.place_of_birth,
        "retire_date":      str(e.retire_date)       if e.retire_date      else None,
        "end_pkwt":         str(e.end_pkwt)          if e.end_pkwt         else None,
        "starting_pkwt":    str(e.starting_pkwt)     if e.starting_pkwt    else None,
        "pkwt_ke":          e.pkwt_ke,
        "permanent_date":   str(e.permanent_date)    if e.permanent_date   else None,
        "resign_date":      str(e.resign_date)        if e.resign_date      else None,
        "no_bpjs_health":   e.no_bpjs_health,
        "no_bpjs_employee": e.no_bpjs_employee,
        "working_experience_years": e.working_experience_years,
        "previous_company": e.previous_company,
        "address":          e.address,
        "npwp_number":      e.npwp_number,
        "bank_account_bca": e.bank_account_bca,
        "bank_account_name": e.bank_account_name,
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
    page_size:  int           = Query(25, ge=1, le=5000),  # higher cap lets the frontend fetch everything in one call for Excel export
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

    return {
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "pages":      (total + page_size - 1) // page_size,
        "employees":  [_emp_dict(e) for e in employees],
    }


@router.get("/monthly-summary")
async def get_monthly_summary(
    month: Optional[int] = Query(None, ge=1, le=12),
    year:  Optional[int] = Query(None),
    db:    AsyncSession = Depends(get_db),
    user:  CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Monthly headcount trend + demographic breakdowns.

    month/year are optional — when given, the KPI/breakdown numbers reflect
    the active-employee roster as of the end of that period (same
    join/resign-date windowing used by /turnover-summary and
    /target-vs-achievement) instead of today's live roster. Attributes like
    department/status/marital status are still each employee's *current*
    value (the Employee table isn't historized), only *which* employees are
    counted is period-aware."""
    import traceback
    from datetime import date
    from calendar import monthrange
    from sqlalchemy import and_, cast, String, literal_column

    MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    try:
        # Monthly joinings map — cast date to text for grouping.
        # group_by references the SELECT alias ("month") rather than repeating
        # the to_char(...) expression: with a bound literal format string,
        # Postgres sees the SELECT and GROUP BY occurrences as two distinct
        # parameters ($1/$2) and can't prove they're equal, raising GroupingError.
        joins_q = await db.execute(
            select(
                func.to_char(Employee.date_of_joining, "YYYY-MM").label("month"),
                func.count().label("cnt"),
            )
            .where(Employee.date_of_joining.isnot(None))
            .group_by(literal_column("month"))
        )
        joins_map = {r[0]: r[1] for r in joins_q.fetchall()}
    except Exception as e:
        raise HTTPException(500, f"joins_q error: {e}\n{traceback.format_exc()}")

    try:
        # All join/resign pairs for cumulative headcount
        emps_q = await db.execute(
            select(Employee.user_id, Employee.date_of_joining, Employee.resign_date)
            .where(Employee.date_of_joining.isnot(None))
        )
        emps_full = [(r[0], r[1], r[2]) for r in emps_q.fetchall()]
        emps = [(join, resign) for _uid, join, resign in emps_full]
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

    # Period filter — when month/year is given, breakdowns/KPIs reflect the
    # active roster as of the end of that period instead of today's roster.
    # Attribute values (department, status, ...) are still each employee's
    # *current* value; only which employees get counted is period-aware.
    active_ids = None
    if year:
        snapshot_date = date(year, month or 12, monthrange(year, month or 12)[1])
        active_ids = {
            uid for uid, join, resign in emps_full
            if join <= snapshot_date and (resign is None or resign >= snapshot_date)
        }
    else:
        snapshot_date = today

    # Generic breakdown helper — explicit AND to avoid any dialect issues
    async def _bd(col):
        try:
            conditions = [col.isnot(None), col != ""]
            if active_ids is not None:
                conditions.append(Employee.user_id.in_(active_ids))
            q = await db.execute(
                select(col, func.count().label("total"))
                .where(and_(*conditions))
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
        sex_q = select(Employee.sex, func.count().label("t"))
        if active_ids is not None:
            sex_q = sex_q.where(Employee.user_id.in_(active_ids))
        sex_q = sex_q.group_by(Employee.sex)
        sex_result = await db.execute(sex_q)
        sex_map = {r[0]: r[1] for r in sex_result.fetchall()}
    except Exception:
        sex_map = {}

    by_gender = [
        {"name": "Male",   "total": sex_map.get("M", 0)},
        {"name": "Female", "total": sex_map.get("F", 0)},
    ]

    period_total = len(active_ids) if active_ids is not None else headcount_trend[-1]["count"]
    if year and month:
        period_joins = joins_map.get(f"{year}-{month:02d}", 0)
    elif year:
        period_joins = sum(v for k, v in joins_map.items() if k.startswith(f"{year}-"))
    else:
        period_joins = None
    period_label = (
        f"{MN[month-1]} {year}" if year and month else
        f"Year {year}" if year else
        "Current"
    )

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
        "period": {
            "year":  year,
            "month": month,
            "label": period_label,
            "snapshot_date": str(snapshot_date),
            "total_employees": period_total,
            "joins_in_month":  period_joins,
        },
    }


@router.get("/turnover-summary")
async def get_turnover_summary(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Laporan turnover: tren resign bulanan, turnover rate, breakdown per departemen/level."""
    from datetime import date
    from calendar import monthrange

    MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    emps_q = await db.execute(
        select(Employee.date_of_joining, Employee.resign_date, Employee.department,
               Employee.level, Employee.status)
        .where(Employee.date_of_joining.isnot(None))
    )
    emps = emps_q.fetchall()

    today = date.today()

    def _month_back(base_year, base_month, n):
        m = base_month - n
        y = base_year
        while m <= 0:
            m += 12
            y -= 1
        return y, m

    # Tren resign + turnover rate bulanan — 24 bulan terakhir
    resign_trend = []
    for i in range(23, -1, -1):
        y, m = _month_back(today.year, today.month, i)
        last_day  = date(y, m, monthrange(y, m)[1])
        first_day = date(y, m, 1)
        resigns_in_month = sum(
            1 for join, resign, *_ in emps
            if resign is not None and first_day <= resign <= last_day
        )
        headcount_start = sum(
            1 for join, resign, *_ in emps
            if join < first_day and (resign is None or resign >= first_day)
        )
        headcount_end = sum(
            1 for join, resign, *_ in emps
            if join <= last_day and (resign is None or resign >= first_day)
        )
        avg_headcount = (headcount_start + headcount_end) / 2 if (headcount_start + headcount_end) > 0 else 0
        rate = round((resigns_in_month / avg_headcount) * 100, 2) if avg_headcount > 0 else 0
        resign_trend.append({
            "month":          f"{y}-{m:02d}",
            "label":          f"{MN[m-1]} '{str(y)[2:]}",
            "resigns":        resigns_in_month,
            "avg_headcount":  round(avg_headcount, 1),
            "turnover_rate":  rate,
        })

    # Turnover rate rolling 12 bulan terakhir
    last_12 = resign_trend[-12:]
    total_resigns_12m = sum(r["resigns"] for r in last_12)
    avg_headcount_12m = sum(r["avg_headcount"] for r in last_12) / len(last_12) if last_12 else 0
    annual_turnover_rate = round((total_resigns_12m / avg_headcount_12m) * 100, 2) if avg_headcount_12m > 0 else 0

    # Breakdown karyawan resign 12 bulan terakhir — per departemen / level / status
    cutoff = date(today.year - 1, today.month, 1)
    resigned_recent = [
        row for row in emps
        if row[1] is not None and row[1] >= cutoff
    ]

    def _bd(idx):
        counts = {}
        for row in resigned_recent:
            key = row[idx] or "—"
            counts[key] = counts.get(key, 0) + 1
        return sorted(
            [{"name": k, "total": v} for k, v in counts.items()],
            key=lambda x: x["total"], reverse=True,
        )

    by_dept   = _bd(2)
    by_level  = _bd(3)
    by_status = _bd(4)

    # Rata-rata masa kerja karyawan yang resign
    tenures = [
        (row[1] - row[0]).days / 365.25
        for row in resigned_recent
        if row[0] and row[1]
    ]
    avg_tenure_years = round(sum(tenures) / len(tenures), 1) if tenures else 0

    current_headcount = sum(1 for join, resign, *_ in emps if resign is None)

    return {
        "resign_trend":         resign_trend,
        "annual_turnover_rate": annual_turnover_rate,
        "total_resigns_12m":    total_resigns_12m,
        "avg_headcount_12m":    round(avg_headcount_12m, 1),
        "avg_tenure_years":     avg_tenure_years,
        "current_headcount":    current_headcount,
        "by_dept":              by_dept,
        "by_level":             by_level,
        "by_status":            by_status,
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


@router.get("/names")
async def get_employee_names(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Lightweight active-employee list for LOV/multi-select fields (e.g. To Do List Assigned To)."""
    result = await db.execute(
        select(Employee.user_id, Employee.full_name, Employee.department)
        .where(Employee.full_name.isnot(None), Employee.resign_date.is_(None))
        .order_by(Employee.full_name)
    )
    return [{"user_id": r[0], "full_name": r[1], "department": r[2]} for r in result.fetchall()]


class SupervisorUpdate(BaseModel):
    supervisor_id: Optional[str] = None


@router.patch("/{user_id}/supervisor")
async def set_employee_supervisor(
    user_id: str,
    body: SupervisorUpdate,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Manual override for one employee's direct supervisor (used by the Organization
    Chart tab). Gets overwritten the next time the master data is re-uploaded, since
    upload REPLACEs the whole table and re-derives supervisor_id from scratch."""
    target = await db.scalar(select(Employee).where(Employee.user_id == user_id))
    if not target:
        raise HTTPException(status_code=404, detail=f"Employee {user_id} not found")

    new_sup_id = body.supervisor_id or None
    if new_sup_id:
        if new_sup_id == user_id:
            raise HTTPException(status_code=400, detail="An employee cannot be their own supervisor")
        supervisor = await db.scalar(select(Employee).where(Employee.user_id == new_sup_id))
        if not supervisor:
            raise HTTPException(status_code=404, detail=f"Supervisor {new_sup_id} not found")

        # Walk the chain upward from the proposed supervisor — if it reaches
        # user_id again, this assignment would create a reporting-line loop.
        cursor = supervisor.supervisor_id
        seen = {user_id}
        hops = 0
        while cursor and hops < 200:
            if cursor in seen:
                raise HTTPException(status_code=400, detail="This assignment would create a reporting-line loop")
            seen.add(cursor)
            cursor = await db.scalar(select(Employee.supervisor_id).where(Employee.user_id == cursor))
            hops += 1

    target.supervisor_id = new_sup_id
    await db.flush()
    return {"user_id": user_id, "supervisor_id": new_sup_id}


@router.get("/org-chart")
async def get_org_chart(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Full company hierarchy, nested by supervisor_id, for the Organization Chart tab.
    Always returns a single root node — employees with no resolvable supervisor chain
    (shouldn't normally happen) are bucketed under a synthetic 'Unassigned' node
    instead of becoming extra floating roots."""
    result = await db.execute(
        select(
            Employee.user_id, Employee.full_name, Employee.job_title, Employee.level,
            Employee.department, Employee.division, Employee.team, Employee.sex,
            Employee.supervisor_id,
        ).where(Employee.resign_date.is_(None)).order_by(Employee.full_name)
    )
    rows = [dict(r._mapping) for r in result.fetchall()]
    if not rows:
        return {"total": 0, "root": None}

    by_id = {r["user_id"]: {**r, "children": []} for r in rows}
    roots = []
    for r in rows:
        node = by_id[r["user_id"]]
        sup_id = r["supervisor_id"]
        if sup_id and sup_id in by_id and sup_id != r["user_id"]:
            by_id[sup_id]["children"].append(node)
        else:
            roots.append(node)

    def subtree_size(node):
        return 1 + sum(subtree_size(c) for c in node["children"])

    def finalize(node):
        node["children"].sort(key=lambda c: (-subtree_size(c), c["full_name"] or ""))
        node["direct_count"] = len(node["children"])
        for c in node["children"]:
            finalize(c)

    main_root = next((n for n in roots if (n["job_title"] or "").strip().lower() == "president director"), None)
    if main_root is None:
        roots.sort(key=lambda n: -len(n["children"]))
        main_root = roots[0] if roots else None

    orphans = [n for n in roots if n is not main_root]
    if main_root and orphans:
        main_root["children"].append({
            "user_id": "__unassigned__", "full_name": "Unassigned", "job_title": "No supervisor set",
            "level": None, "department": None, "division": None, "team": None, "sex": None,
            "supervisor_id": main_root["user_id"], "children": orphans,
        })

    if main_root:
        finalize(main_root)

    return {"total": len(rows), "root": main_root}


# NOTE: declared last — a path-param route shadows any static route registered
# after it (FastAPI matches in declaration order), so this must stay below
# /departments, /teams, /names, /org-chart, and /{user_id}/supervisor.
@router.get("/{user_id}")
async def get_employee(
    user_id: str,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Single employee's full record — used by the Organization Chart tab when a node is clicked."""
    emp = await db.scalar(select(Employee).where(Employee.user_id == user_id))
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {user_id} not found")
    return _emp_dict(emp)
