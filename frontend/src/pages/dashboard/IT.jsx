import { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Server, Activity, HardDrive, Clock, AlertTriangle,
  RefreshCw, Settings, Wifi, WifiOff, Loader2, X, CheckCircle,
  PlusCircle, Database, AlertCircle, Maximize2,
  Cpu, TrendingUp, List, Lightbulb, Terminal,
} from "lucide-react";
import {
  AreaChart, Area,
  BarChart, Bar, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList,
} from "recharts";
import { itApi } from "@/api/dashboard";

/* ─── Tab definitions ─────────────────────────────── */

const TABS = [
  { id: "server-monitoring", icon: Server,        color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Server Monitoring" },
  { id: "tablespace-usage",  icon: Activity,      color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Tablespace Usage"  },
  { id: "disk-usage",        icon: HardDrive,     color: "text-yellow-400", bg: "bg-yellow-500/10", activeBorder: "border-yellow-500/40", label: "Disk Usage"        },
  { id: "pending-jobs",      icon: Clock,         color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Pending Jobs"      },
  { id: "workflow-error",    icon: AlertTriangle, color: "text-red-400",    bg: "bg-red-500/10",    activeBorder: "border-red-500/40",    label: "Workflow Error"    },
];

/* ─── Main Page ───────────────────────────────────── */

export default function ITDashboard() {
  const navigate  = useNavigate();
  const location  = useLocation();

  // Derive active tab from URL
  const activeId = TABS.find((t) => location.pathname.endsWith(t.id))?.id ?? "server-monitoring";

  // On first load with no sub-path, redirect to server-monitoring
  useEffect(() => {
    if (location.pathname === "/dashboard/it" || location.pathname === "/dashboard/it/") {
      navigate("/dashboard/it/server-monitoring", { replace: true });
    }
  }, []);

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-2">
        {TABS.map((tab) => {
          const active = activeId === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => navigate(`/dashboard/it/${tab.id}`)}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-all ${
                active
                  ? `${tab.bg} ${tab.activeBorder} ring-1 ring-inset ${tab.activeBorder}`
                  : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
              }`}
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${tab.bg} border ${tab.activeBorder}`}>
                <tab.icon size={15} className={tab.color} />
              </div>
              <span className={`text-sm font-medium truncate ${active ? "text-white" : "text-gray-400"}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Section Panels */}
      {activeId === "server-monitoring" && <ServerMonitoringSection />}
      {activeId === "tablespace-usage"  && <TablespaceSection />}
      {activeId === "disk-usage"        && <DiskUsageSection />}
      {activeId === "pending-jobs"      && <PendingJobsSection />}
      {activeId === "workflow-error"    && <WorkflowErrorSection />}
    </div>
  );
}

/* ─── Section: Server Monitoring ─────────────────── */

// ── Analysis engine (pure JS, no backend needed) ──────────────────────────

const LEVEL_CFG = {
  critical: { bg: "rgba(239,68,68,0.08)",  border: "rgba(239,68,68,0.25)",  dot: "#ef4444", text: "#dc2626", badge: "bg-red-500/20 text-red-500",     icon: "🔴" },
  warning:  { bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.25)", dot: "#f59e0b", text: "#d97706", badge: "bg-amber-500/20 text-amber-500",  icon: "🟡" },
  elevated: { bg: "rgba(251,146,60,0.08)", border: "rgba(251,146,60,0.25)", dot: "#fb923c", text: "#ea580c", badge: "bg-orange-500/20 text-orange-500", icon: "🟠" },
  normal:   { bg: "rgba(34,197,94,0.08)",  border: "rgba(34,197,94,0.25)",  dot: "#22c55e", text: "#16a34a", badge: "bg-green-500/20 text-green-500",   icon: "🟢" },
};

function buildAnalysis(m) {
  if (!m || m.status !== "online") return [];
  const cpuCount  = m.cpu_count || 4;
  const load      = parseFloat(m.load) || 0;
  const loadRatio = cpuCount > 0 ? load / cpuCount : load;
  const swapPct   = m.swap_percent ?? 0;
  const items     = [];

  // CPU
  const cpu = m.cpu;
  let cpuLvl, cpuTitle, cpuMsg, cpuRecs;
  if (cpu >= 90) {
    cpuLvl = "critical"; cpuTitle = "CPU Critical";
    cpuMsg = `CPU sangat tinggi (${cpu}%) — kemungkinan full table scan Oracle, batch besar, atau proses runaway`;
    cpuRecs = ["Lihat Top Processes di bawah untuk identifikasi pelaku", "Di Oracle: periksa v$session + v$sql untuk SQL berat yang berjalan", "Pertimbangkan batasi Oracle EBS Concurrent Request sementara"];
  } else if (cpu >= 70) {
    cpuLvl = "warning"; cpuTitle = "CPU Tinggi";
    cpuMsg = `CPU tinggi (${cpu}%) — jika bertahan > 15 menit, perlu investigasi`;
    cpuRecs = ["Cek apakah ada Oracle batch job terjadwal", "Periksa index rebuild atau gather statistics yang sedang berjalan"];
  } else if (cpu >= 50) {
    cpuLvl = "elevated"; cpuTitle = "CPU Sedang";
    cpuMsg = `CPU (${cpu}%) di atas rata-rata tapi masih dalam toleransi`;
    cpuRecs = [];
  } else {
    cpuLvl = "normal"; cpuTitle = "CPU Normal";
    cpuMsg = `CPU dalam batas aman (${cpu}%)`;
    cpuRecs = [];
  }
  items.push({ key: "cpu", label: "CPU", icon: <Cpu size={12} />, title: cpuTitle, value: `${cpu}%`, level: cpuLvl, msg: cpuMsg, recs: cpuRecs });

  // Memory
  const mem = m.memory_percent;
  let memLvl, memTitle, memMsg, memRecs;
  if (mem >= 95) {
    memLvl = "critical"; memTitle = "Memory Critical";
    memMsg = `Memory hampir habis (${mem}%) — sistem mulai pakai swap, Oracle akan sangat lambat`;
    memRecs = ["Segera kill idle Oracle sessions: ALTER SYSTEM DISCONNECT SESSION 'sid,serial#' IMMEDIATE", "Review Oracle SGA_TARGET — kemungkinan terlalu besar untuk RAM server", "Pertimbangkan restart Oracle app tier jika ada memory leak"];
  } else if (mem >= 85) {
    memLvl = "warning"; memTitle = "Memory Tinggi";
    memMsg = `Memory tinggi (${mem}%) — risiko pakai swap, pantau ketat`;
    memRecs = ["Periksa jumlah Oracle session aktif via v$session", "Cek Oracle PGA_AGGREGATE_TARGET vs kebutuhan aktual"];
  } else if (mem >= 70) {
    memLvl = "elevated"; memTitle = "Memory Sedang";
    memMsg = `Memory (${mem}%) di atas rata-rata — normal untuk Oracle EBS dengan SGA besar`;
    memRecs = [];
  } else {
    memLvl = "normal"; memTitle = "Memory Normal";
    memMsg = `Memory dalam batas aman (${mem}%, ${m.memory_used}/${m.memory_total} GB)`;
    memRecs = [];
  }
  items.push({ key: "mem", label: "Memory", icon: <TrendingUp size={12} />, title: memTitle, value: `${mem}%`, level: memLvl, msg: memMsg, recs: memRecs });

  // Load Average
  let loadLvl, loadTitle, loadMsg, loadRecs;
  if (loadRatio >= 2) {
    loadLvl = "critical"; loadTitle = "Load Critical";
    loadMsg = `Load average sangat tinggi (${load} / ${cpuCount} CPU) — banyak proses antri, kemungkinan I/O bottleneck`;
    loadRecs = ["Ini bukan sekadar CPU tinggi — kemungkinan besar ada disk I/O wait", "Di Oracle: periksa v$session_wait untuk wait event terbesar", "Pertimbangkan kurangi Oracle concurrent request"];
  } else if (loadRatio >= 1) {
    loadLvl = "warning"; loadTitle = "Load Tinggi";
    loadMsg = `Load melebihi jumlah CPU (${load} / ${cpuCount} CPU) — ada antrian proses`;
    loadRecs = ["Periksa Oracle redo log archiving — bottleneck I/O sering dari sini", "Cek apakah ada operasi besar sedang berjalan (backup, export)"];
  } else {
    loadLvl = "normal"; loadTitle = "Load Normal";
    loadMsg = `Load average proporsional (${load} / ${cpuCount} CPU) — tidak ada antrian`;
    loadRecs = [];
  }
  items.push({ key: "load", label: "Load", icon: <Activity size={12} />, title: loadTitle, value: load.toFixed(2), level: loadLvl, msg: loadMsg, recs: loadRecs });

  // Swap
  let swapLvl, swapTitle, swapMsg, swapRecs;
  if (swapPct >= 50) {
    swapLvl = "critical"; swapTitle = "Swap Critical";
    swapMsg = `Swap sangat tinggi (${swapPct}%) — Oracle pasti melambat drastis, risiko OOM kill`;
    swapRecs = ["SEGERA kurangi Oracle SGA — pakai swap = RAM habis", "Kill non-essential processes secepatnya", "Koordinasikan reboot terjadwal dengan user jika tidak ada jalan lain"];
  } else if (swapPct >= 10) {
    swapLvl = "warning"; swapTitle = "Swap Aktif";
    swapMsg = `Swap digunakan (${swapPct}%) — RAM sudah tidak cukup menampung semua proses`;
    swapRecs = ["Kurangi Oracle SGA_TARGET atau PGA_AGGREGATE_TARGET", "Kill idle Oracle sessions untuk bebaskan memory"];
  } else if (swapPct > 0) {
    swapLvl = "elevated"; swapTitle = "Swap Minimal";
    swapMsg = `Sedikit swap digunakan (${swapPct}%) — normal, pantau tren`;
    swapRecs = [];
  } else {
    swapLvl = "normal"; swapTitle = "Swap Tidak Aktif";
    swapMsg = "Tidak ada penggunaan swap — memory masih lebih dari cukup";
    swapRecs = [];
  }
  items.push({ key: "swap", label: "Swap", icon: <HardDrive size={12} />, title: swapTitle, value: `${swapPct}%`, level: swapLvl, msg: swapMsg, recs: swapRecs });

  return items;
}

// ── Auto-refresh selector ────────────────────────────────────────────────

const AUTO_OPTS = [
  { label: "Off", v: 0 },
  { label: "30s", v: 30000 },
  { label: "1m",  v: 60000 },
  { label: "2m",  v: 120000 },
];

function AutoRefreshSelector({ value, onChange }) {
  return (
    <div style={{ display: "flex", background: "#e8edf5", borderRadius: 10, padding: 3, boxShadow: "inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff", gap: 2 }}>
      {AUTO_OPTS.map(o => (
        <button key={o.v} onClick={() => onChange(o.v)} style={{
          padding: "4px 10px", borderRadius: 7, border: "none", cursor: "pointer",
          background: value === o.v ? "#2563eb" : "transparent",
          color: value === o.v ? "#fff" : "#64748b",
          fontSize: 11, fontWeight: 700, transition: "all 0.15s ease",
          boxShadow: value === o.v ? "2px 2px 6px rgba(37,99,235,0.3)" : "none",
        }}>{o.label}</button>
      ))}
    </div>
  );
}

// ── Analysis card ────────────────────────────────────────────────────────

function AnalysisCard({ item }) {
  const [open, setOpen] = useState(item.level !== "normal");
  const lc = LEVEL_CFG[item.level];
  return (
    <div style={{ borderRadius: 14, padding: "11px 14px", background: lc.bg, border: `1.5px solid ${lc.border}`, transition: "all 0.2s" }}>
      <div className="flex items-center justify-between cursor-pointer select-none" onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-2">
          <span style={{ fontSize: 13 }}>{lc.icon}</span>
          <div style={{ color: lc.text }}>
            {item.icon}
          </div>
          <span style={{ fontSize: 11.5, fontWeight: 800, color: lc.text }}>{item.title}</span>
          <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace", marginLeft: 2 }}>{item.value}</span>
        </div>
        <span style={{ fontSize: 9, color: "#94a3b8", marginLeft: 4 }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ marginTop: 8 }}>
          <p style={{ fontSize: 11.5, color: "#475569", lineHeight: 1.55, marginBottom: item.recs.length > 0 ? 8 : 0 }}>{item.msg}</p>
          {item.recs.length > 0 && (
            <>
              <p style={{ fontSize: 9.5, fontWeight: 800, color: lc.text, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>Rekomendasi:</p>
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {item.recs.map((r, i) => (
                  <li key={i} style={{ fontSize: 11, color: "#475569", display: "flex", gap: 6 }}>
                    <span style={{ color: lc.dot, flexShrink: 0, fontWeight: 700 }}>→</span>
                    <span style={{ lineHeight: 1.5 }}>{r}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Top Processes panel ─────────────────────────────────────────────────

function TopProcessesPanel({ processes, loading, onRefresh }) {
  const [tab, setTab] = useState("cpu");

  const rows = processes?.[tab] ?? [];
  const TAB_S = { fontSize: 11, fontWeight: 700, padding: "4px 12px", border: "none", cursor: "pointer", transition: "all 0.15s ease" };

  return (
    <div style={{ marginTop: 20 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Terminal size={13} color="#2563eb" />
          <span style={{ fontSize: 11, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.08em" }}>Top Processes</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Tab selector */}
          <div style={{ display: "flex", background: "#e8edf5", borderRadius: 9, padding: 3, boxShadow: "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff", gap: 2 }}>
            {[["cpu", "▲ CPU"], ["mem", "▲ Memory"]].map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)} style={{
                ...TAB_S,
                borderRadius: 6,
                background: tab === k ? "#2563eb" : "transparent",
                color: tab === k ? "#fff" : "#64748b",
                boxShadow: tab === k ? "2px 2px 5px rgba(37,99,235,0.3)" : "none",
              }}>{l}</button>
            ))}
          </div>
          <ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={onRefresh} />
        </div>
      </div>

      <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff" }}>
        <table className="w-full">
          <thead>
            <tr style={{ background: "linear-gradient(135deg,#dfe5ed,#d8dee8)" }}>
              {["User", "PID", "%CPU", "%MEM", "Process"].map(h => (
                <th key={h} style={{ padding: "10px 13px", fontSize: 10, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap", textAlign: "left", borderBottom: "2px solid rgba(0,0,0,0.06)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processes === null ? (
              <tr><td colSpan={5} style={{ padding: "28px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>Klik Refresh untuk memuat data proses</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: "28px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>Tidak ada data</td></tr>
            ) : (
              rows.map((p, i) => {
                const cpuNum = parseFloat(p.cpu);
                const memNum = parseFloat(p.mem);
                const cpuColor = cpuNum >= 30 ? "#ef4444" : cpuNum >= 10 ? "#f59e0b" : "#22c55e";
                const memColor = memNum >= 30 ? "#ef4444" : memNum >= 10 ? "#f59e0b" : "#22c55e";
                return (
                  <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5", transition: "background 0.12s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(37,99,235,0.06)"}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"}
                  >
                    <td style={{ padding: "8px 13px", fontSize: 12, color: "#334155", fontWeight: 600 }}>{p.user}</td>
                    <td style={{ padding: "8px 13px", fontSize: 11, color: "#64748b", fontFamily: "monospace" }}>{p.pid}</td>
                    <td style={{ padding: "8px 13px" }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: cpuColor, fontFamily: "monospace" }}>{p.cpu}%</span>
                    </td>
                    <td style={{ padding: "8px 13px" }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: memColor, fontFamily: "monospace" }}>{p.mem}%</span>
                    </td>
                    <td style={{ padding: "8px 13px", fontSize: 12, color: "#1e293b", fontFamily: "monospace", fontWeight: 600 }}>{p.command}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main section ─────────────────────────────────────────────────────────

function ServerMonitoringSection() {
  const [config,       setConfig]       = useState(null);
  const [metrics,      setMetrics]      = useState(null);
  const [history,      setHistory]      = useState([]);
  const [loading,      setLoading]      = useState(false);
  const [autoInterval, setAutoInterval] = useState(0);    // 0 = off
  const [processes,    setProcesses]    = useState(null); // null = not yet loaded
  const [procLoading,  setProcLoading]  = useState(false);
  const [showModal,    setShowModal]    = useState(false);
  const [testResult,   setTestResult]   = useState(null);

  useEffect(() => {
    itApi.getServerConfig().then(res => setConfig(res.data)).catch(() => {});
  }, []);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const res = await itApi.getServerMetrics();
      const d = res.data;
      setMetrics(d);
      if (d.status === "online") {
        setHistory(prev => [
          ...prev.slice(-29),
          { ts: new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }), cpu: d.cpu, mem: d.memory_percent, load: parseFloat(d.load) || 0 },
        ]);
      }
    } catch (e) {
      setMetrics({ status: "error", error: String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchProcesses = useCallback(async () => {
    setProcLoading(true);
    try {
      const res = await itApi.getTopProcesses();
      if (res?.success) setProcesses({ cpu: res.cpu, mem: res.mem });
    } catch (_) {}
    finally { setProcLoading(false); }
  }, []);

  // Fetch both metrics + processes in parallel on every refresh
  const fetchAll = useCallback(async () => {
    await Promise.all([fetchMetrics(), fetchProcesses()]);
  }, [fetchMetrics, fetchProcesses]);

  // Auto-refresh at selected interval
  useEffect(() => {
    if (autoInterval === 0) return;
    fetchAll();
    const id = setInterval(fetchAll, autoInterval);
    return () => clearInterval(id);
  }, [autoInterval, fetchAll]);

  const statusOnline  = metrics?.status === "online";
  const statusError   = metrics?.status === "error";
  const statusNotConf = metrics?.status === "not_configured";
  const analysis      = buildAnalysis(metrics);

  // Overall health badge
  const worstLevel = analysis.reduce((a, b) => {
    const order = { critical: 3, warning: 2, elevated: 1, normal: 0 };
    return (order[b.level] ?? 0) > (order[a.level] ?? 0) ? b : a;
  }, { level: "normal" });

  return (
    <>
      <SectionCard
        title="Real-time Server Monitoring"
        action={
          <div className="flex items-center gap-2">
            <AutoRefreshSelector value={autoInterval} onChange={setAutoInterval} />
            <ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={fetchAll} />
          </div>
        }
      >
        {/* Config bar */}
        <div className="mb-5 flex items-center justify-between p-4 rounded-lg bg-gray-800/50 border border-gray-700">
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">Server</span>
            <span className="text-sm font-medium text-gray-200">{config ? `${config.ip}:${config.port}` : "—"}</span>
            {config?.username && <span className="text-xs text-gray-500">({config.username})</span>}
            {config?.has_password === false && <span className="text-xs text-amber-400">Password not set</span>}
          </div>
          <ActionBtn icon={Settings} label="Configure" color="bg-gray-700 hover:bg-gray-600" onClick={() => setShowModal(true)} />
        </div>

        {/* Status banners */}
        {statusError && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            <WifiOff size={14} /> {metrics.error}
          </div>
        )}
        {statusNotConf && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm">
            <Settings size={14} /> SSH belum dikonfigurasi. Klik Configure untuk memasukkan kredensial.
          </div>
        )}

        {/* KPI Cards — now with swap */}
        <div className="grid grid-cols-4 gap-3 mb-5">
          <MetricCard label="CPU Usage"     value={metrics ? `${metrics.cpu}%`             : "—"} sub={`Load: ${metrics?.load ?? "—"} / ${metrics?.cpu_count ?? "—"} CPU`}      gradient="from-indigo-500 to-purple-600" />
          <MetricCard label="Memory Usage"  value={metrics ? `${metrics.memory_percent}%`  : "—"} sub={metrics ? `${metrics.memory_used} / ${metrics.memory_total} GB`  : "—"}   gradient="from-pink-500 to-rose-500" />
          <MetricCard label="Swap Usage"    value={metrics ? `${metrics.swap_percent ?? 0}%`: "—"} sub={metrics ? `${metrics.swap_used_mb ?? 0} / ${metrics.swap_total_mb ?? 0} MB`: "—"} gradient={metrics?.swap_percent > 10 ? "from-orange-500 to-red-500" : "from-teal-500 to-cyan-500"} />
          <MetricCard
            label="Server Status"
            value={
              <span className="flex items-center justify-center gap-2">
                {statusOnline  ? <><Wifi size={16} />Online</>    : null}
                {statusError   ? <><WifiOff size={16} />Error</>   : null}
                {!metrics || statusNotConf ? <><Wifi size={16} />Waiting</> : null}
              </span>
            }
            sub={`Uptime: ${metrics?.uptime ?? "—"}`}
            gradient={statusOnline ? "from-cyan-500 to-blue-500" : statusError ? "from-red-600 to-red-800" : "from-gray-600 to-gray-700"}
          />
        </div>

        {/* Charts */}
        <div className="space-y-4">
          <MiniChart title="CPU Usage History (%)"    data={history} dataKey="cpu"  color="#818cf8" domain={[0, 100]} />
          <MiniChart title="Memory Usage History (%)" data={history} dataKey="mem"  color="#f472b6" domain={[0, 100]} />
          <MiniChart title="Load Average History"     data={history} dataKey="load" color="#22d3ee" />
        </div>

        {/* ── Analysis & Recommendations ── */}
        {statusOnline && analysis.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb size={13} color="#f59e0b" />
              <span style={{ fontSize: 11, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.08em" }}>Analisa & Rekomendasi</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${LEVEL_CFG[worstLevel.level].badge}`}>
                {worstLevel.level === "critical" ? "Ada masalah kritis"
                  : worstLevel.level === "warning"  ? "Perlu perhatian"
                  : worstLevel.level === "elevated" ? "Normal, pantau tren"
                  : "Sistem sehat ✓"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {analysis.map(item => <AnalysisCard key={item.key} item={item} />)}
            </div>
          </div>
        )}

        {/* ── Top Processes ── */}
        {statusOnline && (
          <TopProcessesPanel processes={processes} loading={procLoading} onRefresh={fetchProcesses} />
        )}
      </SectionCard>

      {showModal && (
        <ConfigModal
          initial={config}
          onClose={() => { setShowModal(false); setTestResult(null); }}
          onSaved={(cfg) => { setConfig(cfg); setShowModal(false); setTestResult(null); }}
          onTest={async (cfg) => {
            await itApi.saveServerConfig(cfg);
            const res = await itApi.testConnection();
            setTestResult(res);
          }}
          testResult={testResult}
        />
      )}
    </>
  );
}

/* ─── Configure Modal ─────────────────────────────── */

function ConfigModal({ initial, onClose, onSaved, onTest, testResult }) {
  const [form,    setForm]    = useState({
    ip:       initial?.ip       ?? "172.21.2.201",
    port:     initial?.port     ?? 22,
    username: initial?.username ?? "",
    password: "",
  });
  const [saving,  setSaving]  = useState(false);
  const [testing, setTesting] = useState(false);

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await itApi.saveServerConfig({ ...form, port: Number(form.port) });
      onSaved({ ip: form.ip, port: Number(form.port), username: form.username, has_password: true });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await onTest({ ...form, port: Number(form.port) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)" }}>
      <div style={{
        width: "100%", maxWidth: 420, borderRadius: 20,
        background: "#e8edf5",
        boxShadow: "10px 10px 30px #b0b5c3, -10px -10px 30px #ffffff",
      }}>
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>SSH Server Configuration</h3>
          <button onClick={onClose} style={{ color: "#94a3b8", transition: "color 0.15s" }}
            onMouseEnter={e => e.currentTarget.style.color = "#1e293b"}
            onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}>
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <Field label="Server IP">
            <input className={INPUT} value={form.ip}       onChange={set("ip")}       placeholder="172.21.2.201" />
          </Field>
          <Field label="Port">
            <input className={INPUT} value={form.port}     onChange={set("port")}     type="number" placeholder="22" />
          </Field>
          <Field label="Username">
            <input className={INPUT} value={form.username} onChange={set("username")} placeholder="oraprod" />
          </Field>
          <Field label="Password">
            <input className={INPUT} value={form.password} onChange={set("password")} type="password" placeholder="Leave blank to keep existing" />
          </Field>

          {testResult && (
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
              testResult.success
                ? "bg-green-500/10 border border-green-500/30 text-green-400"
                : "bg-red-500/10 border border-red-500/30 text-red-400"
            }`}>
              {testResult.success ? <CheckCircle size={14} /> : <X size={14} />}
              {testResult.success ? testResult.message : testResult.error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 px-5 py-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
          <ActionBtn
            icon={testing ? Loader2 : Wifi}
            label={testing ? "Testing..." : "Test Connection"}
            color="bg-gray-700 hover:bg-gray-600"
            onClick={handleTest}
          />
          <ActionBtn
            icon={saving ? Loader2 : CheckCircle}
            label={saving ? "Saving..." : "Save"}
            color="bg-blue-600 hover:bg-blue-700"
            onClick={handleSave}
          />
        </div>
      </div>
    </div>
  );
}

const INPUT = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500";

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  );
}

/* ─── Mini Chart ──────────────────────────────────── */

function MiniChart({ title, data, dataKey, color, domain }) {
  return (
    <div>
      <p style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>{title}</p>
      {data.length === 0 ? (
        <div style={{
          height: 80, borderRadius: 14,
          background: "#e8edf5",
          boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>Start monitoring to view charts</span>
        </div>
      ) : (
        <div style={{
          height: 80, borderRadius: 14, overflow: "hidden",
          background: "#e8edf5",
          boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
        }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -30 }}>
              <defs>
                <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={color} stopOpacity={0}   />
                </linearGradient>
              </defs>
              <XAxis dataKey="ts" tick={{ fontSize: 9, fill: "#6b7280" }} interval="preserveStartEnd" />
              <YAxis domain={domain} tick={{ fontSize: 9, fill: "#6b7280" }} />
              <Tooltip
                contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 6, fontSize: 11, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                labelStyle={{ color: "#9ca3af" }}
                itemStyle={{ color: color }}
              />
              <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} fill={`url(#grad-${dataKey})`} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/* ─── Section: Tablespace ─────────────────────────── */

const TS_COLORS = {
  Critical: { bar: "#ef4444", badge: "bg-red-500/20 text-red-400" },
  Warning:  { bar: "#f59e0b", badge: "bg-amber-500/20 text-amber-400" },
  Normal:   { bar: "#22c55e", badge: "bg-green-500/20 text-green-400" },
};

function TablespaceSection() {
  const [data,       setData]       = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [modalTs,       setModalTs]       = useState(null); // Add Datafile modal
  const [resizeModalTs, setResizeModalTs] = useState(null); // Resize Datafile modal
  const [successMsg,    setSuccessMsg]    = useState(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await itApi.getTablespace();
      if (res.success) {
        setData(res.data ?? []);
      } else {
        setError(res.error ?? "Failed to load data");
      }
    } catch (e) {
      setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  };

  const handleSuccess = (msg) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 6000);
    refresh(); // reload usage after adding datafile
  };

  const chartData = data.map((r) => ({
    name:   r.tablespace_name,
    pct:    parseFloat(r.usage_percent),
    status: r.status,
  }));

  return (
    <>
      <SectionCard
        title="Top 5 Tablespaces by Usage"
        action={<ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={refresh} />}
      >
        {successMsg && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-600 text-sm">
            <CheckCircle size={14} /> {successMsg}
          </div>
        )}
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Horizontal Bar Chart */}
        {chartData.length > 0 ? (
          <div className="mb-5 h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 4, right: 48, bottom: 4, left: 8 }}
              >
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: "#6b7280" }} tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10, fill: "#475569" }} />
                <Tooltip
                  formatter={(v) => [`${v}%`, "Usage"]}
                  contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 6, fontSize: 11, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                  labelStyle={{ color: "#9ca3af" }}
                />
                <Bar dataKey="pct" radius={[0, 4, 4, 0]} maxBarSize={22}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={TS_COLORS[entry.status]?.bar ?? "#22c55e"} />
                  ))}
                  <LabelList dataKey="pct" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: "#9ca3af" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <ChartPlaceholder label="Click Refresh to load tablespace data" className="mb-5" />
        )}

        {/* Table */}
        <DataTable
          headers={["Tablespace Name", "Usage (%)", "Used (GB)", "Total (GB)", "Status", "Action"]}
          rows={data.map((r) => [
            r.tablespace_name,
            <UsageBar key={r.tablespace_name} pct={parseFloat(r.usage_percent)} />,
            `${r.used_gb} GB`,
            `${r.total_gb} GB`,
            <span key={r.tablespace_name + "-s"} className={`px-2 py-0.5 rounded-full text-xs font-medium ${TS_COLORS[r.status]?.badge}`}>
              {r.status}
            </span>,
            <div key={r.tablespace_name + "-actions"} style={{ display: "flex", gap: 5 }}>
              <button
                onClick={() => setModalTs(r)}
                title="Tambah Datafile baru"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "4px 9px", borderRadius: 8, border: "none",
                  background: "#e8edf5",
                  boxShadow: "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff",
                  color: "#2563eb", fontSize: 11, fontWeight: 700,
                  cursor: "pointer", whiteSpace: "nowrap",
                  transition: "box-shadow 0.15s ease",
                }}
                onMouseDown={e => e.currentTarget.style.boxShadow = "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff"}
                onMouseUp={e => e.currentTarget.style.boxShadow = "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff"}
                onMouseLeave={e => e.currentTarget.style.boxShadow = "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff"}
              >
                <PlusCircle size={11} /> Tambah File
              </button>
              <button
                onClick={() => setResizeModalTs(r)}
                title="Extend ukuran datafile yang sudah ada"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "4px 9px", borderRadius: 8, border: "none",
                  background: "#e8edf5",
                  boxShadow: "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff",
                  color: "#7c3aed", fontSize: 11, fontWeight: 700,
                  cursor: "pointer", whiteSpace: "nowrap",
                  transition: "box-shadow 0.15s ease",
                }}
                onMouseDown={e => e.currentTarget.style.boxShadow = "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff"}
                onMouseUp={e => e.currentTarget.style.boxShadow = "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff"}
                onMouseLeave={e => e.currentTarget.style.boxShadow = "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff"}
              >
                <Maximize2 size={11} /> Resize File
              </button>
            </div>,
          ])}
          placeholder="Click Refresh to load tablespace data"
        />
      </SectionCard>

      {/* Add Datafile Modal */}
      {modalTs && (
        <AddDatafileModal
          tablespace={modalTs}
          onClose={() => setModalTs(null)}
          onSuccess={handleSuccess}
        />
      )}

      {/* Resize Datafile Modal */}
      {resizeModalTs && (
        <ResizeDatafileModal
          tablespace={resizeModalTs}
          onClose={() => setResizeModalTs(null)}
          onSuccess={handleSuccess}
        />
      )}
    </>
  );
}

/* ─── Add Datafile Modal ─────────────────────────────── */

function AddDatafileModal({ tablespace, onClose, onSuccess }) {
  const [files,       setFiles]       = useState([]);
  const [loadingFiles,setLoadingFiles] = useState(true);
  const [filePath,    setFilePath]    = useState("");
  const [sizeValue,   setSizeValue]   = useState("500");
  const [sizeUnit,    setSizeUnit]    = useState("MB");
  const [autoextend,  setAutoextend]  = useState(false);
  const [step,        setStep]        = useState("form"); // "form" | "confirm"
  const [saving,      setSaving]      = useState(false);
  const [saveError,   setSaveError]   = useState(null);

  // Load existing datafiles for reference
  useEffect(() => {
    itApi.getTablespaceDatafiles(tablespace.tablespace_name)
      .then(res => {
        if (res?.success) {
          setFiles(res.data ?? []);
          // Auto-suggest path based on last file
          const arr = res.data ?? [];
          if (arr.length > 0) {
            const last = arr[arr.length - 1].file_name ?? "";
            const suggested = last.replace(
              /(\d+)(\.dbf)$/i,
              (_, n, ext) => `${String(parseInt(n, 10) + 1).padStart(String(n).length, "0")}${ext}`
            );
            setFilePath(suggested !== last ? suggested : last.replace(/\.dbf$/i, "_ext.dbf"));
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoadingFiles(false));
  }, [tablespace.tablespace_name]);

  const sizeNum   = parseFloat(sizeValue) || 0;
  const canSubmit = filePath.trim().length > 0 && sizeNum > 0;

  const ddlPreview = canSubmit
    ? `ALTER TABLESPACE ${tablespace.tablespace_name} ADD DATAFILE '${filePath.trim()}' SIZE ${sizeNum}${sizeUnit}${autoextend ? " AUTOEXTEND ON NEXT 100M MAXSIZE UNLIMITED" : ""}`
    : "";

  const handleConfirm = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await itApi.addTablespaceDatafile({
        tablespace_name: tablespace.tablespace_name,
        file_path:       filePath.trim(),
        size_value:      sizeNum,
        size_unit:       sizeUnit,
        autoextend,
      });
      if (res?.success) {
        onSuccess?.(res.message);
        onClose();
      } else {
        setSaveError(res?.error ?? "Gagal menambahkan datafile");
        setStep("form");
      }
    } catch (e) {
      setSaveError(String(e?.message ?? e));
      setStep("form");
    } finally {
      setSaving(false);
    }
  };

  const neu    = { background: "#e8edf5" };
  const shadow = "10px 10px 30px #b0b5c3, -10px -10px 30px #ffffff";
  const divider= { borderBottom: "1px solid rgba(0,0,0,0.06)" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.35)", backdropFilter: "blur(4px)" }}>
      <div style={{ width: "100%", maxWidth: 520, borderRadius: 20, ...neu, boxShadow: shadow }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={divider}>
          <div className="flex items-center gap-2">
            <Database size={15} color="#2563eb" />
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
              {step === "form" ? "Tambah Datafile" : "Konfirmasi DDL"} — {tablespace.tablespace_name}
            </h3>
          </div>
          <button onClick={onClose} style={{ color: "#94a3b8" }}
            onMouseEnter={e => e.currentTarget.style.color = "#1e293b"}
            onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}>
            <X size={16} />
          </button>
        </div>

        {step === "form" ? (
          <>
            <div className="p-5 space-y-4">

              {/* Existing files reference */}
              <div>
                <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Datafile yang sudah ada:
                </p>
                <div style={{
                  borderRadius: 10, padding: "10px 12px",
                  background: "#e8edf5",
                  boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                  maxHeight: 100, overflowY: "auto",
                }}>
                  {loadingFiles ? (
                    <p style={{ fontSize: 11, color: "#94a3b8" }}>Memuat...</p>
                  ) : files.length === 0 ? (
                    <p style={{ fontSize: 11, color: "#94a3b8" }}>Tidak ada datafile ditemukan</p>
                  ) : (
                    files.map((f, i) => (
                      <div key={i} style={{ fontSize: 11, color: "#475569", marginBottom: i < files.length - 1 ? 4 : 0, fontFamily: "monospace" }}>
                        <span style={{ color: "#2563eb" }}>•</span> {f.file_name}
                        <span style={{ color: "#94a3b8", marginLeft: 8 }}>
                          ({f.size_gb ?? f.size_mb} {f.size_gb != null ? "GB" : "MB"}, AUTOEXTEND: {f.autoextensible})
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* File path */}
              <Field label="Lokasi File Baru">
                <input
                  className={INPUT}
                  value={filePath}
                  onChange={e => setFilePath(e.target.value)}
                  placeholder="/u01/app/oracle/oradata/CKDO/tablespace01.dbf"
                  style={{ fontFamily: "monospace", fontSize: 12 }}
                />
              </Field>

              {/* Size */}
              <Field label="Ukuran">
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    className={INPUT}
                    value={sizeValue}
                    onChange={e => setSizeValue(e.target.value)}
                    type="number"
                    min="1"
                    max="102400"
                    placeholder="500"
                    style={{ flex: 1 }}
                  />
                  <select
                    value={sizeUnit}
                    onChange={e => setSizeUnit(e.target.value)}
                    className={INPUT}
                    style={{ width: 80, flex: "none" }}
                  >
                    <option value="MB">MB</option>
                    <option value="GB">GB</option>
                  </select>
                </div>
              </Field>

              {/* Autoextend */}
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input
                  type="checkbox"
                  id="autoextend"
                  checked={autoextend}
                  onChange={e => setAutoextend(e.target.checked)}
                  style={{ width: 14, height: 14, cursor: "pointer", accentColor: "#2563eb" }}
                />
                <label htmlFor="autoextend" style={{ fontSize: 12, color: "#475569", cursor: "pointer", userSelect: "none" }}>
                  AUTOEXTEND ON <span style={{ color: "#94a3b8" }}>(NEXT 100M, MAXSIZE UNLIMITED)</span>
                </label>
              </div>

              {/* DDL Preview */}
              {ddlPreview && (
                <div>
                  <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Preview DDL:
                  </p>
                  <div style={{
                    borderRadius: 10, padding: "10px 12px",
                    background: "#e8edf5",
                    boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                    fontSize: 11, fontFamily: "monospace", color: "#1e40af",
                    wordBreak: "break-all", lineHeight: 1.6,
                  }}>
                    {ddlPreview}
                  </div>
                </div>
              )}

              {saveError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                  <AlertCircle size={12} /> {saveError}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 px-5 py-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
              <ActionBtn icon={X} label="Batal" color="bg-gray-700 hover:bg-gray-600" onClick={onClose} />
              <ActionBtn
                icon={PlusCircle}
                label="Lanjut ke Konfirmasi"
                color={canSubmit ? "bg-blue-600 hover:bg-blue-700" : "bg-gray-500 cursor-not-allowed"}
                onClick={() => canSubmit && setStep("confirm")}
              />
            </div>
          </>
        ) : (
          <>
            <div className="p-5 space-y-4">

              {/* Warning */}
              <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <AlertCircle size={16} color="#d97706" style={{ flexShrink: 0, marginTop: 1 }} />
                <div>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 2 }}>Perhatian</p>
                  <p style={{ fontSize: 11.5, color: "#78350f", lineHeight: 1.5 }}>
                    DDL di bawah akan dieksekusi langsung ke database Oracle. Operasi ini tidak dapat dibatalkan setelah dijalankan.
                  </p>
                </div>
              </div>

              {/* DDL box */}
              <div>
                <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  DDL yang akan dijalankan:
                </p>
                <div style={{
                  borderRadius: 10, padding: "12px 14px",
                  background: "#e8edf5",
                  boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                  fontSize: 12, fontFamily: "monospace", color: "#1e40af",
                  wordBreak: "break-all", lineHeight: 1.7,
                }}>
                  {ddlPreview}
                </div>
              </div>

              {/* Details */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[
                  ["Tablespace",  tablespace.tablespace_name],
                  ["Ukuran",      `${sizeNum} ${sizeUnit}`],
                  ["Autoextend",  autoextend ? "ON (NEXT 100M, MAXSIZE UNLIMITED)" : "OFF"],
                  ["Penggunaan",  `${tablespace.usage_percent}% (${tablespace.used_gb} / ${tablespace.total_gb} GB)`],
                ].map(([k, v]) => (
                  <div key={k} style={{
                    borderRadius: 8, padding: "8px 12px",
                    background: "#e8edf5",
                    boxShadow: "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff",
                  }}>
                    <p style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>{k}</p>
                    <p style={{ fontSize: 11.5, color: "#1e293b", fontWeight: 600 }}>{v}</p>
                  </div>
                ))}
              </div>

              {saveError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                  <AlertCircle size={12} /> {saveError}
                </div>
              )}
            </div>

            <div className="flex justify-between px-5 py-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
              <ActionBtn icon={X} label="Kembali" color="bg-gray-700 hover:bg-gray-600" onClick={() => setStep("form")} />
              <ActionBtn
                icon={saving ? Loader2 : CheckCircle}
                label={saving ? "Menjalankan DDL..." : "Ya, Jalankan DDL"}
                color="bg-green-600 hover:bg-green-700"
                onClick={handleConfirm}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Resize Datafile Modal ──────────────────────────── */

function ResizeDatafileModal({ tablespace, onClose, onSuccess }) {
  const [files,        setFiles]        = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [selected,     setSelected]     = useState(null);  // file object
  const [addValue,     setAddValue]     = useState("1");
  const [addUnit,      setAddUnit]      = useState("GB");
  const [step,         setStep]         = useState("form"); // "form" | "confirm"
  const [saving,       setSaving]       = useState(false);
  const [saveError,    setSaveError]    = useState(null);

  useEffect(() => {
    itApi.getTablespaceDatafiles(tablespace.tablespace_name)
      .then(res => {
        if (res?.success) {
          const arr = res.data ?? [];
          setFiles(arr);
          if (arr.length > 0) setSelected(arr[0]);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingFiles(false));
  }, [tablespace.tablespace_name]);

  const addNum    = parseFloat(addValue) || 0;
  const addMb     = addNum * (addUnit === "GB" ? 1024 : 1);
  const currMb    = selected ? parseFloat(selected.size_mb) : 0;
  const newTotalMb = currMb + addMb;

  const fmtSize = (mb) => mb >= 1024
    ? `${(mb / 1024).toFixed(2)} GB`
    : `${mb.toFixed(0)} MB`;

  const canSubmit = selected && addNum > 0;

  const ddlPreview = canSubmit
    ? `ALTER DATABASE DATAFILE '${selected.file_name}' RESIZE ${Math.round(newTotalMb)}M`
    : "";

  const handleConfirm = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await itApi.resizeTablespaceDatafile({
        file_path: selected.file_name,
        add_value: addNum,
        add_unit:  addUnit,
      });
      if (res?.success) {
        onSuccess?.(res.message);
        onClose();
      } else {
        setSaveError(res?.error ?? "Gagal resize datafile");
        setStep("form");
      }
    } catch (e) {
      setSaveError(String(e?.message ?? e));
      setStep("form");
    } finally {
      setSaving(false);
    }
  };

  const neu    = { background: "#e8edf5" };
  const shadow = "10px 10px 30px #b0b5c3, -10px -10px 30px #ffffff";
  const divider= { borderBottom: "1px solid rgba(0,0,0,0.06)" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.35)", backdropFilter: "blur(4px)" }}>
      <div style={{ width: "100%", maxWidth: 540, borderRadius: 20, ...neu, boxShadow: shadow }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={divider}>
          <div className="flex items-center gap-2">
            <Maximize2 size={15} color="#7c3aed" />
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
              {step === "form" ? "Resize Datafile" : "Konfirmasi DDL"} — {tablespace.tablespace_name}
            </h3>
          </div>
          <button onClick={onClose} style={{ color: "#94a3b8" }}
            onMouseEnter={e => e.currentTarget.style.color = "#1e293b"}
            onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}>
            <X size={16} />
          </button>
        </div>

        {step === "form" ? (
          <>
            <div className="p-5 space-y-4">

              {/* Pilih datafile */}
              <div>
                <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Pilih Datafile:
                </p>
                {loadingFiles ? (
                  <p style={{ fontSize: 11, color: "#94a3b8", padding: "10px 0" }}>Memuat datafile...</p>
                ) : files.length === 0 ? (
                  <p style={{ fontSize: 11, color: "#ef4444", padding: "10px 0" }}>Tidak ada datafile ditemukan di tablespace ini.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {files.map((f, i) => {
                      const isSelected = selected?.file_name === f.file_name;
                      return (
                        <div
                          key={i}
                          onClick={() => setSelected(f)}
                          style={{
                            borderRadius: 10, padding: "10px 14px",
                            background: "#e8edf5",
                            boxShadow: isSelected
                              ? "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff"
                              : "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff",
                            cursor: "pointer",
                            border: isSelected ? "1.5px solid #7c3aed" : "1.5px solid transparent",
                            transition: "all 0.15s ease",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{
                              width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                              background: isSelected ? "#7c3aed" : "#c5cad8",
                              boxShadow: isSelected ? "0 0 5px #7c3aed" : "none",
                              transition: "all 0.15s ease",
                            }} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ fontSize: 11, fontFamily: "monospace", color: "#1e293b", fontWeight: isSelected ? 700 : 500, wordBreak: "break-all" }}>
                                {f.file_name}
                              </p>
                              <p style={{ fontSize: 10.5, color: "#64748b", marginTop: 2 }}>
                                Ukuran: <strong>{fmtSize(parseFloat(f.size_mb))}</strong>
                                <span style={{ marginLeft: 10, color: "#94a3b8" }}>AUTOEXTEND: {f.autoextensible}</span>
                                <span style={{ marginLeft: 10, color: "#94a3b8" }}>Status: {f.status}</span>
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Tambah ukuran */}
              <Field label="Tambah Ukuran">
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    className={INPUT}
                    value={addValue}
                    onChange={e => setAddValue(e.target.value)}
                    type="number"
                    min="1"
                    max="102400"
                    placeholder="1"
                    style={{ flex: 1 }}
                  />
                  <select
                    value={addUnit}
                    onChange={e => setAddUnit(e.target.value)}
                    className={INPUT}
                    style={{ width: 80, flex: "none" }}
                  >
                    <option value="MB">MB</option>
                    <option value="GB">GB</option>
                  </select>
                </div>
              </Field>

              {/* Size summary */}
              {selected && addNum > 0 && (
                <div style={{
                  borderRadius: 12, padding: "12px 14px",
                  background: "#e8edf5",
                  boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                  display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10,
                }}>
                  {[
                    { label: "Ukuran Sekarang", value: fmtSize(currMb),     color: "#64748b"  },
                    { label: `+ Tambahan`,       value: fmtSize(addMb),      color: "#7c3aed"  },
                    { label: "Ukuran Baru",      value: fmtSize(newTotalMb), color: "#16a34a"  },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{ textAlign: "center" }}>
                      <p style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>{label}</p>
                      <p style={{ fontSize: 14, fontWeight: 800, color }}>{value}</p>
                      <p style={{ fontSize: 9.5, color: "#94a3b8" }}>({Math.round(color === "#7c3aed" ? addMb : color === "#16a34a" ? newTotalMb : currMb).toLocaleString()} MB)</p>
                    </div>
                  ))}
                </div>
              )}

              {/* DDL Preview */}
              {ddlPreview && (
                <div>
                  <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Preview DDL:
                  </p>
                  <div style={{
                    borderRadius: 10, padding: "10px 12px",
                    background: "#e8edf5",
                    boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                    fontSize: 11, fontFamily: "monospace", color: "#5b21b6",
                    wordBreak: "break-all", lineHeight: 1.6,
                  }}>
                    {ddlPreview}
                  </div>
                </div>
              )}

              {saveError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                  <AlertCircle size={12} /> {saveError}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 px-5 py-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
              <ActionBtn icon={X} label="Batal" color="bg-gray-700 hover:bg-gray-600" onClick={onClose} />
              <ActionBtn
                icon={Maximize2}
                label="Lanjut ke Konfirmasi"
                color={canSubmit ? "bg-purple-600 hover:bg-purple-700" : "bg-gray-500 cursor-not-allowed"}
                onClick={() => canSubmit && setStep("confirm")}
              />
            </div>
          </>
        ) : (
          <>
            <div className="p-5 space-y-4">

              {/* Warning */}
              <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <AlertCircle size={16} color="#d97706" style={{ flexShrink: 0, marginTop: 1 }} />
                <div>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 2 }}>Perhatian</p>
                  <p style={{ fontSize: 11.5, color: "#78350f", lineHeight: 1.5 }}>
                    DDL di bawah akan mengubah ukuran datafile secara langsung di database Oracle. Ukuran tidak dapat dikurangi setelah di-resize.
                  </p>
                </div>
              </div>

              {/* DDL box */}
              <div>
                <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  DDL yang akan dijalankan:
                </p>
                <div style={{
                  borderRadius: 10, padding: "12px 14px",
                  background: "#e8edf5",
                  boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
                  fontSize: 12, fontFamily: "monospace", color: "#5b21b6",
                  wordBreak: "break-all", lineHeight: 1.7,
                }}>
                  {ddlPreview}
                </div>
              </div>

              {/* Details grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[
                  ["Tablespace",      tablespace.tablespace_name],
                  ["Datafile",        selected?.file_name?.split("/").pop() ?? "-"],
                  ["Ukuran Sekarang", fmtSize(currMb)],
                  ["Ukuran Baru",     fmtSize(newTotalMb)],
                  ["Tambahan",        `+${fmtSize(addMb)} (+${Math.round(addMb).toLocaleString()} MB)`],
                  ["Penggunaan TS",   `${tablespace.usage_percent}%`],
                ].map(([k, v]) => (
                  <div key={k} style={{
                    borderRadius: 8, padding: "8px 12px",
                    background: "#e8edf5",
                    boxShadow: "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff",
                  }}>
                    <p style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>{k}</p>
                    <p style={{ fontSize: 11.5, color: "#1e293b", fontWeight: 600, wordBreak: "break-all" }}>{v}</p>
                  </div>
                ))}
              </div>

              {saveError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                  <AlertCircle size={12} /> {saveError}
                </div>
              )}
            </div>

            <div className="flex justify-between px-5 py-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
              <ActionBtn icon={X} label="Kembali" color="bg-gray-700 hover:bg-gray-600" onClick={() => setStep("form")} />
              <ActionBtn
                icon={saving ? Loader2 : CheckCircle}
                label={saving ? "Menjalankan DDL..." : "Ya, Jalankan DDL"}
                color="bg-green-600 hover:bg-green-700"
                onClick={handleConfirm}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Section: Disk Usage ─────────────────────────── */

const DISK_SERVERS_CFG = [
  { key: "db",  label: "DB Server",  ip: "172.21.2.201" },
  { key: "app", label: "App Server", ip: "172.21.2.202" },
];

function DiskUsageSection() {
  const [serverData, setServerData] = useState({ db: null, app: null }); // null=not loaded, {status,rows,error}
  const [loading,    setLoading]    = useState(false);
  const [globalErr,  setGlobalErr]  = useState("");
  const [activeTab,  setActiveTab]  = useState("db");

  const refresh = async () => {
    setLoading(true); setGlobalErr("");
    try {
      const res = await itApi.getDiskUsage();
      if (res?.success) {
        const map = {};
        (res.servers ?? []).forEach(s => { map[s.key] = s; });
        setServerData(prev => ({ ...prev, ...map }));
      } else {
        setGlobalErr(res?.error || "Failed to fetch disk usage");
      }
    } catch (e) {
      setGlobalErr(e?.detail || e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const active = serverData[activeTab];
  const rows   = active?.rows ?? [];

  const chartData = [...rows]
    .sort((a, b) => b.used_gb - a.used_gb)
    .slice(0, 8)
    .map(r => ({ name: r.mountpoint, used: r.used_gb, free: r.free_gb, pct: r.usage_percent }));

  const barColor = (pct) => pct >= 90 ? "#f87171" : pct >= 70 ? "#fbbf24" : "#34d399";

  return (
    <SectionCard
      title="Disk Usage — DB & App Servers"
      subtitle="SSH df -P  ·  172.21.2.201 (DB)  ·  172.21.2.202 (App)"
      action={<ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-yellow-600 hover:bg-yellow-700" onClick={refresh} />}
    >
      {/* ── Server tabs — always visible ── */}
      <div className="flex gap-2 mb-4">
        {DISK_SERVERS_CFG.map(s => {
          const sd = serverData[s.key];
          const dotColor = !sd ? "bg-gray-600" : sd.status === "online" ? "bg-green-400" : "bg-red-400";
          return (
            <button key={s.key} onClick={() => setActiveTab(s.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                activeTab === s.key
                  ? "bg-yellow-500/10 border-yellow-500/40 text-yellow-400"
                  : "bg-gray-800/60 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"
              }`}>
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColor}`} />
              <span className="font-semibold">{s.label}</span>
              <span className="font-mono opacity-60">{s.ip}</span>
            </button>
          );
        })}
      </div>

      {/* ── Global error ── */}
      {globalErr && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
          <X size={12} />{globalErr}
        </div>
      )}

      {/* ── Loading ── */}
      {loading && (
        <div className="flex items-center justify-center py-10 text-gray-500 text-sm gap-2">
          <Loader2 size={16} className="animate-spin" /> Connecting to both servers via SSH…
        </div>
      )}

      {/* ── Not yet loaded ── */}
      {!loading && !active && !globalErr && (
        <p className="text-xs text-gray-500 py-6 text-center">
          Click <strong>Refresh</strong> to fetch disk usage via SSH.
          Ensure SSH credentials are set in <span className="text-blue-400">Server Monitoring → Settings</span>.
        </p>
      )}

      {/* ── Per-server error ── */}
      {!loading && active?.status === "error" && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-4 text-sm text-red-400">
          SSH error on <strong>{active.ip}</strong>: {active.error}
        </div>
      )}

      {/* ── Chart + table ── */}
      {!loading && active?.status === "online" && (
        <div className="space-y-4">
          {/* Bar chart */}
          {chartData.length > 0 && (
            <div style={{
              borderRadius: 16, padding: 16,
              background: "#e8edf5",
              boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
            }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 12 }}>
                {DISK_SERVERS_CFG.find(s => s.key === activeTab)?.label} — Disk Usage per Mount Point (GB)
              </p>
              <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 40)}>
                <BarChart data={chartData} layout="vertical"
                  margin={{ top: 0, right: 64, left: 8, bottom: 0 }}>
                  <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 10 }}
                    tickFormatter={v => `${v}G`} />
                  <YAxis type="category" dataKey="name" width={130}
                    tick={{ fill: "#475569", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                    formatter={(v, name) => [`${v} GB`, name === "used" ? "Used" : "Free"]}
                  />
                  <Bar dataKey="used" name="used" stackId="d" radius={[0,0,0,0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={barColor(entry.pct)} />
                    ))}
                    <LabelList dataKey="pct" position="right"
                      formatter={v => `${v}%`}
                      style={{ fill: "#475569", fontSize: 10, fontWeight: 600 }} />
                  </Bar>
                  <Bar dataKey="free" name="free" stackId="d" fill="#cbd5e1" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-4 mt-3 justify-center text-xs" style={{ color: "#64748b", fontWeight: 500 }}>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#34d399"}}/>Normal &lt;70%</span>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#fbbf24"}}/>Warning 70–90%</span>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#f87171"}}/>Critical ≥90%</span>
              </div>
            </div>
          )}

          {/* Detail table */}
          <div style={{
            borderRadius: 16, overflow: "hidden",
            boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
          }}>
            <div style={{
              padding: "10px 16px",
              background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
              borderBottom: "2px solid rgba(0,0,0,0.06)",
            }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>
                {rows.length} mount points · {active.label} ({active.ip})
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                    {["Mount Point","Filesystem","Used (GB)","Free (GB)","Total (GB)","Usage %","Status"].map(h => (
                      <th key={h} style={{ color: "#374151", fontSize: 11, fontWeight: 700, padding: "12px 14px",
                        textAlign: h.includes("GB") || h === "Usage %" ? "right" : "left",
                        textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap",
                        borderBottom: "2px solid rgba(0,0,0,0.06)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={7} style={{ padding: "40px 14px", textAlign: "center", color: "#94a3b8", fontSize: 12 }}>No mount points found</td></tr>
                  ) : rows.map((r, i) => (
                    <tr key={i} style={{
                      background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5",
                      transition: "background 0.15s ease",
                    }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(37,99,235,0.06)"}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"}
                    >
                      <td style={{ padding: "10px 14px", color: "#1e293b", fontFamily: "monospace", fontWeight: 700, fontSize: 12.5 }}>{r.mountpoint}</td>
                      <td style={{ padding: "10px 14px", color: "#64748b", fontFamily: "monospace", fontSize: 11.5, fontWeight: 500, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.filesystem}>{r.filesystem}</td>
                      <td style={{ padding: "10px 14px", textAlign: "right", color: "#334155", fontSize: 12.5, fontWeight: 600 }}>{r.used_gb}</td>
                      <td style={{ padding: "10px 14px", textAlign: "right", color: "#64748b", fontSize: 12.5, fontWeight: 500 }}>{r.free_gb}</td>
                      <td style={{ padding: "10px 14px", textAlign: "right", color: "#64748b", fontSize: 12.5, fontWeight: 500 }}>{r.total_gb}</td>
                      <td style={{ padding: "10px 14px", textAlign: "right" }}><UsageBar pct={r.usage_percent} /></td>
                      <td style={{ padding: "10px 14px" }}><StatusBadge pct={r.usage_percent} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

/* ─── Section: Pending Jobs ───────────────────────── */

function PendingJobsSection() {
  const [data, setData]       = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await itApi.getPendingJobs();
      setData(res.data ?? []);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard
      title="Concurrent Requests — Pending & Running"
      action={<ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={refresh} />}
    >
      <DataTable
        headers={["Request ID", "Program Name", "User", "Request Date", "Wait Time", "Status"]}
        rows={data.map((r) => [r.request_id, r.program_name, r.requested_by, r.request_date, r.wait_time, r.phase_code])}
        placeholder="Click Refresh to load pending jobs"
      />
    </SectionCard>
  );
}

/* ─── Section: Workflow Error ─────────────────────── */

function WorkflowErrorSection() {
  const [data,    setData]    = useState([]);
  const [summary, setSummary] = useState({ error: 0, suspended: 0, notified: 0 });
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await itApi.getWorkflowError();
      setData(res.data ?? []);
      if (res.summary) setSummary(res.summary);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard
      title="Oracle Workflow — Error & Pending Items (Top 10)"
      action={<ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={refresh} />}
    >
      <div className="grid grid-cols-3 gap-4 mb-6">
        <MetricCard label="Error"     value={summary.error}     gradient="from-red-500 to-red-700" />
        <MetricCard label="Suspended" value={summary.suspended} gradient="from-amber-500 to-orange-600" />
        <MetricCard label="Notified"  value={summary.notified}  gradient="from-blue-500 to-blue-700" />
      </div>
      <DataTable
        headers={["Item Key", "Item Type", "Activity Name", "Status", "Error Message", "Begin Date", "Days Pending"]}
        rows={data.map((r) => [r.item_key, r.item_type, r.activity_name, r.activity_status, r.error_message, r.begin_date, r.days_pending])}
        placeholder="Click Refresh to load workflow data"
      />
    </SectionCard>
  );
}

/* ─── Shared UI ───────────────────────────────────── */

function SectionCard({ title, subtitle, action, children }) {
  return (
    <div style={{
      background: "#e8edf5",
      borderRadius: 20,
      boxShadow: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
    }}>
      <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", letterSpacing: "0.01em" }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 12, color: "#64748b", marginTop: 2, fontWeight: 500 }}>{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs text-white transition-all ${color}`}
      style={{ fontWeight: 700, letterSpacing: "0.02em", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" }}
      onMouseDown={e => e.currentTarget.style.boxShadow = "inset 2px 2px 4px rgba(0,0,0,0.15)"}
      onMouseUp={e => e.currentTarget.style.boxShadow = "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff"}
      onMouseLeave={e => e.currentTarget.style.boxShadow = "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff"}
    >
      <Icon size={13} />{label}
    </button>
  );
}

function MetricCard({ label, value, sub, gradient }) {
  return (
    <div className={`rounded-xl bg-gradient-to-br ${gradient} p-5 text-center`}
      style={{ color: "#ffffff", boxShadow: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff", borderRadius: 16 }}>
      <p style={{ fontSize: 11, fontWeight: 600, opacity: 0.9, marginBottom: 6 }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 800 }}>{value}</p>
      {sub && <p style={{ fontSize: 11, opacity: 0.8, marginTop: 4, fontWeight: 500 }}>{sub}</p>}
    </div>
  );
}

function ChartPlaceholder({ label, className = "" }) {
  return (
    <div className={className} style={{
      height: 112, borderRadius: 14,
      background: "#e8edf5",
      boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>{label}</span>
    </div>
  );
}

function DataTable({ headers, rows = [], placeholder }) {
  return (
    <div style={{
      borderRadius: 16,
      boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
      overflow: "hidden",
    }}>
      <table className="w-full text-sm">
        <thead>
          <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
            {headers.map((h) => (
              <th key={h} style={{
                padding: "12px 14px", textAlign: "left", fontSize: 11, fontWeight: 700,
                color: "#374151", textTransform: "uppercase", letterSpacing: "0.06em",
                whiteSpace: "nowrap", borderBottom: "2px solid rgba(0,0,0,0.06)",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                {placeholder}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} style={{
                background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5",
                transition: "background 0.15s ease",
              }}
                onMouseEnter={e => e.currentTarget.style.background = "rgba(37,99,235,0.06)"}
                onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"}
              >
                {row.map((cell, j) => (
                  <td key={j} style={{
                    padding: "10px 14px", fontSize: 12.5, color: "#334155",
                    fontWeight: 500, whiteSpace: "nowrap",
                    borderBottom: "1px solid rgba(0,0,0,0.04)",
                  }}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function UsageBar({ pct }) {
  const barColor = pct >= 90 ? "#ef4444" : pct >= 70 ? "#f59e0b" : "#22c55e";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 80, height: 7, borderRadius: 99,
        background: "#e8edf5",
        boxShadow: "inset 2px 2px 4px #c5cad8, inset -2px -2px 4px #ffffff",
      }}>
        <div style={{ height: "100%", width: `${pct}%`, borderRadius: 99, background: barColor, transition: "width 0.3s ease" }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>{pct}%</span>
    </div>
  );
}

function StatusBadge({ pct }) {
  const [label, cls] =
    pct >= 90 ? ["Critical", "bg-red-500/20 text-red-400"] :
    pct >= 70 ? ["Warning",  "bg-amber-500/20 text-amber-400"] :
                ["Normal",   "bg-green-500/20 text-green-400"];
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{label}</span>
  );
}
