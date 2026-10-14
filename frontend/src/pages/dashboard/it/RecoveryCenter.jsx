/**
 * Backup & Recovery Center (Oracle EBS)
 * ─────────────────────────────────────────
 * Replaces the old "Recovery Health" tab. Two data sources:
 *   - /recovery/catalog  → RMAN's own records (control file): which full
 *     backups are restorable, how far each can be rolled forward, and a
 *     required / optional / obsolete verdict for every archive log copy.
 *   - /inventory/scan    → every backup folder on disk / MinIO / Synology,
 *     now with its backup date, newest first.
 * Nothing is deleted without an explicit, typed confirmation, and the backend
 * re-checks every archive log at delete time.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import {
  ShieldCheck, ShieldAlert, ShieldX, RefreshCw, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Trash2, Database, FileArchive, FolderOpen, BookOpen, ChevronDown, ChevronUp, Copy, Search,
  Clock, HardDrive, Info, ArrowDownWideNarrow, ArrowUpNarrowWide, X,
} from "lucide-react";
import { ebsBackupApi } from "@/api/ebsBackup";

/* ─── Formatting ─────────────────────────────────── */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtBytes(n) {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i >= 3 ? 1 : 0)} ${units[i]}`;
}

// Database-server local time ("YYYY-MM-DD HH:MM:SS", WIB) — parsed by hand so
// it renders the same in every browser and is never shifted by the viewer's
// own timezone.
function parseLocal(s) {
  const m = s && /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s);
  if (!m) return null;
  return { y: +m[1], mo: +m[2], d: +m[3], h: m[4], mi: m[5], ms: Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) };
}

function fmtLocal(s, { time = true } = {}) {
  const p = parseLocal(s);
  if (!p) return "—";
  const date = `${String(p.d).padStart(2, "0")} ${MONTHS[p.mo - 1]} ${p.y}`;
  return time ? `${date} ${p.h}:${p.mi}` : date;
}

function fmtIso(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (_) { return iso; }
}

function fmtMinutes(min) {
  if (min === null || min === undefined) return "—";
  if (min < 60) return `${min} min`;
  if (min < 1440) return `${Math.floor(min / 60)} h ${min % 60} m`;
  return `${Math.floor(min / 1440)} d ${Math.floor((min % 1440) / 60)} h`;
}

function daysAgo(s) {
  const p = parseLocal(s);
  if (!p) return null;
  const now = new Date();
  const nowWib = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), now.getUTCHours() + 7, now.getUTCMinutes());
  return Math.max(0, Math.floor((nowWib - p.ms) / 86400000));
}

/* ─── Small UI pieces ────────────────────────────── */

const C = {
  ink: "#0f172a", sub: "#64748b", faint: "#94a3b8", line: "rgba(15,23,42,0.08)", soft: "#f8fafc",
  blue: "#2563eb", green: "#16a34a", amber: "#d97706", red: "#dc2626",
};

const CATEGORY = {
  required: { label: "Must keep", short: "Must keep", color: C.red, bg: "rgba(220,38,38,0.08)" },
  optional: { label: "Optional (older PITR)", short: "Optional", color: C.amber, bg: "rgba(217,119,6,0.1)" },
  obsolete: { label: "Safe to delete", short: "Safe to delete", color: C.green, bg: "rgba(22,163,74,0.1)" },
  unknown: { label: "Not from PROD", short: "Not PROD", color: C.sub, bg: "rgba(100,116,139,0.1)" },
};

// Where archive log copies live. archive_dest (the database's own folder) is
// shown but never deletable from here — RMAN manages it.
const LOCS = [
  { id: "staging", label: "Staging", long: "Staging (server DB)" },
  { id: "minio", label: "MinIO", long: "MinIO (archive-logs/)" },
  { id: "synology", label: "Synology", long: "Synology (NFS)" },
];

function Card({ children, style, className = "" }) {
  return (
    <div className={`rounded-xl ${className}`} style={{ background: "#fff", border: `1px solid ${C.line}`, ...style }}>
      {children}
    </div>
  );
}

function Button({ onClick, children, variant = "default", disabled, icon: Icon, size = "md", title }) {
  const v = {
    default: { bg: "#f1f5f9", color: "#334155" },
    primary: { bg: C.blue, color: "#fff" },
    danger: { bg: C.red, color: "#fff" },
    ghost: { bg: "transparent", color: C.blue },
  }[variant];
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title}
      className="inline-flex items-center gap-1.5 rounded-lg transition-all whitespace-nowrap"
      style={{
        background: v.bg, color: v.color, fontWeight: 700, border: "none",
        padding: size === "sm" ? "5px 10px" : "7px 14px", fontSize: size === "sm" ? 11 : 12,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
      }}>
      {Icon && <Icon size={size === "sm" ? 12 : 13} className={Icon === Loader2 ? "animate-spin" : ""} />}{children}
    </button>
  );
}

function Pill({ color, bg, children, title }) {
  return (
    <span title={title} className="inline-flex items-center gap-1 rounded-full whitespace-nowrap"
      style={{ color, background: bg || `${color}14`, padding: "2px 8px", fontSize: 10.5, fontWeight: 700 }}>
      {children}
    </span>
  );
}

function Stat({ label, value, sub, color = C.ink, icon: Icon }) {
  return (
    <Card style={{ padding: 14 }}>
      <div className="flex items-center gap-1.5" style={{ fontSize: 10.5, color: C.sub, fontWeight: 700, marginBottom: 6 }}>
        {Icon && <Icon size={12} />}{label}
      </div>
      <div style={{ fontSize: 17, fontWeight: 800, color, lineHeight: 1.25 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: C.faint, marginTop: 3 }}>{sub}</div>}
    </Card>
  );
}

function Empty({ children }) {
  return <p style={{ fontSize: 12, color: C.faint, textAlign: "center", padding: "28px 0" }}>{children}</p>;
}

function ErrorBox({ children }) {
  return (
    <div className="flex items-start gap-2 rounded-lg px-3 py-2 mb-3" style={{ background: "rgba(220,38,38,0.06)", color: C.red, fontSize: 12 }}>
      <XCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} /><span>{children}</span>
    </div>
  );
}

function Modal({ title, onClose, children, footer }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(15,23,42,0.45)" }} onClick={onClose}>
      <div className="rounded-2xl w-full" style={{ background: "#fff", maxWidth: 560, maxHeight: "90vh", overflow: "auto", boxShadow: "0 20px 50px rgba(15,23,42,0.25)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3.5" style={{ borderBottom: `1px solid ${C.line}` }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{title}</h3>
          <button type="button" onClick={onClose} style={{ color: C.sub, background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <div className="p-5" style={{ fontSize: 12.5, color: C.ink }}>{children}</div>
        {footer && <div className="flex justify-end gap-2 px-5 py-3" style={{ borderTop: `1px solid ${C.line}`, background: C.soft }}>{footer}</div>}
      </div>
    </div>
  );
}

function errMsg(e, fallback) {
  return e?.response?.data?.detail || e?.detail || e?.message || fallback;
}

/* ─── Main ───────────────────────────────────────── */

const VIEWS = [
  { id: "summary", label: "Summary", icon: ShieldCheck },
  { id: "fulls", label: "Full Backup (RMAN)", icon: Database },
  { id: "archivelog", label: "Archive Log", icon: FileArchive },
  { id: "files", label: "All Backup Files", icon: FolderOpen },
  { id: "guide", label: "Guide", icon: BookOpen },
];

export default function RecoveryCenter() {
  const [view, setView] = useState("summary");
  const [catalog, setCatalog] = useState(null);
  const [catalogErr, setCatalogErr] = useState(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [inventory, setInventory] = useState(null);
  const [inventoryErr, setInventoryErr] = useState(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true); setCatalogErr(null);
    try { setCatalog(await ebsBackupApi.recoveryCatalog()); }
    catch (e) { setCatalogErr(errMsg(e, "Failed to read the RMAN catalog")); }
    finally { setCatalogLoading(false); }
  }, []);

  const loadInventory = useCallback(async () => {
    setInventoryLoading(true); setInventoryErr(null);
    try { setInventory(await ebsBackupApi.scanInventory()); }
    catch (e) { setInventoryErr(errMsg(e, "Failed to scan backup files")); }
    finally { setInventoryLoading(false); }
  }, []);

  const refreshAll = useCallback(() => { loadCatalog(); loadInventory(); }, [loadCatalog, loadInventory]);
  useEffect(() => { refreshAll(); }, [refreshAll]);

  const loading = catalogLoading || inventoryLoading;

  return (
    <div style={{ background: "#fff", borderRadius: 16, boxShadow: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", marginBottom: 16 }}>
      <div className="flex items-center justify-between flex-wrap gap-3 px-5 py-3.5" style={{ borderBottom: `1px solid ${C.line}` }}>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: C.ink }}>Backup &amp; Recovery Center</h3>
          <p style={{ fontSize: 11.5, color: C.sub, marginTop: 2 }}>
            Recovery status is read directly from PROD's RMAN records (control file) — not guessed from file names.
            {catalog?.generated_at && <> Last scanned {fmtIso(catalog.generated_at + "Z")}.</>}
          </p>
        </div>
        <Button icon={loading ? Loader2 : RefreshCw} onClick={refreshAll} disabled={loading}>{loading ? "Scanning…" : "Rescan"}</Button>
      </div>

      <div className="flex gap-1 flex-wrap px-5 pt-3">
        {VIEWS.map((v) => {
          const Icon = v.icon;
          const active = view === v.id;
          const badge = v.id === "archivelog" && catalog?.archivelog_summary?.obsolete?.count
            ? catalog.archivelog_summary.obsolete.count : null;
          return (
            <button key={v.id} type="button" onClick={() => setView(v.id)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs transition-all"
              style={{ fontWeight: 700, border: "none", cursor: "pointer", color: active ? C.blue : C.sub, background: active ? "rgba(37,99,235,0.08)" : "transparent" }}>
              <Icon size={13} />{v.label}
              {badge ? <span className="rounded-full" style={{ background: C.green, color: "#fff", fontSize: 9.5, padding: "0 6px" }}>{badge}</span> : null}
            </button>
          );
        })}
      </div>

      <div className="p-5">
        {view === "summary" && <SummaryView catalog={catalog} err={catalogErr} goTo={setView} />}
        {view === "fulls" && <FullBackupsView catalog={catalog} err={catalogErr} inventory={inventory} />}
        {view === "archivelog" && <ArchivelogView catalog={catalog} err={catalogErr} onChanged={loadCatalog} />}
        {view === "files" && <FilesView inventory={inventory} err={inventoryErr} catalog={catalog} onChanged={refreshAll} />}
        {view === "guide" && <GuideView catalog={catalog} />}
      </div>
    </div>
  );
}

/* ─── Summary ────────────────────────────────────── */

function SummaryView({ catalog, err, goTo }) {
  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!catalog) return <Empty>Reading the RMAN catalog…</Empty>;
  const s = catalog.summary;
  const cfg = {
    green: { icon: ShieldCheck, color: C.green, title: "READY TO RESTORE" },
    amber: { icon: ShieldAlert, color: C.amber, title: "NEEDS ATTENTION" },
    red: { icon: ShieldX, color: C.red, title: "NOT READY TO RESTORE" },
  }[s.status] || { icon: ShieldAlert, color: C.faint, title: "—" };
  const Icon = cfg.icon;
  const latest = catalog.full_backups.find((f) => f.is_latest);
  const obs = catalog.archivelog_summary.obsolete;

  return (
    <>
      <div className="rounded-xl p-5 mb-4 flex items-start gap-4" style={{ background: `${cfg.color}0d`, border: `1px solid ${cfg.color}40` }}>
        <Icon size={40} color={cfg.color} style={{ flexShrink: 0 }} />
        <div>
          <p style={{ fontSize: 20, fontWeight: 800, color: cfg.color, letterSpacing: 0.3 }}>{cfg.title}</p>
          <p style={{ fontSize: 13, color: C.ink, marginTop: 4 }}>{s.message}</p>
          {s.warnings?.map((w, i) => (
            <p key={i} className="flex items-start gap-1.5" style={{ fontSize: 12, color: C.amber, marginTop: 6 }}>
              <AlertTriangle size={13} style={{ marginTop: 1, flexShrink: 0 }} />{w}
            </p>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
        <Stat icon={Clock} label="Recoverable up to" value={fmtLocal(s.recoverable_until)} sub="latest point (WIB)" color={C.green} />
        <Stat icon={Clock} label="Oldest point" value={fmtLocal(s.oldest_point)} sub="with the oldest full backup" />
        <Stat icon={Database} label="Restorable full backups" value={`${s.restorable_count} / ${catalog.full_backups.length}`}
          sub={latest ? `latest ${daysAgo(latest.start_time)} days ago` : "—"} color={s.restorable_count ? C.ink : C.red} />
        <Stat icon={AlertTriangle} label="Potential data loss (RPO)" value={fmtMinutes(s.rpo_minutes)}
          sub="if the server were lost right now" color={s.rpo_minutes > 1440 ? C.red : s.rpo_minutes > 360 ? C.amber : C.ink} />
        <Stat icon={HardDrive} label="Archive logs safe to delete" value={fmtBytes(obs.bytes)}
          sub={`${obs.count} sequence · ${LOCS.map((l) => `${l.label} ${fmtBytes(obs.by_location?.[l.id]?.bytes || 0)}`).join(" · ")}`} color={C.green} />
      </div>

      <RecoveryTimeline catalog={catalog} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
        <QuickLink onClick={() => goTo("fulls")} icon={Database} title="View full backups"
          text="Which backups can be restored, up to when, and their RMAN commands." />
        <QuickLink onClick={() => goTo("archivelog")} icon={FileArchive} title="Manage archive logs"
          text={`${obs.count} files (${fmtBytes(obs.bytes)}) are no longer needed by any backup.`} />
        <QuickLink onClick={() => goTo("guide")} icon={BookOpen} title="How recovery works"
          text="A short explanation of full backups + archive logs and the retention policy." />
      </div>
    </>
  );
}

function QuickLink({ onClick, icon: Icon, title, text }) {
  return (
    <button type="button" onClick={onClick} className="text-left rounded-xl p-4 transition-all hover:shadow-sm"
      style={{ background: C.soft, border: `1px solid ${C.line}`, cursor: "pointer" }}>
      <div className="flex items-center gap-2" style={{ fontSize: 12.5, fontWeight: 800, color: C.blue }}><Icon size={14} />{title}</div>
      <p style={{ fontSize: 11.5, color: C.sub, marginTop: 4 }}>{text}</p>
    </button>
  );
}

function RecoveryTimeline({ catalog }) {
  const fulls = catalog.full_backups.filter((f) => f.restorable && f.recoverable_until);
  if (!fulls.length) return null;
  const t0 = Math.min(...fulls.map((f) => parseLocal(f.start_time).ms));
  const t1 = Math.max(...fulls.map((f) => parseLocal(f.recoverable_until).ms));
  const span = Math.max(t1 - t0, 3600000);
  const pct = (s) => ((parseLocal(s).ms - t0) / span) * 100;

  return (
    <Card style={{ padding: 16 }}>
      <div className="flex items-center justify-between mb-3">
        <p style={{ fontSize: 12, fontWeight: 800, color: C.ink }}>Recovery window (point-in-time)</p>
        <p style={{ fontSize: 11, color: C.faint }}>Green bar = the time range that backup can be recovered to</p>
      </div>
      <div className="space-y-3">
        {fulls.map((f) => {
          const left = pct(f.start_time), right = pct(f.recoverable_until);
          return (
            <div key={f.tag} className="flex items-center gap-3">
              <div style={{ width: 150, flexShrink: 0, fontSize: 11.5 }}>
                <div style={{ fontWeight: 700, color: C.ink }}>{fmtLocal(f.start_time, { time: false })}</div>
                <div style={{ color: C.faint, fontSize: 10.5 }}>{f.is_latest ? "Latest full backup" : "Older full backup"}</div>
              </div>
              <div className="relative flex-1 rounded-full" style={{ height: 14, background: "#eef2f7" }}>
                <div className="absolute rounded-full" title={`Restore + recover: ${fmtLocal(f.recoverable_from)} → ${fmtLocal(f.recoverable_until)}`}
                  style={{ left: `${left}%`, width: `${Math.max(right - left, 0.8)}%`, top: 0, bottom: 0, background: f.is_latest ? C.green : "rgba(22,163,74,0.45)" }} />
                <div className="absolute" title="Full backup taken" style={{ left: `calc(${left}% - 1px)`, top: -3, bottom: -3, width: 3, borderRadius: 2, background: C.blue }} />
              </div>
              <div style={{ width: 130, flexShrink: 0, fontSize: 11, color: C.sub, textAlign: "right" }}>to {fmtLocal(f.recoverable_until)}</div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-2" style={{ fontSize: 10.5, color: C.faint, paddingLeft: 162, paddingRight: 142 }}>
        <span>{fmtLocal(fulls[fulls.length - 1].start_time, { time: false })}</span>
        <span>{fmtLocal(fulls[0].recoverable_until)}</span>
      </div>
    </Card>
  );
}

/* ─── Full Backup (RMAN) ─────────────────────────── */

function FullBackupsView({ catalog, err, inventory }) {
  const [open, setOpen] = useState({});
  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!catalog) return <Empty>Reading the RMAN catalog…</Empty>;
  if (!catalog.full_backups.length) return <Empty>No RMAN full backup is recorded in the control file yet.</Empty>;

  // Offsite copies come from the inventory scan, matched by folder name.
  const copiesFor = (f) => {
    const names = new Set(f.folder_names);
    const hit = inventory?.items?.find((it) => it.locations?.some((l) => names.has(String(l.path).replace(/\/+$/, "").split("/").pop())));
    return hit ? hit.locations.map((l) => l.location_label) : [];
  };

  return (
    <>
      <p style={{ fontSize: 12, color: C.sub, marginBottom: 12 }}>
        Newest first. A full backup <b>can be restored</b> when every datafile is backed up, every backup piece still exists,
        a controlfile backup exists, and the archive logs since the backup started are available without gaps.
      </p>
      <div className="space-y-3">
        {catalog.full_backups.map((f) => {
          const copies = copiesFor(f);
          const isOpen = !!open[f.tag];
          return (
            <Card key={f.tag} style={{ borderColor: f.restorable ? (f.is_latest ? "rgba(22,163,74,0.45)" : C.line) : "rgba(220,38,38,0.35)" }}>
              <div className="flex items-start gap-4 p-4 flex-wrap">
                <div style={{ minWidth: 170 }}>
                  <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 700 }}>BACKUP DATE</div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: C.ink }}>{fmtLocal(f.start_time, { time: false })}</div>
                  <div style={{ fontSize: 11, color: C.faint }}>{f.start_time?.slice(11, 16)} – {f.end_time?.slice(11, 16)} WIB · {daysAgo(f.start_time)} days ago</div>
                </div>
                <div className="flex-1" style={{ minWidth: 240 }}>
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    {f.restorable
                      ? <Pill color={C.green}><CheckCircle2 size={11} />Restorable</Pill>
                      : <Pill color={C.red}><XCircle size={11} />Not restorable</Pill>}
                    {f.is_latest && <Pill color={C.blue}>Latest</Pill>}
                    <Pill color={C.sub}>{f.datafiles}/{f.datafiles_total} datafile</Pill>
                    <Pill color={C.sub}>{fmtBytes(f.size_bytes)}</Pill>
                    {f.controlfile_ok && <Pill color={C.sub}>+ controlfile</Pill>}
                    {(f.copies || []).map((loc) => <Pill key={loc} color={C.blue}>{loc === "synology" ? "Synology copy" : "On staging"}</Pill>)}
                    {f.restorable && !(f.copies || []).includes("synology") && <Pill color={C.amber} title="If the DB server fails, this backup is lost with it">Not on Synology yet</Pill>}
                  </div>
                  {f.restorable ? (
                    <div style={{ fontSize: 12, color: C.ink }}>
                      Can be recovered to any time from <b>{fmtLocal(f.recoverable_from)}</b> to <b>{fmtLocal(f.recoverable_until)}</b> WIB
                      <span style={{ color: C.faint }}> (archive log seq {f.start_seq}–{f.last_seq})</span>
                    </div>
                  ) : (
                    f.problems.map((p, i) => <div key={i} style={{ fontSize: 12, color: C.red }}>• {p}</div>)
                  )}
                  {(f.notes || []).map((n, i) => <div key={i} style={{ fontSize: 11.5, color: C.amber, marginTop: 2 }}>• {n}</div>)}
                  <div style={{ fontSize: 11, color: C.faint, marginTop: 4 }}>
                    Tag {f.tag} · {f.dirs.join(", ") || "location unknown"}
                    {f.synology_paths?.length > 0 && <> · Synology: {f.synology_paths.join(", ")}</>}
                    {copies.length > 0 && <> · Copies: {copies.join(", ")}</>}
                  </div>
                </div>
                <Button size="sm" variant="ghost" icon={isOpen ? ChevronUp : ChevronDown} onClick={() => setOpen((o) => ({ ...o, [f.tag]: !o[f.tag] }))}>
                  Restore commands
                </Button>
              </div>
              {isOpen && <RestoreScript f={f} stagingPath={catalog.staging_path} />}
            </Card>
          );
        })}
      </div>
    </>
  );
}

function RestoreScript({ f, stagingPath }) {
  const [copied, setCopied] = useState(false);
  const until = f.recoverable_until || f.end_time;
  const dir = f.restore_dir || f.dirs[0];
  const script = [
    "# REFERENCE — run on the target server (Dev / replacement server), NEVER on the running PROD.",
    "# 1. Startup nomount with the PROD pfile/spfile, then:",
    "rman target /",
    "",
    ...(f.restore_source === "synology" ? ["# The staging folder is gone — using the Synology copy (NFS mount)."] : []),
    `RESTORE CONTROLFILE FROM '<${dir || "folder_backup"}/CTL_...bkp>';`,
    "ALTER DATABASE MOUNT;",
    `CATALOG START WITH '${dir || "<folder_backup>"}/' NOPROMPT;`,
    `CATALOG START WITH '${stagingPath}/' NOPROMPT;`,
    "# If the archive logs needed are no longer on staging, also CATALOG the archive log folder on Synology.",
    "",
    "RUN {",
    `  SET UNTIL TIME "TO_DATE('${until}','YYYY-MM-DD HH24:MI:SS')";`,
    `  RESTORE DATABASE FROM TAG '${f.tag}';`,
    "  RECOVER DATABASE;",
    "}",
    "ALTER DATABASE OPEN RESETLOGS;",
  ].join("\n");

  const copy = async () => {
    try { await navigator.clipboard.writeText(script); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch (_) {}
  };

  return (
    <div className="px-4 pb-4">
      <div className="relative rounded-lg" style={{ background: "#0f172a" }}>
        <button type="button" onClick={copy} className="absolute flex items-center gap-1 rounded-md"
          style={{ top: 8, right: 8, background: "rgba(255,255,255,0.1)", color: "#e2e8f0", border: "none", fontSize: 10.5, padding: "3px 8px", cursor: "pointer" }}>
          <Copy size={11} />{copied ? "Copied" : "Copy"}
        </button>
        <pre style={{ color: "#e2e8f0", fontSize: 11, padding: 14, overflowX: "auto", whiteSpace: "pre" }}>{script}</pre>
      </div>
      <p style={{ fontSize: 11, color: C.faint, marginTop: 6 }}>
        Change the time in <code>SET UNTIL TIME</code> to recover to a point before an incident (e.g. before data was deleted). To test a restore to Dev, use the <b>Restore</b> tab.
      </p>
    </div>
  );
}

/* ─── Archive Log ────────────────────────────────── */

const PAGE = 100;

function LocationStatus({ locations }) {
  if (!locations) return null;
  return (
    <div className="flex gap-2 flex-wrap mb-3">
      {LOCS.map((l) => {
        const s = locations[l.id];
        const ok = s?.ok;
        return (
          <span key={l.id} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1"
            title={ok ? s.path : s?.error || "Not scanned"}
            style={{ fontSize: 11, background: ok ? "rgba(22,163,74,0.07)" : "rgba(217,119,6,0.08)", color: ok ? C.green : C.amber, fontWeight: 700 }}>
            {ok ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
            {l.long}
            <span style={{ color: C.faint, fontWeight: 500 }}>
              {ok ? (s.path || "") : (s?.error || "not scanned")}
              {ok && l.id === "synology" && s.writable === false ? " · read-only" : ""}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function ArchivelogView({ catalog, err, onChanged }) {
  const [filter, setFilter] = useState("all");
  const [locFilter, setLocFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState({});
  const [limit, setLimit] = useState(PAGE);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState(null);

  const logs = useMemo(() => catalog?.archivelogs || [], [catalog]);
  const byName = useMemo(() => Object.fromEntries(logs.map((a) => [a.name, a])), [logs]);

  // Drop selections that disappeared or became non-deletable after a rescan.
  useEffect(() => {
    setSelected((s) => Object.fromEntries(Object.entries(s).filter(([n, v]) => v && byName[n]?.deletable)));
  }, [byName]);

  const rows = useMemo(() => logs.filter((a) =>
    (filter === "all" || a.category === filter)
    && (locFilter === "all" || (locFilter === "archive_dest" ? a.on_disk : a.copies?.[locFilter]))
    && (!query || a.name.includes(query.trim()) || String(a.sequence).includes(query.trim()))
  ), [logs, filter, locFilter, query]);

  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!catalog) return <Empty>Reading the RMAN catalog…</Empty>;

  const sum = catalog.archivelog_summary;
  const chosen = Object.keys(selected).filter((n) => selected[n]).map((n) => byName[n]).filter(Boolean);
  const chosenBytes = chosen.reduce((t, a) => t + Object.values(a.copies || {}).reduce((x, c) => x + c.size_bytes, 0), 0);
  const visibleDeletable = rows.filter((a) => a.deletable);
  const allVisibleChecked = visibleDeletable.length > 0 && visibleDeletable.every((a) => selected[a.name]);

  const selectCategory = (cat) => {
    const next = {};
    logs.forEach((a) => { if (a.deletable && a.category === cat) next[a.name] = true; });
    setSelected(next);
  };
  const toggleVisible = (checked) => setSelected((s) => {
    const n = { ...s };
    visibleDeletable.forEach((a) => { n[a.name] = checked; });
    return n;
  });

  return (
    <>
      <LocationStatus locations={catalog.locations} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {["required", "optional", "obsolete"].map((k) => {
          const c = CATEGORY[k];
          const active = filter === k;
          return (
            <button key={k} type="button" onClick={() => setFilter(active ? "all" : k)} className="text-left rounded-xl p-4 transition-all"
              style={{ background: active ? c.bg : "#fff", border: `1px solid ${active ? c.color : C.line}`, cursor: "pointer" }}>
              <div className="flex items-center justify-between">
                <span style={{ fontSize: 11, fontWeight: 800, color: c.color }}>{c.label.toUpperCase()}</span>
                <span style={{ fontSize: 11, color: C.faint }}>{active ? "filter on" : "click to filter"}</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.ink, marginTop: 4 }}>{sum[k].count} sequence · {fmtBytes(sum[k].bytes)}</div>
              <div className="flex gap-3 flex-wrap" style={{ fontSize: 10.5, color: C.sub, marginTop: 3 }}>
                {LOCS.map((l) => (
                  <span key={l.id}>{l.label}: <b>{sum[k].by_location?.[l.id]?.count || 0}</b> ({fmtBytes(sum[k].by_location?.[l.id]?.bytes || 0)})</span>
                ))}
              </div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 4 }}>
                {k === "required" && "Needed by the latest full backup to recover up to now. Cannot be deleted from any location."}
                {k === "optional" && "Only for recovering to an earlier time with an older full backup. May be deleted with confirmation."}
                {k === "obsolete" && "Older than every restorable full backup — no longer needed."}
              </div>
            </button>
          );
        })}
      </div>
      {sum.unknown?.count > 0 && (
        <p className="flex items-start gap-1.5 mb-3" style={{ fontSize: 11.5, color: C.sub }}>
          <Info size={13} style={{ marginTop: 1, flexShrink: 0 }} />
          {sum.unknown.count} archive logs ({fmtBytes(sum.unknown.bytes)}) have a resetlogs id the PROD database does not know —
          probably from another database (DEV/TEST) on the same share/bucket. They cannot be deleted from this page.
        </p>
      )}

      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div className="flex items-center gap-1.5 rounded-lg px-2.5" style={{ border: `1px solid ${C.line}`, height: 32 }}>
          <Search size={13} color={C.faint} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search sequence / file name"
            style={{ border: "none", outline: "none", fontSize: 12, width: 180 }} />
        </div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12, height: 32, padding: "0 8px" }}>
          <option value="all">All statuses</option>
          <option value="required">Must keep</option>
          <option value="optional">Optional</option>
          <option value="obsolete">Safe to delete</option>
          <option value="unknown">Not from PROD</option>
        </select>
        <select value={locFilter} onChange={(e) => setLocFilter(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12, height: 32, padding: "0 8px" }}>
          <option value="all">All locations</option>
          {LOCS.map((l) => <option key={l.id} value={l.id}>On {l.label}</option>)}
          <option value="archive_dest">On /archive DB</option>
        </select>
        <Button size="sm" icon={CheckCircle2} onClick={() => selectCategory("obsolete")} disabled={!sum.obsolete.count}>Select all safe to delete</Button>
        {chosen.length > 0 && <Button size="sm" onClick={() => setSelected({})}>Clear selection</Button>}
        <div className="flex-1" />
        <Button variant="danger" icon={Trash2} disabled={!chosen.length} onClick={() => { setResult(null); setConfirming(true); }}>
          Delete selected {chosen.length ? `(${chosen.length} · ${fmtBytes(chosenBytes)})` : ""}
        </Button>
      </div>

      {result && (
        <div className="rounded-lg px-3 py-2 mb-3" style={{ background: "rgba(22,163,74,0.08)", fontSize: 12, color: C.ink }}>
          <b style={{ color: C.green }}>{result.deleted.length} copies deleted</b> ({fmtBytes(result.freed_bytes)} freed
          {result.by_location ? ` — ${LOCS.filter((l) => result.by_location[l.id]?.count).map((l) => `${l.label} ${result.by_location[l.id].count} file / ${fmtBytes(result.by_location[l.id].bytes)}`).join(", ")}` : ""}).
          {result.refused.length > 0 && (
            <div style={{ color: C.amber, marginTop: 4 }}>
              {result.refused.length} refused: {result.refused.slice(0, 5).map((r) => `${r.name}${r.location ? ` @${r.location}` : ""} (${r.reason})`).join("; ")}
              {result.refused.length > 5 ? "…" : ""}
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl overflow-x-auto" style={{ border: `1px solid ${C.line}` }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: C.soft, color: C.sub, fontWeight: 700 }}>
              <td className="px-3 py-2" style={{ width: 28 }}>
                <input type="checkbox" checked={allVisibleChecked} disabled={!visibleDeletable.length} onChange={(e) => toggleVisible(e.target.checked)}
                  title="Select every deletable row in this view" />
              </td>
              <td className="px-3 py-2">Seq</td>
              <td className="px-3 py-2">Redo period (WIB)</td>
              <td className="px-3 py-2">Size</td>
              <td className="px-3 py-2">Copies available</td>
              <td className="px-3 py-2">Status</td>
              <td className="px-3 py-2">Reason</td>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((a) => {
              const c = CATEGORY[a.category] || CATEGORY.unknown;
              return (
                <tr key={`${a.resetlogs_id}:${a.name}`} style={{ borderTop: `1px solid ${C.line}`, background: selected[a.name] ? "rgba(220,38,38,0.03)" : undefined }}>
                  <td className="px-3 py-2">
                    <input type="checkbox" disabled={!a.deletable} checked={!!selected[a.name]}
                      title={a.deletable ? "" : a.location === "archive_dest" ? "Only in the archive destination — managed by RMAN" : c.label}
                      onChange={(e) => setSelected((s) => ({ ...s, [a.name]: e.target.checked }))} />
                  </td>
                  <td className="px-3 py-2">
                    <div style={{ fontWeight: 800, color: C.ink }}>{a.sequence}</div>
                    <div style={{ color: C.faint, fontSize: 10 }}>{a.name}</div>
                  </td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>
                    {a.first_time ? <>{fmtLocal(a.first_time)}<div style={{ color: C.faint, fontSize: 10 }}>to {fmtLocal(a.end_time)}</div></>
                      : <span style={{ color: C.faint }}>file: {fmtIso(a.modified_at)}</span>}
                  </td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>{fmtBytes(a.size_bytes)}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1 flex-wrap">
                      {LOCS.map((l) => a.copies?.[l.id] && (
                        <Pill key={l.id} color={l.id === "staging" ? C.sub : C.blue}
                          title={a.copies[l.id].refs?.join("\n")}>
                          {l.label}{a.copies[l.id].count > 1 ? ` ×${a.copies[l.id].count}` : ""}
                        </Pill>
                      ))}
                      {a.on_disk && <Pill color={C.sub}>/archive DB</Pill>}
                      {a.in_backupset && <Pill color={C.blue} title={a.backupset_tags.join(", ")}>RMAN backup</Pill>}
                    </div>
                  </td>
                  <td className="px-3 py-2"><Pill color={c.color} bg={c.bg}>{c.short}</Pill></td>
                  <td className="px-3 py-2" style={{ color: C.sub, fontSize: 11, minWidth: 260 }}>{a.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!rows.length && <Empty>No archive logs match the filter.</Empty>}
      </div>
      {rows.length > limit && (
        <div className="flex justify-center mt-3">
          <Button size="sm" onClick={() => setLimit((l) => l + PAGE)}>Show {Math.min(PAGE, rows.length - limit)} more (of {rows.length - limit})</Button>
        </div>
      )}

      {confirming && (
        <DeleteArchivelogModal chosen={chosen} locations={catalog.locations}
          onClose={() => setConfirming(false)}
          onDone={(res) => { setConfirming(false); setSelected({}); setResult(res); onChanged(); }} />
      )}
    </>
  );
}

function DeleteArchivelogModal({ chosen, locations, onClose, onDone }) {
  // Per location: how many of the chosen logs have a copy there, and its size.
  const perLoc = useMemo(() => Object.fromEntries(LOCS.map((l) => {
    const copies = chosen.map((a) => a.copies?.[l.id]).filter(Boolean);
    return [l.id, { files: copies.reduce((t, c) => t + c.count, 0), bytes: copies.reduce((t, c) => t + c.size_bytes, 0) }];
  })), [chosen]);
  const usable = (id) => perLoc[id].files > 0 && locations?.[id]?.ok && !(id === "synology" && locations.synology.writable === false);

  const [locs, setLocs] = useState(() => Object.fromEntries(LOCS.map((l) => [l.id, usable(l.id)])));
  const [ack, setAck] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const optional = chosen.filter((a) => a.category === "optional");
  const seqs = chosen.map((a) => a.sequence).sort((x, y) => x - y);
  const picked = LOCS.filter((l) => locs[l.id] && usable(l.id)).map((l) => l.id);
  const pickedBytes = picked.reduce((t, id) => t + perLoc[id].bytes, 0);
  const ok = typed === "DELETE" && picked.length > 0 && (!optional.length || ack);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res = await ebsBackupApi.deleteArchivelogs({ names: chosen.map((a) => a.name), locations: picked, allow_optional: optional.length > 0 });
      onDone(res);
    } catch (e) {
      setError(errMsg(e, "Delete failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Delete archive logs" onClose={busy ? undefined : onClose}
      footer={<>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="danger" icon={busy ? Loader2 : Trash2} disabled={!ok || busy} onClick={submit}>{busy ? "Deleting…" : `Delete (${fmtBytes(pickedBytes)})`}</Button>
      </>}>
      <p>
        <b>{chosen.length} archive logs</b> selected, sequence <b>{seqs[0]}</b>
        {seqs.length > 1 && <> to <b>{seqs[seqs.length - 1]}</b></>}. Choose the locations to delete the copies from:
      </p>

      <div className="rounded-lg mt-3" style={{ border: `1px solid ${C.line}` }}>
        {LOCS.map((l) => {
          const can = usable(l.id);
          const why = !perLoc[l.id].files ? "no copy there" : !locations?.[l.id]?.ok ? "location unreachable"
            : l.id === "synology" && locations.synology.writable === false ? "read-only share from the DB server" : "";
          return (
            <label key={l.id} className="flex items-center gap-2 px-3 py-2" style={{ fontSize: 12, borderTop: l.id === "staging" ? "none" : `1px solid ${C.line}`, opacity: can ? 1 : 0.5 }}>
              <input type="checkbox" disabled={!can || busy} checked={can && !!locs[l.id]} onChange={(e) => setLocs((s) => ({ ...s, [l.id]: e.target.checked }))} />
              <span style={{ fontWeight: 700, width: 150 }}>{l.long}</span>
              <span style={{ color: C.sub }}>{perLoc[l.id].files} file · {fmtBytes(perLoc[l.id].bytes)}</span>
              {why && <span style={{ color: C.faint, marginLeft: "auto" }}>{why}</span>}
            </label>
          );
        })}
      </div>
      <p style={{ color: C.sub, marginTop: 8 }}>
        The server re-checks every file before deleting — any that turn out to be still required are refused automatically.
        Files in the database's archive destination (/archive DB) are not touched; RMAN manages them.
      </p>

      {optional.length > 0 && (
        <div className="rounded-lg p-3 mt-3" style={{ background: "rgba(217,119,6,0.08)", border: "1px solid rgba(217,119,6,0.3)" }}>
          <p style={{ fontWeight: 700, color: C.amber }}>
            <AlertTriangle size={13} style={{ display: "inline", marginRight: 4, verticalAlign: -2 }} />
            {optional.length} archive logs marked Optional
          </p>
          <p style={{ fontSize: 12, marginTop: 4 }}>
            If deleted from every location, older full backups can only be recovered up to the sequence before the deleted files.
            Recovery from the latest full backup is not affected.
          </p>
          <label className="flex items-center gap-2 mt-2" style={{ fontSize: 12 }}>
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand and still want to delete.
          </label>
        </div>
      )}

      <div className="mt-3">
        <label style={{ fontSize: 11, fontWeight: 700, color: C.sub, display: "block", marginBottom: 4 }}>Type <b>DELETE</b> to confirm</label>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="DELETE"
          style={{ width: 200, padding: "7px 10px", borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.line}` }} />
      </div>
      {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
    </Modal>
  );
}

/* ─── All Backup Files (inventory) ───────────────── */

const REC = {
  delete: { label: "Delete", color: C.red },
  move_offsite: { label: "Copy offsite", color: C.amber },
  review: { label: "Review", color: C.sub },
  keep: { label: "Keep", color: C.green },
};

function FilesView({ inventory, err, catalog, onChanged }) {
  const [sort, setSort] = useState({ key: "date", dir: "desc" });
  const [typeFilter, setTypeFilter] = useState("all");
  const [selected, setSelected] = useState({});
  const [confirming, setConfirming] = useState(false);

  // Folder name -> RMAN full backup it holds (from the catalog).
  const fullByFolder = useMemo(() => {
    const m = {};
    catalog?.full_backups?.forEach((f) => f.folder_names.forEach((n) => { m[n] = f; }));
    return m;
  }, [catalog]);

  const items = useMemo(() => {
    const list = (inventory?.items || []).map((it) => {
      const folders = it.locations.map((l) => String(l.path).replace(/\/+$/, "").split("/").pop());
      const rman = folders.map((n) => fullByFolder[n]).find(Boolean) || null;
      const key = `${it.locations[0].location}::${it.locations[0].server_id}::${it.locations[0].path}`;
      return { ...it, rman, key, sortDate: it.backup_at || (it.date ? `${it.date}T00:00:00` : "") };
    });
    const val = (it) => ({ date: it.sortDate, size: it.size_bytes, name: it.name.toLowerCase(), type: it.type_label })[sort.key];
    return list
      .filter((it) => typeFilter === "all" || it.type === typeFilter)
      .sort((a, b) => {
        const x = val(a), y = val(b);
        if (x === y) return 0;
        if (x === "" || x == null) return 1;
        if (y === "" || y == null) return -1;
        return (x < y ? -1 : 1) * (sort.dir === "asc" ? 1 : -1);
      });
  }, [inventory, fullByFolder, sort, typeFilter]);

  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!inventory) return <Empty>Scanning backup folders on the DB server, MinIO and Synology…</Empty>;

  const types = [...new Map(inventory.items.map((it) => [it.type, it.type_label])).entries()];
  // Never offer to delete the folder holding the newest restorable full backup.
  const protectedRow = (it) => it.rman?.is_latest;
  const chosen = items.filter((it) => selected[it.key]);

  const header = (key, label) => {
    const active = sort.key === key;
    const Icon = active && sort.dir === "asc" ? ArrowUpNarrowWide : ArrowDownWideNarrow;
    return (
      <button type="button" onClick={() => setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }))}
        className="inline-flex items-center gap-1" style={{ background: "none", border: "none", cursor: "pointer", color: active ? C.blue : C.sub, fontWeight: 700, fontSize: 12 }}>
        {label}<Icon size={11} style={{ opacity: active ? 1 : 0.35 }} />
      </button>
    );
  };

  const doDelete = async () => {
    for (const it of chosen) {
      for (const l of it.locations) {
        try { await ebsBackupApi.deleteInventoryItem({ location: l.location, server_id: Number(l.server_id), path: l.path }); } catch (_) {}
      }
    }
    setSelected({}); setConfirming(false); onChanged();
  };

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Total backup size" value={fmtBytes(inventory.total_bytes)} icon={HardDrive} />
        <Stat label="Recommended to delete" value={fmtBytes(inventory.reclaimable_bytes)} color={C.green} icon={Trash2} />
        <Stat label="Backup folders" value={inventory.items.length} icon={FolderOpen} />
        <Stat label="Latest backup" value={fmtIso(items.find((i) => i.sortDate)?.sortDate)} icon={Clock} />
      </div>

      <div className="flex items-center gap-2 flex-wrap mb-3">
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12, height: 32, padding: "0 8px" }}>
          <option value="all">All backup types</option>
          {types.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <span style={{ fontSize: 11.5, color: C.faint }}>Click a column header to sort. Default: newest date first.</span>
        <div className="flex-1" />
        <Button variant="danger" icon={Trash2} disabled={!chosen.length} onClick={() => setConfirming(true)}>
          Delete selected {chosen.length ? `(${chosen.length})` : ""}
        </Button>
      </div>

      <div className="rounded-xl overflow-x-auto" style={{ border: `1px solid ${C.line}` }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: C.soft }}>
              <td className="px-3 py-2" style={{ width: 28 }}></td>
              <td className="px-3 py-2">{header("date", "Backup Date")}</td>
              <td className="px-3 py-2">{header("name", "Name")}</td>
              <td className="px-3 py-2">{header("type", "Type")}</td>
              <td className="px-3 py-2">{header("size", "Size")}</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Location</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Restorable?</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Recommendation</td>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => {
              const rec = REC[it.recommendation] || REC.review;
              const canSelect = it.recommendation === "delete" && !protectedRow(it);
              return (
                <tr key={it.key} style={{ borderTop: `1px solid ${C.line}` }}>
                  <td className="px-3 py-2">
                    {canSelect && <input type="checkbox" checked={!!selected[it.key]} onChange={(e) => setSelected((s) => ({ ...s, [it.key]: e.target.checked }))} />}
                  </td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>
                    <div style={{ fontWeight: 700, color: C.ink }}>{fmtIso(it.sortDate)}</div>
                    <div style={{ color: C.faint, fontSize: 10 }}>{it.age_days != null ? `${it.age_days} days ago` : ""}</div>
                  </td>
                  <td className="px-3 py-2" style={{ color: C.ink, fontWeight: 600 }}>{it.name}</td>
                  <td className="px-3 py-2">{it.type_label}</td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>{fmtBytes(it.size_bytes)}</td>
                  <td className="px-3 py-2">{it.locations.map((l) => l.location_label).join(", ")}</td>
                  <td className="px-3 py-2">
                    {it.rman ? (
                      it.rman.restorable ? (
                        <div>
                          <Pill color={C.green}><CheckCircle2 size={11} />Yes{it.rman.is_latest ? " · latest" : ""}</Pill>
                          <div style={{ color: C.faint, fontSize: 10, marginTop: 2 }}>to {fmtLocal(it.rman.recoverable_until)}</div>
                        </div>
                      ) : <Pill color={C.red} title={it.rman.problems.join(" ")}><XCircle size={11} />No</Pill>
                    ) : it.type === "rman_full" ? (
                      <Pill color={C.faint} title="This folder is not recorded in the control file — it needs a manual CATALOG before it can be used">Not in RMAN</Pill>
                    ) : <span style={{ color: C.faint }}>—</span>}
                  </td>
                  <td className="px-3 py-2" style={{ minWidth: 220 }}>
                    <span style={{ color: rec.color, fontWeight: 700 }}>{rec.label}</span>
                    <div style={{ color: C.faint, fontSize: 10 }}>{protectedRow(it) ? "Latest restorable full backup — protected." : it.reason}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!items.length && <Empty>No backup folders.</Empty>}
      </div>

      {confirming && (
        <ConfirmTyped title="Delete backup folders" onClose={() => setConfirming(false)} onConfirm={doDelete}
          body={<>
            <p>{chosen.length} folders will be permanently deleted from all their locations ({fmtBytes(chosen.reduce((t, i) => t + i.size_bytes, 0))}):</p>
            <ul style={{ margin: "8px 0 0 16px", listStyle: "disc", color: C.sub }}>
              {chosen.slice(0, 8).map((i) => <li key={i.key}>{i.name} — {fmtIso(i.sortDate)}</li>)}
              {chosen.length > 8 && <li>…and {chosen.length - 8} more</li>}
            </ul>
            {chosen.some((i) => i.rman?.restorable) && (
              <p style={{ color: C.amber, marginTop: 8 }}>Some folders hold full backups that can still be restored. The recovery window will shrink once they are deleted.</p>
            )}
          </>} />
      )}
    </>
  );
}

function ConfirmTyped({ title, body, onClose, onConfirm }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } };
  return (
    <Modal title={title} onClose={busy ? undefined : onClose}
      footer={<>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="danger" icon={busy ? Loader2 : Trash2} disabled={typed !== "DELETE" || busy} onClick={run}>{busy ? "Deleting…" : "Delete"}</Button>
      </>}>
      {body}
      <div className="mt-3">
        <label style={{ fontSize: 11, fontWeight: 700, color: C.sub, display: "block", marginBottom: 4 }}>Type <b>DELETE</b> to confirm</label>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="DELETE"
          style={{ width: 200, padding: "7px 10px", borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.line}` }} />
      </div>
    </Modal>
  );
}

/* ─── Guide ──────────────────────────────────────── */

function GuideView({ catalog }) {
  const s = catalog?.summary;
  const Section = ({ title, children }) => (
    <Card style={{ padding: 16 }}>
      <p className="flex items-center gap-1.5" style={{ fontSize: 13, fontWeight: 800, color: C.ink, marginBottom: 6 }}><Info size={14} color={C.blue} />{title}</p>
      <div style={{ fontSize: 12.5, color: "#334155", lineHeight: 1.65 }}>{children}</div>
    </Card>
  );
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <Section title="How does Oracle recovery work?">
        <p>An <b>RMAN full backup (online)</b> is a copy of every datafile at the time the backup runs. Because the database keeps running during the backup, that copy is not yet consistent.</p>
        <p style={{ marginTop: 6 }}><b>Archive logs</b> record every change after that. During recovery, RMAN restores the full backup and then "replays" the archive logs one by one, so the database can be recovered to <b>any second</b> up to the last archive log available.</p>
        <p style={{ marginTop: 6 }}>The condition: archive logs must be <b>continuous, without gaps</b>, from the sequence at which the full backup started. One missing sequence = recovery stops there.</p>
      </Section>
      <Section title="When can archive logs be deleted?">
        <ul style={{ listStyle: "disc", paddingLeft: 18 }}>
          <li><b style={{ color: C.red }}>Must keep</b> — sequences since the latest full backup. This is the only way to recover up to the present.</li>
          <li><b style={{ color: C.amber }}>Optional</b> — only used to recover to an earlier date with an older full backup.</li>
          <li><b style={{ color: C.green }}>Safe to delete</b> — older than every remaining full backup; no backup can use them.</li>
        </ul>
        <p style={{ marginTop: 6 }}>When an older full backup is deleted, its "optional" archive logs automatically become "safe to delete" on the next scan.</p>
      </Section>
      <Section title="Recommended retention policy">
        <ul style={{ listStyle: "disc", paddingLeft: 18 }}>
          <li>A <b>weekly</b> online full backup to staging + a Synology copy; keep at least the last <b>2</b> full backups.</li>
          <li>Archive logs are copied to staging, MinIO and Synology <b>every day</b>. The three are equivalent copies — one intact copy is enough for recovery.</li>
          <li>Delete archive logs marked <b>Safe to delete</b> from all three locations once a new full backup has succeeded and been copied to Synology.</li>          <li>Test a restore to Dev at least <b>once a month</b> (Restore tab) — a backup that has never been tested is not proven.</li>
        </ul>
      </Section>
      <Section title="Current state">
        {!s ? <p>Loading…</p> : (
          <>
            <p>{s.message}</p>
            <p style={{ marginTop: 6 }}>Current sequence: <b>{catalog.db.current_sequence ?? "—"}</b> · latest archive log: <b>{catalog.db.latest_archived_sequence ?? "—"}</b> · datafiles: <b>{catalog.db.datafile_count}</b>.</p>
            <p style={{ marginTop: 6, color: C.sub }}>Archive logs still in the database's archive destination (/archive) are deleted automatically by RMAN after 7 days (cron 05:00), after being copied to staging by the 01:00 cron.</p>
          </>
        )}
      </Section>
    </div>
  );
}
