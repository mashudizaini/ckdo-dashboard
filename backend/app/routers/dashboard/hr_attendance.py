"""
HR Attendance Router
Route prefix : /api/v1/dashboard/hr/attendance
Upload file Excel absensi → UPSERT ke PostgreSQL.

Format file: Attendance HO.xlsx
  Header : baris 1
  Data   : mulai baris 2
  Kolom  : Name | ID | Department | Date | Week | Time Period |
           Check-In Time | Check-Out Time |
           Actual Check-In Time | Actual Check-Out Time | Notes
"""
import io
from datetime import datetime, date
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import select, update, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.attendance import AttendanceRecord, AttendanceUploadLog

router = APIRouter()

# ── Mapping kolom Excel (0-based) ─────────────────────────────────────────────
COL_NAME       = 0
COL_ID         = 1
COL_DEPT       = 2
COL_DATE       = 3
COL_WEEK       = 4
COL_PERIOD     = 5
COL_SCHED_IN   = 6
COL_SCHED_OUT  = 7
COL_ACTUAL_IN  = 8
COL_ACTUAL_OUT = 9
COL_NOTES      = 10


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
    # Coba parse string "YYYY-MM-DD"
    s = str(val).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_row(row: tuple, batch_id: str) -> Optional[dict]:
    """Ubah satu baris Excel → dict. Return None jika baris kosong / tanpa ID."""
    if len(row) <= COL_ID:
        return None
    employee_id = _to_str(row[COL_ID])
    if not employee_id:
        return None

    att_date = _to_date(row[COL_DATE]) if len(row) > COL_DATE else None
    if att_date is None:
        return None

    return {
        "employee_id":       employee_id,
        "employee_name":     _to_str(row[COL_NAME])      if len(row) > COL_NAME      else None,
        "department":        _to_str(row[COL_DEPT])      if len(row) > COL_DEPT      else None,
        "attendance_date":   att_date,
        "week_day":          _to_str(row[COL_WEEK])      if len(row) > COL_WEEK      else None,
        "time_period":       _to_str(row[COL_PERIOD])    if len(row) > COL_PERIOD    else None,
        "scheduled_checkin": _to_str(row[COL_SCHED_IN])  if len(row) > COL_SCHED_IN  else None,
        "scheduled_checkout":_to_str(row[COL_SCHED_OUT]) if len(row) > COL_SCHED_OUT else None,
        "actual_checkin":    _to_str(row[COL_ACTUAL_IN]) if len(row) > COL_ACTUAL_IN else None,
        "actual_checkout":   _to_str(row[COL_ACTUAL_OUT])if len(row) > COL_ACTUAL_OUT else None,
        "notes":             _to_str(row[COL_NOTES])     if len(row) > COL_NOTES     else None,
        "upload_batch_id":   batch_id,
        "uploaded_at":       datetime.utcnow(),
    }


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_attendance(
    file:  UploadFile    = File(...),
    notes: str           = Form(""),
    db:    AsyncSession  = Depends(get_db),
    user:  CurrentUser   = Depends(require_role(Roles.HR)),
):
    """
    Upload file Excel absensi (format Attendance HO.xlsx).
    Header di baris 1, data mulai baris 2.
    UPSERT berdasarkan employee_id + attendance_date.
    """
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="File harus berformat .xlsx atau .xlsm")

    contents = await file.read()
    batch_id = f"att_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File Excel tidak valid: {e}")

    ws = wb.active

    rows_parsed = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        parsed = _parse_row(row, batch_id)
        if parsed is None:
            continue
        rows_parsed.append(parsed)

    if not rows_parsed:
        raise HTTPException(
            status_code=422,
            detail="Tidak ada data absensi ditemukan. "
                   "Pastikan format file sesuai template (header baris 1, data mulai baris 2).",
        )

    # Kumpulkan key (employee_id, date) yang sudah ada di DB
    keys_result = await db.execute(
        select(AttendanceRecord.employee_id, AttendanceRecord.attendance_date)
    )
    existing_keys = {(r[0], r[1]) for r in keys_result.fetchall()}

    inserted = 0
    updated  = 0
    skipped  = 0

    for data in rows_parsed:
        key = (data["employee_id"], data["attendance_date"])
        if key in existing_keys:
            await db.execute(
                update(AttendanceRecord)
                .where(AttendanceRecord.employee_id == key[0])
                .where(AttendanceRecord.attendance_date == key[1])
                .values(**{k: v for k, v in data.items()})
            )
            updated += 1
        else:
            db.add(AttendanceRecord(**data))
            inserted += 1

    await db.flush()

    log = AttendanceUploadLog(
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
        "message":    f"Upload berhasil: {inserted} record baru, {updated} diperbarui.",
    }


# ── Upload logs ────────────────────────────────────────────────────────────────

@router.get("/upload-logs")
async def get_upload_logs(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(
        select(AttendanceUploadLog)
        .order_by(AttendanceUploadLog.uploaded_at.desc())
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


# ── List attendance records ────────────────────────────────────────────────────

@router.get("")
async def list_attendance(
    employee_id: Optional[str] = Query(None),
    department:  Optional[str] = Query(None),
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(50, ge=1, le=200),
    db:          AsyncSession  = Depends(get_db),
    user:        CurrentUser   = Depends(require_role(Roles.HR)),
):
    q = select(AttendanceRecord)

    if employee_id:
        q = q.where(AttendanceRecord.employee_id == employee_id)
    if department:
        q = q.where(AttendanceRecord.department == department)
    if date_from:
        try:
            q = q.where(AttendanceRecord.attendance_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_to:
        try:
            q = q.where(AttendanceRecord.attendance_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass

    count_q = await db.execute(select(func.count()).select_from(q.subquery()))
    total   = count_q.scalar() or 0

    q       = q.order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.employee_name)
    q       = q.offset((page - 1) * page_size).limit(page_size)
    result  = await db.execute(q)
    records = result.scalars().all()

    def _rec(r: AttendanceRecord) -> dict:
        return {
            "id":                r.id,
            "employee_id":       r.employee_id,
            "employee_name":     r.employee_name,
            "department":        r.department,
            "attendance_date":   str(r.attendance_date) if r.attendance_date else None,
            "week_day":          r.week_day,
            "time_period":       r.time_period,
            "scheduled_checkin": r.scheduled_checkin,
            "scheduled_checkout":r.scheduled_checkout,
            "actual_checkin":    r.actual_checkin,
            "actual_checkout":   r.actual_checkout,
            "notes":             r.notes,
        }

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "records":   [_rec(r) for r in records],
    }


# ── Kehadiran hari ini (per department) ───────────────────────────────────────

WEEKENDS = ["Saturday", "Sunday"]

@router.get("/today")
async def get_today_attendance(
    target_date: Optional[str] = Query(None),
    db:          AsyncSession  = Depends(get_db),
    user:        CurrentUser   = Depends(require_role(Roles.HR)),
):
    """
    Kehadiran untuk tanggal tertentu (default: hari ini), dikelompokkan per department.
    Jika tidak ada data untuk hari ini, otomatis tampilkan tanggal terakhir yang ada.
    """
    today = date.today()

    if target_date:
        try:
            q_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            q_date = today
    else:
        q_date = today

    # Cek apakah ada data untuk tanggal tersebut
    count_q = await db.execute(
        select(func.count()).select_from(AttendanceRecord)
        .where(AttendanceRecord.attendance_date == q_date)
    )
    count = count_q.scalar() or 0

    actual_date = q_date
    if count == 0:
        latest_q = await db.execute(
            select(func.max(AttendanceRecord.attendance_date))
        )
        latest = latest_q.scalar()
        if not latest:
            return {"requested_date": str(q_date), "actual_date": str(q_date),
                    "is_today": False, "has_data": False, "summary": {}, "data": []}
        actual_date = latest

    # Hitung kehadiran per department (hari kerja saja)
    result = await db.execute(
        select(
            AttendanceRecord.department,
            func.count().label("total"),
            func.sum(case(
                (AttendanceRecord.actual_checkin.isnot(None), 1), else_=0
            )).label("hadir"),
        )
        .where(AttendanceRecord.attendance_date == actual_date)
        .where(AttendanceRecord.week_day.notin_(WEEKENDS))
        .group_by(AttendanceRecord.department)
        .order_by(AttendanceRecord.department)
    )
    rows = result.fetchall()

    data = [
        {
            "department": r[0] or "—",
            "total":  int(r[1]),
            "hadir":  int(r[2] or 0),
            "absen":  int(r[1]) - int(r[2] or 0),
            "rate":   round(int(r[2] or 0) / int(r[1]) * 100, 1) if r[1] > 0 else 0,
        }
        for r in rows
    ]

    total_all   = sum(d["total"]  for d in data)
    total_hadir = sum(d["hadir"]  for d in data)
    total_absen = sum(d["absen"]  for d in data)

    return {
        "requested_date": str(q_date),
        "actual_date":    str(actual_date),
        "is_today":       actual_date == today,
        "has_data":       True,
        "summary": {
            "total":          total_all,
            "hadir":          total_hadir,
            "absen":          total_absen,
            "attendance_rate": round(total_hadir / total_all * 100, 1) if total_all > 0 else 0,
        },
        "data": data,
    }


# ── Monthly attendance rate ────────────────────────────────────────────────────

@router.get("/monthly-rate")
async def get_monthly_attendance_rate(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Attendance rate per bulan (12 bulan terakhir)."""
    from sqlalchemy import extract

    result = await db.execute(
        select(
            extract("year",  AttendanceRecord.attendance_date).label("year"),
            extract("month", AttendanceRecord.attendance_date).label("month"),
            func.sum(case(
                (AttendanceRecord.week_day.notin_(WEEKENDS), 1), else_=0
            )).label("working"),
            func.sum(case(
                (and_(
                    AttendanceRecord.actual_checkin.isnot(None),
                    AttendanceRecord.week_day.notin_(WEEKENDS),
                ), 1), else_=0
            )).label("hadir"),
        )
        .group_by(
            extract("year",  AttendanceRecord.attendance_date),
            extract("month", AttendanceRecord.attendance_date),
        )
        .order_by(
            extract("year",  AttendanceRecord.attendance_date).desc(),
            extract("month", AttendanceRecord.attendance_date).desc(),
        )
        .limit(12)
    )
    rows = result.fetchall()

    MONTHS = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]
    data = []
    for r in rows:
        year    = int(r[0])
        month   = int(r[1])
        working = int(r[2] or 0)
        hadir   = int(r[3] or 0)
        absen   = working - hadir
        rate    = round(hadir / working * 100, 1) if working > 0 else 0
        data.append({
            "period":   f"{MONTHS[month-1]} {year}",
            "year":     year,
            "month":    month,
            "working":  working,
            "hadir":    hadir,
            "absen":    absen,
            "rate":     rate,
        })
    return data
