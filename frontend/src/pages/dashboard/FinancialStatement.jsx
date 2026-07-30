import { useState, useEffect, useMemo, useCallback } from "react";
import { FileBarChart2, Table2, TrendingUp, CalendarDays, Loader2, RefreshCw, AlertTriangle, Download } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { financialStatementApi } from "@/api/dashboard";

// Fixed categorical order (never cycled) — validated for CVD-safe adjacent
// pairs, see the dataviz skill's reference palette. Gross Profit / Profit
// (Loss) Before Tax / Total Comprehensive Income always map to these three
// slots in this order.
const CHART_COLORS = { grossProfit: "#2a78d6", pbt: "#eb6834", tci: "#1baf7a" };

const NEU = {
  bg:          "#e8edf5",
  shadowOut:   "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn:    "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
};

// colorScheme:"light" forces native form controls (the <select>'s own
// dropdown/<option> list) to render with light-mode system colors even
// when the OS/browser is in dark mode — without it, the dropdown panel
// can pick up a dark system background while inheriting our light text
// color, making the open list unreadable.
const SELECT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none", colorScheme: "light" };
const BTN = { padding: "8px 14px", borderRadius: 9, border: "none", background: NEU.bg, boxShadow: NEU.shadowOutSm, color: "#334155", fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 };

// client.js's axios interceptor already unwraps response.data for every
// call in this app, so `blobData` here IS the Blob itself — not {data: Blob}.
async function downloadExport(apiCall, filename, setBusy, setErr) {
  setBusy(true);
  try {
    const blobData = await apiCall();
    const blob = new Blob([blobData], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    let msg = "Export failed";
    if (e instanceof Blob) {
      try { msg = JSON.parse(await e.text())?.detail || msg; } catch (_) {}
    } else if (e?.detail) {
      msg = e.detail;
    } else if (e?.message) {
      msg = e.message;
    }
    setErr?.("Export error: " + msg);
  } finally {
    setBusy(false);
  }
}

const FS_SUBTABS = [
  { id: "balance-sheet",        label: "Balance Sheet",         icon: FileBarChart2 },
  { id: "balance-sheet-detail", label: "Balance Sheet Detail",  icon: Table2 },
  { id: "profit-loss",          label: "Profit or Loss",        icon: TrendingUp },
  { id: "profit-loss-monthly",  label: "Profit or Loss Monthly", icon: CalendarDays },
];

const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
const MONTH_LABEL = { JAN:"Jan",FEB:"Feb",MAR:"Mar",APR:"Apr",MAY:"May",JUN:"Jun",JUL:"Jul",AUG:"Aug",SEP:"Sep",OCT:"Oct",NOV:"Nov",DEC:"Dec" };

function fmtNum(v) {
  const n = Number(v) || 0;
  const s = Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  return n < 0 ? `(${s})` : s;
}

function fmtShort(v) {
  const n = Number(v) || 0;
  const abs = Math.abs(n);
  const s = abs >= 1_000_000_000 ? (abs / 1_000_000_000).toFixed(1) + "B"
    : abs >= 1_000_000 ? (abs / 1_000_000).toFixed(0) + "M"
    : abs >= 1_000 ? (abs / 1_000).toFixed(0) + "K"
    : String(abs);
  return n < 0 ? `(${s})` : s;
}

function yy(year) { return String(year).slice(-2); }

/* ── Period helpers ──────────────────────────────────────────────────── */

function fiscalYears(periods) {
  return [...new Set(periods.filter(p => p.adjustment_period_flag !== "Y").map(p => p.period_year))].sort((a, b) => b - a);
}

function periodsOfYear(periods, year) {
  return periods.filter(p => p.period_year === year && p.adjustment_period_flag !== "Y").sort((a, b) => a.period_num - b.period_num);
}

function yearEndInfo(periods, year) {
  const yp = periodsOfYear(periods, year);
  const dec = yp.find(p => p.period_num === 12);
  const isClosed = dec && dec.has_activity === "Y";
  const adj = periods.find(p => p.period_year === year && p.adjustment_period_flag === "Y");
  return { yp, dec, isClosed, adj };
}

function fyColumnPeriods(periods, year) {
  const { yp, dec, isClosed, adj } = yearEndInfo(periods, year);
  if (isClosed) {
    return yp.map(p => p.period_name).concat(adj && adj.has_activity === "Y" ? [adj.period_name] : []);
  }
  return yp.filter(p => p.has_activity === "Y").map(p => p.period_name);
}

function latestActivePeriod(periods) {
  const active = periods.filter(p => p.adjustment_period_flag !== "Y" && p.has_activity === "Y");
  active.sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
  return active[active.length - 1] || null;
}

function periodLabel(p) {
  if (!p) return "";
  return p.adjustment_period_flag === "Y" ? `ADJ ${p.period_year}` : `${MONTH_LABEL[MONTHS[p.period_num - 1]]} ${p.period_year}`;
}

// Month options for a given year's Single Period picker — restricted to
// months that actually have posted balances, same constraint the old flat
// "As of Period" dropdown enforced.
function monthOptionsForYear(periods, year) {
  if (!year) return [];
  return periodsOfYear(periods, year).filter(p => p.has_activity === "Y").map(p => MONTHS[p.period_num - 1]);
}

// Resolves a (month, year) pair to its GL period_name, or null if that
// period doesn't exist / has no posted activity yet (e.g. a future month
// in the currently-open fiscal year).
function periodNameForMonthYear(periods, month, year) {
  const p = periodsOfYear(periods, year).find(pp => MONTHS[pp.period_num - 1] === month);
  return p && p.has_activity === "Y" ? p.period_name : null;
}

/* ── Generic line-item table ──────────────────────────────────────────────
 * Row model mirrors the Excel export / management-report look: a dark-navy
 * "ACCOUNT" header, bold no-fill group/section headers (ASSETS, CURRENT
 * ASSETS, ...), indented non-bold line items, and bold light-blue-filled
 * TOTAL rows — see the reference screenshot from FS_CKD OTTO's Balance
 * Sheet tab.
 *   { type: "header", label, level }               — e.g. ASSETS, CURRENT ASSETS
 *   { type: "line",   label, values, level }        — e.g. CASH & CASH EQUIVALENTS
 *   { type: "total",  label, values, level }        — e.g. TOTAL CURRENT ASSETS
 */

// The .fs-table / [data-type] / [data-lvl] rules in index.css do the real
// styling — the global tbody/thead CSS in this app forces zebra striping,
// uniform padding and font-weight on every plain <table> via !important,
// which silently defeats inline styles. A scoped class + data attributes
// is this codebase's established fix for that (see .inv-rmpm-table).
// growthMode: "none" (default, all other FsTable callers) | "diff" (1 prior
// period -> absolute delta + %) | "cagr" (>1 prior periods spanning years ->
// compound annual growth rate). Only BalanceSheetPanel passes this — every
// other caller keeps its original 1-column-per-period layout.
function FsTable({ columns, rows, checkDiff, growthMode = "none" }) {
  const growthHeaders = growthMode === "diff" ? ["Growth", "Growth %"] : growthMode === "cagr" ? ["CAGR %"] : [];
  const allColumns = [...columns, ...growthHeaders];
  return (
    <div style={{ overflowX: "auto", borderRadius: 12, boxShadow: NEU.shadowOutSm }}>
      <table className="fs-table" style={{ width: "100%", fontSize: 12.5, minWidth: 480 + allColumns.length * 130 }}>
        <thead>
          <tr>
            <th>ACCOUNT</th>
            {allColumns.map((c, i) => <th key={i} style={{ whiteSpace: "nowrap" }}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => <FsRow key={ri} row={row} columnCount={allColumns.length} growthMode={growthMode} />)}
        </tbody>
      </table>
      {checkDiff && (
        <div style={{ padding: "8px 14px", fontSize: 11, color: Math.abs(checkDiff[checkDiff.length - 1]) > 1 ? "#dc2626" : "#16a34a" }}>
          Assets − (Liabilities + Equity) check: {checkDiff.map(d => fmtNum(d)).join(" / ")}
        </div>
      )}
    </div>
  );
}

function fmtPct(v) {
  if (v == null || !isFinite(v)) return "n/a";
  const s = Math.abs(v).toFixed(1) + "%";
  return v < 0 ? `(${s})` : s;
}

function growthColor(v) {
  if (v == null || !isFinite(v)) return "#94a3b8";
  return v > 0 ? "#16a34a" : v < 0 ? "#dc2626" : "#334155";
}

function FsRow({ row, columnCount = 0, growthMode = "none" }) {
  const level = Math.min(row.level || 0, 2);
  // Header (section title) rows previously rendered zero <td> for the value
  // columns (row.values was undefined, so `(row.values||[]).map(...)` gave
  // an empty array) — the browser just left those column positions with no
  // cell at all, letting the page background show through as a stray grey
  // box under the period columns. Rendering the full columnCount of blank
  // cells here makes the row's background fill apply uniformly across it.
  if (row.type === "header") {
    return (
      <tr data-type="header">
        <td data-lvl={level}>{row.label}</td>
        {Array.from({ length: columnCount }, (_, ci) => <td key={ci} />)}
      </tr>
    );
  }
  const values = row.values || [];
  const g = row.growth;
  return (
    <tr data-type={row.type}>
      <td data-lvl={level}>{row.label}</td>
      {values.map((v, ci) => (
        <td key={ci} style={{ textAlign: "right", fontFamily: "monospace" }}>{fmtNum(v)}</td>
      ))}
      {growthMode === "diff" && (
        <>
          <td style={{ textAlign: "right", fontFamily: "monospace" }}>{g ? fmtNum(g.delta) : "—"}</td>
          <td style={{ textAlign: "right", fontFamily: "monospace", color: growthColor(g?.pct) }}>{g ? fmtPct(g.pct) : "—"}</td>
        </>
      )}
      {growthMode === "cagr" && (
        <td style={{ textAlign: "right", fontFamily: "monospace", color: growthColor(g?.cagr) }}>{g ? fmtPct(g.cagr) : "—"}</td>
      )}
    </tr>
  );
}

// Growth-rate helper shared by the Balance Sheet's Single Period vs Period
// From/To comparison. `values` is the row's array aligned to periodList
// (chronological, Single Period always last):
//   mode "diff" — exactly 1 prior period: absolute delta + % change.
//   mode "cagr" — >1 prior periods (a multi-year Period From/To range):
//     CAGR = (End/Begin)^(1/n) − 1, n = years between the earliest prior
//     period and the Single Period. Undefined (shown "n/a") when the
//     beginning value is zero or the sign flips (asset/liability turning
//     negative to positive, e.g.), since a fractional power of a negative
//     base isn't a real percentage rate.
function computeGrowth(values, mode, cagrYears) {
  if (mode === "none" || !values || values.length < 2) return null;
  const begin = values[0], end = values[values.length - 1];
  if (mode === "diff") {
    const delta = end - begin;
    const pct = begin !== 0 ? (delta / Math.abs(begin)) * 100 : null;
    return { delta, pct };
  }
  if (!cagrYears || cagrYears < 1 || begin === 0 || (begin < 0) !== (end < 0)) {
    return { cagr: null };
  }
  const sign = end < 0 ? -1 : 1;
  const cagr = sign * (Math.pow(Math.abs(end) / Math.abs(begin), 1 / cagrYears) - 1) * 100;
  return { cagr };
}

/* ── Balance Sheet ────────────────────────────────────────────────────── */

function BalanceSheetPanel({ periods, detail }) {
  const years = useMemo(() => fiscalYears(periods), [periods]);
  const latest = useMemo(() => latestActivePeriod(periods), [periods]);

  // Single Period — the report date (renamed from "As of Period"), split
  // into separate Month/Year selects.
  const [asOfMonth, setAsOfMonth] = useState("");
  const [asOfYear, setAsOfYear] = useState("");

  // Period From / Period To — replaces the old single "Compare To" period
  // with a range, so up to ~10 years of history can be compared at once.
  // Year-only (no month picker) — these are always fiscal year-end (Dec)
  // snapshots, so the month is fixed rather than user-selectable.
  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!latest || asOfYear) return;
    setAsOfMonth(MONTHS[latest.period_num - 1]);
    setAsOfYear(latest.period_year);
    const prevYear = latest.period_year - 1;
    const { isClosed, yp } = yearEndInfo(periods, prevYear);
    const dec = yp.find(p => p.period_num === 12);
    if (isClosed && dec) {
      setFromYear(prevYear);
      setToYear(prevYear);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  // If the year changes and the currently-selected month no longer has
  // posted activity in it (e.g. switching from a closed year to the
  // current partial year), snap to the latest month that does.
  useEffect(() => {
    if (!asOfYear) return;
    const opts = monthOptionsForYear(periods, asOfYear);
    if (opts.length && !opts.includes(asOfMonth)) setAsOfMonth(opts[opts.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOfYear, periods]);

  const asOf = useMemo(
    () => (asOfMonth && asOfYear ? periodNameForMonthYear(periods, asOfMonth, asOfYear) : ""),
    [periods, asOfMonth, asOfYear],
  );

  // Chronological annual (December) snapshots between Period From and
  // Period To (inclusive) — e.g. From=2015/To=2024 gives DEC-15..DEC-24.
  // Collapses to a single period when From and To are the same year
  // (identical to the old single Compare To).
  const rangePeriods = useMemo(() => {
    if (!fromYear || !toYear) return [];
    const lo = Math.min(fromYear, toYear), hi = Math.max(fromYear, toYear);
    const names = [];
    for (let y = lo; y <= hi; y++) {
      const pn = periodNameForMonthYear(periods, "DEC", y);
      if (pn && pn !== asOf) names.push(pn);
    }
    return names;
  }, [periods, fromYear, toYear, asOf]);

  const periodList = useMemo(() => (asOf ? [...rangePeriods, asOf] : []), [rangePeriods, asOf]);

  // Growth-rate mode: exactly 1 prior period -> simple diff & %; more than
  // 1 (a multi-year Period From/To range) -> CAGR from the earliest period
  // to the Single Period, n = years spanned between them.
  const growthMode = rangePeriods.length === 1 ? "diff" : rangePeriods.length > 1 ? "cagr" : "none";
  const cagrYears = useMemo(() => {
    if (growthMode !== "cagr" || !rangePeriods.length) return 0;
    const first = periods.find(p => p.period_name === rangePeriods[0]);
    const last = periods.find(p => p.period_name === asOf);
    return first && last ? last.period_year - first.period_year : 0;
  }, [growthMode, rangePeriods, asOf, periods]);

  const load = useCallback(async () => {
    if (!periodList.length) return;
    setLoading(true); setError(null);
    try {
      const res = detail
        ? await financialStatementApi.getBalanceSheetDetail(periodList)
        : await financialStatementApi.getBalanceSheet(periodList);
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [periodList, detail]);

  useEffect(() => { load(); }, [load]);

  const columnLabels = data ? data.periods.map(pn => periodLabel(periods.find(p => p.period_name === pn))) : [];

  const handleExport = () => {
    const asOfP = periods.find(p => p.period_name === asOf);
    const label = periodLabel(asOfP);
    const apiFn = detail ? financialStatementApi.exportBalanceSheetDetail : financialStatementApi.exportBalanceSheet;
    downloadExport(
      () => apiFn(periodList, label),
      `Balance_Sheet${detail ? "_Detail" : ""}_${asOf}.xlsx`,
      setExporting, setError,
    );
  };

  const withGrowth = useCallback(
    (row) => ({ ...row, growth: computeGrowth(row.values, growthMode, cagrYears) }),
    [growthMode, cagrYears],
  );

  const rows = useMemo(() => {
    if (!data) return [];
    if (detail) {
      const byType = { A: [], L: [], O: [] };
      data.accounts.forEach(a => byType[a.account_type]?.push(a));
      const toLines = (accs) => accs.map(a => withGrowth({ type: "line", level: 1, label: `${a.account_code} — ${a.account_desc || a.line_item}`, values: a.values }));
      return [
        { type: "header", level: 0, label: "ASSETS" }, ...toLines(byType.A),
        { type: "header", level: 0, label: "LIABILITIES" }, ...toLines(byType.L),
        { type: "header", level: 0, label: "EQUITY" }, ...toLines(byType.O),
      ];
    }
    const lines = (arr) => arr.map(r => withGrowth({ type: "line", level: 2, label: r.label, values: r.values }));
    return [
      { type: "header", level: 0, label: "ASSETS" },
      { type: "header", level: 1, label: "CURRENT ASSETS" },
      ...lines(data.current_assets),
      withGrowth({ type: "total", level: 1, label: "TOTAL CURRENT ASSETS", values: data.total_current_assets }),
      { type: "header", level: 1, label: "NON CURRENT ASSET" },
      ...lines(data.noncurrent_assets),
      withGrowth({ type: "total", level: 1, label: "TOTAL NON CURRENT ASSETS", values: data.total_noncurrent_assets }),
      withGrowth({ type: "total", level: 0, label: "TOTAL ASSETS", values: data.total_assets }),
      { type: "header", level: 0, label: "LIABILITIES" },
      { type: "header", level: 1, label: "CURRENT LIABILITIES" },
      ...lines(data.current_liabilities),
      withGrowth({ type: "total", level: 1, label: "TOTAL CURRENT LIABILITIES", values: data.total_current_liabilities }),
      { type: "header", level: 1, label: "NONCURRENT LIABILITIES" },
      ...lines(data.noncurrent_liabilities),
      withGrowth({ type: "total", level: 1, label: "TOTAL NONCURRENT LIABILITIES", values: data.total_noncurrent_liabilities }),
      withGrowth({ type: "total", level: 0, label: "TOTAL  LIABILITIES", values: data.total_liabilities }),
      { type: "header", level: 0, label: "EQUITY" },
      ...data.equity.map(r => withGrowth({ type: "line", level: 1, label: r.label, values: r.values })),
      withGrowth({ type: "total", level: 0, label: "TOTAL  EQUITY", values: data.total_equity }),
      withGrowth({ type: "total", level: 0, label: "TOTAL  LIABILITIES AND EQUITY", values: data.total_liabilities_and_equity }),
    ];
  }, [data, detail, withGrowth]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Single Period</label>
          <div style={{ display: "flex", gap: 6 }}>
            <select style={SELECT} value={asOfMonth} onChange={e => setAsOfMonth(e.target.value)}>
              {monthOptionsForYear(periods, asOfYear).map(m => <option key={m} value={m}>{MONTH_LABEL[m]}</option>)}
            </select>
            <select style={SELECT} value={asOfYear} onChange={e => setAsOfYear(Number(e.target.value))}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period From</label>
          <select style={SELECT} value={fromYear} onChange={e => setFromYear(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— None —</option>
            {years.map(y => <option key={y} value={y}>{`Dec ${y}`}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period To</label>
          <select style={SELECT} value={toYear} onChange={e => setToYear(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— None —</option>
            {years.map(y => <option key={y} value={y}>{`Dec ${y}`}</option>)}
          </select>
        </div>
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data} style={BTN}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
        {data?.unmapped_accounts?.length > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#d97706" }}>
            <AlertTriangle size={13} /> {data.unmapped_accounts.length} unmapped account(s): {data.unmapped_accounts.join(", ")}
          </span>
        )}
      </div>

      {growthMode === "cagr" && (
        <div style={{ fontSize: 11, color: "#64748b" }}>
          Membandingkan {rangePeriods.length} tahun ({periodLabel(periods.find(p => p.period_name === rangePeriods[0]))} → {periodLabel(periods.find(p => p.period_name === asOf))}) — kolom growth memakai CAGR ({cagrYears} tahun).
        </div>
      )}

      {loading && !data ? (
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : error ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{error}</div>
      ) : data ? (
        <FsTable columns={columnLabels} rows={rows} checkDiff={!detail ? data.check_diff : null} growthMode={growthMode} />
      ) : null}
    </div>
  );
}

/* ── Profit or Loss ───────────────────────────────────────────────────── */

// Trend chart shown above the table — Gross Profit / Profit (Loss) Before
// Tax / Total Comprehensive Income (Loss), one grouped bar per selected
// fiscal year. A ReferenceLine at 0 matters here since any of the three
// can go negative (a loss year).
function ProfitLossChart({ data }) {
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.columns.map((label, i) => ({
      label,
      grossProfit: data.gross_profit[i],
      pbt: data.profit_before_tax[i],
      tci: data.total_comprehensive[i],
    }));
  }, [data]);

  if (!chartData.length) return null;

  return (
    <div style={{ borderRadius: 12, boxShadow: NEU.shadowOutSm, background: "#ffffff", padding: "14px 18px" }}>
      <p style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>Gross Profit vs Profit (Loss) Before Tax vs Total Comprehensive Income (Loss) — IDR</p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
          <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 11 }} />
          <YAxis tickFormatter={fmtShort} tick={{ fill: "#64748b", fontSize: 10 }} />
          <ReferenceLine y={0} stroke="#c3c2b7" />
          <Tooltip
            contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
            formatter={(v, name) => [fmtNum(v), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#64748b" }} />
          <Bar dataKey="grossProfit" name="Gross Profit" fill={CHART_COLORS.grossProfit} radius={[4, 4, 0, 0]} />
          <Bar dataKey="pbt" name="Profit (Loss) Before Tax" fill={CHART_COLORS.pbt} radius={[4, 4, 0, 0]} />
          <Bar dataKey="tci" name="Total Comprehensive Income (Loss)" fill={CHART_COLORS.tci} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ProfitLossPanel({ periods }) {
  const years = useMemo(() => fiscalYears(periods), [periods]);

  // Period — the current/reporting fiscal year (analogous to Balance
  // Sheet's Single Period, year-only since a P&L column is a whole fiscal
  // year, not a point in time).
  const [periodYear, setPeriodYear] = useState("");
  // Period From / Period To — comparison range (analogous to Balance
  // Sheet's Period From/To), replacing the old Fiscal Years checkbox list.
  // Same year on both = 1 prior year (old default); different years =
  // multi-year trend.
  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!years.length || periodYear) return;
    const latestYear = years[0]; // fiscalYears() sorts descending
    setPeriodYear(latestYear);
    const prevYear = latestYear - 1;
    if (years.includes(prevYear)) {
      setFromYear(prevYear);
      setToYear(prevYear);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [years]);

  const rangeYears = useMemo(() => {
    if (!fromYear || !toYear) return [];
    const lo = Math.min(fromYear, toYear), hi = Math.max(fromYear, toYear);
    const ys = [];
    for (let y = lo; y <= hi; y++) if (y !== periodYear) ys.push(y);
    return ys;
  }, [fromYear, toYear, periodYear]);

  const selectedYears = useMemo(
    () => (periodYear ? [...rangeYears, periodYear] : []),
    [rangeYears, periodYear],
  );

  const columnsForYears = useCallback(
    () => selectedYears.map(y => ({ label: `FY ${y}`, periods: fyColumnPeriods(periods, y) })),
    [selectedYears, periods],
  );

  const load = useCallback(async () => {
    if (!selectedYears.length) return;
    setLoading(true); setError(null);
    try {
      const res = await financialStatementApi.getProfitLoss(columnsForYears());
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [selectedYears, columnsForYears]);

  useEffect(() => { load(); }, [load]);

  const handleExport = () => {
    downloadExport(
      () => financialStatementApi.exportProfitLoss(columnsForYears()),
      `Profit_or_Loss_${selectedYears.join("-")}.xlsx`,
      setExporting, setError,
    );
  };

  const rows = useMemo(() => {
    if (!data) return [];
    const lines = (arr) => arr.map(r => ({ type: "line", level: 1, label: r.label, values: r.values }));
    return [
      { type: "header", level: 0, label: "NET SALES" },
      ...lines([...data.sales_lines, ...data.contra_lines]),
      { type: "total", level: 0, label: "TOTAL NET SALES", values: data.total_net_sales },
      { type: "header", level: 0, label: "COGS" },
      ...lines(data.cogs_lines),
      { type: "total", level: 0, label: "TOTAL COGS", values: data.total_cogs },
      { type: "total", level: 0, label: "GROSS PROFIT", values: data.gross_profit },
      { type: "header", level: 0, label: "EXPENSES" },
      ...lines(data.expense_lines),
      { type: "total", level: 0, label: "TOTAL EXPENSES", values: data.total_expenses },
      { type: "header", level: 0, label: "OTHER INCOME / EXPENSES" },
      ...lines(data.other_lines),
      { type: "total", level: 0, label: "TOTAL OTHER INCOME (EXPENSES)", values: data.total_other },
      { type: "total", level: 0, label: "PROFIT (LOSS) BEFORE TAX", values: data.profit_before_tax },
      { type: "header", level: 0, label: "INCOME TAX" },
      ...lines(data.tax_lines),
      { type: "total", level: 0, label: "TOTAL INCOME TAX BENEFIT (EXPENSE)", values: data.total_tax },
      { type: "total", level: 0, label: "PROFIT (LOSS) AFTER TAX", values: data.profit_after_tax },
      { type: "line", level: 1, label: "OTHER COMPREHENSIVE INCOME", values: data.oci },
      { type: "total", level: 0, label: "TOTAL COMPREHENSIVE INCOME (LOSS)", values: data.total_comprehensive },
    ];
  }, [data]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period</label>
          <select style={SELECT} value={periodYear} onChange={e => setPeriodYear(e.target.value ? Number(e.target.value) : "")}>
            {years.map(y => <option key={y} value={y}>{`FY ${y}`}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period From</label>
          <select style={SELECT} value={fromYear} onChange={e => setFromYear(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— None —</option>
            {years.map(y => <option key={y} value={y}>{`FY ${y}`}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period To</label>
          <select style={SELECT} value={toYear} onChange={e => setToYear(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— None —</option>
            {years.map(y => <option key={y} value={y}>{`FY ${y}`}</option>)}
          </select>
        </div>
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data} style={BTN}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
        {data?.unmapped_accounts?.length > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#d97706" }}>
            <AlertTriangle size={13} /> {data.unmapped_accounts.length} unmapped account(s): {data.unmapped_accounts.join(", ")}
          </span>
        )}
      </div>

      {loading && !data ? (
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : error ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{error}</div>
      ) : data ? (
        <>
          <ProfitLossChart data={data} />
          <FsTable columns={data.columns} rows={rows} />
        </>
      ) : null}
    </div>
  );
}

/* ── Profit or Loss Monthly ───────────────────────────────────────────── */

// Bespoke 3-row grouped header (ACCOUNT spanning all three rows, AMOUNT
// spanning both year-blocks, each year-block's actual period-end date
// spanning its MTD/YTD pair, then the MTD/YTD labels themselves) — black
// background with a white grid, matching the reference layout. Only the
// <thead> is custom; the body reuses FsRow so line/total/header row
// styling stays identical to every other Financial Statement table.
function PlMonthlyTable({ rows, dateLast, dateThis }) {
  const columnCount = 4; // MTD/YTD x 2 years, fixed for this report
  return (
    <div style={{ overflowX: "auto", borderRadius: 12, boxShadow: NEU.shadowOutSm }}>
      <table className="fs-table pl-monthly-table" style={{ width: "100%", fontSize: 12.5, minWidth: 480 + columnCount * 130 }}>
        <thead>
          <tr>
            <th rowSpan={3}>ACCOUNT</th>
            <th colSpan={columnCount}>AMOUNT</th>
          </tr>
          <tr>
            <th colSpan={2}>{dateLast}</th>
            <th colSpan={2}>{dateThis}</th>
          </tr>
          <tr>
            <th>MTD</th>
            <th>YTD</th>
            <th>MTD</th>
            <th>YTD</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => <FsRow key={ri} row={row} columnCount={columnCount} />)}
        </tbody>
      </table>
    </div>
  );
}

function ProfitLossMonthlyPanel({ periods }) {
  const latest = useMemo(() => latestActivePeriod(periods), [periods]);
  const [period, setPeriod] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => { if (latest && !period) setPeriod(latest.period_name); }, [latest]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildParams = useCallback(() => {
    const p = periods.find(x => x.period_name === period);
    if (!p) return null;
    const lastYearP = periods.find(x => x.period_year === p.period_year - 1 && x.period_num === p.period_num && x.adjustment_period_flag !== "Y");
    if (!lastYearP) return null;
    const ytdThis = periodsOfYear(periods, p.period_year).filter(x => x.period_num <= p.period_num).map(x => x.period_name);
    const ytdLast = periodsOfYear(periods, lastYearP.period_year).filter(x => x.period_num <= lastYearP.period_num).map(x => x.period_name);
    return { periodThis: p.period_name, ytdThis, periodLast: lastYearP.period_name, ytdLast, dateLabel: periodLabel(p) };
  }, [period, periods]);

  const load = useCallback(async () => {
    if (!period) return;
    const params = buildParams();
    if (!params) { setError("No corresponding period found in the prior year."); setData(null); return; }
    setLoading(true); setError(null);
    try {
      const res = await financialStatementApi.getProfitLossMonthly(params);
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [period, buildParams]);

  useEffect(() => { load(); }, [load]);

  const handleExport = () => {
    const params = buildParams();
    if (!params) return;
    downloadExport(
      () => financialStatementApi.exportProfitLossMonthly(params),
      `Profit_or_Loss_Monthly_${period}.xlsx`,
      setExporting, setError,
    );
  };

  // Actual period-end dates ("June 30, 2026") for the header's year-block
  // labels, matching the reference layout — periodLabel() alone only gives
  // "Jun 2026", not the full date.
  const headerDates = useMemo(() => {
    const fmt = (p) => p?.end_date
      ? new Date(p.end_date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
      : "";
    const p = periods.find(x => x.period_name === period);
    if (!p) return { this: "", last: "" };
    const lastYearP = periods.find(x => x.period_year === p.period_year - 1 && x.period_num === p.period_num && x.adjustment_period_flag !== "Y");
    return { this: fmt(p), last: fmt(lastYearP) };
  }, [period, periods]);

  const rows = useMemo(() => {
    if (!data) return [];
    const lines = (arr) => arr.map(r => ({ type: "line", level: 1, label: r.label, values: r.values }));
    return [
      { type: "header", level: 0, label: "NET SALES" },
      ...lines([...data.sales_lines, ...data.contra_lines]),
      { type: "total", level: 0, label: "TOTAL NET SALES", values: data.total_net_sales },
      { type: "header", level: 0, label: "COGS" },
      ...lines(data.cogs_lines),
      { type: "total", level: 0, label: "TOTAL COGS", values: data.total_cogs },
      { type: "total", level: 0, label: "GROSS PROFIT", values: data.gross_profit },
      { type: "header", level: 0, label: "EXPENSES" },
      ...lines(data.expense_lines),
      { type: "total", level: 0, label: "TOTAL EXPENSES", values: data.total_expenses },
      { type: "total", level: 0, label: "PROFIT (LOSS) BEFORE INTEREST & INCOME TAX", values: data.gross_profit.map((g, i) => g - data.total_expenses[i]) },
      { type: "header", level: 0, label: "OTHER INCOME / EXPENSES" },
      ...lines(data.other_lines),
      { type: "total", level: 0, label: "TOTAL OTHER INCOME (EXPENSE)", values: data.total_other },
      { type: "total", level: 0, label: "PROFIT (LOSS) BEFORE INCOME TAX", values: data.profit_before_tax },
      { type: "header", level: 0, label: "INCOME TAX" },
      ...lines(data.tax_lines),
      { type: "total", level: 0, label: "TOTAL INCOME TAX", values: data.total_tax },
      { type: "total", level: 0, label: "NET PROFIT (LOSS)", values: data.profit_after_tax },
      { type: "line", level: 1, label: "OTHER COMPREHENSIVE INCOME (LOSS)", values: data.oci },
      { type: "total", level: 0, label: "TOTAL COMPREHENSIVE INCOME (LOSS)", values: data.total_comprehensive },
    ];
  }, [data]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period</label>
          <select style={SELECT} value={period} onChange={e => setPeriod(e.target.value)}>
            {periods.filter(p => p.has_activity === "Y" && p.adjustment_period_flag !== "Y").map(p => (
              <option key={p.period_name} value={p.period_name}>{periodLabel(p)}</option>
            ))}
          </select>
        </div>
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data} style={BTN}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
      </div>

      {loading && !data ? (
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : error ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{error}</div>
      ) : data ? (
        <PlMonthlyTable rows={rows} dateLast={headerDates.last} dateThis={headerDates.this} />
      ) : null}
    </div>
  );
}

/* ── Root ─────────────────────────────────────────────────────────────── */

export default function FinancialStatement() {
  const [subTab, setSubTab] = useState("balance-sheet");
  const [periods, setPeriods] = useState([]);
  const [loadingPeriods, setLoadingPeriods] = useState(true);
  const [periodsError, setPeriodsError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await financialStatementApi.getPeriods();
        if (res.success) setPeriods(res.data);
        else setPeriodsError(res.error || "Failed to load GL periods");
      } catch (e) {
        setPeriodsError(e?.response?.data?.detail || e?.detail || String(e));
      } finally {
        setLoadingPeriods(false);
      }
    })();
  }, []);

  return (
    <div style={{ colorScheme: "light" }}>
      <div style={{ marginBottom: 4 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1e293b" }}>Financial Statement</h2>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
          Live dari Oracle EBS GL_BALANCES — format mengikuti FS_CKD OTTO 2015-2026_sent.xlsx.
          Breakdown Net Sales/COGS per sales channel (bukan per customer — lihat catatan di README).
        </p>
      </div>

      <div style={{ display: "flex", gap: 4, marginBottom: 16, marginTop: 14, borderBottom: "2px solid rgba(0,0,0,0.06)" }}>
        {FS_SUBTABS.map(t => {
          const active = subTab === t.id;
          return (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "9px 18px", border: "none", cursor: "pointer",
                background: "transparent",
                borderBottom: active ? "2px solid #10b981" : "2px solid transparent",
                marginBottom: -2,
                color: active ? "#10b981" : "#64748b",
                fontSize: 13, fontWeight: active ? 700 : 500,
                transition: "all 0.15s",
              }}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          );
        })}
      </div>

      {loadingPeriods ? (
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : periodsError ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{periodsError}</div>
      ) : (
        <>
          {subTab === "balance-sheet"        && <BalanceSheetPanel periods={periods} />}
          {subTab === "balance-sheet-detail" && <BalanceSheetPanel periods={periods} detail />}
          {subTab === "profit-loss"          && <ProfitLossPanel periods={periods} />}
          {subTab === "profit-loss-monthly"  && <ProfitLossMonthlyPanel periods={periods} />}
        </>
      )}
    </div>
  );
}
