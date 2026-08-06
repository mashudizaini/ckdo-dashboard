/**
 * Oracle EBS Backup Recovery
 * ─────────────────────────────────────────
 * Ported into the Dashboard IT tab that used to be "Workflow Error" — full
 * functionality moved over from the standalone ebs-backup-dashboard app
 * (was running separately on port 28200/28201): server inventory, DB/App
 * backup triggers, a Dev-database restore wizard, recovery-readiness
 * scanning, scheduling, job history with live log tail, and MinIO/Synology
 * storage browsing. Reskinned flat-white to match the rest of this app —
 * the standalone was dark-themed (slate/amber).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  HardDrive, Database, RotateCcw, HeartPulse, CalendarClock,
  GitBranch, History as HistoryIcon, FileBarChart, Settings2, RefreshCw,
  Loader2, CheckCircle2, XCircle, AlertTriangle, Play, Pause, Square,
  Trash2, Plus, Key, ShieldCheck, ChevronDown, ChevronUp, Server as ServerIcon,
} from "lucide-react";
import { ebsBackupApi } from "@/api/ebsBackup";

/* ─── Sub-tabs ────────────────────────────────────── */

const SUB_TABS = [
  { id: "overview", label: "Overview", icon: HeartPulse },
  { id: "disk-space", label: "Disk Space", icon: HardDrive },
  { id: "db-backup", label: "DB Backup", icon: Database },
  { id: "app-backup", label: "App Backup", icon: ServerIcon },
  { id: "restore", label: "Restore", icon: RotateCcw },
  { id: "recovery-health", label: "Recovery Health", icon: ShieldCheck },
  { id: "schedule", label: "Schedule", icon: CalendarClock },
  { id: "replication", label: "Replication", icon: GitBranch },
  { id: "history", label: "History", icon: HistoryIcon },
  { id: "reports", label: "Reports", icon: FileBarChart },
  { id: "setup", label: "Setup", icon: Settings2 },
];

export default function EbsBackupRecovery() {
  const [tab, setTab] = useState("overview");
  const [servers, setServers] = useState([]);

  const refreshServers = useCallback(async () => {
    try { setServers(await ebsBackupApi.listServers()); } catch (_) {}
  }, []);

  useEffect(() => { refreshServers(); }, [refreshServers]);

  return (
    <div>
      <div className="flex gap-1 flex-wrap mb-4" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)", paddingBottom: 10 }}>
        {SUB_TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs transition-all"
              style={{
                fontWeight: 700, color: active ? "#2563eb" : "#64748b",
                background: active ? "rgba(37,99,235,0.08)" : "transparent",
              }}>
              <Icon size={13} />{t.label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "disk-space" && <DiskSpaceTab />}
      {tab === "db-backup" && <DbBackupTab servers={servers} />}
      {tab === "app-backup" && <AppBackupTab servers={servers} />}
      {tab === "restore" && <RestoreTab servers={servers} />}
      {tab === "recovery-health" && <RecoveryHealthTab />}
      {tab === "schedule" && <ScheduleTab servers={servers} />}
      {tab === "replication" && <ReplicationTab />}
      {tab === "history" && <HistoryTab />}
      {tab === "reports" && <ReportsTab />}
      {tab === "setup" && <SetupTab servers={servers} onServersChanged={refreshServers} />}
    </div>
  );
}

/* ─── Shared UI ───────────────────────────────────── */

function Panel({ title, subtitle, action, children }) {
  return (
    <div style={{ background: "#ffffff", borderRadius: 16, boxShadow: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", marginBottom: 16 }}>
      <div className="flex items-center justify-between px-5 py-3.5" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Btn({ onClick, children, variant = "default", disabled, icon: Icon, size = "md", type = "button" }) {
  const variants = {
    default: { bg: "#f1f5f9", color: "#334155" },
    primary: { bg: "#2563eb", color: "#ffffff" },
    danger: { bg: "#dc2626", color: "#ffffff" },
    ghost: { bg: "transparent", color: "#2563eb" },
  };
  const v = variants[variant] || variants.default;
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className="flex items-center gap-1.5 rounded-lg transition-all"
      style={{
        background: v.bg, color: v.color, fontWeight: 700,
        padding: size === "sm" ? "5px 10px" : "7px 14px",
        fontSize: size === "sm" ? 11 : 12,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
        border: "none",
      }}>
      {Icon && <Icon size={size === "sm" ? 12 : 13} />}{children}
    </button>
  );
}

const inputStyle = {
  width: "100%", padding: "7px 10px", borderRadius: 8, fontSize: 12.5,
  border: "1px solid rgba(15,23,42,0.14)", background: "#ffffff", color: "#0f172a",
};

function Field({ label, children }) {
  return (
    <div>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}

const STATUS_CFG = {
  success: { color: "#16a34a", bg: "rgba(22,163,74,0.1)", icon: CheckCircle2 },
  running: { color: "#2563eb", bg: "rgba(37,99,235,0.1)", icon: Loader2 },
  paused: { color: "#d97706", bg: "rgba(217,119,6,0.1)", icon: Pause },
  pending: { color: "#64748b", bg: "rgba(100,116,139,0.1)", icon: Loader2 },
  failed: { color: "#dc2626", bg: "rgba(220,38,38,0.1)", icon: XCircle },
  cancelled: { color: "#64748b", bg: "rgba(100,116,139,0.1)", icon: Square },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.pending;
  const Icon = cfg.icon;
  return (
    <span className="inline-flex items-center gap-1 rounded-full" style={{ background: cfg.bg, color: cfg.color, padding: "2px 8px", fontSize: 10.5, fontWeight: 700 }}>
      <Icon size={10} className={status === "running" ? "animate-spin" : ""} />{status}
    </span>
  );
}

function fmtBytes(n) {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch (_) { return iso; }
}

function fmtDuration(sec) {
  if (!sec && sec !== 0) return "—";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

function Empty({ children }) {
  return <p style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "24px 0" }}>{children}</p>;
}

/* ─── Overview ────────────────────────────────────── */

function OverviewTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setData(await ebsBackupApi.getOverview()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); const t = setInterval(refresh, 30000); return () => clearInterval(t); }, [refresh]);

  const rpoColor = data?.rpo_minutes == null ? "#94a3b8" : data.rpo_minutes > 1440 ? "#dc2626" : data.rpo_minutes > 360 ? "#d97706" : "#16a34a";

  return (
    <Panel title="Backup & Recovery Overview" action={<Btn icon={loading ? Loader2 : RefreshCw} onClick={refresh}>Refresh</Btn>}>
      {!data ? <Empty>Loading…</Empty> : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-5">
            <div className="rounded-xl p-4 text-center" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, marginBottom: 6 }}>RPO (Archivelog Lag)</p>
              <p style={{ fontSize: 22, fontWeight: 800, color: rpoColor }}>
                {data.rpo_minutes == null ? "—" : data.rpo_minutes < 60 ? `${data.rpo_minutes}m` : `${Math.floor(data.rpo_minutes / 60)}h`}
              </p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, marginBottom: 6 }}>Success (7d)</p>
              <p style={{ fontSize: 22, fontWeight: 800, color: "#16a34a" }}>{data.success_7d}</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, marginBottom: 6 }}>Failed (7d)</p>
              <p style={{ fontSize: 22, fontWeight: 800, color: data.failed_7d > 0 ? "#dc2626" : "#0f172a" }}>{data.failed_7d}</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, marginBottom: 6 }}>Running Now</p>
              <p style={{ fontSize: 22, fontWeight: 800, color: "#2563eb" }}>{data.running_now}</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-5">
            <div className="rounded-xl p-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Last Full Backup</p>
              <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>{fmtDate(data.last_full_backup)}</p>
            </div>
            <div className="rounded-xl p-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Last Archivelog Backup</p>
              <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>{fmtDate(data.last_archlog_backup)}</p>
              {data.archivelog_external && <p style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>via external cron ({data.archivelog_external.file_count} files)</p>}
            </div>
            <div className="rounded-xl p-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Last App Backup</p>
              <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>{fmtDate(data.last_app_backup)}</p>
            </div>
          </div>

          {data.warnings?.length > 0 && (
            <div className="space-y-2">
              {data.warnings.map((w, i) => (
                <div key={i} className="flex items-center gap-2 rounded-lg px-3 py-2" style={{ background: w.level === "critical" ? "rgba(220,38,38,0.08)" : "rgba(217,119,6,0.08)" }}>
                  <AlertTriangle size={14} color={w.level === "critical" ? "#dc2626" : "#d97706"} />
                  <span style={{ fontSize: 12, color: w.level === "critical" ? "#dc2626" : "#d97706", fontWeight: 600 }}>{w.msg}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

/* ─── Disk Space ──────────────────────────────────── */

function DiskSpaceTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setData(await ebsBackupApi.getDiskSpace()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <Panel title="Disk Space — DB & App Servers" action={<Btn icon={loading ? Loader2 : RefreshCw} onClick={refresh}>Refresh</Btn>}>
      {!data?.results?.length ? <Empty>No servers registered yet (add one in Setup).</Empty> : (
        <div className="space-y-4">
          {data.results.map((r, i) => (
            <div key={i} className="rounded-xl p-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <div className="flex items-center justify-between mb-2">
                <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>{r.server} <span style={{ fontWeight: 500, color: "#94a3b8" }}>({r.host}, {r.role})</span></p>
              </div>
              {r.error ? <p style={{ fontSize: 11.5, color: "#dc2626" }}>{r.error}</p> : (
                <div className="space-y-2">
                  {r.mounts.map((m, j) => (
                    <div key={j}>
                      <div className="flex justify-between" style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>
                        <span>{m.mount_point}</span>
                        <span>{m.used_gb}GB / {m.size_gb}GB ({m.use_percent}%)</span>
                      </div>
                      <div style={{ height: 6, borderRadius: 4, background: "#f1f5f9", overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${m.use_percent}%`, background: m.use_percent > 90 ? "#dc2626" : m.use_percent > 75 ? "#d97706" : "#2563eb" }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

/* ─── Jobs list (shared by DB Backup / App Backup / History) ─────── */

function JobsList({ jobTypes, refreshSignal }) {
  const [jobs, setJobs] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const all = await ebsBackupApi.listJobs({ limit: 50 });
      setJobs(jobTypes ? all.filter((j) => jobTypes.includes(j.job_type)) : all);
    } finally { setLoading(false); }
  }, [jobTypes]);

  useEffect(() => { refresh(); }, [refresh, refreshSignal]);
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === "running" || j.status === "paused" || j.status === "pending");
    if (!hasActive) return;
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [jobs, refresh]);

  return (
    <div>
      <div className="flex justify-end mb-2">
        <Btn size="sm" icon={loading ? Loader2 : RefreshCw} onClick={refresh}>Refresh</Btn>
      </div>
      {!jobs.length ? <Empty>No jobs yet.</Empty> : (
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                <td className="px-3 py-2">ID</td><td className="px-3 py-2">Type</td><td className="px-3 py-2">Status</td>
                <td className="px-3 py-2">Started</td><td className="px-3 py-2">Duration</td><td className="px-3 py-2">Size</td><td className="px-3 py-2"></td>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <>
                  <tr key={j.id} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                    <td className="px-3 py-2">#{j.id}</td>
                    <td className="px-3 py-2">{j.job_type}</td>
                    <td className="px-3 py-2"><StatusBadge status={j.status} /></td>
                    <td className="px-3 py-2" style={{ color: "#64748b" }}>{fmtDate(j.started_at)}</td>
                    <td className="px-3 py-2" style={{ color: "#64748b" }}>{fmtDuration(j.duration_sec)}</td>
                    <td className="px-3 py-2" style={{ color: "#64748b" }}>{fmtBytes(j.total_size_bytes)}</td>
                    <td className="px-3 py-2">
                      <button onClick={() => setExpanded(expanded === j.id ? null : j.id)} style={{ color: "#2563eb" }}>
                        {expanded === j.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </td>
                  </tr>
                  {expanded === j.id && (
                    <tr key={`${j.id}-detail`}>
                      <td colSpan={7} style={{ background: "#f8fafc", padding: 0 }}>
                        <JobDetail jobId={j.id} onChanged={refresh} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function JobDetail({ jobId, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try { setDetail(await ebsBackupApi.getJob(jobId, { list_files: true })); } catch (_) {}
  }, [jobId]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!detail || !["running", "paused"].includes(detail.status)) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [detail, refresh]);

  const act = async (fn) => {
    setBusy(true);
    try { await fn(); await refresh(); onChanged?.(); } catch (e) { alert(e?.detail || "Action failed"); } finally { setBusy(false); }
  };

  if (!detail) return <div className="p-4"><Loader2 size={14} className="animate-spin" /></div>;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        {detail.status === "running" && <Btn size="sm" icon={Pause} disabled={busy} onClick={() => act(() => ebsBackupApi.pauseJob(jobId))}>Pause</Btn>}
        {detail.status === "paused" && <Btn size="sm" icon={Play} disabled={busy} onClick={() => act(() => ebsBackupApi.resumeJob(jobId))}>Resume</Btn>}
        {["running", "paused"].includes(detail.status) && (
          <Btn size="sm" variant="danger" icon={Square} disabled={busy} onClick={() => { if (confirm("Cancel this job?")) act(() => ebsBackupApi.cancelJob(jobId)); }}>Cancel</Btn>
        )}
        {["success", "failed", "cancelled"].includes(detail.status) && detail.output_path && (
          <Btn size="sm" variant="ghost" icon={Trash2} disabled={busy} onClick={() => { if (confirm("Delete this job's staging output?")) act(() => ebsBackupApi.deleteJobOutput(jobId)); }}>Delete Output</Btn>
        )}
      </div>

      {detail.progress_percent != null && (
        <div>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>Progress: {detail.progress_percent}%</div>
          <div style={{ height: 6, borderRadius: 4, background: "#e2e8f0", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${detail.progress_percent}%`, background: "#2563eb" }} />
          </div>
        </div>
      )}

      {detail.error_message && <p style={{ fontSize: 11.5, color: "#dc2626" }}>{detail.error_message}</p>}

      {detail.live_log && (
        <pre style={{ background: "#0f172a", color: "#e2e8f0", fontSize: 10.5, padding: 10, borderRadius: 8, maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap" }}>
          {detail.live_log}
        </pre>
      )}

      {detail.output_files?.length > 0 && (
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>Output files</p>
          <ul style={{ fontSize: 11, color: "#334155" }}>
            {detail.output_files.map((f, i) => <li key={i}>{f.name} — {fmtBytes(f.size_bytes)}</li>)}
          </ul>
        </div>
      )}

      <p style={{ fontSize: 10.5, color: "#94a3b8" }}>Output path: {detail.output_path || "—"}</p>
    </div>
  );
}

/* ─── DB Backup ───────────────────────────────────── */

function DbBackupTab({ servers }) {
  const dbServers = servers.filter((s) => s.role === "db");
  const minioServers = servers.filter((s) => s.role === "minio");
  const synologyServers = servers.filter((s) => s.role === "synology");

  const [jobType, setJobType] = useState("online_full");
  const [serverId, setServerId] = useState("");
  const [parallelism, setParallelism] = useState(4);
  const [compression, setCompression] = useState(true);
  const [includeArchivelog, setIncludeArchivelog] = useState(true);
  const [archDeleteInput, setArchDeleteInput] = useState(false);
  const [incLevel, setIncLevel] = useState(1);
  const [destination, setDestination] = useState("staging");
  const [minioId, setMinioId] = useState("");
  const [synologyId, setSynologyId] = useState("");
  const [dataPaths, setDataPaths] = useState("/data01,/data02,/data03,/data04");
  const [stopApps, setStopApps] = useState(true);
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [refreshSignal, setRefreshSignal] = useState(0);

  const submit = async () => {
    if (!serverId) return alert("Select a DB server first");
    setSubmitting(true);
    try {
      if (jobType === "offline_cold") {
        if (confirmText !== "SHUTDOWN") return alert('Type "SHUTDOWN" to confirm — this stops the database.');
        await ebsBackupApi.triggerOffline({
          server_id: Number(serverId), data_paths: dataPaths.split(",").map((s) => s.trim()).filter(Boolean),
          stop_apps_first: stopApps, confirm_token: "SHUTDOWN_CONFIRMED",
        });
      } else if (jobType === "archivelog") {
        await ebsBackupApi.triggerArchivelog({ server_id: Number(serverId), delete_input: archDeleteInput });
      } else {
        await ebsBackupApi.triggerOnlineBackup({
          server_id: Number(serverId), job_type: jobType, incremental_level: incLevel, parallelism,
          compression, include_archivelog: includeArchivelog, archivelog_delete_input: archDeleteInput,
          destination, minio_server_id: minioId ? Number(minioId) : null, synology_server_id: synologyId ? Number(synologyId) : null,
        });
      }
      setConfirmText("");
      setRefreshSignal((n) => n + 1);
    } catch (e) {
      alert(e?.detail || "Failed to submit backup job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Panel title="Trigger Database Backup" subtitle="RMAN online full / incremental / archivelog, or a maintenance-window offline cold backup.">
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Field label="DB Server">
            <select style={inputStyle} value={serverId} onChange={(e) => setServerId(e.target.value)}>
              <option value="">Select…</option>
              {dbServers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.host})</option>)}
            </select>
          </Field>
          <Field label="Backup Type">
            <select style={inputStyle} value={jobType} onChange={(e) => setJobType(e.target.value)}>
              <option value="online_full">Online Full (RMAN)</option>
              <option value="online_incremental">Online Incremental (RMAN)</option>
              <option value="archivelog">Archivelog Only</option>
              <option value="offline_cold">Offline Cold ⚠️</option>
            </select>
          </Field>
          {["online_full", "online_incremental"].includes(jobType) && (
            <Field label="Parallelism (channels)">
              <input type="number" min={1} max={8} style={inputStyle} value={parallelism} onChange={(e) => setParallelism(Number(e.target.value))} />
            </Field>
          )}
        </div>

        {jobType === "online_incremental" && (
          <div className="grid grid-cols-3 gap-4 mb-4">
            <Field label="Incremental Level">
              <select style={inputStyle} value={incLevel} onChange={(e) => setIncLevel(Number(e.target.value))}>
                <option value={0}>Level 0 (baseline)</option>
                <option value={1}>Level 1</option>
              </select>
            </Field>
          </div>
        )}

        {jobType === "online_full" && (
          <div className="grid grid-cols-3 gap-4 mb-4 items-end">
            <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={compression} onChange={(e) => setCompression(e.target.checked)} /> Compression
            </label>
            <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={includeArchivelog} onChange={(e) => setIncludeArchivelog(e.target.checked)} /> Include Archivelog
            </label>
            <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={archDeleteInput} onChange={(e) => setArchDeleteInput(e.target.checked)} /> Delete Input After Backup
            </label>
          </div>
        )}

        {jobType === "archivelog" && (
          <div className="mb-4">
            <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={archDeleteInput} onChange={(e) => setArchDeleteInput(e.target.checked)} /> Delete Input After Backup
            </label>
          </div>
        )}

        {["online_full"].includes(jobType) && (
          <div className="grid grid-cols-3 gap-4 mb-4">
            <Field label="Destination">
              <select style={inputStyle} value={destination} onChange={(e) => setDestination(e.target.value)}>
                <option value="staging">Local Staging Only</option>
                <option value="minio_direct">Staging + Push to MinIO</option>
                <option value="synology_direct">Staging + Push to Synology</option>
              </select>
            </Field>
            {destination === "minio_direct" && (
              <Field label="MinIO Server">
                <select style={inputStyle} value={minioId} onChange={(e) => setMinioId(e.target.value)}>
                  <option value="">Select…</option>
                  {minioServers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            )}
            {destination === "synology_direct" && (
              <Field label="Synology Server">
                <select style={inputStyle} value={synologyId} onChange={(e) => setSynologyId(e.target.value)}>
                  <option value="">Select…</option>
                  {synologyServers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            )}
          </div>
        )}

        {jobType === "offline_cold" && (
          <div className="space-y-3 mb-4">
            <div className="rounded-lg px-3 py-2" style={{ background: "rgba(220,38,38,0.08)", color: "#dc2626", fontSize: 12, fontWeight: 600 }}>
              ⚠️ This SHUTS DOWN the database (and optionally the EBS apps tier) for the duration of the backup. Only run in a maintenance window.
            </div>
            <Field label="Data Paths (comma-separated)">
              <input style={inputStyle} value={dataPaths} onChange={(e) => setDataPaths(e.target.value)} />
            </Field>
            <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={stopApps} onChange={(e) => setStopApps(e.target.checked)} /> Stop EBS apps tier first
            </label>
            <Field label='Type "SHUTDOWN" to confirm'>
              <input style={inputStyle} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="SHUTDOWN" />
            </Field>
          </div>
        )}

        <Btn variant="primary" icon={Play} disabled={submitting} onClick={submit}>
          {submitting ? "Submitting…" : "Trigger Backup"}
        </Btn>
      </Panel>

      <Panel title="Recent Database Backup Jobs">
        <JobsList jobTypes={["online_full", "online_incremental", "archivelog", "offline_cold", "db_sync_minio", "db_sync_synology"]} refreshSignal={refreshSignal} />
      </Panel>
    </>
  );
}

/* ─── App Backup ──────────────────────────────────── */

function AppBackupTab({ servers }) {
  const appServers = servers.filter((s) => s.role === "app");
  const dbServers = servers.filter((s) => s.role === "db");

  const [serverId, setServerId] = useState("");
  const [fsTarget, setFsTarget] = useState("fs2");
  const [includeInstTop, setIncludeInstTop] = useState(true);
  const [remoteTargetId, setRemoteTargetId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [refreshSignal, setRefreshSignal] = useState(0);

  const submit = async () => {
    if (!serverId) return alert("Select an App server first");
    setSubmitting(true);
    try {
      await ebsBackupApi.triggerApp({
        server_id: Number(serverId), fs_target: fsTarget, include_inst_top: includeInstTop,
        remote_target_server_id: remoteTargetId ? Number(remoteTargetId) : null,
      });
      setRefreshSignal((n) => n + 1);
    } catch (e) {
      alert(e?.detail || "Failed to submit app backup job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Panel title="Trigger Application Tier Backup" subtitle="FS1/FS2 tar backup — streamed to a DB server instead of local disk when the App server has no backup partition.">
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Field label="App Server">
            <select style={inputStyle} value={serverId} onChange={(e) => setServerId(e.target.value)}>
              <option value="">Select…</option>
              {appServers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.host})</option>)}
            </select>
          </Field>
          <Field label="Filesystem">
            <select style={inputStyle} value={fsTarget} onChange={(e) => setFsTarget(e.target.value)}>
              <option value="fs1">FS1</option>
              <option value="fs2">FS2</option>
              <option value="both">Both</option>
            </select>
          </Field>
          <Field label="Remote Target (optional — stream via SSH)">
            <select style={inputStyle} value={remoteTargetId} onChange={(e) => setRemoteTargetId(e.target.value)}>
              <option value="">Local disk on App server</option>
              {dbServers.map((s) => <option key={s.id} value={s.id}>Stream to {s.name}</option>)}
            </select>
          </Field>
        </div>
        <label className="flex items-center gap-2 mb-4" style={{ fontSize: 12 }}>
          <input type="checkbox" checked={includeInstTop} onChange={(e) => setIncludeInstTop(e.target.checked)} /> Include inst_top / fs_ne
        </label>
        <Btn variant="primary" icon={Play} disabled={submitting} onClick={submit}>
          {submitting ? "Submitting…" : "Trigger App Backup"}
        </Btn>
      </Panel>

      <Panel title="Recent App Backup Jobs">
        <JobsList jobTypes={["app_fs"]} refreshSignal={refreshSignal} />
      </Panel>
    </>
  );
}

/* ─── Restore ─────────────────────────────────────── */

function RestoreTab() {
  const [preflight, setPreflight] = useState(null);
  const [loading, setLoading] = useState(false);
  const [devServerId, setDevServerId] = useState("");
  const [checkbox, setCheckbox] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setPreflight(await ebsBackupApi.restorePreflight()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const submit = async () => {
    if (!devServerId) return alert("Select a Dev target server");
    if (!checkbox || confirmText !== "OVERWRITE") return alert('Confirm the checkbox and type "OVERWRITE" to proceed.');
    setSubmitting(true);
    try {
      const res = await ebsBackupApi.restoreToDev({ source_job_id: preflight.source_backup.job_id, dev_server_id: Number(devServerId) });
      alert(`Restore job #${res.job_id} submitted — track it in History.`);
      setCheckbox(false); setConfirmText("");
    } catch (e) {
      alert(e?.detail || "Restore failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Panel title="Restore PROD Backup → Dev Database" subtitle="Database-only restore for backup validation. Deliberately does NOT touch the EBS application tier, and can only target a server explicitly registered with role = Dev — never Production." action={<Btn icon={loading ? Loader2 : RefreshCw} onClick={refresh}>Refresh</Btn>}>
      {!preflight ? <Empty>Loading…</Empty> : (
        <>
          <div className="rounded-xl p-4 mb-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6 }}>Source backup (latest successful Online Full)</p>
            {!preflight.source_backup ? <p style={{ fontSize: 12, color: "#dc2626" }}>No successful Online Full backup found — trigger one first.</p> : (
              <p style={{ fontSize: 12.5, color: "#0f172a" }}>
                Job #{preflight.source_backup.job_id} — {fmtDate(preflight.source_backup.finished_at)} — {fmtBytes(preflight.source_backup.total_size_bytes)}
              </p>
            )}
          </div>

          <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 8 }}>Dev target servers</p>
          <div className="space-y-2 mb-5">
            {!preflight.dev_servers?.length && <Empty>No Dev servers registered (add one with role="dev" in Setup).</Empty>}
            {preflight.dev_servers?.map((d) => (
              <label key={d.id} className="flex items-center gap-3 rounded-lg p-3 cursor-pointer" style={{ border: devServerId === String(d.id) ? "1.5px solid #2563eb" : "1px solid rgba(0,0,0,0.08)", background: devServerId === String(d.id) ? "rgba(37,99,235,0.04)" : "#fff" }}>
                <input type="radio" name="dev-server" checked={devServerId === String(d.id)} onChange={() => setDevServerId(String(d.id))} disabled={!d.connected} />
                <div style={{ fontSize: 12 }}>
                  <span style={{ fontWeight: 700, color: "#0f172a" }}>{d.name}</span> ({d.host}, SID={d.oracle_sid}) —{" "}
                  {d.connected ? <span style={{ color: "#16a34a" }}>connected, {fmtBytes(d.available_bytes)} free, DB status: {d.current_db_status}</span> : <span style={{ color: "#dc2626" }}>{d.error || "not reachable"}</span>}
                </div>
              </label>
            ))}
          </div>

          {preflight.source_backup && (
            <div className="rounded-xl p-4" style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)" }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: "#dc2626", marginBottom: 8 }}>⚠️ This will overwrite the selected Dev database's current content.</p>
              <label className="flex items-center gap-2 mb-3" style={{ fontSize: 12 }}>
                <input type="checkbox" checked={checkbox} onChange={(e) => setCheckbox(e.target.checked)} /> I understand this will destroy the current Dev database content.
              </label>
              <Field label='Type "OVERWRITE" to confirm'>
                <input style={{ ...inputStyle, maxWidth: 240 }} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="OVERWRITE" />
              </Field>
              <div className="mt-3">
                <Btn variant="danger" icon={RotateCcw} disabled={submitting} onClick={submit}>{submitting ? "Submitting…" : "Restore to Dev"}</Btn>
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

/* ─── Recovery Health ─────────────────────────────── */

function RecoveryHealthTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState({});

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setData(await ebsBackupApi.scanInventory()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const readinessColor = { green: "#16a34a", amber: "#d97706", red: "#dc2626" }[data?.readiness?.status] || "#94a3b8";

  const deleteSelected = async () => {
    const targets = Object.entries(selected).filter(([, v]) => v).map(([k]) => k);
    if (!targets.length) return;
    if (!confirm(`Delete ${targets.length} selected backup copies? This cannot be undone.`)) return;
    for (const key of targets) {
      const [location, server_id, ...pathParts] = key.split("::");
      try { await ebsBackupApi.deleteInventoryItem({ location, server_id: Number(server_id), path: pathParts.join("::") }); } catch (_) {}
    }
    setSelected({});
    refresh();
  };

  return (
    <Panel title="Recovery Readiness" subtitle="Heuristic scan across the DB server's /backup tree, MinIO, and Synology — every recommendation carries its reasoning; nothing is deleted automatically." action={<Btn icon={loading ? Loader2 : RefreshCw} onClick={refresh}>{loading ? "Scanning…" : "Rescan"}</Btn>}>
      {!data ? <Empty>Loading…</Empty> : (
        <>
          <div className="rounded-xl p-5 mb-5 text-center" style={{ background: `${readinessColor}12`, border: `1px solid ${readinessColor}40` }}>
            <p style={{ fontSize: 26, fontWeight: 800, color: readinessColor, textTransform: "uppercase" }}>{data.readiness.status}</p>
            <p style={{ fontSize: 13, color: "#0f172a", marginTop: 4 }}>{data.readiness.message}</p>
            {data.readiness.warnings?.map((w, i) => <p key={i} style={{ fontSize: 11.5, color: "#d97706", marginTop: 4 }}>{w}</p>)}
          </div>

          <div className="grid grid-cols-2 gap-4 mb-5">
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>Total Backup Footprint</p>
              <p style={{ fontSize: 18, fontWeight: 800, color: "#0f172a" }}>{fmtBytes(data.total_bytes)}</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>Reclaimable (safe to delete)</p>
              <p style={{ fontSize: 18, fontWeight: 800, color: "#16a34a" }}>{fmtBytes(data.reclaimable_bytes)}</p>
            </div>
          </div>

          {Object.values(selected).some(Boolean) && (
            <div className="mb-3"><Btn variant="danger" icon={Trash2} onClick={deleteSelected}>Delete Selected</Btn></div>
          )}

          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                  <td className="px-3 py-2"></td><td className="px-3 py-2">Name</td><td className="px-3 py-2">Type</td>
                  <td className="px-3 py-2">Age</td><td className="px-3 py-2">Size</td><td className="px-3 py-2">Locations</td><td className="px-3 py-2">Recommendation</td>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it, i) => {
                  const primaryLoc = it.locations[0];
                  const key = `${primaryLoc.location}::${primaryLoc.server_id}::${primaryLoc.path}`;
                  const recColor = { delete: "#dc2626", move_offsite: "#d97706", review: "#64748b", keep: "#16a34a" }[it.recommendation];
                  return (
                    <tr key={i} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                      <td className="px-3 py-2">
                        {it.recommendation === "delete" && <input type="checkbox" checked={!!selected[key]} onChange={(e) => setSelected((s) => ({ ...s, [key]: e.target.checked }))} />}
                      </td>
                      <td className="px-3 py-2" style={{ color: "#0f172a", fontWeight: 600 }}>{it.name}</td>
                      <td className="px-3 py-2">{it.type_label}</td>
                      <td className="px-3 py-2">{it.age_days != null ? `${it.age_days}d` : "—"}</td>
                      <td className="px-3 py-2">{fmtBytes(it.size_bytes)}</td>
                      <td className="px-3 py-2">{it.locations.map((l) => l.location_label).join(", ")}</td>
                      <td className="px-3 py-2">
                        <span style={{ color: recColor, fontWeight: 700 }}>{it.recommendation}</span>
                        <div style={{ color: "#94a3b8", fontSize: 10 }}>{it.reason}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

/* ─── Schedule ─────────────────────────────────────── */

function ScheduleTab({ servers }) {
  const [schedules, setSchedules] = useState([]);
  const [form, setForm] = useState({ name: "", job_type: "archivelog_sync", cron_expression: "0 */6 * * *", target_server_id: "", parameters: "{}", enabled: true });
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => { setSchedules(await ebsBackupApi.listSchedules()); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const submit = async () => {
    let params;
    try { params = JSON.parse(form.parameters || "{}"); } catch (_) { return alert("Parameters must be valid JSON"); }
    if (!form.name || !form.target_server_id) return alert("Name and target server are required");
    setSubmitting(true);
    try {
      await ebsBackupApi.upsertSchedule({ ...form, target_server_id: Number(form.target_server_id), parameters: params });
      setForm({ name: "", job_type: "archivelog_sync", cron_expression: "0 */6 * * *", target_server_id: "", parameters: "{}", enabled: true });
      refresh();
    } catch (e) {
      alert(e?.detail || "Failed to save schedule");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Panel title="New / Update Schedule" subtitle='Only "Archivelog Sync → MinIO" has an automatic runner today — other job types just track intent (next_run_at) until a human clicks Trigger in their tab.'>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <Field label="Name (unique)"><input style={inputStyle} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></Field>
          <Field label="Job Type">
            <select style={inputStyle} value={form.job_type} onChange={(e) => setForm((f) => ({ ...f, job_type: e.target.value }))}>
              <option value="archivelog_sync">Archivelog Sync → MinIO (automatic)</option>
              <option value="online_full">Online Full (manual trigger still required)</option>
              <option value="online_incremental">Online Incremental (manual trigger still required)</option>
              <option value="archivelog">Archivelog (manual trigger still required)</option>
              <option value="app_fs">App Backup (manual trigger still required)</option>
            </select>
          </Field>
          <Field label="Cron Expression (UTC)"><input style={inputStyle} value={form.cron_expression} onChange={(e) => setForm((f) => ({ ...f, cron_expression: e.target.value }))} /></Field>
          <Field label="Target Server">
            <select style={inputStyle} value={form.target_server_id} onChange={(e) => setForm((f) => ({ ...f, target_server_id: e.target.value }))}>
              <option value="">Select…</option>
              {servers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.role})</option>)}
            </select>
          </Field>
        </div>
        <Field label="Parameters (JSON)"><textarea style={{ ...inputStyle, height: 70, fontFamily: "monospace" }} value={form.parameters} onChange={(e) => setForm((f) => ({ ...f, parameters: e.target.value }))} /></Field>
        <div className="mt-4"><Btn variant="primary" icon={Plus} disabled={submitting} onClick={submit}>Save Schedule</Btn></div>
      </Panel>

      <Panel title="Schedules">
        {!schedules.length ? <Empty>No schedules yet.</Empty> : (
          <div className="space-y-2">
            {schedules.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg p-3" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
                <div>
                  <p style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>{s.name} <span style={{ fontWeight: 500, color: "#94a3b8" }}>({s.job_type})</span></p>
                  <p style={{ fontSize: 11, color: "#64748b" }}>cron: {s.cron_expression} — next run: {fmtDate(s.next_run_at)} — last: {s.last_run_status || "never"} at {fmtDate(s.last_run_at)}</p>
                </div>
                <div className="flex gap-2">
                  <Btn size="sm" onClick={async () => { await ebsBackupApi.toggleSchedule(s.id); refresh(); }}>{s.enabled ? "Disable" : "Enable"}</Btn>
                  <Btn size="sm" variant="danger" icon={Trash2} onClick={async () => { if (confirm("Delete this schedule?")) { await ebsBackupApi.deleteSchedule(s.id); refresh(); } }}>Delete</Btn>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

/* ─── Replication ─────────────────────────────────── */

function ReplicationTab() {
  return (
    <Panel title="Replication Strategy (3-2-1)" subtitle="Planned — no live trigger UI yet, same as the standalone app this was ported from.">
      <div className="flex items-center justify-center gap-6 py-6" style={{ fontSize: 12.5, color: "#334155" }}>
        <div className="text-center">
          <div className="rounded-xl p-4 mb-2" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}><Database size={22} /></div>
          Local Staging
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div className="text-center">
          <div className="rounded-xl p-4 mb-2" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}><HardDrive size={22} /></div>
          Synology (onsite copy)
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div className="text-center">
          <div className="rounded-xl p-4 mb-2" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.06)" }}><GitBranch size={22} /></div>
          MinIO (offsite copy)
        </div>
      </div>
      <p style={{ fontSize: 11.5, color: "#64748b" }}>
        3 copies of data, on 2 different media, with 1 offsite. Today this is achieved via the "Push to MinIO/Synology" destination option on DB Backup, plus the manual "Sync" actions on a completed job in History.
      </p>
    </Panel>
  );
}

/* ─── History ─────────────────────────────────────── */

function HistoryTab() {
  return (
    <Panel title="All Backup Jobs">
      <JobsList />
    </Panel>
  );
}

/* ─── Reports ─────────────────────────────────────── */

function ReportsTab() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setData(await ebsBackupApi.getReportsSummary(days)); } finally { setLoading(false); }
  }, [days]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <Panel title="Reports" action={
      <div className="flex gap-2 items-center">
        <select style={{ ...inputStyle, width: 100 }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={5}>5 days</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option>
        </select>
        <Btn icon={loading ? Loader2 : RefreshCw} onClick={refresh}>Refresh</Btn>
      </div>
    }>
      {!data ? <Empty>Loading…</Empty> : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-5">
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700 }}>Total Jobs</p>
              <p style={{ fontSize: 20, fontWeight: 800, color: "#0f172a" }}>{data.kpi.total_jobs}</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700 }}>Success Rate</p>
              <p style={{ fontSize: 20, fontWeight: 800, color: "#16a34a" }}>{data.kpi.success_rate_pct ?? "—"}%</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700 }}>Total Backed Up</p>
              <p style={{ fontSize: 20, fontWeight: 800, color: "#0f172a" }}>{fmtBytes(data.kpi.total_bytes_backed_up)}</p>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700 }}>Failed</p>
              <p style={{ fontSize: 20, fontWeight: 800, color: data.kpi.failed_jobs ? "#dc2626" : "#0f172a" }}>{data.kpi.failed_jobs}</p>
            </div>
          </div>

          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
            <table className="w-full text-xs">
              <thead><tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                <td className="px-3 py-2">Date</td><td className="px-3 py-2">Jobs</td><td className="px-3 py-2">Archivelog (external cron)</td>
              </tr></thead>
              <tbody>
                {data.daily.map((d) => (
                  <tr key={d.date} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                    <td className="px-3 py-2" style={{ fontWeight: 700 }}>{d.date}</td>
                    <td className="px-3 py-2">
                      {d.jobs.length === 0 ? <span style={{ color: "#94a3b8" }}>—</span> : d.jobs.map((j) => (
                        <span key={j.id} className="inline-block mr-2"><StatusBadge status={j.status} /> {j.job_type}</span>
                      ))}
                    </td>
                    <td className="px-3 py-2">{d.archivelog ? `${d.archivelog.file_count} files, ${fmtBytes(d.archivelog.total_size_bytes)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

/* ─── Setup — servers, credentials, SSH wizard ────── */

function SetupTab({ servers, onServersChanged }) {
  const [editing, setEditing] = useState(null);
  const [credServerId, setCredServerId] = useState("");

  return (
    <>
      <Panel title={editing ? `Edit Server — ${editing.name}` : "Add Server"} action={editing && <Btn size="sm" onClick={() => setEditing(null)}>New Server</Btn>}>
        <ServerForm key={editing?.id || "new"} initial={editing} onSaved={() => { setEditing(null); onServersChanged(); }} />
      </Panel>

      <Panel title="Registered Servers">
        {!servers.length ? <Empty>No servers yet.</Empty> : (
          <div className="space-y-2">
            {servers.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg p-3" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
                <div>
                  <p style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>{s.name} <span style={{ fontWeight: 500, color: "#94a3b8" }}>({s.role})</span> {!s.enabled && <span style={{ color: "#dc2626" }}>disabled</span>}</p>
                  <p style={{ fontSize: 11, color: "#64748b" }}>{s.host}:{s.port}</p>
                </div>
                <div className="flex gap-2">
                  <Btn size="sm" onClick={async () => { const r = await ebsBackupApi.testConnection(s.id); alert(r.ok ? `OK\n${r.output}` : `Failed: ${r.error}`); }}>Test</Btn>
                  <Btn size="sm" icon={Key} onClick={() => setCredServerId(String(s.id))}>Credentials</Btn>
                  <Btn size="sm" onClick={() => setEditing(s)}>Edit</Btn>
                  <Btn size="sm" variant="danger" icon={Trash2} onClick={async () => { if (confirm(`Delete server ${s.name}?`)) { await ebsBackupApi.deleteServer(s.id); onServersChanged(); } }}>Delete</Btn>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {credServerId && (
        <Panel title={`Credentials — ${servers.find((s) => String(s.id) === credServerId)?.name}`} action={<Btn size="sm" onClick={() => setCredServerId("")}>Close</Btn>}>
          <CredentialForm serverId={Number(credServerId)} />
        </Panel>
      )}

      <Panel title="SSH Passwordless Setup Wizard" subtitle="Generate a key on a source server, copy it to a target server's authorized_keys (temporary password, never stored), then verify.">
        <SshSetupWizard servers={servers} />
      </Panel>
    </>
  );
}

function ServerForm({ initial, onSaved }) {
  const [form, setForm] = useState(initial || {
    name: "", role: "db", host: "", port: 22, oracle_sid: "", oracle_home: "", apps_base: "", current_fs: "fs2",
    endpoint_url: "", bucket: "", region: "", share_path: "", protocol: "rsync_ssh", notes: "", enabled: true,
  });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!form.name || !form.host) return alert("Name and host are required");
    setSubmitting(true);
    try {
      await ebsBackupApi.upsertServer({ ...form, port: Number(form.port) || 22 });
      onSaved();
    } catch (e) {
      alert(e?.detail || "Failed to save server");
    } finally {
      setSubmitting(false);
    }
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div>
      <div className="grid grid-cols-3 gap-4 mb-4">
        <Field label="Name (unique)"><input style={inputStyle} value={form.name} onChange={set("name")} /></Field>
        <Field label="Role">
          <select style={inputStyle} value={form.role} onChange={set("role")}>
            <option value="db">DB</option><option value="app">App</option><option value="dev">Dev (restore target)</option>
            <option value="synology">Synology</option><option value="minio">MinIO</option>
          </select>
        </Field>
        <Field label="Host / IP"><input style={inputStyle} value={form.host} onChange={set("host")} /></Field>
        <Field label="SSH Port"><input type="number" style={inputStyle} value={form.port} onChange={set("port")} /></Field>
        <label className="flex items-center gap-2" style={{ fontSize: 12, marginTop: 20 }}>
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))} /> Enabled
        </label>
      </div>

      {["db", "app", "dev"].includes(form.role) && (
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Field label="Oracle SID"><input style={inputStyle} value={form.oracle_sid || ""} onChange={set("oracle_sid")} /></Field>
          <Field label="Oracle Home"><input style={inputStyle} value={form.oracle_home || ""} onChange={set("oracle_home")} /></Field>
          <Field label="Apps Base"><input style={inputStyle} value={form.apps_base || ""} onChange={set("apps_base")} /></Field>
          {form.role === "app" && (
            <Field label="Current FS"><select style={inputStyle} value={form.current_fs || "fs2"} onChange={set("current_fs")}><option value="fs1">FS1</option><option value="fs2">FS2</option></select></Field>
          )}
        </div>
      )}

      {form.role === "minio" && (
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Field label="Endpoint URL"><input style={inputStyle} value={form.endpoint_url || ""} onChange={set("endpoint_url")} placeholder="http://host:9000" /></Field>
          <Field label="Bucket"><input style={inputStyle} value={form.bucket || ""} onChange={set("bucket")} /></Field>
          <Field label="Region"><input style={inputStyle} value={form.region || ""} onChange={set("region")} /></Field>
        </div>
      )}

      {form.role === "synology" && (
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Field label="Share Path"><input style={inputStyle} value={form.share_path || ""} onChange={set("share_path")} /></Field>
          <Field label="Protocol"><input style={inputStyle} value={form.protocol || "rsync_ssh"} onChange={set("protocol")} /></Field>
        </div>
      )}

      <Field label="Notes"><textarea style={{ ...inputStyle, height: 50 }} value={form.notes || ""} onChange={set("notes")} /></Field>
      <div className="mt-4"><Btn variant="primary" disabled={submitting} onClick={submit}>{initial ? "Update Server" : "Add Server"}</Btn></div>
    </div>
  );
}

function CredentialForm({ serverId }) {
  const [existing, setExisting] = useState([]);
  const [credType, setCredType] = useState("ssh_password");
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => { setExisting(await ebsBackupApi.listCredentials(serverId)); }, [serverId]);
  useEffect(() => { refresh(); }, [refresh]);

  const submit = async () => {
    if (!secret) return alert("Secret is required");
    setSubmitting(true);
    try {
      await ebsBackupApi.upsertCredential({ server_id: serverId, cred_type: credType, username, secret, key_passphrase: passphrase || null });
      setSecret(""); setPassphrase("");
      refresh();
    } catch (e) {
      alert(e?.detail || "Failed to save credential");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div className="mb-4">
        <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6 }}>Configured</p>
        {!existing.length ? <p style={{ fontSize: 12, color: "#94a3b8" }}>None yet.</p> : (
          <ul style={{ fontSize: 12 }}>{existing.map((c) => <li key={c.id}>{c.cred_type} — {c.username || "—"}{c.has_passphrase ? " (has passphrase)" : ""}</li>)}</ul>
        )}
      </div>
      <div className="grid grid-cols-3 gap-4 mb-3">
        <Field label="Type">
          <select style={inputStyle} value={credType} onChange={(e) => setCredType(e.target.value)}>
            <option value="ssh_password">SSH Password</option><option value="ssh_key">SSH Private Key</option><option value="minio">MinIO Access Key</option>
          </select>
        </Field>
        <Field label="Username / Access Key"><input style={inputStyle} value={username} onChange={(e) => setUsername(e.target.value)} /></Field>
        <Field label={credType === "ssh_key" ? "Private Key (PEM)" : credType === "minio" ? "Secret Key" : "Password"}>
          <input type={credType === "ssh_password" || credType === "minio" ? "password" : "text"} style={inputStyle} value={secret} onChange={(e) => setSecret(e.target.value)} />
        </Field>
      </div>
      {credType === "ssh_key" && <Field label="Key Passphrase (optional)"><input type="password" style={inputStyle} value={passphrase} onChange={(e) => setPassphrase(e.target.value)} /></Field>}
      <div className="mt-3"><Btn variant="primary" disabled={submitting} onClick={submit}>Save Credential</Btn></div>
    </div>
  );
}

function SshSetupWizard({ servers }) {
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [targetUsername, setTargetUsername] = useState("");
  const [targetPassword, setTargetPassword] = useState("");
  const [pubKey, setPubKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const genKey = async () => {
    if (!sourceId) return alert("Select a source server");
    setBusy(true);
    try { const r = await ebsBackupApi.sshGenerateKey({ source_server_id: Number(sourceId) }); setPubKey(r.public_key); setResult(r.message); }
    catch (e) { alert(e?.detail || "Failed"); } finally { setBusy(false); }
  };
  const copyId = async () => {
    if (!sourceId || !targetId || !targetUsername || !targetPassword) return alert("Fill source, target, username and password");
    setBusy(true);
    try { const r = await ebsBackupApi.sshCopyId({ source_server_id: Number(sourceId), target_server_id: Number(targetId), target_username: targetUsername, target_password: targetPassword }); setResult(r.message); setTargetPassword(""); }
    catch (e) { alert(e?.detail || "Failed"); } finally { setBusy(false); }
  };
  const test = async () => {
    if (!sourceId || !targetId || !targetUsername) return alert("Fill source, target and username");
    setBusy(true);
    try { const r = await ebsBackupApi.sshTest({ source_server_id: Number(sourceId), target_server_id: Number(targetId), target_username: targetUsername }); setResult(r.ok ? `✓ ${r.message}` : `✗ ${r.message}: ${r.hint || ""}`); }
    catch (e) { alert(e?.detail || "Failed"); } finally { setBusy(false); }
  };

  return (
    <div>
      <div className="grid grid-cols-3 gap-4 mb-4">
        <Field label="1. Source Server (has/gets the key)">
          <select style={inputStyle} value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            <option value="">Select…</option>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="2. Target Server (receives the key)">
          <select style={inputStyle} value={targetId} onChange={(e) => setTargetId(e.target.value)}>
            <option value="">Select…</option>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Target Username"><input style={inputStyle} value={targetUsername} onChange={(e) => setTargetUsername(e.target.value)} /></Field>
      </div>
      <div className="flex gap-2 flex-wrap mb-3">
        <Btn disabled={busy} onClick={genKey}>1. Generate Key on Source</Btn>
        <input type="password" style={{ ...inputStyle, width: 220 }} placeholder="Target's temporary password" value={targetPassword} onChange={(e) => setTargetPassword(e.target.value)} />
        <Btn disabled={busy} onClick={copyId}>2. Copy Key to Target</Btn>
        <Btn disabled={busy} onClick={test}>3. Test Passwordless</Btn>
      </div>
      {pubKey && <pre style={{ background: "#f8fafc", fontSize: 10.5, padding: 8, borderRadius: 8, overflow: "auto", marginBottom: 8 }}>{pubKey}</pre>}
      {result && <p style={{ fontSize: 12, color: "#334155", whiteSpace: "pre-wrap" }}>{result}</p>}
    </div>
  );
}
