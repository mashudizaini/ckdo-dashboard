/**
 * ETL Admin
 * ─────────────────────────────────────────
 * Control tab for the EIS data warehouse's Oracle EBS extraction jobs —
 * moved here from the EIS dashboard (was "EIS > ETL Admin") since running/
 * monitoring ETL jobs is an IT/ops concern, same reasoning as EBS Backup
 * Recovery and VPN/HikCentral living here rather than under the
 * business-facing dashboards.
 *
 * Each job card shows the Oracle EBS source tables and the Postgres (eis
 * schema) destination table it writes to, a "View Source" button that pulls
 * the job's real extraction code live from the backend (inspect.getsource
 * on eis_etl_tasks.py — always exactly what's running, never a stale
 * description), and — per run in the history table — a "click to expand"
 * preview of the actual imported rows, so what's really in the warehouse
 * for each group is never a mystery.
 *
 * Local helpers duplicated (not shared) matching the convention already
 * used by VpnAccessMonitoring.jsx / HikCentralIntegration.jsx for
 * self-contained IT sub-tabs.
 */
import { useState, useEffect, Fragment } from "react";
import {
  Loader2, RefreshCw, Play, Square, ChevronDown, ChevronUp, Database,
  CheckCircle2, XCircle, Clock, X, Code2, Table2,
} from "lucide-react";
import { etlAdminApi } from "@/api/dashboard";

const CY = new Date().getFullYear();
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const fmtN = (v, d = 1) => v == null ? "—" : Number(v).toLocaleString("id-ID", { maximumFractionDigits: d, minimumFractionDigits: d });
const selCls = "text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-1.5 focus:outline-none focus:border-cyan-500";

function Loading() {
  return <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>;
}

function ChartCard({ title, subtitle, right, className = "", children }) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl p-4 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-1">
        <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        {right}
      </div>
      {subtitle && <p className="text-xs text-gray-500 mb-3">{subtitle}</p>}
      {children}
    </div>
  );
}

function EtlStatusBadge({ status }) {
  const cfg = {
    success: { cls: "bg-emerald-500/15 text-emerald-400", icon: <CheckCircle2 size={11} className="mr-1" /> },
    failed:  { cls: "bg-red-500/15 text-red-400", icon: <XCircle size={11} className="mr-1" /> },
    stopped: { cls: "bg-gray-700 text-gray-400", icon: <Square size={11} className="mr-1" /> },
    running: { cls: "bg-amber-500/15 text-amber-400", icon: <Loader2 size={11} className="mr-1 animate-spin" /> },
  };
  const { cls, icon } = cfg[status] || cfg.running;
  return <span className={`text-[10px] font-bold px-2 py-1 rounded-full inline-flex items-center ${cls}`}>{icon}{status}</span>;
}

function EtlDataPreview({ jobName, runParams }) {
  const [rows, setRows] = useState(null);
  const [cols, setCols] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    const p = typeof runParams === "string" ? JSON.parse(runParams) : runParams;
    etlAdminApi.getJobData(jobName, p?.year || CY, p?.month || null)
      .then((res) => { setRows(res.data || []); setCols(res.columns || []); })
      .catch((e) => setErr(e?.response?.data?.detail || e?.detail || e.message));
  }, [jobName, runParams]);

  const colLabel = (c) => c.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());

  return (
    <tr>
      <td colSpan={8} className="p-0">
        <div className="bg-gray-950 border-t border-gray-800 px-4 py-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-400 mb-3"><Database size={13} /> Data hasil import — <span className="font-mono">{jobName}</span></div>
          {rows === null ? (
            <div className="flex items-center gap-2 text-xs text-gray-500 py-2"><Loader2 size={13} className="animate-spin" /> Memuat data...</div>
          ) : err ? <div className="text-xs text-red-400 py-2">{err}</div>
          : rows.length === 0 ? <div className="text-xs text-gray-600 py-2">Belum ada data untuk parameter ini.</div>
          : (
            <div className="overflow-x-auto rounded border border-gray-800 max-h-64">
              <table className="w-full text-[11px] border-collapse min-w-max">
                <thead className="bg-gray-900 text-gray-200 sticky top-0 z-10">
                  <tr>{cols.map((c) => <th key={c} className="px-2.5 py-1.5 text-left font-medium whitespace-nowrap">{colLabel(c)}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i} className={`border-b border-gray-800/60 ${i % 2 === 0 ? "bg-gray-900/40" : "bg-gray-900/70"}`}>
                      {cols.map((c) => {
                        const v = row[c]; const isNum = typeof v === "number"; const isPct = c.endsWith("_pct");
                        return <td key={c} className={`px-2.5 py-1.5 whitespace-nowrap font-mono ${isNum ? "text-right" : "text-gray-400"} ${isPct && v < 80 ? "text-red-400" : isPct && v >= 100 ? "text-emerald-400" : "text-gray-300"}`}>
                          {v == null ? "—" : isPct ? `${fmtN(v)}%` : isNum ? fmtN(v) : String(v)}
                        </td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

function SourceModal({ jobName, onClose }) {
  const [source, setSource] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    etlAdminApi.getSource(jobName)
      .then((res) => setSource(res.source))
      .catch((e) => setErr(e?.response?.data?.detail || e?.detail || e.message));
  }, [jobName]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-800 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <h4 className="font-semibold text-gray-200 flex items-center gap-2"><Code2 size={15} className="text-cyan-400" /> Extraction Source — <span className="font-mono text-cyan-400">{jobName}</span></h4>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>
        <div className="p-5 overflow-auto">
          {err ? (
            <p className="text-sm text-red-400">{err}</p>
          ) : source === null ? (
            <div className="flex items-center gap-2 text-xs text-gray-500"><Loader2 size={13} className="animate-spin" /> Memuat kode...</div>
          ) : (
            <pre className="text-[11px] text-gray-300 font-mono whitespace-pre-wrap leading-relaxed bg-gray-950 rounded-lg p-4 border border-gray-800">{source}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

export default function EtlAdmin() {
  const [jobs, setJobs] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState("");
  const [stopping, setStopping] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [modal, setModal] = useState(null);
  const [sourceJob, setSourceJob] = useState(null);
  const YEARS = Array.from({ length: 5 }, (_, i) => CY - i);

  const loadData = async () => {
    setLoading(true);
    try {
      const [jRes, sRes] = await Promise.all([etlAdminApi.getStatus(), etlAdminApi.getSchedule()]);
      setJobs(jRes.data || []);
      setSchedule(sRes.data || []);
    } catch (e) { console.error("Failed to load ETL:", e); }
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []); // eslint-disable-line
  useEffect(() => {
    if (!jobs.some((j) => j.status === "running")) return;
    const t = setInterval(loadData, 15000);
    return () => clearInterval(t);
  }, [jobs]); // eslint-disable-line

  const handleTrigger = async () => {
    const { job, year, month } = modal;
    setModal(null); setTriggering(job);
    try { await etlAdminApi.trigger(job, { year, month: month || null }); setTimeout(loadData, 2000); }
    catch (err) { alert("Gagal: " + (err?.response?.data?.detail || err?.detail || err.message)); }
    setTriggering("");
  };

  const handleStop = async (jobName, e) => {
    e.stopPropagation();
    if (!confirm(`Hentikan job "${jobName}" yang sedang berjalan?`)) return;
    setStopping(jobName);
    try { await etlAdminApi.stop(jobName); await loadData(); }
    catch (err) { alert("Gagal stop: " + (err?.response?.data?.detail || err?.detail || err.message)); }
    setStopping("");
  };

  const parseParams = (raw) => {
    if (!raw) return "—";
    const p = typeof raw === "string" ? JSON.parse(raw) : raw;
    return p.month ? `${p.year}/${String(p.month).padStart(2, "0")}` : `${p.year}`;
  };

  if (loading) return <Loading />;

  return (
    <div className="space-y-4">
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setModal(null)}>
          <div className="bg-gray-900 border border-gray-800 rounded-xl w-80 p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-gray-200">Run <span className="font-mono text-cyan-400">{modal.job}</span></h4>
              <button onClick={() => setModal(null)} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Tahun</label>
                <select value={modal.year} onChange={(e) => setModal({ ...modal, year: Number(e.target.value) })} className={`${selCls} w-full`}>
                  {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Bulan <span className="text-gray-600 font-normal">(kosong = semua bulan)</span></label>
                <select value={modal.month} onChange={(e) => setModal({ ...modal, month: e.target.value ? Number(e.target.value) : "" })} className={`${selCls} w-full`}>
                  <option value="">Semua bulan</option>
                  {MONTHS_SHORT.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setModal(null)} className="flex-1 border border-gray-700 text-gray-400 px-4 py-2 rounded-lg text-sm hover:bg-gray-800">Batal</button>
              <button onClick={handleTrigger} className="flex-1 flex items-center justify-center gap-1.5 bg-cyan-600 hover:bg-cyan-700 text-white px-4 py-2 rounded-lg text-sm font-medium"><Play size={13} /> Jalankan</button>
            </div>
          </div>
        </div>
      )}

      {sourceJob && <SourceModal jobName={sourceJob} onClose={() => setSourceJob(null)} />}

      <ChartCard title="ETL Schedule" subtitle="Oracle EBS source tables → Postgres (eis) destination, per job." right={<button onClick={loadData} className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"><RefreshCw size={13} /> Refresh</button>}>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {schedule.map((s) => (
            <div key={s.job} className="bg-gray-800/50 rounded-lg p-3 border border-gray-800">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-200">{s.job}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5"><Clock size={9} className="inline mr-1" />{s.frequency} — {s.schedule}</div>
                  <div className="text-[9px] text-gray-600 mt-0.5">{s.source}</div>
                </div>
                <button onClick={() => setModal({ job: s.job, year: CY, month: "" })} disabled={triggering === s.job}
                  className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 shrink-0">
                  {triggering === s.job ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />} Run
                </button>
              </div>
              <div className="mt-2.5 pt-2.5 border-t border-gray-800 space-y-1.5">
                <div className="flex items-start gap-1.5">
                  <Table2 size={11} className="text-amber-400 mt-0.5 shrink-0" />
                  <div className="text-[10px] text-gray-500 leading-relaxed">
                    <span className="text-gray-400 font-medium">{s.source_system || "Oracle EBS"}:</span> <span className="font-mono">{(s.oracle_tables || []).join(", ")}</span>
                  </div>
                </div>
                <div className="flex items-start gap-1.5">
                  <Database size={11} className="text-emerald-400 mt-0.5 shrink-0" />
                  <div className="text-[10px] text-gray-500 leading-relaxed">
                    <span className="text-gray-400 font-medium">Destination:</span> <span className="font-mono">{s.destination_table}</span>
                  </div>
                </div>
                <button onClick={() => setSourceJob(s.job)} className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 mt-1">
                  <Code2 size={10} /> View source query
                </button>
              </div>
            </div>
          ))}
        </div>
      </ChartCard>

      <ChartCard title="Recent Job History" subtitle="10 terakhir · klik baris untuk lihat data yang sudah masuk" className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-950 border-b border-gray-800">
              {["Job","Status","Started","Duration","Records","Parameter","Error",""].map((h, i) => (
                <th key={i} className={`py-2 px-3 font-medium text-gray-500 text-xs ${h === "Records" ? "text-right" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 ? (
              <tr><td colSpan={8} className="py-10 text-center text-gray-600 text-sm">Belum ada job yang dijalankan</td></tr>
            ) : jobs.map((j) => (
              <Fragment key={j.id}>
                <tr onClick={() => setExpandedId((p) => (p === j.id ? null : j.id))} className={`border-b border-gray-800/60 cursor-pointer transition-colors ${expandedId === j.id ? "bg-cyan-500/5" : "hover:bg-gray-800/40"}`}>
                  <td className="py-2 px-3 font-mono text-xs font-semibold text-cyan-400">
                    <span className="flex items-center gap-1">{expandedId === j.id ? <ChevronUp size={12} /> : <ChevronDown size={12} className="text-gray-600" />}{j.job_name}</span>
                  </td>
                  <td className="py-2 px-3"><EtlStatusBadge status={j.status} /></td>
                  <td className="py-2 px-3 text-xs text-gray-500">{j.started_at ? new Date(j.started_at).toLocaleString("id-ID") : "—"}</td>
                  <td className="py-2 px-3 text-xs text-gray-500">{j.duration_secs != null ? `${j.duration_secs}s` : "—"}</td>
                  <td className="py-2 px-3 text-right font-mono text-xs text-gray-400">{j.records_processed || 0}</td>
                  <td className="py-2 px-3 text-xs text-gray-500">{parseParams(j.run_params)}</td>
                  <td className="py-2 px-3 text-xs text-red-400 max-w-[160px] truncate" title={j.error_message}>{j.error_message || "—"}</td>
                  <td className="py-2 px-3">
                    {j.status === "running" && (
                      <button onClick={(e) => handleStop(j.job_name, e)} disabled={stopping === j.job_name} title="Hentikan job"
                        className="flex items-center gap-1 text-xs bg-red-500/10 text-red-400 border border-red-500/30 px-2 py-1 rounded-lg hover:bg-red-500/20 disabled:opacity-50">
                        {stopping === j.job_name ? <Loader2 size={11} className="animate-spin" /> : <Square size={11} />} Stop
                      </button>
                    )}
                  </td>
                </tr>
                {expandedId === j.id && <EtlDataPreview jobName={j.job_name} runParams={j.run_params} />}
              </Fragment>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </div>
  );
}
