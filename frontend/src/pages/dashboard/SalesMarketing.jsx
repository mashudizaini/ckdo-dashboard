/**
 * Sales & Marketing Dashboard
 * ─────────────────────────────────────────
 * Fase 1 + Fase 2 (3 modules) of the "Blueprint Sales & Marketing" plan —
 * Sales Trend, Sales vs Budget (both read eis.fact_sales, already
 * populated by the existing etl_sales job) and Open Sales Order (reads
 * the new eis.fact_sales_order, populated by etl_sales_orders — see
 * eis_etl_tasks.py). No dedicated Keycloak role exists for this team yet,
 * so this page is reachable by any authenticated user, same as General.
 *
 * Local helpers below are self-contained rather than imported from
 * General.jsx, matching this codebase's established convention for
 * dashboard sections (see General.jsx's own docstring).
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { RefreshCw, TrendingUp, Package, AlertCircle, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const SALES_API = "/api/v1/dashboard/sales";
const BUSINESS_TYPES = ["Local", "Export", "CMO"];
const BIZ_COLOR = { Local: "#60a5fa", Export: "#34d399", CMO: "#fbbf24" };

function SectionCard({ title, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

function SubTabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1.5 mb-4">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-colors ${
            active === t.id ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-gray-200"
          }`}>
          <t.icon size={13} /> {t.label}
        </button>
      ))}
    </div>
  );
}

function KpiCard({ label, value, color, bg }) {
  return (
    <div className={`rounded-lg border px-4 py-3 space-y-1 ${bg}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-bold truncate ${color}`}>{value}</p>
    </div>
  );
}

const fmtRp = (v) => {
  if (v === undefined || v === null) return "Rp 0";
  return (v < 0 ? "-Rp " : "Rp ") + Math.abs(Math.round(v)).toLocaleString("id-ID");
};
const fmtAxis = (v) => {
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(1)}M`; // miliar
  if (abs >= 1e6) return `${(v / 1e6).toFixed(0)}jt`; // juta
  return v;
};

/* ── Sales Trend + Sales vs Budget share one fetch (/trend) — same data,
   two different chart configurations. ── */
function useSalesTrend() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();

  const [year, setYear] = useState(curYear);
  const [years, setYears] = useState([curYear]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [RC, setRC] = useState(null);

  useEffect(() => { import("recharts").then((mod) => setRC(mod)).catch(() => {}); }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${SALES_API}/years`, { headers: hdrs });
        if (res.ok) {
          const ys = await res.json();
          if (ys.length) { setYears(ys); setYear(ys[0]); }
        }
      } catch (_) {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${SALES_API}/trend?year=${year}`, { headers: hdrs });
      if (res.ok) setData((await res.json()).data);
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  useEffect(() => { load(); }, [load]);

  return { year, setYear, years, data, loading, RC };
}

function SalesTrendSection() {
  const { year, setYear, years, data, loading, RC } = useSalesTrend();

  // pivot rows (one per period+business_type) into one row per period,
  // with a column per business_type's actual + a total prior-year line.
  const chartData = (() => {
    if (!data) return [];
    const byPeriod = {};
    for (const r of data) {
      const key = r.period_num;
      byPeriod[key] ||= { period: r.period_name, period_num: r.period_num, prior: 0 };
      byPeriod[key][r.business_type] = r.actual_amount;
      byPeriod[key].prior += r.prior_year_actual || 0;
    }
    return Object.values(byPeriod);
  })();

  const totalActual = (data || []).reduce((s, r) => s + (r.actual_amount || 0), 0);
  const totalPrior = (data || []).reduce((s, r) => s + (r.prior_year_actual || 0), 0);
  const yoyPct = totalPrior > 0 ? (((totalActual - totalPrior) / totalPrior) * 100).toFixed(1) : null;

  const { token } = useAuthStore();
  const [selected, setSelected] = useState(null); // { periodNum, periodLabel, businessType } | null
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const handleBarClick = (row, businessType) => {
    // Recharts' <Bar onClick> passes the clicked Rectangle's props, not the
    // raw chartData row directly — the actual data lives at row.payload for
    // some recharts versions/interactions, at the top level for others.
    // Reading both defensively: without this, clicking any segment other
    // than the first-rendered one silently got an undefined period_num
    // (bad request -> fetch failed -> stale/empty detail table stayed on
    // screen even though the header updated to the newly-clicked segment).
    const source = row?.payload ?? row;
    const periodNum = source?.period_num;
    const periodLabel = source?.period;
    if (periodNum == null) return; // couldn't resolve which bar was clicked — don't fetch garbage
    setSelected({ periodNum, periodLabel, businessType });
  };

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    (async () => {
      setDetailLoading(true);
      setDetail(null); // clear the previous segment's rows immediately — never show stale data under a newly-clicked segment's header
      try {
        const params = new URLSearchParams({ year, month: selected.periodNum, business_type: selected.businessType });
        const res = await fetch(`${SALES_API}/order-detail?${params}`, { headers: { Authorization: `Bearer ${token}` } });
        setDetail(res.ok ? (await res.json()).data : []);
      } catch (_) {
        setDetail([]);
      }
      setDetailLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, year]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select value={year} onChange={(e) => setYear(+e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500">
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {loading && <Loader2 size={16} className="animate-spin text-gray-600" />}
      </div>

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard label="Total Actual (IDR)" value={fmtRp(totalActual)} color="text-blue-400" bg="bg-blue-500/10 border-blue-500/20" />
            <KpiCard label="Total Tahun Lalu (IDR)" value={fmtRp(totalPrior)} color="text-gray-400" bg="bg-gray-800/40 border-gray-700" />
            <KpiCard label="YoY Growth" value={yoyPct !== null ? `${yoyPct}%` : "—"}
              color={yoyPct >= 0 ? "text-green-400" : "text-red-400"}
              bg={yoyPct >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"} />
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
            <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">Sales Trend per Bulan — {year}</p>
            {!RC ? (
              <div className="py-10 text-center text-xs text-gray-500">Loading chart…</div>
            ) : chartData.length === 0 ? (
              <div className="py-10 text-center text-xs text-gray-600">No sales data for year {year}.</div>
            ) : (
              <RC.ResponsiveContainer width="100%" height={300}>
                <RC.ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
                  <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <RC.XAxis dataKey="period" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
                  <RC.YAxis tick={{ fill: "#cbd5e1", fontSize: 10 }} tickFormatter={fmtAxis} />
                  <RC.Tooltip contentStyle={{ borderRadius: 8, fontSize: 11 }} formatter={(v) => fmtRp(v)} />
                  <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
                  {BUSINESS_TYPES.map((bt) => (
                    <RC.Bar key={bt} dataKey={bt} stackId="a" fill={BIZ_COLOR[bt]} radius={[2, 2, 0, 0]}
                      cursor="pointer" onClick={(row) => handleBarClick(row, bt)} />
                  ))}
                  <RC.Line type="monotone" dataKey="prior" name="Tahun Lalu" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 3" dot={{ r: 2, fill: "#94a3b8" }} />
                </RC.ComposedChart>
              </RC.ResponsiveContainer>
            )}
            {!RC ? null : chartData.length > 0 && (
              <p className="text-[11px] text-gray-600 mt-2">Klik salah satu bar untuk lihat rincian order bulan tersebut.</p>
            )}
          </div>

          {selected && (
            <div className="rounded-xl border border-gray-800 bg-gray-900">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
                <h4 className="text-xs font-semibold text-gray-200">
                  Rincian Order — {selected.businessType}, {selected.periodLabel} {year}
                </h4>
                <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-300 text-xs">Tutup ✕</button>
              </div>
              <div className="p-0">
                {detailLoading ? (
                  <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
                ) : !detail || detail.length === 0 ? (
                  <div className="py-10 text-center text-xs text-gray-600">Tidak ada data order untuk periode ini.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
                          <th className="px-3 py-2 text-left font-semibold">Order No</th>
                          <th className="px-3 py-2 text-left font-semibold">Customer</th>
                          <th className="px-3 py-2 text-left font-semibold">Item</th>
                          <th className="px-3 py-2 text-left font-semibold">Status</th>
                          <th className="px-3 py-2 text-right font-semibold">Amount (IDR)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800/60">
                        {detail.map((r, i) => (
                          <tr key={`${r.order_number}-${r.line_num}-${i}`} className="hover:bg-gray-800/30">
                            <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.order_number}-{r.line_num}</td>
                            <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.customer_name || "—"}</td>
                            <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.item_code} — {r.item_description}</td>
                            <td className="px-3 py-2 whitespace-nowrap">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                r.flow_status_code === "CLOSED" ? "bg-green-500/15 text-green-400" : "bg-amber-500/15 text-amber-400"
                              }`}>{r.flow_status_code}</span>
                            </td>
                            <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtRp(r.amount_idr)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SalesVsBudgetSection() {
  const { year, setYear, years, data, loading, RC } = useSalesTrend();

  const chartData = (() => {
    if (!data) return [];
    const byPeriod = {};
    for (const r of data) {
      const key = r.period_num;
      byPeriod[key] ||= { period: r.period_name, Budget: 0, Actual: 0 };
      byPeriod[key].Budget += r.bp_amount || 0;
      byPeriod[key].Actual += r.actual_amount || 0;
    }
    return Object.values(byPeriod);
  })();

  const totalBudget = chartData.reduce((s, r) => s + r.Budget, 0);
  const totalActual = chartData.reduce((s, r) => s + r.Actual, 0);
  const achievementPct = totalBudget > 0 ? ((totalActual / totalBudget) * 100).toFixed(1) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select value={year} onChange={(e) => setYear(+e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500">
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {loading && <Loader2 size={16} className="animate-spin text-gray-600" />}
      </div>

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard label="Total Budget (IDR)" value={fmtRp(totalBudget)} color="text-blue-400" bg="bg-blue-500/10 border-blue-500/20" />
            <KpiCard label="Total Actual (IDR)" value={fmtRp(totalActual)} color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
            <KpiCard label="Achievement" value={achievementPct !== null ? `${achievementPct}%` : "—"}
              color={achievementPct >= 100 ? "text-green-400" : "text-amber-400"}
              bg={achievementPct >= 100 ? "bg-green-500/10 border-green-500/20" : "bg-amber-500/10 border-amber-500/20"} />
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
            <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">Budget vs Actual per Bulan — {year}</p>
            {!RC ? (
              <div className="py-10 text-center text-xs text-gray-500">Loading chart…</div>
            ) : chartData.length === 0 ? (
              <div className="py-10 text-center text-xs text-gray-600">No sales data for year {year}.</div>
            ) : (
              <RC.ResponsiveContainer width="100%" height={300}>
                <RC.BarChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
                  <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <RC.XAxis dataKey="period" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
                  <RC.YAxis tick={{ fill: "#cbd5e1", fontSize: 10 }} tickFormatter={fmtAxis} />
                  <RC.Tooltip contentStyle={{ borderRadius: 8, fontSize: 11 }} formatter={(v) => fmtRp(v)} />
                  <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
                  <RC.Bar dataKey="Budget" fill="#60a5fa" radius={[3, 3, 0, 0]} />
                  <RC.Bar dataKey="Actual" fill="#a78bfa" radius={[3, 3, 0, 0]} />
                </RC.BarChart>
              </RC.ResponsiveContainer>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function OpenSalesOrderSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };

  const [customerName, setCustomerName] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (customerName) params.set("customer_name", customerName);
      if (businessType) params.set("business_type", businessType);
      const res = await fetch(`${SALES_API}/open-orders?${params}`, { headers: hdrs });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerName, businessType]);

  useEffect(() => { load(); }, [load]);

  const kpi = data?.kpi;
  const rows = data?.data || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Customer</label>
          <input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Search customer…"
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 w-52" />
        </div>
        <div>
          <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Business Type</label>
          <select value={businessType} onChange={(e) => setBusinessType(e.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 cursor-pointer">
            <option value="">All</option>
            {BUSINESS_TYPES.map((bt) => <option key={bt} value={bt}>{bt}</option>)}
          </select>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {kpi && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="Open Orders" value={String(kpi.open_order_count)} color="text-blue-400" bg="bg-blue-500/10 border-blue-500/20" />
          <KpiCard label="Open Lines" value={String(kpi.open_line_count)} color="text-gray-300" bg="bg-gray-800/40 border-gray-700" />
          <KpiCard label="Backlog Value (IDR)" value={fmtRp(kpi.total_backlog_idr)} color="text-amber-400" bg="bg-amber-500/10 border-amber-500/20" />
          <KpiCard label="Oldest Order (hari)" value={kpi.oldest_order_days != null ? String(kpi.oldest_order_days) : "—"}
            color={kpi.oldest_order_days > 30 ? "text-red-400" : "text-green-400"}
            bg={kpi.oldest_order_days > 30 ? "bg-red-500/10 border-red-500/20" : "bg-green-500/10 border-green-500/20"} />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center text-xs text-gray-600">No open sales orders match the current filters.</div>
      ) : (
        <div className="rounded-lg border border-gray-800 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
                <th className="px-3 py-2 text-left font-semibold">Order No</th>
                <th className="px-3 py-2 text-left font-semibold">Customer</th>
                <th className="px-3 py-2 text-left font-semibold">Item</th>
                <th className="px-3 py-2 text-left font-semibold">Type</th>
                <th className="px-3 py-2 text-left font-semibold">Status</th>
                <th className="px-3 py-2 text-left font-semibold">Schedule Ship</th>
                <th className="px-3 py-2 text-right font-semibold">Amount (IDR)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {rows.map((r, i) => (
                <tr key={`${r.order_number}-${r.line_num}-${i}`} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.order_number}-{r.line_num}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.customer_name || "—"}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.item_code} — {r.item_description}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.business_type}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-400">{r.flow_status_code}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.schedule_ship_date || "—"}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtRp(r.amount_idr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Root ─────────────────────────────────────────────────────────────── */

const TABS = [
  { id: "trend",        label: "Sales Trend",     icon: TrendingUp },
  { id: "vs-budget",    label: "Sales vs Budget",  icon: AlertCircle },
  { id: "open-orders",  label: "Open Sales Order", icon: Package },
];

export default function SalesMarketing() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeSection = TABS.map((t) => t.id).find((id) => location.pathname.endsWith(id)) ?? "trend";

  useEffect(() => {
    if (location.pathname === "/dashboard/sales" || location.pathname === "/dashboard/sales/" || location.pathname === "/dashboard/sales/overview") {
      navigate("/dashboard/sales/trend", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-6 space-y-4">
      <SubTabs tabs={TABS} active={activeSection} onChange={(id) => navigate(`/dashboard/sales/${id}`)} />
      {activeSection === "trend" && (
        <SectionCard><SalesTrendSection /></SectionCard>
      )}
      {activeSection === "vs-budget" && (
        <SectionCard><SalesVsBudgetSection /></SectionCard>
      )}
      {activeSection === "open-orders" && (
        <SectionCard title="Open Sales Order (Backlog)"><OpenSalesOrderSection /></SectionCard>
      )}
    </div>
  );
}
