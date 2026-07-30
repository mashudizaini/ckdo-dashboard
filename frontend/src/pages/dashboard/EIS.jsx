import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  BarChart2, TrendingUp, TrendingDown, Landmark, Wallet, Users, PieChart as PieIcon,
  Loader2, RefreshCw, Upload, FileSpreadsheet, Save, Plus, Trash2, Play, Square,
  ChevronDown, ChevronUp, Database, CheckCircle2, XCircle, Clock, X, Target, Package,
  DollarSign, Activity,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, ComposedChart, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine, LabelList,
} from "recharts";
import { eisApi } from "@/api/dashboard";

/* ─── Shared constants & helpers ──────────────────────────────────
   Ported from eis-dashboard-v2 (standalone app), restyled to match
   ckdo-dashboard-v2's dark theme. Data-fetching/chart logic kept
   faithful to the original; markup rewritten (no external "pharma"
   Tailwind theme / chart-container classes exist in this app). */

const CY = new Date().getFullYear();
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const MONTHS_FULL_ID = [
  { key: "january", label: "January" }, { key: "february", label: "February" },
  { key: "march", label: "March" }, { key: "april", label: "April" },
  { key: "may", label: "May" }, { key: "june", label: "June" },
  { key: "july", label: "July" }, { key: "august", label: "August" },
  { key: "september", label: "September" }, { key: "october", label: "October" },
  { key: "november", label: "November" }, { key: "december", label: "December" },
];
const BP_MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec_val"];
const BP_MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const fmtN = (v, d = 1) => v == null ? "—" : Number(v).toLocaleString("id-ID", { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtInt = (v) => v == null ? "—" : Number(v).toLocaleString("id-ID", { maximumFractionDigits: 0 });

const TOOLTIP_STYLE = { background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" };
const GRID_STROKE = "rgba(255,255,255,0.06)";
const AXIS_TICK = { fontSize: 11, fill: "#9ca3af" };
const COLOR_PRIMARY = "#22d3ee";   // cyan-400 — matches EIS nav icon color
const COLOR_GOLD = "#d4a843";
const COLOR_GREEN = "#10b981";
const COLOR_RED = "#ef4444";
const COLOR_AMBER = "#f59e0b";

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

function EisKpiCard({ title, value, unit, target, icon: Icon, color = "cyan" }) {
  const numValue = parseFloat(value) || 0;
  const numTarget = parseFloat(target);
  const hasTarget = !isNaN(numTarget) && numTarget > 0;
  const achievement = hasTarget ? (numValue / numTarget * 100) : null;
  const colorMap = {
    cyan: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30",
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/30",
    orange: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  };
  const cls = colorMap[color] || colorMap.cyan;
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg border flex items-center justify-center ${cls}`}>
          {Icon && <Icon size={17} />}
        </div>
        {achievement !== null && (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-1 ${
            achievement >= 90 ? "bg-emerald-500/15 text-emerald-400" : achievement >= 70 ? "bg-amber-500/15 text-amber-400" : "bg-red-500/15 text-red-400"
          }`}>
            {achievement >= 100 ? <TrendingUp size={10} /> : achievement >= 90 ? null : <TrendingDown size={10} />}
            {achievement.toFixed(1)}%
          </span>
        )}
      </div>
      <div className="text-[11px] text-gray-500 font-medium mb-1">{title}</div>
      <div className="text-xl font-bold text-gray-100">
        {typeof value === "number" ? value.toLocaleString("id-ID", { maximumFractionDigits: 1 }) : (value ?? "—")}
        {unit && <span className="text-xs font-normal text-gray-500 ml-1">{unit}</span>}
      </div>
      {hasTarget && (
        <div className="mt-2">
          <div className="flex justify-between text-[10px] text-gray-500 mb-1">
            <span>vs BP</span><span>{numTarget.toLocaleString("id-ID", { maximumFractionDigits: 0 })}</span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${achievement >= 90 ? "bg-emerald-500" : achievement >= 70 ? "bg-amber-500" : "bg-red-500"}`}
              style={{ width: `${Math.min(achievement, 100)}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

function MsgBanner({ msg, onClose }) {
  if (!msg) return null;
  return (
    <div className={`mt-3 flex items-start gap-2 text-xs rounded-lg px-3 py-2 ${msg.type === "err" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400"}`}>
      {msg.type === "ok" && <CheckCircle2 size={13} className="mt-0.5 shrink-0" />}
      <span className="flex-1">{msg.text}</span>
      <button onClick={onClose}><X size={12} /></button>
    </div>
  );
}

const selCls = "text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-1.5 focus:outline-none focus:border-cyan-500";
const uploadBtnCls = "flex items-center gap-2 px-4 py-2.5 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-60";

/* ─── Tab: Summary ──────────────────────────────────────────────── */
function EisSummaryTab({ year, period }) {
  const [kpi, setKpi] = useState(null);
  const [closing, setClosing] = useState([]);
  const [nwc, setNwc] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [kpiRes, closingRes, nwcRes] = await Promise.all([
        eisApi.getKpiCards(year, period),
        eisApi.getClosingEstimation(year, period),
        eisApi.getNwc(year, period),
      ]);
      setKpi(kpiRes.data);
      setClosing(closingRes.data || []);
      setNwc(nwcRes.data);
    } catch (e) { console.error("Failed to load EIS summary:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year, period]); // eslint-disable-line

  if (loading) return <Loading />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <EisKpiCard title="Sales Achievement" value={kpi?.sales_achievement || 0} unit="%" icon={DollarSign} color="cyan" />
        <EisKpiCard title="Production Yield" value={kpi?.yield_pct || 0} unit="%" target={95} icon={Activity} color="emerald" />
        <EisKpiCard title="Net Profit Achievement" value={kpi?.net_profit_achievement || 0} unit="%" icon={Landmark} color="amber" />
        <EisKpiCard title="Cashflow Achievement" value={kpi?.cashflow_achievement || 0} unit="%" icon={Wallet} color="orange" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Sales closing estimation">
          {closing.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={closing} barCategoryGap="25%">
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="business_type" tick={AXIS_TICK} />
                <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => `${fmtInt(v)} M IDR`} contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="bp_total" name="Business Plan" fill={COLOR_PRIMARY} radius={[4, 4, 0, 0]} />
                <Bar dataKey="actual_total" name="Actual" fill={COLOR_GOLD} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="text-center text-gray-600 py-10 text-sm">No data available</div>}
        </ChartCard>

        <ChartCard title="Net working capital">
          {nwc ? (
            <div className="space-y-4">
              <div className="text-center">
                <div className="text-4xl font-bold text-cyan-400">{fmtN(nwc.nwc_days, 1)}</div>
                <div className="text-sm text-gray-500 mt-1">days ({fmtN(nwc.nwc_months, 1)} months)</div>
              </div>
              <div className="grid grid-cols-3 gap-3 mt-4">
                {[
                  { label: "DSO", value: nwc.dso_days, cls: "bg-cyan-500/10 text-cyan-400" },
                  { label: "DIO", value: nwc.dio_days, cls: "bg-amber-500/10 text-amber-400" },
                  { label: "DPO", value: nwc.dpo_days, cls: "bg-emerald-500/10 text-emerald-400" },
                ].map((item) => (
                  <div key={item.label} className={`rounded-lg p-3 text-center ${item.cls}`}>
                    <div className="text-[10px] font-medium opacity-80">{item.label}</div>
                    <div className="text-xl font-bold mt-1">{fmtN(item.value, 1)}</div>
                    <div className="text-[9px] opacity-60">days</div>
                  </div>
                ))}
              </div>
              <div className="text-center text-[10px] text-gray-600 mt-2">NWC = DSO + DIO − DPO</div>
            </div>
          ) : <div className="text-center text-gray-600 py-10 text-sm">No data available</div>}
        </ChartCard>
      </div>
    </div>
  );
}

/* ─── Tab: Performance ──────────────────────────────────────────── */
function EisPerformanceTab({ year, period, segment }) {
  const [monthly, setMonthly] = useState([]);
  const [achievement, setAchievement] = useState([]);
  const [ebit, setEbit] = useState([]);
  const [area, setArea] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [mRes, aRes, eRes, arRes] = await Promise.all([
        eisApi.getMonthlySales(year, segment),
        eisApi.getSalesAchievement(year, segment),
        eisApi.getEbitProduct(year, period),
        eisApi.getAreaSales(year, period),
      ]);
      setMonthly(mRes.data || []);
      setAchievement(aRes.data || []);
      setEbit((eRes.data || []).slice(0, 5));
      setArea(arRes.data || []);
    } catch (e) { console.error("Failed to load EIS performance:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year, period, segment]); // eslint-disable-line

  if (loading) return <Loading />;
  const latestAch = achievement.length > 0 ? achievement[achievement.length - 1] : null;

  return (
    <div className="space-y-4">
      {latestAch && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-6">
          <div className="relative w-24 h-24 shrink-0">
            <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#1f2937" strokeWidth="8" />
              <circle cx="50" cy="50" r="42" fill="none"
                stroke={Number(latestAch.achievement_pct) >= 80 ? COLOR_GREEN : Number(latestAch.achievement_pct) >= 60 ? COLOR_AMBER : COLOR_RED}
                strokeWidth="8" strokeLinecap="round" strokeDasharray={`${Number(latestAch.achievement_pct) * 2.64} 264`} />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold text-gray-100">{fmtN(latestAch.achievement_pct, 1)}%</span>
              <span className="text-[9px] text-gray-500">YTD</span>
            </div>
          </div>
          <div>
            <div className="text-base font-semibold text-gray-200">{segment === "all" ? "Company" : segment} sales achievement</div>
            <div className="text-xs text-gray-500 mt-1">
              Actual: {fmtInt(latestAch.actual_cumulative)} M IDR / BP: {fmtInt(latestAch.bp_cumulative)} M IDR
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Monthly sales: BP vs actual">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={monthly} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="bp_amount" name="Business Plan" fill={COLOR_PRIMARY} radius={[3, 3, 0, 0]} />
              <Bar dataKey="actual_amount" name="Actual" fill={COLOR_GOLD} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Cumulative achievement trend">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={achievement} barCategoryGap="25%">
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} unit="%" domain={[0, 130]} />
              <Tooltip formatter={(v) => [`${fmtN(v, 1)}%`, "Achievement"]} contentStyle={TOOLTIP_STYLE} />
              <ReferenceLine y={100} stroke={COLOR_RED} strokeDasharray="6 3" label={{ value: "Target 100%", fill: COLOR_RED, fontSize: 10, position: "insideTopRight" }} />
              <Bar dataKey="achievement_pct" name="Achievement %" radius={[4, 4, 0, 0]} maxBarSize={40}>
                {achievement.map((entry, i) => (
                  <Cell key={i} fill={Number(entry.achievement_pct) >= 100 ? COLOR_GREEN : Number(entry.achievement_pct) >= 80 ? COLOR_GOLD : COLOR_RED} />
                ))}
                <LabelList dataKey="achievement_pct" position="top" formatter={(v) => `${Number(v).toFixed(0)}%`} style={{ fontSize: 10, fontWeight: 600, fill: "#9ca3af" }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="EBIT — Product" subtitle="Top 5 produk berdasarkan nilai penjualan tertinggi">
          {ebit.length === 0 ? <div className="text-center text-gray-600 py-10 text-sm">No data available</div> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={ebit} layout="vertical" margin={{ left: 130, right: 60, top: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} tickFormatter={(v) => `${v}%`} domain={[0, "dataMax + 5"]} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="product_name" tick={{ fontSize: 11, fill: "#d1d5db" }} width={125} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => [`${fmtN(v, 1)}%`, "EBIT %"]} contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="ebit_pct" name="EBIT %" radius={[0, 4, 4, 0]} barSize={28} fill={COLOR_PRIMARY}>
                  <LabelList dataKey="ebit_pct" position="right" formatter={(v) => `${Number(v).toFixed(0)}%`} style={{ fontSize: 11, fontWeight: 600, fill: "#9ca3af" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Area sales performance">
          {area.length > 0 ? (
            <div className="space-y-3">
              {area.map((a) => (
                <div key={a.area_name} className="flex items-center gap-3">
                  <div className="w-24 text-xs font-medium text-gray-300 truncate">{a.area_name}</div>
                  <div className="flex-1 h-6 bg-gray-800 rounded-full overflow-hidden relative">
                    <div className="h-full bg-cyan-500 rounded-full transition-all duration-700" style={{ width: `${Number(a.portion_pct)}%` }} />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-medium text-gray-300">{fmtInt(a.cumulative_amount)} M</span>
                  </div>
                  <div className="w-12 text-right text-xs font-mono font-medium text-cyan-400">{fmtN(a.portion_pct, 1)}%</div>
                </div>
              ))}
            </div>
          ) : <div className="text-center text-gray-600 py-10 text-sm">No data available</div>}
        </ChartCard>
      </div>
    </div>
  );
}

/* ─── Tab: Production ───────────────────────────────────────────── */
function EisProductionTab({ year, period }) {
  const [yieldData, setYieldData] = useState([]);
  const [overtime, setOvertime] = useState([]);
  const [cogs, setCogs] = useState([]);
  const [release, setRelease] = useState([]);
  const [dio, setDio] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [yRes, oRes, cRes, rRes, dRes] = await Promise.all([
        eisApi.getYieldProduction(year), eisApi.getOvertime(year),
        eisApi.getCogsRatio(year, period), eisApi.getReleaseTime(year), eisApi.getDio(year),
      ]);
      setYieldData(yRes.data || []);
      setOvertime(oRes.data || []);
      setCogs((cRes.data || []).slice(0, 14));
      setRelease(rRes.data || []);
      setDio(dRes.data || []);
    } catch (e) { console.error("Failed to load EIS production:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year, period]); // eslint-disable-line

  if (loading) return <Loading />;
  const latestYield = yieldData.length > 0 ? yieldData[yieldData.length - 1] : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Current yield", value: `${fmtN(latestYield?.yield_pct || 0, 1)}%`, sub: "Target: 95%", good: Number(latestYield?.yield_pct || 0) >= 95 },
          { label: "Days inventory (DIO)", value: dio.length ? fmtN(dio[dio.length - 1].dio_days, 0) : "—", sub: "days", good: null },
          { label: "FG release time", value: release.length ? release[release.length - 1].actual_days : "—", sub: "days (target: 16)", good: release.length && Number(release[release.length - 1]?.actual_days) <= 16 },
          { label: "Overtime ratio", value: overtime.length ? `${fmtN(overtime[overtime.length - 1]?.ratio_pct, 1)}%` : "—", sub: "Target: <15%", good: overtime.length && Number(overtime[overtime.length - 1]?.ratio_pct) <= 15 },
        ].map((k) => (
          <div key={k.label} className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
            <div className="text-xs text-gray-500 font-medium mb-2">{k.label}</div>
            <div className={`text-3xl font-bold ${k.good === null ? "text-cyan-400" : k.good ? "text-emerald-400" : "text-amber-400"}`}>{k.value}</div>
            <div className="text-[10px] text-gray-600 mt-1">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Yield production trend">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={yieldData}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} unit="%" domain={[80, 100]} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <ReferenceLine y={95} stroke={COLOR_RED} strokeDasharray="5 5" label={{ value: "Target 95%", position: "right", fontSize: 10, fill: COLOR_RED }} />
              <Line type="monotone" dataKey="yield_pct" stroke={COLOR_GREEN} strokeWidth={2.5} dot={{ r: 4, fill: COLOR_GREEN }} name="Yield %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Plant overtime ratio">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={overtime}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} unit="%" />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <ReferenceLine y={15} stroke={COLOR_RED} strokeDasharray="5 5" label={{ value: "15%", position: "right", fontSize: 10, fill: COLOR_RED }} />
              <Bar dataKey="ratio_pct" name="Overtime %" radius={[4, 4, 0, 0]}>
                {overtime.map((entry, i) => (
                  <Cell key={i} fill={Number(entry.ratio_pct) <= 15 ? COLOR_GREEN : Number(entry.ratio_pct) <= 20 ? COLOR_AMBER : COLOR_RED} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="COGS ratio by product">
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={cogs} layout="vertical" margin={{ left: 130 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis type="number" tick={AXIS_TICK} />
              <YAxis type="category" dataKey="product_name" tick={{ fontSize: 10, fill: "#d1d5db" }} width={125} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="cogs_rate" name="COGS Ratio" radius={[0, 4, 4, 0]}>
                {cogs.map((entry, i) => (
                  <Cell key={i} fill={Number(entry.cogs_rate) > 1 ? COLOR_RED : Number(entry.cogs_rate) > 0.7 ? COLOR_AMBER : COLOR_PRIMARY} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Days inventory outstanding (DIO)">
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={dio}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} unit=" d" />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <ReferenceLine y={150} stroke={COLOR_AMBER} strokeDasharray="5 5" />
              <Line type="monotone" dataKey="dio_days" stroke={COLOR_GOLD} strokeWidth={2.5} dot={{ r: 4 }} name="DIO (days)" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

/* ─── Tab: Expansion ────────────────────────────────────────────── */
const STAGE_COLORS = {
  1: { bg: "bg-gray-700", text: "text-gray-200", label: "Market Analysis" },
  2: { bg: "bg-blue-800", text: "text-blue-200", label: "Resource Supplier" },
  3: { bg: "bg-amber-700", text: "text-amber-100", label: "Contract Agreement" },
  4: { bg: "bg-emerald-800", text: "text-emerald-200", label: "Registration" },
  5: { bg: "bg-emerald-500", text: "text-white", label: "Launch Preparation" },
};

function EisExpansionTab({ year, period }) {
  const [pipeline, setPipeline] = useState([]);
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [pRes, sRes] = await Promise.all([eisApi.getPipeline(year), eisApi.getPipelineSummary(year, period)]);
      setPipeline(pRes.data || []);
      setSummary(sRes.data || []);
    } catch (e) { console.error("Failed to load EIS expansion:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year, period]); // eslint-disable-line

  if (loading) return <Loading />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {Object.entries(STAGE_COLORS).map(([order, style]) => {
          const count = summary.find((s) => s.stage_order === Number(order))?.product_count || 0;
          return (
            <div key={order} className={`rounded-xl p-4 ${style.bg} ${style.text}`}>
              <div className="text-xs font-medium opacity-80">{style.label}</div>
              <div className="text-3xl font-bold mt-1">{count}</div>
              <div className="text-[10px] opacity-60 mt-0.5">products</div>
            </div>
          );
        })}
      </div>

      <ChartCard title="Business development progress" className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left py-2 px-3 font-medium text-gray-400 w-40">Product</th>
              <th className="text-left py-2 px-3 font-medium text-gray-400 w-44">Supplier</th>
              {MONTHS_SHORT.map((m, i) => (
                <th key={i} className={`text-center py-2 px-1 font-medium text-gray-500 w-16 ${i + 1 === period ? "bg-cyan-500/10 text-cyan-400 rounded-t-lg" : ""}`}>{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pipeline.map((product, idx) => (
              <tr key={idx} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                <td className="py-2 px-3 font-medium text-gray-200">{product.product_name}</td>
                <td className="py-2 px-3 text-gray-500 text-xs">{product.supplier}<span className="text-gray-600 ml-1">({product.country_origin})</span></td>
                {MONTHS_SHORT.map((_, monthIdx) => {
                  const monthData = product.months?.[monthIdx + 1];
                  if (!monthData) {
                    return <td key={monthIdx} className={`py-1.5 px-0.5 ${monthIdx + 1 === period ? "bg-cyan-500/5" : ""}`}><div className="h-7 rounded bg-gray-800/60" /></td>;
                  }
                  const stage = STAGE_COLORS[monthData.stage_order] || STAGE_COLORS[1];
                  return (
                    <td key={monthIdx} className={`py-1.5 px-0.5 ${monthIdx + 1 === period ? "bg-cyan-500/5" : ""}`}>
                      <div className={`h-7 rounded ${stage.bg} ${stage.text} flex items-center justify-center text-[9px] font-medium`}
                        title={`${monthData.stage_name}${monthData.status_text ? ": " + monthData.status_text : ""}`}>
                        {monthData.stage_order}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
            {pipeline.length === 0 && <tr><td colSpan={14} className="py-10 text-center text-gray-600">No pipeline data</td></tr>}
          </tbody>
        </table>
        <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-gray-800">
          {Object.entries(STAGE_COLORS).map(([order, style]) => (
            <div key={order} className="flex items-center gap-1.5">
              <div className={`w-5 h-5 rounded ${style.bg} flex items-center justify-center text-[10px] font-bold ${style.text}`}>{order}</div>
              <span className="text-xs text-gray-500">{style.label}</span>
            </div>
          ))}
        </div>
      </ChartCard>
    </div>
  );
}

/* ─── Tab: Administration ───────────────────────────────────────── */
const ADMIN_TABS = [
  { key: "personnel", label: "Personnel", icon: Users },
  { key: "financial", label: "Financial", icon: Landmark },
  { key: "ratios", label: "Ratios", icon: PieIcon },
  { key: "budget", label: "Budget", icon: Wallet },
];

function EisAdministrationTab({ year }) {
  const [tab, setTab] = useState("personnel");
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [hRes, tRes, pRes, cRes, rRes, bRes] = await Promise.all([
        eisApi.getHeadcount(year), eisApi.getTurnover(year), eisApi.getProfit(year),
        eisApi.getCashflow(year), eisApi.getRatios(year), eisApi.getBudget(year),
      ]);
      setData({
        headcount: hRes.data || [], turnover: tRes.data || [], profit: pRes.data || [],
        cashflow: cRes.data || [], ratios: rRes.data || [], budget: bRes.data || [],
      });
    } catch (e) { console.error("Failed to load EIS administration:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year]); // eslint-disable-line

  if (loading) return <Loading />;

  const headcountByMonth = {};
  (data.headcount || []).forEach((r) => {
    if (!headcountByMonth[r.period_num]) headcountByMonth[r.period_num] = { period_name: r.period_name, period_num: r.period_num, total: 0 };
    headcountByMonth[r.period_num][r.dept_group] = r.headcount;
    headcountByMonth[r.period_num].total += r.headcount;
  });
  const headcountChart = Object.values(headcountByMonth).sort((a, b) => a.period_num - b.period_num);

  const budgetByMonth = {};
  (data.budget || []).forEach((r) => {
    if (!budgetByMonth[r.period_num]) budgetByMonth[r.period_num] = { period_name: r.period_name, bp: 0, actual: 0 };
    budgetByMonth[r.period_num].bp += Number(r.bp_amount || 0);
    budgetByMonth[r.period_num].actual += Number(r.actual_amount || 0);
  });
  const budgetChart = Object.values(budgetByMonth);

  return (
    <div className="space-y-4">
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        {ADMIN_TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-colors ${tab === key ? "bg-cyan-600 text-white" : "text-gray-400 hover:bg-gray-800"}`}>
            <Icon size={14} />{label}
          </button>
        ))}
      </div>

      {tab === "personnel" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title="Employee headcount">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={headcountChart}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="SM" stackId="a" fill={COLOR_PRIMARY} name="S&M" />
                <Bar dataKey="SD" stackId="a" fill="#47a7c7" name="SD" />
                <Bar dataKey="Plant Direct" stackId="a" fill={COLOR_GREEN} name="Plant Direct" />
                <Bar dataKey="Plant Indirect" stackId="a" fill="#6ee7b7" name="Plant Indirect" />
                <Bar dataKey="Admin" stackId="a" fill={COLOR_GOLD} name="Admin" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Turnover rate">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data.turnover}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} unit="%" />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <ReferenceLine y={15} stroke={COLOR_AMBER} strokeDasharray="5 5" />
                <ReferenceLine y={20} stroke={COLOR_RED} strokeDasharray="5 5" />
                <Line type="monotone" dataKey="turnover_pct" stroke="#ef6c4a" strokeWidth={2.5} dot={{ r: 4 }} name="Turnover %" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {tab === "financial" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title="Monthly net profit">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.profit}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <ReferenceLine y={0} stroke="#4b5563" />
                <Bar dataKey="net_profit_actual" name="Net Profit" radius={[4, 4, 0, 0]}>
                  {(data.profit || []).map((entry, i) => <Cell key={i} fill={Number(entry.net_profit_actual) >= 0 ? COLOR_GREEN : COLOR_RED} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Cashflow: plan vs actual">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data.cashflow}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="cf_ending_balance_bp" stroke="#6b7280" strokeWidth={1.5} strokeDasharray="5 5" name="Plan" dot={false} />
                <Line type="monotone" dataKey="cf_ending_balance_actual" stroke={COLOR_PRIMARY} strokeWidth={2.5} dot={{ r: 3 }} name="Actual" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {tab === "ratios" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title="DSO & DPO trend">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data.ratios}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} unit=" d" />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="dso_days" stroke={COLOR_PRIMARY} strokeWidth={2} dot={{ r: 3 }} name="DSO" />
                <Line type="monotone" dataKey="dpo_days" stroke={COLOR_GOLD} strokeWidth={2} dot={{ r: 3 }} name="DPO" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Net working capital trend">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data.ratios}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} unit=" d" />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="nwc_days" stroke="#ef6c4a" strokeWidth={2.5} dot={{ r: 4 }} name="NWC (days)" />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {tab === "budget" && (
        <ChartCard title="Monthly budget: plan vs actual">
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={budgetChart} barCategoryGap="25%">
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
              <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="bp" name="Business Plan" fill={COLOR_PRIMARY} radius={[4, 4, 0, 0]} />
              <Bar dataKey="actual" name="Actual" fill={COLOR_GOLD} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  );
}

/* ─── Tab: Business Plan ────────────────────────────────────────── */
function EisBusinessPlanTab({ year }) {
  const [plans, setPlans] = useState([]);
  const [types, setTypes] = useState([]);
  const [selectedType, setSelectedType] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const blankForm = { fiscal_year: year, plan_type: "", category: "", sub_category: "", jan: 0, feb: 0, mar: 0, apr: 0, may: 0, jun: 0, jul: 0, aug: 0, sep: 0, oct: 0, nov: 0, dec_val: 0 };
  const [form, setForm] = useState(blankForm);

  const load = async () => {
    setLoading(true);
    try {
      const [tRes, pRes] = await Promise.all([eisApi.getBpTypes(), eisApi.getBpList(year, selectedType || undefined)]);
      setTypes(tRes.data || []);
      setPlans(pRes.data || []);
    } catch (e) { console.error("Failed to load business plan:", e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [year, selectedType]); // eslint-disable-line

  const handleSave = async () => {
    if (!form.plan_type || !form.category) return;
    setSaving(true);
    try {
      await eisApi.saveBp({ ...form, fiscal_year: year });
      await load();
      setShowForm(false);
      setForm(blankForm);
    } catch (e) {
      alert("Failed to save: " + (e?.response?.data?.detail || e?.detail || e.message));
    }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this entry?")) return;
    try {
      await eisApi.deleteBp(id);
      setPlans((p) => p.filter((x) => x.id !== id));
    } catch (e) { alert("Failed to delete"); }
  };

  const total = BP_MONTHS.reduce((s, m) => s + Number(form[m] || 0), 0);
  if (loading) return <Loading />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <FileSpreadsheet size={16} className="text-cyan-400" />
          <select value={selectedType} onChange={(e) => setSelectedType(e.target.value)} className={selCls}>
            <option value="">All Types</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <button onClick={() => setShowForm((v) => !v)} className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-700 text-white px-4 py-2 rounded-lg text-xs font-medium transition-colors">
          <Plus size={14} /> Add entry
        </button>
      </div>

      {showForm && (
        <ChartCard title="New business plan entry">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
            <select value={form.plan_type} onChange={(e) => setForm({ ...form, plan_type: e.target.value })} className={selCls}>
              <option value="">Select type...</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input type="text" placeholder="Category (e.g. Local Public)" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-2 focus:outline-none focus:border-cyan-500" />
            <input type="text" placeholder="Sub-category (optional)" value={form.sub_category} onChange={(e) => setForm({ ...form, sub_category: e.target.value })}
              className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-2 focus:outline-none focus:border-cyan-500" />
            <div className="flex items-center gap-2 text-xs text-gray-400">Total: <span className="font-mono font-bold text-cyan-400">{fmtInt(total)}</span></div>
          </div>
          <div className="grid grid-cols-6 sm:grid-cols-12 gap-2 mb-4">
            {BP_MONTHS.map((m, i) => (
              <div key={m}>
                <label className="text-[9px] text-gray-500 block mb-1">{BP_MONTH_LABELS[i]}</label>
                <input type="number" step="0.01" value={form[m]} onChange={(e) => setForm({ ...form, [m]: Number(e.target.value) || 0 })}
                  className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5 text-right font-mono focus:outline-none focus:border-cyan-500" />
              </div>
            ))}
          </div>
          <button onClick={handleSave} disabled={saving || !form.plan_type || !form.category}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-50">
            <Save size={14} /> {saving ? "Saving..." : "Save"}
          </button>
        </ChartCard>
      )}

      <ChartCard title="" className="overflow-x-auto !pt-3">
        <table className="w-full min-w-[1000px] text-xs">
          <thead>
            <tr className="border-b-2 border-gray-800">
              <th className="text-left py-2 px-2 font-medium text-gray-400">Type</th>
              <th className="text-left py-2 px-2 font-medium text-gray-400">Category</th>
              <th className="text-left py-2 px-2 font-medium text-gray-400">Sub</th>
              {BP_MONTH_LABELS.map((m) => <th key={m} className="text-right py-2 px-1 font-medium text-gray-500 w-16">{m}</th>)}
              <th className="text-right py-2 px-2 font-medium text-gray-400">Total</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {plans.length === 0 ? (
              <tr><td colSpan={16} className="py-10 text-center text-gray-600">No entries yet. Click "Add entry" to start.</td></tr>
            ) : plans.map((p) => (
              <tr key={p.id} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                <td className="py-2 px-2 font-medium text-cyan-400">{p.plan_type}</td>
                <td className="py-2 px-2 text-gray-300">{p.category}</td>
                <td className="py-2 px-2 text-gray-500">{p.sub_category || "—"}</td>
                {["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].map((m) => (
                  <td key={m} className="py-2 px-1 text-right font-mono text-gray-400">{fmtInt(p[m])}</td>
                ))}
                <td className="py-2 px-2 text-right font-mono font-bold text-gray-200">{fmtInt(p.total)}</td>
                <td className="py-2 px-1"><button onClick={() => handleDelete(p.id)} className="p-1 text-gray-600 hover:text-red-400"><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </div>
  );
}

/* ─── Tab: Daily Sales ──────────────────────────────────────────── */
function EisDailySalesTab({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState("december");
  // Upload target year — defaults to the page's shared Year selector but is
  // independently adjustable, same convention as the Data Upload tab's
  // uploaders. Required on every upload so the file is stored under the
  // right year instead of silently overwriting whatever was there before.
  const [uploadYear, setUploadYear] = useState(year);
  const [deleting, setDeleting] = useState(false);
  const fileRef = useRef(null);
  const YEARS = Array.from({ length: 5 }, (_, i) => CY - i);

  const load = async (y) => {
    setLoading(true);
    try {
      const d = (await eisApi.getDailySales(y)).data;
      setData(d);
      // Point the month selector at whatever month this year's data actually
      // has (backend's last_month_with_data), instead of leaving it on
      // whatever month was selected for the previous year — otherwise
      // switching to a year that hasn't reached that month yet (e.g. every
      // year before it's over) shows a chart with zero rows and looks like
      // the whole chart failed to load.
      if (d?.month) setSelectedMonth(d.month.toLowerCase());
    }
    catch (e) { console.error("Failed to load daily sales:", e); }
    setLoading(false);
  };

  useEffect(() => { load(year); }, [year]); // eslint-disable-line

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await eisApi.uploadDailySales(fd, uploadYear);
      setMsg({ type: "ok", text: res.message || `Data successfully updated from "${file.name}"` });
      if (uploadYear === year) setData(res.data);
    } catch (err) {
      setMsg({ type: "err", text: "Upload failed: " + (err?.response?.data?.detail || err?.detail || err.message) });
    }
    setUploading(false); e.target.value = "";
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete Daily Sales data for ${year}? This action cannot be undone.`)) return;
    setDeleting(true); setMsg(null);
    try {
      const res = await eisApi.deleteDailySales(year);
      setMsg({ type: "ok", text: res.message || `Data for ${year} successfully deleted` });
      setData(null);
    } catch (err) {
      setMsg({ type: "err", text: "Delete failed: " + (err?.response?.data?.detail || err?.detail || err.message) });
    }
    setDeleting(false);
  };

  if (loading) return <Loading />;
  const rows = data?.rows || [];
  const monthTargets = data?.month_targets || {};
  const achPct = data?.achievement_pct || 0;
  const achColor = achPct >= 100 ? "text-emerald-400" : achPct >= 80 ? "text-amber-400" : "text-red-400";
  const chartData = rows.filter((r) => r[selectedMonth]?.acc != null).map((r) => ({ wd: r.wd, acc: r[selectedMonth].acc, sales: r[selectedMonth].sales }));
  const monthTarget = monthTargets[selectedMonth] || 0;

  return (
    <div className="space-y-4">
      <ChartCard title="Upload Data Excel" subtitle={`Worksheet "Chart" (WD, Target, Acc, Sales per month) + "Daily Sales Performance". Reference format: EIS_Sales_Daily.xlsx`}
        right={
          <div className="flex items-center gap-2 shrink-0">
            <select value={uploadYear} onChange={(e) => setUploadYear(Number(e.target.value))} className={selCls} title="Year the data belongs to">
              {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <button onClick={() => fileRef.current?.click()} disabled={uploading} className={`${uploadBtnCls} bg-cyan-600 hover:bg-cyan-700`}>
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {uploading ? "Uploading..." : `Choose File for ${uploadYear} (.xlsx)`}
            </button>
            <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleUpload} />
            {data && (
              <button onClick={handleDelete} disabled={deleting} title={`Delete Daily Sales data for ${year}`}
                className={`${uploadBtnCls} bg-red-600/80 hover:bg-red-600`}>
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} Delete Data {year}
              </button>
            )}
          </div>
        }>
        <MsgBanner msg={msg} onClose={() => setMsg(null)} />
      </ChartCard>

      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1">Daily Sales Performance — {year} ({data?.month || "no data yet"})</h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <EisKpiCard title="Business Plan" value={`${fmtN(data?.business_plan, 2)} M`} icon={Target} color="cyan" />
        <EisKpiCard title="Expectation Closing" value={`${fmtN(data?.expectation_closing, 2)} M`} icon={TrendingUp} color="amber" />
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg border border-emerald-500/30 bg-emerald-500/10 flex items-center justify-center"><CheckCircle2 size={17} className="text-emerald-400" /></div>
            <div>
              <div className="text-[11px] text-gray-500 font-medium">Achievement</div>
              <div className={`text-xl font-bold ${achColor}`}>{fmtN(achPct, 2)}%</div>
            </div>
          </div>
        </div>
      </div>

      <ChartCard title="Accumulated Sales per Working Day"
        right={
          <select value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)} className={selCls}>
            {MONTHS_FULL_ID.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        }>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={chartData} margin={{ right: 16, left: 8, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis dataKey="wd" tick={AXIS_TICK} label={{ value: "Working Day", position: "insideBottomRight", offset: -4, fontSize: 10, fill: "#6b7280" }} />
            <YAxis tick={AXIS_TICK} tickFormatter={(v) => `${(v / 1000).toFixed(1)}K`} width={52} />
            <Tooltip formatter={(v, name) => [`${fmtN(v, 2)} M IDR`, name]} labelFormatter={(l) => `Working Day ${l}`} contentStyle={TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {monthTarget > 0 && <ReferenceLine y={monthTarget} ifOverflow="extendDomain" stroke={COLOR_PRIMARY} strokeWidth={2} strokeDasharray="6 3" label={{ value: `BP ${fmtN(monthTarget, 0)}M`, fill: COLOR_PRIMARY, fontSize: 10, position: "insideTopRight" }} />}
            <Bar dataKey="sales" fill="#6b7280" name="Sales" maxBarSize={14} radius={[2, 2, 0, 0]} />
            <Line type="monotone" dataKey="acc" stroke="#e07b39" strokeWidth={2.5} dot={{ r: 2.5, fill: "#e07b39", strokeWidth: 0 }} activeDot={{ r: 5 }} name="Acc" />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="Daily Sales Detail per Working Day" subtitle="in Million IDR · Acc = Accumulated, Sales = Daily" className="overflow-x-auto">
        <table className="text-[11px] border-collapse" style={{ minWidth: "1100px", width: "100%" }}>
          <thead>
            <tr className="bg-gray-950 text-gray-200">
              <th className="px-3 py-2 text-center font-semibold sticky left-0 bg-gray-950 z-10 w-10 border-r border-gray-800">WD</th>
              {MONTHS_SHORT.map((m, idx) => (
                <th key={m} colSpan={2} className="py-2 text-center font-semibold border-l border-gray-800">
                  <div>{m}</div>
                  <div className="text-[9px] font-normal text-gray-500">{fmtN(monthTargets[MONTHS_FULL_ID[idx].key], 0)}M</div>
                </th>
              ))}
            </tr>
            <tr className="bg-gray-900 text-gray-500 text-[9px]">
              <th className="px-3 py-1 sticky left-0 bg-gray-900 z-10 border-r border-gray-800" />
              {MONTHS_SHORT.map((m) => (
                <Fragment key={m}>
                  <th className="px-1.5 py-1 text-center border-l border-gray-800 font-medium">Acc</th>
                  <th className="px-1.5 py-1 text-center font-medium text-gray-600">Sales</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.wd} className={`border-b border-gray-800/60 hover:bg-gray-800/40 ${idx % 2 === 0 ? "bg-gray-900" : "bg-gray-900/60"}`}>
                <td className="px-3 py-1.5 font-mono font-bold text-cyan-400 text-center sticky left-0 bg-inherit z-10 border-r border-gray-800">{row.wd}</td>
                {MONTHS_FULL_ID.map((m) => {
                  const cell = row[m.key] || {};
                  const overTarget = cell.acc != null && monthTargets[m.key] && cell.acc >= monthTargets[m.key];
                  return (
                    <Fragment key={m.key}>
                      <td className={`px-1.5 py-1.5 text-right font-mono border-l border-gray-800/60 ${cell.acc == null ? "text-gray-700" : overTarget ? "text-emerald-400 font-semibold" : "text-gray-300"}`}>{fmtInt(cell.acc)}</td>
                      <td className={`px-1.5 py-1.5 text-right font-mono ${cell.sales == null ? "text-gray-700" : cell.sales < 0 ? "text-red-400" : "text-gray-500"}`}>{fmtInt(cell.sales)}</td>
                    </Fragment>
                  );
                })}
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={25} className="py-10 text-center text-gray-600">No data uploaded yet</td></tr>}
          </tbody>
        </table>
      </ChartCard>
    </div>
  );
}

/* ─── Tab: Data Upload (Overtime / Sales BP / COGS) ────────────────*/
function EisDataUploadTab({ year: sharedYear }) {
  const [selectedYear, setSelectedYear] = useState(sharedYear || CY);
  const [selectedPeriod, setSelectedPeriod] = useState(12);

  const [overtime, setOvertime] = useState([]);
  const [otLoading, setOtLoading] = useState(true);
  const [otUploading, setOtUploading] = useState(false);
  const [otMsg, setOtMsg] = useState(null);
  const otFileRef = useRef(null);

  const [cogs, setCogs] = useState([]);
  const [cogsLoading, setCogsLoading] = useState(true);
  const [cogsUploading, setCogsUploading] = useState(false);
  const [cogsMsg, setCogsMsg] = useState(null);
  const cogsFileRef = useRef(null);

  const [salesBP, setSalesBP] = useState([]);
  const [bpLoading, setBpLoading] = useState(true);
  const [bpUploading, setBpUploading] = useState(false);
  const [bpMsg, setBpMsg] = useState(null);
  const bpFileRef = useRef(null);

  const loadOvertime = async () => { setOtLoading(true); try { setOvertime((await eisApi.getOvertimeData(selectedYear)).data || []); } catch (e) { console.error(e); } setOtLoading(false); };
  const loadCogs = async () => { setCogsLoading(true); try { setCogs((await eisApi.getCogsUploadData(selectedYear, selectedPeriod)).data || []); } catch (e) { console.error(e); } setCogsLoading(false); };
  const loadSalesBP = async () => { setBpLoading(true); try { setSalesBP((await eisApi.getSalesBP(selectedYear)).data || []); } catch (e) { console.error(e); } setBpLoading(false); };

  useEffect(() => { loadOvertime(); }, [selectedYear]); // eslint-disable-line
  useEffect(() => { loadCogs(); }, [selectedYear, selectedPeriod]); // eslint-disable-line
  useEffect(() => { loadSalesBP(); }, [selectedYear]); // eslint-disable-line

  const handleOtUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setOtUploading(true); setOtMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadOvertimeData(selectedYear, fd);
      setOvertime(res.data || []);
      setOtMsg({ type: "ok", text: res.message });
    } catch (err) { setOtMsg({ type: "err", text: "Gagal: " + (err?.response?.data?.detail || err?.detail || err.message) }); }
    setOtUploading(false); e.target.value = "";
  };

  const handleCogsUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setCogsUploading(true); setCogsMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadCogsData(selectedYear, fd);
      await loadCogs();
      const skipped = res.skipped?.length > 0 ? ` (tidak cocok: ${res.skipped.join(", ")})` : "";
      setCogsMsg({ type: "ok", text: res.message + skipped });
    } catch (err) { setCogsMsg({ type: "err", text: "Gagal: " + (err?.response?.data?.detail || err?.detail || err.message) }); }
    setCogsUploading(false); e.target.value = "";
  };

  const handleBPUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setBpUploading(true); setBpMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadSalesBP(selectedYear, fd);
      await loadSalesBP();
      const note = res.detected_year && res.detected_year !== selectedYear ? ` (tahun di file: ${res.detected_year})` : "";
      setBpMsg({ type: "ok", text: res.message + note });
    } catch (err) { setBpMsg({ type: "err", text: "Gagal: " + (err?.response?.data?.detail || err?.detail || err.message) }); }
    setBpUploading(false); e.target.value = "";
  };

  const YearSelector = () => (
    <div className="flex items-center gap-2">
      <label className="text-xs text-gray-500 font-medium">Tahun:</label>
      <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))} className={selCls}>
        {Array.from({ length: 5 }, (_, i) => CY - i).map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
    </div>
  );

  return (
    <div className="space-y-4">
      <ChartCard title="Upload Data Overtime" subtitle="Format kolom B: label (Overtime Hour / Working Hour) · Kolom C–N: Jan–Dec · Referensi: overtime_data.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => otFileRef.current?.click()} disabled={otUploading} className={`${uploadBtnCls} bg-cyan-600 hover:bg-cyan-700`}>
              {otUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {otUploading ? "Mengupload..." : "Pilih File"}
            </button>
            <input ref={otFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleOtUpload} />
          </div>
        }>
        <MsgBanner msg={otMsg} onClose={() => setOtMsg(null)} />
      </ChartCard>

      <ChartCard title="Upload Data Business Plan Sales" subtitle="Header bulan (Jan–Dec) + baris segmen (Total/Local/CMO/Export), nilai dalam juta IDR. Referensi: DATA BP.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => bpFileRef.current?.click()} disabled={bpUploading} className={`${uploadBtnCls} bg-blue-600 hover:bg-blue-700`}>
              {bpUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {bpUploading ? "Mengupload..." : "Pilih File"}
            </button>
            <input ref={bpFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleBPUpload} />
          </div>
        }>
        <MsgBanner msg={bpMsg} onClose={() => setBpMsg(null)} />
      </ChartCard>

      {!bpLoading && salesBP.length > 0 && (
        <ChartCard title={`Sales Business Plan — ${selectedYear}`} right={<button onClick={loadSalesBP} className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"><RefreshCw size={12} /> Refresh</button>} className="overflow-x-auto">
          <table className="text-xs border-collapse" style={{ minWidth: "900px", width: "100%" }}>
            <thead>
              <tr className="bg-blue-950 text-white">
                <th className="px-3 py-2 text-left font-semibold sticky left-0 bg-blue-950 z-10">Segmen</th>
                {BP_MONTH_LABELS.map((m) => <th key={m} className="px-2 py-2 text-right font-semibold">{m}</th>)}
                <th className="px-3 py-2 text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {salesBP.map((row, i) => {
                const months = [row.jan, row.feb, row.mar, row.apr, row.may, row.jun, row.jul, row.aug, row.sep, row.oct, row.nov, row.dec];
                const isTotal = row.category === "Total";
                return (
                  <tr key={i} className={`border-b border-gray-800/60 ${isTotal ? "bg-blue-900/30 font-semibold" : i % 2 === 0 ? "bg-gray-900" : "bg-gray-900/60"}`}>
                    <td className={`px-3 py-1.5 sticky left-0 z-10 ${isTotal ? "bg-blue-900/30 font-bold text-blue-300" : "bg-inherit text-gray-300 font-medium"}`}>{row.category}</td>
                    {months.map((v, mi) => <td key={mi} className="px-2 py-1.5 text-right font-mono text-gray-400">{v != null ? fmtInt(v) : "—"}</td>)}
                    <td className={`px-3 py-1.5 text-right font-mono font-bold ${isTotal ? "text-blue-300" : "text-gray-200"}`}>{row.total != null ? fmtInt(row.total) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ChartCard>
      )}

      <ChartCard title="Upload Data COGS" subtitle="Kolom B = Nama Produk, Kolom C = COGS (IDR). Net Sales otomatis dari Oracle OE (etl_cogs). Referensi: cogs_data.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => cogsFileRef.current?.click()} disabled={cogsUploading} className={`${uploadBtnCls} bg-amber-600 hover:bg-amber-700`}>
              {cogsUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {cogsUploading ? "Mengupload..." : "Pilih File"}
            </button>
            <input ref={cogsFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleCogsUpload} />
          </div>
        }>
        <MsgBanner msg={cogsMsg} onClose={() => setCogsMsg(null)} />
      </ChartCard>

      <ChartCard title={`COGS Ratio by Product — ${selectedYear}`}
        right={
          <div className="flex items-center gap-3">
            <select value={selectedPeriod} onChange={(e) => setSelectedPeriod(Number(e.target.value))} className={selCls}>
              {MONTHS_SHORT.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select>
            <button onClick={loadCogs} className="text-cyan-400 hover:text-cyan-300"><RefreshCw size={13} /></button>
          </div>
        }>
        {cogsLoading ? <div className="py-8 text-center text-gray-600 text-sm">Memuat...</div> : cogs.length === 0 ? (
          <div className="py-8 text-center text-gray-600 text-sm">Belum ada data COGS. Upload file dan pastikan etl_cogs sudah dijalankan.</div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(200, cogs.length * 36)}>
              <BarChart data={cogs} layout="vertical" margin={{ left: 140, right: 70 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} tickFormatter={(v) => `${v}%`} domain={[0, "dataMax + 5"]} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="product_name" tick={{ fontSize: 11, fill: "#d1d5db" }} width={135} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => [`${fmtN(v)}%`, "COGS Ratio"]} contentStyle={TOOLTIP_STYLE} />
                <ReferenceLine x={70} stroke={COLOR_AMBER} strokeDasharray="5 5" label={{ value: "70%", fill: COLOR_AMBER, fontSize: 10 }} />
                <Bar dataKey="cogs_pct" name="COGS Ratio %" radius={[0, 4, 4, 0]} barSize={22}>
                  {cogs.map((entry, i) => <Cell key={i} fill={Number(entry.cogs_pct) > 100 ? COLOR_RED : Number(entry.cogs_pct) > 70 ? COLOR_AMBER : COLOR_PRIMARY} />)}
                  <LabelList dataKey="cogs_pct" position="right" formatter={(v) => `${fmtN(v, 1)}%`} style={{ fontSize: 11, fontWeight: 600, fill: "#9ca3af" }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-4 overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-gray-950 text-gray-200">
                    <th className="px-3 py-2 text-left font-semibold">Produk</th>
                    <th className="px-3 py-2 text-right font-semibold">Net Sales (IDR)</th>
                    <th className="px-3 py-2 text-right font-semibold">COGS (IDR)</th>
                    <th className="px-3 py-2 text-right font-semibold">COGS Ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {cogs.map((row, i) => (
                    <tr key={i} className={`border-b border-gray-800/60 ${i % 2 === 0 ? "bg-gray-900" : "bg-gray-900/60"}`}>
                      <td className="px-3 py-2 font-medium text-gray-300">{row.product_name}</td>
                      <td className="px-3 py-2 text-right font-mono text-gray-500">{row.net_sales == null ? "—" : `${(row.net_sales / 1e6).toFixed(2)} M`}</td>
                      <td className="px-3 py-2 text-right font-mono text-gray-500">{row.cogs == null ? "—" : `${(row.cogs / 1e6).toFixed(2)} M`}</td>
                      <td className={`px-3 py-2 text-right font-mono font-semibold ${Number(row.cogs_pct) > 100 ? "text-red-400" : Number(row.cogs_pct) > 70 ? "text-amber-400" : "text-emerald-400"}`}>{fmtN(row.cogs_pct)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </ChartCard>

      {otLoading ? <Loading /> : overtime.length === 0 ? (
        <ChartCard title="">
          <div className="text-center py-10 text-gray-600">
            <BarChart2 size={32} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Belum ada data overtime untuk tahun {selectedYear}.</p>
          </div>
        </ChartCard>
      ) : (
        <>
          <ChartCard title={`Plant Overtime Ratio — ${selectedYear}`} right={<button onClick={loadOvertime} className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"><RefreshCw size={12} /> Refresh</button>}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={overtime} margin={{ right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                <XAxis dataKey="period_name" tick={AXIS_TICK} tickFormatter={(v) => v?.slice(0, 3)} />
                <YAxis tick={AXIS_TICK} unit="%" domain={[0, "dataMax + 3"]} />
                <Tooltip formatter={(v) => [`${fmtN(v)}%`, "Overtime Ratio"]} contentStyle={TOOLTIP_STYLE} />
                <ReferenceLine y={15} stroke={COLOR_RED} strokeDasharray="5 5" label={{ value: "Target 15%", position: "insideTopRight", fontSize: 10, fill: COLOR_RED }} />
                <Bar dataKey="ratio_pct" name="Overtime %" radius={[4, 4, 0, 0]} barSize={30}>
                  {overtime.map((entry, i) => <Cell key={i} fill={Number(entry.ratio_pct) <= 15 ? COLOR_GREEN : Number(entry.ratio_pct) <= 20 ? COLOR_AMBER : COLOR_RED} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title={`Detail Data Overtime — ${selectedYear}`} className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-950 text-gray-200 text-xs">
                  <th className="px-4 py-2 text-left font-semibold">Bulan</th>
                  <th className="px-4 py-2 text-right font-semibold">Overtime Hours</th>
                  <th className="px-4 py-2 text-right font-semibold">Working Hours</th>
                  <th className="px-4 py-2 text-right font-semibold">Total Hours</th>
                  <th className="px-4 py-2 text-right font-semibold">Overtime Ratio</th>
                </tr>
              </thead>
              <tbody>
                {overtime.map((row, i) => {
                  const total = (row.overtime_hours || 0) + (row.working_hours || 0);
                  const isOver = Number(row.ratio_pct) > 15;
                  return (
                    <tr key={i} className={`border-b border-gray-800/60 ${i % 2 === 0 ? "bg-gray-900" : "bg-gray-900/60"}`}>
                      <td className="px-4 py-2 font-medium text-gray-300">{row.period_name}</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-400">{fmtN(row.overtime_hours)}</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-400">{fmtN(row.working_hours)}</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-500">{fmtN(total)}</td>
                      <td className={`px-4 py-2 text-right font-mono font-semibold ${isOver ? "text-red-400" : "text-emerald-400"}`}>
                        {fmtN(row.ratio_pct)}%{isOver && <span className="ml-1 text-[9px] font-normal bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">Over</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ChartCard>
        </>
      )}
    </div>
  );
}

/* ─── Tab: ETL Admin ────────────────────────────────────────────── */
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
    eisApi.getEtlJobData(jobName, p?.year || CY, p?.month || null)
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

function EisEtlAdminTab() {
  const [jobs, setJobs] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState("");
  const [stopping, setStopping] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [modal, setModal] = useState(null);
  const YEARS = Array.from({ length: 5 }, (_, i) => CY - i);

  const loadData = async () => {
    setLoading(true);
    try {
      const [jRes, sRes] = await Promise.all([eisApi.getEtlStatus(), eisApi.getEtlSchedule()]);
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
    try { await eisApi.triggerEtl(job, { year, month: month || null }); setTimeout(loadData, 2000); }
    catch (err) { alert("Gagal: " + (err?.response?.data?.detail || err?.detail || err.message)); }
    setTriggering("");
  };

  const handleStop = async (jobName, e) => {
    e.stopPropagation();
    if (!confirm(`Hentikan job "${jobName}" yang sedang berjalan?`)) return;
    setStopping(jobName);
    try { await eisApi.stopEtl(jobName); await loadData(); }
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

      <ChartCard title="ETL Schedule" right={<button onClick={loadData} className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"><RefreshCw size={13} /> Refresh</button>}>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {schedule.map((s) => (
            <div key={s.job} className="flex items-center justify-between bg-gray-800/50 rounded-lg p-3 border border-gray-800">
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-200">{s.job}</div>
                <div className="text-[10px] text-gray-500 mt-0.5"><Clock size={9} className="inline mr-1" />{s.frequency} — {s.schedule}</div>
                <div className="text-[9px] text-gray-600 mt-0.5">{s.source}</div>
              </div>
              <button onClick={() => setModal({ job: s.job, year: CY, month: "" })} disabled={triggering === s.job}
                className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 shrink-0 ml-2">
                {triggering === s.job ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />} Run
              </button>
            </div>
          ))}
        </div>
      </ChartCard>

      <ChartCard title="Recent Job History" subtitle="10 terakhir · klik baris untuk lihat data" className="overflow-x-auto">
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

/* ─── Main: EIS Dashboard ───────────────────────────────────────── */
const EIS_TABS = [
  { id: "summary", label: "Summary" },
  { id: "performance", label: "Performance" },
  { id: "production", label: "Production" },
  { id: "expansion", label: "Expansion" },
  { id: "administration", label: "Administration" },
  { id: "business-plan", label: "Business Plan" },
  { id: "daily-sales", label: "Daily Sales" },
  { id: "data-upload", label: "Data Upload" },
  { id: "etl", label: "ETL Admin" },
];

export default function EISDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const [year, setYear] = useState(CY);
  const [period, setPeriod] = useState(new Date().getMonth() || 12);
  const [segment, setSegment] = useState("all");
  const YEARS = Array.from({ length: 5 }, (_, i) => CY - i);

  // Derive active tab from URL — navigation now lives in the sidebar tree menu.
  const tab = EIS_TABS.find((t) => location.pathname.endsWith(t.id))?.id ?? "summary";

  useEffect(() => {
    if (location.pathname === "/dashboard/eis" || location.pathname === "/dashboard/eis/") {
      navigate("/dashboard/eis/summary", { replace: true });
    }
  }, []); // eslint-disable-line

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
          <Database size={20} className="text-cyan-400" /> EIS — Executive Information System
        </h1>
        <div className="flex items-center gap-2">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} className={selCls}>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={period} onChange={(e) => setPeriod(Number(e.target.value))} className={selCls}>
            {MONTHS_SHORT.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          {tab === "performance" && (
            <select value={segment} onChange={(e) => setSegment(e.target.value)} className={selCls}>
              <option value="all">All Segments</option>
              <option value="Local">Local</option>
              <option value="Export">Export</option>
              <option value="CMO">CMO</option>
            </select>
          )}
        </div>
      </div>

      {tab === "summary" && <EisSummaryTab year={year} period={period} />}
      {tab === "performance" && <EisPerformanceTab year={year} period={period} segment={segment} />}
      {tab === "production" && <EisProductionTab year={year} period={period} />}
      {tab === "expansion" && <EisExpansionTab year={year} period={period} />}
      {tab === "administration" && <EisAdministrationTab year={year} />}
      {tab === "business-plan" && <EisBusinessPlanTab year={year} />}
      {tab === "daily-sales" && <EisDailySalesTab year={year} />}
      {tab === "data-upload" && <EisDataUploadTab year={year} />}
      {tab === "etl" && <EisEtlAdminTab />}
    </div>
  );
}
