import { useState, useEffect, useMemo } from "react";
import {
  Banknote, ExternalLink, RefreshCw, Filter, X,
  Download, Loader2, TrendingUp, TrendingDown, Minus,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer, ReferenceLine,
} from "recharts";
import * as XLSX from "xlsx";
import { pacApi } from "@/api/dashboard";

/* ─── Tabs ────────────────────────────────────────── */
const TABS = [
  { id: "budget",  icon: Banknote, color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Budget Usage Report" },
  { id: "mt940",   icon: Banknote, color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "BCA MT940 Upload"    },
];

const CY = new Date().getFullYear();
const PAGE_SIZE = 15;

/* ─── Formatters ─────────────────────────────────── */
const fmtIDR = (n) => n == null ? "—" : Number(n).toLocaleString("id-ID");
const fmtB   = (n) => {
  if (n == null) return "—";
  const v = Math.abs(Number(n));
  if (v >= 1_000_000_000) return (Number(n) / 1_000_000_000).toFixed(2) + " B";
  if (v >= 1_000_000)     return (Number(n) / 1_000_000).toFixed(1) + " M";
  return fmtIDR(n);
};
const fmtShort = (v) => {
  const abs = Math.abs(Number(v));
  if (abs >= 1_000_000_000) return (Number(v)/1_000_000_000).toFixed(1)+"B";
  if (abs >= 1_000_000)     return (Number(v)/1_000_000).toFixed(0)+"M";
  if (abs >= 1_000)         return (Number(v)/1_000).toFixed(0)+"K";
  return String(Number(v));
};

const MONTH_NAMES = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/* ─── Main ───────────────────────────────────────── */
export default function PACDashboard() {
  const [activeTab, setActiveTab] = useState("budget");

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 gap-2">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-all ${
                active
                  ? `${tab.bg} ${tab.activeBorder} ring-1 ring-inset ${tab.activeBorder}`
                  : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
              }`}>
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

      {activeTab === "budget" && <BudgetUsageSection />}
      {activeTab === "mt940"  && <MT940Section />}
    </div>
  );
}

/* ─── Section: Budget Usage Report ──────────────── */
function BudgetUsageSection() {
  const [ledgers,  setLedgers]  = useState([]);
  const [f, setF] = useState({
    year: CY, month: "", cost_center: "", account_type: "", ledger_id: "",
  });
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const [rows,     setRows]     = useState([]);
  const [monthly,  setMonthly]  = useState([]);
  const [kpi,      setKpi]      = useState(null);
  const [error,    setError]    = useState("");
  const [page,     setPage]     = useState(1);
  const [chartMode, setChartMode] = useState("bar");  // "bar" | "line"

  useEffect(() => {
    pacApi.getLedgers().then(r => { if (r?.success) setLedgers(r.data ?? []); }).catch(() => {});
  }, []);

  const setFld = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));

  const handleSearch = async () => {
    setLoading(true); setError(""); setPage(1);
    try {
      const p = { year: f.year };
      if (f.month)        p.month        = f.month;
      if (f.cost_center)  p.cost_center  = f.cost_center;
      if (f.account_type) p.account_type = f.account_type;
      if (f.ledger_id)    p.ledger_id    = f.ledger_id;
      const r = await pacApi.getBudgetUsage(p);
      if (r?.success) {
        setRows(r.data || []);
        setMonthly(r.monthly || []);
        setKpi(r.kpi || null);
        setSearched(true);
      } else {
        setError(r?.error || "Request failed");
      }
    } catch (e) {
      setError(e?.detail || e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setF({ year: CY, month: "", cost_center: "", account_type: "", ledger_id: "" });
    setRows([]); setMonthly([]); setKpi(null); setSearched(false); setError(""); setPage(1);
  };

  const handleDownload = () => {
    const cols = ["Period","Cost Center Code","Cost Center","Account Code","Account","Type",
                  "Actual (IDR)","Budget (IDR)","Variance (IDR)","Absorption (%)"];
    const data = rows.map(r => {
      const actual   = Number(r.actual_amount) || 0;
      const budget   = Number(r.budget_amount) || 0;
      const variance = budget - actual;
      const abs_pct  = budget ? (actual / budget * 100).toFixed(1) : "—";
      return [r.period_name, r.cost_center_code, r.cost_center_name,
              r.account_code, r.account_name, r.account_type,
              actual, budget, variance, abs_pct];
    });
    const ws = XLSX.utils.aoa_to_sheet([cols, ...data]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Budget Usage");
    XLSX.writeFile(wb, `budget_usage_${f.year}${f.month ? "_M"+f.month : ""}.xlsx`);
  };

  // Pivot for cost-center summary (used in table detail)
  const paged = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const TH = { padding: "10px 12px", fontSize: 11, fontWeight: 600, color: "#9ca3af",
               textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" };
  const TD = { padding: "9px 12px", fontSize: 12, whiteSpace: "nowrap" };

  const absorptionColor = (pct) =>
    pct > 100 ? "#f87171" : pct >= 80 ? "#fbbf24" : "#34d399";

  const INPUT  = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-500/60";
  const SELECT = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-green-500/60";

  return (
    <div className="space-y-4">
      {/* ── Filter ── */}
      <SectionCard
        title="Budget Usage Report — Actual vs Business Plan"
        subtitle="GL Balances from Oracle EBS · Actual (A) vs Budget (B)"
        action={
          <div className="flex gap-2">
            <ActionBtn icon={RefreshCw} label="Reset"  color="bg-gray-700 hover:bg-gray-600" onClick={handleReset} />
            <ActionBtn icon={loading ? Loader2 : Filter} label="Search" color="bg-green-600 hover:bg-green-700" onClick={handleSearch} />
          </div>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
          <Field label="Year *">
            <input className={INPUT} type="number" value={f.year} onChange={setFld("year")} min={2020} max={2030} />
          </Field>
          <Field label="Month">
            <select className={SELECT} value={f.month} onChange={setFld("month")}>
              <option value="">— All Months —</option>
              {MONTH_NAMES.slice(1).map((m, i) => (
                <option key={i+1} value={i+1}>{m}</option>
              ))}
            </select>
          </Field>
          <Field label="Cost Center">
            <input className={INPUT} value={f.cost_center} onChange={setFld("cost_center")} placeholder="partial search…" />
          </Field>
          <Field label="Account Type">
            <select className={SELECT} value={f.account_type} onChange={setFld("account_type")}>
              <option value="">— All —</option>
              <option value="E">Expense (E)</option>
              <option value="A">Asset (A)</option>
              <option value="L">Liability (L)</option>
              <option value="R">Revenue (R)</option>
              <option value="O">Owner Equity (O)</option>
            </select>
          </Field>
          <Field label="Ledger">
            <select className={SELECT} value={f.ledger_id} onChange={setFld("ledger_id")}>
              <option value="">— All Ledgers —</option>
              {ledgers.map(l => (
                <option key={l.ledger_id} value={l.ledger_id}>{l.ledger_name} ({l.currency_code})</option>
              ))}
            </select>
          </Field>
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <X size={12} />{error}
          </div>
        )}
      </SectionCard>

      {loading && (
        <div className="flex items-center justify-center py-12 text-gray-500 text-sm gap-2">
          <Loader2 size={16} className="animate-spin" /> Loading from Oracle EBS GL…
        </div>
      )}

      {searched && !loading && (
        <>
          {/* ── KPI Cards ── */}
          {kpi && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Total Actual",    value: fmtB(kpi.total_actual),    color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20" },
                { label: "Total Budget",    value: fmtB(kpi.total_budget),    color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/20" },
                {
                  label: "Absorption",
                  value: kpi.absorption_pct + "%",
                  color: kpi.absorption_pct > 100 ? "text-red-400" : kpi.absorption_pct >= 80 ? "text-yellow-400" : "text-green-400",
                  bg: kpi.absorption_pct > 100 ? "bg-red-500/10" : "bg-yellow-500/10",
                  border: kpi.absorption_pct > 100 ? "border-red-500/20" : "border-yellow-500/20",
                },
                { label: "Remaining Budget", value: fmtB(kpi.variance),      color: kpi.variance < 0 ? "text-red-400" : "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
              ].map(k => (
                <div key={k.label} className={`rounded-lg border ${k.border} ${k.bg} px-4 py-3`}>
                  <p className="text-xs text-gray-500 mb-1">{k.label}</p>
                  <p className={`text-xl font-bold ${k.color}`}>{k.value}</p>
                </div>
              ))}
            </div>
          )}

          {/* ── Chart toggle ── */}
          {monthly.length > 0 && (
            <>
              <div className="flex gap-2">
                {[{ id: "bar", label: "Bar Chart" }, { id: "line", label: "Trend Line" }].map(m => (
                  <button key={m.id} onClick={() => setChartMode(m.id)}
                    className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                      chartMode === m.id
                        ? "bg-green-500/10 border-green-500/40 text-green-400"
                        : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
                    }`}>{m.label}</button>
                ))}
              </div>

              <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
                <p className="text-xs text-gray-500 mb-3">
                  Monthly Budget vs Actual (IDR) — {f.year}
                </p>
                <ResponsiveContainer width="100%" height={300}>
                  {chartMode === "bar" ? (
                    <BarChart data={monthly} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="period_name" tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <YAxis tickFormatter={fmtShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8, fontSize: 12 }}
                        formatter={(v, name) => [fmtIDR(v), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                      <Bar dataKey="budget" name="Budget (BP)" fill="#3b82f6" radius={[4,4,0,0]} opacity={0.7} />
                      <Bar dataKey="actual" name="Actual"      fill="#34d399" radius={[4,4,0,0]} />
                    </BarChart>
                  ) : (
                    <LineChart data={monthly} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="period_name" tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <YAxis tickFormatter={fmtShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8, fontSize: 12 }}
                        formatter={(v, name) => [fmtIDR(v), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                      <Line type="monotone" dataKey="budget" name="Budget (BP)" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="actual" name="Actual"      stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    </LineChart>
                  )}
                </ResponsiveContainer>

                {/* Absorption mini-table per month */}
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-xs">
                    <tbody>
                      <tr>
                        <td style={{ padding: "4px 8px", color: "#6b7280", whiteSpace: "nowrap" }}>Absorption %</td>
                        {monthly.map(m => (
                          <td key={m.period_name} style={{ padding: "4px 8px", textAlign: "center", whiteSpace: "nowrap",
                            fontWeight: 600, color: absorptionColor(m.absorption) }}>
                            {m.absorption}%
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* ── Detail Table ── */}
          <div className="rounded-lg border border-gray-800 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800 bg-gray-900/50">
              <span className="text-xs text-gray-500">{rows.length} rows</span>
              {rows.length > 0 && (
                <button onClick={handleDownload}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
                  <Download size={12} /> Download Excel
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ background: "rgba(55,65,81,0.6)" }}>
                    {["Period","Cost Center","Account","Type","Actual (IDR)","Budget (IDR)","Variance","Absorption"].map((h, i) => (
                      <th key={h} style={{ ...TH, textAlign: i >= 4 ? "right" : "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={8} style={{ padding: "40px 12px", textAlign: "center", color: "#6b7280", fontSize: 12 }}>No data found</td></tr>
                  ) : paged.map((r, i) => {
                    const actual   = Number(r.actual_amount)  || 0;
                    const budget   = Number(r.budget_amount)  || 0;
                    const variance = budget - actual;
                    const absPct   = budget ? (actual / budget * 100) : 0;
                    return (
                      <tr key={i} style={{ borderTop: "1px solid rgba(55,65,81,0.5)" }}
                        className="hover:bg-gray-800/30 transition-colors">
                        <td style={{ ...TD, color: "#9ca3af" }}>{r.period_name}</td>
                        <td style={{ ...TD, color: "#d1d5db" }}>
                          <span style={{ fontFamily: "monospace", color: "#60a5fa", marginRight: 6 }}>{r.cost_center_code}</span>
                          {r.cost_center_name !== r.cost_center_code ? r.cost_center_name : ""}
                        </td>
                        <td style={{ ...TD, color: "#d1d5db" }}>
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#a78bfa", marginRight: 6 }}>{r.account_code}</span>
                          <span style={{ color: "#9ca3af" }}>{r.account_name}</span>
                        </td>
                        <td style={{ ...TD }}>
                          <span style={{ padding: "2px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                            background: r.account_type === "E" ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)",
                            color: r.account_type === "E" ? "#f87171" : "#60a5fa" }}>
                            {r.account_type}
                          </span>
                        </td>
                        <td style={{ ...TD, textAlign: "right", color: "#34d399", fontWeight: 500 }}>{fmtIDR(actual)}</td>
                        <td style={{ ...TD, textAlign: "right", color: "#60a5fa" }}>{fmtIDR(budget)}</td>
                        <td style={{ ...TD, textAlign: "right", color: variance < 0 ? "#f87171" : "#9ca3af", fontWeight: 500 }}>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            {variance < 0
                              ? <TrendingUp size={11} color="#f87171" />
                              : variance > 0
                                ? <TrendingDown size={11} color="#6b7280" />
                                : <Minus size={11} color="#6b7280" />}
                            {fmtIDR(Math.abs(variance))}
                          </span>
                        </td>
                        <td style={{ ...TD, textAlign: "right" }}>
                          <span style={{ fontWeight: 600, color: absorptionColor(absPct) }}>
                            {budget ? absPct.toFixed(1) + "%" : "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {rows.length > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-800 bg-gray-900/50">
                <span className="text-xs text-gray-500">
                  {(page-1)*PAGE_SIZE+1}–{Math.min(page*PAGE_SIZE, rows.length)} of {rows.length}
                </span>
                <div className="flex gap-1">
                  <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}
                    className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 disabled:opacity-30">‹ Prev</button>
                  <button onClick={() => setPage(p => Math.min(Math.ceil(rows.length/PAGE_SIZE), p+1))}
                    disabled={page >= Math.ceil(rows.length/PAGE_SIZE)}
                    className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 disabled:opacity-30">Next ›</button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Section: MT940 ─────────────────────────────── */
function MT940Section() {
  return (
    <SectionCard title="BCA MT940 Upload"
      action={
        <a href="/apps/MT940_upload"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors">
          <ExternalLink size={13} /> Open App
        </a>
      }>
      <div className="grid grid-cols-3 gap-4 mb-5">
        <MetricCard label="Total Files"  value="—" gradient="from-indigo-500 to-purple-600" />
        <MetricCard label="Generated"    value="—" gradient="from-cyan-500 to-teal-500" />
        <MetricCard label="Not Found"    value="—" gradient="from-rose-500 to-pink-600" />
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {["File Name","Size","Generated At","Status"].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr><td colSpan={4} className="px-3 py-10 text-center text-xs text-gray-600">No data</td></tr>
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

/* ─── Shared UI ──────────────────────────────────── */
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
    <button onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors ${color}`}>
      <Icon size={13} />{label}
    </button>
  );
}

function Field({ label, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-gray-500">{label}</label>
      {children}
    </div>
  );
}

function MetricCard({ label, value, gradient }) {
  return (
    <div className={`rounded-xl bg-gradient-to-br ${gradient} p-5 text-white text-center`}>
      <p className="text-xs opacity-80 mb-2">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}
