import { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Server, Activity, HardDrive, Clock, AlertTriangle,
  RefreshCw, Settings, Wifi, WifiOff, Loader2, X, CheckCircle,
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

function ServerMonitoringSection() {
  const [config,      setConfig]      = useState(null);
  const [metrics,     setMetrics]     = useState(null);
  const [history,     setHistory]     = useState([]);   // [{ts, cpu, mem, load}]
  const [loading,     setLoading]     = useState(false);
  const [polling,     setPolling]     = useState(false);
  const [showModal,   setShowModal]   = useState(false);
  const [testResult,  setTestResult]  = useState(null);

  // Load config on mount
  useEffect(() => {
    itApi.getServerConfig()
      .then((res) => setConfig(res.data))
      .catch(() => {});
  }, []);

  // Fetch metrics once
  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const res = await itApi.getServerMetrics();
      const d = res.data;
      setMetrics(d);
      if (d.status === "online") {
        setHistory((prev) => [
          ...prev.slice(-29),
          {
            ts:   new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            cpu:  d.cpu,
            mem:  d.memory_percent,
            load: parseFloat(d.load) || 0,
          },
        ]);
      }
    } catch (e) {
      setMetrics({ status: "error", error: String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  // Polling
  useEffect(() => {
    if (!polling) return;
    fetchMetrics();
    const id = setInterval(fetchMetrics, 5000);
    return () => clearInterval(id);
  }, [polling, fetchMetrics]);

  const statusOnline  = metrics?.status === "online";
  const statusError   = metrics?.status === "error";
  const statusNotConf = metrics?.status === "not_configured";

  return (
    <>
      <SectionCard
        title="Real-time Server Monitoring"
        action={
          <div className="flex gap-2">
            {polling ? (
              <ActionBtn icon={RefreshCw} label="Stop" color="bg-red-600 hover:bg-red-700" onClick={() => setPolling(false)} />
            ) : (
              <ActionBtn icon={RefreshCw} label="Start" color="bg-green-600 hover:bg-green-700" onClick={() => setPolling(true)} />
            )}
            <ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={fetchMetrics} />
          </div>
        }
      >
        {/* Config bar */}
        <div className="mb-5 flex items-center justify-between p-4 rounded-lg bg-gray-800/50 border border-gray-700">
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">Server</span>
            <span className="text-sm font-medium text-gray-200">
              {config ? `${config.ip}:${config.port}` : "—"}
            </span>
            {config?.username && (
              <span className="text-xs text-gray-500">({config.username})</span>
            )}
            {config?.has_password === false && (
              <span className="text-xs text-amber-400">Password belum diset</span>
            )}
          </div>
          <ActionBtn icon={Settings} label="Configure" color="bg-gray-700 hover:bg-gray-600" onClick={() => setShowModal(true)} />
        </div>

        {/* Status banner */}
        {statusError && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            <WifiOff size={14} /> {metrics.error}
          </div>
        )}
        {statusNotConf && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm">
            <Settings size={14} /> Konfigurasi SSH belum lengkap. Klik Configure untuk mengisi credentials.
          </div>
        )}

        {/* Metric Cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <MetricCard
            label="CPU Usage"
            value={metrics ? `${metrics.cpu}%` : "—"}
            sub={`Load Average: ${metrics?.load ?? "—"}`}
            gradient="from-indigo-500 to-purple-600"
          />
          <MetricCard
            label="Memory Usage"
            value={metrics ? `${metrics.memory_percent}%` : "—"}
            sub={metrics ? `${metrics.memory_used} / ${metrics.memory_total} GB` : "— / —"}
            gradient="from-pink-500 to-rose-500"
          />
          <MetricCard
            label="Server Status"
            value={
              <span className="flex items-center justify-center gap-2">
                {statusOnline  ? <><Wifi size={16} />Online</>   : null}
                {statusError   ? <><WifiOff size={16} />Error</>  : null}
                {!metrics || statusNotConf ? <><Wifi size={16} />Waiting</> : null}
              </span>
            }
            sub={`Uptime: ${metrics?.uptime ?? "—"}`}
            gradient={statusOnline ? "from-cyan-500 to-blue-500" : statusError ? "from-red-600 to-red-800" : "from-gray-600 to-gray-700"}
          />
        </div>

        {/* Charts */}
        <div className="space-y-4">
          <MiniChart title="CPU Usage History (%)" data={history} dataKey="cpu" color="#818cf8" domain={[0, 100]} />
          <MiniChart title="Memory Usage History (%)" data={history} dataKey="mem" color="#f472b6" domain={[0, 100]} />
          <MiniChart title="Load Average History" data={history} dataKey="load" color="#22d3ee" />
        </div>
      </SectionCard>

      {/* Configure Modal */}
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">SSH Server Configuration</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
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

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-gray-800">
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
      <p className="text-sm font-medium text-gray-300 mb-2">{title}</p>
      {data.length === 0 ? (
        <div className="h-20 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center">
          <span className="text-xs text-gray-600">Start monitoring untuk melihat grafik</span>
        </div>
      ) : (
        <div className="h-20 rounded-lg bg-gray-800 border border-gray-700 overflow-hidden">
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
  const [data,    setData]    = useState([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await itApi.getTablespace();
      if (res.success) {
        setData(res.data ?? []);
      } else {
        setError(res.error ?? "Gagal memuat data");
      }
    } catch (e) {
      setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  };

  // Chart data: short name + usage_percent
  const chartData = data.map((r) => ({
    name:    r.tablespace_name,
    pct:     parseFloat(r.usage_percent),
    status:  r.status,
  }));

  return (
    <SectionCard
      title="Top 5 Tablespaces by Usage"
      action={<ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" onClick={refresh} />}
    >
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
              <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10, fill: "#d1d5db" }} />
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
        <ChartPlaceholder label="Klik Refresh untuk memuat data tablespace" className="mb-5" />
      )}

      {/* Table */}
      <DataTable
        headers={["Tablespace Name", "Usage (%)", "Used (GB)", "Total (GB)", "Status"]}
        rows={data.map((r) => [
          r.tablespace_name,
          <UsageBar key={r.tablespace_name} pct={parseFloat(r.usage_percent)} />,
          `${r.used_gb} GB`,
          `${r.total_gb} GB`,
          <span key={r.tablespace_name + "-s"} className={`px-2 py-0.5 rounded-full text-xs font-medium ${TS_COLORS[r.status]?.badge}`}>
            {r.status}
          </span>,
        ])}
        placeholder="Klik Refresh untuk memuat data tablespace"
      />
    </SectionCard>
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
            <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4">
              <p className="text-xs font-medium mb-3" style={{ color: "var(--text-secondary, #9ca3af)" }}>
                {DISK_SERVERS_CFG.find(s => s.key === activeTab)?.label} — Disk Usage per Mount Point (GB)
              </p>
              <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 40)}>
                <BarChart data={chartData} layout="vertical"
                  margin={{ top: 0, right: 64, left: 8, bottom: 0 }}>
                  <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 10 }}
                    tickFormatter={v => `${v}G`} />
                  <YAxis type="category" dataKey="name" width={130}
                    tick={{ fill: "#d1d5db", fontSize: 10 }} />
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
                      style={{ fill: "#d1d5db", fontSize: 10, fontWeight: 600 }} />
                  </Bar>
                  <Bar dataKey="free" name="free" stackId="d" fill="#374151" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-4 mt-3 justify-center text-xs" style={{ color: "var(--text-secondary, #9ca3af)" }}>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#34d399"}}/>Normal &lt;70%</span>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#fbbf24"}}/>Warning 70–90%</span>
                <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block" style={{background:"#f87171"}}/>Critical ≥90%</span>
              </div>
            </div>
          )}

          {/* Detail table */}
          <div className="rounded-lg border border-gray-700 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-700 bg-gray-800/50">
              <span className="text-xs font-medium" style={{ color: "var(--text-secondary, #9ca3af)" }}>
                {rows.length} mount points · {active.label} ({active.ip})
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: "rgba(55,65,81,0.6)" }}>
                    {["Mount Point","Filesystem","Used (GB)","Free (GB)","Total (GB)","Usage %","Status"].map(h => (
                      <th key={h} style={{ color: "#9ca3af", fontSize: 11, fontWeight: 600, padding: "10px 12px",
                        textAlign: h.includes("GB") || h === "Usage %" ? "right" : "left",
                        textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={7} style={{ padding: "32px 12px", textAlign: "center", color: "#6b7280", fontSize: 12 }}>No mount points found</td></tr>
                  ) : rows.map((r, i) => (
                    <tr key={i} style={{ borderTop: "1px solid rgba(55,65,81,0.6)" }}
                      className="hover:bg-gray-800/30 transition-colors">
                      <td style={{ padding: "10px 12px", color: "#e5e7eb", fontFamily: "monospace", fontWeight: 600, fontSize: 12 }}>{r.mountpoint}</td>
                      <td style={{ padding: "10px 12px", color: "#9ca3af", fontFamily: "monospace", fontSize: 11, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.filesystem}>{r.filesystem}</td>
                      <td style={{ padding: "10px 12px", textAlign: "right", color: "#d1d5db", fontSize: 12 }}>{r.used_gb}</td>
                      <td style={{ padding: "10px 12px", textAlign: "right", color: "#9ca3af", fontSize: 12 }}>{r.free_gb}</td>
                      <td style={{ padding: "10px 12px", textAlign: "right", color: "#9ca3af", fontSize: 12 }}>{r.total_gb}</td>
                      <td style={{ padding: "10px 12px", textAlign: "right" }}><UsageBar pct={r.usage_percent} /></td>
                      <td style={{ padding: "10px 12px" }}><StatusBadge pct={r.usage_percent} /></td>
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
        placeholder="Klik Refresh untuk memuat pending jobs"
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
        placeholder="Klik Refresh untuk memuat workflow data"
      />
    </SectionCard>
  );
}

/* ─── Shared UI ───────────────────────────────────── */

function SectionCard({ title, subtitle, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors ${color}`}
    >
      <Icon size={13} />{label}
    </button>
  );
}

function MetricCard({ label, value, sub, gradient }) {
  return (
    <div className={`rounded-xl bg-gradient-to-br ${gradient} p-5 text-white text-center`}>
      <p className="text-xs opacity-80 mb-2">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
      {sub && <p className="text-xs opacity-70 mt-1">{sub}</p>}
    </div>
  );
}

function ChartPlaceholder({ label, className = "" }) {
  return (
    <div className={`h-28 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center ${className}`}>
      <span className="text-xs text-gray-600">{label}</span>
    </div>
  );
}

function DataTable({ headers, rows = [], placeholder }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-800/60">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className="px-3 py-10 text-center text-xs text-gray-600">
                {placeholder}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-2.5 text-xs text-gray-300 whitespace-nowrap">
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
  const color = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-green-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 rounded-full bg-gray-700">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs">{pct}%</span>
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
