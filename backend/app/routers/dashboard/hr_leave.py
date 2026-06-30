"""
HR Leave Router
Route prefix: /api/v1/dashboard/hr/leave

Source: AttendanceLeave Excel (revised format)
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
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.leave import LeaveRecord, LeaveUploadLog

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
COL_SHIFT    = 3
COL_ATT_CODE = 6
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
            "employee_id": emp_id,
            "employee_name": _to_str(row[COL_NAME]),
            "organization": _to_str(row[COL_SHIFT]) if len(row) > COL_SHIFT else None,
            "job_position": None,
            "leave_date": leave_dt,
            "leave_code": timeoff_code,
            "leave_type": LEAVE_CODE_MAP.get(timeoff_code, timeoff_code),
            "upload_batch_id": batch_id,
            "uploaded_at": datetime.utcnow(),
        })

    wb.close()

    if not records:
        raise HTTPException(status_code=422, detail="No leave data found in file (column Time Off Code is empty)")

    inserted = 0
    updated = 0

    for rec in records:
        existing = await db.execute(
            select(LeaveRecord.id).where(
                LeaveRecord.employee_id == rec["employee_id"],
                LeaveRecord.leave_date == rec["leave_date"],
            )
        )
        if existing.scalar():
            await db.execute(
                text("""
                    UPDATE leave_records
                    SET employee_name = :employee_name, organization = :organization,
                        job_position = :job_position, leave_code = :leave_code,
                        leave_type = :leave_type, upload_batch_id = :upload_batch_id,
                        uploaded_at = :uploaded_at
                    WHERE employee_id = :employee_id AND leave_date = :leave_date
                """),
                rec,
            )
            updated += 1
        else:
            db.add(LeaveRecord(**rec))
            inserted += 1

    log = LeaveUploadLog(
        batch_id=batch_id,
        filename=file.filename,
        total_rows=len(records),
        inserted=inserted,
        updated=updated,
        uploaded_by=user.username,
        notes=notes,
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
    stmt = select(LeaveUploadLog).order_by(LeaveUploadLog.uploaded_at.desc()).limit(20)
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
    organization: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    conditions = []
    if month:
        conditions.append(func.extract("month", LeaveRecord.leave_date) == month)
    if year:
        conditions.append(func.extract("year", LeaveRecord.leave_date) == year)
    if leave_code:
        conditions.append(LeaveRecord.leave_code == leave_code)
    if organization:
        conditions.append(LeaveRecord.organization == organization)
    if search:
        pat = f"%{search}%"
        conditions.append(
            LeaveRecord.employee_name.ilike(pat) | LeaveRecord.employee_id.ilike(pat)
        )

    where = and_(*conditions) if conditions else True

    count_stmt = select(func.count()).select_from(LeaveRecord).where(where)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(LeaveRecord)
        .where(where)
        .order_by(LeaveRecord.leave_date.desc(), LeaveRecord.employee_name)
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
                "employee_id": r.employee_id,
                "employee_name": r.employee_name,
                "organization": r.organization,
                "job_position": r.job_position,
                "leave_date": r.leave_date.isoformat() if r.leave_date else None,
                "leave_code": r.leave_code,
                "leave_type": r.leave_type,
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
    conditions = []
    if year:
        conditions.append(func.extract("year", LeaveRecord.leave_date) == year)
    if month:
        conditions.append(func.extract("month", LeaveRecord.leave_date) == month)

    where = and_(*conditions) if conditions else True

    stmt = (
        select(LeaveRecord.leave_code, func.count().label("count"))
        .where(where)
        .group_by(LeaveRecord.leave_code)
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


@router.get("/organizations")
async def get_leave_organizations(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    stmt = (
        select(LeaveRecord.organization)
        .where(LeaveRecord.organization.isnot(None))
        .distinct()
        .order_by(LeaveRecord.organization)
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

    from sqlalchemy import extract
    al_count_result = await db.execute(
        select(func.count()).select_from(LeaveRecord).where(
            LeaveRecord.employee_id == employee_id,
            LeaveRecord.leave_code.in_(["AL", "ALAB"]),
            extract("year", LeaveRecord.leave_date) == yr,
        )
    )
    al_taken = al_count_result.scalar() or 0

    history_result = await db.execute(
        select(LeaveRecord)
        .where(LeaveRecord.employee_id == employee_id)
        .order_by(LeaveRecord.leave_date.desc())
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
            {"leave_date": h.leave_date.isoformat(), "leave_code": h.leave_code, "leave_type": h.leave_type}
            for h in history
        ],
    }
