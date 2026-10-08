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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

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
    return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (_) { return iso; }
}

function fmtMinutes(min) {
  if (min === null || min === undefined) return "—";
  if (min < 60) return `${min} menit`;
  if (min < 1440) return `${Math.floor(min / 60)} jam ${min % 60} m`;
  return `${Math.floor(min / 1440)} hari ${Math.floor((min % 1440) / 60)} jam`;
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
  required: { label: "Wajib disimpan", short: "Wajib", color: C.red, bg: "rgba(220,38,38,0.08)" },
  optional: { label: "Opsional (PITR lama)", short: "Opsional", color: C.amber, bg: "rgba(217,119,6,0.1)" },
  obsolete: { label: "Aman dihapus", short: "Aman dihapus", color: C.green, bg: "rgba(22,163,74,0.1)" },
};

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
  { id: "summary", label: "Ringkasan", icon: ShieldCheck },
  { id: "fulls", label: "Full Backup (RMAN)", icon: Database },
  { id: "archivelog", label: "Archive Log", icon: FileArchive },
  { id: "files", label: "Semua File Backup", icon: FolderOpen },
  { id: "guide", label: "Panduan", icon: BookOpen },
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
    catch (e) { setCatalogErr(errMsg(e, "Gagal membaca katalog RMAN")); }
    finally { setCatalogLoading(false); }
  }, []);

  const loadInventory = useCallback(async () => {
    setInventoryLoading(true); setInventoryErr(null);
    try { setInventory(await ebsBackupApi.scanInventory()); }
    catch (e) { setInventoryErr(errMsg(e, "Gagal memindai file backup")); }
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
            Status recovery dibaca langsung dari catatan RMAN (control file) PROD — bukan tebakan dari nama file.
            {catalog?.generated_at && <> Terakhir dipindai {fmtIso(catalog.generated_at + "Z")}.</>}
          </p>
        </div>
        <Button icon={loading ? Loader2 : RefreshCw} onClick={refreshAll} disabled={loading}>{loading ? "Memindai…" : "Pindai Ulang"}</Button>
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

/* ─── Ringkasan ──────────────────────────────────── */

function SummaryView({ catalog, err, goTo }) {
  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!catalog) return <Empty>Membaca katalog RMAN…</Empty>;
  const s = catalog.summary;
  const cfg = {
    green: { icon: ShieldCheck, color: C.green, title: "SIAP RESTORE" },
    amber: { icon: ShieldAlert, color: C.amber, title: "PERLU PERHATIAN" },
    red: { icon: ShieldX, color: C.red, title: "TIDAK SIAP RESTORE" },
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
        <Stat icon={Clock} label="Bisa dipulihkan sampai" value={fmtLocal(s.recoverable_until)} sub="titik terbaru (WIB)" color={C.green} />
        <Stat icon={Clock} label="Titik terlama" value={fmtLocal(s.oldest_point)} sub="dengan full backup tertua" />
        <Stat icon={Database} label="Full backup siap restore" value={`${s.restorable_count} / ${catalog.full_backups.length}`}
          sub={latest ? `terbaru ${daysAgo(latest.start_time)} hari lalu` : "—"} color={s.restorable_count ? C.ink : C.red} />
        <Stat icon={AlertTriangle} label="Potensi data hilang (RPO)" value={fmtMinutes(s.rpo_minutes)}
          sub="jika server hilang total saat ini" color={s.rpo_minutes > 1440 ? C.red : s.rpo_minutes > 360 ? C.amber : C.ink} />
        <Stat icon={HardDrive} label="Archive log aman dihapus" value={fmtBytes(obs.bytes)} sub={`${obs.count} file di staging`} color={C.green} />
      </div>

      <RecoveryTimeline catalog={catalog} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
        <QuickLink onClick={() => goTo("fulls")} icon={Database} title="Lihat full backup"
          text="Backup mana yang bisa di-restore, sampai kapan, dan perintah RMAN-nya." />
        <QuickLink onClick={() => goTo("archivelog")} icon={FileArchive} title="Kelola archive log"
          text={`${obs.count} file (${fmtBytes(obs.bytes)}) sudah tidak dibutuhkan backup mana pun.`} />
        <QuickLink onClick={() => goTo("guide")} icon={BookOpen} title="Cara kerja recovery"
          text="Penjelasan singkat full backup + archive log dan kebijakan retensi." />
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
        <p style={{ fontSize: 12, fontWeight: 800, color: C.ink }}>Jendela recovery (point-in-time)</p>
        <p style={{ fontSize: 11, color: C.faint }}>Bar hijau = rentang waktu yang bisa dipulihkan dengan backup tersebut</p>
      </div>
      <div className="space-y-3">
        {fulls.map((f) => {
          const left = pct(f.start_time), right = pct(f.recoverable_until);
          return (
            <div key={f.tag} className="flex items-center gap-3">
              <div style={{ width: 150, flexShrink: 0, fontSize: 11.5 }}>
                <div style={{ fontWeight: 700, color: C.ink }}>{fmtLocal(f.start_time, { time: false })}</div>
                <div style={{ color: C.faint, fontSize: 10.5 }}>{f.is_latest ? "Full backup terbaru" : "Full backup lama"}</div>
              </div>
              <div className="relative flex-1 rounded-full" style={{ height: 14, background: "#eef2f7" }}>
                <div className="absolute rounded-full" title={`Restore + recover: ${fmtLocal(f.recoverable_from)} → ${fmtLocal(f.recoverable_until)}`}
                  style={{ left: `${left}%`, width: `${Math.max(right - left, 0.8)}%`, top: 0, bottom: 0, background: f.is_latest ? C.green : "rgba(22,163,74,0.45)" }} />
                <div className="absolute" title="Full backup diambil" style={{ left: `calc(${left}% - 1px)`, top: -3, bottom: -3, width: 3, borderRadius: 2, background: C.blue }} />
              </div>
              <div style={{ width: 130, flexShrink: 0, fontSize: 11, color: C.sub, textAlign: "right" }}>s/d {fmtLocal(f.recoverable_until)}</div>
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
  if (!catalog) return <Empty>Membaca katalog RMAN…</Empty>;
  if (!catalog.full_backups.length) return <Empty>Belum ada full backup RMAN yang tercatat di control file.</Empty>;

  // Offsite copies come from the inventory scan, matched by folder name.
  const copiesFor = (f) => {
    const names = new Set(f.folder_names);
    const hit = inventory?.items?.find((it) => it.locations?.some((l) => names.has(String(l.path).replace(/\/+$/, "").split("/").pop())));
    return hit ? hit.locations.map((l) => l.location_label) : [];
  };

  return (
    <>
      <p style={{ fontSize: 12, color: C.sub, marginBottom: 12 }}>
        Diurutkan dari yang terbaru. Sebuah full backup <b>bisa di-restore</b> bila semua datafile ter-backup, semua backup piece masih ada,
        ada backup controlfile, dan archive log sejak backup dimulai tersedia tanpa celah.
      </p>
      <div className="space-y-3">
        {catalog.full_backups.map((f) => {
          const copies = copiesFor(f);
          const isOpen = !!open[f.tag];
          return (
            <Card key={f.tag} style={{ borderColor: f.restorable ? (f.is_latest ? "rgba(22,163,74,0.45)" : C.line) : "rgba(220,38,38,0.35)" }}>
              <div className="flex items-start gap-4 p-4 flex-wrap">
                <div style={{ minWidth: 170 }}>
                  <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 700 }}>TANGGAL BACKUP</div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: C.ink }}>{fmtLocal(f.start_time, { time: false })}</div>
                  <div style={{ fontSize: 11, color: C.faint }}>{f.start_time?.slice(11, 16)} – {f.end_time?.slice(11, 16)} WIB · {daysAgo(f.start_time)} hari lalu</div>
                </div>
                <div className="flex-1" style={{ minWidth: 240 }}>
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    {f.restorable
                      ? <Pill color={C.green}><CheckCircle2 size={11} />Bisa di-restore</Pill>
                      : <Pill color={C.red}><XCircle size={11} />Tidak bisa di-restore</Pill>}
                    {f.is_latest && <Pill color={C.blue}>Terbaru</Pill>}
                    <Pill color={C.sub}>{f.datafiles}/{f.datafiles_total} datafile</Pill>
                    <Pill color={C.sub}>{fmtBytes(f.size_bytes)}</Pill>
                    {f.controlfile_ok && <Pill color={C.sub}>+ controlfile</Pill>}
                  </div>
                  {f.restorable ? (
                    <div style={{ fontSize: 12, color: C.ink }}>
                      Bisa dipulihkan ke waktu mana pun dari <b>{fmtLocal(f.recoverable_from)}</b> sampai <b>{fmtLocal(f.recoverable_until)}</b> WIB
                      <span style={{ color: C.faint }}> (archive log seq {f.start_seq}–{f.last_seq})</span>
                    </div>
                  ) : (
                    f.problems.map((p, i) => <div key={i} style={{ fontSize: 12, color: C.red }}>• {p}</div>)
                  )}
                  <div style={{ fontSize: 11, color: C.faint, marginTop: 4 }}>
                    Tag {f.tag} · {f.dirs.join(", ") || "lokasi tidak diketahui"}
                    {copies.length > 0 && <> · Salinan: {copies.join(", ")}</>}
                  </div>
                </div>
                <Button size="sm" variant="ghost" icon={isOpen ? ChevronUp : ChevronDown} onClick={() => setOpen((o) => ({ ...o, [f.tag]: !o[f.tag] }))}>
                  Perintah restore
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
  const script = [
    "# REFERENSI — jalankan di server target (Dev / server pengganti), JANGAN di PROD yang sedang berjalan.",
    "# 1. Startup nomount dengan pfile/spfile PROD, lalu:",
    "rman target /",
    "",
    `RESTORE CONTROLFILE FROM '<${f.dirs[0] || "folder_backup"}/CTL_...bkp>';`,
    "ALTER DATABASE MOUNT;",
    `CATALOG START WITH '${f.dirs[0] || "<folder_backup>"}/' NOPROMPT;`,
    `CATALOG START WITH '${stagingPath}/' NOPROMPT;`,
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
          <Copy size={11} />{copied ? "Tersalin" : "Salin"}
        </button>
        <pre style={{ color: "#e2e8f0", fontSize: 11, padding: 14, overflowX: "auto", whiteSpace: "pre" }}>{script}</pre>
      </div>
      <p style={{ fontSize: 11, color: C.faint, marginTop: 6 }}>
        Ganti waktu di <code>SET UNTIL TIME</code> untuk memulihkan ke titik sebelum kejadian (mis. sebelum data terhapus). Untuk uji restore ke Dev, gunakan tab <b>Restore</b>.
      </p>
    </div>
  );
}

/* ─── Archive Log ────────────────────────────────── */

const PAGE = 100;

function ArchivelogView({ catalog, err, onChanged }) {
  const [filter, setFilter] = useState("all");
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
    && (!query || a.name.includes(query.trim()) || String(a.sequence).includes(query.trim()))
  ), [logs, filter, query]);

  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!catalog) return <Empty>Membaca katalog RMAN…</Empty>;

  const sum = catalog.archivelog_summary;
  const chosen = Object.keys(selected).filter((n) => selected[n]).map((n) => byName[n]).filter(Boolean);
  const chosenBytes = chosen.reduce((t, a) => t + a.size_bytes, 0);
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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {["required", "optional", "obsolete"].map((k) => {
          const c = CATEGORY[k];
          const active = filter === k;
          return (
            <button key={k} type="button" onClick={() => setFilter(active ? "all" : k)} className="text-left rounded-xl p-4 transition-all"
              style={{ background: active ? c.bg : "#fff", border: `1px solid ${active ? c.color : C.line}`, cursor: "pointer" }}>
              <div className="flex items-center justify-between">
                <span style={{ fontSize: 11, fontWeight: 800, color: c.color }}>{c.label.toUpperCase()}</span>
                <span style={{ fontSize: 11, color: C.faint }}>{active ? "filter aktif" : "klik untuk filter"}</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.ink, marginTop: 4 }}>{sum[k].count} file · {fmtBytes(sum[k].bytes)}</div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                {k === "required" && "Dibutuhkan full backup terbaru untuk recovery sampai sekarang. Tidak bisa dihapus."}
                {k === "optional" && "Hanya untuk recovery ke masa lalu memakai full backup lama. Boleh dihapus dengan konfirmasi."}
                {k === "obsolete" && "Lebih tua dari semua full backup yang ada — tidak dibutuhkan lagi."}
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div className="flex items-center gap-1.5 rounded-lg px-2.5" style={{ border: `1px solid ${C.line}`, height: 32 }}>
          <Search size={13} color={C.faint} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari sequence / nama file"
            style={{ border: "none", outline: "none", fontSize: 12, width: 180 }} />
        </div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12, height: 32, padding: "0 8px" }}>
          <option value="all">Semua status</option>
          <option value="required">Wajib disimpan</option>
          <option value="optional">Opsional</option>
          <option value="obsolete">Aman dihapus</option>
        </select>
        <Button size="sm" icon={CheckCircle2} onClick={() => selectCategory("obsolete")} disabled={!sum.obsolete.count}>Pilih semua yang aman dihapus</Button>
        {chosen.length > 0 && <Button size="sm" onClick={() => setSelected({})}>Batal pilih</Button>}
        <div className="flex-1" />
        <Button variant="danger" icon={Trash2} disabled={!chosen.length} onClick={() => { setResult(null); setConfirming(true); }}>
          Hapus terpilih {chosen.length ? `(${chosen.length} · ${fmtBytes(chosenBytes)})` : ""}
        </Button>
      </div>

      {result && (
        <div className="rounded-lg px-3 py-2 mb-3" style={{ background: "rgba(22,163,74,0.08)", fontSize: 12, color: C.ink }}>
          <b style={{ color: C.green }}>{result.deleted.length} file dihapus</b> ({fmtBytes(result.freed_bytes)} dibebaskan
          {result.minio_removed ? `, ${result.minio_removed} salinan MinIO ikut dihapus` : ""}).
          {result.refused.length > 0 && (
            <div style={{ color: C.amber, marginTop: 4 }}>
              {result.refused.length} file ditolak: {result.refused.slice(0, 5).map((r) => `${r.name} (${r.reason})`).join("; ")}
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
                  title="Pilih semua baris yang bisa dihapus di tampilan ini" />
              </td>
              <td className="px-3 py-2">Seq</td>
              <td className="px-3 py-2">Periode redo (WIB)</td>
              <td className="px-3 py-2">Ukuran</td>
              <td className="px-3 py-2">Salinan tersedia</td>
              <td className="px-3 py-2">Status</td>
              <td className="px-3 py-2">Alasan</td>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((a) => {
              const c = CATEGORY[a.category];
              return (
                <tr key={`${a.location}:${a.name}`} style={{ borderTop: `1px solid ${C.line}`, background: selected[a.name] ? "rgba(220,38,38,0.03)" : undefined }}>
                  <td className="px-3 py-2">
                    <input type="checkbox" disabled={!a.deletable} checked={!!selected[a.name]}
                      title={a.deletable ? "" : a.location === "archive_dest" ? "Di archive destination — dikelola RMAN" : "Wajib disimpan"}
                      onChange={(e) => setSelected((s) => ({ ...s, [a.name]: e.target.checked }))} />
                  </td>
                  <td className="px-3 py-2">
                    <div style={{ fontWeight: 800, color: C.ink }}>{a.sequence}</div>
                    <div style={{ color: C.faint, fontSize: 10 }}>{a.name}</div>
                  </td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>
                    {a.first_time ? <>{fmtLocal(a.first_time)}<div style={{ color: C.faint, fontSize: 10 }}>s/d {fmtLocal(a.end_time)}</div></>
                      : <span style={{ color: C.faint }}>file: {fmtIso(a.modified_at)}</span>}
                  </td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>{fmtBytes(a.size_bytes)}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1 flex-wrap">
                      {a.in_staging && <Pill color={C.sub}>Staging</Pill>}
                      {a.on_disk && <Pill color={C.sub}>/archive DB</Pill>}
                      {a.in_backupset && <Pill color={C.blue} title={a.backupset_tags.join(", ")}>RMAN backup</Pill>}
                      {a.in_minio && <Pill color={C.blue}>MinIO</Pill>}
                    </div>
                  </td>
                  <td className="px-3 py-2"><Pill color={c.color} bg={c.bg}>{c.short}</Pill></td>
                  <td className="px-3 py-2" style={{ color: C.sub, fontSize: 11, minWidth: 260 }}>{a.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!rows.length && <Empty>Tidak ada archive log yang cocok dengan filter.</Empty>}
      </div>
      {rows.length > limit && (
        <div className="flex justify-center mt-3">
          <Button size="sm" onClick={() => setLimit((l) => l + PAGE)}>Tampilkan {Math.min(PAGE, rows.length - limit)} lagi (dari {rows.length - limit})</Button>
        </div>
      )}

      {confirming && (
        <DeleteArchivelogModal chosen={chosen} chosenBytes={chosenBytes}
          onClose={() => setConfirming(false)}
          onDone={(res) => { setConfirming(false); setSelected({}); setResult(res); onChanged(); }} />
      )}
    </>
  );
}

function DeleteArchivelogModal({ chosen, chosenBytes, onClose, onDone }) {
  const [ack, setAck] = useState(false);
  const [minio, setMinio] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const optional = chosen.filter((a) => a.category === "optional");
  const seqs = chosen.map((a) => a.sequence).sort((x, y) => x - y);
  const ok = typed === "HAPUS" && (!optional.length || ack);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res = await ebsBackupApi.deleteArchivelogs({ names: chosen.map((a) => a.name), allow_optional: optional.length > 0, include_minio: minio });
      onDone(res);
    } catch (e) {
      setError(errMsg(e, "Gagal menghapus"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Hapus archive log dari staging" onClose={busy ? undefined : onClose}
      footer={<>
        <Button onClick={onClose} disabled={busy}>Batal</Button>
        <Button variant="danger" icon={busy ? Loader2 : Trash2} disabled={!ok || busy} onClick={submit}>{busy ? "Menghapus…" : `Hapus ${chosen.length} file`}</Button>
      </>}>
      <p>
        Anda akan menghapus <b>{chosen.length} file</b> ({fmtBytes(chosenBytes)}), sequence <b>{seqs[0]}</b>
        {seqs.length > 1 && <> s/d <b>{seqs[seqs.length - 1]}</b></>}, dari folder staging di server DB.
      </p>
      <p style={{ color: C.sub, marginTop: 6 }}>
        Server akan memeriksa ulang setiap file sebelum menghapus — file yang ternyata masih wajib disimpan akan ditolak otomatis.
      </p>

      {optional.length > 0 && (
        <div className="rounded-lg p-3 mt-3" style={{ background: "rgba(217,119,6,0.08)", border: "1px solid rgba(217,119,6,0.3)" }}>
          <p style={{ fontWeight: 700, color: C.amber }}>
            <AlertTriangle size={13} style={{ display: "inline", marginRight: 4, verticalAlign: -2 }} />
            {optional.length} file berstatus Opsional
          </p>
          <p style={{ fontSize: 12, marginTop: 4 }}>
            Setelah dihapus, full backup yang lebih lama hanya bisa dipulihkan sampai sequence sebelum file yang dihapus.
            Recovery dari full backup terbaru tidak terpengaruh.
          </p>
          <label className="flex items-center gap-2 mt-2" style={{ fontSize: 12 }}>
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> Saya mengerti dan tetap ingin menghapus.
          </label>
        </div>
      )}

      <label className="flex items-center gap-2 mt-3" style={{ fontSize: 12 }}>
        <input type="checkbox" checked={minio} onChange={(e) => setMinio(e.target.checked)} />
        Hapus juga salinannya di MinIO (archive-logs/)
      </label>

      <div className="mt-3">
        <label style={{ fontSize: 11, fontWeight: 700, color: C.sub, display: "block", marginBottom: 4 }}>Ketik <b>HAPUS</b> untuk konfirmasi</label>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="HAPUS"
          style={{ width: 200, padding: "7px 10px", borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.line}` }} />
      </div>
      {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
    </Modal>
  );
}

/* ─── Semua File Backup (inventory) ──────────────── */

const REC = {
  delete: { label: "Hapus", color: C.red },
  move_offsite: { label: "Salin ke offsite", color: C.amber },
  review: { label: "Tinjau", color: C.sub },
  keep: { label: "Simpan", color: C.green },
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
  if (!inventory) return <Empty>Memindai folder backup di server DB, MinIO, dan Synology…</Empty>;

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
        <Stat label="Total ukuran backup" value={fmtBytes(inventory.total_bytes)} icon={HardDrive} />
        <Stat label="Disarankan dihapus" value={fmtBytes(inventory.reclaimable_bytes)} color={C.green} icon={Trash2} />
        <Stat label="Jumlah folder backup" value={inventory.items.length} icon={FolderOpen} />
        <Stat label="Backup terbaru" value={fmtIso(items.find((i) => i.sortDate)?.sortDate)} icon={Clock} />
      </div>

      <div className="flex items-center gap-2 flex-wrap mb-3">
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12, height: 32, padding: "0 8px" }}>
          <option value="all">Semua jenis backup</option>
          {types.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <span style={{ fontSize: 11.5, color: C.faint }}>Klik judul kolom untuk mengurutkan. Default: tanggal terbaru di atas.</span>
        <div className="flex-1" />
        <Button variant="danger" icon={Trash2} disabled={!chosen.length} onClick={() => setConfirming(true)}>
          Hapus terpilih {chosen.length ? `(${chosen.length})` : ""}
        </Button>
      </div>

      <div className="rounded-xl overflow-x-auto" style={{ border: `1px solid ${C.line}` }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: C.soft }}>
              <td className="px-3 py-2" style={{ width: 28 }}></td>
              <td className="px-3 py-2">{header("date", "Tanggal Backup")}</td>
              <td className="px-3 py-2">{header("name", "Nama")}</td>
              <td className="px-3 py-2">{header("type", "Jenis")}</td>
              <td className="px-3 py-2">{header("size", "Ukuran")}</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Lokasi</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Bisa di-restore?</td>
              <td className="px-3 py-2" style={{ color: C.sub, fontWeight: 700 }}>Rekomendasi</td>
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
                    <div style={{ color: C.faint, fontSize: 10 }}>{it.age_days != null ? `${it.age_days} hari lalu` : ""}</div>
                  </td>
                  <td className="px-3 py-2" style={{ color: C.ink, fontWeight: 600 }}>{it.name}</td>
                  <td className="px-3 py-2">{it.type_label}</td>
                  <td className="px-3 py-2" style={{ whiteSpace: "nowrap" }}>{fmtBytes(it.size_bytes)}</td>
                  <td className="px-3 py-2">{it.locations.map((l) => l.location_label).join(", ")}</td>
                  <td className="px-3 py-2">
                    {it.rman ? (
                      it.rman.restorable ? (
                        <div>
                          <Pill color={C.green}><CheckCircle2 size={11} />Ya{it.rman.is_latest ? " · terbaru" : ""}</Pill>
                          <div style={{ color: C.faint, fontSize: 10, marginTop: 2 }}>s/d {fmtLocal(it.rman.recoverable_until)}</div>
                        </div>
                      ) : <Pill color={C.red} title={it.rman.problems.join(" ")}><XCircle size={11} />Tidak</Pill>
                    ) : it.type === "rman_full" ? (
                      <Pill color={C.faint} title="Folder ini tidak tercatat di control file — perlu CATALOG manual sebelum bisa dipakai">Tidak tercatat RMAN</Pill>
                    ) : <span style={{ color: C.faint }}>—</span>}
                  </td>
                  <td className="px-3 py-2" style={{ minWidth: 220 }}>
                    <span style={{ color: rec.color, fontWeight: 700 }}>{rec.label}</span>
                    <div style={{ color: C.faint, fontSize: 10 }}>{protectedRow(it) ? "Full backup terbaru yang bisa di-restore — dilindungi." : it.reason}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!items.length && <Empty>Tidak ada folder backup.</Empty>}
      </div>

      {confirming && (
        <ConfirmTyped title="Hapus folder backup" onClose={() => setConfirming(false)} onConfirm={doDelete}
          body={<>
            <p>{chosen.length} folder akan dihapus permanen dari semua lokasinya ({fmtBytes(chosen.reduce((t, i) => t + i.size_bytes, 0))}):</p>
            <ul style={{ margin: "8px 0 0 16px", listStyle: "disc", color: C.sub }}>
              {chosen.slice(0, 8).map((i) => <li key={i.key}>{i.name} — {fmtIso(i.sortDate)}</li>)}
              {chosen.length > 8 && <li>…dan {chosen.length - 8} lainnya</li>}
            </ul>
            {chosen.some((i) => i.rman?.restorable) && (
              <p style={{ color: C.amber, marginTop: 8 }}>Sebagian folder berisi full backup yang masih bisa di-restore. Jendela recovery akan menyempit setelah dihapus.</p>
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
        <Button onClick={onClose} disabled={busy}>Batal</Button>
        <Button variant="danger" icon={busy ? Loader2 : Trash2} disabled={typed !== "HAPUS" || busy} onClick={run}>{busy ? "Menghapus…" : "Hapus"}</Button>
      </>}>
      {body}
      <div className="mt-3">
        <label style={{ fontSize: 11, fontWeight: 700, color: C.sub, display: "block", marginBottom: 4 }}>Ketik <b>HAPUS</b> untuk konfirmasi</label>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="HAPUS"
          style={{ width: 200, padding: "7px 10px", borderRadius: 8, fontSize: 12.5, border: `1px solid ${C.line}` }} />
      </div>
    </Modal>
  );
}

/* ─── Panduan ────────────────────────────────────── */

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
      <Section title="Bagaimana recovery Oracle bekerja?">
        <p><b>Full backup RMAN (online)</b> adalah salinan seluruh datafile pada saat backup dijalankan. Karena database tetap berjalan selama backup, salinan itu belum konsisten.</p>
        <p style={{ marginTop: 6 }}><b>Archive log</b> adalah catatan setiap perubahan setelahnya. Saat recovery, RMAN me-restore full backup lalu "memutar ulang" archive log satu per satu, sehingga database bisa dipulihkan ke <b>detik mana pun</b> sampai archive log terakhir yang tersedia.</p>
        <p style={{ marginTop: 6 }}>Syaratnya: archive log harus <b>berurutan tanpa celah</b> mulai dari sequence saat full backup dimulai. Satu sequence hilang = recovery berhenti di situ.</p>
      </Section>
      <Section title="Kapan archive log boleh dihapus?">
        <ul style={{ listStyle: "disc", paddingLeft: 18 }}>
          <li><b style={{ color: C.red }}>Wajib disimpan</b> — sequence sejak full backup terbaru. Ini satu-satunya jalan recovery sampai kondisi terkini.</li>
          <li><b style={{ color: C.amber }}>Opsional</b> — hanya dipakai bila ingin memulihkan ke tanggal lampau memakai full backup lama.</li>
          <li><b style={{ color: C.green }}>Aman dihapus</b> — lebih tua dari semua full backup yang masih ada; tidak ada backup yang bisa memakainya.</li>
        </ul>
        <p style={{ marginTop: 6 }}>Saat full backup lama dihapus, archive log "opsional" miliknya otomatis menjadi "aman dihapus" pada pemindaian berikutnya.</p>
      </Section>
      <Section title="Kebijakan retensi yang disarankan">
        <ul style={{ listStyle: "disc", paddingLeft: 18 }}>
          <li>Full backup online <b>mingguan</b>; simpan minimal <b>2</b> full backup terakhir (lokal + MinIO/Synology).</li>
          <li>Archive log disalin ke staging & MinIO <b>setiap hari</b> (sudah berjalan via cron 01:00).</li>
          <li>Hapus archive log yang berstatus <b>Aman dihapus</b> setelah full backup baru berhasil.</li>
          <li>Uji restore ke Dev minimal <b>sebulan sekali</b> (tab Restore) — backup yang belum pernah diuji belum terbukti.</li>
        </ul>
      </Section>
      <Section title="Kondisi saat ini">
        {!s ? <p>Memuat…</p> : (
          <>
            <p>{s.message}</p>
            <p style={{ marginTop: 6 }}>Sequence aktif sekarang: <b>{catalog.db.current_sequence ?? "—"}</b> · archive log terakhir: <b>{catalog.db.latest_archived_sequence ?? "—"}</b> · jumlah datafile: <b>{catalog.db.datafile_count}</b>.</p>
            <p style={{ marginTop: 6, color: C.sub }}>Archive log yang masih di archive destination database (/archive) dihapus otomatis oleh RMAN setelah 7 hari (cron 05:00), setelah sebelumnya disalin ke staging oleh cron 01:00.</p>
          </>
        )}
      </Section>
    </div>
  );
}
