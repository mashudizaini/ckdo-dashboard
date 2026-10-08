"""
Which backups can actually bring production back, and to when?

The inventory scanner (router: /inventory/scan) looks at folders and guesses
from file names. That is enough to show what is taking disk space, but not to
answer the question an operator asks before deleting anything: "if I restore
this, how far forward can I roll it?"

That answer lives in the control file, so this module reads it — RMAN's own
record of every backup piece and every archived log — and combines it with
what is physically on disk:

  full backup restorable  = every datafile backed up, every piece AVAILABLE
                            and its folder still present on disk,
                            a control file backup taken after it started, and
                            the archive logs from its start up to its end
                            (an online backup is fuzzy until those are applied)
  recoverable until       = the end of the unbroken run of archive log
                            sequences that starts at the backup's first SCN

and classifies every archive log copy in the staging folder:

  required  sequence >= start of the NEWEST restorable full backup — the only
            path from that backup to "now". Never deletable from here.
  optional  between the oldest and newest restorable full backup — only needed
            to recover to a moment in that older window.
  obsolete  older than every restorable full backup, or from an old database
            incarnation — no backup on record can use it.

Everything here is pure parsing/logic on the text sqlplus prints; the router
owns the SSH. Times are database-server local time (WIB), labelled as such.
"""
import re
from datetime import datetime
from typing import Optional

# Archive file names follow log_archive_format %t_%s_%r.arc
ARC_NAME_RE = re.compile(r"^(\d+)_(\d+)_(\d+)\.(arc|ARC|dbf|log)$")

_TS = "%Y-%m-%d %H:%M:%S"

CATALOG_SQL = r"""SET PAGES 0 FEED OFF VERIFY OFF HEADING OFF ECHO OFF TRIMSPOOL ON TRIMOUT ON LINESIZE 4000 TAB OFF
WHENEVER SQLERROR CONTINUE
SELECT 'DB|' || d.name || '|' || i.resetlogs_id || '|' || d.resetlogs_change# || '|' || d.log_mode || '|'
       || (SELECT COUNT(*) FROM v$datafile) || '|' || TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')
       || '|' || TO_CHAR(SYSTIMESTAMP, 'TZH:TZM')
  FROM v$database d, v$database_incarnation i WHERE i.status = 'CURRENT';
SELECT 'LH|' || thread# || '|' || sequence# || '|' || first_change# || '|' || next_change# || '|'
       || TO_CHAR(first_time, 'YYYY-MM-DD HH24:MI:SS')
  FROM v$log_history
 WHERE resetlogs_change# = (SELECT resetlogs_change# FROM v$database)
   AND first_time > SYSDATE - 400;
SELECT 'FB|' || p.tag || '|' || TO_CHAR(MIN(p.start_time), 'YYYY-MM-DD HH24:MI:SS') || '|'
       || TO_CHAR(MAX(p.completion_time), 'YYYY-MM-DD HH24:MI:SS') || '|' || COUNT(DISTINCT d.file#) || '|'
       || MIN(d.checkpoint_change#) || '|' || MAX(d.checkpoint_change#)
  FROM v$backup_datafile d
  JOIN v$backup_set s ON s.set_stamp = d.set_stamp AND s.set_count = d.set_count
  JOIN v$backup_piece p ON p.set_stamp = d.set_stamp AND p.set_count = d.set_count
 WHERE d.file# > 0 AND p.deleted = 'NO'
   AND (s.backup_type = 'D' OR (s.backup_type = 'I' AND s.incremental_level = 0))
 GROUP BY p.tag;
SELECT 'BP|' || tag || '|' || status || '|' || SUM(bytes) || '|' || COUNT(*) || '|'
       || SUBSTR(handle, 1, INSTR(handle, '/', -1) - 1)
  FROM v$backup_piece WHERE deleted = 'NO'
 GROUP BY tag, status, SUBSTR(handle, 1, INSTR(handle, '/', -1) - 1);
SELECT DISTINCT 'CF|' || TO_CHAR(p.completion_time, 'YYYY-MM-DD HH24:MI:SS')
  FROM v$backup_set s JOIN v$backup_piece p ON p.set_stamp = s.set_stamp AND p.set_count = s.set_count
 WHERE s.controlfile_included IN ('YES', 'SBY') AND p.status = 'A' AND p.deleted = 'NO';
SELECT DISTINCT 'AB|' || r.thread# || '|' || r.sequence# || '|' || p.tag || '|'
       || SUBSTR(p.handle, 1, INSTR(p.handle, '/', -1) - 1)
  FROM v$backup_redolog r JOIN v$backup_piece p ON p.set_stamp = r.set_stamp AND p.set_count = r.set_count
 WHERE p.status = 'A' AND p.deleted = 'NO'
   AND r.resetlogs_change# = (SELECT resetlogs_change# FROM v$database);
SELECT 'AL|' || thread# || '|' || sequence# || '|' || TO_CHAR(first_time, 'YYYY-MM-DD HH24:MI:SS') || '|'
       || TO_CHAR(next_time, 'YYYY-MM-DD HH24:MI:SS') || '|' || (blocks * block_size) || '|' || name
  FROM v$archived_log
 WHERE deleted = 'NO' AND status = 'A' AND name IS NOT NULL AND standby_dest = 'NO'
   AND resetlogs_change# = (SELECT resetlogs_change# FROM v$database);
SELECT 'CUR|' || thread# || '|' || sequence# || '|' || TO_CHAR(first_time, 'YYYY-MM-DD HH24:MI:SS')
  FROM v$log WHERE status = 'CURRENT';
EXIT;
"""


def _ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), _TS)
    except Exception:
        return None


def _fmt(d: Optional[datetime]) -> Optional[str]:
    return d.strftime(_TS) if d else None


def parse_catalog(text: str) -> dict:
    """sqlplus output (one 'TAG|field|field' row per line) -> raw dict."""
    out = {"db": None, "log_history": {}, "fulls": {}, "pieces": [], "controlfiles": [],
           "backed_up": {}, "backed_up_dirs": {}, "on_disk": {}, "current": {}, "current_since": {},
           "errors": []}
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith(("ORA-", "SP2-", "ERROR")):
            out["errors"].append(line)
            continue
        parts = line.split("|")
        kind = parts[0]
        try:
            if kind == "DB" and len(parts) >= 8:
                out["db"] = {"name": parts[1], "resetlogs_id": parts[2], "resetlogs_change": int(parts[3]),
                             "log_mode": parts[4], "datafile_count": int(parts[5]),
                             "server_time": parts[6], "tz": parts[7]}
            elif kind == "LH" and len(parts) >= 6:
                key = (int(parts[1]), int(parts[2]))
                out["log_history"][key] = {"first_change": int(parts[3]), "next_change": int(parts[4]),
                                           "first_time": _ts(parts[5])}
            elif kind == "FB" and len(parts) >= 7:
                out["fulls"][parts[1]] = {"tag": parts[1], "start": _ts(parts[2]), "end": _ts(parts[3]),
                                          "datafiles": int(parts[4]), "min_ckp": int(parts[5]),
                                          "max_ckp": int(parts[6])}
            elif kind == "BP" and len(parts) >= 6:
                out["pieces"].append({"tag": parts[1], "status": parts[2], "bytes": int(parts[3] or 0),
                                      "count": int(parts[4] or 0), "dir": "|".join(parts[5:])})
            elif kind == "CF" and len(parts) >= 2:
                t = _ts(parts[1])
                if t:
                    out["controlfiles"].append(t)
            elif kind == "AB" and len(parts) >= 4:
                key = (int(parts[1]), int(parts[2]))
                out["backed_up"].setdefault(key, set()).add(parts[3])
                out["backed_up_dirs"].setdefault(key, set()).add("|".join(parts[4:]))
            elif kind == "AL" and len(parts) >= 7:
                out["on_disk"][(int(parts[1]), int(parts[2]))] = {
                    "first_time": _ts(parts[3]), "next_time": _ts(parts[4]),
                    "size_bytes": int(parts[5] or 0), "path": "|".join(parts[6:]),
                }
            elif kind == "CUR" and len(parts) >= 3:
                out["current"][int(parts[1])] = int(parts[2])
                if len(parts) >= 4 and _ts(parts[3]):
                    out["current_since"][int(parts[1])] = _ts(parts[3])
        except (ValueError, IndexError):
            continue
    return out


def piece_dirs(raw: dict) -> set:
    """Every folder the control file says holds an AVAILABLE backup piece —
    the router checks these exist on disk before trusting the catalog."""
    dirs = {p["dir"] for p in raw["pieces"] if p["dir"] and p["status"] == "A"}
    for ds in raw["backed_up_dirs"].values():
        dirs |= {d for d in ds if d}
    return dirs


def parse_staging_listing(text: str) -> list[dict]:
    """`find -printf '%f|%s|%T@\\n'` -> [{name, size_bytes, mtime_epoch}]"""
    files = []
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        try:
            files.append({"name": parts[0], "size_bytes": int(parts[1]), "mtime_epoch": float(parts[2])})
        except ValueError:
            continue
    return files


def _seq_for_scn(log_history: dict, thread: int, scn: int) -> Optional[int]:
    for (t, seq), lh in log_history.items():
        if t == thread and lh["first_change"] <= scn < lh["next_change"]:
            return seq
    return None


def _seq_for_time(log_history: dict, thread: int, when: datetime) -> Optional[int]:
    """The sequence that was being written at `when` — last one whose
    first_time is at or before it."""
    best = None
    for (t, seq), lh in log_history.items():
        if t == thread and lh["first_time"] and lh["first_time"] <= when:
            if best is None or seq > best:
                best = seq
    return best


def _seq_end_time(raw: dict, thread: int, seq: int) -> Optional[datetime]:
    """When a sequence stopped being written: its own next_time if the control
    file still knows the file, else the next sequence's first_time (for the
    last archived sequence that is the online log now being written, which
    v$log_history does not list yet)."""
    d = raw["on_disk"].get((thread, seq))
    if d and d["next_time"]:
        return d["next_time"]
    nxt = raw["log_history"].get((thread, seq + 1))
    if nxt:
        return nxt["first_time"]
    if raw["current"].get(thread) == seq + 1:
        return raw["current_since"].get(thread)
    return None


def build_catalog(raw: dict, staging_files: list[dict], minio_names: Optional[set] = None,
                  staging_path: str = "", missing_dirs: Optional[set] = None) -> dict:
    db = raw["db"] or {}
    thread = 1
    rid = str(db.get("resetlogs_id") or "")
    total_df = db.get("datafile_count") or 0
    minio_names = minio_names or set()
    # Folders the control file still lists as AVAILABLE but that are gone from
    # disk (deleted by hand, no CROSSCHECK since). Trusting the control file
    # alone would call such a backup restorable — and then mark every older
    # archive log obsolete, i.e. deletable, while the only usable backup is
    # the older one.
    missing_dirs = missing_dirs or set()
    backed_up = {k: v for k, v in raw["backed_up"].items()
                 if not missing_dirs or (raw["backed_up_dirs"].get(k, set()) - missing_dirs)}

    # ── Which sequences exist anywhere we could restore them from ──────────
    staging_by_seq: dict[tuple, dict] = {}
    for f in staging_files:
        m = ARC_NAME_RE.match(f["name"])
        if m and m.group(3) == rid:
            staging_by_seq[(int(m.group(1)), int(m.group(2)))] = f
    available = set(backed_up) | set(raw["on_disk"]) | set(staging_by_seq)
    for name in minio_names:
        m = ARC_NAME_RE.match(name)
        if m and m.group(3) == rid:
            available.add((int(m.group(1)), int(m.group(2))))

    current_seq = raw["current"].get(thread)
    archived_seqs = [s for (t, s) in available if t == thread]
    latest_archived = max(archived_seqs) if archived_seqs else None

    def run_until(start_seq: int) -> int:
        """Last sequence of the unbroken run beginning at start_seq (start-1 if
        start itself is missing)."""
        s = start_seq
        while (thread, s) in available:
            s += 1
        return s - 1

    # ── Full backups ───────────────────────────────────────────────────────
    pieces_by_tag: dict[str, list] = {}
    for p in raw["pieces"]:
        pieces_by_tag.setdefault(p["tag"], []).append(p)

    fulls = []
    for fb in raw["fulls"].values():
        pcs = pieces_by_tag.get(fb["tag"], [])
        bad = sum(p["count"] for p in pcs if p["status"] != "A")
        size = sum(p["bytes"] for p in pcs)
        dirs = sorted({p["dir"] for p in pcs if p["dir"]})
        # Archive/controlfile pieces of the same run usually carry their own
        # tags but land in the same folder — count them toward the folder.
        run_bytes = sum(p["bytes"] for p in raw["pieces"] if p["dir"] in dirs and p["status"] == "A")
        gone = [d for d in dirs if d in missing_dirs]
        ctl_ok = any(c >= fb["start"] for c in raw["controlfiles"]) if fb["start"] else False
        start_seq = _seq_for_scn(raw["log_history"], thread, fb["min_ckp"])
        end_seq = _seq_for_time(raw["log_history"], thread, fb["end"]) if fb["end"] else None

        problems = []
        if total_df and fb["datafiles"] < total_df:
            problems.append(f"Hanya {fb['datafiles']} dari {total_df} datafile yang ter-backup.")
        if bad:
            problems.append(f"{bad} backup piece berstatus EXPIRED/UNAVAILABLE (file hilang dari disk).")
        if gone:
            problems.append("Folder backup tidak ada lagi di disk: " + ", ".join(gone)
                            + " — control file belum di-CROSSCHECK.")
        if not ctl_ok:
            problems.append("Tidak ada backup controlfile setelah backup ini dimulai.")
        if start_seq is None:
            problems.append("Sequence archive log awal tidak ditemukan di control file.")

        last_seq = None
        recoverable_until = None
        if start_seq is not None:
            last_seq = run_until(start_seq)
            if end_seq is not None and last_seq < end_seq:
                missing = [s for s in range(start_seq, end_seq + 1) if (thread, s) not in available]
                problems.append(
                    "Archive log yang dibutuhkan agar backup ini konsisten hilang: seq "
                    + ", ".join(str(s) for s in missing[:10]) + ("…" if len(missing) > 10 else "")
                )
            elif last_seq >= start_seq:
                recoverable_until = _seq_end_time(raw, thread, last_seq)

        restorable = not problems
        fulls.append({
            "tag": fb["tag"],
            "start_time": _fmt(fb["start"]), "end_time": _fmt(fb["end"]),
            "datafiles": fb["datafiles"], "datafiles_total": total_df,
            "datafile_bytes": size, "size_bytes": run_bytes or size,
            "dirs": dirs, "folder_names": [d.rstrip("/").split("/")[-1] for d in dirs],
            "controlfile_ok": ctl_ok, "bad_pieces": bad,
            "start_seq": start_seq, "end_seq": end_seq, "last_seq": last_seq,
            "restorable": restorable,
            "recoverable_from": _fmt(fb["end"]) if restorable else None,
            "recoverable_until": _fmt(recoverable_until) if restorable else None,
            "problems": problems,
        })
    fulls.sort(key=lambda f: f["start_time"] or "", reverse=True)

    restorable_fulls = [f for f in fulls if f["restorable"]]
    for i, f in enumerate(fulls):
        f["is_latest"] = bool(restorable_fulls) and f is restorable_fulls[0]

    # ── Gaps in the chain the restorable backups depend on ────────────────
    gaps = []
    if restorable_fulls and latest_archived is not None:
        lo = min(f["start_seq"] for f in restorable_fulls)
        gaps = [s for s in range(lo, latest_archived + 1) if (thread, s) not in available]

    # ── Classify archive log copies ────────────────────────────────────────
    newest = restorable_fulls[0] if restorable_fulls else None
    oldest = restorable_fulls[-1] if restorable_fulls else None

    def classify(t: int, seq: int, file_rid: str) -> tuple[str, str]:
        if file_rid != rid:
            return "obsolete", "Dari incarnation database lama (sebelum RESETLOGS) — tidak bisa dipakai lagi."
        if not newest:
            return "required", "Belum ada full backup yang terbukti bisa di-restore — simpan semua archive log."
        if seq >= newest["start_seq"]:
            return "required", (f"Dibutuhkan untuk recovery dari full backup terbaru ({newest['start_time']}) "
                                f"sampai kondisi terkini.")
        if seq >= oldest["start_seq"]:
            older = [f for f in restorable_fulls if f["start_seq"] <= seq]
            ref = older[0] if older else oldest
            return "optional", (f"Hanya untuk point-in-time recovery ke waktu antara {ref['start_time'][:10]} "
                                f"dan {newest['start_time'][:10]} memakai full backup lama ({ref['tag']}).")
        return "obsolete", (f"Lebih tua dari full backup tertua yang masih bisa di-restore "
                            f"({oldest['start_time'][:10]}, mulai seq {oldest['start_seq']}) — tidak ada backup yang membutuhkannya.")

    archivelogs = []
    seen = set()
    for f in staging_files:
        m = ARC_NAME_RE.match(f["name"])
        if not m:
            continue
        t, seq, file_rid = int(m.group(1)), int(m.group(2)), m.group(3)
        cat, reason = classify(t, seq, file_rid)
        same_inc = file_rid == rid
        lh = raw["log_history"].get((t, seq)) if same_inc else None
        tags = sorted(backed_up.get((t, seq), set())) if same_inc else []
        seen.add((t, seq, file_rid))
        archivelogs.append({
            "name": f["name"], "thread": t, "sequence": seq, "resetlogs_id": file_rid,
            "size_bytes": f["size_bytes"],
            "modified_at": datetime.utcfromtimestamp(f["mtime_epoch"]).isoformat() + "Z",
            "first_time": _fmt(lh["first_time"]) if lh else None,
            "end_time": _fmt(_seq_end_time(raw, t, seq)) if same_inc else None,
            "in_staging": True,
            "on_disk": same_inc and (t, seq) in raw["on_disk"],
            "in_backupset": bool(tags), "backupset_tags": tags,
            "in_minio": f["name"] in minio_names,
            "category": cat, "reason": reason,
            "deletable": cat in ("obsolete", "optional"),
            "location": "staging", "path": f"{staging_path.rstrip('/')}/{f['name']}" if staging_path else f["name"],
        })
    # Archive logs only in the database's own archive destination (not yet
    # copied to staging) — shown for completeness, never deletable from here:
    # those are managed by RMAN (cron RMAN-DelArch.sh), not by rm.
    for (t, seq), d in raw["on_disk"].items():
        if (t, seq, rid) in seen:
            continue
        cat, reason = classify(t, seq, rid)
        tags = sorted(backed_up.get((t, seq), set()))
        lh = raw["log_history"].get((t, seq))
        archivelogs.append({
            "name": d["path"].split("/")[-1], "thread": t, "sequence": seq, "resetlogs_id": rid,
            "size_bytes": d["size_bytes"], "modified_at": None,
            "first_time": _fmt(d["first_time"] or (lh["first_time"] if lh else None)),
            "end_time": _fmt(d["next_time"]),
            "in_staging": False, "on_disk": True,
            "in_backupset": bool(tags), "backupset_tags": tags,
            "in_minio": d["path"].split("/")[-1] in minio_names,
            "category": cat,
            "reason": reason + " (Belum tersalin ke staging — dikelola oleh RMAN di archive destination.)",
            "deletable": False, "location": "archive_dest", "path": d["path"],
        })
    archivelogs.sort(key=lambda a: (a["resetlogs_id"] == rid, a["sequence"]), reverse=True)

    summary_by_cat = {c: {"count": 0, "bytes": 0} for c in ("required", "optional", "obsolete")}
    for a in archivelogs:
        if a["location"] == "staging":
            summary_by_cat[a["category"]]["count"] += 1
            summary_by_cat[a["category"]]["bytes"] += a["size_bytes"]

    # ── Overall verdict ────────────────────────────────────────────────────
    server_now = _ts(db.get("server_time", "")) if db else None
    until = _ts(newest["recoverable_until"]) if newest and newest["recoverable_until"] else None
    rpo_minutes = int((server_now - until).total_seconds() // 60) if (server_now and until) else None
    warnings = []
    if not newest:
        status, message = "red", "Tidak ada full backup RMAN yang terbukti bisa di-restore."
    else:
        age_days = (server_now - _ts(newest["start_time"])).days if server_now else None
        message = (f"Database bisa dipulihkan ke titik waktu mana pun antara {newest['recoverable_from']} "
                   f"dan {newest['recoverable_until'] or 'sequence ' + str(newest['last_seq'])} WIB "
                   f"memakai full backup {newest['tag']}.")
        status = "green"
        if age_days is not None and age_days > 7:
            status = "amber"
            warnings.append(f"Full backup terbaru sudah {age_days} hari — recovery akan butuh banyak archive log "
                            f"(lebih lama). Jadwalkan full backup mingguan.")
        if rpo_minutes is not None and rpo_minutes > 24 * 60:
            status = "amber"
            warnings.append(f"Archive log terakhir yang tersedia {rpo_minutes // 60} jam lalu — "
                            f"cek apakah log switch / sinkronisasi archive berjalan.")
        if len(restorable_fulls) < 2:
            warnings.append("Hanya ada 1 full backup yang bisa di-restore. Idealnya simpan minimal 2.")
    if gaps:
        if status == "green":
            status = "amber"
        warnings.append("Ada sequence archive log yang hilang: " + ", ".join(str(g) for g in gaps[:15])
                        + ("…" if len(gaps) > 15 else "") + " — recovery berhenti di sequence sebelum celah.")

    return {
        "db": {**db, "current_sequence": current_seq, "latest_archived_sequence": latest_archived},
        "summary": {
            "status": status, "message": message, "warnings": warnings,
            "recoverable_from": newest["recoverable_from"] if newest else None,
            "recoverable_until": newest["recoverable_until"] if newest else None,
            "oldest_point": oldest["recoverable_from"] if oldest else None,
            "rpo_minutes": rpo_minutes, "restorable_count": len(restorable_fulls),
            "gaps": gaps,
        },
        "full_backups": fulls,
        "archivelogs": archivelogs,
        "archivelog_summary": summary_by_cat,
        "errors": raw["errors"][:5],
    }
