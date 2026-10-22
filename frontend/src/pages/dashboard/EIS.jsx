import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  BarChart2, TrendingUp, TrendingDown, Landmark, Wallet, Users, PieChart as PieIcon,
  Loader2, RefreshCw, Upload, FileSpreadsheet, Save, Plus, Trash2, Play, Square,
  ChevronDown, ChevronUp, Database, CheckCircle2, XCircle, Clock, X, Target, Package,
  DollarSign, Activity, PersonStanding,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, ComposedChart, PieChart, Pie, XAxis, YAxis, CartesianGrid,
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

const EXPECTATION_STATUS_CFG = {
  actual:          { valueColor: "text-gray-100",  badge: null },
  projected:       { valueColor: "text-purple-400", badge: "Projected" },
  carried_forward: { valueColor: "text-gray-400 italic", badge: "YTD to last month" },
  no_data:         { valueColor: "text-gray-700",  badge: null },
};

function DailySalesKpiColumn({ label, kpi }) {
  const achPct = kpi?.achievement_pct || 0;
  const achColor = achPct >= 100 ? "text-emerald-400" : achPct >= 80 ? "text-amber-400" : "text-red-400";
  const expCfg = EXPECTATION_STATUS_CFG[kpi?.expectation_status] || EXPECTATION_STATUS_CFG.actual;
  const rows = [
    { title: "Business Plan", value: `${fmtN(kpi?.business_plan, 2)} M`, icon: Target, color: "cyan", valueColor: "text-gray-100", badge: null },
    { title: "Expectation Closing", value: `${fmtN(kpi?.expectation_closing, 2)} M`, icon: TrendingUp, color: "amber", valueColor: expCfg.valueColor, badge: expCfg.badge },
    { title: "Achievement", value: `${fmtN(achPct, 2)}%`, icon: CheckCircle2, color: "emerald", valueColor: achColor, badge: null },
  ];
  const colorMap = {
    cyan: "border-cyan-500/30 bg-cyan-500/10 text-cyan-400",
    amber: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  };
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1">{label}</h3>
      {rows.map(({ title, value, icon: Icon, color, valueColor, badge }) => (
        <div key={title} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${colorMap[color]}`}><Icon size={17} /></div>
            <div>
              <div className="text-xs text-gray-500 font-medium flex items-center gap-1.5">
                {title}
                {badge && <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-400 normal-case">{badge}</span>}
              </div>
              <div className={`text-xl font-bold ${valueColor}`}>{value}</div>
            </div>
          </div>
        </div>
      ))}
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

/* ─── Required-columns table + upload history (Data Upload tab) ─────────── */

function RequiredColumnsTable({ columns }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 rounded-lg border border-gray-800 bg-gray-950/40">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-gray-300">
        <span className="flex items-center gap-1.5"><FileSpreadsheet size={12} /> Required columns ({columns.length})</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="border-t border-gray-800 overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="bg-gray-800/60 text-gray-500">
                <th className="px-2 py-1.5 text-left">Column</th>
                <th className="px-2 py-1.5 text-left">Name</th>
                <th className="px-2 py-1.5 text-left">Required</th>
                <th className="px-2 py-1.5 text-left">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {columns.map((c, i) => (
                <tr key={i}>
                  <td className="px-2 py-1.5 text-gray-500 font-mono whitespace-nowrap">{c.idx}</td>
                  <td className="px-2 py-1.5 text-gray-200 font-medium whitespace-nowrap">{c.name}</td>
                  <td className="px-2 py-1.5">
                    {c.required ? <span className="text-red-400 font-semibold">Yes</span> : <span className="text-gray-600">No</span>}
                  </td>
                  <td className="px-2 py-1.5 text-gray-500">{c.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Sales BP has no fixed column layout (it scans for a month-name header
 * row, then rows labeled by segment) — so it gets a format-description
 * panel instead of a fixed idx/name table. */
function RequiredFormatNote({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 rounded-lg border border-gray-800 bg-gray-950/40">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-gray-300">
        <span className="flex items-center gap-1.5"><FileSpreadsheet size={12} /> Required file format</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && <div className="border-t border-gray-800 px-3 py-2.5 text-[11px] text-gray-400 space-y-2">{children}</div>}
    </div>
  );
}

function fmtLogDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch (_) { return iso; }
}

function UploadHistoryTable({ uploadType, refreshKey }) {
  const [open, setOpen] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setLogs(await eisApi.getUploadLogs(uploadType, 10)); } catch (_) {} finally { setLoading(false); }
  };

  useEffect(() => { if (open) load(); }, [open, refreshKey]); // eslint-disable-line

  return (
    <div className="mt-2 rounded-lg border border-gray-800 bg-gray-950/40">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-gray-300">
        <span className="flex items-center gap-1.5"><Clock size={12} /> Upload History</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="border-t border-gray-800 overflow-x-auto">
          {loading ? (
            <div className="py-4 text-center text-xs text-gray-600"><Loader2 size={13} className="animate-spin inline" /></div>
          ) : logs.length === 0 ? (
            <div className="py-4 text-center text-xs text-gray-600">No upload history yet.</div>
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-gray-800/60 text-gray-500">
                  <th className="px-2 py-1.5 text-left">Time</th>
                  <th className="px-2 py-1.5 text-left">File</th>
                  <th className="px-2 py-1.5 text-left">Year</th>
                  <th className="px-2 py-1.5 text-left">Rows</th>
                  <th className="px-2 py-1.5 text-left">Status</th>
                  <th className="px-2 py-1.5 text-left">By</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td className="px-2 py-1.5 text-gray-400 whitespace-nowrap">{fmtLogDate(l.uploaded_at)}</td>
                    <td className="px-2 py-1.5 text-gray-300 max-w-[160px] truncate" title={l.filename}>{l.filename || "—"}</td>
                    <td className="px-2 py-1.5 text-gray-400">{l.fiscal_year ?? "—"}</td>
                    <td className="px-2 py-1.5 text-gray-400">{l.rows_loaded ?? "—"}</td>
                    <td className="px-2 py-1.5">
                      {l.status === "success"
                        ? <span className="text-emerald-400 font-semibold">Success</span>
                        : <span className="text-red-400 font-semibold" title={l.error_message}>Failed</span>}
                    </td>
                    <td className="px-2 py-1.5 text-gray-500">{l.uploaded_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

const OVERTIME_COLUMNS = [
  { idx: "B", name: "Row label", required: true, note: 'One row with the text "Overtime Hour", another with "Working Hour" (searched within rows 1–10)' },
  { idx: "C–N", name: "Jan–Dec", required: true, note: "12 monthly hour values for each label row" },
];

const COGS_COLUMNS = [
  { idx: "B", name: "No", required: true, note: "Sequence number, must be numeric — rows without a number in this column are skipped" },
  { idx: "C", name: "Market", required: false, note: 'Public/Private/CMO/Export/Service Agreement/Accounting — defaults to "Public" when empty' },
  { idx: "E", name: "Products", required: true, note: 'Short product name, e.g. "Carboplatin 150 mg" — the strength suffix is removed automatically to group by product' },
  { idx: "I", name: "Price IDR", required: false, note: "Unit price (rupiah) — used to calculate Net Sales" },
  { idx: "J–U", name: "COGS Quantity Jan–Dec", required: true, note: "12 monthly quantity columns" },
  { idx: "W–AH", name: "COGS Amount Jan–Dec", required: true, note: "12 monthly COGS value columns, in MILLION IDR" },
];

/* ─── Tab: Summary ────────────────────────────────────────────────
   After the template's Summary sheet. Same numbers as the Performance /
   Production / Administration pages (the backend's /summary/dashboard
   calls their own functions), plus Product Portfolio (Sales_Ledger +
   Oracle OPM cost split) and Sales Closing Estimation for the month being
   closed (the one after the selected month). */
const fmtOrDash = (v) => (v == null ? "—" : fmtInt(v));
const pctOrDash = (v) => (v == null ? "—" : `${fmtN(v, 0)}%`);
const BUSINESS_LINES = ["Local", "CMO & Others", "Export"];

function ClosingEstBox({ title, seg, planLabel, estLabel }) {
  const s = seg || {};
  const pctCls = s.pct == null ? "text-gray-500" : s.pct >= 80 ? "text-emerald-600" : s.pct >= 60 ? "text-amber-600" : "text-red-600";
  return (
    <div className="shrink-0 border border-gray-800 rounded-lg overflow-hidden text-xs min-w-[190px]">
      <div className="text-center font-bold text-gray-200 py-1.5 border-b border-gray-800">{title}</div>
      <div className="grid grid-cols-3 text-center text-gray-500 font-semibold border-b border-gray-800">
        <span className="py-1">{planLabel}</span><span className="py-1 border-x border-gray-800">{estLabel}</span><span className="py-1">%</span>
      </div>
      <div className="grid grid-cols-3 text-right font-mono text-gray-100">
        <span className="px-2 py-2">{fmtOrDash(s.plan)}</span>
        <span className="px-2 py-2 border-x border-gray-800">{fmtOrDash(s.est)}</span>
        <span className={`px-2 py-2 font-semibold ${pctCls}`}>{pctOrDash(s.pct)}</span>
      </div>
    </div>
  );
}

function ClosingEstArrow() {
  return (
    <div className="shrink-0 w-9 flex items-center justify-center self-center">
      <div className="w-7 h-7" style={{ background: XL_BLUE, clipPath: "polygon(0% 0%, 55% 0%, 100% 50%, 55% 100%, 0% 100%, 45% 50%)" }} />
    </div>
  );
}

/** One header+values strip of the portfolio table (div grid — the app's
 * global table CSS would restyle a real <table>). */
function PortfolioStrip({ cols }) {
  return (
    <div className="overflow-x-auto">
      <div className="grid min-w-[880px] text-xs border border-gray-800 rounded-lg overflow-hidden"
        style={{ gridTemplateColumns: cols.map((c) => c.w || "1fr").join(" ") }}>
        {cols.map((c, i) => <div key={`h${i}`} className="bg-amber-100 text-gray-200 font-bold text-center px-1 py-1 border-b border-gray-800">{c.h}</div>)}
        {cols.map((c, i) => <div key={`v${i}`} className={`px-2 py-1.5 text-gray-300 ${c.num ? "text-right font-mono" : "text-center"}`}>{c.v}</div>)}
      </div>
    </div>
  );
}

function ProductPortfolio({ year, period, initial }) {
  const [p, setP] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setP(initial); }, [initial]);

  if (!p) return <div className="py-8 text-center text-xs text-gray-600">No Sales_Ledger data yet. Upload the EIS Template workbook in EIS → Data Upload.</div>;
  const sel = p.selected;
  const markets = p.markets.filter((m) => m.business === sel.business);
  const products = (p.markets.find((m) => m.market === sel.market) || { products: [] }).products;

  const choose = async (market, product) => {
    setBusy(true);
    try { setP(await eisApi.getSummaryPortfolio(year, period, market, product)); } catch (e) { console.error(e); }
    setBusy(false);
  };
  const onBusiness = (b) => { const m = p.markets.find((x) => x.business === b); if (m) choose(m.market, null); };

  const c = p.cost;
  const costCell = (k) => (c && !c.error ? c[k] : null);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select value={sel.business} onChange={(e) => onBusiness(e.target.value)} className={selCls}>
          {BUSINESS_LINES.filter((b) => p.markets.some((m) => m.business === b)).map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select value={sel.market} onChange={(e) => choose(e.target.value, null)} className={selCls}>
          {markets.map((m) => <option key={m.market} value={m.market}>{m.market}</option>)}
        </select>
        <select value={sel.product} onChange={(e) => choose(sel.market, e.target.value)} className={selCls}>
          {products.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        {busy && <Loader2 size={13} className="animate-spin text-gray-500" />}
        <span className="ml-auto text-[10px] text-amber-600">Sales_Ledger as of {MONTHS_SHORT[p.as_of.month - 1]} {p.as_of.year}</span>
      </div>
      <PortfolioStrip cols={[
        { h: "Business", v: sel.business }, { h: "Market", v: sel.market }, { h: "Product", v: sel.product, w: "1.6fr" },
        { h: "Sales", v: fmtOrDash(sel.sales), num: true }, { h: "COGS", v: fmtOrDash(sel.cogs), num: true }, { h: "%", v: pctOrDash(sel.cogs_pct), num: true, w: ".6fr" },
        { h: "Gross Profit", v: fmtOrDash(sel.gross_profit), num: true }, { h: "%", v: pctOrDash(sel.gp_pct), num: true, w: ".6fr" },
        { h: "OPEX", v: fmtOrDash(sel.opex), num: true }, { h: "%", v: pctOrDash(sel.opex_pct), num: true, w: ".6fr" },
        { h: "EBIT", v: fmtOrDash(sel.ebit), num: true }, { h: "%", v: pctOrDash(sel.ebit_pct), num: true, w: ".6fr" },
      ]} />
      <PortfolioStrip cols={[
        { h: "COGS", v: `${sel.business} · ${sel.market} · ${sel.product}`, w: "3.6fr" },
        { h: "Price", v: fmtOrDash(sel.cogs), num: true },
        { h: "Material", v: fmtOrDash(costCell("material")?.amount), num: true }, { h: "%", v: pctOrDash(costCell("material")?.pct), num: true, w: ".6fr" },
        { h: "Labour", v: fmtOrDash(costCell("labour")?.amount), num: true }, { h: "%", v: pctOrDash(costCell("labour")?.pct), num: true, w: ".6fr" },
        { h: "Depreciation", v: fmtOrDash(costCell("depreciation")?.amount), num: true }, { h: "%", v: pctOrDash(costCell("depreciation")?.pct), num: true, w: ".6fr" },
        { h: "FOH", v: fmtOrDash(costCell("foh")?.amount), num: true }, { h: "%", v: pctOrDash(costCell("foh")?.pct), num: true, w: ".6fr" },
      ]} />
      <div className="text-[10px] text-gray-600">
        Values follow the Sales_Ledger scale. COGS split = Oracle OPM cost component ratio
        {c && !c.error ? ` (${c.item_code} ${c.item_desc}, ${c.period})` : ""}
        {c && !c.error && !c.detailed ? " — this period's costing does not split Labour/Depreciation yet; both are still inside FOH (GL Allocation)." : "."}
        {!c && " — item not found in Oracle costing for this period."}
        {c?.error && ` — Oracle could not be read: ${c.error}`}
      </div>
    </div>
  );
}

function EisSummaryTab({ year, period }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    eisApi.getSummaryDashboard(year, period)
      .then((r) => { if (!cancelled) setD(r); })
      .catch((e) => { console.error("Failed to load EIS summary:", e); if (!cancelled) setD(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [year, period]);

  if (loading) return <Loading />;
  if (!d) return <ChartCard title=""><div className="py-12 text-center text-sm text-gray-500">Failed to load the Summary.</div></ChartCard>;

  const cl = d.closing, n = d.nwc;
  const closeLabel = `${MONTH_NAMES[cl.month - 1]} ${cl.year}`;
  const estNote = cl.daily_sales
    ? `Local = Daily Sales projection (${cl.daily_sales.wd_actual}/${cl.daily_sales.wd_total} WD)`
    : "Local = no Daily Sales this month yet";

  return (
    <div className="space-y-4">
      <SourceTag>Performance · Production · Administration · Daily Sales · Oracle OPM</SourceTag>
      <EisHeaderBand title="Summary" year={year} period={period} />

      <EisSection title="Product Portfolio">
        <ProductPortfolio year={year} period={period} initial={d.portfolio} />
      </EisSection>

      <EisSection title="Sales Closing Estimation" subtitle={`Closing ${closeLabel}`}>
        <div className="flex items-stretch gap-3 overflow-x-auto py-1">
          <ClosingEstBox title="Sales" seg={cl.sales} planLabel="Business Plan" estLabel="Estimation" />
          <ClosingEstArrow />
          <ClosingEstBox title="Local" seg={cl.local} planLabel="Plan" estLabel="Est." />
          <ClosingEstBox title="CMO & Other" seg={cl.cmo_other} planLabel="Plan" estLabel="Est." />
          <ClosingEstBox title="Export" seg={cl.export} planLabel="Plan" estLabel="Est." />
        </div>
        <div className="text-[10px] text-gray-600 mt-1">
          Plan: SalesSummary_Monthly{["local", "cmo_other", "export"].some((s) => cl[s].plan == null) ? ` (no plan for ${closeLabel} in SalesSummary_Monthly yet — upload it under EIS → Data Upload)` : ""} · {estNote} · CMO &amp; Export = that month's actual once available · million IDR
        </div>
      </EisSection>

      <EisSection title="Net Working Capital">
        {n.error ? <div className="py-6 text-center text-xs text-red-600">Oracle data could not be read: {n.error}</div> : (
          <div className="flex items-stretch gap-3 overflow-x-auto">
            <div className="shrink-0 min-w-[180px] border border-gray-800 rounded-lg text-center">
              <div className="text-xs font-bold text-gray-200 py-1 border-b border-gray-800">NWC (Days)</div>
              <div className="text-3xl font-extrabold text-gray-100 py-3">{n.nwc_days == null ? "—" : fmtN(n.nwc_days, 0)}</div>
            </div>
            <ClosingEstArrow />
            <div className="flex-1 grid grid-cols-3 border border-gray-800 rounded-lg divide-x divide-gray-800 min-w-[420px]">
              {[["DSO", n.dso_days, n.dso_months], ["DIO", n.dio_days, n.dio_months], ["DPO", n.dpo_days, n.dpo_months]].map(([lbl, v, mo]) => (
                <div key={lbl} className="text-center">
                  <div className="text-xs font-bold text-gray-200 py-1 border-b border-gray-800">{lbl}</div>
                  <div className="text-3xl font-extrabold text-gray-100 py-3">{v == null ? "—" : fmtN(v, 0)}</div>
                  <div className="text-[11px] italic text-blue-700 pb-1">Month {mo == null ? "—" : fmtN(mo, 0)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="text-[10px] text-gray-600 mt-1">
          NWC = DSO + DIO − DPO · DSO = Average AR ÷ Sales × 365, DPO = Average AP ÷ COGS × 365
          {" "}({[["DSO", n.dso_source, n.dso_month], ["DPO", n.dpo_source, n.dpo_month]].map(([k, src, mo]) =>
            `${k}: ${src === "template" ? "Administration_Ratios" : src === "oracle" ? "Oracle GL (not in Administration_Ratios)" : "no data"}${src && mo && mo !== period ? ` as of ${MONTHS_SHORT[mo - 1]}` : ""}`).join(" · ")})
          {" "}· DIO from Production{n.dio_month && n.dio_month !== period ? ` (as of ${MONTHS_SHORT[n.dio_month - 1]})` : ""}
        </div>
      </EisSection>
    </div>
  );
}

/* ─── EIS template pages (Performance, Production) — shared ───────
   Both pages are laid out after the EIS template's own dashboard sheets
   and read the tables filled by the EIS Template upload (eis.perf_*,
   eis.prod_*), one call per page; every formula lives in the backend
   (eis_performance.py / eis_production.py /dashboard). Series colors
   follow the sheets: blue = business plan / main series, orange = actual.

   The app's theme is light (index.css "FLAT WHITE") and forces
   .text-white to near-black, so the navy bands use text-blue-50 to stay
   light, and chart labels/grid use explicit dark-on-white colors rather
   than GRID_STROKE / AXIS_TICK, which were tuned for the old dark theme. */
const XL_BLUE = "#4472C4";
const XL_ORANGE = "#ED7D31";
const XL_GRAY = "#A5A5A5";
const TPL_GRID = "#e5e7eb";
const TPL_TICK = { fontSize: 11, fill: "#64748b" };
const TPL_LABEL = { fontSize: 9, fill: "#334155", fontWeight: 600 };
const MONTH_NAMES = MONTHS_FULL_ID.map((m) => m.label);

/** Title block of the sheet: company · page name · year / month. */
function EisHeaderBand({ title, year, period }) {
  return (
    <div className="grid grid-cols-[2fr_1.4fr_1fr] rounded-xl overflow-hidden border border-blue-900 bg-blue-950 text-blue-50">
      <div className="px-4 py-2 text-xs sm:text-sm font-bold leading-snug flex items-center justify-center text-center">
        PT CKD OTTO PHARMACEUTICALS<br />EXECUTIVE INFORMATION SUMMARY
      </div>
      <div className="border-x border-blue-900 flex items-center justify-center text-sm sm:text-base font-bold tracking-wide">{title}</div>
      <div className="grid grid-rows-2 text-center text-sm font-bold">
        <div className="flex items-center justify-center border-b border-blue-900">{year}</div>
        <div className="flex items-center justify-center">{MONTH_NAMES[period - 1]}</div>
      </div>
    </div>
  );
}

function EisSection({ title, subtitle, className = "", children }) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl overflow-hidden flex flex-col ${className}`}>
      <div className="bg-blue-950 border-b border-blue-900 px-3 py-1.5 text-center text-sm font-bold text-blue-50">{title}</div>
      {subtitle && <div className="border-b border-gray-800 px-3 py-1 text-center text-xs font-bold text-gray-200">{subtitle}</div>}
      <div className="p-3 flex-1">{children}</div>
    </div>
  );
}

/** "as of Jul 2026" when a block shows a different month than the one selected. */
function AsOf({ year, month, selYear, selMonth }) {
  if (!month || (year === selYear && month === selMonth)) return null;
  return <div className="text-[10px] text-amber-600 text-center mt-1">as of {MONTHS_SHORT[month - 1]} {year}</div>;
}

function BigNumber({ value, unit }) {
  return (
    <div className="text-center">
      <div className="text-4xl font-extrabold text-gray-100 leading-tight">{value}</div>
      {unit && <div className="text-[11px] text-gray-500">{unit}</div>}
    </div>
  );
}

/** Half-donut like the sheet's gauges: blue = achieved, orange = remainder
 * (capped at 100% visually; the label shows the real value). */
function HalfGauge({ pct, height = 130, digits = 0 }) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={[{ v }, { v: 100 - v }]} dataKey="v" startAngle={180} endAngle={0}
            cx="50%" cy="85%" innerRadius="60%" outerRadius="100%" stroke="none" isAnimationActive={false}>
            <Cell fill={XL_BLUE} /><Cell fill={XL_ORANGE} />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-x-0 bottom-2 text-center text-lg font-extrabold text-gray-100">
        {pct == null ? "—" : `${fmtN(pct, digits)}%`}
      </div>
    </div>
  );
}

function BlockTitle({ children, right }) {
  return (
    <div className="flex items-center justify-center gap-3 text-sm font-bold text-gray-200 mb-1">
      <span>{children}</span>{right}
    </div>
  );
}

function PctTag({ pct, amount }) {
  if (pct == null) return null;
  const sign = (v) => (v > 0 ? "+" : "");
  return (
    <span className={pct < 0 ? "text-red-600" : "text-emerald-600"}>
      {sign(pct)}{fmtN(pct, 0)}%
      {amount != null && <span className="font-semibold"> ({sign(amount)}{fmtInt(amount)})</span>}
    </span>
  );
}

/* ─── Tab: Performance ──────────────────────────────────────────── */
const EBIT_MARKETS = [
  ["Public", "Local Public"], ["Private", "Local Private"], ["CMO", "CMO"],
  ["Export", "Export"], ["Service Agreement", "Service Agreement"],
];

/** Business plan (bars) vs actual (line, labeled) per month. */
function MonthlyPlanActual({ seg, height = 230 }) {
  const data = seg.monthly.map((r) => ({ ...r, name: MONTHS_SHORT[r.month - 1] }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 18, right: 16, left: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
        <XAxis dataKey="name" tick={TPL_TICK} />
        <YAxis tick={TPL_TICK} tickFormatter={fmtInt} width={56} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => fmtInt(v)} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="plan" name="Business Plan" fill={XL_BLUE} />
        <Line type="linear" dataKey="actual" name="Actual" stroke={XL_ORANGE} strokeWidth={2} dot={{ r: 3, fill: XL_ORANGE }}>
          <LabelList dataKey="actual" position="top" formatter={(v) => v == null ? "" : fmtInt(v)} style={TPL_LABEL} />
        </Line>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Previous-year vs this-year YTD actual, same months. */
function GrowthBars({ seg, year, period, height = 180 }) {
  const data = [
    { name: String(year - 1), value: seg.prev_ytd_actual },
    { name: String(year), value: seg.ytd_actual },
  ];
  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 18, right: 16, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
          <XAxis dataKey="name" tick={TPL_TICK} />
          <YAxis tick={TPL_TICK} tickFormatter={fmtInt} width={56} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmtInt(v), "Actual"]} />
          <Bar dataKey="value" name="Actual" fill={XL_ORANGE} barSize={36}>
            <LabelList dataKey="value" position="top" formatter={(v) => v == null ? "" : fmtInt(v)} style={TPL_LABEL} />
          </Bar>
          <Line type="linear" dataKey="value" stroke={XL_ORANGE} strokeDasharray="3 3" dot={false} legendType="none" tooltipType="none" />
        </ComposedChart>
      </ResponsiveContainer>
      {seg.prev_ytd_actual == null ? (
        <div className="text-[10px] text-amber-600 text-center">No {year - 1} data (Jan–{MONTHS_SHORT[period - 1]}) in {seg.source === "sales_ledger" ? "Sales_Ledger" : "SalesSummary_Monthly"} yet</div>
      ) : (
        <div className="text-[11px] text-center text-gray-400">
          Growth {year - 1} → {year} (Jan–{MONTHS_SHORT[period - 1]}): <PctTag pct={seg.growth_pct} amount={seg.growth_amount} />
        </div>
      )}
    </>
  );
}

/** Company figures come straight from Sales_Ledger (no rescaling or
 * filling) — say so when the ledger is thin or mixes scales. */
function LedgerCheckNote({ seg, period, markets }) {
  const c = seg?.ledger_check;
  if (!c) return null;
  const mon = (ms) => ms.map((m) => MONTHS_SHORT[m - 1]).join(", ");
  const issues = [];
  if (c.months_without_actual.length) issues.push(`no Actual for ${mon(c.months_without_actual)}`);
  if (!c.months_with_plan.length) issues.push(`no Business Plan for Jan–${MONTHS_SHORT[period - 1]}`);
  else if (c.months_with_plan.length < period) issues.push(`Business Plan only in ${mon(c.months_with_plan)}`);
  if (c.scale_ratio && c.scale_ratio > 100) issues.push(`the largest month is ${fmtInt(c.scale_ratio)}× the smallest — the months look to be on different scales`);
  if (c.unmapped_markets?.length) issues.push(`market ${c.unmapped_markets.join(", ")} is not in lookup EIS_MARKET_BUSINESS_TYPE (classified by name for now)`);
  return (
    <div className={`mb-2 text-[11px] rounded-lg px-3 py-1.5 border ${issues.length ? "text-amber-700 bg-amber-500/10 border-amber-500/30" : "text-gray-500 border-gray-800"}`}>
      Source: Sales_Ledger{markets ? ` (${markets})` : ""} — scenario Business Plan / Actual, sum of sales_amount per month.
      {issues.length > 0 && <> Check the uploaded ledger: {issues.join("; ")}.</>}
    </div>
  );
}

function YearlyGrowthColumn({ seg, year, period }) {
  return (
    <div className="space-y-3">
      <div>
        <BlockTitle>Yearly</BlockTitle>
        <HalfGauge pct={seg.achievement_pct} height={180} />
      </div>
      <div>
        <BlockTitle right={<PctTag pct={seg.growth_pct} amount={seg.growth_amount} />}>Growth</BlockTitle>
        <GrowthBars seg={seg} year={year} period={period} />
      </div>
    </div>
  );
}

function AreaSalesBlock({ area }) {
  if (!area) return <div className="py-8 text-center text-xs text-gray-600">No area sales data yet.</div>;
  return (
    <div className="text-xs">
      <div className="grid grid-cols-2 border border-gray-800 rounded-lg overflow-hidden mb-2">
        {area.groups.map((g, i) => (
          <div key={g.name} className={i ? "border-l border-gray-800" : ""}>
            <div className="text-center font-bold text-gray-200 py-1 border-b border-gray-800">{g.name}</div>
            <div className="grid grid-cols-2 text-center py-1.5">
              <span className="font-semibold text-gray-200">{fmtInt(g.amount)}</span>
              <span className="text-gray-400">{g.portion_pct == null ? "—" : `${fmtN(g.portion_pct, 0)}%`}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="border border-gray-800 rounded-lg overflow-hidden">
        <div className="grid grid-cols-3 font-bold text-gray-300 border-b border-gray-800 px-2 py-1">
          <span>Area</span><span className="text-right">Amount</span><span className="text-right">Portion</span>
        </div>
        {area.regions.map((r) => (
          <div key={r.region} className="grid grid-cols-3 px-2 py-0.5 text-gray-300">
            <span>{r.region}</span><span className="text-right font-mono">{fmtInt(r.amount)}</span>
            <span className="text-right font-mono">{r.portion_pct == null ? "—" : `${fmtN(r.portion_pct, 0)}%`}</span>
          </div>
        ))}
        <div className="grid grid-cols-3 px-2 py-1 border-t border-gray-800 font-bold text-gray-200">
          <span>Total</span><span className="text-right font-mono">{fmtInt(area.total)}</span><span className="text-right font-mono">100%</span>
        </div>
      </div>
    </div>
  );
}

function MarketingBlock({ marketing, year, period }) {
  if (!marketing.length) return <div className="py-8 text-center text-xs text-gray-600">No marketing activity data yet.</div>;
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${marketing.length}, minmax(0, 1fr))` }}>
      {marketing.map((e) => (
        <div key={e.event} className="border border-gray-800 rounded-lg overflow-hidden">
          <div className="text-center text-xs font-bold text-gray-200 py-1 border-b border-gray-800">{e.event}</div>
          <div className="grid grid-cols-2 divide-x divide-gray-800 text-center">
            <div className="py-2">
              <div className="text-[11px] font-semibold text-gray-400">Business Plan</div>
              <div className="text-3xl font-extrabold text-gray-100">{e.plan == null ? "—" : fmtInt(e.plan)}</div>
            </div>
            <div className="py-2">
              <div className="text-[11px] font-semibold text-gray-400">Actual</div>
              <div className="text-3xl font-extrabold text-gray-100">{e.actual == null ? "—" : fmtInt(e.actual)}</div>
              <div className="text-sm font-bold text-gray-300">{e.achievement_pct == null ? "" : `${fmtN(e.achievement_pct, 0)}%`}</div>
            </div>
          </div>
          <AsOf year={year} month={e.month} selYear={year} selMonth={period} />
        </div>
      ))}
    </div>
  );
}

function EisPerformanceTab({ year, period }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ebitMarket, setEbitMarket] = useState("Public");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    eisApi.getPerformanceDashboard(year, period, ebitMarket)
      .then((r) => { if (!cancelled) setD(r); })
      .catch((e) => { console.error("Failed to load EIS performance:", e); if (!cancelled) setD(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [year, period, ebitMarket]);

  // Only the first load blanks the page; switching the EBIT market keeps
  // the rest on screen while it refetches.
  if (loading && !d) return <Loading />;
  if (!d?.has_data) {
    return (
      <ChartCard title="">
        <div className="text-center py-12 text-gray-500">
          <BarChart2 size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No Performance data for {MONTH_NAMES[period - 1]} {year} yet.</p>
          <p className="text-xs text-gray-600 mt-1">Upload the EIS Template workbook in EIS → Data Upload → "EIS Template".</p>
        </div>
      </ChartCard>
    );
  }

  const s = d.segments;
  const ebitItems = d.ebit?.items || [];

  return (
    <div className="space-y-4">
      <SourceTag>EIS Template (upload Excel)</SourceTag>
      <EisHeaderBand title="PERFORMANCE" year={year} period={period} />

      <EisSection title="Company Sales Performance" subtitle="Achievement">
        <LedgerCheckNote seg={s.Company} period={period} />
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
          <YearlyGrowthColumn seg={s.Company} year={year} period={period} />
          <div className="space-y-3">
            <div>
              <BlockTitle>Monthly</BlockTitle>
              <MonthlyPlanActual seg={s.Company} />
            </div>
            <div className="border-t border-gray-800 pt-2">
              <div className="flex items-center justify-between gap-2 mb-1">
                <select value={ebitMarket} onChange={(e) => setEbitMarket(e.target.value)} className={selCls}>
                  {EBIT_MARKETS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                </select>
                {loading && <Loader2 size={13} className="animate-spin text-gray-500" />}
              </div>
              <BlockTitle>EBIT - Product</BlockTitle>
              {ebitItems.length === 0 ? <div className="py-8 text-center text-xs text-gray-600">No product with a positive EBIT in this market.</div> : (
                <ResponsiveContainer width="100%" height={ebitItems.length * 30 + 40}>
                  <BarChart data={ebitItems} layout="vertical" margin={{ left: 8, right: 44, top: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} horizontal={false} />
                    <XAxis type="number" tick={TPL_TICK} tickFormatter={(v) => `${v}%`} />
                    <YAxis type="category" dataKey="product" tick={{ fontSize: 10, fill: "#334155" }} width={130} interval={0} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${fmtN(v, 1)}%`, "EBIT"]} />
                    <Bar dataKey="ebit_pct" name="EBIT" fill={XL_BLUE} barSize={12}>
                      <LabelList dataKey="ebit_pct" position="right" formatter={(v) => `${fmtN(v, 0)}%`} style={{ ...TPL_LABEL, fontSize: 10 }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
              {d.ebit && <AsOf year={d.ebit.year} month={d.ebit.month} selYear={year} selMonth={period} />}
              <div className="text-[10px] text-gray-600 text-center mt-0.5">Top 5 products by sales with a positive EBIT · EBIT ÷ sales</div>
            </div>
          </div>
        </div>
      </EisSection>

      <EisSection title="Local Performance" subtitle="Achievement">
        <LedgerCheckNote seg={s.Local} period={period} markets="markets with business type Local in lookup EIS_MARKET_BUSINESS_TYPE" />
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
          <YearlyGrowthColumn seg={s.Local} year={year} period={period} />
          <div className="space-y-3">
            <div>
              <BlockTitle>Monthly</BlockTitle>
              <MonthlyPlanActual seg={s.Local} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-gray-800 pt-2">
              <div>
                <BlockTitle>Area Sales Force Performance</BlockTitle>
                <AreaSalesBlock area={d.area} />
              </div>
              <div>
                <BlockTitle>Marketing Activity</BlockTitle>
                <MarketingBlock marketing={d.marketing} year={year} period={period} />
              </div>
            </div>
          </div>
        </div>
      </EisSection>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {[["CMO & Others Performance", s["CMO & Others"], "markets with business type CMO & Others in lookup EIS_MARKET_BUSINESS_TYPE"],
          ["Export Performance", s.Export, "markets with business type Export in lookup EIS_MARKET_BUSINESS_TYPE"]].map(([title, seg, markets]) => (
          <EisSection key={title} title={title}>
            <LedgerCheckNote seg={seg} period={period} markets={markets} />
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_1.4fr] gap-3">
              <div>
                <BlockTitle>Yearly</BlockTitle>
                <HalfGauge pct={seg.achievement_pct} />
              </div>
              <div>
                <BlockTitle right={<PctTag pct={seg.growth_pct} amount={seg.growth_amount} />}>GROWTH</BlockTitle>
                <GrowthBars seg={seg} year={year} period={period} height={150} />
              </div>
            </div>
            <div className="mt-3">
              <BlockTitle>Monthly</BlockTitle>
              <MonthlyPlanActual seg={seg} />
            </div>
          </EisSection>
        ))}
      </div>
    </div>
  );
}

/* ─── Tab: Production ─────────────────────────────────────────────
   Laid out after the template's Production_Dashboard sheet (Executive
   Information Summary): Batch & Yield, DIO, Quality Release, COGS
   Performance (GPM), Overtime Ratio (Machine Utilization removed
   2026-10-22 — no longer used). Data comes
   from the EIS template upload (eis.prod_*), one call for the whole page;
   every formula lives in the backend (eis_production.py /dashboard).
   Shared pieces (header band, sections, gauge) are defined above the
   Performance tab. */
function EisProductionTab({ year, period }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    eisApi.getProductionDashboard(year, period)
      .then((r) => { if (!cancelled) setD(r); })
      .catch((e) => { console.error("Failed to load EIS production:", e); if (!cancelled) setD(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [year, period]);

  if (loading) return <Loading />;
  if (!d?.has_data) {
    return (
      <ChartCard title="">
        <div className="text-center py-12 text-gray-500">
          <BarChart2 size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No Production data for {MONTH_NAMES[period - 1]} {year} yet.</p>
          <p className="text-xs text-gray-600 mt-1">Upload the EIS Template workbook in EIS → Data Upload → "EIS Template — Production".</p>
        </div>
      </ChartCard>
    );
  }

  const label = (m) => MONTHS_SHORT[m - 1];
  const batch = d.batch.map((r) => ({ ...r, name: label(r.month) }));
  const yieldRows = d.yield.monthly.map((r) => ({ ...r, name: label(r.month) }));
  const overtime = d.overtime.map((r) => ({ ...r, name: label(r.month) }));
  const yieldVals = yieldRows.map((r) => r.yield_pct).filter((v) => v != null);
  const yieldDomain = yieldVals.length
    ? [Math.floor(Math.min(...yieldVals) - 3), Math.min(100, Math.ceil(Math.max(...yieldVals) + 2))]
    : [80, 100];
  const sel = { selYear: year, selMonth: period };
  const gpm = d.gpm?.items || [];

  return (
    <div className="space-y-4">
      <SourceTag>EIS Template (upload Excel)</SourceTag>

      <EisHeaderBand title="PRODUCTION" year={year} period={period} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <EisSection title="Batch & Yield Production">
          <div className="text-center text-xs font-semibold text-gray-300 mb-1">Batch Production - Vials : Accumulated</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={batch} margin={{ top: 18, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
              <XAxis dataKey="name" tick={TPL_TICK} />
              <YAxis tick={TPL_TICK} tickFormatter={fmtInt} width={64} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => fmtInt(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="plan_cum" name="Business Plan" fill={XL_BLUE}>
                <LabelList dataKey="plan_cum" position="top" formatter={fmtInt} style={TPL_LABEL} />
              </Bar>
              <Bar dataKey="actual_cum" name="Actual" fill={XL_ORANGE}>
                <LabelList dataKey="actual_cum" position="top" formatter={fmtInt} style={TPL_LABEL} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-3 mt-3">
            <div className="rounded-lg border border-gray-800 flex flex-col">
              <div className="text-center text-xs font-semibold text-gray-300 pt-2">Yield</div>
              <HalfGauge pct={d.yield.current?.yield_pct} digits={1} />
              <AsOf year={year} month={d.yield.current?.month} {...sel} />
              <div className="border-t border-gray-800 mt-2 py-2 text-center">
                <div className="text-sm font-bold text-gray-200">Target Yield</div>
                <div className="text-xl font-extrabold text-gray-100">{fmtN(d.yield.target_pct, 1)}%</div>
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 p-2">
              <div className="text-center text-xs font-semibold text-gray-300 mb-1">Monthly Yield</div>
              <ResponsiveContainer width="100%" height={210}>
                <LineChart data={yieldRows} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
                  <XAxis dataKey="name" tick={TPL_TICK} />
                  <YAxis tick={TPL_TICK} domain={yieldDomain} tickFormatter={(v) => `${v}%`} width={44} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${fmtN(v, 1)}%`, "Yield"]} />
                  <ReferenceLine y={d.yield.target_pct} stroke={COLOR_RED} strokeDasharray="5 5" />
                  <Line type="linear" dataKey="yield_pct" name="Yield" stroke={XL_GRAY} strokeWidth={2} dot={{ r: 3, fill: XL_GRAY }} connectNulls={false}>
                    <LabelList dataKey="yield_pct" position="top" formatter={(v) => v == null ? "" : `${fmtN(v, 1)}%`} style={TPL_LABEL} />
                  </Line>
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </EisSection>

        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <EisSection title="DIO">
              <div className="text-center text-[11px] text-gray-500 mb-1">Days</div>
              <BigNumber value={d.dio?.days == null ? "—" : fmtN(d.dio.days, 0)} />
              <AsOf year={year} month={d.dio?.month} {...sel} />
            </EisSection>
            <EisSection title="Quality Release">
              <div className="text-center text-[11px] text-gray-500 mb-1">Days</div>
              <div className="grid grid-cols-2 divide-x divide-gray-800">
                <div><div className="text-center text-xs font-semibold text-gray-400">Plan</div><BigNumber value={d.release?.plan_days == null ? "—" : fmtN(d.release.plan_days, 0)} /></div>
                <div><div className="text-center text-xs font-semibold text-gray-400">Actual</div><BigNumber value={d.release?.actual_days == null ? "—" : fmtN(d.release.actual_days, 0)} /></div>
              </div>
              <AsOf year={year} month={d.release?.month} {...sel} />
            </EisSection>
          </div>

          <EisSection title="COGS Performance">
            <div className="text-center text-xs font-semibold text-gray-300 mb-1">GPM</div>
            {gpm.length === 0 ? <div className="py-8 text-center text-xs text-gray-600">No GPM data yet.</div> : (
              <ResponsiveContainer width="100%" height={Math.max(180, gpm.length * 22 + 30)}>
                <BarChart data={gpm} layout="vertical" margin={{ left: 8, right: 44, top: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} horizontal={false} />
                  <XAxis type="number" tick={TPL_TICK} tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="product" tick={{ fontSize: 10, fill: "#334155" }} width={110} interval={0} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${fmtN(v, 1)}%`, "GPM"]} />
                  <Bar dataKey="gpm_pct" name="GPM" fill={XL_BLUE} barSize={12}>
                    <LabelList dataKey="gpm_pct" position="right" formatter={(v) => `${fmtN(v, 0)}%`} style={{ ...TPL_LABEL, fontSize: 10 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
            {d.gpm && <AsOf year={d.gpm.year} month={d.gpm.month} {...sel} />}
          </EisSection>
        </div>
      </div>

      <EisSection title="Overtime Ratio">
        <div className="text-center text-xs font-semibold text-gray-300 mb-1">Overtime Ratio - Plant</div>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={overtime} margin={{ top: 16, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
            <XAxis dataKey="name" tick={TPL_TICK} />
            <YAxis yAxisId="h" tick={TPL_TICK} tickFormatter={fmtInt} width={56} />
            <YAxis yAxisId="r" orientation="right" tick={TPL_TICK} tickFormatter={(v) => `${v}%`} width={40} domain={[0, (max) => Math.max(25, Math.ceil(max / 5) * 5)]} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, n) => n === "Overtime Ratio" ? [`${fmtN(v, 0)}%`, n] : [fmtInt(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="h" dataKey="overtime_hours" name="Overtime Hour" fill={XL_BLUE} />
            <Bar yAxisId="h" dataKey="working_hours" name="Working Hour" fill={XL_ORANGE} />
            <Line yAxisId="r" type="linear" dataKey="ratio_pct" name="Overtime Ratio" stroke={XL_GRAY} strokeWidth={2} dot={{ r: 3, fill: XL_GRAY }}>
              <LabelList dataKey="ratio_pct" position="top" formatter={(v) => v == null ? "" : `${fmtN(v, 0)}%`} style={TPL_LABEL} />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>
      </EisSection>
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
function SourceTag({ children }) {
  return (
    <div className="flex justify-end">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 bg-gray-900 border border-gray-800 rounded-full px-2.5 py-1">
        Source data: {children}
      </span>
    </div>
  );
}

/* Laid out after the template's Administration sheet: Personel Plan,
   Financial Updates, Financial Ratio, Budget Utilization. Actuals are live
   (HRGA employees, Oracle GL via Accounting); plans come from the EIS
   Template upload — see eis_administration.py /dashboard. Uses the shared
   EIS template pieces defined above the Performance tab. */
const ADM_GROUP_LABEL = {
  "Sales & Marketing": "S&M", "Strategy & Development": "SD", Plant: "Plant", Administration: "Admin",
};
const ADM_PIE_COLORS = [XL_BLUE, XL_ORANGE, XL_GRAY, "#FFC000"];

/** Full ring: blue = achieved, pale = remainder (capped at 100% visually). */
function FullDonut({ pct, height = 150 }) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={[{ v }, { v: 100 - v }]} dataKey="v" startAngle={90} endAngle={-270}
            innerRadius="58%" outerRadius="90%" stroke="none" isAnimationActive={false}>
            <Cell fill={XL_BLUE} /><Cell fill="#dbe4f3" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex items-center justify-center text-lg font-extrabold text-gray-100">
        {pct == null ? "—" : `${fmtN(pct, 0)}%`}
      </div>
    </div>
  );
}

function PersonRow({ label, count, indent = false }) {
  return (
    <div className="grid grid-cols-[110px_36px_1fr] items-center gap-2 py-0.5">
      <span className={`text-xs font-bold text-gray-200 ${indent ? "pl-5" : ""}`}>{label}</span>
      <span className="text-xs font-semibold text-gray-300 text-right">{count}</span>
      <div className="flex flex-wrap gap-px">
        {Array.from({ length: count }, (_, i) => <PersonStanding key={i} size={11} strokeWidth={2.5} style={{ color: XL_ORANGE }} />)}
      </div>
    </div>
  );
}

function KpiBox({ title, value }) {
  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden flex flex-col">
      <div className="text-center text-xs font-bold text-gray-200 py-1 border-b border-gray-800">{title}</div>
      <div className="flex-1 flex items-center justify-center py-2 text-4xl font-extrabold text-gray-100">{value}</div>
    </div>
  );
}

function OracleError({ block }) {
  return <div className="py-8 text-center text-xs text-red-600">Oracle data could not be read: {block.error}</div>;
}

/** Monthly bars with value labels (negative bars allowed). */
function MonthlyBars({ rows, height = 210 }) {
  const data = rows.map((r) => ({ ...r, name: MONTHS_SHORT[r.month - 1] }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 18, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
        <XAxis dataKey="name" tick={TPL_TICK} />
        <YAxis tick={TPL_TICK} tickFormatter={fmtInt} width={62} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmtInt(v), "Actual"]} />
        <ReferenceLine y={0} stroke="#94a3b8" />
        <Bar dataKey="actual" name="Actual" fill={XL_BLUE} barSize={18}>
          <LabelList dataKey="actual" position="top" formatter={(v) => v == null ? "" : fmtInt(v)} style={TPL_LABEL} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function EisAdministrationTab({ year, period }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    eisApi.getAdministrationDashboard(year, period)
      .then((r) => { if (!cancelled) setD(r); })
      .catch((e) => { console.error("Failed to load EIS administration:", e); if (!cancelled) setD(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [year, period]);

  if (loading) return <Loading />;
  if (!d) return <ChartCard title=""><div className="py-12 text-center text-sm text-gray-500">Failed to load the Administration data.</div></ChartCard>;

  const p = d.personnel, f = d.financial, r = d.ratios, b = d.budget;
  const g = p.groups;
  const budgetRows = (b?.monthly || []).map((x) => ({ ...x, name: MONTHS_SHORT[x.month - 1] }));
  const pie = (b?.departments || []).map((x) => ({ ...x, name: ADM_GROUP_LABEL[x.group] }));

  return (
    <div className="space-y-4">
      <SourceTag>HRGA Employee · Oracle GL (Accounting) · plan: EIS Template</SourceTag>
      <EisHeaderBand title="ADMINISTRATION" year={year} period={period} />
      {!d.has_plan && (
        <div className="text-xs text-amber-700 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          Plan (Business Plan headcount, Net Profit, Cashflow, Budget) is not available for {year} yet. Upload the EIS Template workbook (sheets Administration_Headcount &amp; Administration_Financial) in EIS → Data Upload.
        </div>
      )}

      <EisSection title="Personnel Plan" subtitle="Total Employee">
        <div className="grid grid-cols-1 lg:grid-cols-[150px_1fr_170px] gap-3">
          <div className="grid grid-rows-2 gap-3">
            <KpiBox title="Total" value={fmtInt(p.total)} />
            <KpiBox title="Turnover Rate" value={p.turnover_pct == null ? "—" : `${fmtN(p.turnover_pct, 0)}%`} />
          </div>
          <div className="border border-gray-800 rounded-lg px-3 py-2 flex flex-col justify-center">
            <PersonRow label="S&M" count={g["Sales & Marketing"]} />
            <PersonRow label="SD" count={g["Strategy & Development"]} />
            <PersonRow label="Plant" count={g.Plant} />
            <PersonRow label="Plant Direct" count={p.plant_direct} indent />
            <PersonRow label="Plant Indirect" count={p.plant_indirect} indent />
            <PersonRow label="Admin" count={g.Administration} />
            {p.unassigned > 0 && <PersonRow label="No department" count={p.unassigned} />}
            <div className="text-[10px] text-gray-600 mt-1">Plant Direct = Production &amp; PPWH teams · turnover = resignations Jan–{MONTHS_SHORT[period - 1]} ÷ average headcount</div>
          </div>
          <div className="grid grid-rows-2 gap-3">
            <KpiBox title="Business Plan" value={p.plan == null ? "—" : fmtInt(p.plan)} />
            <KpiBox title="Achievement" value={p.achievement_pct == null ? "—" : `${fmtN(p.achievement_pct, 0)}%`} />
          </div>
        </div>
        <div className="mt-3">
          <BlockTitle>Monthly Headcount</BlockTitle>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={p.monthly.map((x) => ({ ...x, name: MONTH_NAMES[x.month - 1] }))} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={TPL_GRID} vertical={false} />
              <XAxis dataKey="name" tick={TPL_TICK} />
              <YAxis tick={TPL_TICK} domain={[(min) => Math.max(0, Math.floor((min - 5) / 2) * 2), (max) => Math.ceil((max + 1) / 2) * 2]} width={40} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [v, "Headcount"]} />
              <Bar dataKey="headcount" name="Headcount" fill={XL_BLUE} barSize={26}>
                <LabelList dataKey="headcount" position="top" style={TPL_LABEL} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </EisSection>

      <EisSection title="Financial Updates">
        {f?.error ? <OracleError block={f} /> : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div>
              <div className="text-center text-sm font-bold text-gray-200 border-b border-gray-800 pb-1 mb-2">Profit or Loss</div>
              <div className="grid grid-cols-1 sm:grid-cols-[150px_1fr] gap-2 items-center">
                <div>
                  <BlockTitle>Net Profit Progress</BlockTitle>
                  <FullDonut pct={f.net_profit_progress_pct} />
                  <div className="text-[10px] text-gray-600 text-center">YTD {fmtInt(f.net_profit_ytd)} ÷ plan {f.net_profit_ytd_plan == null ? "—" : fmtInt(f.net_profit_ytd_plan)}</div>
                </div>
                <div>
                  <BlockTitle>Monthly Net Profit - IDR Million</BlockTitle>
                  <MonthlyBars rows={f.net_profit} />
                </div>
              </div>
            </div>
            <div>
              <div className="text-center text-sm font-bold text-gray-200 border-b border-gray-800 pb-1 mb-2">Cashflow</div>
              <div className="grid grid-cols-1 sm:grid-cols-[150px_1fr] gap-2 items-center">
                <div>
                  <BlockTitle>Achievement</BlockTitle>
                  <FullDonut pct={f.cash_achievement_pct} />
                  <div className="text-[10px] text-gray-600 text-center">Cash balance {MONTHS_SHORT[period - 1]} ÷ plan {f.cash_plan == null ? "—" : fmtInt(f.cash_plan)}</div>
                </div>
                <div>
                  <BlockTitle>Monthly - IDR Million</BlockTitle>
                  <MonthlyBars rows={f.cash} />
                </div>
              </div>
            </div>
          </div>
        )}
      </EisSection>

      <EisSection title="Financial Ratio (days)">
        {r?.error ? <OracleError block={r} /> : (
          <div className="grid grid-cols-2 divide-x divide-gray-800 border border-gray-800 rounded-lg">
            {[["DSO", "dso", `Average AR ${fmtInt(r.avg_ar)} ÷ Sales ${fmtInt(r.sales)} × 365`],
              ["DPO", "dpo", `Average AP ${fmtInt(r.avg_ap)} ÷ COGS ${fmtInt(r.cogs)} × 365`]].map(([k, key, formula]) => {
              const src = r[`${key}_source`], mo = r[`${key}_month`];
              const from = src === "template" ? "Administration_Ratios" : src === "oracle" ? "Oracle GL (not in Administration_Ratios)" : null;
              return (
                <div key={k} className="text-center py-2">
                  <div className="text-sm font-bold text-gray-200 border-b border-gray-800 pb-1 mb-2">{k}</div>
                  <div className="text-3xl font-extrabold text-gray-100">{r[`${key}_days`] == null ? "—" : fmtN(r[`${key}_days`], 0)}</div>
                  <div className="text-[10px] text-gray-600 mt-1">
                    {from ? `${formula} · ${from}${mo && mo !== period ? ` as of ${MONTHS_SHORT[mo - 1]}` : ""}` : "No data"}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </EisSection>

      <EisSection title="Budget Utilization">
        {b?.error ? <OracleError block={b} /> : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div>
              <BlockTitle>Monthly - IDR Million</BlockTitle>
              <MonthlyPlanActual seg={{ monthly: b.monthly }} />
            </div>
            <div>
              <div className="grid grid-cols-2 gap-3 mb-1">
                <div>
                  <div className="text-xs font-bold text-gray-200">Budget Usage :</div>
                  <div className="text-xl font-extrabold text-gray-100">{fmtInt(b.ytd_actual)} <span className="text-xs font-semibold text-gray-500">IDR Million</span></div>
                  <div className="text-[10px] text-gray-600">Jan–{MONTHS_SHORT[period - 1]} · plan {b.ytd_plan == null ? "—" : fmtInt(b.ytd_plan)}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs font-bold text-gray-200">Budget Achievement :</div>
                  <div className="text-xl font-extrabold text-gray-100">{b.achievement_pct == null ? "—" : `${fmtN(b.achievement_pct, 0)}%`}</div>
                </div>
              </div>
              <BlockTitle>Department Allocation</BlockTitle>
              <ResponsiveContainer width="100%" height={230}>
                <PieChart>
                  <Pie data={pie} dataKey="actual" nameKey="name" outerRadius="75%" isAnimationActive={false}
                    label={({ share_pct }) => `${fmtN(share_pct, 0)}%`} labelLine={false}>
                    {pie.map((_, i) => <Cell key={i} fill={ADM_PIE_COLORS[i % ADM_PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, n, item) => [`${fmtInt(v)} (plan ${item.payload.plan == null ? "—" : fmtInt(item.payload.plan)})`, n]} />
                  <Legend layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="text-[10px] text-gray-600 text-center">Actual from Oracle GL (expenses per department, segment3) · plan from the EIS Template</div>
            </div>
          </div>
        )}
      </EisSection>
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
  // Business Plan / Expectation Closing / Achievement cards: Yearly sums
  // all 12 months, Monthly follows whatever month is selected below (same
  // selector the WD chart already uses) — both shown side by side rather
  // than behind a toggle, see getDailySalesKpi.
  const [kpiYearly, setKpiYearly] = useState(null);
  const [kpiMonthly, setKpiMonthly] = useState(null);
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

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      eisApi.getDailySalesKpi(year, null),
      eisApi.getDailySalesKpi(year, selectedMonth),
    ]).then(([y, m]) => { if (!cancelled) { setKpiYearly(y); setKpiMonthly(m); } })
      .catch(() => { if (!cancelled) { setKpiYearly(null); setKpiMonthly(null); } });
    return () => { cancelled = true; };
  }, [year, selectedMonth]);

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
  const chartData = rows.filter((r) => r[selectedMonth]?.acc != null).map((r) => ({ wd: r.wd, acc: r[selectedMonth].acc, sales: r[selectedMonth].sales }));
  const monthTarget = monthTargets[selectedMonth] || 0;
  const selectedMonthLabel = MONTHS_FULL_ID.find((m) => m.key === selectedMonth)?.label || selectedMonth;

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

      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1">
        Daily Sales Performance — {year} ({data?.month || "no data yet"})
      </h2>

      {(kpiYearly || kpiMonthly) && !(kpiYearly?.has_pac_data ?? kpiMonthly?.has_pac_data) && (
        <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          The PAC dashboard has no Business Plan (Sales Plan) data for {year} yet — the Business Plan &amp; Achievement cards below show 0 until it is uploaded in PAC.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DailySalesKpiColumn label="Yearly" kpi={kpiYearly} />
        <DailySalesKpiColumn label={`Monthly — ${selectedMonthLabel}`} kpi={kpiMonthly} />
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

      <ChartCard title="Daily Sales Detail per Working Day" subtitle="in Million IDR · Acc = Accumulated, Sales = Daily · purple italic = run-rate projection (no actual data yet)" className="overflow-x-auto">
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
                  const title = cell.projected ? "Projected — no actual data yet, calculated from the current month's run-rate" : undefined;
                  return (
                    <Fragment key={m.key}>
                      <td title={title} className={`px-1.5 py-1.5 text-right font-mono border-l border-gray-800/60 ${
                        cell.acc == null ? "text-gray-700" : cell.projected ? "text-purple-400 italic" : overTarget ? "text-emerald-400 font-semibold" : "text-gray-300"
                      }`}>{fmtInt(cell.acc)}</td>
                      <td title={title} className={`px-1.5 py-1.5 text-right font-mono ${
                        cell.sales == null ? "text-gray-700" : cell.projected ? "text-purple-400/70 italic" : cell.sales < 0 ? "text-red-400" : "text-gray-500"
                      }`}>{fmtInt(cell.sales)}</td>
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
  const [otLogsKey, setOtLogsKey] = useState(0);
  const otFileRef = useRef(null);

  const [cogs, setCogs] = useState([]);
  const [cogsLoading, setCogsLoading] = useState(true);
  const [cogsUploading, setCogsUploading] = useState(false);
  const [cogsMsg, setCogsMsg] = useState(null);
  const [cogsLogsKey, setCogsLogsKey] = useState(0);
  const cogsFileRef = useRef(null);

  const [salesBP, setSalesBP] = useState([]);
  const [bpLoading, setBpLoading] = useState(true);
  const [bpUploading, setBpUploading] = useState(false);
  const [bpMsg, setBpMsg] = useState(null);
  const [bpLogsKey, setBpLogsKey] = useState(0);
  const bpFileRef = useRef(null);

  const [expUploading, setExpUploading] = useState(false);
  const [expMsg, setExpMsg] = useState(null);
  const [expLogsKey, setExpLogsKey] = useState(0);
  const expFileRef = useRef(null);

  const [ptUploading, setPtUploading] = useState(false);
  const [ptMsg, setPtMsg] = useState(null);
  const [ptLogsKey, setPtLogsKey] = useState(0);
  const ptFileRef = useRef(null);

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
      setOtLogsKey((k) => k + 1);
    } catch (err) { setOtMsg({ type: "err", text: "Failed: " + (err?.response?.data?.detail || err?.detail || err.message) }); setOtLogsKey((k) => k + 1); }
    setOtUploading(false); e.target.value = "";
  };

  const handleCogsUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setCogsUploading(true); setCogsMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadCogsData(selectedYear, fd);
      await loadCogs();
      const skipped = res.skipped?.length > 0 ? ` (no match: ${res.skipped.join(", ")})` : "";
      setCogsMsg({ type: "ok", text: res.message + skipped });
      setCogsLogsKey((k) => k + 1);
    } catch (err) { setCogsMsg({ type: "err", text: "Failed: " + (err?.response?.data?.detail || err?.detail || err.message) }); setCogsLogsKey((k) => k + 1); }
    setCogsUploading(false); e.target.value = "";
  };

  const handleBPUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setBpUploading(true); setBpMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadSalesBP(selectedYear, fd);
      await loadSalesBP();
      const note = res.detected_year && res.detected_year !== selectedYear ? ` (year in the file: ${res.detected_year})` : "";
      setBpMsg({ type: "ok", text: res.message + note });
      setBpLogsKey((k) => k + 1);
    } catch (err) { setBpMsg({ type: "err", text: "Failed: " + (err?.response?.data?.detail || err?.detail || err.message) }); setBpLogsKey((k) => k + 1); }
    setBpUploading(false); e.target.value = "";
  };

  const handleExpUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setExpUploading(true); setExpMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadExpansionData(selectedYear, fd);
      const note = res.detected_year && res.detected_year !== selectedYear ? ` (year in the file: ${res.detected_year})` : "";
      setExpMsg({ type: "ok", text: res.message + note });
      setExpLogsKey((k) => k + 1);
    } catch (err) { setExpMsg({ type: "err", text: "Failed: " + (err?.response?.data?.detail || err?.detail || err.message) }); setExpLogsKey((k) => k + 1); }
    setExpUploading(false); e.target.value = "";
  };

  const handlePtUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setPtUploading(true); setPtMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await eisApi.uploadEisTemplate(fd);
      setPtMsg({ type: "ok", text: res.message });
    } catch (err) { setPtMsg({ type: "err", text: "Failed: " + (err?.response?.data?.detail || err?.detail || err.message) }); }
    setPtLogsKey((k) => k + 1);
    setPtUploading(false); e.target.value = "";
  };

  const YearSelector = () => (
    <div className="flex items-center gap-2">
      <label className="text-xs text-gray-500 font-medium">Year:</label>
      <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))} className={selCls}>
        {Array.from({ length: 5 }, (_, i) => CY - i).map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
    </div>
  );

  return (
    <div className="space-y-4">
      <ChartCard title="EIS Template — Production, Performance & Administration" subtitle="EIS Template workbook (e.g. EIS_Template_2026_V2_Filled_v4-PRODUCTION.xlsx). Only the sheets in the file are updated; other sheets are ignored. The year is taken from the file contents."
        right={
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={() => ptFileRef.current?.click()} disabled={ptUploading} className={`${uploadBtnCls} bg-indigo-600 hover:bg-indigo-700`}>
              {ptUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {ptUploading ? "Uploading..." : "Choose File"}
            </button>
            <input ref={ptFileRef} type="file" accept=".xlsx" className="hidden" onChange={handlePtUpload} />
          </div>
        }>
        <MsgBanner msg={ptMsg} onClose={() => setPtMsg(null)} />
        <RequiredFormatNote>
          <p>Each sheet is a table with its <strong className="text-gray-300">header in row 1</strong> (column names, any order). The <strong className="text-gray-300">notes</strong> column is only a filling guide and is not stored.</p>
          <ul className="list-disc pl-4 space-y-0.5">
            <li><strong className="text-gray-300">Production_BatchYield</strong>: segment, year, month, plan_qty, batch_size_qty, actual_qty — the "(Total Company)" segment holds the batch size &amp; actual for yield</li>
            <li><strong className="text-gray-300">Production_Ratios</strong>: metric (DIO / Overtime Ratio), segment, year, month, value_1, Type (COGS, Average Inventory / Overtime Hour, Working Hour)</li>
            <li><strong className="text-gray-300">Production_Release</strong>: product_code, year, month, plan_days, actual_days</li>
            <li><strong className="text-gray-300">Production_COGSRatio</strong>: product_code (molecule name), year, month, gpm_ratio (1.87 = 187%)</li>
            <li><strong className="text-gray-300">Production_MachineUtilization</strong>: plant, year, month, availability_pct, performance_pct, quality_pct (0.8 = 80%)</li>
            <li><strong className="text-gray-300">SalesSummary_Monthly</strong>: business_type (Local / CMO &amp; Others / Export), year, month, plan_amount, actual_amount — monthly, million IDR. Also fill in the previous year so Growth can be shown</li>
            <li><strong className="text-gray-300">Sales_Ledger</strong>: product_name, market, year, month, scenario (Actual / Business Plan), sales_amount, cogs_amount, opex_amount, ebit_amount — used for EBIT - Product</li>
            <li><strong className="text-gray-300">AreaSales_Ledger</strong>: region, city, year, month, segment, sales_amount — monthly per area</li>
            <li><strong className="text-gray-300">Marketing_Activities</strong>: event_name, region, year, Month, plan_event_count (annual target), actual_event_count (cumulative YTD)</li>
            <li><strong className="text-gray-300">Administration_Headcount</strong>: department, year, month, plan_count, actual_count — only the company-row plan (empty department) is used; actual headcount comes live from HRGA</li>
            <li><strong className="text-gray-300">Administration_Financial</strong>: metric (Net Profit / Cashflow Ending Balance / Budget Usage / Budget Allocation), department, year, month, plan_amount, actual_amount — only the plan is used; actuals come live from Oracle GL</li>
            <li><strong className="text-gray-300">Administration_Ratios</strong>: metric (DSO / DPO), year, month, value_1, Type (Sales, Average AR / COGS, Average AP) — the Summary's Net Working Capital uses DSO = Average AR ÷ Sales × 365 and DPO = Average AP ÷ COGS × 365</li>
          </ul>
          <p><strong className="text-gray-300">month</strong> = English month name (January…) or 1–12. Re-uploading replaces all data for the years in the file; empty cells are stored empty (not zero).</p>
        </RequiredFormatNote>
        <UploadHistoryTable uploadType="eis-template" refreshKey={ptLogsKey} />
      </ChartCard>

      <ChartCard title="Upload Overtime Data" subtitle="Column B format: label (Overtime Hour / Working Hour) · Columns C–N: Jan–Dec · Reference: overtime_data.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => otFileRef.current?.click()} disabled={otUploading} className={`${uploadBtnCls} bg-cyan-600 hover:bg-cyan-700`}>
              {otUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {otUploading ? "Uploading..." : "Choose File"}
            </button>
            <input ref={otFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleOtUpload} />
          </div>
        }>
        <MsgBanner msg={otMsg} onClose={() => setOtMsg(null)} />
        <RequiredColumnsTable columns={OVERTIME_COLUMNS} />
        <UploadHistoryTable uploadType="overtime" refreshKey={otLogsKey} />
      </ChartCard>

      <ChartCard title="Upload Business Plan Sales Data" subtitle="Month header (Jan–Dec) + segment rows (Total/Local/CMO/Export), values in million IDR. Reference: DATA BP.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => bpFileRef.current?.click()} disabled={bpUploading} className={`${uploadBtnCls} bg-blue-600 hover:bg-blue-700`}>
              {bpUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {bpUploading ? "Uploading..." : "Choose File"}
            </button>
            <input ref={bpFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleBPUpload} />
          </div>
        }>
        <MsgBanner msg={bpMsg} onClose={() => setBpMsg(null)} />
        <RequiredFormatNote>
          <p>The file must have <strong className="text-gray-300">1 header row with month names</strong> (Jan–Dec, at least 6 of 12 months detected) in any columns, followed by rows with a segment label in one of the first 6 columns:</p>
          <p><strong className="text-gray-300">Total</strong> / <strong className="text-gray-300">Local</strong> (or "Lokal") / <strong className="text-gray-300">CMO</strong> / <strong className="text-gray-300">Export</strong> (or "Ekspor") — "Grand Total", "Jumlah", "Total Local", etc. also work.</p>
          <p>Values under the matching month columns are read as numbers. <strong className="text-gray-300">Values in million IDR.</strong></p>
          <div className="mt-1 rounded border border-gray-800 overflow-hidden">
            <table className="w-full text-[10.5px]">
              <thead><tr className="bg-gray-800/60 text-gray-500"><th className="px-2 py-1 text-left">—</th><th className="px-2 py-1 text-right">Jan</th><th className="px-2 py-1 text-right">Feb</th><th className="px-2 py-1 text-right">...</th><th className="px-2 py-1 text-right">Dec</th></tr></thead>
              <tbody className="text-gray-500">
                <tr><td className="px-2 py-1">Total</td><td className="px-2 py-1 text-right">800</td><td className="px-2 py-1 text-right">900</td><td className="px-2 py-1 text-right">...</td><td className="px-2 py-1 text-right">880</td></tr>
                <tr><td className="px-2 py-1">Local</td><td className="px-2 py-1 text-right">500</td><td className="px-2 py-1 text-right">600</td><td className="px-2 py-1 text-right">...</td><td className="px-2 py-1 text-right">550</td></tr>
              </tbody>
            </table>
          </div>
        </RequiredFormatNote>
        <UploadHistoryTable uploadType="sales-bp" refreshKey={bpLogsKey} />
      </ChartCard>

      {!bpLoading && salesBP.length > 0 && (
        <ChartCard title={`Sales Business Plan — ${selectedYear}`} right={<button onClick={loadSalesBP} className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"><RefreshCw size={12} /> Refresh</button>} className="overflow-x-auto">
          <table className="text-xs border-collapse" style={{ minWidth: "900px", width: "100%" }}>
            <thead>
              <tr className="bg-blue-950 text-white">
                <th className="px-3 py-2 text-left font-semibold sticky left-0 bg-blue-950 z-10">Segment</th>
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

      <ChartCard title="Upload COGS Data" subtitle={'"COGS Data New.xlsx" format: row 3 header, row 4 month names, rows 5+ product data (see column details below)'}
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => cogsFileRef.current?.click()} disabled={cogsUploading} className={`${uploadBtnCls} bg-amber-600 hover:bg-amber-700`}>
              {cogsUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {cogsUploading ? "Uploading..." : "Choose File"}
            </button>
            <input ref={cogsFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleCogsUpload} />
          </div>
        }>
        <MsgBanner msg={cogsMsg} onClose={() => setCogsMsg(null)} />
        <RequiredColumnsTable columns={COGS_COLUMNS} />
        <UploadHistoryTable uploadType="cogs" refreshKey={cogsLogsKey} />
      </ChartCard>

      <ChartCard title="Upload Business Expansion Data" subtitle="Sheet 'Business Expansion_Dashboard': columns Product, Potential Supplier, month headers Jan–Dec. Reference: Business Expansion.xlsx"
        right={
          <div className="flex items-center gap-2 shrink-0">
            <YearSelector />
            <button onClick={() => expFileRef.current?.click()} disabled={expUploading} className={`${uploadBtnCls} bg-emerald-600 hover:bg-emerald-700`}>
              {expUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {expUploading ? "Uploading..." : "Choose File"}
            </button>
            <input ref={expFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleExpUpload} />
          </div>
        }>
        <MsgBanner msg={expMsg} onClose={() => setExpMsg(null)} />
        <RequiredFormatNote>
          <p>Headers <strong className="text-gray-300">Product</strong> (column B) and <strong className="text-gray-300">Potential Supplier</strong> (column D), followed by month headers <strong className="text-gray-300">Jan–Dec</strong> (found automatically, at least 10 of 12 months detected in any row).</p>
          <p>Potential Supplier format: <strong className="text-gray-300">"Supplier Name - Country"</strong> (e.g. "Kexing Biopharm - China") — the country part is optional.</p>
          <p>Fill the month columns with the <strong className="text-gray-300">stage</strong> name only in the month the stage changes (cells may be merged across several months) — empty months in between automatically continue the last stage. "-" or empty = no stage yet. Recognised stages:</p>
          <p className="text-gray-300">Market Analysis &middot; Resource Supplier &middot; Contract Agreement &middot; Registration &middot; Launch Preparation</p>
        </RequiredFormatNote>
        <UploadHistoryTable uploadType="expansion" refreshKey={expLogsKey} />
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
        {cogsLoading ? <div className="py-8 text-center text-gray-600 text-sm">Loading...</div> : cogs.length === 0 ? (
          <div className="py-8 text-center text-gray-600 text-sm">No COGS data yet. Upload the file and make sure etl_cogs has run.</div>
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
                    <th className="px-3 py-2 text-left font-semibold">Product</th>
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
            <p className="text-sm">No overtime data for {selectedYear} yet.</p>
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
                  <th className="px-4 py-2 text-left font-semibold">Month</th>
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

/* ─── Main: EIS Dashboard ───────────────────────────────────────── */
const EIS_TABS = [
  { id: "summary", label: "Summary" },
  { id: "production", label: "Production" },
  { id: "performance", label: "Performance" },
  { id: "administration", label: "Administration" },
  { id: "daily-sales", label: "Daily Sales" },
  { id: "expansion", label: "Expansion" },
  { id: "business-plan", label: "Business Plan" },
  { id: "data-upload", label: "Data Upload" },
];

export default function EISDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const [year, setYear] = useState(CY);
  const [period, setPeriod] = useState(new Date().getMonth() || 12);
  const YEARS = Array.from({ length: 5 }, (_, i) => CY - i);

  // Derive active tab from URL — navigation now lives in the sidebar tree menu.
  const tab = EIS_TABS.find((t) => location.pathname.endsWith(t.id))?.id ?? "summary";

  useEffect(() => {
    if (location.pathname === "/dashboard/eis" || location.pathname === "/dashboard/eis/") {
      navigate("/dashboard/eis/summary", { replace: true });
    }
  }, []); // eslint-disable-line

  // Daily Sales only has data for years someone has actually uploaded —
  // unlike every other EIS tab (backed by live DB queries), so the shared
  // Year selector switches to that real list while this tab is active
  // instead of the generic rolling-5-year window, which used to offer
  // years with nothing to show.
  const [dailySalesYears, setDailySalesYears] = useState(null);
  useEffect(() => {
    if (tab !== "daily-sales") return;
    let cancelled = false;
    eisApi.getDailySalesYears().then((ys) => { if (!cancelled) setDailySalesYears(ys); }).catch(() => {});
    return () => { cancelled = true; };
  }, [tab]);

  const yearOptions = tab === "daily-sales" && dailySalesYears?.length ? dailySalesYears : YEARS;
  useEffect(() => {
    if (tab === "daily-sales" && dailySalesYears?.length && !dailySalesYears.includes(year)) {
      setYear(dailySalesYears[0]);
    }
  }, [tab, dailySalesYears]); // eslint-disable-line

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
          <Database size={20} className="text-cyan-400" /> EIS — Executive Information System
        </h1>
        <div className="flex items-center gap-2">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} className={selCls}>
            {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={period} onChange={(e) => setPeriod(Number(e.target.value))} className={selCls}>
            {MONTHS_SHORT.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
        </div>
      </div>

      {tab === "summary" && <EisSummaryTab year={year} period={period} />}
      {tab === "performance" && <EisPerformanceTab year={year} period={period} />}
      {tab === "production" && <EisProductionTab year={year} period={period} />}
      {tab === "expansion" && <EisExpansionTab year={year} period={period} />}
      {tab === "administration" && <EisAdministrationTab year={year} period={period} />}
      {tab === "business-plan" && <EisBusinessPlanTab year={year} />}
      {tab === "daily-sales" && <EisDailySalesTab year={year} />}
      {tab === "data-upload" && <EisDataUploadTab year={year} />}
    </div>
  );
}
