"""
HR Leave Router
Route prefix: /api/v1/dashboard/hr/leave

Source: Talenta "revised format" Excel (8 columns) — same leave codes as the
Attendance Talenta upload (hr_attendance.py), just a different column
layout/export. Upserts `leave_code` directly onto `AttendanceRecord`
(source="talenta-leave") — the same master table every other
attendance/leave report reads from. There is no separate leave table; see
hr_attendance.py's module docstring for the full picture.
  Col 0: Employee ID
  Col 1: Full Name
  Col 2: Date
  Col 3: Shift
  Col 4: Schedule Check In
  Col 5: Schedule Check Out
  Col 6: Attendance Code
  Col 7: Time Off Code
"""
import io
from datetime import datetime, date
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import select, update, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.attendance import AttendanceRecord, AttendanceUploadLog

router = APIRouter()

LEAVE_CODE_MAP = {
    "SL":   "Sick Leave",
    "AL":   "Annual Leave",
    "ALAB": "Annual Leave",
    "EM":   "Employee Marriage",
    "UL":   "Unpaid Leave",
    "ULBB": "Unpaid Leave",
    "ML":   "Maternity Leave",
    "BT":   "Business Trip",
}

COL_EMP_ID   = 0
COL_NAME     = 1
COL_DATE     = 2
COL_TIMEOFF  = 7


def _to_str(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "-", "None") else s


def _to_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val).strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@router.post("/upload")
async def upload_leave(
    file: UploadFile = File(...),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="File must be .xlsx or .xlsm format")

    contents = await file.read()
    batch_id = datetime.utcnow().strftime("LV%Y%m%d%H%M%S")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    ws = wb.active

    records = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 8:
            continue
        timeoff_code = _to_str(row[COL_TIMEOFF])
        if not timeoff_code:
            continue
        emp_id = _to_str(row[COL_EMP_ID])
        leave_dt = _to_date(row[COL_DATE])
        if not emp_id or not leave_dt:
            continue
        records.append({
            "employee_id":     emp_id,
            "employee_name":   _to_str(row[COL_NAME]),
            "attendance_date": leave_dt,
            "leave_code":      timeoff_code,
        })

    wb.close()

    if not records:
        raise HTTPException(status_code=422, detail="No leave data found in file (column Time Off Code is empty)")

    from app.models.employee import Employee
    emp_dept_q = await db.execute(select(Employee.user_id, Employee.department))
    emp_dept_map = {r[0]: r[1] for r in emp_dept_q.fetchall() if r[1]}

    ar_keys_result = await db.execute(select(AttendanceRecord.employee_id, AttendanceRecord.attendance_date))
    existing_keys = {(r[0], r[1]) for r in ar_keys_result.fetchall()}

    now = datetime.utcnow()
    inserted = updated = 0
    for rec in records:
        key = (rec["employee_id"], rec["attendance_date"])
        if key in existing_keys:
            await db.execute(
                update(AttendanceRecord)
                .where(AttendanceRecord.employee_id == key[0])
                .where(AttendanceRecord.attendance_date == key[1])
                .values(leave_code=rec["leave_code"], source="talenta-leave",
                        upload_batch_id=batch_id, uploaded_at=now)
            )
            updated += 1
        else:
            db.add(AttendanceRecord(
                employee_id=rec["employee_id"], employee_name=rec["employee_name"],
                department=emp_dept_map.get(rec["employee_id"]),
                attendance_date=rec["attendance_date"], week_day=rec["attendance_date"].strftime("%A"),
                leave_code=rec["leave_code"], source="talenta-leave",
                upload_batch_id=batch_id, uploaded_at=now,
            ))
            existing_keys.add(key)
            inserted += 1

    log = AttendanceUploadLog(
        batch_id=batch_id, source="talenta-leave", filename=file.filename,
        total_rows=len(records), inserted=inserted, updated=updated, skipped=0,
        uploaded_by=user.username, notes=notes or None,
    )
    db.add(log)

    return {
        "batch_id": batch_id,
        "filename": file.filename,
        "total_rows": len(records),
        "inserted": inserted,
        "updated": updated,
    }


@router.get("/history")
async def get_upload_history(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    stmt = (
        select(AttendanceUploadLog)
        .where(AttendanceUploadLog.source == "talenta-leave")
        .order_by(AttendanceUploadLog.uploaded_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "batch_id": l.batch_id,
            "filename": l.filename,
            "total_rows": l.total_rows,
            "inserted": l.inserted,
            "updated": l.updated,
            "uploaded_by": l.uploaded_by,
            "uploaded_at": l.uploaded_at.isoformat() if l.uploaded_at else None,
            "notes": l.notes,
        }
        for l in logs
    ]


@router.get("/data")
async def get_leave_data(
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    leave_code: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    conditions = [AttendanceRecord.leave_code.isnot(None)]
    if month:
        conditions.append(extract("month", AttendanceRecord.attendance_date) == month)
    if year:
        conditions.append(extract("year", AttendanceRecord.attendance_date) == year)
    if leave_code:
        conditions.append(AttendanceRecord.leave_code == leave_code)
    if department:
        conditions.append(AttendanceRecord.department == department)
    if search:
        pat = f"%{search}%"
        conditions.append(
            AttendanceRecord.employee_name.ilike(pat) | AttendanceRecord.employee_id.ilike(pat)
        )

    where = and_(*conditions)

    count_stmt = select(func.count()).select_from(AttendanceRecord).where(where)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AttendanceRecord)
        .where(where)
        .order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.employee_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
        "data": [
            {
                "employee_id":   r.employee_id,
                "employee_name": r.employee_name,
                "department":    r.department,
                "leave_date":    r.attendance_date.isoformat() if r.attendance_date else None,
                "leave_code":    r.leave_code,
                "leave_type":    LEAVE_CODE_MAP.get(r.leave_code, r.leave_code),
            }
            for r in rows
        ],
    }


@router.get("/summary")
async def get_leave_summary(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    conditions = [AttendanceRecord.leave_code.isnot(None)]
    if year:
        conditions.append(extract("year", AttendanceRecord.attendance_date) == year)
    if month:
        conditions.append(extract("month", AttendanceRecord.attendance_date) == month)

    where = and_(*conditions)

    stmt = (
        select(AttendanceRecord.leave_code, func.count().label("count"))
        .where(where)
        .group_by(AttendanceRecord.leave_code)
        .order_by(func.count().desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "total": sum(r.count for r in rows),
        "by_code": [
            {"code": r.leave_code, "label": LEAVE_CODE_MAP.get(r.leave_code, r.leave_code), "count": r.count}
            for r in rows
        ],
    }


@router.get("/departments")
async def get_leave_departments(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    stmt = (
        select(AttendanceRecord.department)
        .where(AttendanceRecord.leave_code.isnot(None))
        .where(AttendanceRecord.department.isnot(None))
        .distinct()
        .order_by(AttendanceRecord.department)
    )
    result = await db.execute(stmt)
    return [r[0] for r in result.all()]


ANNUAL_LEAVE_QUOTA = 12


@router.get("/employee/{employee_id}/detail")
async def get_employee_leave_detail(
    employee_id: str,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    from app.models.employee import Employee

    emp_result = await db.execute(select(Employee).where(Employee.user_id == employee_id))
    emp = emp_result.scalars().first()

    yr = year or datetime.utcnow().year

    al_count_result = await db.execute(
        select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.leave_code.in_(["AL", "ALAB"]),
            extract("year", AttendanceRecord.attendance_date) == yr,
        )
    )
    al_taken = al_count_result.scalar() or 0

    history_result = await db.execute(
        select(AttendanceRecord)
        .where(AttendanceRecord.employee_id == employee_id)
        .where(AttendanceRecord.leave_code.isnot(None))
        .order_by(AttendanceRecord.attendance_date.desc())
        .limit(20)
    )
    history = history_result.scalars().all()

    return {
        "employee": {
            "id": employee_id,
            "name": emp.full_name if emp else None,
            "job_title": emp.job_title if emp else None,
            "department": emp.department if emp else None,
            "date_of_joining": emp.date_of_joining.isoformat() if emp and emp.date_of_joining else None,
        },
        "annual_leave_amount": ANNUAL_LEAVE_QUOTA,
        "annual_leave_taken": al_taken,
        "annual_leave_remaining": max(ANNUAL_LEAVE_QUOTA - al_taken, 0),
        "year": yr,
        "history": [
            {
                "leave_date": h.attendance_date.isoformat(),
                "leave_code": h.leave_code,
                "leave_type": LEAVE_CODE_MAP.get(h.leave_code, h.leave_code),
            }
            for h in history
        ],
    }


@router.get("/annual-report")
async def get_annual_leave_report(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Per-employee leave matrix for one year — every leave/BT day, broken
    down by month, so HR can see total leave taken Jan-Dec at a glance (and
    who took none at all). Every code counts here (including BT/H), same
    scope as /summary and the Leave Distribution chart."""
    from app.models.employee import Employee

    yr = year or datetime.utcnow().year

    rows_result = await db.execute(
        select(
            AttendanceRecord.employee_id,
            extract("month", AttendanceRecord.attendance_date).label("month"),
            AttendanceRecord.leave_code,
            func.count().label("count"),
        )
        .where(AttendanceRecord.leave_code.isnot(None))
        .where(extract("year", AttendanceRecord.attendance_date) == yr)
        .group_by(AttendanceRecord.employee_id, extract("month", AttendanceRecord.attendance_date), AttendanceRecord.leave_code)
    )

    by_employee = {}
    for emp_id, month, code, count in rows_result.fetchall():
        month, count = int(month), int(count)
        bucket = by_employee.setdefault(emp_id, {})
        cell = bucket.setdefault(month, {"total": 0, "by_code": {}})
        cell["total"] += count
        cell["by_code"][code] = cell["by_code"].get(code, 0) + count

    # Base roster: active employees, plus anyone with leave data this year
    # who may have since resigned — so a mid-year resignation doesn't drop
    # their leave history for that year off the report.
    active_result = await db.execute(
        select(Employee.user_id, Employee.full_name, Employee.department)
        .where(Employee.employment_status == "Active")
    )
    roster = {r[0]: {"name": r[1], "department": r[2]} for r in active_result.fetchall()}

    missing_ids = set(by_employee.keys()) - set(roster.keys())
    if missing_ids:
        extra_result = await db.execute(
            select(Employee.user_id, Employee.full_name, Employee.department)
            .where(Employee.user_id.in_(missing_ids))
        )
        for r in extra_result.fetchall():
            roster[r[0]] = {"name": r[1], "department": r[2]}
        # Employees not found in the master at all (rare — e.g. an
        # employee_id typo'd into a manual entry) still get a row, using
        # whatever name AttendanceRecord itself carries.
        still_missing = missing_ids - set(roster.keys())
        if still_missing:
            name_result = await db.execute(
                select(AttendanceRecord.employee_id, AttendanceRecord.employee_name, AttendanceRecord.department)
                .where(AttendanceRecord.employee_id.in_(still_missing))
            )
            for emp_id, name, dept in name_result.fetchall():
                roster.setdefault(emp_id, {"name": name, "department": dept})

    employees = []
    for emp_id, info in roster.items():
        months_data = by_employee.get(emp_id, {})
        months = []
        year_total = 0
        for m in range(1, 13):
            cell = months_data.get(m, {"total": 0, "by_code": {}})
            months.append({"month": m, "total": cell["total"], "by_code": cell["by_code"]})
            year_total += cell["total"]
        employees.append({
            "employee_id": emp_id,
            "employee_name": info["name"],
            "department": info["department"],
            "months": months,
            "total": year_total,
        })

    employees.sort(key=lambda e: e["employee_name"] or "")

    return {"year": yr, "employees": employees}
