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

and classifies every archive log, wherever its copies are (staging folder on
the DB server, MinIO archive-logs/, Synology over the NFS mount):

  required  sequence >= start of the NEWEST restorable full backup — the only
            path from that backup to "now". Never deletable from here.
  optional  between the oldest and newest restorable full backup — only needed
            to recover to a moment in that older window.
  obsolete  older than every restorable full backup, or from an old database
            incarnation — no backup on record can use it.
  unknown   resetlogs id this database never had — another database's log
            sharing the NAS / bucket. Never deletable from here.

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
SELECT 'INC|' || resetlogs_id FROM v$database_incarnation;
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
           "incarnations": set(), "errors": []}
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
            elif kind == "INC" and len(parts) >= 2 and parts[1]:
                out["incarnations"].add(parts[1])
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


def parse_file_listing(text: str) -> list[dict]:
    """`find -printf '%p|%s|%T@\\n'` -> [{name, ref, size_bytes, mtime_epoch}].
    `ref` is the full path — what a delete has to name. Split from the right
    so a '|' in a folder name cannot shift the fields."""
    files = []
    for line in text.splitlines():
        parts = line.strip().rsplit("|", 2)
        if len(parts) != 3 or not parts[0]:
            continue
        try:
            files.append({"name": parts[0].rsplit("/", 1)[-1], "ref": parts[0],
                          "size_bytes": int(parts[1]), "mtime_epoch": float(parts[2])})
        except ValueError:
            continue
    return files


def parse_staging_listing(text: str) -> list[dict]:
    """Kept for callers of the old '%f|%s|%T@' form."""
    return parse_file_listing(text)


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


# Where an archive log copy can live. archive_dest (the database's own
# log_archive_dest) is listed too but never deleted from here — RMAN owns it.
COPY_LOCATIONS = ("staging", "minio", "synology")
CATEGORIES = ("required", "optional", "obsolete", "unknown")


def build_catalog(raw: dict, staging_files: list[dict], minio_names: Optional[set] = None,
                  staging_path: str = "", missing_dirs: Optional[set] = None,
                  remote_files: Optional[dict] = None, synology_dirs: Optional[dict] = None) -> dict:
    """
    staging_files / remote_files["minio"|"synology"]: [{name, ref, size_bytes, mtime_epoch}]
    synology_dirs: {folder basename: full path} of every folder on the NAS —
                   a full backup whose staging folder is gone may still be
                   restorable from its Synology copy.
    minio_names:   legacy — bare names only, used when remote_files has no minio.
    """
    db = raw["db"] or {}
    thread = 1
    rid = str(db.get("resetlogs_id") or "")
    incarnations = set(raw.get("incarnations") or ()) | ({rid} if rid else set())
    total_df = db.get("datafile_count") or 0
    remote_files = dict(remote_files or {})
    if "minio" not in remote_files and minio_names:
        remote_files["minio"] = [{"name": n, "ref": n, "size_bytes": 0, "mtime_epoch": None} for n in minio_names]
    synology_dirs = synology_dirs or {}

    # Folders the control file still lists as AVAILABLE but that are gone from
    # disk (deleted by hand, no CROSSCHECK since). Trusting the control file
    # alone would call such a backup restorable — and then mark every older
    # archive log obsolete, i.e. deletable, while the only usable backup is
    # the older one. A folder that still exists on Synology is not lost: it can
    # be catalogued from there.
    def _base(d: str) -> str:
        return d.rstrip("/").rsplit("/", 1)[-1]

    missing_all = set(missing_dirs or ())
    on_synology = {d for d in missing_all if _base(d) in synology_dirs}
    missing = missing_all - on_synology
    backed_up = {k: v for k, v in raw["backed_up"].items()
                 if not missing or (raw["backed_up_dirs"].get(k, set()) - missing)}

    # ── Every copy of every archive log, grouped by (thread, seq, resetlogs) ─
    groups: dict[tuple, dict] = {}

    def add_copy(loc: str, f: dict):
        m = ARC_NAME_RE.match(f["name"])
        if not m:
            return
        key = (int(m.group(1)), int(m.group(2)), m.group(3))
        g = groups.setdefault(key, {"name": f["name"], "copies": {}})
        c = g["copies"].setdefault(loc, {"refs": [], "size_bytes": 0, "mtime_epoch": None})
        c["refs"].append(f.get("ref") or f["name"])
        c["size_bytes"] += f.get("size_bytes") or 0
        if f.get("mtime_epoch") and (c["mtime_epoch"] is None or f["mtime_epoch"] > c["mtime_epoch"]):
            c["mtime_epoch"] = f["mtime_epoch"]

    for f in staging_files:
        add_copy("staging", f)
    for loc in ("minio", "synology"):
        for f in remote_files.get(loc) or []:
            add_copy(loc, f)

    available = set(backed_up) | set(raw["on_disk"])
    available |= {(t, s) for (t, s, r), g in groups.items() if r == rid and g["copies"]}

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
        gone = [d for d in dirs if d in missing]
        from_syn = [d for d in dirs if d in on_synology]
        syn_paths = sorted({synology_dirs[_base(d)] for d in dirs if _base(d) in synology_dirs})
        ctl_ok = any(c >= fb["start"] for c in raw["controlfiles"]) if fb["start"] else False
        start_seq = _seq_for_scn(raw["log_history"], thread, fb["min_ckp"])
        end_seq = _seq_for_time(raw["log_history"], thread, fb["end"]) if fb["end"] else None

        problems, notes = [], []
        if total_df and fb["datafiles"] < total_df:
            problems.append(f"Hanya {fb['datafiles']} dari {total_df} datafile yang ter-backup.")
        if bad:
            problems.append(f"{bad} backup piece berstatus EXPIRED/UNAVAILABLE (file hilang dari disk).")
        if gone:
            problems.append("Folder backup tidak ada lagi di disk maupun Synology: " + ", ".join(gone)
                            + " — control file belum di-CROSSCHECK.")
        if from_syn:
            notes.append("Folder di staging sudah tidak ada — restore dari salinan Synology "
                         "(jalankan CATALOG START WITH ke folder Synology lebih dulu).")
        if not ctl_ok:
            problems.append("Tidak ada backup controlfile setelah backup ini dimulai.")
        if start_seq is None:
            problems.append("Sequence archive log awal tidak ditemukan di control file.")

        last_seq = None
        recoverable_until = None
        if start_seq is not None:
            last_seq = run_until(start_seq)
            if end_seq is not None and last_seq < end_seq:
                miss = [s for s in range(start_seq, end_seq + 1) if (thread, s) not in available]
                problems.append(
                    "Archive log yang dibutuhkan agar backup ini konsisten hilang: seq "
                    + ", ".join(str(s) for s in miss[:10]) + ("…" if len(miss) > 10 else "")
                )
            elif last_seq >= start_seq:
                recoverable_until = _seq_end_time(raw, thread, last_seq)

        restorable = not problems
        copies = (["staging"] if any(d not in missing_all for d in dirs) else []) + (["synology"] if syn_paths else [])
        fulls.append({
            "tag": fb["tag"],
            "start_time": _fmt(fb["start"]), "end_time": _fmt(fb["end"]),
            "datafiles": fb["datafiles"], "datafiles_total": total_df,
            "datafile_bytes": size, "size_bytes": run_bytes or size,
            "dirs": dirs, "folder_names": [_base(d) for d in dirs],
            "synology_paths": syn_paths, "copies": copies,
            "restore_dir": syn_paths[0] if (from_syn and syn_paths) else (dirs[0] if dirs else None),
            "restore_source": "synology" if from_syn else "staging",
            "controlfile_ok": ctl_ok, "bad_pieces": bad,
            "start_seq": start_seq, "end_seq": end_seq, "last_seq": last_seq,
            "restorable": restorable,
            "recoverable_from": _fmt(fb["end"]) if restorable else None,
            "recoverable_until": _fmt(recoverable_until) if restorable else None,
            "problems": problems, "notes": notes,
        })
    fulls.sort(key=lambda f: f["start_time"] or "", reverse=True)

    restorable_fulls = [f for f in fulls if f["restorable"]]
    for f in fulls:
        f["is_latest"] = bool(restorable_fulls) and f is restorable_fulls[0]

    # ── Gaps in the chain the restorable backups depend on ────────────────
    gaps = []
    if restorable_fulls and latest_archived is not None:
        lo = min(f["start_seq"] for f in restorable_fulls)
        gaps = [s for s in range(lo, latest_archived + 1) if (thread, s) not in available]

    # ── Classify archive logs ──────────────────────────────────────────────
    newest = restorable_fulls[0] if restorable_fulls else None
    oldest = restorable_fulls[-1] if restorable_fulls else None

    def classify(t: int, seq: int, file_rid: str) -> tuple[str, str]:
        if file_rid != rid:
            if file_rid in incarnations:
                return "obsolete", "Dari incarnation database lama (sebelum RESETLOGS) — tidak bisa dipakai lagi."
            # MinIO / Synology may also hold logs of another database (DEV,
            # TEST) with the same naming. Not ours to judge — never deletable.
            return "unknown", ("Resetlogs id tidak dikenal oleh database PROD — kemungkinan milik database lain. "
                               "Tidak bisa dihapus dari sini.")
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

    # Logs only in the database's own archive destination still get a row.
    for (t, seq), d in raw["on_disk"].items():
        groups.setdefault((t, seq, rid), {"name": d["path"].split("/")[-1], "copies": {}})

    def _iso(epoch):
        return datetime.utcfromtimestamp(epoch).isoformat() + "Z" if epoch else None

    archivelogs = []
    for (t, seq, file_rid), g in groups.items():
        cat, reason = classify(t, seq, file_rid)
        same_inc = file_rid == rid
        lh = raw["log_history"].get((t, seq)) if same_inc else None
        d = raw["on_disk"].get((t, seq)) if same_inc else None
        tags = sorted(backed_up.get((t, seq), set())) if same_inc else []
        copies = {loc: {"count": len(c["refs"]), "size_bytes": c["size_bytes"], "refs": c["refs"],
                        "modified_at": _iso(c["mtime_epoch"])}
                  for loc, c in g["copies"].items()}
        mtimes = [c["mtime_epoch"] for c in g["copies"].values() if c["mtime_epoch"]]
        sizes = [c["size_bytes"] // max(len(c["refs"]), 1) for c in g["copies"].values() if c["size_bytes"]]
        if not copies:
            reason += " (Belum tersalin ke staging/MinIO/Synology — dikelola oleh RMAN di archive destination.)"
        staging_ref = copies["staging"]["refs"][0] if "staging" in copies else None
        archivelogs.append({
            "name": g["name"], "thread": t, "sequence": seq, "resetlogs_id": file_rid,
            "size_bytes": max(sizes) if sizes else (d["size_bytes"] if d else 0),
            "modified_at": _iso(max(mtimes)) if mtimes else None,
            "first_time": _fmt((d and d["first_time"]) or (lh["first_time"] if lh else None)),
            "end_time": _fmt(_seq_end_time(raw, t, seq)) if same_inc else None,
            "copies": copies,
            "in_staging": "staging" in copies, "in_minio": "minio" in copies, "in_synology": "synology" in copies,
            "on_disk": d is not None,
            "in_backupset": bool(tags), "backupset_tags": tags,
            "category": cat, "reason": reason,
            "deletable": cat in ("obsolete", "optional") and bool(copies),
            "location": "staging" if staging_ref else ("remote" if copies else "archive_dest"),
            "path": staging_ref or (d["path"] if d else g["name"]),
        })
    archivelogs.sort(key=lambda a: (a["resetlogs_id"] == rid, a["sequence"]), reverse=True)

    def _empty():
        return {"count": 0, "bytes": 0}

    summary_by_cat = {c: {**_empty(), "by_location": {loc: _empty() for loc in COPY_LOCATIONS}} for c in CATEGORIES}
    for a in archivelogs:
        if not a["copies"]:
            continue
        s = summary_by_cat[a["category"]]
        s["count"] += 1
        for loc, c in a["copies"].items():
            s["bytes"] += c["size_bytes"]
            s["by_location"][loc]["count"] += c["count"]
            s["by_location"][loc]["bytes"] += c["size_bytes"]

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
        if synology_dirs and "synology" not in newest["copies"]:
            warnings.append("Full backup terbaru belum punya salinan di Synology — bila server DB rusak, "
                            "backup ini ikut hilang.")
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
