"""
HikCentral attendance poller — pulls today's raw door (face-recognition
check-in) events from HikCentral every 15 minutes and upserts them into
AttendanceRecord, same table and same UPSERT-by-(employee_id, attendance_date)
pattern as the Plant/Intercom/Talenta/Office Excel uploads (see
hr_attendance.py's upload_attendance_plant for the reference implementation
this mirrors).

Design: each tick re-fetches ALL of today's events (midnight -> now) and
re-derives checkin (earliest event) / checkout (latest event) per person,
rather than tracking a "last synced" checkpoint. Simpler and self-healing —
a missed tick or a restart just gets caught up by the next tick, since
re-deriving from the full day's events is idempotent. The trade-off is
re-fetching the whole day every 15 minutes rather than only new events;
acceptable at office headcount scale (dozens-hundreds of events/day).

── NEEDS VERIFICATION once HikCentral AppKey/AppSecret exist ──
The exact JSON field names below (personId/jobNo/name/time) are Hikvision's
commonly-documented ACS event shape, but should be confirmed against a real
response from your HikCentral version before trusting this in production —
see hikcentral_client.py's module docstring for how to get one. In
particular: `_employee_id_from_event()` assumes the terminal was enrolled
with each person's company NIK in the "Job No" field — if your enrollment
used a different field (or HikCentral's internal personId happens to *be*
the NIK), adjust that one function; nothing else needs to change.
"""
import logging
from collections import defaultdict
from datetime import datetime, date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from app.database import SessionLocal
from app.config import get_settings
from app.models.attendance import AttendanceRecord, AttendanceUploadLog
from app.services.hikcentral_client import HikCentralClient, HikCentralError

logger = logging.getLogger("hikcentral.scheduler")

_scheduler: BackgroundScheduler | None = None

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _employee_id_from_event(evt: dict) -> str | None:
    """The company NIK for this event — see module docstring. Falls back
    through the field names Hikvision events commonly carry for a
    person's external ID, in likely-correctness order."""
    return evt.get("jobNo") or evt.get("personCode") or evt.get("cardNo") or evt.get("personId")


def _parse_event_time(evt: dict) -> datetime | None:
    raw = evt.get("time") or evt.get("eventTime")
    if not raw:
        return None
    try:
        # Hikvision timestamps are typically ISO-8601 with a timezone offset,
        # e.g. "2026-08-13T08:03:11+07:00".
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _fetch_today_events(client: HikCentralClient, today: date) -> list[dict]:
    tz_suffix = datetime.now().astimezone().strftime("%z")
    tz_suffix = f"{tz_suffix[:3]}:{tz_suffix[3:]}" if tz_suffix else "+07:00"
    start_time = f"{today.isoformat()}T00:00:00{tz_suffix}"
    end_time = datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}")

    events: list[dict] = []
    page_no = 1
    while True:
        result = client.search_door_events(start_time, end_time, page_no=page_no, page_size=1000)
        batch = result.get("list") or result.get("events") or []
        if not batch:
            break
        events.extend(batch)
        total = int(result.get("total", len(events)))
        if len(events) >= total or not batch:
            break
        page_no += 1
    return events


def _tick():
    settings = get_settings()
    if not (settings.hikcentral_base_url and settings.hikcentral_app_key and settings.hikcentral_app_secret):
        return  # not configured yet — silently idle rather than log-spam every 15 minutes

    db = SessionLocal()
    try:
        client = HikCentralClient()
        today = date.today()
        try:
            events = _fetch_today_events(client, today)
        except HikCentralError:
            logger.exception("HikCentral poll failed")
            return

        # Group by employee_id, keep earliest event as check-in and latest as check-out.
        by_employee: dict[str, list[datetime]] = defaultdict(list)
        names: dict[str, str] = {}
        for evt in events:
            emp_id = _employee_id_from_event(evt)
            ts = _parse_event_time(evt)
            if not emp_id or not ts:
                continue
            by_employee[str(emp_id)].append(ts)
            if evt.get("personName"):
                names[str(emp_id)] = evt["personName"]

        if not by_employee:
            return

        from app.models.employee import Employee
        emp_dept_map = {
            r[0]: (r[1], r[2])
            for r in db.execute(select(Employee.user_id, Employee.department, Employee.team)).fetchall()
        }

        batch_id = f"hik_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        existing_keys = {
            (r[0], r[1])
            for r in db.execute(
                select(AttendanceRecord.employee_id, AttendanceRecord.attendance_date)
                .where(AttendanceRecord.attendance_date == today)
            ).fetchall()
        }

        inserted = updated = 0
        for emp_id, timestamps in by_employee.items():
            timestamps.sort()
            checkin, checkout = timestamps[0], timestamps[-1]
            dept, team = emp_dept_map.get(emp_id, (None, None))
            data = {
                "employee_id":        emp_id,
                "employee_name":      names.get(emp_id),
                "department":         dept,
                "team":               team,
                "attendance_date":    today,
                "week_day":           WEEKDAY_NAMES[today.weekday()],
                "scheduled_checkin":  None,
                "scheduled_checkout": None,
                "actual_checkin":     checkin.strftime("%H:%M"),
                "actual_checkout":    checkout.strftime("%H:%M") if checkout != checkin else None,
                "attendance_status":  "W",
                "notes":              None,
                "is_day_off":         False,
                "leave_code":         None,
                "source":             "hikcentral",
                "upload_batch_id":    batch_id,
            }
            key = (emp_id, today)
            if key in existing_keys:
                db.execute(
                    update(AttendanceRecord)
                    .where(AttendanceRecord.employee_id == emp_id)
                    .where(AttendanceRecord.attendance_date == today)
                    .values(**data)
                )
                updated += 1
            else:
                db.add(AttendanceRecord(**data))
                existing_keys.add(key)
                inserted += 1

        db.add(AttendanceUploadLog(
            batch_id=batch_id, source="hikcentral", filename="(HikCentral OpenAPI poll)",
            total_rows=len(by_employee), inserted=inserted, updated=updated, skipped=0,
            uploaded_by="scheduler", notes=f"{len(events)} raw events for {today.isoformat()}",
        ))
        db.commit()
        logger.info("HikCentral poll: %d events -> %d inserted, %d updated", len(events), inserted, updated)
    except Exception:
        logger.exception("HikCentral poll tick failed")
        db.rollback()
    finally:
        db.close()


def start():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", minutes=15, id="hikcentral_attendance_poller",
                        next_run_time=datetime.utcnow(), max_instances=1)
    _scheduler.start()
    logger.info("HikCentral attendance poller started (15min interval)")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
