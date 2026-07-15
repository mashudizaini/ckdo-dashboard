import { useState, useCallback, useMemo } from "react";
import {
  FileText, DollarSign, FileDown, RefreshCw,
  BarChart2, Package, Download, Search, Loader2, Layers, ClipboardList,
  AlertTriangle, ChevronLeft, ChevronRight,
} from "lucide-react";
import CoretaxDownloader from "./CoretaxDownloader";
import APAutoInvoice from "./APAutoInvoice";
import { accountingApi } from "@/api/dashboard";

const NEU = {
  bg:          "#e8edf5",
  shadowOut:   "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn:    "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
};

const TABS = [
  { id: "ap-invoice", icon: FileText,   label: "AP Autoinvoice",    color: "#2563eb" },
  { id: "cogs",       icon: BarChart2,  label: "COGS Report",       color: "#10b981" },
  { id: "profit",     icon: DollarSign, label: "AP Outstanding",    color: "#3b82f6" },
  { id: "ar",         icon: FileText,   label: "AR Outstanding",    color: "#f59e0b" },
  { id: "coretax",    icon: FileDown,   label: "Coretax Download",  color: "#8b5cf6" },
];

export default function AccountingDashboard() {
  const [active, setActive] = useState("ap-invoice");

  return (
    <div className="p-6 space-y-4">
      {/* Navigation Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {TABS.map((tab) => {
          const isActive = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActive(tab.id)}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "14px 16px", borderRadius: 16, border: "none",
                background: NEU.bg, cursor: "pointer",
                boxShadow: isActive ? NEU.shadowIn : NEU.shadowOut,
                transform: isActive ? "scale(0.98)" : "scale(1)",
                transition: "all 0.2s ease",
              }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: isActive ? tab.color : NEU.bg,
                boxShadow: isActive ? "none" : NEU.shadowOutSm,
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.2s ease",
              }}>
                <tab.icon size={16} style={{ color: isActive ? "#fff" : tab.color }} />
              </div>
              <span style={{
                fontSize: 13, fontWeight: 700, letterSpacing: "0.01em",
                color: isActive ? tab.color : "#475569",
                transition: "color 0.2s ease",
              }}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      {active === "ap-invoice" && <APAutoInvoice />}
      {active === "cogs"       && <COGSReport />}

      {active === "profit" && <APOutstandingPanel />}

      {active === "ar" && <AROutstandingPanel />}

      {active === "coretax" && <CoretaxDownloader />}
    </div>
  );
}

/* ─── AP Outstanding Panel ───────────────────────────────────────────────── */

const AP_HEADERS = [
  { key: "operating_unit",       label: "Operating Unit",    width: 140 },
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
  { key: "original_amount_idr",  label: "Orig Amt (IDR)",    width: 130, num: true },
  { key: "remaining_amount_idr", label: "Remaining (IDR)",   width: 130, num: true },
  { key: "original_amount_orig", label: "Orig Amt (FC)",     width: 110, num: true },
  { key: "remaining_amount_orig",label: "Remaining (FC)",    width: 110, num: true },
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
  const today = new Date().toISOString().slice(0, 10);
  const [asOfDate,       setAsOfDate]       = useState(today);
  const [supplierName,   setSupplierName]   = useState("");
  const [ouFilter,       setOuFilter]       = useState("");
  const [payStatusFilter,setPayStatusFilter] = useState("ALL");
  const [limit,          setLimit]          = useState(500);
  const [data,           setData]           = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [search,         setSearch]         = useState("");
  const [page,           setPage]           = useState(1);
  const [sort,           setSort]           = useState({ key: null, dir: "asc" });

  const AP_PAGE_SIZE = 10;
  const AP_NUMERIC_KEYS = ["original_amount_idr", "remaining_amount_idr", "original_amount_orig", "remaining_amount_orig"];

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = {
        limit,
        ...(asOfDate      && { as_of_date:      asOfDate      }),
        ...(supplierName  && { supplier_name:   supplierName  }),
        ...(ouFilter      && { operating_unit:  ouFilter      }),
        ...(payStatusFilter && payStatusFilter !== "ALL" && { payment_status: payStatusFilter }),
      };
      const res = await accountingApi.getApOutstanding(params);
      if (res.success) { setData(res); setPage(1); }
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [asOfDate, supplierName, ouFilter, payStatusFilter, limit]);

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const filteredRows = data?.data?.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.supplier_name        || "").toLowerCase().includes(q)
        || (r.transaction_number   || "").toLowerCase().includes(q)
        || (r.coa                  || "").toLowerCase().includes(q)
        || (r.coa_descpt           || "").toLowerCase().includes(q)
        || (r.operating_unit       || "").toLowerCase().includes(q);
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

  const pagedRows = rows.slice((page - 1) * AP_PAGE_SIZE, page * AP_PAGE_SIZE);

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
    return i % 2 === 0 ? "#f0f3f9" : "#e8edf5";
  };

  const sm = data?.summary;

  return (
    <SectionCard>
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>As of Date</p>
          <input type="date" value={asOfDate} onChange={e => setAsOfDate(e.target.value)} style={{ ...INPUT, width: 150 }} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Supplier</p>
          <input value={supplierName} onChange={e => setSupplierName(e.target.value)}
            placeholder="Search supplier…" style={{ ...INPUT, width: 180 }}
            onKeyDown={e => e.key === "Enter" && loadData()} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Operating Unit</p>
          <input value={ouFilter} onChange={e => setOuFilter(e.target.value)}
            placeholder="Filter OU…" style={{ ...INPUT, width: 150 }}
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
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#3b82f6" onClick={loadData} disabled={loading} />
        {data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#3b82f6" onClick={() => exportApCSV(data.data)} />
        )}
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
            {[
              { label: "Total Invoices",       val: (data.count || 0).toLocaleString(),               color: "#3b82f6" },
              { label: "Not Paid",             val: (sm?.not_paid_count    || 0).toLocaleString(),    color: "#dc2626" },
              { label: "Partially Paid",       val: (sm?.partial_paid_count|| 0).toLocaleString(),    color: "#d97706" },
              { label: "Total Outstanding",    val: "Rp " + fmtNum(sm?.total_outstanding_idr || 0),   color: "#2563eb" },
              { label: "Not Paid Amount",      val: "Rp " + fmtNum(sm?.not_paid_idr          || 0),   color: "#dc2626" },
            ].map(c => (
              <div key={c.label} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
                <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{c.label}</p>
                <p style={{ fontSize: 13, fontWeight: 800, color: c.color, fontFamily: "monospace" }}>{c.val}</p>
              </div>
            ))}
          </div>

          {/* Client-side search */}
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
              placeholder="Filter by supplier / invoice / COA / OU…"
              style={{ ...INPUT, width: 340 }} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              Showing {rows.length.toLocaleString()} of {data.count.toLocaleString()} rows
            </span>
          </div>

          {/* Table */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1800 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#1e3a5f,#1e40af)" }}>
                    <th style={{ ...TH, color: "#bfdbfe", background: "transparent", fontSize: 9.5 }}>#</th>
                    {AP_HEADERS.map(h => (
                      <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort}
                        style={{ color: "#bfdbfe", background: "transparent", fontSize: 9.5, minWidth: h.width, whiteSpace: "nowrap" }} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.length === 0 ? (
                    <tr>
                      <td colSpan={AP_HEADERS.length + 1} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No records found
                      </td>
                    </tr>
                  ) : pagedRows.map((r, i) => {
                    const globalIndex = (page - 1) * AP_PAGE_SIZE + i;
                    return (
                    <tr key={globalIndex}
                      style={{ background: rowBg(r, i) }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(59,130,246,0.07)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg(r, i)}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>{globalIndex + 1}</td>
                      <td style={{ ...TD, fontSize: 11, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.operating_unit}>{r.operating_unit}</td>
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
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700 }}>{fmtNum(r.original_amount_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 800, color: r.remaining_amount_idr > 0 ? "#dc2626" : "#16a34a" }}>{fmtNum(r.remaining_amount_idr)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{r.original_amount_orig != null ? fmtNum(r.original_amount_orig) : "—"}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", color: "#64748b" }}>{r.remaining_amount_orig != null ? fmtNum(r.remaining_amount_orig) : "—"}</td>
                      <td style={{ ...TD, fontSize: 11, color: "#64748b", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.description}>{r.description}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {rows.length > 0 && (
              <Pagination total={rows.length} page={page} onPage={setPage} pageSize={AP_PAGE_SIZE} />
            )}
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div style={{ padding: "48px", textAlign: "center", background: "#f0f3f9", borderRadius: 12, boxShadow: NEU.shadowIn }}>
          <DollarSign size={28} style={{ color: "#3b82f6", marginBottom: 10 }} />
          <p style={{ fontSize: 13, fontWeight: 600, color: "#475569", margin: 0 }}>Set as-of date and click Load to fetch AP outstanding data</p>
          <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>Default: today · Excludes fully Paid invoices</p>
        </div>
      )}
    </SectionCard>
  );
}

/* ─── AR Outstanding Panel ───────────────────────────────────────────────── */

const AR_HEADERS = [
  { key: "customer_name",    label: "Customer",        width: 200 },
  { key: "account_number",   label: "Account #",       width: 100 },
  { key: "invoice_number",   label: "Invoice No",      width: 120 },
  { key: "transaction_type", label: "Type",            width: 60  },
  { key: "invoice_date",     label: "Invoice Date",    width: 100 },
  { key: "due_date",         label: "Due Date",        width: 100 },
  { key: "currency",         label: "Cur",             width: 45  },
  { key: "original_amount",  label: "Original Amt",    width: 120, num: true },
  { key: "remaining_amount", label: "Remaining Amt",   width: 120, num: true },
  { key: "days_overdue",     label: "Days Overdue",    width: 90,  num: true },
  { key: "status",           label: "Status",          width: 60  },
  { key: "operating_unit",   label: "OU",              width: 120 },
  { key: "comments",         label: "Comments",        width: 160 },
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
  const [customerName,   setCustomerName]   = useState("");
  const [invoiceNumber,  setInvoiceNumber]  = useState("");
  const [dateFrom,       setDateFrom]       = useState("");
  const [dateTo,         setDateTo]         = useState("");
  const [statusFilter,   setStatusFilter]   = useState("OP");
  const [limit,          setLimit]          = useState(500);
  const [data,           setData]           = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [search,         setSearch]         = useState("");
  const [page,           setPage]           = useState(1);
  const [sort,           setSort]           = useState({ key: null, dir: "asc" });

  const AR_PAGE_SIZE = 10;
  const AR_NUMERIC_KEYS = ["original_amount", "remaining_amount", "days_overdue"];

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = {
        status: statusFilter,
        limit,
        ...(customerName  && { customer_name:  customerName  }),
        ...(invoiceNumber && { invoice_number: invoiceNumber }),
        ...(dateFrom      && { date_from:       dateFrom      }),
        ...(dateTo        && { date_to:         dateTo        }),
      };
      const res = await accountingApi.getArOutstanding(params);
      if (res.success) { setData(res); setPage(1); }
      else { setError(res.error || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e)); setData(null);
    } finally { setLoading(false); }
  }, [customerName, invoiceNumber, dateFrom, dateTo, statusFilter, limit]);

  const toggleSort = (key) => {
    setPage(1);
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

  const pagedRows = rows.slice((page - 1) * AR_PAGE_SIZE, page * AR_PAGE_SIZE);

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

  return (
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
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#f59e0b" onClick={loadData} disabled={loading} />
        {data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#f59e0b" onClick={() => exportArCSV(data.data)} />
        )}
      </div>

      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
            {[
              { label: "Open Invoices",     val: (sm?.open_invoice_count || 0).toLocaleString(),    color: "#f59e0b" },
              { label: "Overdue Count",      val: (sm?.overdue_count     || 0).toLocaleString(),    color: "#dc2626" },
              { label: "Total Outstanding",  val: "Rp " + fmtNum(sm?.total_remaining || 0),         color: "#2563eb" },
              { label: "Total Overdue",      val: "Rp " + fmtNum(sm?.total_overdue   || 0),         color: "#dc2626" },
            ].map(c => (
              <div key={c.label} style={{ background: NEU.bg, borderRadius: 12, padding: "10px 14px", boxShadow: NEU.shadowOutSm }}>
                <p style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{c.label}</p>
                <p style={{ fontSize: 13, fontWeight: 800, color: c.color, fontFamily: "monospace" }}>{c.val}</p>
              </div>
            ))}
          </div>

          {/* Client-side search */}
          <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
              placeholder="Filter results by customer / invoice / account…"
              style={{ ...INPUT, width: 320 }} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              Showing {rows.length.toLocaleString()} of {data.count.toLocaleString()} rows
            </span>
          </div>

          {/* Table */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1400 }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#92400e,#78350f)" }}>
                    <th style={{ ...TH, color: "#fef3c7", background: "transparent", fontSize: 9.5 }}>#</th>
                    {AR_HEADERS.map(h => (
                      <SortableTH key={h.key} label={h.label} sortKey={h.key} sort={sort} onSort={toggleSort}
                        style={{ color: "#fef3c7", background: "transparent", fontSize: 9.5, minWidth: h.width, whiteSpace: "nowrap" }} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.length === 0 ? (
                    <tr>
                      <td colSpan={AR_HEADERS.length + 1} style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                        No records found
                      </td>
                    </tr>
                  ) : pagedRows.map((r, i) => {
                    const globalIndex = (page - 1) * AR_PAGE_SIZE + i;
                    return (
                    <tr key={globalIndex}
                      style={{ background: rowBg(r) || (i % 2 === 0 ? "#f0f3f9" : "#e8edf5") }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(245,158,11,0.08)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg(r) || (i % 2 === 0 ? "#f0f3f9" : "#e8edf5")}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>{globalIndex + 1}</td>
                      <td style={{ ...TD, fontWeight: 700, color: "#1e293b", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.customer_name}>{r.customer_name}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.account_number}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontWeight: 700, color: "#2563eb", whiteSpace: "nowrap" }}>{r.invoice_number}</td>
                      <td style={{ ...TD, fontSize: 11 }}>{r.transaction_type}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.invoice_date}</td>
                      <td style={{ ...TD, fontFamily: "monospace", fontSize: 11 }}>{r.due_date}</td>
                      <td style={{ ...TD, fontSize: 11, fontWeight: 600 }}>{r.currency}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace" }}>{fmtNum(r.original_amount)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", fontWeight: 700, color: r.remaining_amount > 0 ? "#dc2626" : "#16a34a" }}>{fmtNum(r.remaining_amount)}</td>
                      <td style={{ ...TD, textAlign: "right", fontFamily: "monospace", ...daysStyle(r.days_overdue) }}>
                        {r.days_overdue > 0 ? `+${r.days_overdue}d` : r.days_overdue === 0 ? "Today" : r.days_overdue < 0 ? `${Math.abs(r.days_overdue)}d left` : "—"}
                      </td>
                      <td style={{ ...TD }}>{statusBadge(r.status)}</td>
                      <td style={{ ...TD, fontSize: 11, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.operating_unit}>{r.operating_unit}</td>
                      <td style={{ ...TD, fontSize: 11, color: "#64748b", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.comments}>{r.comments}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {rows.length > 0 && (
              <Pagination total={rows.length} page={page} onPage={setPage} pageSize={AR_PAGE_SIZE} />
            )}
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div style={{ padding: "48px", textAlign: "center", background: "#f0f3f9", borderRadius: 12, boxShadow: NEU.shadowIn }}>
          <AlertTriangle size={28} style={{ color: "#f59e0b", marginBottom: 10 }} />
          <p style={{ fontSize: 13, fontWeight: 600, color: "#475569", margin: 0 }}>Set filters and click Load to fetch AR outstanding data</p>
          <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>Default: Open invoices (INV + DM), up to 500 rows</p>
        </div>
      )}
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
    const res = await accountingApi.exportInventoryRmPm({ period, include_begin: includeBegin });
    const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `inventory_rm_pm_${period}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(e?.response?.data?.detail || "Export failed");
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
    borderBottom: "1px solid rgba(255,255,255,0.08)", borderLeft: "1px solid rgba(255,255,255,0.05)",
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
          {/* Table grouped by material type — matches sumber/ouput-inventory RMPM.xlsx layout */}
          <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 2600 }}>
                <thead>
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
                          <tr key={rKey} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5", transition: "background 0.1s" }}
                            onMouseEnter={e => e.currentTarget.style.background="rgba(16,185,129,0.05)"}
                            onMouseLeave={e => e.currentTarget.style.background= i%2===0?"#f0f3f9":"#e8edf5"}
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
                                  style={{ fontSize: 10, padding: "2px 8px", borderRadius: 6, border: "none", cursor: "pointer", background: isOpen ? "#e8edf5" : "rgba(16,185,129,0.1)", color: "#10b981", boxShadow: NEU.shadowOutSm }}>
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
        <div style={{ padding: "40px", textAlign: "center", fontSize: 12, color: "#94a3b8", background: "#f0f3f9", borderRadius: 12, boxShadow: NEU.shadowIn }}>
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
      itemColors[r.segment1] = colorIdx++ % 2 === 0 ? "#f0f3f9" : "#e8edf5";
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
                  const rowBg = itemColors[row.segment1] ?? "#f0f3f9";
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
                      style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5", transition: "background 0.1s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.05)"}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"}
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
              <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
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
