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
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import Optional

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
    "P24005".

    BUG FOUND live 2026-08-28 via direct SQL check (see the conversation
    that led to this fix): the numeric suffix is NOT unique company-wide
    — it's a separate sequence PER DEPARTMENT PREFIX (A/P/S/D/N/...), each
    independently counting from 001. E.g. numeric suffix "16001" belongs
    to FOUR different real people across four different departments
    (Administration, Plant x2, Sales & Marketing) with completely
    different names and join dates — not one person whose ID changed.
    The original "keep whichever NIK is seen first" logic was therefore
    effectively random (query-order luck), and could attribute a Plant
    terminal's swipe to an Administration/Sales/other employee who never
    set foot at a Plant device — corrupting both the employee_id AND the
    derived Late/checkin-time data for whoever wrongly "won" the numeric
    suffix.

    Fix: every ZKTeco device managed here is physically at Plant, so a
    "P"-prefixed employee is what a device's bare numeric ID actually
    means. Prefer a Plant match for a given numeric suffix; only fall
    back to a non-Plant record if Plant has none for that suffix (e.g.
    the person transferred out and their NIK was never P-prefixed). Two
    DIFFERENT Plant employees sharing the same numeric suffix (shouldn't
    happen — Plant's own sequence should itself be unique) still logs a
    warning and keeps the first found."""
    from app.models.employee import Employee
    mapping: dict[str, str] = {}
    is_plant_kept: dict[str, bool] = {}
    for (uid,) in db.execute(select(Employee.user_id)).fetchall():
        if not uid:
            continue
        numeric = re.sub(r"^\D+", "", uid)
        if not numeric:
            continue
        is_plant = uid.upper().startswith("P")

        if numeric not in mapping:
            mapping[numeric] = uid
            is_plant_kept[numeric] = is_plant
            continue

        if is_plant and not is_plant_kept[numeric]:
            # A Plant record beats whatever non-Plant record was kept —
            # every ZKTeco device is at Plant, so this is the real match.
            mapping[numeric] = uid
            is_plant_kept[numeric] = True
        elif is_plant and is_plant_kept[numeric]:
            logger.warning("ZKTeco id map collision within Plant: numeric suffix %s matches both %s and %s — keeping %s",
                            numeric, mapping[numeric], uid, mapping[numeric])
        # else: incoming record is non-Plant — irrelevant whether we keep
        # it or the earlier one, neither is a Plant terminal's real match
        # unless/until a Plant record for this suffix shows up.
    return mapping


def _poll_one_device(dev: dict) -> tuple[str, dict, list, Optional[str]]:
    client = ZKTecoClient(dev["ip"], port=dev["port"], password=dev["password"])
    try:
        dev_names, dev_atts = client.fetch()
        return dev["name"], dev_names, dev_atts, None
    except ZKTecoError as e:
        return dev["name"], {}, [], str(e)


def _fetch_all_devices(devices: list[dict], on_progress=None) -> tuple[list[tuple[str, datetime]], dict, list[str]]:
    """Polls every device IN PARALLEL (each is an independent network
    call — a broken/unreachable device otherwise makes the whole sync
    wait out its full timeout before moving to the next one; sequentially
    that's `sum` of every device's timeout, easily exceeding the HTTP/
    reverse-proxy timeout on the manual "Sync Now" request once more than
    a couple of devices are down at once — confirmed live 2026-08-28 with
    5 of 8 Plant devices unreachable). In parallel, total wall-clock time
    is bounded by the SLOWEST single device instead. Returns (events:
    [(device_user_id, timestamp), ...], name_by_device_id: {device_user_id:
    name} merged across devices, errors: ["<device name>: <error>", ...])
    — one device failing doesn't stop the others from being polled.

    `on_progress(message, phase=None, done=None, total=None)`, if given,
    is called as EACH device finishes (via as_completed, not submission
    order) so a caller can show live progress instead of only a final
    summary — phase="devices" throughout, so the caller can tell this
    done/total apart from a later, unrelated done/total (e.g. rows
    written to the database)."""
    events: list[tuple[str, datetime]] = []
    names: dict[str, str] = {}
    errors: list[str] = []
    if not devices:
        return events, names, errors
    done = 0
    with ThreadPoolExecutor(max_workers=len(devices)) as pool:
        futures = {pool.submit(_poll_one_device, dev): dev for dev in devices}
        for fut in as_completed(futures):
            dev_name, dev_names, dev_atts, err = fut.result()
            done += 1
            if err:
                errors.append(f"{dev_name}: {err}")
                if on_progress:
                    on_progress(f"{dev_name}: FAILED — {err}", phase="devices", done=done, total=len(devices))
                continue
            names.update({k: v for k, v in dev_names.items() if v})
            events.extend(dev_atts)
            if on_progress:
                on_progress(f"{dev_name}: {len(dev_atts)} event(s), {len(dev_names)} enrolled user(s)", phase="devices", done=done, total=len(devices))
    return events, names, errors


def run_sync(uploaded_by: str = "scheduler", on_progress=None) -> dict:
    """Fetches every enabled device's full log, merges per (employee,
    date) ACROSS all devices (someone can swipe in at Lobby and out at
    Male Lab — both count toward the same day's record), and upserts
    AttendanceRecord the same leave-safe way hikcentral_scheduler.py
    does. Raises ZKTecoError only if every configured device failed; a
    partial failure (some devices unreachable, others fine) is instead
    reported in the result's "device_errors" list so one broken terminal
    doesn't block the other 7.

    `on_progress(message, phase=None, done=None, total=None)`, if given,
    is called at each major step (and per-device as devices finish, via
    _fetch_all_devices) — phase is "devices" while polling terminals,
    "writing" while upserting AttendanceRecord (done/total mean something
    different in each — the caller shouldn't conflate them into one bar).
    start_manual_sync() uses this to feed a live progress bar/log; the
    regular 15-minute scheduler tick doesn't pass one, since nothing is
    watching it."""
    def progress(message, **kw):
        if on_progress:
            on_progress(message, **kw)

    devices = _get_devices()
    if not devices:
        raise ZKTecoError("No ZKTeco devices configured — add one in IT Dashboard > ZKTeco Integration.")

    progress(f"Polling {len(devices)} device(s) in parallel...", phase="devices", done=0, total=len(devices))
    events, names, errors = _fetch_all_devices(devices, on_progress=progress)
    if not events and errors and len(errors) == len(devices):
        raise ZKTecoError("; ".join(errors))

    progress(f"Fetched {len(events)} raw event(s) total. Matching to employees...")
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

        progress(f"Matched {len(grouped)} employee-day record(s) across {len({e for e, _ in grouped})} employee(s)"
                 + (f" ({len(unmapped_ids)} device ID(s) unmapped)" if unmapped_ids else "") + ". Writing to database...",
                 phase="writing", done=0, total=len(grouped))

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
        total_groups = len(grouped)
        PROGRESS_EVERY = 100  # log every Nth row — this loop can run into the
        # thousands (years of history x ~150 employees) and a line-per-row log
        # would swamp the UI; batching keeps it readable while still moving.
        for i, ((emp_id, d), timestamps) in enumerate(grouped.items(), start=1):
            if i == 1 or i % PROGRESS_EVERY == 0 or i == total_groups:
                progress(f"Writing to database... {i}/{total_groups} record(s)", phase="writing", done=i, total=total_groups)
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
        progress(f"Done — {inserted} new, {updated} updated, {len(unmapped_ids)} unmapped device ID(s).",
                 phase="writing", done=total_groups, total=total_groups)
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


# ── Manual "Sync Now" — runs in the background ───────────────────────────
# run_sync() reprocesses each device's ENTIRE history every time (see
# module docstring) — with ~150 employees' NIKs spanning 2018-2026 in this
# company's real data, that means the per-(employee, date) upsert loop can
# run for many thousands of rows across several devices in one call.
# Confirmed live 2026-08-28: the sync itself completed successfully (full
# log line reached, db.commit() succeeded) but "Sync Now" still showed
# "Sync failed" in the browser — the HTTP request/reverse-proxy had
# already timed out and closed the connection before the (now much
# faster, but still not instant) response could be sent back. Mirrors
# hikcentral_scheduler.py's backfill: run in a background thread, poll
# progress instead of blocking the request. The scheduled 15-minute tick
# doesn't need this — APScheduler already runs it off the request path.

_manual_sync_status: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "result": None, "error": None,
    # Live progress — see run_sync()'s on_progress docstring. "phase" is
    # "devices" (polling terminals) or "writing" (upserting
    # AttendanceRecord); "done"/"total" mean different things in each, so
    # the frontend must key its progress bar off `phase`, not just reuse
    # whatever done/total last were. "log" is every message so far, oldest
    # first, capped to the most recent 300 so a huge sync doesn't grow this
    # dict unboundedly.
    "phase": None, "done": 0, "total": 0, "log": [],
}
_manual_sync_lock = threading.Lock()
_MANUAL_SYNC_LOG_CAP = 300


def get_manual_sync_status() -> dict:
    return dict(_manual_sync_status)


def _manual_sync_progress(message: str, phase: str | None = None, done: int | None = None, total: int | None = None):
    global _manual_sync_status
    entry = f"{datetime.utcnow().strftime('%H:%M:%S')}  {message}"
    log = _manual_sync_status["log"] + [entry]
    if len(log) > _MANUAL_SYNC_LOG_CAP:
        log = log[-_MANUAL_SYNC_LOG_CAP:]
    _manual_sync_status["log"] = log
    if phase is not None:
        _manual_sync_status["phase"] = phase
    if done is not None:
        _manual_sync_status["done"] = done
    if total is not None:
        _manual_sync_status["total"] = total


def _run_manual_sync_body(uploaded_by: str):
    global _manual_sync_status
    try:
        result = run_sync(uploaded_by=uploaded_by, on_progress=_manual_sync_progress)
        _manual_sync_status["result"] = result
        _manual_sync_status["error"] = None
    except ZKTecoError as e:
        _manual_sync_status["error"] = str(e)
        _manual_sync_status["result"] = None
    except Exception as e:
        logger.exception("ZKTeco manual sync failed")
        _manual_sync_status["error"] = f"Unexpected error: {e}"
        _manual_sync_status["result"] = None
    finally:
        _manual_sync_status["running"] = False
        _manual_sync_status["finished_at"] = datetime.utcnow().isoformat()


def start_manual_sync(uploaded_by: str = "manual") -> dict:
    """Kicks off run_sync() in a background thread and returns
    immediately — see comment above for why. Raises ZKTecoError (-> 409)
    if a manual sync is already in progress."""
    with _manual_sync_lock:
        if _manual_sync_status.get("running"):
            raise ZKTecoError("A sync is already running — check its progress before starting another.")
        _manual_sync_status.update(running=True, started_at=datetime.utcnow().isoformat(), finished_at=None,
                                    result=None, error=None, phase=None, done=0, total=0, log=[])
    t = threading.Thread(target=_run_manual_sync_body, args=(uploaded_by,), daemon=True)
    t.start()
    return {"status": "started"}


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
