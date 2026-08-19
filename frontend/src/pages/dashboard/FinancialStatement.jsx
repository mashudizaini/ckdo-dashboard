import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { FileBarChart2, TrendingUp, CalendarDays, Wallet, Loader2, RefreshCw, AlertTriangle, Download, Upload, Database, FileSpreadsheet, Square, Info, X } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { financialStatementApi } from "@/api/dashboard";

// Fixed categorical order (never cycled) — validated for CVD-safe adjacent
// pairs, see the dataviz skill's reference palette. Gross Profit / Profit
// (Loss) Before Tax / Total Comprehensive Income always map to these three
// slots in this order.
const CHART_COLORS = { grossProfit: "#2a78d6", pbt: "#eb6834", tci: "#1baf7a" };

// A stable empty-array reference for `x || []`-style fallbacks used inside
// useMemo/useCallback dependency arrays — `[]` written inline creates a
// brand new array (new identity) on every render even when nothing
// meaningful changed, which useMemo/useEffect treat as "changed" and
// recompute/refire for. That's what caused BalanceSheetPanel's infinite
// load loop (see excelYears below): every load() call's own re-render
// produced a fresh empty array, which cascaded into rangePeriods ->
// periodList -> load being considered "new" again, which fired another
// load() before the previous one had even settled — read by users as the
// Refresh spinner never stopping and the panel visibly flickering.
const EMPTY_ARRAY = Object.freeze([]);

// Oracle GL_BALANCES as a Financial Statement data source is temporarily
// disabled (2026-08-18, user request) — every report defaults to and is
// locked onto the Excel source until this is flipped back on. Balance
// Sheet's inline natural-account expansion is unaffected: it always
// queries Oracle directly, independent of this toggle.
const SHOW_ORACLE_SOURCE = false;

// "Today", computed once at module load — anchors the Period Type
// defaults (current year / current year - 1) and the current-year
// monthly-breakdown expansion below.
const NOW = new Date();
const CURRENT_YEAR = NOW.getFullYear();
const CURRENT_MONTH_IDX = NOW.getMonth(); // 0 = Jan

const NEU = {
  bg:          "#f1f5f9",
  shadowOut:   "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  shadowOutSm: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  shadowIn:    "inset 0 2px 5px rgba(15,23,42,0.09)",
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
  { id: "profit-loss",          label: "Profit or Loss",        icon: TrendingUp },
  { id: "profit-loss-monthly",  label: "Profit or Loss Monthly", icon: CalendarDays },
  { id: "cash-flow",            label: "Cash Flow",             icon: Wallet },
];

// Balance Sheet Detail is no longer a standalone tab — it's reached by
// clicking an individual account line (e.g. CASH & CASH EQUIVALENTS)
// inside Balance Sheet, which drills into that line's natural accounts
// (still tagged with the group it belongs to, for the Oracle query).

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
function FsTable({ columns, rows, checkDiff, growthMode = "none", onLineClick, expandedLines }) {
  const growthHeaders = growthMode === "diff" ? ["Growth", "Growth %"] : growthMode === "cagr" ? ["CAGR %"] : [];
  const allColumns = [...columns, ...growthHeaders];
  return (
    <div>
      {/* .fs-table-scroll caps the table's own height and scrolls both
          axes inside itself (index.css), instead of the old plain
          overflow-x:auto div — on a tall table (Balance Sheet Detail,
          Cash Flow) that left the horizontal scrollbar sitting below the
          last row, reachable only after scrolling the whole page down
          first. ACCOUNT (first column) and the header row are pinned via
          position:sticky (also index.css) so they stay in view while
          scrolling either direction, Excel-frozen-pane style. */}
      <div className="fs-table-scroll" style={{ borderRadius: 12, boxShadow: NEU.shadowOutSm }}>
        <table className="fs-table" style={{ width: "100%", fontSize: 12.5, minWidth: 480 + allColumns.length * 130 }}>
          <thead>
            <tr>
              <th>ACCOUNT</th>
              {allColumns.map((c, i) => <th key={i} style={{ whiteSpace: "nowrap" }}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <FsRow key={ri} row={row} columnCount={allColumns.length} growthMode={growthMode}
                onLineClick={onLineClick} expandedLines={expandedLines} />
            ))}
          </tbody>
        </table>
      </div>
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

function FsRow({ row, columnCount = 0, growthMode = "none", onLineClick, expandedLines }) {
  const level = Math.min(row.level || 0, 3);
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
  // Same fix applies to a placeholder "detail-line" row (Loading…/Error/No
  // accounts found) — it has no row.values at all (nothing to show per
  // period yet), so it renders as a full-width message row instead of
  // leaving misaligned/missing cells under the value columns.
  if (row.type === "detail-line" && !row.values) {
    return (
      <tr data-type="detail-line">
        <td data-lvl={level}>{row.label}</td>
        {Array.from({ length: columnCount }, (_, ci) => <td key={ci} />)}
      </tr>
    );
  }
  const values = row.values || [];
  const g = row.growth;
  // Only individual account lines (CASH & CASH EQUIVALENTS, ACCOUNT
  // RECEIVABLES, ...) expand into their natural-account detail — TOTAL
  // rows and section headers stay inert, and so do the spliced-in
  // "detail-line" rows themselves (no row.group). `row.group` is only set
  // by BalanceSheetPanel's summary rows, so this is a no-op for every
  // other FsTable caller (Profit or Loss, etc.).
  const clickable = row.type === "line" && !!row.group && !!onLineClick;
  const expanded = clickable && expandedLines?.has(`${row.group}|${row.label}`);
  return (
    <tr
      data-type={row.type}
      onClick={clickable ? () => onLineClick(row.group, row.label) : undefined}
      style={clickable ? { cursor: "pointer" } : undefined}
      title={clickable ? (expanded ? `Hide ${row.label} account detail` : `Show ${row.label} account detail`) : undefined}
    >
      <td data-lvl={level}>{clickable ? (expanded ? "▾ " : "▸ ") : ""}{row.label}</td>
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

/* ── Data source toggle + Excel upload (shared: Balance Sheet, Profit or
   Loss, Profit or Loss Monthly) ─────────────────────────────────────────
   Transition period from manual Excel reporting to Oracle: each of the 3
   reports can be switched between the live Oracle query and whatever was
   last uploaded for that report_type. reportType matches the backend's
   report_type enum: balance_sheet | profit_loss | profit_loss_monthly. */

// Expected Excel format per report_type — kept in sync by hand against the
// parser (financial_statement_upload_service.py), since that's the single
// source of truth for what it actually reads. If the parser's row-label
// matching ever changes, update this alongside it.
const FS_FORMAT_GUIDE = {
  balance_sheet: {
    sheetName: "Balance sheet",
    notes: [
      "Row 6: one column per year, header \"FY 2022\", \"FY 2023\", etc.",
      "Rows 1–5 (column A, optional): the latest year's snapshot date, e.g. \"June 30, 2026\" — if left blank, the last column is displayed as \"Dec {year}\".",
      "Row 7 onward: one row per account — the first column containing text becomes the row label, the year columns hold numbers.",
      "The row names below MUST match exactly (not case-sensitive) to be automatically placed in the right section — rows with any other name are still saved but shown as \"unmapped\".",
    ],
    sections: [
      { label: "CURRENT ASSETS", items: ["CASH & CASH EQUIVALENTS", "ACCOUNT RECEIVABLES", "INVENTORY", "PREPAIDS", "OTHER CURRENT ASSETS", "ACCRUED INCOME"] },
      { label: "NON CURRENT ASSETS", items: ["PROPERTY, PLANT AND EQUIPMENT", "OTHER NON - CURRENT ASSETS", "INTANGIBLE ASSET"] },
      { label: "CURRENT LIABILITIES", items: ["SHORT TERM BORROWINGS", "ACCOUNT PAYABLES", "TAX PAYABLES", "ACCRUED EXPENSES", "CURRENT PORTION OF LONG TERM BORROWINGS", "CURRENT LEASE LIABILITIES", "OTHER CURRENT LIABILITIES"] },
      { label: "NON CURRENT LIABILITIES", items: ["LTB-LOANS", "ESTIMATED LIABILITIES FOR EMPLOYEES", "NON-CURRENT SALES RETURN ALLOWANCE", "LONG-TERM LEASE LIABILITIES"] },
      { label: "EQUITY", items: ["CAPITAL STOCK", "RETAINED EARNINGS - PRIOR YEAR", "RETAINED EARNINGS - CURRENT YEAR", "OTHER COMPREHENSIVE INCOME - PRIOR YEAR", "OTHER COMPREHENSIVE INCOME - CURRENT YEAR"] },
    ],
    totals: ["TOTAL CURRENT ASSETS", "TOTAL NON CURRENT ASSETS", "TOTAL ASSETS", "TOTAL CURRENT LIABILITIES", "TOTAL NONCURRENT LIABILITIES", "TOTAL LIABILITIES", "TOTAL EQUITY", "TOTAL LIABILITIES AND EQUITY"],
    totalsNote: "The TOTAL rows above must exist with exactly this name — used directly as the total value (not recomputed).",
  },
  profit_loss: {
    sheetName: "Profit or loss",
    notes: [
      "Row 6: one column per year, header \"FY 2022\", \"FY 2023\", etc.",
      "The rows between a section header and its TOTAL row are free-form (account/customer names as the company's own data has them) — all of them are carried through as-is.",
      "The following section header rows are REQUIRED, exactly as written: NET SALES, COGS, EXPENSES, OTHER INCOME / EXPENSES, INCOME TAX.",
    ],
    sections: [],
    totals: ["TOTAL NET SALES", "TOTAL COGS", "GROSS PROFIT", "TOTAL EXPENSES", "TOTAL OTHER INCOME (EXPENSES)", "PROFIT (LOSS) BEFORE TAX", "TOTAL INCOME TAX BENEFIT (EXPENSE)", "PROFIT (LOSS) AFTER TAX", "OTHER COMPREHENSIVE INCOME", "TOTAL COMPREHENSIVE INCOME (LOSS) FOR THE YEAR"],
    totalsNote: "The TOTAL rows above must exist with exactly this name.",
  },
  profit_loss_monthly: {
    sheetName: "PL_monthly",
    notes: [
      "Row 7: 2 adjacent date labels — last year then this year, e.g. \"June 30, 2025\" then \"June 30, 2026\". Each is followed by 2 columns (MTD, YTD).",
      "Row 8: MTD/YTD sub-labels in those same 4 columns.",
      "Same section headers as the annual \"Profit or loss\" sheet: NET SALES, COGS, EXPENSES, OTHER INCOME / EXPENSES, INCOME TAX.",
      "The TOTAL row names are DIFFERENT from the annual sheet — see the exact wording below.",
    ],
    sections: [],
    totals: ["TOTAL NET SALES", "TOTAL COGS", "GROSS PROFIT", "TOTAL EXPENSES", "TOTAL OTHER INCOME (EXPENSE)", "PROFIT (LOSS) BEFORE INCOME TAX", "TOTAL INCOME TAX", "NET PROFIT (LOSS)", "OTHER COMPREHENSIVE INCOME (LOSS)", "TOTAL COMPREHENSIVE INCOME (LOSS) FOR THE YEAR"],
    totalsNote: "The TOTAL rows above must exist with exactly this name — different from the annual \"Profit or loss\" sheet (e.g. \"TOTAL INCOME TAX\", not \"TOTAL INCOME TAX BENEFIT (EXPENSE)\").",
  },
  cash_flow: {
    sheetName: "Cashflow",
    notes: [
      "Row 6: one column per year, header as a bare year number (2022, not \"FY 2022\").",
      "The most recent year may instead be split into one column per posted month, with the month name (Jan, Feb, ...) in row 8 of those columns — used for a year that's still in progress.",
      "Column B holds the 5 trunk rows (Beginning Balance, Cash In, Cash Out, Net Cash Flow, Ending Balance). Column C holds the Operating/Investing/Financing subtotal under Cash In and Cash Out. Column D holds the free-form line items under each — all carried through exactly as found, in file order.",
      "Every row is read from row 9 onward — no fixed row-name list to match against.",
    ],
    sections: [],
    totals: ["Beginning Balance", "Cash In", "Cash Out", "Net Cash Flow", "Ending Balance"],
    totalsNote: "These 5 rows (column B) and the Operating/Investing/Financing subtotal rows (column C) are treated as bold total rows — everything in column D is a plain line item.",
  },
};

function FormatGuideModal({ reportType, onClose }) {
  const guide = FS_FORMAT_GUIDE[reportType];
  if (!guide) return null;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.4)" }} onClick={onClose}>
      <div style={{ width: "100%", maxWidth: 560, maxHeight: "85vh", overflow: "auto", borderRadius: 14, background: "#ffffff", boxShadow: "0 20px 40px rgba(15,23,42,0.2)" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>Expected Excel Format</h3>
            <p style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>Sheet name: <code style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: 4 }}>{guide.sheetName}</code></p>
          </div>
          <button onClick={onClose} style={{ color: "#94a3b8", border: "none", background: "none", cursor: "pointer" }}><X size={18} /></button>
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
            {guide.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
          {guide.sections.map(sec => (
            <div key={sec.label}>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#1F4E78", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.3 }}>{sec.label}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {sec.items.map(it => (
                  <span key={it} style={{ fontSize: 11, background: "#f1f5f9", color: "#334155", padding: "3px 8px", borderRadius: 6, fontFamily: "monospace" }}>{it}</span>
                ))}
              </div>
            </div>
          ))}
          <div>
            <p style={{ fontSize: 11, fontWeight: 700, color: "#1F4E78", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.3 }}>TOTAL rows (required)</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {guide.totals.map(it => (
                <span key={it} style={{ fontSize: 11, background: "#fef3c7", color: "#92400e", padding: "3px 8px", borderRadius: 6, fontFamily: "monospace" }}>{it}</span>
              ))}
            </div>
            {guide.totalsNote && <p style={{ fontSize: 11, color: "#64748b", marginTop: 6 }}>{guide.totalsNote}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

function fmtUploadTs(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function FsSourceControl({ reportType, source, setSource, onStatus, onUploaded }) {
  const [status, setStatus] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);
  const [showFormatGuide, setShowFormatGuide] = useState(false);
  const fileRef = useRef(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await financialStatementApi.getUploadStatus(reportType);
      const data = res.success ? res.data : null;
      setStatus(data);
      onStatus?.(data);
    } catch (e) { /* upload status is informational only */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportType]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true); setErr(null);
    try {
      const res = await financialStatementApi.uploadExcel(reportType, file);
      if (res.success) {
        await loadStatus();
        onUploaded?.();
      } else {
        setErr(res.error || "Upload failed");
      }
    } catch (e2) {
      setErr(e2?.response?.data?.detail || e2?.detail || String(e2));
    } finally {
      setUploading(false);
    }
  };

  const toggleBtn = (active) => ({
    padding: "7px 13px", border: "none", fontSize: 12, fontWeight: 600, cursor: "pointer",
    display: "flex", alignItems: "center", gap: 5,
    background: active ? "#1F4E78" : "transparent",
    color: active ? "#ffffff" : "#64748b",
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      {/* Oracle data source temporarily hidden (2026-08-18, user request) —
          flip SHOW_ORACLE_SOURCE back to true to restore the toggle. The
          "source" state/prop plumbing everywhere else is untouched so this
          re-enables cleanly; only the switch itself is hidden. */}
      {SHOW_ORACLE_SOURCE && (
        <div style={{ display: "flex", borderRadius: 9, overflow: "hidden", boxShadow: NEU.shadowIn }}>
          <button onClick={() => setSource("oracle")} style={toggleBtn(source === "oracle")}><Database size={12} /> Oracle</button>
          <button onClick={() => setSource("excel")} style={toggleBtn(source === "excel")}><FileSpreadsheet size={12} /> Excel</button>
        </div>
      )}
      <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleFile} />
      <button onClick={() => fileRef.current?.click()} disabled={uploading} style={BTN}>
        {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Upload Excel
      </button>
      <button onClick={() => setShowFormatGuide(true)} style={{ ...BTN, padding: "7px 9px" }} title="View the expected Excel format">
        <Info size={13} />
      </button>
      {showFormatGuide && <FormatGuideModal reportType={reportType} onClose={() => setShowFormatGuide(false)} />}
      {status ? (
        <span style={{ fontSize: 11, color: "#64748b" }}>
          Last uploaded: {status.original_filename} · {status.uploaded_by} · {fmtUploadTs(status.uploaded_at)}
        </span>
      ) : (
        <span style={{ fontSize: 11, color: "#94a3b8" }}>No Excel data uploaded yet</span>
      )}
      {err && (
        <span style={{ fontSize: 11, color: "#dc2626" }}>
          {err} — <button onClick={() => setShowFormatGuide(true)} style={{ border: "none", background: "none", color: "#dc2626", textDecoration: "underline", cursor: "pointer", fontSize: 11, padding: 0 }}>view expected format</button>
        </span>
      )}
    </div>
  );
}

/* ── Balance Sheet ────────────────────────────────────────────────────── */

// Snaps a month state to the latest month that actually has posted activity
// in `year`, if the current value isn't one of them (e.g. the year changed
// to one with fewer/different posted months). Shared by Period From and
// Period To's month pickers.
function useMonthSnap(source, periods, year, month, setMonth) {
  useEffect(() => {
    if (source !== "oracle" || !year) return;
    const opts = monthOptionsForYear(periods, year);
    if (opts.length && !opts.includes(month)) setMonth(opts[opts.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, periods, source]);
}

function BalanceSheetPanel({ periods }) {
  const years = useMemo(() => fiscalYears(periods), [periods]);
  const latest = useMemo(() => latestActivePeriod(periods), [periods]);

  // Data source toggle — Oracle (live GL_BALANCES) vs the last uploaded
  // Excel snapshot. Oracle is currently hidden (SHOW_ORACLE_SOURCE), so
  // this stays "excel" in practice, but the branching is kept intact for
  // when it's switched back on.
  const [source, setSource] = useState(SHOW_ORACLE_SOURCE ? "oracle" : "excel");
  const [excelStatus, setExcelStatus] = useState(null);
  const excelYears = excelStatus?.years || EMPTY_ARRAY;
  const pickerYears = source === "excel" ? excelYears : years;

  // Period From / Period To are now the only period controls (the old
  // separate "Single Period" picker was folded in: Period To plays that
  // role for the most recent/rightmost column). Each carries its own
  // month + year — Oracle mode only; Excel snapshots are year-only so the
  // month selects don't render in that mode.
  const [fromMonth, setFromMonth] = useState("DEC");
  const [fromYear, setFromYear] = useState("");
  const [toMonth, setToMonth] = useState("DEC");
  const [toYear, setToYear] = useState("");

  // Period Type — "multi" (default): Period From/To both active, a real
  // range. "single": Period To is disabled and ignored entirely; Period
  // From alone drives a 1-column view.
  const [periodType, setPeriodType] = useState("multi");

  // Show Jan..current-month as separate columns wherever the current
  // year appears in the range, instead of one single column for it —
  // e.g. if today is in July, the current year expands into Jan-Jul.
  // Oracle mode only (Excel snapshots have no month granularity to
  // expand into). Defaults on.
  const [showCurrentYearMonthly, setShowCurrentYearMonthly] = useState(true);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  // Account Group — narrows the Oracle query to one section instead of
  // always scanning Assets+Liabilities+Equity together, which is what made
  // a wide Period From/To range (e.g. 2022-2026) slow enough to look stuck:
  // each extra column was a full extra sequential Oracle round-trip just
  // for the Equity section's retained-earnings figure. "" = All.
  const [accountGroup, setAccountGroup] = useState("");

  // Natural-account detail for a summary line (e.g. "CASH & CASH
  // EQUIVALENTS") now expands INLINE right below the clicked row instead
  // of navigating to a separate "Balance Sheet Detail" screen — click
  // again to collapse. expandedLines holds "GROUP|Label" keys currently
  // expanded; groupDetail caches the (unfiltered) natural-account rows
  // for a whole account group, fetched once and reused across every
  // expanded line within that group (mirrors how the old detail view
  // fetched the whole group then filtered client-side to one line).
  const [expandedLines, setExpandedLines] = useState(() => new Set());
  const [groupDetail, setGroupDetail] = useState({}); // { [group]: { loading, error, accounts, periodKey } }
  const detailFetchKeys = useRef(new Set()); // in-flight/cached "group|periodKey" — de-dupes fetches

  // Default on mount — anchored to today's real calendar year, not
  // whatever year the data happens to cover: Period From = current year
  // - 1, Period To = current year (Multi Period), or just Period From =
  // current year - 1 (Single Period, Period To disabled).
  // setPeriodTypeWithDefaults below re-applies the same defaults whenever
  // Period Type is switched, since this guarded effect (only filling in
  // blank values) won't re-fire just because periodType changed if
  // fromYear/toYear are already set from before.
  useEffect(() => {
    if (!fromYear) {
      setFromYear(CURRENT_YEAR - 1);
      setFromMonth("DEC");
    }
    if (periodType === "multi" && !toYear) {
      setToYear(CURRENT_YEAR);
      setToMonth(source === "oracle" && latest ? MONTHS[latest.period_num - 1] : "DEC");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodType]);

  const setPeriodTypeWithDefaults = (val) => {
    setPeriodType(val);
    setFromYear(CURRENT_YEAR - 1);
    setFromMonth("DEC");
    if (val === "multi") {
      setToYear(CURRENT_YEAR);
      setToMonth(source === "oracle" && latest ? MONTHS[latest.period_num - 1] : "DEC");
    }
  };

  useMonthSnap(source, periods, fromYear, fromMonth, setFromMonth);
  useMonthSnap(source, periods, toYear, toMonth, setToMonth);

  // Single Period ignores Period To entirely — Period From is the only
  // (and therefore also the "to") endpoint, producing exactly 1 column
  // (subject to the current-year expansion below).
  const effToYear = periodType === "single" ? fromYear : toYear;
  const effToMonth = periodType === "single" ? fromMonth : toMonth;

  // Chronological period list, oldest → newest, left to right (this is the
  // ordering Balance Sheet Detail already had — now shared by construction
  // since both views run through this exact same loop). Period From and
  // Period To each resolve using their own month; any year strictly
  // between them is always its fiscal year-end (December) snapshot. In
  // excel mode there's no month component — each year is either present in
  // the uploaded file or skipped. Wherever the real current year lands in
  // the range, showCurrentYearMonthly (Oracle only) expands it into one
  // column per posted month (Jan..now) instead of a single column.
  const periodList = useMemo(() => {
    if (!fromYear || !effToYear || fromYear > effToYear) return [];
    const list = [];
    for (let y = fromYear; y <= effToYear; y++) {
      if (source === "oracle" && showCurrentYearMonthly && y === CURRENT_YEAR) {
        for (let m = 0; m <= CURRENT_MONTH_IDX; m++) {
          const pn = periodNameForMonthYear(periods, MONTHS[m], y);
          if (pn != null) list.push(pn);
        }
        continue;
      }
      let pn;
      if (source === "excel") {
        pn = pickerYears.includes(y) ? y : null;
      } else if (y === effToYear) {
        pn = periodNameForMonthYear(periods, effToMonth, y);
      } else if (y === fromYear) {
        pn = periodNameForMonthYear(periods, fromMonth, y);
      } else {
        pn = periodNameForMonthYear(periods, "DEC", y);
      }
      if (pn != null) list.push(pn);
    }
    return list;
  }, [source, periods, fromYear, effToYear, fromMonth, effToMonth, pickerYears, showCurrentYearMonthly]);

  // Natural-account detail always queries Oracle directly (no Excel
  // equivalent — the manual file has no natural-account granularity), so
  // when the summary is in excel mode its bare years get resolved to their
  // Oracle December period_name equivalents before an inline expansion can
  // fetch them. Years with no matching Oracle period (e.g. history older
  // than Oracle's GL calendar) are simply dropped.
  const detailPeriodList = useMemo(() => {
    if (source !== "excel") return periodList;
    return periodList.map(y => periodNameForMonthYear(periods, "DEC", y)).filter(Boolean);
  }, [periodList, source, periods]);

  // Any expanded line's cached detail is only valid for the exact period
  // set it was fetched for — collapse everything and drop the cache
  // whenever Period From/To (or the data source) changes, so a stale
  // expansion never shows the wrong period's numbers.
  useEffect(() => {
    setExpandedLines(new Set());
    setGroupDetail({});
    detailFetchKeys.current = new Set();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detailPeriodList.join(","), source]);

  // Growth-rate mode: exactly 2 columns -> simple diff & %; more than 2
  // (a multi-year Period From/To range) -> CAGR spanning Period From to
  // Period To.
  const growthMode = periodList.length === 2 ? "diff" : periodList.length > 2 ? "cagr" : "none";
  const cagrYears = growthMode === "cagr" ? effToYear - fromYear : 0;

  // Tracks the in-flight request so a newer one can cancel a still-running
  // older one — without this, a slow response arriving late (e.g. after
  // the user already changed a filter and a second request went out) could
  // overwrite fresher data or flip loading back off/on out of order, which
  // is what the spinner "never settling" / the panel flickering looks like
  // from the outside. Only the request that's still current when it
  // resolves is allowed to touch loading/data state.
  const abortRef = useRef(null);

  const load = useCallback(async () => {
    if (!periodList.length) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true); setError(null);
    try {
      const res = await financialStatementApi.getBalanceSheet(periodList, source, source === "oracle" ? accountGroup : "", controller.signal);
      if (abortRef.current !== controller) return; // superseded — a newer request is already in charge
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      if (e?.code === "ERR_CANCELED" || e?.name === "CanceledError") return; // aborted — not a real error
      if (abortRef.current !== controller) return;
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally {
      if (abortRef.current === controller) { setLoading(false); abortRef.current = null; }
    }
  }, [periodList, source, accountGroup]);

  const stop = useCallback(() => { abortRef.current?.abort(); setLoading(false); }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => abortRef.current?.abort(), []); // cancel any pending request on unmount

  // Backend supplies pre-formatted column labels for both sources (GL
  // period_display_label for oracle, "Dec YYYY" / the file's own as-of
  // date for excel) — no need to resolve against the GL periods list here.
  const columnLabels = data?.column_labels || [];

  const handleExport = () => {
    const label = columnLabels[columnLabels.length - 1] || "";
    downloadExport(
      () => financialStatementApi.exportBalanceSheet(periodList, label),
      `Balance_Sheet_${fromYear}-${effToYear}.xlsx`,
      setExporting, setError,
    );
  };

  // Fetches (once, cached per group+period-set) every natural-account row
  // for a whole Balance Sheet section — reused across every expanded line
  // within that group instead of one fetch per line.
  const ensureGroupDetail = useCallback((group) => {
    const periodKey = detailPeriodList.join(",");
    const cacheKey = `${group}|${periodKey}`;
    if (detailFetchKeys.current.has(cacheKey)) return;
    detailFetchKeys.current.add(cacheKey);

    if (!detailPeriodList.length) {
      setGroupDetail(prev => ({ ...prev, [group]: { loading: false, error: "No matching Oracle GL period for the selected years.", accounts: [], periodKey } }));
      return;
    }
    setGroupDetail(prev => ({ ...prev, [group]: { loading: true, error: null, accounts: null, periodKey } }));
    financialStatementApi.getBalanceSheetDetail(detailPeriodList, group)
      .then(res => {
        setGroupDetail(prev => ({
          ...prev,
          [group]: res.success
            ? { loading: false, error: null, accounts: res.accounts || [], periodKey }
            : { loading: false, error: res.error || "Failed to load", accounts: [], periodKey },
        }));
      })
      .catch(e => {
        detailFetchKeys.current.delete(cacheKey); // allow retry on next click
        setGroupDetail(prev => ({ ...prev, [group]: { loading: false, error: e?.response?.data?.detail || String(e), accounts: [], periodKey } }));
      });
  }, [detailPeriodList]);

  const toggleLineDetail = useCallback((group, label) => {
    const key = `${group}|${label}`;
    setExpandedLines(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
        ensureGroupDetail(group);
      }
      return next;
    });
  }, [ensureGroupDetail]);

  const withGrowth = useCallback(
    (row) => ({ ...row, growth: computeGrowth(row.values, growthMode, cagrYears) }),
    [growthMode, cagrYears],
  );

  // When Account Group narrows the query, the backend zeroes out the
  // sections it didn't fetch rather than omitting them (keeps the export
  // builder's expected shape intact) — filter which blocks actually render
  // here instead, using the same accountGroup the request was made with.
  const showAssets = !accountGroup || accountGroup === "ASSETS";
  const showLiabilities = !accountGroup || accountGroup === "LIABILITIES";
  const showEquity = !accountGroup || accountGroup === "EQUITY";

  const rows = useMemo(() => {
    if (!data) return [];
    // A viewMode flip used to make `data` transiently the wrong shape
    // here (crash-to-blank-screen); that risk no longer exists since
    // there's only one view now, but the shape guard stays as cheap
    // insurance against a still-loading/empty response.
    if (!Array.isArray(data.current_assets)) return [];
    // Each account line is tagged with its group (ASSETS/LIABILITIES/
    // EQUITY) so clicking it can both identify which cached group-detail
    // to expand and which line_item within it to show. When a line is
    // expanded, its natural-account rows are spliced in directly after
    // it (detail-line rows, indented one level deeper, not themselves
    // clickable) instead of navigating to a separate screen.
    const lines = (arr, group) => arr.flatMap(r => {
      const line = withGrowth({ type: "line", level: 2, label: r.label, values: r.values, group });
      const key = `${group}|${r.label}`;
      if (!expandedLines.has(key)) return [line];
      const gd = groupDetail[group];
      let detailRows;
      if (gd?.loading) {
        detailRows = [{ type: "detail-line", level: 3, label: "Loading…" }];
      } else if (gd?.error) {
        detailRows = [{ type: "detail-line", level: 3, label: `Error: ${gd.error}` }];
      } else {
        const accs = (gd?.accounts || []).filter(a => a.line_item === r.label);
        detailRows = accs.length
          ? accs.map(a => ({ type: "detail-line", level: 3, label: `${a.account_code} — ${a.account_desc || a.line_item}`, values: a.values }))
          : [{ type: "detail-line", level: 3, label: "No accounts found" }];
      }
      return [line, ...detailRows];
    });
    return [
      ...(showAssets ? [
        { type: "header", level: 0, label: "ASSETS" },
        { type: "header", level: 1, label: "CURRENT ASSETS" },
        ...lines(data.current_assets, "ASSETS"),
        withGrowth({ type: "total", level: 1, label: "TOTAL CURRENT ASSETS", values: data.total_current_assets }),
        { type: "header", level: 1, label: "NON CURRENT ASSET" },
        ...lines(data.noncurrent_assets, "ASSETS"),
        withGrowth({ type: "total", level: 1, label: "TOTAL NON CURRENT ASSETS", values: data.total_noncurrent_assets }),
        withGrowth({ type: "total", level: 0, label: "TOTAL ASSETS", values: data.total_assets }),
      ] : []),
      ...(showLiabilities ? [
        { type: "header", level: 0, label: "LIABILITIES" },
        { type: "header", level: 1, label: "CURRENT LIABILITIES" },
        ...lines(data.current_liabilities, "LIABILITIES"),
        withGrowth({ type: "total", level: 1, label: "TOTAL CURRENT LIABILITIES", values: data.total_current_liabilities }),
        { type: "header", level: 1, label: "NONCURRENT LIABILITIES" },
        ...lines(data.noncurrent_liabilities, "LIABILITIES"),
        withGrowth({ type: "total", level: 1, label: "TOTAL NONCURRENT LIABILITIES", values: data.total_noncurrent_liabilities }),
        withGrowth({ type: "total", level: 0, label: "TOTAL  LIABILITIES", values: data.total_liabilities }),
      ] : []),
      ...(showEquity ? [
        { type: "header", level: 0, label: "EQUITY" },
        // Only the clickable "line" rows get bumped up to level 1 (Equity
        // has no CURRENT/NON-CURRENT sub-header, unlike Assets/
        // Liabilities) — a spliced-in "detail-line" row must keep its own
        // deeper level so it still reads as nested under its parent.
        ...lines(data.equity, "EQUITY").map(r => (r.type === "line" ? { ...r, level: 1 } : r)),
        withGrowth({ type: "total", level: 0, label: "TOTAL  EQUITY", values: data.total_equity }),
      ] : []),
      ...(showAssets && showLiabilities && showEquity ? [
        withGrowth({ type: "total", level: 0, label: "TOTAL  LIABILITIES AND EQUITY", values: data.total_liabilities_and_equity }),
      ] : []),
    ];
  }, [data, expandedLines, groupDetail, withGrowth, showAssets, showLiabilities, showEquity]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <FsSourceControl
        reportType="balance_sheet" source={source} setSource={setSource}
        onStatus={setExcelStatus} onUploaded={load}
      />
      {source === "oracle" && (
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#334155", cursor: "pointer" }}>
          <input type="checkbox" checked={showCurrentYearMonthly} onChange={e => setShowCurrentYearMonthly(e.target.checked)} />
          Show {CURRENT_YEAR} by month (Jan–{MONTH_LABEL[MONTHS[CURRENT_MONTH_IDX]]}) instead of a single column
        </label>
      )}
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period Type</label>
          <select style={SELECT} value={periodType} onChange={e => setPeriodTypeWithDefaults(e.target.value)}>
            <option value="multi">Multi Period</option>
            <option value="single">Single Period</option>
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period From</label>
          <div style={{ display: "flex", gap: 6 }}>
            {source === "oracle" && (
              <select style={SELECT} value={fromMonth} onChange={e => setFromMonth(e.target.value)}>
                {monthOptionsForYear(periods, fromYear).map(m => <option key={m} value={m}>{MONTH_LABEL[m]}</option>)}
              </select>
            )}
            <select style={SELECT} value={fromYear} onChange={e => setFromYear(e.target.value ? Number(e.target.value) : "")}>
              {pickerYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period To</label>
          <div style={{ display: "flex", gap: 6 }}>
            {source === "oracle" && (
              <select style={SELECT} value={toMonth} onChange={e => setToMonth(e.target.value)} disabled={periodType === "single"}>
                {monthOptionsForYear(periods, toYear).map(m => <option key={m} value={m}>{MONTH_LABEL[m]}</option>)}
              </select>
            )}
            <select style={SELECT} value={toYear} onChange={e => setToYear(e.target.value ? Number(e.target.value) : "")} disabled={periodType === "single"}>
              {pickerYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>
        {source === "oracle" && (
          <div>
            <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Account Group</label>
            <select style={SELECT} value={accountGroup} onChange={e => setAccountGroup(e.target.value)}
              title="Narrow the query to one section — faster, especially for a wide Period From/To range">
              <option value="">All</option>
              <option value="ASSETS">Assets</option>
              <option value="LIABILITIES">Liabilities</option>
              <option value="EQUITY">Equity</option>
            </select>
          </div>
        )}
        {loading ? (
          <button onClick={stop} style={{ ...BTN, color: "#dc2626" }} title="Cancel the in-progress request">
            <Square size={13} /> Stop
          </button>
        ) : (
          <button onClick={load} style={BTN}>
            <RefreshCw size={13} /> Refresh
          </button>
        )}
        <button onClick={handleExport} disabled={exporting || !data || source === "excel"} style={BTN}
          title={source === "excel" ? "Excel export isn't supported for the Excel data source" : undefined}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
        {data?.unmapped_accounts?.length > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#d97706" }}>
            <AlertTriangle size={13} /> {data.unmapped_accounts.length} unmapped account(s): {data.unmapped_accounts.join(", ")}
          </span>
        )}
      </div>

      {!loading && growthMode === "cagr" && columnLabels.length > 1 && (
        <div style={{ fontSize: 11, color: "#64748b" }}>
          Comparing {periodList.length} years ({columnLabels[0]} → {columnLabels[columnLabels.length - 1]}) — the growth column uses CAGR ({cagrYears} years).
        </div>
      )}

      {fromYear && effToYear && fromYear > effToYear ? (
        <div style={{ padding: 16, fontSize: 12, color: "#dc2626" }}>Period From must not be after Period To.</div>
      ) : loading ? (
        // Shown for every load (not just the first one, before `data`
        // exists) — the table only ever appears once a request finishes,
        // instead of leaving a stale table on screen while new columns/
        // filters are still loading underneath it (mismatched headers vs.
        // still-old values is what reads as the screen "blinking").
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}>
          <Loader2 size={20} className="animate-spin" />
          <p style={{ fontSize: 12, marginTop: 10 }}>Loading data — may take a few seconds for a wide year range.</p>
        </div>
      ) : error ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{error}</div>
      ) : data ? (
        <FsTable
          columns={columnLabels} rows={rows}
          checkDiff={!accountGroup ? data.check_diff : null}
          growthMode={growthMode}
          onLineClick={toggleLineDetail}
          expandedLines={expandedLines}
        />
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

  // Data source toggle — Oracle (live GL_BALANCES YTD) vs the last
  // uploaded Excel snapshot (the "Profit or loss" sheet). Oracle is
  // currently hidden (SHOW_ORACLE_SOURCE) — stays "excel" in practice.
  const [source, setSource] = useState(SHOW_ORACLE_SOURCE ? "oracle" : "excel");
  const [excelStatus, setExcelStatus] = useState(null);
  const pickerYears = source === "excel" ? (excelStatus?.years || EMPTY_ARRAY) : years;

  // Period From / Period To — the only period controls (the old separate
  // single "Period" picker was folded in: Period To plays that role as
  // the rightmost/most-recent column). Same year on both = 1 column.
  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  // Default (and re-default on source switch) — years[] sorts descending
  // so years[0] is the latest either way.
  useEffect(() => {
    if (!pickerYears.length) return;
    const latestYear = source === "excel" ? Math.max(...pickerYears) : pickerYears[0];
    if (!toYear || !pickerYears.includes(toYear)) setToYear(latestYear);
    if (!fromYear || !pickerYears.includes(fromYear)) {
      const prevYear = latestYear - 1;
      setFromYear(pickerYears.includes(prevYear) ? prevYear : latestYear);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, pickerYears.join(",")]);

  // Chronological, oldest → newest, left to right — by construction, since
  // the loop always runs from fromYear up to toYear.
  const selectedYears = useMemo(() => {
    if (!fromYear || !toYear || fromYear > toYear) return [];
    const ys = [];
    for (let y = fromYear; y <= toYear; y++) if (pickerYears.includes(y)) ys.push(y);
    return ys;
  }, [fromYear, toYear, pickerYears]);

  const columnsForYears = useCallback(
    () => selectedYears.map(y => ({ label: `FY ${y}`, periods: fyColumnPeriods(periods, y) })),
    [selectedYears, periods],
  );

  const load = useCallback(async () => {
    if (!selectedYears.length) return;
    setLoading(true); setError(null);
    try {
      const res = source === "excel"
        ? await financialStatementApi.getProfitLoss(null, source, selectedYears)
        : await financialStatementApi.getProfitLoss(columnsForYears(), source);
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [selectedYears, columnsForYears, source]);

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
      <FsSourceControl
        reportType="profit_loss" source={source} setSource={setSource}
        onStatus={setExcelStatus} onUploaded={load}
      />
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period From</label>
          <select style={SELECT} value={fromYear} onChange={e => setFromYear(e.target.value ? Number(e.target.value) : "")}>
            {pickerYears.map(y => <option key={y} value={y}>{`FY ${y}`}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period To</label>
          <select style={SELECT} value={toYear} onChange={e => setToYear(e.target.value ? Number(e.target.value) : "")}>
            {pickerYears.map(y => <option key={y} value={y}>{`FY ${y}`}</option>)}
          </select>
        </div>
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data || source === "excel"} style={BTN}
          title={source === "excel" ? "Excel export isn't supported for the Excel data source" : undefined}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
        {data?.unmapped_accounts?.length > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#d97706" }}>
            <AlertTriangle size={13} /> {data.unmapped_accounts.length} unmapped account(s): {data.unmapped_accounts.join(", ")}
          </span>
        )}
      </div>

      {fromYear && toYear && fromYear > toYear ? (
        <div style={{ padding: 16, fontSize: 12, color: "#dc2626" }}>Period From must not be after Period To.</div>
      ) : loading && !data ? (
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
    <div className="fs-table-scroll" style={{ borderRadius: 12, boxShadow: NEU.shadowOutSm }}>
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

  // Data source toggle — Oracle (live MTD/YTD this-vs-last-year query) vs
  // the last uploaded Excel snapshot (the "PL_monthly" sheet). Excel mode
  // has no Period selector: the uploaded file is a single fixed MTD/YTD
  // comparison as of whatever date it was saved at, not a range to pick
  // from — its own date_last/date_this drive the header instead of GL
  // periods.
  const [source, setSource] = useState(SHOW_ORACLE_SOURCE ? "oracle" : "excel");
  const [excelStatus, setExcelStatus] = useState(null);

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
    if (source === "excel") {
      setLoading(true); setError(null);
      try {
        const res = await financialStatementApi.getProfitLossMonthly({}, "excel");
        if (res.success) setData(res); else setError(res.error || "Failed to load");
      } catch (e) {
        setError(e?.response?.data?.detail || e?.detail || String(e));
      } finally { setLoading(false); }
      return;
    }
    if (!period) return;
    const params = buildParams();
    if (!params) { setError("No corresponding period found in the prior year."); setData(null); return; }
    setLoading(true); setError(null);
    try {
      const res = await financialStatementApi.getProfitLossMonthly(params, "oracle");
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [period, buildParams, source]);

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
  // "Jun 2026", not the full date. Excel mode gets these directly from the
  // uploaded file instead of resolving GL periods.
  const headerDates = useMemo(() => {
    if (source === "excel") return { this: data?.date_this || "", last: data?.date_last || "" };
    const fmt = (p) => p?.end_date
      ? new Date(p.end_date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
      : "";
    const p = periods.find(x => x.period_name === period);
    if (!p) return { this: "", last: "" };
    const lastYearP = periods.find(x => x.period_year === p.period_year - 1 && x.period_num === p.period_num && x.adjustment_period_flag !== "Y");
    return { this: fmt(p), last: fmt(lastYearP) };
  }, [source, data, period, periods]);

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
      <FsSourceControl
        reportType="profit_loss_monthly" source={source} setSource={setSource}
        onStatus={setExcelStatus} onUploaded={load}
      />
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        {source === "oracle" ? (
          <div>
            <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period</label>
            <select style={SELECT} value={period} onChange={e => setPeriod(e.target.value)}>
              {periods.filter(p => p.has_activity === "Y" && p.adjustment_period_flag !== "Y").map(p => (
                <option key={p.period_name} value={p.period_name}>{periodLabel(p)}</option>
              ))}
            </select>
          </div>
        ) : (
          <span style={{ fontSize: 11, color: "#64748b" }}>
            {excelStatus ? `Uploaded snapshot: ${headerDates.last} vs ${headerDates.this}` : "No Excel data uploaded yet"}
          </span>
        )}
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data || source === "excel"} style={BTN}
          title={source === "excel" ? "Excel export isn't supported for the Excel data source" : undefined}>
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

/* ── Cash Flow ─────────────────────────────────────────────────────────── */

// Excel-only — no live Oracle equivalent exists (a statutory cash flow
// isn't a direct GL_BALANCES query, it's manually derived from the other
// statements each period), so unlike the other 3 panels there's no source
// toggle logic to carry — FsSourceControl is used purely for its upload/
// format-guide UI, with source hardcoded to "excel". The backend already
// returns each row pre-leveled/typed (level 0/1/2, type total|line)
// exactly as read from the sheet, so rows pass straight through to FsTable
// with no client-side reshaping.
function CashFlowPanel() {
  const [excelStatus, setExcelStatus] = useState(null);
  const pickerYears = excelStatus?.years || EMPTY_ARRAY;

  const [fromYear, setFromYear] = useState("");
  const [toYear, setToYear] = useState("");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!pickerYears.length) return;
    const latestYear = Math.max(...pickerYears);
    if (!toYear || !pickerYears.includes(toYear)) setToYear(latestYear);
    if (!fromYear || !pickerYears.includes(fromYear)) {
      const prevYear = latestYear - 1;
      setFromYear(pickerYears.includes(prevYear) ? prevYear : latestYear);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerYears.join(",")]);

  // Chronological, oldest → newest, left to right — by construction.
  const selectedYears = useMemo(() => {
    if (!fromYear || !toYear || fromYear > toYear) return [];
    const ys = [];
    for (let y = fromYear; y <= toYear; y++) if (pickerYears.includes(y)) ys.push(y);
    return ys;
  }, [fromYear, toYear, pickerYears]);

  const load = useCallback(async () => {
    if (!selectedYears.length) return;
    setLoading(true); setError(null);
    try {
      const res = await financialStatementApi.getCashFlow(selectedYears);
      if (res.success) setData(res); else setError(res.error || "Failed to load");
    } catch (e) {
      setError(e?.response?.data?.detail || e?.detail || String(e));
    } finally { setLoading(false); }
  }, [selectedYears]);

  useEffect(() => { load(); }, [load]);

  // Same growth-rate convention as Balance Sheet: exactly 2 columns -> diff
  // & %, more than 2 -> CAGR spanning Period From to Period To.
  const growthMode = selectedYears.length === 2 ? "diff" : selectedYears.length > 2 ? "cagr" : "none";
  const cagrYears = growthMode === "cagr" ? toYear - fromYear : 0;

  const rows = useMemo(() => {
    if (!data) return [];
    return data.rows.map(r => ({ ...r, growth: computeGrowth(r.values, growthMode, cagrYears) }));
  }, [data, growthMode, cagrYears]);

  const handleExport = () => {
    downloadExport(
      () => financialStatementApi.exportCashFlow(selectedYears),
      `Cash_Flow_${fromYear}-${toYear}.xlsx`,
      setExporting, setError,
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <FsSourceControl
        reportType="cash_flow" source="excel" setSource={() => {}}
        onStatus={setExcelStatus} onUploaded={load}
      />
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period From</label>
          <select style={SELECT} value={fromYear} onChange={e => setFromYear(e.target.value ? Number(e.target.value) : "")}>
            {pickerYears.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>Period To</label>
          <select style={SELECT} value={toYear} onChange={e => setToYear(e.target.value ? Number(e.target.value) : "")}>
            {pickerYears.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <button onClick={load} disabled={loading} style={BTN}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
        <button onClick={handleExport} disabled={exporting || !data} style={BTN}>
          {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download Excel
        </button>
      </div>

      {!loading && growthMode === "cagr" && selectedYears.length > 1 && (
        <div style={{ fontSize: 11, color: "#64748b" }}>
          Comparing {selectedYears.length} years ({fromYear} → {toYear}) — the growth column uses CAGR ({cagrYears} years).
        </div>
      )}

      {fromYear && toYear && fromYear > toYear ? (
        <div style={{ padding: 16, fontSize: 12, color: "#dc2626" }}>Period From must not be after Period To.</div>
      ) : loading && !data ? (
        <div style={{ padding: 40, textAlign: "center", color: "#64748b" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : error ? (
        <div style={{ padding: 16, color: "#dc2626", fontSize: 13 }}>{error}</div>
      ) : data ? (
        <FsTable columns={data.columns} rows={rows} growthMode={growthMode} />
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
          Sourced from the uploaded Excel snapshot — format follows FS_CKD OTTO 2015-2026_sent.xlsx.
          Net Sales/COGS is broken down by sales channel (not by customer — see the README notes).
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
          {subTab === "profit-loss"          && <ProfitLossPanel periods={periods} />}
          {subTab === "profit-loss-monthly"  && <ProfitLossMonthlyPanel periods={periods} />}
          {subTab === "cash-flow"            && <CashFlowPanel />}
        </>
      )}
    </div>
  );
}
