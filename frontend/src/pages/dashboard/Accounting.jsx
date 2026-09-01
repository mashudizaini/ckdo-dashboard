import { useState, useEffect, useCallback, useMemo, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FileText, DollarSign, FileBarChart2, RefreshCw,
  BarChart2, Package, Download, Search, Loader2, Layers, ClipboardList,
  AlertTriangle, ChevronLeft, ChevronRight, RotateCcw, ChevronDown,
} from "lucide-react";
import FinancialStatement from "./FinancialStatement";
import APAutoInvoice from "./APAutoInvoice";
import { accountingApi } from "@/api/dashboard";

const NEU = {
  bg:          "#f1f5f9",
  shadowOut:   "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  shadowOutSm: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  shadowIn:    "inset 0 2px 5px rgba(15,23,42,0.09)",
};

const TABS = [
  { id: "ap-invoice", icon: FileText,   label: "AP Autoinvoice",    color: "#2563eb" },
  { id: "cogs",       icon: BarChart2,  label: "COGS Report",       color: "#10b981" },
  { id: "profit",     icon: DollarSign, label: "AP Outstanding",    color: "#3b82f6" },
  { id: "ar",         icon: FileText,   label: "AR Outstanding",    color: "#f59e0b" },
  { id: "financial-statement", icon: FileBarChart2, label: "Financial Statement", color: "#8b5cf6" },
];

export default function AccountingDashboard() {
  const navigate = useNavigate();
  const location = useLocation();

  // Derive active tab from URL — navigation now lives in the sidebar tree menu.
  const active = TABS.find((t) => location.pathname.endsWith(t.id))?.id ?? "ap-invoice";

  useEffect(() => {
    if (location.pathname === "/dashboard/accounting" || location.pathname === "/dashboard/accounting/") {
      navigate("/dashboard/accounting/ap-invoice", { replace: true });
    }
  }, []); // eslint-disable-line

  return (
    <div className="p-6 space-y-4">
      {/* Content */}
      {active === "ap-invoice" && <APAutoInvoice />}
      {active === "cogs"       && <COGSReport />}

      {active === "profit" && <APOutstandingPanel />}

      {active === "ar" && <AROutstandingPanel />}

      {active === "financial-statement" && <FinancialStatement />}
    </div>
  );
}

/* ─── Aging shared helpers (used by both AP Aging by Supplier and AR Aging
       by Customer) ───────────────────────────────────────────────────── */

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const AGING_BUCKETS = [
  { key: "current_amt", label: "Current",   color: "#16a34a" },
  { key: "d1_30",       label: "1-30",      color: "#eab308" },
  { key: "d31_60",      label: "31-60",     color: "#f59e0b" },
  { key: "d61_90",      label: "61-90",     color: "#ea580c" },
  { key: "over_90",     label: "> 90 Days", color: "#dc2626" },
];

function fmtIdr(v) {
  const n = Number(v) || 0;
  const s = Math.abs(n).toLocaleString("id-ID", { maximumFractionDigits: 0 });
  return n < 0 ? `(${s})` : s;
}

// AP Outstanding number format: English (comma thousands, period decimal),
// decimals shown only for non-IDR (foreign-currency native) amounts.
function fmtNumAp(v, isIdr = true) {
  if (v === null || v === undefined || v === "-") return "-";
  const n = Number(v);
  if (isNaN(n)) return v;
  return n.toLocaleString("en-US", { minimumFractionDigits: isIdr ? 0 : 2, maximumFractionDigits: isIdr ? 0 : 2 });
}

/* ─── AP Outstanding Panel ───────────────────────────────────────────────── */

const AP_HEADERS = [
  { key: "supplier_name",        label: "Supplier",          width: 180 },
  { key: "transaction_type",     label: "Type",              width: 60  },
  { key: "transaction_number",   label: "Invoice No",        width: 130 },
  { key: "invoice_date",         label: "Invoice Date",      width: 100 },
  { key: "gl_date",              label: "GL Date",           width: 100 },
  { key: "currency",             label: "Cur",               width: 45  },
  { key: "coa",                  label: "COA",               width: 180 },
  { key: "coa_number",           label: "Account",           width: 70  },
  { key: "coa_descpt",           label: "Account Desc",      width: 160 },
  { key: "payment_status",       label: "Status",            width: 100 },
  { key: "original_amount_orig", label: "Orig Amt (FC)",     width: 110, num: true },
  { key: "remaining_amount_orig",label: "Remaining (FC)",    width: 110, num: true },
  { key: "original_amount_idr",  label: "Orig Amt (IDR)",    width: 130, num: true },
  { key: "remaining_amount_idr", label: "Remaining (IDR)",   width: 130, num: true },
  { key: "after_revaluation_idr",label: "After Revaluation (IDR)", width: 150, num: true },
  { key: "description",          label: "Description",       width: 160 },
];

function exportApCSV(rows) {
  if (!rows?.length) return;
  const lines = [
    "﻿" + AP_HEADERS.map(h => h.label).join(","),
    ...rows.map(r =>
      AP_HEADERS.map(h => `"${String(r[h.key] ?? "").replace(/"/g, '""')}"`).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = "ap_outstanding.csv"; a.click();
  URL.revokeObjectURL(url);
}

function APOutstandingPanel() {
  const [viewMode,       setViewMode]       = useState("list"); // "list" | "aging"
  const today = new Date().toISOString().slice(0, 10);
  const [asOfDate,       setAsOfDate]       = useState(today);
  const [dateFrom,       setDateFrom]       = useState("");
  const [dateTo,         setDateTo]         = useState("");
  const [supplierName,   setSupplierName]   = useState("");
  const [payStatusFilter,setPayStatusFilter] = useState("ALL");
  const [limit,          setLimit]          = useState(100);
  const [usdRate,        setUsdRate]        = useState("");
  const [eurRate,        setEurRate]        = useState("");
  const [rateInfo,       setRateInfo]       = useState(null); // { date, source }
  const [rateLoading,    setRateLoading]    = useState(false);
  const [data,           setData]           = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [search,         setSearch]         = useState("");
  const [sort,           setSort]           = useState({ key: null, dir: "asc" });

  const AP_NUMERIC_KEYS = ["original_amount_idr", "remaining_amount_idr", "original_amount_orig", "remaining_amount_orig", "after_revaluation_idr"];

  const loadBiRate = useCallback(async () => {
    setRateLoading(true);
    try {
      const res = await accountingApi.getExchangeRate({ as_of_date: asOfDate });
      const midOf = (r) => {
        if (!r || (!r.sell && !r.buy)) return null;
        const denom = r.denomination || 1;
        return ((r.sell && r.buy ? (r.sell + r.buy) / 2 : (r.sell || r.buy)) / denom);
      };
      const usd = midOf(res?.rates?.find(r => r.code === "USD"));
      const eur = midOf(res?.rates?.find(r => r.code === "EUR"));
      const usdStr = usd != null ? String(Math.round(usd * 100) / 100) : null;
      const eurStr = eur != null ? String(Math.round(eur * 100) / 100) : null;
      if (usdStr != null) setUsdRate(usdStr);
      if (eurStr != null) setEurRate(eurStr);
      if (usdStr != null || eurStr != null) setRateInfo({ date: res.date, source: res.source });
      // Returned (not just set as state) so a caller that needs the fresh
      // rate immediately after — see the Refresh button below — doesn't
      // read a stale usdRate/eurRate closure from before this state update
      // has actually re-rendered the component.
      return { usd: usdStr, eur: eurStr };
    } catch (e) {
      return { usd: null, eur: null };
      // Silent — fields stay editable/empty and the user can type rates manually.
    } finally { setRateLoading(false); }
  }, [asOfDate]);

  useEffect(() => { loadBiRate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const loadData = useCallback(async (overrides = {}) => {
    setLoading(true); setError(null);
    try {
      const effUsdRate = overrides.usdRate ?? usdRate;
      const effEurRate = overrides.eurRate ?? eurRate;
      const params = {
        limit,
        ...(asOfDate      && { as_of_date:      asOfDate      }),
        ...(dateFrom      && { date_from:       dateFrom      }),
        ...(dateTo        && { date_to:         dateTo        }),
        ...(supplierName  && { supplier_name:   supplierName  }),
        ...(payStatusFilter && payStatusFilter !== "ALL" && { payment_status: payStatusFilter }),
        ...(effUsdRate    && { usd_rate:        Number(effUsdRate) }),
        ...(effEurRate    && { eur_rate:        Number(effEurRate) }),
      };
      const res = await accountingApi.getApOutstanding(params);
      if (res.success) { setData(res); }
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [asOfDate, dateFrom, dateTo, supplierName, payStatusFilter, limit, usdRate, eurRate]);

  // One click = fetch the fresh BI rate AND reload the list with it applied
  // — passing the just-fetched rate straight into loadData() as an explicit
  // override, instead of relying on state (which wouldn't have re-rendered
  // yet), is what avoids needing a second click.
  const refreshRateAndReload = useCallback(async () => {
    const { usd, eur } = await loadBiRate();
    loadData({ usdRate: usd ?? usdRate, eurRate: eur ?? eurRate });
  }, [loadBiRate, loadData, usdRate, eurRate]);

  const toggleSort = (key) => {
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const filteredRows = data?.data?.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.supplier_name        || "").toLowerCase().includes(q)
        || (r.transaction_number   || "").toLowerCase().includes(q)
        || (r.coa                  || "").toLowerCase().includes(q)
        || (r.coa_descpt           || "").toLowerCase().includes(q);
  }) ?? [];

  const rows = useMemo(() => {
    if (!sort.key) return filteredRows;
    const numeric = AP_NUMERIC_KEYS.includes(sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      if (numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, search, sort]);

  const INPUT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none" };

  const payBadge = (s) => {
    const cfg = {
      "Not Paid":      { bg: "rgba(239,68,68,0.12)",   color: "#dc2626" },
      "Partially Paid":{ bg: "rgba(245,158,11,0.12)",  color: "#d97706" },
      "Paid":          { bg: "rgba(34,197,94,0.12)",   color: "#16a34a" },
    }[s] || { bg: "#f1f5f9", color: "#64748b" };
    return (
      <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: cfg.bg, color: cfg.color }}>
        {s}
      </span>
    );
  };

  const rowBg = (r, i) => {
    if (r.payment_status === "Partially Paid") return i%2===0 ? "rgba(245,158,11,0.07)" : "rgba(245,158,11,0.04)";
    if (r.payment_status === "Not Paid")       return i%2===0 ? "rgba(239,68,68,0.06)"  : "rgba(239,68,68,0.03)";
    return i % 2 === 0 ? "#f8fafc" : "#f1f5f9";
  };

  const sm = data?.summary;

  const viewToggleBtn = (mode, label) => (
    <button
      onClick={() => setViewMode(mode)}
      style={{
        padding: "7px 14px", border: "none", borderRadius: 9, cursor: "pointer",
        fontSize: 12, fontWeight: 700,
        background: viewMode === mode ? "#3b82f6" : NEU.bg,
        color: viewMode === mode ? "#ffffff" : "#64748b",
        boxShadow: viewMode === mode ? NEU.shadowOutSm : NEU.shadowIn,
      }}
    >
      {label}
    </button>
  );

  if (viewMode === "aging") {
    return (
      <>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {viewToggleBtn("list", "List")}
          {viewToggleBtn("aging", "Aging by Supplier")}
        </div>
        <APAgingPanel />
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {viewToggleBtn("list", "List")}
        {viewToggleBtn("aging", "Aging by Supplier")}
      </div>
    <SectionCard>
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>As of Date</p>
          <input type="date" value={asOfDate} onChange={e => setAsOfDate(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Period From</p>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Period To</p>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Supplier</p>
          <input value={supplierName} onChange={e => setSupplierName(e.target.value)}
            placeholder="Search supplier…" style={{ ...INPUT, width: 180 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Pay Status</p>
          <select value={payStatusFilter} onChange={e => setPayStatusFilter(e.target.value)} style={{ ...INPUT, width: 140, cursor: "pointer" }}>
            <option value="ALL">All Outstanding</option>
            <option value="Not Paid">Not Paid</option>
            <option value="Partially Paid">Partially Paid</option>
          </select>
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Limit</p>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{ ...INPUT, width: 90, cursor: "pointer" }}>
            {[200, 500, 1000, 2000].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>USD Rate</p>
          <input type="number" step="0.01" value={usdRate} onChange={e => setUsdRate(e.target.value)}
            placeholder="e.g. 16250" style={{ ...INPUT, width: 100 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>EUR Rate</p>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="number" step="0.01" value={eurRate} onChange={e => setEurRate(e.target.value)}
              placeholder="e.g. 17800" style={{ ...INPUT, width: 100 }} />
            <button type="button" onClick={refreshRateAndReload} disabled={rateLoading} title="Refresh rate (as of the selected date) and reload the list"
              style={{ border: "none", borderRadius: 9, padding: "7px 8px", background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: rateLoading ? "default" : "pointer", color: "#64748b" }}>
              <RefreshCw size={13} className={rateLoading ? "animate-spin" : ""} />
            </button>
            {rateInfo && (
              <span style={{ fontSize: 9.5, color: "#94a3b8", whiteSpace: "nowrap" }}>Kurs Tengah BI{rateInfo.date ? ` · ${rateInfo.date}` : ""}</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Summary cards — Total Invoices/Not Paid/Partially Paid are narrow
          fixed-width (short counts) so the 2 IDR-amount cards get the
          freed-up space; Load/Export CSV sit to the right of the row
          instead of in the filter bar. Total After Revaluation revalues
          Not Paid invoices' original amount at the USD/EUR Kurs Tengah
          BI rate above (falling back to the existing base_amount-derived
          conversion for any other currency, or when no rate is entered). */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "stretch" }}>
        <div style={{ display: "grid", gridTemplateColumns: "110px 110px 110px repeat(2, 1fr)", gap: 10, flex: 1 }}>
          {[
            { label: "Total Invoices",       val: (data?.count || 0).toLocaleString(),               color: "#3b82f6" },
            { label: "Not Paid",             val: (sm?.not_paid_count    || 0).toLocaleString(),    color: "#dc2626" },
            { label: "Partially Paid",       val: (sm?.partial_paid_count|| 0).toLocaleString(),    color: "#d97706" },
            { label: "Total Outstanding",    val: "Rp " + fmtNumAp(sm?.total_outstanding_idr || 0),   color: "#2563eb" },
            { label: "Total After Revaluation", val: "Rp " + fmtNumAp(sm?.total_after_revaluation_idr || 0), color: "#dc2626" },
          ].map(c => (
            <div key={c.label} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
              <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{c.label}</p>
              <p style={{ fontSize: 13, fontWeight: 800, color: c.color, fontFamily: "monospace" }}>{c.val}</p>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, justifyContent: "center" }}>
          <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#3b82f6" onClick={loadData} disabled={loading} />
          {data?.data?.length > 0 && (
            <ActionBtn icon={Download} label="Export CSV" color="#3b82f6" onClick={() => exportApCSV(data.data)} />
          )}
        </div>
      </div>

      {data && (
        <>
          {/* Client-side search */}
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Filter by supplier / invoice / COA…"
              style={{ ...INPUT, width: 340 }} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              Showing {rows.length.toLocaleString()} of {data.count.toLocaleString()} rows
            </span>
          </div>

          {/* Table — no pagination: all fetched rows (up to Limit) render
              in one continuous table. Height is bounded with both-axis
              scroll and a sticky header so the horizontal scrollbar sits
              right under the visible rows — no need to scroll all the
              way down the page to reach it. */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ maxHeight: "70vh", overflow: "auto" }}>
              <table className="acct-outstanding-table" style={{ width: "100%", borderCollapse: "collapse", minWidth: 1660 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#1e3a5f,#1e40af)" }}>
                    <th style={{ ...TH, color: "#bfdbfe", background: "#1e3a5f", fontSize: 9.5, position: "sticky", top: 0, zIndex: 1 }}>#</th>
                    {AP_HEADERS.map(h => (
                      <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort}
                        style={{ color: "#bfdbfe", background: "#1e3a5f", fontSize: 9.5, minWidth: h.width, whiteSpace: "nowrap", position: "sticky", top: 0, zIndex: 1 }} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={AP_HEADERS.length + 1} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No records found
                      </td>
                    </tr>
                  ) : rows.map((r, i) => {
                    return (
                    <tr key={i}
                      style={{ background: rowBg(r, i) }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(59,130,246,0.07)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg(r, i)}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>{i + 1}</td>
                      <td style={{ ...TD, fontWeight: 700, color: "#1e293b", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.supplier_name}>{r.supplier_name}</td>
                      <td style={{ ...TD, fontSize: 11 }}>{r.transaction_type}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontWeight: 700, color: "#2563eb", whiteSpace: "nowrap" }}>{r.transaction_number}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.invoice_date}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.gl_date}</td>
                      <td style={{ ...TD, fontSize: 11, fontWeight: 600 }}>{r.currency}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 10, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.coa}>{r.coa}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.coa_number}</td>
                      <td style={{ ...TD, fontSize: 11, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.coa_descpt}>{r.coa_descpt}</td>
                      <td style={{ ...TD }}>{payBadge(r.payment_status)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{r.original_amount_orig != null ? fmtNumAp(r.original_amount_orig, false) : "—"}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{r.remaining_amount_orig != null ? fmtNumAp(r.remaining_amount_orig, false) : "—"}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700 }}>{fmtNumAp(r.original_amount_idr, true)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: r.remaining_amount_idr > 0 ? "#dc2626" : "#16a34a" }}>{fmtNumAp(r.remaining_amount_idr, true)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: "#dc2626" }}>{fmtNumAp(r.after_revaluation_idr, true)}</td>
                      <td style={{ ...TD, fontSize: 11, color: "#64748b", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.description}>{r.description}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div style={{ padding: "48px", textAlign: "center", background: "#f8fafc", borderRadius: 12, boxShadow: NEU.shadowIn }}>
          <DollarSign size={28} style={{ color: "#3b82f6", marginBottom: 10 }} />
          <p style={{ fontSize: 13, fontWeight: 600, color: "#475569", margin: 0 }}>Set as-of date and click Load to fetch AP outstanding data</p>
          <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>Default: today · Excludes fully Paid invoices</p>
        </div>
      )}
    </SectionCard>
    </>
  );
}

/* ─── AP Aging Panel ─────────────────────────────────────────────────────── */

function APAgingPanel() {
  const [supplierName, setSupplierName] = useState("");
  const [baseDate,      setBaseDate]     = useState(todayIso());
  const [data,          setData]         = useState(null);
  const [loading,       setLoading]      = useState(false);
  const [error,         setError]        = useState(null);

  const INPUT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none" };

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = { limit: 500, base_date: baseDate || todayIso(), ...(supplierName && { supplier_name: supplierName }) };
      const res = await accountingApi.getApAging(params);
      if (res.success) setData(res);
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [supplierName, baseDate]);

  useEffect(() => { loadData(); }, [loadData]);

  const totals = data?.totals;
  const isToday = (data?.base_date || baseDate) === todayIso();

  return (
    <SectionCard
      title="AP Aging by Supplier"
      subtitle={`Open items (payment_status IN Not Paid/Partially Paid), IDR converted, priced and bucketed as of ${data?.base_date || baseDate}${isToday ? " (today)" : ""}.`}
    >
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Supplier</p>
          <input value={supplierName} onChange={e => setSupplierName(e.target.value)}
            placeholder="Search supplier…" style={{ ...INPUT, width: 220 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Base Date</p>
          <input type="date" value={baseDate} onChange={e => setBaseDate(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        {baseDate !== todayIso() && (
          <ActionBtn icon={RefreshCw} label="Reset to Today" color="#64748b" onClick={() => setBaseDate(todayIso())} />
        )}
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#3b82f6" onClick={loadData} disabled={loading} />
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : data ? (
        <>
          {/* Bucket summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
            {AGING_BUCKETS.map(b => (
              <div key={b.key} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
                <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{b.label}</p>
                <p style={{ fontSize: 13, fontWeight: 800, color: b.color, fontFamily: "monospace" }}>Rp {fmtIdr(totals?.[b.key] || 0)}</p>
              </div>
            ))}
          </div>

          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1040 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#1e3a5f,#1e40af)" }}>
                    <th style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5 }}>Supplier</th>
                    <th style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5 }}>Operating Unit</th>
                    {AGING_BUCKETS.map(b => (
                      <th key={b.key} style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5, textAlign: "right" }}>{b.label}</th>
                    ))}
                    <th style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5, textAlign: "right" }}>Total</th>
                    <th style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5, textAlign: "right" }}>Items</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.length === 0 ? (
                    <tr>
                      <td colSpan={AGING_BUCKETS.length + 4} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No open items found
                      </td>
                    </tr>
                  ) : data.data.map((r, i) => (
                    <tr key={r.supplier_name + r.operating_unit}
                      style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(59,130,246,0.08)"}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f8fafc" : "#f1f5f9"}
                    >
                      <td style={{ ...TD, fontWeight: 700, color: "#1e293b" }}>{r.supplier_name}</td>
                      <td style={{ ...TD, fontSize: 11, color: "#64748b" }}>{r.operating_unit}</td>
                      {AGING_BUCKETS.map(b => (
                        <td key={b.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: r[b.key] < 0 ? "#16a34a" : "#334155" }}>
                          {fmtIdr(r[b.key])}
                        </td>
                      ))}
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: "#2563eb" }}>{fmtIdr(r.total_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#94a3b8" }}>{r.item_count}</td>
                    </tr>
                  ))}
                </tbody>
                {data.data.length > 0 && (
                  <tfoot>
                    <tr style={{ background: "#D9E1F2" }}>
                      <td style={{ ...TD, fontWeight: 800, color: "#1e293b" }} colSpan={2}>TOTAL</td>
                      {AGING_BUCKETS.map(b => (
                        <td key={b.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{fmtIdr(totals?.[b.key])}</td>
                      ))}
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{fmtIdr(totals?.total_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{totals?.item_count}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>
        </>
      ) : null}
    </SectionCard>
  );
}

/* ─── AR Outstanding Panel ───────────────────────────────────────────────── */

const AR_HEADERS = [
  { key: "customer_name",       label: "Customer",        width: 200 },
  { key: "account_number",      label: "Account #",       width: 100 },
  { key: "invoice_number",      label: "Invoice No",      width: 120 },
  { key: "transaction_type",    label: "Type",            width: 70  },
  { key: "invoice_date",        label: "Invoice Date",    width: 100 },
  { key: "due_date",            label: "Due Date",        width: 100 },
  { key: "currency",            label: "Cur",             width: 45  },
  { key: "original_amount",     label: "Original Amt",    width: 120, num: true },
  { key: "remaining_amount",    label: "Remaining Amt",   width: 120, num: true },
  { key: "conversion_rate",     label: "Rate (Corp.)",    width: 90,  num: true },
  { key: "remaining_amount_idr", label: "Remaining (IDR)", width: 130, num: true },
  { key: "after_revaluation_idr", label: "After Revaluation (IDR)", width: 150, num: true },
  { key: "days_overdue",        label: "Days Overdue",    width: 90,  num: true },
  { key: "status",              label: "Status",          width: 60  },
  { key: "payment_date",        label: "Payment Date",    width: 100 },
  { key: "operating_unit",      label: "OU",              width: 120 },
  { key: "tax_invoice_number",  label: "Tax Invoice Number", width: 160 },
];

function exportArCSV(rows) {
  if (!rows?.length) return;
  const lines = [
    "﻿" + AR_HEADERS.map(h => h.label).join(","),
    ...rows.map(r =>
      AR_HEADERS.map(h => `"${String(r[h.key] ?? "").replace(/"/g, '""')}"`).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = "ar_outstanding.csv"; a.click();
  URL.revokeObjectURL(url);
}

function AROutstandingPanel() {
  const [viewMode,       setViewMode]       = useState("list"); // "list" | "aging"
  const [customerName,   setCustomerName]   = useState("");
  const [invoiceNumber,  setInvoiceNumber]  = useState("");
  const [dateFrom,       setDateFrom]       = useState("");
  const [dateTo,         setDateTo]         = useState("");
  const [statusFilter,   setStatusFilter]   = useState("OP");
  const [limit,          setLimit]          = useState(100);
  const [asOfDate,       setAsOfDate]       = useState("");
  const [usdRate,        setUsdRate]        = useState("");
  const [rateInfo,       setRateInfo]       = useState(null); // { date, source }
  const [rateLoading,    setRateLoading]    = useState(false);
  const [data,           setData]           = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [search,         setSearch]         = useState("");
  const [sort,           setSort]           = useState({ key: null, dir: "asc" });

  const AR_NUMERIC_KEYS = ["original_amount", "remaining_amount", "conversion_rate", "remaining_amount_idr", "after_revaluation_idr", "days_overdue"];

  const loadBiRate = useCallback(async () => {
    setRateLoading(true);
    try {
      const res = await accountingApi.getExchangeRate({ as_of_date: asOfDate });
      const usd = res?.rates?.find(r => r.code === "USD");
      let usdStr = null;
      if (usd && (usd.sell || usd.buy)) {
        const denom = usd.denomination || 1;
        const mid = (usd.sell && usd.buy ? (usd.sell + usd.buy) / 2 : (usd.sell || usd.buy)) / denom;
        usdStr = String(Math.round(mid * 100) / 100);
        setUsdRate(usdStr);
        setRateInfo({ date: res.date, source: res.source });
      }
      // Returned so a caller needing the fresh value right away (the
      // Refresh button below) doesn't read a stale usdRate closure from
      // before this state update has actually re-rendered the component.
      return usdStr;
    } catch (e) {
      // Silent — the field just stays editable/empty and the user can type a rate manually.
      return null;
    } finally { setRateLoading(false); }
  }, [asOfDate]);

  useEffect(() => { loadBiRate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const loadData = useCallback(async (overrides = {}) => {
    setLoading(true); setError(null);
    try {
      const effUsdRate = overrides.usdRate ?? usdRate;
      const params = {
        status: statusFilter,
        limit,
        ...(customerName  && { customer_name:  customerName  }),
        ...(invoiceNumber && { invoice_number: invoiceNumber }),
        ...(dateFrom      && { date_from:       dateFrom      }),
        ...(dateTo        && { date_to:         dateTo        }),
        ...(effUsdRate    && { usd_rate:        Number(effUsdRate) }),
        ...(asOfDate      && { as_of_date:      asOfDate      }),
      };
      const res = await accountingApi.getArOutstanding(params);
      if (res.success) { setData(res); }
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [customerName, invoiceNumber, dateFrom, dateTo, statusFilter, limit, usdRate, asOfDate]);

  // One click = fetch the fresh BI rate AND reload the list with it applied
  // — same fix as AP Outstanding's Refresh button, which had the identical
  // stale-closure bug (loadBiRate()+loadData() fired together read usdRate
  // from before the fetch resolved).
  const refreshRateAndReload = useCallback(async () => {
    const usd = await loadBiRate();
    loadData({ usdRate: usd ?? usdRate });
  }, [loadBiRate, loadData, usdRate]);

  const RESET_DEFAULTS = { customerName: "", invoiceNumber: "", dateFrom: "", dateTo: "", statusFilter: "OP", limit: 100, asOfDate: "" };
  const resetFilters = () => {
    setCustomerName(RESET_DEFAULTS.customerName);
    setInvoiceNumber(RESET_DEFAULTS.invoiceNumber);
    setDateFrom(RESET_DEFAULTS.dateFrom);
    setDateTo(RESET_DEFAULTS.dateTo);
    setStatusFilter(RESET_DEFAULTS.statusFilter);
    setLimit(RESET_DEFAULTS.limit);
    setAsOfDate(RESET_DEFAULTS.asOfDate);
  };

  const toggleSort = (key) => {
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  // Client-side search on top of fetched data
  const filteredRows = data?.data?.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.customer_name  || "").toLowerCase().includes(q)
        || (r.invoice_number || "").toLowerCase().includes(q)
        || (r.account_number || "").toLowerCase().includes(q);
  }) ?? [];

  const rows = useMemo(() => {
    if (!sort.key) return filteredRows;
    const numeric = AR_NUMERIC_KEYS.includes(sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      if (numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, search, sort]);

  const INPUT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none" };

  const rowBg = (r) => {
    const days = r.days_overdue || 0;
    const isOpen = r.status === "OP";
    if (isOpen && days > 0)   return "rgba(239,68,68,0.06)";
    if (isOpen && days > -30) return "rgba(245,158,11,0.05)";
    return undefined;
  };

  const daysStyle = (days) => {
    if (!days) return { color: "#94a3b8" };
    if (days > 90) return { color: "#dc2626", fontWeight: 800 };
    if (days > 30) return { color: "#ea580c", fontWeight: 700 };
    if (days > 0)  return { color: "#d97706", fontWeight: 700 };
    return { color: "#16a34a" };
  };

  const statusBadge = (s) => (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700,
      background: s === "OP" ? "rgba(239,68,68,0.12)" : "rgba(34,197,94,0.12)",
      color:      s === "OP" ? "#dc2626"               : "#16a34a",
    }}>{s === "OP" ? "OPEN" : "CLOSED"}</span>
  );

  const sm = data?.summary;

  const viewToggleBtn = (mode, label) => (
    <button
      onClick={() => setViewMode(mode)}
      style={{
        padding: "7px 14px", border: "none", borderRadius: 9, cursor: "pointer",
        fontSize: 12, fontWeight: 700,
        background: viewMode === mode ? "#f59e0b" : NEU.bg,
        color: viewMode === mode ? "#ffffff" : "#64748b",
        boxShadow: viewMode === mode ? NEU.shadowOutSm : NEU.shadowIn,
      }}
    >
      {label}
    </button>
  );

  if (viewMode === "aging") {
    return (
      <>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {viewToggleBtn("list", "List")}
          {viewToggleBtn("aging", "Aging by Customer")}
        </div>
        <ARAgingPanel />
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {viewToggleBtn("list", "List")}
        {viewToggleBtn("aging", "Aging by Customer")}
      </div>
    <SectionCard>
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Customer</p>
          <input value={customerName} onChange={e => setCustomerName(e.target.value)}
            placeholder="Search customer…" style={{ ...INPUT, width: 180 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Invoice No</p>
          <input value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)}
            placeholder="e.g. INV-2024…" style={{ ...INPUT, width: 140 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Invoice Date From</p>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...INPUT, width: 140 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>To</p>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...INPUT, width: 140 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: asOfDate ? "#7c3aed" : "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>As Of Date</p>
          <input type="date" value={asOfDate} onChange={e => setAsOfDate(e.target.value)}
            style={{ ...INPUT, width: 140, boxShadow: asOfDate ? "inset 0 2px 5px rgba(124,58,237,0.25)" : NEU.shadowIn }} />
          {asOfDate && (
            <p style={{ fontSize: 9.5, color: "#7c3aed", marginTop: 4, maxWidth: 150 }}>Status &amp; Remaining reconstructed as of this date</p>
          )}
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Status</p>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...INPUT, width: 110, cursor: "pointer" }}>
            <option value="OP">Open</option>
            <option value="CL">Closed</option>
            <option value="ALL">All</option>
          </select>
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Limit</p>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{ ...INPUT, width: 90, cursor: "pointer" }}>
            {[200, 500, 1000, 2000].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Exchange Rate (USD)</p>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="number" step="0.01" value={usdRate} onChange={e => setUsdRate(e.target.value)}
              placeholder="e.g. 16250" style={{ ...INPUT, width: 110 }} />
            <button type="button" onClick={refreshRateAndReload} disabled={rateLoading} title="Refresh rate (as of the selected date) and reload the list"
              style={{ border: "none", borderRadius: 9, padding: "7px 8px", background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: rateLoading ? "default" : "pointer", color: "#64748b" }}>
              <RefreshCw size={13} className={rateLoading ? "animate-spin" : ""} />
            </button>
            {rateInfo && (
              <span style={{ fontSize: 9.5, color: "#94a3b8", whiteSpace: "nowrap" }}>Kurs Tengah BI{rateInfo.date ? ` · ${rateInfo.date}` : ""}</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {data?.as_of_date && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.2)", fontSize: 11.5, color: "#7c3aed", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> Showing Status &amp; Remaining Amount reconstructed as of {data.as_of_date} (replaying receipts applied by that date), not today's live values. Balances closed purely via manual write-off/adjustment aren't replayed and may still show as open.
        </div>
      )}

      {/* Summary cards — totals are Corporate-rate IDR conversions
          (sm.total_remaining_idr/total_overdue_idr), not a raw sum of
          remaining_amount across mixed currencies (that undercounted
          open USD invoices at their bare numeric value, e.g. treating
          $1 as Rp 1). Returns (CM) surfaces the unapplied credit
          memos now included/netted into the total, instead of being
          silently excluded. Open Invoices/Overdue Count are narrow
          fixed-width (their values are short counts, max ~5 digits) so
          the 3 IDR-amount cards get the freed-up space; Load/Export CSV
          sit to the right of the row instead of in the filter bar. */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "stretch" }}>
        <div style={{ display: "grid", gridTemplateColumns: "110px 110px repeat(4, 1fr)", gap: 10, flex: 1 }}>
          {[
            { label: "Open Invoices",     val: (sm?.open_invoice_count || 0).toLocaleString(),    color: "#f59e0b" },
            { label: "Overdue Count",      val: (sm?.overdue_count     || 0).toLocaleString(),    color: "#dc2626" },
            { label: "Total Outstanding (IDR)", val: "Rp " + fmtNumAp(sm?.total_remaining_idr || 0), color: "#2563eb" },
            { label: "Total Overdue (IDR)",     val: "Rp " + fmtNumAp(sm?.total_overdue_idr   || 0), color: "#dc2626" },
            { label: "Total After Revaluation (IDR)", val: "Rp " + fmtNumAp(sm?.total_after_revaluation_idr || 0), color: "#0891b2" },
            { label: "Returns (CM)",       val: `${sm?.returns_count || 0} · Rp ${fmtNumAp(sm?.returns_remaining_idr || 0)}`, color: "#7c3aed" },
          ].map(c => (
            <div key={c.label} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
              <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{c.label}</p>
              <p style={{ fontSize: 13, fontWeight: 800, color: c.color, fontFamily: "monospace" }}>{c.val}</p>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, justifyContent: "center" }}>
          <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#f59e0b" onClick={() => loadData()} disabled={loading} />
          <ActionBtn icon={RotateCcw} label="Reset" color="#64748b" onClick={resetFilters} disabled={loading} />
          {data?.data?.length > 0 && (
            <ActionBtn icon={Download} label="Export CSV" color="#f59e0b" onClick={() => exportArCSV(data.data)} />
          )}
        </div>
      </div>

      {data && (
        <>
          {/* Client-side search */}
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Filter results by customer / invoice / account…"
              style={{ ...INPUT, width: 320 }} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              Showing {rows.length.toLocaleString()} of {data.count.toLocaleString()} rows
            </span>
          </div>

          {/* Table — no pagination: all fetched rows (up to Limit) render
              in one continuous table. Height is bounded with both-axis
              scroll and a sticky header so the horizontal scrollbar sits
              right under the visible rows — no need to scroll all the
              way down the page to reach it. */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ maxHeight: "70vh", overflow: "auto" }}>
              <table className="acct-outstanding-table" style={{ width: "100%", borderCollapse: "collapse", minWidth: 1770 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#92400e,#78350f)" }}>
                    <th style={{ ...TH, color: "#fef3c7", background: "#92400e", fontSize: 9.5, position: "sticky", top: 0, zIndex: 1 }}>#</th>
                    {AR_HEADERS.map(h => (
                      <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort}
                        style={{ color: "#fef3c7", background: "#92400e", fontSize: 9.5, minWidth: h.width, whiteSpace: "nowrap", position: "sticky", top: 0, zIndex: 1 }} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={AR_HEADERS.length + 1} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No records found
                      </td>
                    </tr>
                  ) : rows.map((r, i) => {
                    return (
                    <tr key={i}
                      style={{ background: rowBg(r) || (i % 2 === 0 ? "#f8fafc" : "#f1f5f9") }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(245,158,11,0.08)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg(r) || (i % 2 === 0 ? "#f8fafc" : "#f1f5f9")}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>{i + 1}</td>
                      <td style={{ ...TD, fontWeight: 700, color: "#1e293b", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.customer_name}>{r.customer_name}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.account_number}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontWeight: 700, color: "#2563eb", whiteSpace: "nowrap" }}>{r.invoice_number}</td>
                      <td style={{ ...TD, fontSize: 11 }}>{r.transaction_type}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.invoice_date}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.due_date}</td>
                      <td style={{ ...TD, fontSize: 11, fontWeight: 600 }}>{r.currency}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace" }}>{fmtNumAp(r.original_amount, false)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: r.remaining_amount > 0 ? "#dc2626" : "#16a34a" }}>{fmtNumAp(r.remaining_amount, false)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontSize: 11, color: "#64748b" }}>{fmtNumAp(r.conversion_rate, false)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: r.remaining_amount_idr > 0 ? "#dc2626" : "#16a34a" }}>{fmtNumAp(r.remaining_amount_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#0891b2" }}>{fmtNumAp(r.after_revaluation_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", ...daysStyle(r.days_overdue) }}>
                        {r.days_overdue > 0 ? `+${r.days_overdue}d` : r.days_overdue === 0 ? "Today" : r.days_overdue < 0 ? `${Math.abs(r.days_overdue)}d left` : "—"}
                      </td>
                      <td style={{ ...TD }}>{statusBadge(r.status)}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11, color: "#64748b" }}>{r.payment_date || "—"}</td>
                      <td style={{ ...TD, fontSize: 11, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.operating_unit}>{r.operating_unit}</td>
                      <td style={{ ...TD, fontSize: 11, color: "#64748b", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.tax_invoice_number}>{r.tax_invoice_number}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div style={{ padding: "48px", textAlign: "center", background: "#f8fafc", borderRadius: 12, boxShadow: NEU.shadowIn }}>
          <AlertTriangle size={28} style={{ color: "#f59e0b", marginBottom: 10 }} />
          <p style={{ fontSize: 13, fontWeight: 600, color: "#475569", margin: 0 }}>Set filters and click Load to fetch AR outstanding data</p>
          <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>Default: Open invoices (INV + DM), up to 500 rows</p>
        </div>
      )}
    </SectionCard>
    </>
  );
}

/* ─── AR Aging Panel ─────────────────────────────────────────────────────── */

function ARAgingPanel() {
  const [customerName, setCustomerName] = useState("");
  const [asOfDate,      setAsOfDate]     = useState(todayIso());
  const [data,          setData]         = useState(null);
  const [loading,       setLoading]      = useState(false);
  const [error,         setError]        = useState(null);

  // Drill-down — click a customer row to see the underlying invoices,
  // fetched with the SAME as_of_date this aging report used (so the detail
  // always matches what's on screen) via the same endpoint AR Outstanding's
  // List view uses. Cached per customer name so re-expanding is instant.
  const [expandedCustomer, setExpandedCustomer] = useState(null);
  const [detailCache,      setDetailCache]      = useState({}); // { [customerName]: rows | "loading" | { error } }

  const INPUT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none" };

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    setExpandedCustomer(null); setDetailCache({});
    try {
      const params = { limit: 500, as_of_date: asOfDate || todayIso(), ...(customerName && { customer_name: customerName }) };
      const res = await accountingApi.getArAging(params);
      if (res.success) setData(res);
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [customerName, asOfDate]);

  const toggleCustomer = async (custName) => {
    if (expandedCustomer === custName) { setExpandedCustomer(null); return; }
    setExpandedCustomer(custName);
    if (detailCache[custName]) return;
    setDetailCache(prev => ({ ...prev, [custName]: "loading" }));
    try {
      const res = await accountingApi.getArOutstanding({
        customer_name: custName, status: "ALL", limit: 500,
        as_of_date: data?.as_of_date || asOfDate || todayIso(),
      });
      if (res.success) {
        // Aging only counts non-zero remaining — mirror that here so the
        // drill-down lines up with the bucket totals it's expanding.
        const rows = (res.data || []).filter(r => Math.round((r.remaining_amount_idr || 0) * 100) !== 0);
        setDetailCache(prev => ({ ...prev, [custName]: rows }));
      } else {
        setDetailCache(prev => ({ ...prev, [custName]: { error: res.error || "Failed to load" } }));
      }
    } catch (e) {
      setDetailCache(prev => ({ ...prev, [custName]: { error: e?.response?.data?.detail || String(e) } }));
    }
  };

  useEffect(() => { loadData(); }, [loadData]);

  const totals = data?.totals;
  const isToday = (data?.as_of_date || asOfDate) === todayIso();

  return (
    <SectionCard
      title="AR Aging by Customer"
      subtitle={`Invoices + Debit Memos + Credit Memos/Returns, Corporate-rate IDR. Balances as of ${data?.as_of_date || asOfDate}${isToday ? " (today, live Oracle balance)" : " (reconstructed by replaying receivable applications + adjustments up to that date)"}. Bucketed by due date. Credit memos/returns net into whichever bucket their own due date falls into — a customer's bucket can go negative when their credit memo in that bucket outweighs any invoice in the same bucket. Click a customer row to see the underlying invoices.`}
    >
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Customer</p>
          <input value={customerName} onChange={e => setCustomerName(e.target.value)}
            placeholder="Search customer…" style={{ ...INPUT, width: 220 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>As Of Date</p>
          <input type="date" value={asOfDate} onChange={e => setAsOfDate(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        {asOfDate !== todayIso() && (
          <ActionBtn icon={RefreshCw} label="Reset to Today" color="#64748b" onClick={() => setAsOfDate(todayIso())} />
        )}
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#f59e0b" onClick={loadData} disabled={loading} />
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}><Loader2 size={20} className="animate-spin" /></div>
      ) : data ? (
        <>
          {/* Bucket summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10, marginBottom: 14 }}>
            <div style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
              <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>Total Amount</p>
              <p style={{ fontSize: 13, fontWeight: 800, color: "#0891b2", fontFamily: "monospace" }}>Rp {fmtNumAp(totals?.total_amount_idr || 0)}</p>
            </div>
            {AGING_BUCKETS.map(b => (
              <div key={b.key} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
                <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{b.label}</p>
                <p style={{ fontSize: 13, fontWeight: 800, color: b.color, fontFamily: "monospace" }}>Rp {fmtNumAp(totals?.[b.key] || 0)}</p>
              </div>
            ))}
          </div>

          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1060 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#92400e,#78350f)" }}>
                    <th style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5 }}>Customer</th>
                    <th style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5, textAlign: "right" }}>Total Amount</th>
                    {AGING_BUCKETS.map(b => (
                      <th key={b.key} style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5, textAlign: "right" }}>{b.label}</th>
                    ))}
                    <th style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5, textAlign: "right" }}>Total Remaining</th>
                    <th style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5, textAlign: "right" }}>Items</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.length === 0 ? (
                    <tr>
                      <td colSpan={AGING_BUCKETS.length + 4} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No open items found
                      </td>
                    </tr>
                  ) : data.data.map((r, i) => {
                    const isExp = expandedCustomer === r.customer_name;
                    const detail = detailCache[r.customer_name];
                    return (
                    <Fragment key={r.customer_name + r.account_number}>
                    <tr
                      onClick={() => toggleCustomer(r.customer_name)}
                      style={{ background: isExp ? "rgba(245,158,11,0.12)" : (i % 2 === 0 ? "#f8fafc" : "#f1f5f9"), cursor: "pointer" }}
                      onMouseEnter={e => { if (!isExp) e.currentTarget.style.background = "rgba(245,158,11,0.08)"; }}
                      onMouseLeave={e => { if (!isExp) e.currentTarget.style.background = i % 2 === 0 ? "#f8fafc" : "#f1f5f9"; }}
                    >
                      <td style={{ ...TD, fontWeight: 700, color: "#1e293b", display: "flex", alignItems: "center", gap: 6 }}>
                        <ChevronDown size={12} style={{ color: "#94a3b8", transform: isExp ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }} />
                        {r.customer_name}
                      </td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#0891b2" }}>{fmtNumAp(r.total_amount_idr)}</td>
                      {AGING_BUCKETS.map(b => (
                        <td key={b.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: r[b.key] < 0 ? "#16a34a" : "#334155" }}>
                          {fmtNumAp(r[b.key])}
                        </td>
                      ))}
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: "#2563eb" }}>{fmtNumAp(r.total_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#94a3b8" }}>{r.item_count}</td>
                    </tr>
                    {isExp && (
                      <tr>
                        <td colSpan={AGING_BUCKETS.length + 4} style={{ padding: 0, background: "#0f172a" }}>
                          {detail === "loading" ? (
                            <div style={{ padding: 20, textAlign: "center" }}><Loader2 size={16} className="animate-spin" style={{ color: "#64748b" }} /></div>
                          ) : detail?.error ? (
                            <div style={{ padding: 14, fontSize: 12, color: "#f87171" }}>{detail.error}</div>
                          ) : !detail?.length ? (
                            <div style={{ padding: 14, fontSize: 12, color: "#94a3b8" }}>No underlying invoices found.</div>
                          ) : (
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                              <thead>
                                <tr style={{ color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                  <th style={{ padding: "6px 12px", textAlign: "left" }}>Invoice No</th>
                                  <th style={{ padding: "6px 12px", textAlign: "left" }}>Type</th>
                                  <th style={{ padding: "6px 12px", textAlign: "left" }}>Invoice Date</th>
                                  <th style={{ padding: "6px 12px", textAlign: "left" }}>Due Date</th>
                                  <th style={{ padding: "6px 12px", textAlign: "right" }}>Remaining (IDR)</th>
                                  <th style={{ padding: "6px 12px", textAlign: "right" }}>Days Overdue</th>
                                  <th style={{ padding: "6px 12px", textAlign: "left" }}>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {detail.map((d, di) => (
                                  <tr key={di} style={{ borderTop: "1px solid #1e293b", color: "#cbd5e1", fontSize: 11.5 }}>
                                    <td style={{ padding: "6px 12px", fontFamily: "monospace", color: "#60a5fa" }}>{d.invoice_number}</td>
                                    <td style={{ padding: "6px 12px" }}>{d.transaction_type}</td>
                                    <td style={{ padding: "6px 12px", fontFamily: "monospace" }}>{d.invoice_date}</td>
                                    <td style={{ padding: "6px 12px", fontFamily: "monospace" }}>{d.due_date}</td>
                                    <td style={{ padding: "6px 12px", textAlign: "right", fontFamily: "monospace", color: d.remaining_amount_idr < 0 ? "#4ade80" : "#f87171" }}>{fmtNumAp(d.remaining_amount_idr)}</td>
                                    <td style={{ padding: "6px 12px", textAlign: "right", fontFamily: "monospace" }}>{d.days_overdue ?? "—"}</td>
                                    <td style={{ padding: "6px 12px" }}>{d.status === "OP" ? "Open" : "Closed"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                    </Fragment>
                    );
                  })}
                </tbody>
                {data.data.length > 0 && (
                  <tfoot>
                    <tr style={{ background: "#D9E1F2" }}>
                      <td style={{ ...TD, fontWeight: 800, color: "#1e293b" }}>TOTAL</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{fmtNumAp(totals?.total_amount_idr)}</td>
                      {AGING_BUCKETS.map(b => (
                        <td key={b.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{fmtNumAp(totals?.[b.key])}</td>
                      ))}
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{fmtNumAp(totals?.total_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#1e293b" }}>{totals?.item_count}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>
        </>
      ) : null}
    </SectionCard>
  );
}

/* ─── COGS Report ─────────────────────────────────────────────────────────── */

const COGS_SUBTABS = [
  { id: "material-trx",  icon: Package,       label: "Material Transaction"  },
  { id: "item-cost-cmp", icon: Layers,         label: "Item Cost Component"   },
  { id: "inventory-rm",  icon: ClipboardList,  label: "Inventory RM PM"       },
];

function COGSReport() {
  const [subTab, setSubTab] = useState("material-trx");

  return (
    <div>
      {/* Sub-tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "2px solid rgba(0,0,0,0.06)", paddingBottom: 0 }}>
        {COGS_SUBTABS.map(t => {
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

      {subTab === "material-trx"  && <MaterialTransactionPanel />}
      {subTab === "item-cost-cmp" && <ItemCostComponentPanel />}
      {subTab === "inventory-rm"  && <InventoryRMPMPanel />}
    </div>
  );
}

/* ─── Inventory RM PM Panel ──────────────────────────────────────────────── */

const MAT_TYPE_ORDER = ["API", "EXCIPIENT", "API & EXCIPIENT", "PRIMARY PACKAGING", "SECONDARY PACKAGING", "PACKAGING", "RM", "OTHER"];
const MAT_TYPE_COLOR = {
  "API": "#7c3aed", "EXCIPIENT": "#0891b2", "API & EXCIPIENT": "#7c3aed",
  "PRIMARY PACKAGING": "#059669", "SECONDARY PACKAGING": "#0284c7",
  "PACKAGING": "#059669", "RM": "#64748b", "OTHER": "#64748b",
};

// Matches the 14 qty / 10 amount movement columns in sumber/ouput-inventory RMPM.xlsx
const QTY_MOVE_COLS = [
  { key: "q_purchase",          label: "Purchase",             sign: +1 },
  { key: "q_return_vendor",     label: "Return to vendor",     sign: -1 },
  { key: "q_sample_qc",         label: "Sample QC/Deduct",     sign: -1 },
  { key: "q_sample_stability",  label: "Sample Stability",     sign: -1 },
  { key: "q_sample_marketing",  label: "Sample Marketing",     sign: -1 },
  { key: "q_manual_addition",   label: "Manual Addition",      sign: +1 },
  { key: "q_wip_issue",         label: "WIP Issue",            sign: -1 },
  { key: "q_wip_return",        label: "WIP Return",           sign: +1 },
  { key: "q_repacking",         label: "Repacking",            sign:  0 },
  { key: "q_rusak",             label: "Issue Rusak",          sign: -1 },
  { key: "q_investigation_adj", label: "Investigation Adj",    sign:  0 },
  { key: "q_trial_production",  label: "Trial Production",     sign: -1 },
  { key: "q_mediafill_wo",      label: "Media Fill W/O",       sign: -1 },
  { key: "q_adj_written_off",   label: "Adj Written Off",      sign: -1 },
];
const AMT_MOVE_COLS = [
  { key: "a_purchase",          label: "Purchase" },
  { key: "a_return_supplier",   label: "Return to Supplier" },
  { key: "a_sample",            label: "Sample" },
  { key: "a_wip_issue",         label: "WIP Issue" },
  { key: "a_repacking",         label: "Repacking" },
  { key: "a_rusak",             label: "Issue Rusak" },
  { key: "a_investigation_adj", label: "Investigation Adj" },
  { key: "a_trial_production",  label: "Trial Production" },
  { key: "a_mediafill",         label: "Mediafill Adj" },
  { key: "a_written_off",       label: "Written Off" },
];

function exportInvCSV(rows, period) {
  if (!rows?.length) return;
  const staticHdrs = ["No","Material Type","Item Code","Item Name","UOM","Price/UOM","Begin Qty","Begin Amount","Price/UOM"];
  const qtyHdrs    = QTY_MOVE_COLS.map(c => c.label);
  const amtHdrs    = AMT_MOVE_COLS.map(c => c.label);
  const allHdrs    = [...staticHdrs, ...qtyHdrs, "QTY Ending", ...amtHdrs, "Amount Ending", "Movements Detail"];
  const lines = [
    "﻿" + allHdrs.join(","),
    ...rows.map((r, i) => {
      const detail = r.movements?.map(m => `${m.trx_type}:${m.qty}`).join("|") ?? "";
      return [
        i+1, r.material_type, r.item_code, r.item_name, r.uom,
        r.unit_price, r.begin_qty, r.begin_amount, r.unit_price,
        ...QTY_MOVE_COLS.map(c => r[c.key]), r.end_qty,
        ...AMT_MOVE_COLS.map(c => r[c.key]), r.end_amount,
        detail,
      ].map(v => `"${String(v ?? "").replace(/"/g,'""')}"`).join(",");
    }),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = `inventory_rm_pm_${period}.csv`; a.click();
  URL.revokeObjectURL(url);
}

async function exportInvExcel(period, includeBegin, setBusy) {
  setBusy(true);
  try {
    // client.js's axios interceptor already unwraps response.data for every
    // call in this app, so `blobData` here IS the Blob itself — not {data: Blob}.
    const blobData = await accountingApi.exportInventoryRmPm({ period, include_begin: includeBegin });
    const blob = new Blob([blobData], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `inventory_rm_pm_${period}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    // Same interceptor rejects with error.response.data directly (not the
    // full error object) — with responseType:"blob" that's a Blob containing
    // the JSON error text, not a parsed object, so `e` itself is the Blob.
    let msg = "Export failed";
    if (e instanceof Blob) {
      try { msg = JSON.parse(await e.text())?.detail || msg; } catch (_) {}
    } else if (e?.detail) {
      msg = e.detail;
    } else if (e?.message) {
      msg = e.message;
    }
    alert(msg);
  } finally {
    setBusy(false);
  }
}

function InventoryRMPMPanel() {
  const [monthInput,    setMonthInput]    = useState(currentMonthInput());
  const [includeBegin,  setIncludeBegin]  = useState(true);
  const [data,          setData]          = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [exporting,     setExporting]     = useState(false);
  const [error,         setError]         = useState(null);
  const [expandedRows,  setExpandedRows]  = useState({});
  const [sort,          setSort]          = useState({ key: null, dir: "asc" });
  const [groupPages,    setGroupPages]    = useState({});

  const period = monthInputToOPM(monthInput);
  const INV_PAGE_SIZE = 8;
  const INV_NUMERIC_KEYS = ["unit_price", "begin_qty", "begin_amount", "end_qty", "end_amount",
    ...QTY_MOVE_COLS.map(c => c.key), ...AMT_MOVE_COLS.map(c => c.key)];
  const TOTAL_COLS = 4 + 3 + 1 + QTY_MOVE_COLS.length + 1 + AMT_MOVE_COLS.length + 1 + 1; // # Code Name UOM | Beg Price/Qty/Amt | Price | qty cols+Ending | amt cols+Ending | Detail

  const loadData = useCallback(async () => {
    if (!period) return;
    setLoading(true); setError(null);
    try {
      const res = await accountingApi.getInventoryRmPm({ period, include_begin: includeBegin });
      if (res.success) { setData(res); setGroupPages({}); }
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [period, includeBegin]);

  const toggleSort = (key) => {
    setGroupPages({});
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sortRows = (rows) => {
    if (!sort.key) return rows;
    const numeric = INV_NUMERIC_KEYS.includes(sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  };

  // No filter tabs — always show all (RM/PM-only) material types, grouped.
  const grouped = {};
  (data?.data ?? []).forEach(r => {
    if (!grouped[r.material_type]) grouped[r.material_type] = [];
    grouped[r.material_type].push(r);
  });

  const groupTotal = (rows) => ({
    begin_amount: rows.reduce((s, r) => s + (r.begin_amount || 0), 0),
    end_amount:   rows.reduce((s, r) => s + (r.end_amount   || 0), 0),
    ...Object.fromEntries(QTY_MOVE_COLS.map(c => [c.key, rows.reduce((s,r) => s + (r[c.key] || 0), 0)])),
    ...Object.fromEntries(AMT_MOVE_COLS.map(c => [c.key, rows.reduce((s,r) => s + (r[c.key] || 0), 0)])),
  });

  const INPUT = { padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12, background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none" };

  const colStyle = (sign, val) => {
    if (!val) return { color: "#94a3b8" };
    if (sign === +1 && val > 0) return { color: "#16a34a", fontWeight: 700 };
    if (sign === -1 && val < 0) return { color: "#dc2626", fontWeight: 700 };
    if (val !== 0) return { color: "#d97706", fontWeight: 700 };
    return { color: "#94a3b8" };
  };

  const HDR_TH = {
    color: "#e2e8f0", background: "transparent", fontSize: 9, fontWeight: 700,
    textAlign: "center", whiteSpace: "nowrap", padding: "5px 7px",
    borderBottom: "1px solid rgba(226,232,240,0.45)", borderLeft: "1px solid rgba(226,232,240,0.25)",
  };
  const sortIndicator = (key) => sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "";

  return (
    <SectionCard>
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Period</p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="month" value={monthInput} onChange={e => setMonthInput(e.target.value)} style={{ ...INPUT, width: 160 }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: "#10b981", fontFamily: "monospace" }}>{period || "—"}</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, paddingBottom: 2 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12, color: "#475569", userSelect: "none" }}>
            <input type="checkbox" checked={includeBegin} onChange={e => setIncludeBegin(e.target.checked)}
              style={{ width: 14, height: 14, accentColor: "#10b981" }} />
            Include beginning balance <span style={{ fontSize: 10, color: "#94a3b8" }}>(slower)</span>
          </label>
        </div>
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#10b981" onClick={loadData} disabled={loading || !period} />
        {data?.data?.length > 0 && (
          <>
            <ActionBtn icon={Download} label="Export CSV" color="#64748b" onClick={() => exportInvCSV(data.data, period)} />
            <ActionBtn icon={exporting ? Loader2 : Download} label={exporting ? "Generating…" : "Export Excel (Template)"} color="#10b981"
              onClick={() => exportInvExcel(period, includeBegin, setExporting)} disabled={exporting} />
          </>
        )}
      </div>

      {error && <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626" }}>{error}</div>}

      {data && (
        <>
          {/* Table grouped by material type — matches sumber/ouput-inventory RMPM.xlsx layout.
              Bounded-height frame with its own scrollbars + sticky header, like an
              Excel freeze-panes view: header stays put while scrolling through rows. */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ maxHeight: "70vh", overflow: "auto" }}>
              <table className="inv-rmpm-table" style={{ width: "100%", borderCollapse: "collapse", minWidth: 2600 }}>
                <thead style={{ position: "sticky", top: 0, zIndex: 2 }}>
                  <tr style={{ background: "linear-gradient(135deg,#1e293b,#0f172a)" }}>
                    <th rowSpan={3} style={HDR_TH}>#</th>
                    <th rowSpan={3} style={{ ...HDR_TH, cursor: "pointer" }} onClick={() => toggleSort("item_code")}>Item Code{sortIndicator("item_code")}</th>
                    <th rowSpan={3} style={{ ...HDR_TH, cursor: "pointer" }} onClick={() => toggleSort("item_name")}>Item Name{sortIndicator("item_name")}</th>
                    <th rowSpan={3} style={HDR_TH}>UOM</th>
                    <th colSpan={3} style={HDR_TH}>Beginning Balance</th>
                    <th rowSpan={3} style={HDR_TH}>Price/UOM</th>
                    <th colSpan={QTY_MOVE_COLS.length + 1} style={HDR_TH}>Qty</th>
                    <th colSpan={AMT_MOVE_COLS.length + 1} style={HDR_TH}>Amount</th>
                    <th rowSpan={3} style={HDR_TH}>Detail</th>
                  </tr>
                  <tr style={{ background: "linear-gradient(135deg,#1e293b,#0f172a)" }}>
                    <th rowSpan={2} style={HDR_TH}>Price/UOM</th>
                    <th rowSpan={2} style={HDR_TH}>Qty Ending</th>
                    <th rowSpan={2} style={HDR_TH}>Amount Ending</th>
                    <th style={HDR_TH}>In</th>
                    <th colSpan={QTY_MOVE_COLS.length - 1} style={HDR_TH}>Out</th>
                    <th rowSpan={2} style={HDR_TH}>Qty Ending</th>
                    <th style={HDR_TH}>In</th>
                    <th colSpan={AMT_MOVE_COLS.length - 1} style={HDR_TH}>Out</th>
                    <th rowSpan={2} style={HDR_TH}>Amount Ending</th>
                  </tr>
                  <tr style={{ background: "linear-gradient(135deg,#1e293b,#0f172a)" }}>
                    {QTY_MOVE_COLS.map(c => (
                      <th key={c.key} style={{ ...HDR_TH, cursor: "pointer" }} onClick={() => toggleSort(c.key)}>{c.label}{sortIndicator(c.key)}</th>
                    ))}
                    {AMT_MOVE_COLS.map(c => (
                      <th key={c.key} style={{ ...HDR_TH, cursor: "pointer" }} onClick={() => toggleSort(c.key)}>{c.label}{sortIndicator(c.key)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(grouped).sort(([a],[b]) => MAT_TYPE_ORDER.indexOf(a)-MAT_TYPE_ORDER.indexOf(b)).map(([matType, rows]) => {
                    const tot  = groupTotal(rows);
                    const tCol = MAT_TYPE_COLOR[matType] || "#64748b";
                    const sortedGroupRows = sortRows(rows);
                    const groupPageCount = Math.max(1, Math.ceil(sortedGroupRows.length / INV_PAGE_SIZE));
                    const groupPage = Math.min(groupPages[matType] || 1, groupPageCount);
                    const pagedGroupRows = sortedGroupRows.slice((groupPage - 1) * INV_PAGE_SIZE, groupPage * INV_PAGE_SIZE);
                    return [
                      // Category header row
                      <tr key={`hdr-${matType}`} style={{ background: `${tCol}15` }}>
                        <td colSpan={TOTAL_COLS} style={{ padding: "7px 12px", fontSize: 11, fontWeight: 800, color: tCol, letterSpacing: "0.05em" }}>
                          ▸ {matType} — {rows.length} items
                        </td>
                      </tr>,
                      // Data rows
                      ...pagedGroupRows.map((r, i) => {
                        const rKey    = r.item_code;
                        const isOpen  = expandedRows[rKey];
                        return [
                          <tr key={rKey} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9", transition: "background 0.1s" }}
                            onMouseEnter={e => e.currentTarget.style.background="rgba(16,185,129,0.05)"}
                            onMouseLeave={e => e.currentTarget.style.background= i%2===0?"#f8fafc":"#f1f5f9"}
                          >
                            <td style={{ ...TD, color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>{(groupPage - 1) * INV_PAGE_SIZE + i + 1}</td>
                            <td style={{ ...TD, fontFamily: "monospace", fontWeight: 700, color: "#1e293b", whiteSpace: "nowrap" }}>{r.item_code}</td>
                            <td style={{ ...TD, fontSize: 11, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.item_name}>{r.item_name}</td>
                            <td style={{ ...TD, fontSize: 11, fontFamily: "monospace" }}>{r.uom}</td>
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace" }}>{fmtNum(r.unit_price)}</td>
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{fmtNum(r.begin_qty)}</td>
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{fmtNum(r.begin_amount)}</td>
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace" }}>{fmtNum(r.unit_price)}</td>
                            {QTY_MOVE_COLS.map(c => (
                              <td key={c.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", ...colStyle(c.sign, r[c.key]) }}>
                                {r[c.key] !== 0 ? fmtNum(r[c.key]) : <span style={{ color: "#d1d5db" }}>—</span>}
                              </td>
                            ))}
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#10b981" }}>{fmtNum(r.end_qty)}</td>
                            {AMT_MOVE_COLS.map(c => (
                              <td key={c.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace" }}>
                                {r[c.key] !== 0 ? fmtNum(r[c.key]) : <span style={{ color: "#d1d5db" }}>—</span>}
                              </td>
                            ))}
                            <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#10b981" }}>{fmtNum(r.end_amount)}</td>
                            <td style={{ ...TD }}>
                              {r.movements?.length > 0 && (
                                <button onClick={() => setExpandedRows(prev => ({ ...prev, [rKey]: !isOpen }))}
                                  style={{ fontSize: 10, padding: "2px 8px", borderRadius: 6, border: "none", cursor: "pointer", background: isOpen ? "#f1f5f9" : "rgba(16,185,129,0.1)", color: "#10b981", boxShadow: NEU.shadowOutSm }}>
                                  {isOpen ? "▲" : `▾ ${r.movements.length}`}
                                </button>
                              )}
                            </td>
                          </tr>,
                          isOpen && (
                            <tr key={`${rKey}-detail`} style={{ background: "#f8fafc" }}>
                              <td colSpan={TOTAL_COLS} style={{ padding: "6px 40px 10px" }}>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                  {r.movements?.map((m, mi) => (
                                    <span key={mi} style={{ fontSize: 10.5, padding: "3px 10px", borderRadius: 20, background: m.qty > 0 ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)", color: m.qty > 0 ? "#16a34a" : "#dc2626", fontFamily: "monospace", fontWeight: 600, border: `1px solid ${m.qty > 0 ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}` }}>
                                      {m.trx_type}: {m.qty > 0 ? "+" : ""}{fmtNum(m.qty)}
                                    </span>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          ),
                        ];
                      }),
                      // Pagination for this group
                      sortedGroupRows.length > INV_PAGE_SIZE && (
                        <tr key={`pg-${matType}`}>
                          <td colSpan={TOTAL_COLS} style={{ padding: 0 }}>
                            <Pagination
                              total={sortedGroupRows.length}
                              page={groupPage}
                              onPage={(p) => setGroupPages(prev => ({ ...prev, [matType]: p }))}
                              pageSize={INV_PAGE_SIZE}
                            />
                          </td>
                        </tr>
                      ),
                      // Group subtotal
                      <tr key={`tot-${matType}`} style={{ background: `${tCol}10`, borderTop: `2px solid ${tCol}30` }}>
                        <td colSpan={4} style={{ padding: "8px 12px", fontSize: 11, fontWeight: 800, color: tCol }}>TOTAL {matType}</td>
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#64748b" }}>—</td>
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#64748b" }}>—</td>
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#64748b" }}>{fmtNum(tot.begin_amount)}</td>
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: "#64748b" }}>—</td>
                        {QTY_MOVE_COLS.map(c => (
                          <td key={c.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: tCol }}>
                            {tot[c.key] !== 0 ? fmtNum(tot[c.key]) : <span style={{ color: "#d1d5db" }}>—</span>}
                          </td>
                        ))}
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: tCol }}>—</td>
                        {AMT_MOVE_COLS.map(c => (
                          <td key={c.key} style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: tCol }}>
                            {tot[c.key] !== 0 ? fmtNum(tot[c.key]) : <span style={{ color: "#d1d5db" }}>—</span>}
                          </td>
                        ))}
                        <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: tCol }}>{fmtNum(tot.end_amount)}</td>
                        <td />
                      </tr>,
                    ];
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8", background: "#f8fafc", borderRadius: 12, boxShadow: NEU.shadowIn }}>
          Select a period and click Load to generate the Inventory RM PM report
        </div>
      )}
    </SectionCard>
  );
}

/* ─── Item Cost Component Panel ──────────────────────────────────────────── */

const MONTHS_SHORT = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

function monthInputToOPM(monthStr) {
  // "2026-02" → "FEB-26"
  const [y, m] = (monthStr || "").split("-");
  if (!y || !m) return "";
  return `${MONTHS_SHORT[parseInt(m, 10) - 1]}-${y.slice(2)}`;
}

function currentMonthInput() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const ICC_HEADERS = [
  { key: "segment1",           label: "Item",            mono: true,  minW: 110 },
  { key: "description",        label: "Description",     mono: false, minW: 200 },
  { key: "item_type",          label: "Item Type",       mono: false, minW: 80  },
  { key: "cost_type",          label: "Cost Type",       mono: false, minW: 100 },
  { key: "cost_cmpntcls_code", label: "Component Class", mono: true,  minW: 140 },
  { key: "cost_analysis_code", label: "Analysis Code",   mono: true,  minW: 110 },
  { key: "cmpnt_cost",         label: "Comp. Cost",      mono: true,  minW: 110 },
  { key: "total_cost",         label: "Total Cost",      mono: true,  minW: 110 },
  { key: "period_code",        label: "Period",          mono: true,  minW: 90  },
];

function exportICCCSV(rows, period) {
  if (!rows?.length) return;
  const hdrs = ICC_HEADERS.map(h => h.label);
  const lines = [
    "﻿" + hdrs.join(","),
    ...rows.map(r =>
      ICC_HEADERS.map(h => {
        const v = String(r[h.key] ?? "").replace(/"/g, '""');
        return `"${v}"`;
      }).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `item_cost_component_${period}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function ItemCostComponentPanel() {
  const [monthInput, setMonthInput] = useState(currentMonthInput());
  const [data,       setData]       = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [page,       setPage]       = useState(1);
  const [sort,       setSort]       = useState({ key: null, dir: "asc" });

  const period = monthInputToOPM(monthInput);
  const ICC_PAGE_SIZE = 8;

  const loadData = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    setError(null);
    try {
      const res = await accountingApi.getItemCostComponents(period);
      if (res.success) {
        setData(res);
        setPage(1);
      } else {
        setError(res.error || "Failed to load data");
        setData(null);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [period]);

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sortedRows = useMemo(() => {
    const rows = data?.data || [];
    if (!sort.key) return rows;
    const numeric = sort.key === "cmpnt_cost" || sort.key === "total_cost";
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [data, sort]);

  const pagedRows = sortedRows.slice((page - 1) * ICC_PAGE_SIZE, page * ICC_PAGE_SIZE);

  // Build per-item row grouping for alternating bg
  const itemColors = {};
  let colorIdx = 0;
  (data?.data || []).forEach(r => {
    if (!(r.segment1 in itemColors)) {
      itemColors[r.segment1] = colorIdx++ % 2 === 0 ? "#f8fafc" : "#f1f5f9";
    }
  });

  const INPUT = {
    padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12,
    background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none",
  };

  return (
    <SectionCard>
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, marginBottom: 18 }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Period</p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="month"
              value={monthInput}
              onChange={e => setMonthInput(e.target.value)}
              style={{ ...INPUT, width: 160 }}
            />
            <span style={{ fontSize: 13, fontWeight: 700, color: "#10b981", fontFamily: "monospace", minWidth: 90 }}>{period || "—"}</span>
          </div>
        </div>
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#10b981" onClick={loadData} disabled={loading || !period} />
        {data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#10b981" onClick={() => exportICCCSV(data.data, period)} />
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626" }}>
          {error}
        </div>
      )}

      {/* Row count */}
      {data && (
        <div style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#10b981" }}>{data.count.toLocaleString()} rows</span>
          <span style={{ fontSize: 10.5, color: "#94a3b8", marginLeft: 8 }}>
            {Object.keys(itemColors).length} items · period {data.period}
          </span>
        </div>
      )}

      {/* Table */}
      <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: ICC_HEADERS.reduce((s, h) => s + h.minW, 0) }}>
            <thead>
              <tr style={{ background: "linear-gradient(135deg,#dfe5ed,#d8dee8)" }}>
                <th style={TH}>#</th>
                {ICC_HEADERS.map(h => (
                  <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort} style={{ minWidth: h.minW }} />
                ))}
              </tr>
            </thead>
            <tbody>
              {!data ? (
                <tr>
                  <td colSpan={ICC_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    Select a period and click Load to query Oracle OPM cost data
                  </td>
                </tr>
              ) : data.data.length === 0 ? (
                <tr>
                  <td colSpan={ICC_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    No cost data found for period {data.period}
                  </td>
                </tr>
              ) : (
                pagedRows.map((row, i) => {
                  const globalIndex = (page - 1) * ICC_PAGE_SIZE + i;
                  const rowBg = itemColors[row.segment1] ?? "#f8fafc";
                  return (
                    <tr key={globalIndex}
                      style={{ background: rowBg, transition: "background 0.1s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.07)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontFamily: "monospace", fontSize: 10 }}>{globalIndex + 1}</td>
                      {ICC_HEADERS.map(h => {
                        const v = row[h.key];
                        const numericCol = h.key === "cmpnt_cost" || h.key === "total_cost";
                        return (
                          <td key={h.key} style={{ ...TD, fontFamily: h.mono ? "monospace" : undefined, textAlign: numericCol ? "right" : "left", minWidth: h.minW }}>
                            {numericCol ? fmtNum(v) : (v ?? "-")}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {data && data.data.length > 0 && (
          <Pagination total={sortedRows.length} page={page} onPage={setPage} pageSize={ICC_PAGE_SIZE} />
        )}
      </div>
    </SectionCard>
  );
}

/* ─── Material Transaction Panel ─────────────────────────────────────────── */

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoStr(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

const MTX_HEADERS = [
  { key: "trx_date",       label: "Date",           mono: false },
  { key: "trx_time",       label: "Time",           mono: true  },
  { key: "organization_code", label: "Org",         mono: false },
  { key: "item_number",    label: "Item",           mono: true  },
  { key: "item_description", label: "Description",  mono: false },
  { key: "trx_type",       label: "Type",           mono: false },
  { key: "quantity",       label: "Qty",            mono: true  },
  { key: "uom",            label: "UOM",            mono: true  },
  { key: "primary_qty",    label: "Prim Qty",       mono: true  },
  { key: "primary_uom",    label: "Prim UOM",       mono: true  },
  { key: "unit_cost",      label: "Unit Cost",      mono: true  },
  { key: "trx_value",      label: "Value",          mono: true  },
  { key: "subinventory",   label: "Subinventory",   mono: false },
  { key: "transfer_subinv", label: "Transfer Sub",  mono: false },
  { key: "reference",      label: "Reference",      mono: false },
  { key: "source_code",    label: "Source",         mono: false },
];

function fmtNum(v) {
  if (v === null || v === undefined || v === "-") return "-";
  const n = Number(v);
  if (isNaN(n)) return v;
  return n.toLocaleString("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: 4 });
}

function exportCSV(rows) {
  if (!rows?.length) return;
  const headers = MTX_HEADERS.map(h => h.label);
  const lines = [
    "﻿" + headers.join(","),   // UTF-8 BOM for Excel
    ...rows.map(r =>
      MTX_HEADERS.map(h => {
        const v = r[h.key] ?? "";
        const s = String(v).replace(/"/g, '""');
        return `"${s}"`;
      }).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `material_transactions_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function MaterialTransactionPanel() {
  const [dateFrom,    setDateFrom]    = useState(daysAgoStr(7));
  const [dateTo,      setDateTo]      = useState(todayStr());
  const [orgCode,     setOrgCode]     = useState("");
  const [itemNumber,  setItemNumber]  = useState("");
  const [trxType,     setTrxType]     = useState("");
  const [limit,       setLimit]       = useState(1000);
  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);
  const [page,        setPage]        = useState(1);
  const [sort,        setSort]        = useState({ key: null, dir: "asc" });

  const MTX_PAGE_SIZE = 8;
  const MTX_NUMERIC_KEYS = ["quantity", "primary_qty", "unit_cost", "trx_value"];

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { date_from: dateFrom, date_to: dateTo, limit };
      if (orgCode.trim())    params.org_code    = orgCode.trim();
      if (itemNumber.trim()) params.item_number = itemNumber.trim();
      if (trxType.trim())    params.trx_type    = trxType.trim();
      const res = await accountingApi.getMaterialTransactions(params);
      if (res.success) {
        setData(res);
        setPage(1);
      } else {
        setError(res.error || "Failed to load data");
        setData(null);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, orgCode, itemNumber, trxType, limit]);

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sortedRows = useMemo(() => {
    const rows = data?.data || [];
    if (!sort.key) return rows;
    const numeric = MTX_NUMERIC_KEYS.includes(sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [data, sort]);

  const pagedRows = sortedRows.slice((page - 1) * MTX_PAGE_SIZE, page * MTX_PAGE_SIZE);

  const INPUT = {
    padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12,
    background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b",
    outline: "none", width: "100%",
  };

  return (
    <SectionCard>
      {/* Filter Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr auto auto auto", gap: 10, marginBottom: 18, alignItems: "end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Date From</p>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Date To</p>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Organization</p>
          <input placeholder="e.g. CKD" value={orgCode} onChange={e => setOrgCode(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Item Number</p>
          <input placeholder="partial search" value={itemNumber} onChange={e => setItemNumber(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Transaction Type</p>
          <input placeholder="partial search" value={trxType} onChange={e => setTrxType(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Max Rows</p>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{ ...INPUT, width: 90 }}>
            {[500, 1000, 2000, 5000].map(n => <option key={n} value={n}>{n.toLocaleString()}</option>)}
          </select>
        </div>
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#10b981" onClick={loadData} disabled={loading} />
        {data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#10b981" onClick={() => exportCSV(data.data)} />
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626" }}>
          {error}
        </div>
      )}

      {/* Row count */}
      {data && (
        <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#10b981" }}>{data.count.toLocaleString()} rows</span>
          {data.count === data.limit && (
            <span style={{ fontSize: 10.5, color: "#f59e0b" }}>⚠ Limit reached — increase Max Rows or narrow date range</span>
          )}
        </div>
      )}

      {/* Table */}
      <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1600 }}>
            <thead>
              <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                <th style={TH}>#</th>
                {MTX_HEADERS.map(h => (
                  <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort} />
                ))}
              </tr>
            </thead>
            <tbody>
              {!data ? (
                <tr>
                  <td colSpan={MTX_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    Set the date range and click Load to query Oracle EBS material transactions
                  </td>
                </tr>
              ) : data.data.length === 0 ? (
                <tr>
                  <td colSpan={MTX_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    No transactions found for the selected period
                  </td>
                </tr>
              ) : (
                pagedRows.map((row, i) => {
                  const globalIndex = (page - 1) * MTX_PAGE_SIZE + i;
                  return (
                    <tr key={row.transaction_id ?? globalIndex}
                      style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9", transition: "background 0.1s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.05)"}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f8fafc" : "#f1f5f9"}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontFamily: "monospace", fontSize: 10 }}>{globalIndex + 1}</td>
                      {MTX_HEADERS.map(h => {
                        const v = row[h.key];
                        const isNum = MTX_NUMERIC_KEYS.includes(h.key);
                        return (
                          <td key={h.key} style={{ ...TD, fontFamily: h.mono ? "monospace" : undefined, textAlign: isNum ? "right" : "left" }}>
                            {isNum ? fmtNum(v) : (v ?? "-")}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {data && data.data.length > 0 && (
          <Pagination total={sortedRows.length} page={page} onPage={setPage} pageSize={MTX_PAGE_SIZE} />
        )}
      </div>
    </SectionCard>
  );
}

/* ─── Shared components ───────────────────────────────────────────────────── */

const TH = {
  padding: "10px 12px", textAlign: "left", fontSize: 10, fontWeight: 700,
  color: "#374151", textTransform: "uppercase", letterSpacing: "0.06em",
  borderBottom: "2px solid rgba(0,0,0,0.06)", whiteSpace: "nowrap",
};
const TD = {
  padding: "8px 12px", fontSize: 12, color: "#334155", whiteSpace: "nowrap",
};

function SectionCard({ title, subtitle, action, children }) {
  return (
    <div style={{ borderRadius: 20, background: NEU.bg, boxShadow: NEU.shadowOut }}>
      {(title || action) && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)",
        }}>
          <div>
            {title && <h3 style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", margin: 0 }}>{title}</h3>}
            {subtitle && <p style={{ fontSize: 11, color: "#94a3b8", margin: "2px 0 0" }}>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

function SortableTH({ label, sortKey, sort, onSort, style }) {
  const active = sort.key === sortKey;
  return (
    <th
      style={{ ...TH, ...style, cursor: sortKey ? "pointer" : "default", userSelect: "none" }}
      onClick={() => sortKey && onSort(sortKey)}
    >
      {label} {active && (sort.dir === "asc" ? "▲" : "▼")}
    </th>
  );
}

function Pagination({ total, page, onPage, pageSize = 8 }) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 14px", background: NEU.bg,
    }}>
      <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button onClick={() => onPage(Math.max(1, page - 1))} disabled={page === 1}
          style={{
            padding: 5, borderRadius: 7, border: "none", cursor: page === 1 ? "not-allowed" : "pointer",
            background: NEU.bg, color: page === 1 ? "#cbd5e1" : "#475569", boxShadow: NEU.shadowOutSm,
          }}>
          <ChevronLeft size={13} />
        </button>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#1e293b", padding: "0 6px" }}>{page} / {pages}</span>
        <button onClick={() => onPage(Math.min(pages, page + 1))} disabled={page === pages}
          style={{
            padding: 5, borderRadius: 7, border: "none", cursor: page === pages ? "not-allowed" : "pointer",
            background: NEU.bg, color: page === pages ? "#cbd5e1" : "#475569", boxShadow: NEU.shadowOutSm,
          }}>
          <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color = "#2563eb", onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "8px 16px", borderRadius: 10, border: "none",
        background: disabled ? "#94a3b8" : color,
        color: "#fff", fontSize: 12, fontWeight: 700,
        cursor: disabled ? "not-allowed" : "pointer",
        boxShadow: disabled ? "none" : NEU.shadowOutSm,
        whiteSpace: "nowrap",
      }}
    >
      <Icon size={13} className={disabled ? "animate-spin" : ""} />{label}
    </button>
  );
}

function DataTable({ headers, rows, placeholder }) {
  return (
    <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
            {headers.map((h) => (
              <th key={h} style={TH}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows?.length ? (
            rows.map((row, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}>
                {row.map((cell, j) => (
                  <td key={j} style={{ ...TD, fontWeight: j === 0 ? 700 : 500 }}>{cell}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                {placeholder || "No data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
