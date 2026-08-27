"""
Hikvision ISAPI attendance poller — pulls today's raw access-control (face/
card authentication) events directly from the office's Hikvision terminal
every 15 minutes and upserts them into AttendanceRecord, same table and same
UPSERT-by-(employee_id, attendance_date) pattern as the Plant/Intercom/
Talenta/Office Excel uploads (see hr_attendance.py's upload_attendance_plant
for the reference implementation this mirrors). Also provides a one-time
historical backfill (see start_backfill()) to migrate the device's existing
event log — going back to 2026-01-05 on this device — into the same table,
so every dashboard tab (Summary, Attendance Detail, Coverage, Monthly Rate,
Attendance Leave, Annual Leave Report, ...) reads consistent history rather
than only picking up Hikvision data from whenever the poller was switched on.

Design: each tick re-fetches ALL of a day's events (midnight -> now for
today; midnight -> 23:59:59 for a backfilled past day) and re-derives
checkin (earliest event) / checkout (latest event) per person, rather than
tracking a "last synced" checkpoint. Simpler and self-healing — a missed
tick or a restart just gets caught up by the next tick, since re-deriving
from the full day's events is idempotent. The trade-off is re-fetching (and
re-paginating, 30 events/page — see hikcentral_client.py) the whole day
every 15 minutes rather than only new events; acceptable at office headcount
scale (dozens-hundreds of identity events/day, even though the device's raw
event log also contains hundreds more door-status/heartbeat entries per day
that carry no employee identity and get filtered out).

── Leave-safe upsert ──
hr_leave.py's Talenta-leave upload (and Plant/Office's is_day_off /
leave_code) is the authoritative source for a day being on-leave or a
rostered rest day — Hikvision only knows physical door swipes, it has no
concept of an approved leave. So when a day already carries a leave_code or
is_day_off=True, this sync does NOT touch attendance_status/leave_code/
is_day_off/scheduled_* — a stray swipe on a leave day (someone drops by the
office) only merges into actual_checkin/actual_checkout as supplementary
evidence, it never flips the day back to "Worked" or erases the leave
record. See _upsert_grouped() below; mirrors the same overlay convention
hr_leave.py's upload_leave() already uses.

── VERIFIED against the live device ──
Confirmed via GET .../AcsEvent/capabilities?format=json and a real
AcsEvent search: identity-carrying events use `employeeNoString` (matches
Employee.user_id / the roster's employeeNo, e.g. "A25002") and `name`;
`time` is ISO-8601 with a timezone offset. See hikcentral_client.py's module
docstring for the full picture, including which major/minor codes are noise.
"""
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from app.database import SessionLocal
from app.config import get_settings
from app.models.attendance import AttendanceRecord, AttendanceUploadLog
from app.models.hikcentral import HikCentralSessionLocal, resolve_effective_config
from app.services.hikcentral_client import HikCentralClient, HikCentralError

logger = logging.getLogger("hikcentral.scheduler")

_scheduler: BackgroundScheduler | None = None

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Earliest event available on the device as of 2026-08-27 (probed live via
# AcsEvent with a startTime of 2020-01-01 — the device returned its oldest
# stored event at 2026-01-05). Used only as the frontend's default backfill
# start date; the device is free to have rolled its log forward since.
EARLIEST_KNOWN_EVENT_DATE = date(2026, 1, 5)

_backfill_status: dict = {
    "running": False, "paused": False, "start_date": None, "end_date": None, "current_date": None,
    "done_days": 0, "total_days": 0,
    "totals": {"events": 0, "inserted": 0, "updated": 0},
    "errors": [], "finished_at": None,
}
_backfill_lock = threading.Lock()
# Set = keep going, clear = pause. The loop blocks on this between days (not
# mid-day — a day's own pagination always finishes first), so "Pause" takes
# effect once the day in progress is done.
_backfill_resume_event = threading.Event()
_backfill_resume_event.set()


def _employee_id_from_event(evt: dict) -> str | None:
    """The company NIK for this event — ISAPI AcsEvent identity events carry
    it as employeeNoString (confirmed live, matches Employee.user_id / the
    roster's employeeNo, e.g. "A25002")."""
    return evt.get("employeeNoString") or evt.get("employeeNo")


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


def _tz_suffix() -> str:
    tz = datetime.now().astimezone().strftime("%z")
    return f"{tz[:3]}:{tz[3:]}" if tz else "+07:00"


def _fetch_events_range(client: HikCentralClient, start_time: str, end_time: str) -> list[dict]:
    """Paginates the full [start_time, end_time) window (ISO-8601 with tz
    offset) and returns only identity-carrying events — door-status/
    heartbeat noise (no employeeNoString) is dropped here."""
    events: list[dict] = []
    position = 0
    while True:
        result = client.search_door_events(start_time, end_time, search_position=position, max_results=30)
        batch = result.get("list") or []
        events.extend(e for e in batch if e.get("employeeNoString") or e.get("employeeNo"))
        position += len(batch)
        total = result.get("totalMatches", position)
        if not batch or result.get("responseStatusStrg") != "MORE" or position >= total:
            break
        # Small pacing between paginated calls — a multi-month backfill can
        # mean thousands of sequential requests, and firing them back to
        # back occasionally trips this device's own login-rate lockout
        # (see hikcentral_client.py's module docstring).
        time.sleep(0.1)
    return events


def _group_events(events: list[dict]) -> tuple[dict[tuple[str, date], list[datetime]], dict[str, str]]:
    """Groups identity events by (employee_id, calendar_date) — a range
    spanning multiple days (backfill) is split per-day here, not just
    per-employee, so each day still gets its own checkin/checkout."""
    grouped: dict[tuple[str, date], list[datetime]] = defaultdict(list)
    names: dict[str, str] = {}
    for evt in events:
        emp_id = _employee_id_from_event(evt)
        ts = _parse_event_time(evt)
        if not emp_id or not ts:
            continue
        emp_id = str(emp_id)
        grouped[(emp_id, ts.date())].append(ts)
        if evt.get("name"):
            names[emp_id] = evt["name"]
    return grouped, names


def _upsert_grouped(db, grouped: dict[tuple[str, date], list[datetime]], names: dict[str, str], batch_id: str) -> tuple[int, int, int]:
    """Leave-safe upsert — see module docstring. Returns
    (inserted, updated, distinct_employee_count)."""
    if not grouped:
        return 0, 0, 0

    from app.models.employee import Employee
    emp_dept_map = {
        r[0]: (r[1], r[2])
        for r in db.execute(select(Employee.user_id, Employee.department, Employee.team)).fetchall()
    }

    dates = {d for (_, d) in grouped}
    existing_rows = {
        (r.employee_id, r.attendance_date): r
        for r in db.execute(
            select(AttendanceRecord).where(AttendanceRecord.attendance_date.in_(dates))
        ).scalars().all()
    }

    inserted = updated = 0
    for (emp_id, d), timestamps in grouped.items():
        timestamps.sort()
        checkin, checkout = timestamps[0], timestamps[-1]
        checkin_str = checkin.strftime("%H:%M")
        checkout_str = checkout.strftime("%H:%M") if checkout != checkin else None
        dept, team = emp_dept_map.get(emp_id, (None, None))
        existing = existing_rows.get((emp_id, d))

        if existing is None:
            db.add(AttendanceRecord(
                employee_id=emp_id, employee_name=names.get(emp_id),
                department=dept, team=team,
                attendance_date=d, week_day=WEEKDAY_NAMES[d.weekday()],
                scheduled_checkin=None, scheduled_checkout=None,
                actual_checkin=checkin_str, actual_checkout=checkout_str,
                attendance_status="W", notes=None, is_day_off=False, leave_code=None,
                source="hikcentral", upload_batch_id=batch_id,
            ))
            inserted += 1
            continue

        values = {
            "actual_checkin":  checkin_str,
            "actual_checkout": checkout_str,
            "upload_batch_id": batch_id,
        }
        if not existing.employee_name and names.get(emp_id):
            values["employee_name"] = names[emp_id]
        if not existing.department and dept:
            values["department"] = dept
        if not existing.team and team:
            values["team"] = team
        if not (existing.leave_code or existing.is_day_off):
            # No leave/rest-day already recorded — Hikvision's physical
            # presence is authoritative for this day.
            values["attendance_status"] = "W"
            values["source"] = "hikcentral"
        db.execute(
            update(AttendanceRecord)
            .where(AttendanceRecord.employee_id == emp_id)
            .where(AttendanceRecord.attendance_date == d)
            .values(**values)
        )
        updated += 1

    return inserted, updated, len({e for e, _ in grouped})


def _get_effective_config() -> dict:
    """Config editable from the IT dashboard's HikCentral tab (hikcentral_config
    table) overrides the .env defaults — resolved fresh on every call so a
    UI-saved change takes effect on the very next tick, no restart needed."""
    cfg_db = HikCentralSessionLocal()
    try:
        return resolve_effective_config(cfg_db)
    finally:
        cfg_db.close()


def is_configured() -> bool:
    cfg = _get_effective_config()
    return bool(cfg["base_url"] and cfg["app_key"] and cfg["app_secret"])


def _build_client() -> HikCentralClient:
    cfg = _get_effective_config()
    if not (cfg["base_url"] and cfg["app_key"] and cfg["app_secret"]):
        raise HikCentralError("Hikvision device not configured — set it in IT Dashboard > HikCentral Integration, or hikcentral_base_url / hikcentral_app_key / hikcentral_app_secret (.env)")
    return HikCentralClient(base_url=cfg["base_url"], username=cfg["app_key"], password=cfg["app_secret"])


def _sync_one_day(client: HikCentralClient, target_date: date, uploaded_by: str) -> dict:
    """Fetches and upserts a single day's events — the core unit both
    run_sync() (today) and the backfill loop (past days) call."""
    tz = _tz_suffix()
    start_time = f"{target_date.isoformat()}T00:00:00{tz}"
    end_time = (
        datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{tz}")
        if target_date >= date.today()
        else f"{target_date.isoformat()}T23:59:59{tz}"
    )
    events = _fetch_events_range(client, start_time, end_time)
    grouped, names = _group_events(events)

    db = SessionLocal()
    try:
        batch_id = f"hik_{target_date.strftime('%Y%m%d')}_{datetime.utcnow().strftime('%H%M%S')}"
        inserted, updated, employees = _upsert_grouped(db, grouped, names, batch_id)
        if employees:
            db.add(AttendanceUploadLog(
                batch_id=batch_id, source="hikcentral", filename="(Hikvision ISAPI sync)",
                total_rows=employees, inserted=inserted, updated=updated, skipped=0,
                uploaded_by=uploaded_by, notes=f"{len(events)} raw events for {target_date.isoformat()}",
            ))
        db.commit()
        return {"date": target_date.isoformat(), "events": len(events), "employees": employees, "inserted": inserted, "updated": updated}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_sync(uploaded_by: str = "scheduler") -> dict:
    """Core sync — fetches today's door events and upserts AttendanceRecord.
    Returns a result dict; raises HikCentralError if the API call itself
    fails (caller decides how to surface that — the scheduler tick logs and
    swallows it, the manual "Sync Now" endpoint lets it become a 502)."""
    client = _build_client()
    try:
        result = _sync_one_day(client, date.today(), uploaded_by)
    finally:
        client.close()
    logger.info("HikCentral sync: %d events -> %d inserted, %d updated", result["events"], result["inserted"], result["updated"])
    return result


def get_last_sync() -> dict | None:
    db = SessionLocal()
    try:
        row = (
            db.execute(
                select(AttendanceUploadLog)
                .where(AttendanceUploadLog.source == "hikcentral")
                .order_by(AttendanceUploadLog.uploaded_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if not row:
            return None
        return {
            "batch_id": row.batch_id, "total_rows": row.total_rows,
            "inserted": row.inserted, "updated": row.updated,
            "notes": row.notes, "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        }
    finally:
        db.close()


# ── Historical backfill ──────────────────────────────────────────────────
# Migrates the device's existing event log into AttendanceRecord, day by
# day, so history predating the 15-minute poller is also in sync across
# every dashboard tab. Runs in a background thread — a multi-month range
# means thousands of paginated device calls (30 events/page), far too slow
# for one HTTP request/response cycle. Each day still commits its own
# AttendanceUploadLog row via _sync_one_day(), so "Sync History" fills in
# incrementally and a restart never loses more than the in-progress day.

def get_backfill_status() -> dict:
    return dict(_backfill_status)


def _run_backfill_body(start_date: date, end_date: date, uploaded_by: str):
    global _backfill_status
    total_days = (end_date - start_date).days + 1
    _backfill_resume_event.set()
    _backfill_status.update(
        running=True, paused=False, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
        current_date=None, done_days=0, total_days=total_days,
        totals={"events": 0, "inserted": 0, "updated": 0}, errors=[], finished_at=None,
    )
    try:
        client = _build_client()
    except HikCentralError as e:
        _backfill_status["errors"].append(str(e))
        _backfill_status["running"] = False
        _backfill_status["finished_at"] = datetime.utcnow().isoformat()
        return

    try:
        d = start_date
        while d <= end_date:
            _backfill_resume_event.wait()  # blocks here while paused
            _backfill_status["current_date"] = d.isoformat()
            try:
                try:
                    result = _sync_one_day(client, d, uploaded_by)
                except HikCentralError:
                    # One retry with a longer pause — covers a device
                    # lockout that outlasts _post_json()'s own backoff.
                    time.sleep(10)
                    result = _sync_one_day(client, d, uploaded_by)
                _backfill_status["totals"]["events"] += result["events"]
                _backfill_status["totals"]["inserted"] += result["inserted"]
                _backfill_status["totals"]["updated"] += result["updated"]
            except Exception as e:
                logger.exception("HikCentral backfill failed for %s", d)
                _backfill_status["errors"].append(f"{d.isoformat()}: {e}")
            _backfill_status["done_days"] += 1
            d += timedelta(days=1)
    finally:
        client.close()

    _backfill_status["running"] = False
    _backfill_status["paused"] = False
    _backfill_status["current_date"] = None
    _backfill_status["finished_at"] = datetime.utcnow().isoformat()
    logger.info("HikCentral backfill done: %s..%s (%d day(s)) -> %s", start_date, end_date, total_days, _backfill_status["totals"])


def pause_backfill() -> dict:
    if not _backfill_status.get("running"):
        raise HikCentralError("No backfill is currently running.")
    _backfill_resume_event.clear()
    _backfill_status["paused"] = True
    return get_backfill_status()


def resume_backfill() -> dict:
    if not _backfill_status.get("running"):
        raise HikCentralError("No backfill is currently running.")
    _backfill_status["paused"] = False
    _backfill_resume_event.set()
    return get_backfill_status()


def start_backfill(start_date: date, end_date: date | None = None, uploaded_by: str = "manual") -> dict:
    """Kicks off the background backfill thread. Raises HikCentralError if
    one is already running or the range is invalid — caller (the IT
    dashboard endpoint) turns that into a 4xx."""
    end_date = end_date or date.today()
    if start_date > end_date:
        raise HikCentralError("start_date must not be after end_date.")
    with _backfill_lock:
        if _backfill_status.get("running"):
            raise HikCentralError("A backfill is already running — check its progress before starting another.")
        _backfill_status["running"] = True  # claim the slot before the thread starts
    t = threading.Thread(target=_run_backfill_body, args=(start_date, end_date, uploaded_by), daemon=True)
    t.start()
    return {"status": "started", "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "total_days": (end_date - start_date).days + 1}


def _tick():
    if not is_configured():
        return  # not configured yet — silently idle rather than log-spam every 15 minutes
    try:
        run_sync(uploaded_by="scheduler")
    except HikCentralError:
        logger.exception("HikCentral poll failed")
    except Exception:
        logger.exception("HikCentral poll tick failed")


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
