"""
Is now a good moment to back up, and what is the database actually doing?

The existing preflight answers "is there room and can we reach the targets".
It says nothing about load, which is the question an operator actually asks at
22:00: is anyone still working, is a long job mid-flight, will this hurt.

Every query here is read-only against V$ views and FND_CONCURRENT_REQUESTS.

On time, and why it gets its own section: the dashboard stores naive UTC while
the database server runs WIB (+7). The failed run on 2026-10-06 is recorded as
started 12:55 and its files are stamped 19:55 — the same moment written two
ways. Anyone scheduling "22:00" without being told which clock that is will be
seven hours wrong, so both clocks are returned together and always labelled.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from app.database import get_oracle_connection

logger = structlog.get_logger(__name__)

# Thresholds for the verdict. Deliberately generous: a full backup is an online
# operation, so the question is not "is the database idle" — it never is — but
# "is this quieter than normal, and is anything mid-flight that a backup would
# make worse".
_SESSIONS_GOOD = 10        # active user sessions at or below this: quiet
_SESSIONS_BUSY = 30        # above this: genuinely busy
_LONG_TXN_MINUTES = 30     # an open transaction older than this is worth listing
# ...but age alone is not a problem, and treating it as one trains the operator
# to ignore the verdict. EBS leaves transactions open for months that hold two
# undo blocks — on 2026-10-07 the oldest was 114 days with 16 KB. What actually
# costs a backup is undo VOLUME, so only transactions above this raise the
# level; the rest are reported as information.
_LONG_TXN_UNDO_MB = 50
_CONC_REQ_GOOD = 2         # EBS concurrent requests still running


def _scalar(cur, sql, default=None):
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else default
    except Exception:
        return default


def _rows(cur, sql, limit=10) -> list[dict]:
    try:
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()[:limit]]
    except Exception:
        return []


def collect(now_utc: Optional[datetime] = None) -> dict:
    """One read-only snapshot of everything that bears on backup timing."""
    now_utc = now_utc or datetime.now(timezone.utc)
    out: dict = {"collected_at_utc": now_utc.isoformat()}

    with get_oracle_connection() as conn:
        cur = conn.cursor()

        # ── Clocks ────────────────────────────────────────────────────────
        db_time = _scalar(cur, "SELECT TO_CHAR(SYSDATE,'YYYY-MM-DD HH24:MI:SS') FROM dual")
        db_tz = _scalar(cur, "SELECT TO_CHAR(SYSTIMESTAMP,'TZH:TZM') FROM dual")
        out["clock"] = {
            "db_server_time": db_time,
            "db_server_tz_offset": db_tz,
            "dashboard_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            # The dashboard stores naive UTC; schedules are entered in server
            # local time. Returning both stops "22:00" meaning two things.
            "note": "Jadwal diisi dalam waktu server database (WIB). Dashboard menyimpannya sebagai UTC.",
        }

        # ── Who is on the database ────────────────────────────────────────
        out["sessions"] = {
            "active_user": _scalar(cur, """
                SELECT COUNT(*) FROM v$session
                WHERE type='USER' AND status='ACTIVE'""", 0),
            "total_user": _scalar(cur, """
                SELECT COUNT(*) FROM v$session WHERE type='USER'""", 0),
            "by_program": _rows(cur, """
                SELECT NVL(program,'(unknown)') AS program, COUNT(*) AS sessions
                FROM v$session WHERE type='USER' AND status='ACTIVE'
                GROUP BY program ORDER BY COUNT(*) DESC FETCH FIRST 8 ROWS ONLY"""),
            "longest_active": _rows(cur, """
                SELECT s.sid, s.username, NVL(s.module,'-') AS module,
                       ROUND(s.last_call_et/60,1) AS running_minutes,
                       NVL(s.event,'-') AS event
                FROM v$session s
                WHERE s.type='USER' AND s.status='ACTIVE' AND s.username IS NOT NULL
                ORDER BY s.last_call_et DESC FETCH FIRST 5 ROWS ONLY"""),
        }

        # ── Open transactions: these pin undo and make a backup window worse
        out["long_transactions"] = _rows(cur, f"""
            SELECT s.sid, NVL(s.username,'(background)') AS username,
                   NVL(s.module,'-') AS module, s.status,
                   ROUND((SYSDATE - t.start_date)*24*60, 1) AS open_minutes,
                   ROUND(t.used_ublk * 8192 / 1024 / 1024, 1) AS undo_mb
            FROM v$transaction t JOIN v$session s ON s.saddr = t.ses_addr
            WHERE (SYSDATE - t.start_date)*24*60 >= {_LONG_TXN_MINUTES}
            ORDER BY t.used_ublk DESC FETCH FIRST 5 ROWS ONLY""")

        # ── EBS concurrent requests still running ─────────────────────────
        # The signal that matters most in an EBS shop: a backup during a long
        # concurrent program competes with it for the same I/O.
        out["concurrent_requests"] = {
            "running": _scalar(cur, """
                SELECT COUNT(*) FROM apps.fnd_concurrent_requests
                WHERE phase_code='R' AND status_code='R'""", None),
            "detail": _rows(cur, """
                SELECT r.request_id, p.user_concurrent_program_name AS program,
                       ROUND((SYSDATE - r.actual_start_date)*24*60, 1) AS running_minutes
                FROM apps.fnd_concurrent_requests r
                JOIN apps.fnd_concurrent_programs_tl p
                  ON p.concurrent_program_id = r.concurrent_program_id
                 AND p.language = USERENV('LANG')
                WHERE r.phase_code='R' AND r.status_code='R'
                ORDER BY r.actual_start_date FETCH FIRST 5 ROWS ONLY"""),
        }

        # ── Archive log area ──────────────────────────────────────────────
        out["archivelog"] = {
            "active_gb": _scalar(cur, """
                SELECT ROUND(SUM(blocks*block_size)/1024/1024/1024, 1)
                FROM v$archived_log WHERE deleted='NO'""", 0),
            "last_24h_gb": _scalar(cur, """
                SELECT ROUND(NVL(SUM(blocks*block_size),0)/1024/1024/1024, 1)
                FROM v$archived_log WHERE completion_time > SYSDATE - 1""", 0),
        }

        out["db_size_gb"] = _scalar(cur, """
            SELECT ROUND(SUM(bytes)/1024/1024/1024, 1) FROM dba_data_files""", None)

        # ── Is a backup already running? ──────────────────────────────────
        out["rman_running"] = _scalar(cur, """
            SELECT COUNT(*) FROM v$rman_status
            WHERE status='RUNNING' AND operation LIKE 'BACKUP%'""", 0)

    out["verdict"] = _verdict(out)
    return out


def _verdict(d: dict) -> dict:
    """Turn the numbers into one plain recommendation plus its reasons.

    A verdict with no reasons is just a coloured dot; every level below names
    exactly what produced it, so the operator can disagree with it knowingly.
    """
    reasons: list[str] = []
    level = "good"

    def worse(to: str):
        nonlocal level
        order = {"good": 0, "caution": 1, "avoid": 2}
        if order[to] > order[level]:
            level = to

    active = d["sessions"]["active_user"] or 0
    if active > _SESSIONS_BUSY:
        worse("avoid")
        reasons.append(f"{active} sesi user aktif — database sedang sibuk.")
    elif active > _SESSIONS_GOOD:
        worse("caution")
        reasons.append(f"{active} sesi user aktif — di atas kondisi tenang ({_SESSIONS_GOOD}).")
    else:
        reasons.append(f"{active} sesi user aktif — tenang.")

    txns = d.get("long_transactions") or []
    heavy = [t for t in txns if (t.get("undo_mb") or 0) >= _LONG_TXN_UNDO_MB]
    if heavy:
        worse("caution")
        biggest = max(t["undo_mb"] for t in heavy)
        reasons.append(
            f"{len(heavy)} transaksi terbuka menahan undo besar (terbesar {biggest} MB) — "
            "backup akan berjalan sementara undo itu tidak bisa didaur ulang."
        )
    elif txns:
        # Listed, not counted against the verdict: EBS always has a few of
        # these and they hold kilobytes.
        oldest = max(t.get("open_minutes") or 0 for t in txns)
        reasons.append(
            f"{len(txns)} transaksi terbuka lama (terlama {oldest/1440:.0f} hari) tapi "
            "undo-nya kecil — sesi EBS yang menganggur, bukan penghalang backup."
        )

    cr = (d.get("concurrent_requests") or {}).get("running")
    if cr is None:
        reasons.append("Jumlah concurrent request tidak terbaca — lewati penilaian ini.")
    elif cr > _CONC_REQ_GOOD:
        worse("caution")
        reasons.append(f"{cr} concurrent request EBS masih berjalan — berebut I/O dengan backup.")
    elif cr:
        reasons.append(f"{cr} concurrent request berjalan — masih wajar.")
    else:
        reasons.append("Tidak ada concurrent request EBS yang berjalan.")

    if d.get("rman_running"):
        worse("avoid")
        reasons.append("RMAN sudah menjalankan backup lain saat ini — jangan dijalankan bersamaan.")

    headline = {
        "good": "Waktu yang tepat untuk backup.",
        "caution": "Boleh dijalankan, tapi ada yang perlu Anda sadari.",
        "avoid": "Sebaiknya tunda — kondisinya tidak tepat sekarang.",
    }[level]
    return {"level": level, "headline": headline, "reasons": reasons}


# ── Live progress, from Oracle rather than from file sizes ───────────────
#
# The byte-based bar is structurally misleading: it compares the staging
# directory's COMPRESSED output against the UNCOMPRESSED datafile total, so a
# finished backup reads about 25%, and the code caps it at 99% so it never
# looks done either. RMAN publishes its own progress in v$session_longops, in
# the same units for both halves, which is the only number that can be trusted
# to reach 100.
def rman_progress() -> Optional[dict]:
    """Percent complete of the RMAN backup running now, or None if none is."""
    try:
        with get_oracle_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT NVL(SUM(sofar),0), NVL(SUM(totalwork),0),
                       ROUND(MAX(elapsed_seconds)/60, 1), COUNT(*)
                FROM v$session_longops
                WHERE opname LIKE 'RMAN%'
                  AND totalwork > 0
                  AND sofar < totalwork
                  AND last_update_time > SYSDATE - 5/1440
            """)
            sofar, total, elapsed_min, channels = cur.fetchone()
            if not total:
                return None
            pct = round(sofar / total * 100, 1)
            eta = None
            if elapsed_min and pct > 0:
                eta = round(elapsed_min * (100 - pct) / pct, 1)
            return {
                "percent": pct,
                "elapsed_minutes": elapsed_min,
                "eta_minutes": eta,
                "channels_working": channels,
                "source": "v$session_longops",
            }
    except Exception as e:
        logger.warning("rman_progress_failed", error=str(e))
        return None
