"""
ZKTeco Plant attendance poller — pulls the FULL user roster + attendance log
from every enabled Plant terminal (see app/models/zkteco.py — up to 8
physical machines confirmed live 2026-08-28: Lobby, Loker Male, Loker
Female, Server IT, Female Lab, Male Lab, Mall, Office) every 15 minutes,
merges every device's events per employee/day, and upserts into
AttendanceRecord — same master table, same leave-safe UPSERT-by-
(employee_id, attendance_date) pattern, and the same scheduled_checkin-
based lateness scoring as hikcentral_scheduler.py (see that module's
docstring for the full leave-safety reasoning; kept as a parallel,
separately-maintained implementation here rather than a shared helper, to
avoid touching the already-working Hikvision path for an unrelated
device family).

── Why no separate backfill/pagination (unlike hikcentral_scheduler.py) ──
Hikvision's ISAPI caps each page at 30 events and needed day-by-day
pagination (plus retry/backoff for an occasional device lockout under
heavy request volume). ZKTeco's get_attendance() has no such limit — it
returns the device's ENTIRE stored log in a single call (confirmed live:
1091 records, one request, no server-side date filter available). So
there's nothing to paginate and no separate "historical backfill" mode:
run_sync() below always reprocesses every date present in the fetched
log, every time it runs — the same call serves both the 15-minute poll
AND a de-facto backfill of the device's whole history. Acceptable at
Plant headcount scale for the foreseeable future; revisit (e.g. only
reprocess the last N days on the routine poll) if a device's log grows
large enough to make full reprocessing slow.

── Employee ID mapping (device numeric ID -> Employee.user_id) ──
A ZKTeco device's own user_id is a plain numeric string (e.g. "24005"),
not this app's Employee.user_id, which carries a department-letter prefix
(e.g. "P24005" — confirmed live: device id "24005" on the Office terminal
= Employee "P24005", Rislah Juana Dewi, department Plant). Resolved via a
numeric-suffix lookup built from the Employee table each sync
(_build_employee_id_map()) — a device ID that doesn't resolve to exactly
one Employee is skipped and reported back in the sync result rather than
guessed at or written under its bare numeric form (which would silently
create a duplicate/orphaned AttendanceRecord employee_id no other report
recognizes).
"""
import logging
import re
from collections import defaultdict
from datetime import datetime, date

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from app.database import SessionLocal
from app.models.attendance import AttendanceRecord, AttendanceUploadLog
from app.models.zkteco import ZKTecoSessionLocal, ZKTecoDevice
from app.services.zkteco_client import ZKTecoClient, ZKTecoError
from app.services.hikcentral_scheduler import (
    DEFAULT_SCHEDULED_CHECKIN, _parse_hhmm, _shift_hhmm, WEEKDAY_NAMES, _STANDARD_SHIFT_HOURS,
)

logger = logging.getLogger("zkteco.scheduler")

_scheduler: BackgroundScheduler | None = None


def _get_devices(enabled_only: bool = True) -> list[dict]:
    db = ZKTecoSessionLocal()
    try:
        q = select(ZKTecoDevice)
        if enabled_only:
            q = q.where(ZKTecoDevice.enabled.is_(True))
        rows = db.execute(q.order_by(ZKTecoDevice.name)).scalars().all()
        return [{"id": r.id, "name": r.name, "ip": r.ip, "port": r.port, "password": r.password} for r in rows]
    finally:
        db.close()


def is_configured() -> bool:
    return len(_get_devices()) > 0


def _build_employee_id_map(db) -> dict[str, str]:
    """{numeric NIK suffix -> full Employee.user_id}, e.g. "24005" ->
    "P24005". A collision (two employees sharing the same numeric suffix
    under different department prefixes) keeps whichever was seen first
    and logs a warning — rare given this company's NIK scheme (join year
    + sequence number), not silently guessed at either way."""
    from app.models.employee import Employee
    mapping: dict[str, str] = {}
    for (uid,) in db.execute(select(Employee.user_id)).fetchall():
        if not uid:
            continue
        numeric = re.sub(r"^\D+", "", uid)
        if not numeric:
            continue
        if numeric in mapping and mapping[numeric] != uid:
            logger.warning("ZKTeco id map collision: numeric suffix %s matches both %s and %s — keeping %s",
                            numeric, mapping[numeric], uid, mapping[numeric])
            continue
        mapping[numeric] = uid
    return mapping


def _fetch_all_devices(devices: list[dict]) -> tuple[list[tuple[str, datetime]], dict, list[str]]:
    """Polls every device, merging results. Returns (events:
    [(device_user_id, timestamp), ...], name_by_device_id: {device_user_id:
    name} merged across devices, errors: ["<device name>: <error>", ...])
    — one device failing doesn't stop the others from being polled."""
    events: list[tuple[str, datetime]] = []
    names: dict[str, str] = {}
    errors: list[str] = []
    for dev in devices:
        client = ZKTecoClient(dev["ip"], port=dev["port"], password=dev["password"])
        try:
            dev_names, dev_atts = client.fetch()
        except ZKTecoError as e:
            errors.append(f"{dev['name']}: {e}")
            continue
        names.update({k: v for k, v in dev_names.items() if v})
        events.extend(dev_atts)
    return events, names, errors


def run_sync(uploaded_by: str = "scheduler") -> dict:
    """Fetches every enabled device's full log, merges per (employee,
    date) ACROSS all devices (someone can swipe in at Lobby and out at
    Male Lab — both count toward the same day's record), and upserts
    AttendanceRecord the same leave-safe way hikcentral_scheduler.py
    does. Raises ZKTecoError only if every configured device failed; a
    partial failure (some devices unreachable, others fine) is instead
    reported in the result's "device_errors" list so one broken terminal
    doesn't block the other 7."""
    devices = _get_devices()
    if not devices:
        raise ZKTecoError("No ZKTeco devices configured — add one in IT Dashboard > ZKTeco Integration.")

    events, names, errors = _fetch_all_devices(devices)
    if not events and errors and len(errors) == len(devices):
        raise ZKTecoError("; ".join(errors))

    db = SessionLocal()
    try:
        emp_id_map = _build_employee_id_map(db)

        grouped: dict[tuple[str, date], list[datetime]] = defaultdict(list)
        resolved_names: dict[str, str] = {}
        unmapped_ids: set[str] = set()
        for device_id, ts in events:
            emp_id = emp_id_map.get(device_id)
            if not emp_id:
                unmapped_ids.add(device_id)
                continue
            grouped[(emp_id, ts.date())].append(ts)
            if names.get(device_id):
                resolved_names[emp_id] = names[device_id]

        if unmapped_ids:
            logger.warning("ZKTeco sync: %d device user_id(s) had no matching Employee: %s",
                            len(unmapped_ids), sorted(unmapped_ids))

        from app.models.employee import Employee
        emp_map = {
            r[0]: (r[1], r[2], r[3])
            for r in db.execute(select(Employee.user_id, Employee.department, Employee.team, Employee.scheduled_checkin)).fetchall()
        }

        dates = {d for (_, d) in grouped}
        existing_rows = {
            (r.employee_id, r.attendance_date): r
            for r in db.execute(select(AttendanceRecord).where(AttendanceRecord.attendance_date.in_(dates))).scalars().all()
        } if dates else {}

        batch_id = f"zk_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        inserted = updated = 0
        for (emp_id, d), timestamps in grouped.items():
            timestamps.sort()
            checkin, checkout = timestamps[0], timestamps[-1]
            checkin_str = checkin.strftime("%H:%M")
            checkout_str = checkout.strftime("%H:%M") if checkout != checkin else None
            dept, team, sched_checkin_raw = emp_map.get(emp_id, (None, None, None))
            sched_checkin = sched_checkin_raw or DEFAULT_SCHEDULED_CHECKIN
            sched_checkout = _shift_hhmm(sched_checkin, _STANDARD_SHIFT_HOURS)
            is_late = checkin.time() > _parse_hhmm(sched_checkin)
            existing = existing_rows.get((emp_id, d))

            if existing is None:
                db.add(AttendanceRecord(
                    employee_id=emp_id, employee_name=resolved_names.get(emp_id),
                    department=dept, team=team,
                    attendance_date=d, week_day=WEEKDAY_NAMES[d.weekday()],
                    scheduled_checkin=sched_checkin, scheduled_checkout=sched_checkout,
                    actual_checkin=checkin_str, actual_checkout=checkout_str,
                    attendance_status="L" if is_late else "W", notes=None, is_day_off=False, leave_code=None,
                    source="zkteco", upload_batch_id=batch_id,
                ))
                inserted += 1
                continue

            values = {
                "actual_checkin":  checkin_str,
                "actual_checkout": checkout_str,
                "upload_batch_id": batch_id,
            }
            if not existing.employee_name and resolved_names.get(emp_id):
                values["employee_name"] = resolved_names[emp_id]
            if not existing.department and dept:
                values["department"] = dept
            if not existing.team and team:
                values["team"] = team
            if not (existing.leave_code or existing.is_day_off):
                # No leave/rest-day already recorded — Plant terminal
                # presence is authoritative for this day.
                values["scheduled_checkin"] = sched_checkin
                values["scheduled_checkout"] = sched_checkout
                values["attendance_status"] = "L" if is_late else "W"
                values["source"] = "zkteco"
            db.execute(
                update(AttendanceRecord)
                .where(AttendanceRecord.employee_id == emp_id)
                .where(AttendanceRecord.attendance_date == d)
                .values(**values)
            )
            updated += 1

        if grouped:
            db.add(AttendanceUploadLog(
                batch_id=batch_id, source="zkteco", filename="(ZKTeco Plant sync)",
                total_rows=len({e for e, _ in grouped}), inserted=inserted, updated=updated, skipped=len(unmapped_ids),
                uploaded_by=uploaded_by,
                notes=f"{len(events)} raw events from {len(devices)} device(s)" + (f"; {len(errors)} device error(s)" if errors else ""),
            ))
        db.commit()
        logger.info("ZKTeco sync: %d events -> %d inserted, %d updated, %d unmapped id(s), %d device error(s)",
                     len(events), inserted, updated, len(unmapped_ids), len(errors))
        return {
            "events": len(events), "employees": len({e for e, _ in grouped}),
            "inserted": inserted, "updated": updated,
            "unmapped_ids": sorted(unmapped_ids), "device_errors": errors,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_last_sync() -> dict | None:
    db = SessionLocal()
    try:
        row = (
            db.execute(
                select(AttendanceUploadLog)
                .where(AttendanceUploadLog.source == "zkteco")
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


def _tick():
    if not is_configured():
        return  # no devices added yet — silently idle rather than log-spam every 15 minutes
    try:
        run_sync(uploaded_by="scheduler")
    except ZKTecoError:
        logger.exception("ZKTeco poll failed")
    except Exception:
        logger.exception("ZKTeco poll tick failed")


def start():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", minutes=15, id="zkteco_attendance_poller",
                        next_run_time=datetime.utcnow(), max_instances=1)
    _scheduler.start()
    logger.info("ZKTeco attendance poller started (15min interval)")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
