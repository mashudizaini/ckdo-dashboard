"""
HR Leave Router
Route prefix: /api/v1/dashboard/hr/leave
Upload Talenta attendance Excel → extract leave records → PostgreSQL.

Source: Attendance Talenta Excel
  Col A: Employee ID
  Col B: Full Name
  Col D: Organization
  Col E: Job Position
  Col F: Date
  Col M: Time Off Code (SL, AL, EM, UL, ML, BT, ALAB, ULBB, etc.)
"""
import io
import traceback
from datetime import datetime, date
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import select, func, and_, text, delete
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
COL_ORG      = 3
COL_POSITION = 4
COL_DATE     = 5
COL_TIMEOFF  = 12


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
        if not row or len(row) < 13:
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
            "organization": _to_str(row[COL_ORG]),
            "job_position": _to_str(row[COL_POSITION]),
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
