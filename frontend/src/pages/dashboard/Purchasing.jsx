import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FileText, History, Banknote, Truck, BookOpen, BarChart2,
  RefreshCw, Plus, Trash2, X, Loader2, CheckCircle, Search, Filter,
  Download, ChevronLeft, ChevronRight, TrendingUp, TrendingDown, ChevronDown,
} from "lucide-react";
import * as XLSX from "xlsx";
import {
  LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { purchasingApi } from "@/api/dashboard";
import { SortableTH, toggleSort, sortRows } from "@/components/SortableTH";

/* ─── Tab definitions ─────────────────────────────── */

const TABS = [
  { id: "open-pr",             icon: FileText,  color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Open PR"             },
  { id: "purchase-history",    icon: History,   color: "text-orange-400", bg: "bg-orange-500/10", activeBorder: "border-orange-500/40", label: "Purchase History"    },
  { id: "price-analysis",      icon: BarChart2, color: "text-cyan-400",   bg: "bg-cyan-500/10",   activeBorder: "border-cyan-500/40",   label: "PO Price Analysis"      },
  { id: "monthly-spend",       icon: Banknote,  color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Monthly Spend"       },
  { id: "active-suppliers",    icon: Truck,     color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Active Suppliers"    },
  { id: "manufacturer-master", icon: BookOpen,  color: "text-purple-400", bg: "bg-purple-500/10", activeBorder: "border-purple-500/40", label: "Manufacturer Master" },
];

/* ─── Main Page ───────────────────────────────────── */

export default function PurchasingDashboard() {
  const navigate = useNavigate();
  const location = useLocation();

  const activeId = TABS.find((t) => location.pathname.includes(t.id))?.id ?? "open-pr";

  useEffect(() => {
    if (location.pathname === "/dashboard/purchasing" || location.pathname === "/dashboard/purchasing/") {
      navigate("/dashboard/purchasing/open-pr", { replace: true });
    }
  }, []);

  return (
    <div className="p-6 space-y-4">
      {/* Section Panels — navigation now lives in the left sidebar tree menu */}
      {activeId === "open-pr"             && <OpenPRSection />}
      {activeId === "purchase-history"    && <PurchaseHistorySection />}
      {activeId === "price-analysis"      && <PriceAnalysisSection />}
      {activeId === "monthly-spend"       && <MonthlySpendSection />}
      {activeId === "active-suppliers"    && <ActiveSuppliersSection />}
      {activeId === "manufacturer-master" && <ManufacturerMasterSection />}
    </div>
  );
}

/* ─── Section: Open PR ────────────────────────────── */

const PR_STATUS_STYLE = {
  "APPROVED":   { label: "Approved",   cls: "bg-green-500/15 text-green-400 border-green-500/30" },
  "IN PROCESS": { label: "In Process", cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30" },
  "INCOMPLETE": { label: "Incomplete", cls: "bg-gray-500/15 text-gray-400 border-gray-500/30" },
  "REJECTED":   { label: "Rejected",   cls: "bg-red-500/15 text-red-400 border-red-500/30" },
};

function AgingBadge({ days }) {
  if (days == null) return <span className="text-gray-600">—</span>;
  const d = Number(days);
  if (d === 0) return <span className="text-gray-400">{d}d</span>;
  if (d <= 7)  return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-500/15 text-yellow-400 border border-yellow-500/30">{d}d</span>;
  return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/30">{d}d</span>;
}

function PRStatusBadge({ status }) {
  const s = PR_STATUS_STYLE[status?.toUpperCase()] || { label: status, cls: "bg-gray-700 text-gray-400 border-gray-600" };
  return <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${s.cls}`}>{s.label}</span>;
}

const OPEN_PR_PAGE_SIZE = 8;

const OPEN_PR_COLS = [
  { key: "pr_number",           label: "PR Number" },
  { key: "po_number",           label: "PO Number" },
  { key: "line_num",            label: "Line",               numeric: true },
  { key: "item_code",           label: "Item Code" },
  { key: "item_description",    label: "Item Description" },
  { key: "category_code",       label: "Category" },
  { key: "material_type",       label: "Type" },
  { key: "supplier_name",       label: "Supplier" },
  { key: "payment_terms",       label: "Payment Terms" },
  { key: "requestor",           label: "Requestor" },
  { key: "uom",                  label: "UoM" },
  { key: "quantity",            label: "Qty",                numeric: true },
  { key: "currency_code",       label: "Currency" },
  { key: "unit_price_orig",     label: "Unit Price",         numeric: true },
  { key: "unit_price_idr",      label: "Unit Price IDR",     numeric: true },
  { key: "last_purchase_price", label: "Last Purchase Price", numeric: true },
  { key: "total_value_orig",    label: "Total Value",        numeric: true },
  { key: "total_value_idr",     label: "Total Value IDR",    numeric: true },
  { key: "pr_status",           label: "Status" },
  { key: "creation_date",       label: "Created" },
  { key: "due_date",            label: "Due Date" },
  { key: "aging_days",          label: "Aging",              numeric: true },
];

function RequestorMultiSelect({ options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClickOutside = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const toggle = (name) => {
    onChange(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name]);
  };

  const label = selected.length === 0 ? "— All —" : selected.length === 1 ? selected[0] : `${selected.length} selected`;

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className={`${SELECT} text-left flex items-center justify-between`}>
        <span className={`truncate ${selected.length ? "" : "text-gray-500"}`}>{label}</span>
        <ChevronDown size={14} className="text-gray-500 shrink-0 ml-1" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto rounded-md border border-gray-700 bg-gray-800 shadow-lg py-1">
          {options.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-500">No data</p>
          ) : options.map((name) => (
            <label key={name} className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-700 cursor-pointer">
              <input type="checkbox" checked={selected.includes(name)} onChange={() => toggle(name)}
                className="rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-0" />
              {name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function OpenPRSection() {
  const today = new Date();
  const pad2  = (n) => String(n).padStart(2, "0");
  const toISO = (d) => `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`;
  const firstOfYear = `${today.getFullYear()}-01-01`;

  const [f, setF] = useState({
    pr_status: "", material_type: "", pr_number: "",
    item_code: "", item_desc: "", requestor: [],
    currency_code: "", date_from: firstOfYear, date_to: toISO(today),
    exchange_rate_type: "Corporate",
  });
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const [rows,     setRows]     = useState([]);
  const [error,    setError]    = useState("");
  const [page,     setPage]     = useState(1);
  const [sort,     setSort]     = useState({ key: null, dir: "asc" });
  const [matTypes, setMatTypes] = useState([]);
  const [requestors, setRequestors] = useState([]);

  useEffect(() => {
    purchasingApi.getMaterialTypes().then(r => { if (r.success) setMatTypes(r.data ?? []); }).catch(() => {});
    purchasingApi.getRequestors().then(r => { if (r.success) setRequestors((r.data ?? []).map(d => d.name)); }).catch(() => {});
  }, []);

  const setFld = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));

  const handleSearch = async () => {
    setLoading(true); setError(""); setPage(1);
    try {
      const p = {};
      if (f.pr_status)          p.pr_status          = f.pr_status;
      if (f.material_type)      p.material_type      = f.material_type;
      if (f.pr_number)          p.pr_number          = f.pr_number;
      if (f.item_code)          p.item_code          = f.item_code;
      if (f.item_desc)          p.item_desc          = f.item_desc;
      if (f.requestor.length)   p.requestor          = f.requestor.join(",");
      if (f.currency_code)      p.currency_code      = f.currency_code;
      if (f.date_from)          p.date_from          = f.date_from;
      if (f.date_to)            p.date_to            = f.date_to;
      if (f.exchange_rate_type) p.exchange_rate_type = f.exchange_rate_type;
      const r = await purchasingApi.getOpenPR(p);
      if (r?.success) {
        setRows(r.data || []);
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
    setF({ pr_status: "", material_type: "", pr_number: "", item_code: "",
           item_desc: "", requestor: [], currency_code: "",
           date_from: firstOfYear, date_to: toISO(today), exchange_rate_type: "Corporate" });
    setRows([]); setSearched(false); setError(""); setPage(1);
  };

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sorted = useMemo(() => {
    if (!sort.key) return rows;
    const col = OPEN_PR_COLS.find(c => c.key === sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (col?.numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [rows, sort]);

  const handleDownload = () => {
    const data = sorted.map(r => [
      r.pr_number, r.po_number || "-", r.line_num, r.item_code, r.item_description,
      r.category_code, r.material_type, r.supplier_name || "-", r.payment_terms || "-",
      r.requestor, r.uom, r.quantity,
      r.currency_code, r.unit_price_orig, r.unit_price_idr, r.last_purchase_price,
      r.total_value_orig, r.total_value_idr,
      r.pr_status, r.creation_date, r.due_date, r.aging_days,
    ]);
    const amountCols = [11, 13, 14, 15, 16, 17];
    downloadExcel(`open_pr_${toISO(today)}`, OPEN_PR_COLS.map(c => c.label), data, amountCols);
  };

  const paged = sorted.slice((page - 1) * OPEN_PR_PAGE_SIZE, page * OPEN_PR_PAGE_SIZE);
  const TH = "px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap cursor-pointer select-none hover:text-gray-300";
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";

  return (
    <div className="space-y-3">
      {/* Filter Panel — no title/subtitle */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
        {error && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <X size={12} />{error}
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-3">
          <Field label="PR Status">
            <select className={SELECT} value={f.pr_status} onChange={setFld("pr_status")}>
              <option value="">— All —</option>
              <option value="IN PROCESS">In Process</option>
              <option value="INCOMPLETE">Incomplete</option>
              <option value="REJECTED">Rejected</option>
              <option value="APPROVED">Approved</option>
            </select>
          </Field>
          <Field label="Material Type">
            <select className={SELECT} value={f.material_type} onChange={setFld("material_type")}>
              <option value="">— All —</option>
              {matTypes.map(t => <option key={t.tag} value={t.tag}>{t.tag}</option>)}
            </select>
          </Field>
          <Field label="Currency">
            <select className={SELECT} value={f.currency_code} onChange={setFld("currency_code")}>
              <option value="">— All —</option>
              <option value="IDR">IDR</option>
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
            </select>
          </Field>
          <Field label="Exchange Rate Type">
            <input className={INPUT} value={f.exchange_rate_type} onChange={setFld("exchange_rate_type")} placeholder="Corporate" />
          </Field>
          <Field label="PR Number">
            <input className={INPUT} value={f.pr_number} onChange={setFld("pr_number")} placeholder="e.g. 2510…" />
          </Field>
          <Field label="Item Code">
            <input className={INPUT} value={f.item_code} onChange={setFld("item_code")} placeholder="e.g. RM-0001" />
          </Field>
          <Field label="Item Description">
            <input className={INPUT} value={f.item_desc} onChange={setFld("item_desc")} placeholder="partial search…" />
          </Field>
          <Field label="Requestor">
            <RequestorMultiSelect options={requestors} selected={f.requestor}
              onChange={(next) => setF(p => ({ ...p, requestor: next }))} />
          </Field>
          <Field label="Date From">
            <input className={INPUT} type="date" value={f.date_from} onChange={setFld("date_from")} />
          </Field>
          <Field label="Date To">
            <input className={INPUT} type="date" value={f.date_to} onChange={setFld("date_to")} />
          </Field>
        </div>
      </div>

      {/* Reset/Search — below the filter panel */}
      <div className="flex items-center justify-end gap-2">
        <ActionBtn icon={RefreshCw} label="Reset" color="bg-gray-700 hover:bg-gray-600" onClick={handleReset} />
        <ActionBtn icon={loading ? Loader2 : Search} label="Search" color="bg-blue-600 hover:bg-blue-700" onClick={handleSearch} />
      </div>

      {/* Results Table */}
      {searched && (
        <div className="rounded-lg border border-gray-800">
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/50">
            <span className="text-xs text-gray-500">{rows.length} lines</span>
            {rows.length > 0 && (
              <button onClick={handleDownload}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
                <Download size={12} /> Download Excel
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-800/60">
                  {OPEN_PR_COLS.map(c => (
                    <th key={c.key} className={TH} onClick={() => toggleSort(c.key)}>
                      <span className="inline-flex items-center gap-1">
                        {c.label}
                        {sort.key === c.key && <span className="text-orange-400">{sort.dir === "asc" ? "▲" : "▼"}</span>}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={OPEN_PR_COLS.length} className="px-3 py-10 text-center text-xs text-gray-500">
                    <Loader2 size={14} className="animate-spin inline mr-2" />Loading...
                  </td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={OPEN_PR_COLS.length} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
                ) : paged.map((r, i) => (
                  <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                    <td className={`${TD} text-blue-400 font-mono font-medium`}>{r.pr_number}</td>
                    <td className={`${TD} text-purple-400 font-mono font-medium`}>{r.po_number || "-"}</td>
                    <td className={`${TD} text-gray-400 text-center`}>{r.line_num}</td>
                    <td className={`${TD} text-gray-300 font-mono`}>{r.item_code}</td>
                    <td className={`${TD} text-gray-300 max-w-48 truncate`} title={r.item_description}>{r.item_description}</td>
                    <td className={`${TD} text-gray-400`}>{r.category_code}</td>
                    <td className={`${TD} text-gray-400`}>
                      <span className={`px-1.5 py-0.5 rounded text-xs border ${
                        r.material_type?.toUpperCase() === "DIRECT MATERIAL"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          : "bg-slate-500/10 text-slate-400 border-slate-500/30"
                      }`}>{r.material_type}</span>
                    </td>
                    <td className={`${TD} text-gray-400 max-w-40 truncate`} title={r.supplier_name}>{r.supplier_name || "-"}</td>
                    <td className={`${TD} text-gray-400`}>{r.payment_terms || "-"}</td>
                    <td className={`${TD} text-gray-400`}>{r.requestor}</td>
                    <td className={`${TD} text-gray-500`}>{r.uom}</td>
                    <td className={`${TD} text-right text-gray-300`}>{fmtQty(r.quantity)}</td>
                    <td className={`${TD} text-gray-500`}>{r.currency_code}</td>
                    <td className={`${TD} text-right text-gray-300`}>{fmtIDR(r.unit_price_orig)}</td>
                    <td className={`${TD} text-right text-gray-400`}>{fmtIDR(r.unit_price_idr)}</td>
                    <td className={`${TD} text-right text-gray-400`}>
                      {r.last_purchase_price != null
                        ? `${r.last_purchase_currency ? r.last_purchase_currency + " " : ""}${fmtIDR(r.last_purchase_price)}`
                        : "-"}
                    </td>
                    <td className={`${TD} text-right text-gray-300 font-medium`}>{fmtIDR(r.total_value_orig)}</td>
                    <td className={`${TD} text-right text-gray-400`}>{fmtIDR(r.total_value_idr)}</td>
                    <td className={TD}><PRStatusBadge status={r.pr_status} /></td>
                    <td className={`${TD} text-gray-500`}>{r.creation_date}</td>
                    <td className={`${TD} text-gray-500`}>{r.due_date || "-"}</td>
                    <td className={TD}><AgingBadge days={r.aging_days} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination total={rows.length} page={page} onPage={setPage} pageSize={OPEN_PR_PAGE_SIZE} />
        </div>
      )}
    </div>
  );
}

/* ─── Section: Purchase History ──────────────────── */

const CY = new Date().getFullYear();
const PAGE_SIZE = 10;
const BUYER_ALL = "MARIA|DEWI";
const VIEWS = [
  { id: "detail",      label: "Detail View" },
  { id: "detail-qty",  label: "Detail View (Qty)" },
  { id: "summary",     label: "Summary" },
  { id: "graph",       label: "Graph" },
  { id: "by-item",     label: "By Item (Pivot)" },
  { id: "by-supplier", label: "By Supplier (Pivot)" },
];
const fmtIDR = (n) => n == null ? "-" : Number(n).toLocaleString("id-ID");
const fmtQty = (n) => n == null ? "-" : Number(n).toLocaleString();

function PurchaseHistorySection() {
  const [orgs,       setOrgs]       = useState([]);
  const [categories, setCategories] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [matTypes,   setMatTypes]   = useState([]);
  const [view,       setView]       = useState("detail");
  const [searched,   setSearched]   = useState(false);
  const [loadingMap, setLoadingMap] = useState({ detail: false, "by-item": false, "by-supplier": false });
  const [results,    setResults]    = useState({ detail: null, "by-item": null, "by-supplier": null });
  const [filterErr,  setFilterErr]  = useState(null);

  const [f, setF] = useState({
    org_id: "", exchange_rate_type: "Corporate",
    year_from: CY - 1, year_to: CY,
    item_code: "", item_desc: "", vendor_name: "", manufacturer: "",
    country_of_origin: "", category: "", currency_code: "", material_type: "",
    po_number: "", buyer: BUYER_ALL,
  });

  useEffect(() => {
    purchasingApi.getOrganizations().then(r => { if (r.success) setOrgs(r.data ?? []); }).catch(() => {});
    purchasingApi.getCategories().then(r => { if (r.success) setCategories(r.data ?? []); }).catch(() => {});
    purchasingApi.getCurrencies().then(r => { if (r.success) setCurrencies(r.data ?? []); }).catch(() => {});
    purchasingApi.getMaterialTypes().then(r => { if (r.success) setMatTypes(r.data ?? []); }).catch(() => {});
  }, []);

  const params = useMemo(() => ({
    org_id:             f.org_id             || undefined,
    exchange_rate_type: f.exchange_rate_type || "Corporate",
    year_from:          f.year_from          || undefined,
    year_to:            f.year_to            || undefined,
    item_code:          f.item_code          || undefined,
    item_desc:          f.item_desc          || undefined,
    vendor_name:        f.vendor_name        || undefined,
    manufacturer:       f.manufacturer       || undefined,
    country_of_origin:  f.country_of_origin  || undefined,
    category:           f.category           || undefined,
    currency_code:      f.currency_code      || undefined,
    material_type:      f.material_type      || undefined,
    po_number:          f.po_number          || undefined,
    buyer:              f.buyer              || undefined,
  }), [f]);

  const handleSearch = async () => {
    if (!f.year_from || !f.year_to) { setFilterErr("Year From and Year To are required"); return; }
    setFilterErr(null);
    setSearched(true);
    setLoadingMap({ detail: true, "by-item": true, "by-supplier": true });
    const [r1, r2, r3] = await Promise.allSettled([
      purchasingApi.getPurchaseHistoryDetail(params),
      purchasingApi.getPurchaseHistoryByItem(params),
      purchasingApi.getPurchaseHistoryBySupplier(params),
    ]);
    setResults({
      detail:       r1.status === "fulfilled" ? r1.value : { success: false, error: String(r1.reason), data: [] },
      "by-item":    r2.status === "fulfilled" ? r2.value : { success: false, error: String(r2.reason), data: [], years: [] },
      "by-supplier":r3.status === "fulfilled" ? r3.value : { success: false, error: String(r3.reason), data: [], years: [] },
    });
    setLoadingMap({ detail: false, "by-item": false, "by-supplier": false });
  };

  const handleReset = () => {
    setF({ org_id: "", exchange_rate_type: "Corporate", year_from: CY - 1, year_to: CY,
           item_code: "", item_desc: "", vendor_name: "", manufacturer: "",
           country_of_origin: "", category: "", currency_code: "", material_type: "",
           po_number: "", buyer: BUYER_ALL });
    setSearched(false); setResults({ detail: null, "by-item": null, "by-supplier": null }); setFilterErr(null);
  };

  const inp = (key, extra = {}) => (
    <input className={INPUT} value={f[key]} onChange={e => setF(p => ({ ...p, [key]: e.target.value }))} {...extra} />
  );

  return (
    <div className="space-y-3">
      {/* Filter Panel — no title/subtitle */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
        {filterErr && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <X size={12} />{filterErr}
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-3">
          <Field label="Organization">
            <select className={SELECT} value={f.org_id} onChange={e => setF(p => ({ ...p, org_id: e.target.value }))}>
              <option value="">— All —</option>
              {orgs.map(o => <option key={o.organization_id} value={o.organization_id}>{o.name}</option>)}
            </select>
          </Field>
          <Field label="Year From *">
            <input className={YEAR_INPUT} type="number" maxLength={4} value={f.year_from} onChange={e => setF(p => ({ ...p, year_from: e.target.value }))} />
          </Field>
          <Field label="Year To *">
            <input className={YEAR_INPUT} type="number" maxLength={4} value={f.year_to} onChange={e => setF(p => ({ ...p, year_to: e.target.value }))} />
          </Field>
          <Field label="Exchange Rate Type">
            {inp("exchange_rate_type", { placeholder: "Corporate" })}
          </Field>
          <Field label="Item Code">{inp("item_code", { placeholder: "e.g. CKD24Q0062" })}</Field>
          <Field label="Item Description">{inp("item_desc", { placeholder: "Partial search..." })}</Field>
          <Field label="Vendor Name">{inp("vendor_name", { placeholder: "Partial search..." })}</Field>
          <Field label="Manufacturer">{inp("manufacturer", { placeholder: "Partial search..." })}</Field>
          <Field label="Country of Origin">{inp("country_of_origin", { placeholder: "e.g. INDONESIA" })}</Field>
          <Field label="Category">
            <select className={SELECT} value={f.category} onChange={e => setF(p => ({ ...p, category: e.target.value }))}>
              <option value="">— All —</option>
              {categories.map(c => <option key={c.category} value={c.category}>{c.category}</option>)}
            </select>
          </Field>
          <Field label="Currency">
            <select className={SELECT} value={f.currency_code} onChange={e => setF(p => ({ ...p, currency_code: e.target.value }))}>
              <option value="">— All —</option>
              {currencies.map(c => <option key={c.currency_code} value={c.currency_code}>{c.currency_code}</option>)}
            </select>
          </Field>
          <Field label="Material Type">
            <select className={SELECT} value={f.material_type} onChange={e => setF(p => ({ ...p, material_type: e.target.value }))}>
              <option value="">— All —</option>
              {matTypes.map(t => <option key={t.tag} value={t.tag}>{t.tag}</option>)}
            </select>
          </Field>
          <Field label="Purchase Order Number">{inp("po_number", { placeholder: "e.g. 2510…" })}</Field>
          <Field label="Buyer">
            <select className={SELECT} value={f.buyer} onChange={e => setF(p => ({ ...p, buyer: e.target.value }))}>
              <option value={BUYER_ALL}>All (Ms Maria &amp; Ms Dewi)</option>
              <option value="MARIA">Ms Maria</option>
              <option value="DEWI">Ms Dewi</option>
            </select>
          </Field>
        </div>
      </div>

      {/* Sub-tabs + Search/Reset — always visible */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-2 flex-wrap">
          {VIEWS.map(v => (
            <button key={v.id} onClick={() => setView(v.id)}
              className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                view === v.id
                  ? "bg-orange-500/10 border-orange-500/40 text-orange-400"
                  : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
              }`}>
              {v.label}
              {results[v.id]?.count != null && (
                <span className="ml-2 px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">{results[v.id].count}</span>
              )}
            </button>
          ))}
        </div>
        <div className="flex gap-2 shrink-0">
          <ActionBtn icon={RefreshCw} label="Reset"  color="bg-gray-700 hover:bg-gray-600"     onClick={handleReset} />
          <ActionBtn icon={Filter}    label="Search" color="bg-orange-600 hover:bg-orange-700" onClick={handleSearch} />
        </div>
      </div>

      {/* Results */}
      {searched && (
        <div className="space-y-3">
          {view === "detail"      && <PHDetailTable      data={results.detail?.data ?? []}           loading={loadingMap.detail}           error={results.detail?.error} />}
          {view === "detail-qty"  && <PHDetailByQtyTable data={results["by-item"]?.data ?? []}       loading={loadingMap["by-item"]}       error={results["by-item"]?.error}       years={results["by-item"]?.years ?? []} />}
          {view === "summary"     && <PHSummaryView      data={results.detail?.data ?? []}           loading={loadingMap.detail}           error={results.detail?.error} />}
          {view === "graph"       && <PHGraphView        data={results.detail?.data ?? []}           loading={loadingMap.detail}           error={results.detail?.error}
                                                         byItemData={results["by-item"]?.data ?? []}  byItemYears={results["by-item"]?.years ?? []}
                                                         bySupData={results["by-supplier"]?.data ?? []} bySupYears={results["by-supplier"]?.years ?? []} />}
          {view === "by-item"     && <PHByItemTable      data={results["by-item"]?.data ?? []}       loading={loadingMap["by-item"]}       error={results["by-item"]?.error}       years={results["by-item"]?.years ?? []} />}
          {view === "by-supplier" && <PHBySupplierTable  data={results["by-supplier"]?.data ?? []}   loading={loadingMap["by-supplier"]}   error={results["by-supplier"]?.error}   years={results["by-supplier"]?.years ?? []} />}
        </div>
      )}
    </div>
  );
}

/* ─── Shared: Excel download helper ─────────────── */

function downloadExcel(filename, headers, rows, amountCols) {
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  if (amountCols && amountCols.length > 0) {
    const fmt = "#,##0.00";
    for (let r = 1; r <= rows.length; r++) {
      for (const c of amountCols) {
        const addr = XLSX.utils.encode_cell({ r, c });
        if (ws[addr] && typeof ws[addr].v === "number") {
          ws[addr].z = fmt;
        }
      }
    }
  }
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Data");
  XLSX.writeFile(wb, `${filename}.xlsx`);
}

/* ─── Shared: Pagination controls ───────────────── */

function Pagination({ total, page, onPage, pageSize = PAGE_SIZE }) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 16px", borderTop: "1px solid rgba(0,0,0,0.06)",
      background: "#f1f5f9",
    }}>
      <span style={{ fontSize: 12, color: "#475569", fontWeight: 600 }}>
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total} rows
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button onClick={() => onPage(page - 1)} disabled={page === 1}
          style={{
            padding: 4, borderRadius: 6, border: "none", cursor: page === 1 ? "not-allowed" : "pointer",
            background: "#f1f5f9", color: page === 1 ? "#cbd5e1" : "#475569",
            boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
          }}>
          <ChevronLeft size={14} />
        </button>
        {Array.from({ length: pages }, (_, i) => i + 1)
          .filter(p => p === 1 || p === pages || Math.abs(p - page) <= 1)
          .reduce((acc, p, i, arr) => {
            if (i > 0 && p - arr[i - 1] > 1) acc.push("...");
            acc.push(p);
            return acc;
          }, [])
          .map((p, i) => p === "..." ? (
            <span key={`e${i}`} style={{ padding: "0 4px", fontSize: 12, color: "#94a3b8" }}>…</span>
          ) : (
            <button key={p} onClick={() => onPage(p)}
              style={{
                width: 28, height: 28, borderRadius: 8, border: "none",
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                background: p === page ? "#2563eb" : "#f1f5f9",
                color: p === page ? "#ffffff" : "#475569",
                boxShadow: p === page
                  ? "inset 2px 2px 4px rgba(0,0,0,0.2)"
                  : "0 1px 2px rgba(15,23,42,0.08)",
              }}>{p}</button>
          ))}
        <button onClick={() => onPage(page + 1)} disabled={page === pages}
          style={{
            padding: 4, borderRadius: 6, border: "none", cursor: page === pages ? "not-allowed" : "pointer",
            background: "#f1f5f9", color: page === pages ? "#cbd5e1" : "#475569",
            boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
          }}>
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

const PH_DETAIL_PAGE_SIZE = 8;

const PH_DETAIL_COLS = [
  { key: "po_number",         label: "PO Number" },
  { key: "line_num",          label: "Line",       numeric: true },
  { key: "item_code",         label: "Item Code" },
  { key: "item_description",  label: "Item Description" },
  { key: "category",          label: "Category" },
  { key: "item_type",         label: "Item Type" },
  { key: "material_type",     label: "Type" },
  { key: "country_of_origin", label: "Country of Origin" },
  { key: "supplier_name",     label: "Supplier" },
  { key: "organization_name", label: "Org" },
  { key: "currency_code",     label: "Currency" },
  { key: "uom",                label: "UOM" },
  { key: "quantity",          label: "Qty",         numeric: true },
  { key: "unit_price",        label: "Unit Price",  numeric: true },
  { key: "amount_orig",       label: "Amount",      numeric: true },
  { key: "amount_idr",        label: "Amount IDR",  numeric: true },
  { key: "received_qty",      label: "Rcvd Qty",    numeric: true },
  { key: "creation_date",     label: "PO Date" },
  { key: "closure_status",    label: "Status" },
];

function PHDetailTable({ data, loading, error }) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState({ key: null, dir: "asc" });
  const TH = "px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap cursor-pointer select-none hover:text-gray-300";
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sorted = useMemo(() => {
    if (!sort.key) return data;
    const col = PH_DETAIL_COLS.find(c => c.key === sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      if (col?.numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [data, sort]);

  const paged = sorted.slice((page - 1) * PH_DETAIL_PAGE_SIZE, page * PH_DETAIL_PAGE_SIZE);

  const handleDownload = () => {
    const rows = sorted.map(r => [
      r.po_number, r.line_num, r.item_code, r.item_description,
      r.category, r.item_type, r.material_type, r.country_of_origin, r.supplier_name, r.organization_name,
      r.currency_code, r.uom, r.quantity, r.unit_price,
      r.amount_orig, r.amount_idr, r.received_qty,
      r.creation_date, r.closure_status,
    ]);
    downloadExcel("purchase_history_detail", PH_DETAIL_COLS.map(c => c.label), rows, [12, 13, 14, 15, 16]);
  };

  return (
    <div className="rounded-lg border border-gray-800">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/50">
        <span className="text-xs text-gray-500">{data.length} rows</span>
        {data.length > 0 && (
          <button onClick={handleDownload}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
            <Download size={12} /> Download Excel
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {PH_DETAIL_COLS.map(c => (
                <th key={c.key} className={TH} onClick={() => toggleSort(c.key)}>
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {sort.key === c.key && <span className="text-orange-400">{sort.dir === "asc" ? "▲" : "▼"}</span>}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={PH_DETAIL_COLS.length} className="px-3 py-10 text-center text-xs text-gray-500"><Loader2 size={14} className="animate-spin inline mr-2" />Loading data...</td></tr>
            ) : error ? (
              <tr><td colSpan={PH_DETAIL_COLS.length} className="px-3 py-6 text-center text-xs text-red-400">{error}</td></tr>
            ) : paged.length === 0 ? (
              <tr><td colSpan={PH_DETAIL_COLS.length} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
            ) : paged.map((r, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                <td className={`${TD} font-mono text-blue-400 font-medium`}>{r.po_number || "-"}</td>
                <td className={`${TD} text-gray-400 text-center`}>{r.line_num ?? "-"}</td>
                <td className={`${TD} font-mono text-gray-300`}>{r.item_code || "-"}</td>
                <td className={`${TD} text-gray-300 max-w-[180px] truncate`} title={r.item_description}>{r.item_description || "-"}</td>
                <td className={`${TD} text-gray-400`}>{r.category || "-"}</td>
                <td className={`${TD} text-gray-400`}>{r.item_type || "-"}</td>
                <td className={`${TD} text-gray-400`}>{r.material_type || "-"}</td>
                <td className={`${TD} text-gray-400`}>{r.country_of_origin || "-"}</td>
                <td className={`${TD} text-gray-300 max-w-[160px] truncate`} title={r.supplier_name}>{r.supplier_name || "-"}</td>
                <td className={`${TD} text-gray-400 max-w-[120px] truncate`} title={r.organization_name}>{r.organization_name || "-"}</td>
                <td className={`${TD} text-yellow-400`}>{r.currency_code || "-"}</td>
                <td className={`${TD} text-gray-500`}>{r.uom || "-"}</td>
                <td className={`${TD} text-right text-gray-300`}>{fmtQty(r.quantity)}</td>
                <td className={`${TD} text-right text-gray-300`}>{fmtIDR(r.unit_price)}</td>
                <td className={`${TD} text-right text-gray-300 font-medium`}>{fmtIDR(r.amount_orig)}</td>
                <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(r.amount_idr)}</td>
                <td className={`${TD} text-right text-gray-400`}>{fmtQty(r.received_qty)}</td>
                <td className={`${TD} text-gray-500`}>{r.creation_date || "-"}</td>
                <td className={`${TD} text-gray-400`}>{r.closure_status || "Open"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={data.length} page={page} onPage={setPage} pageSize={PH_DETAIL_PAGE_SIZE} />
    </div>
  );
}

function PHByItemTable({ data, years, loading, error }) {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";
  const fixedCols = [
    { field: "organization_id",   label: "Org ID",       align: "left" },
    { field: "organization_name", label: "Organization", align: "left" },
    { field: "item_code",         label: "Item Code",    align: "left" },
    { field: "item_description",  label: "Item Desc",    align: "left" },
    { field: "category",          label: "Category",     align: "left" },
    { field: "material_type",     label: "Type",         align: "left" },
    { field: "country_of_origin", label: "Country of Origin", align: "left" },
    { field: "currency_code",     label: "Currency",     align: "left" },
    { field: "uom",               label: "UOM",          align: "left" },
  ];
  const totalCols = fixedCols.length + years.length * 2 + 2;

  const numericFields = useMemo(() => [
    "organization_id", ...years.flatMap(y => [`value_idr_${y}`, `qty_${y}`]), "total_value_idr", "total_qty",
  ], [years]);

  const onSort = (field) => {
    setPage(1);
    const next = toggleSort(sortBy, sortDir, field);
    setSortBy(next.sortBy); setSortDir(next.sortDir);
  };

  const sorted = useMemo(() => sortRows(data, sortBy, sortDir, numericFields), [data, sortBy, sortDir, numericFields]);
  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleDownload = () => {
    const headers = [...fixedCols.map(c => c.label), ...years.flatMap(y => [`Value IDR ${y}`, `Qty ${y}`]), "Total Value IDR", "Total Qty"];
    const rows = sorted.map(r => [
      r.organization_id, r.organization_name, r.item_code, r.item_description,
      r.category, r.material_type, r.country_of_origin, r.currency_code, r.uom,
      ...years.flatMap(y => [r[`value_idr_${y}`] ?? 0, r[`qty_${y}`] ?? 0]),
      r.total_value_idr, r.total_qty,
    ]);
    const amtCols = [];
    for (let i = fixedCols.length; i < headers.length; i++) amtCols.push(i);
    downloadExcel("purchase_history_by_item", headers, rows, amtCols);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">{data.length} rows ditemukan</span>
        <button onClick={handleDownload} disabled={data.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600/20 hover:bg-green-600/30 text-green-400 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          <Download size={12} /> Download Excel
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {fixedCols.map(c => (
                <SortableTH key={c.field} label={c.label} field={c.field} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align={c.align} rowSpan={2} />
              ))}
              {years.map(y => (
                <th key={y} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap" colSpan={2}>{y}</th>
              ))}
              <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap" colSpan={2}>TOTAL</th>
            </tr>
            <tr className="bg-gray-800/40">
              {years.map(y => (
                <Fragment key={y}>
                  <SortableTH label="Value IDR" field={`value_idr_${y}`} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
                  <SortableTH label="Qty"       field={`qty_${y}`}       sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
                </Fragment>
              ))}
              <SortableTH label="Value IDR" field="total_value_idr" sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
              <SortableTH label="Qty"       field="total_qty"       sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-500"><Loader2 size={14} className="animate-spin inline mr-2" />Loading data...</td></tr>
            ) : error ? (
              <tr><td colSpan={totalCols} className="px-3 py-6 text-center text-xs text-red-400">{error}</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
            ) : paged.map((r, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                <td className={`${TD} text-gray-400 font-mono`}>{r.organization_id}</td>
                <td className={`${TD} text-gray-300 max-w-[120px] truncate`} title={r.organization_name}>{r.organization_name}</td>
                <td className={`${TD} font-mono text-blue-400`}>{r.item_code}</td>
                <td className={`${TD} text-gray-300 max-w-[160px] truncate`} title={r.item_description}>{r.item_description}</td>
                <td className={`${TD} text-gray-400`}>{r.category}</td>
                <td className={`${TD} text-gray-400`}>{r.material_type}</td>
                <td className={`${TD} text-gray-400`}>{r.country_of_origin}</td>
                <td className={`${TD} text-yellow-400`}>{r.currency_code}</td>
                <td className={`${TD} text-gray-500`}>{r.uom}</td>
                {years.map(y => (
                  <Fragment key={y}>
                    <td className={`${TD} text-right text-gray-300`}>{fmtIDR(r[`value_idr_${y}`])}</td>
                    <td className={`${TD} text-right text-gray-400`}>{fmtQty(r[`qty_${y}`])}</td>
                  </Fragment>
                ))}
                <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(r.total_value_idr)}</td>
                <td className={`${TD} text-right text-gray-300 font-medium`}>{fmtQty(r.total_qty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={data.length} page={page} onPage={setPage} />
    </div>
  );
}

function PHBySupplierTable({ data, years, loading, error }) {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";
  const fixedCols = [
    { field: "supplier_name", label: "Supplier", align: "left" },
    { field: "currency_code", label: "Currency", align: "left" },
    { field: "item_count",    label: "Items",     align: "center" },
    { field: "po_count",      label: "POs",       align: "center" },
  ];
  const totalCols = fixedCols.length + years.length * 3 + 3;

  const numericFields = useMemo(() => [
    "item_count", "po_count",
    ...years.flatMap(y => [`value_orig_${y}`, `value_idr_${y}`, `qty_${y}`]),
    "total_value_orig", "total_value_idr", "total_qty",
  ], [years]);

  const onSort = (field) => {
    setPage(1);
    const next = toggleSort(sortBy, sortDir, field);
    setSortBy(next.sortBy); setSortDir(next.sortDir);
  };

  const sorted = useMemo(() => sortRows(data, sortBy, sortDir, numericFields), [data, sortBy, sortDir, numericFields]);
  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleDownload = () => {
    const headers = [...fixedCols.map(c => c.label), ...years.flatMap(y => [`Value Orig ${y}`, `Value IDR ${y}`, `Qty ${y}`]), "Total Orig", "Total IDR", "Total Qty"];
    const rows = sorted.map(r => [
      r.supplier_name, r.currency_code, r.item_count, r.po_count,
      ...years.flatMap(y => [r[`value_orig_${y}`] ?? 0, r[`value_idr_${y}`] ?? 0, r[`qty_${y}`] ?? 0]),
      r.total_value_orig, r.total_value_idr, r.total_qty,
    ]);
    const amtCols = [];
    for (let i = fixedCols.length; i < headers.length; i++) amtCols.push(i);
    downloadExcel("purchase_history_by_supplier", headers, rows, amtCols);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">{data.length} rows ditemukan</span>
        <button onClick={handleDownload} disabled={data.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600/20 hover:bg-green-600/30 text-green-400 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          <Download size={12} /> Download Excel
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {fixedCols.map(c => (
                <SortableTH key={c.field} label={c.label} field={c.field} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align={c.align} rowSpan={2} />
              ))}
              {years.map(y => (
                <th key={y} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap" colSpan={3}>{y}</th>
              ))}
              <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap" colSpan={3}>TOTAL</th>
            </tr>
            <tr className="bg-gray-800/40">
              {years.map(y => (
                <Fragment key={y}>
                  <SortableTH label="Orig" field={`value_orig_${y}`} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
                  <SortableTH label="IDR"  field={`value_idr_${y}`}  sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
                  <SortableTH label="Qty"  field={`qty_${y}`}        sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
                </Fragment>
              ))}
              <SortableTH label="Orig" field="total_value_orig" sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
              <SortableTH label="IDR"  field="total_value_idr"  sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
              <SortableTH label="Qty"  field="total_qty"        sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" className="!py-1 !text-[11px] !normal-case" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-500"><Loader2 size={14} className="animate-spin inline mr-2" />Loading data...</td></tr>
            ) : error ? (
              <tr><td colSpan={totalCols} className="px-3 py-6 text-center text-xs text-red-400">{error}</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
            ) : paged.map((r, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                <td className={`${TD} text-gray-300 max-w-[180px] truncate font-medium`} title={r.supplier_name}>{r.supplier_name}</td>
                <td className={`${TD} text-yellow-400`}>{r.currency_code}</td>
                <td className={`${TD} text-gray-400 text-center`}>{r.item_count}</td>
                <td className={`${TD} text-gray-400 text-center`}>{r.po_count}</td>
                {years.map(y => (
                  <Fragment key={y}>
                    <td className={`${TD} text-right text-gray-300`}>{fmtIDR(r[`value_orig_${y}`])}</td>
                    <td className={`${TD} text-right text-green-400`}>{fmtIDR(r[`value_idr_${y}`])}</td>
                    <td className={`${TD} text-right text-gray-400`}>{fmtQty(r[`qty_${y}`])}</td>
                  </Fragment>
                ))}
                <td className={`${TD} text-right text-gray-300 font-medium`}>{fmtIDR(r.total_value_orig)}</td>
                <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(r.total_value_idr)}</td>
                <td className={`${TD} text-right text-gray-300 font-medium`}>{fmtQty(r.total_qty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={data.length} page={page} onPage={setPage} />
    </div>
  );
}

/* ─── Purchase History: Detail View by Qty (currency-merged) ───
   "By Item (Pivot)" groups by item + currency, so one item bought in both
   USD and IDR shows as two rows. This view merges those currency variants
   into a single row per item so the total quantity purchased in the
   selected period is visible at a glance — derived client-side from the
   already-fetched by-item pivot data, no extra API call needed. */
function aggregatePHByQty(byItemData, years) {
  const map = new Map();
  for (const r of byItemData) {
    const key = `${r.organization_id}||${r.item_code}`;
    let agg = map.get(key);
    if (!agg) {
      agg = {
        organization_id: r.organization_id, organization_name: r.organization_name,
        item_code: r.item_code, item_description: r.item_description,
        category: r.category, material_type: r.material_type, uom: r.uom,
        total_qty: 0,
      };
      for (const y of years) agg[`qty_${y}`] = 0;
      map.set(key, agg);
    }
    agg.total_qty += Number(r.total_qty) || 0;
    for (const y of years) agg[`qty_${y}`] += Number(r[`qty_${y}`]) || 0;
  }
  return [...map.values()];
}

function PHDetailByQtyTable({ data, years, loading, error }) {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";
  const fixedCols = [
    { field: "organization_id",   label: "Org ID",       align: "left" },
    { field: "organization_name", label: "Organization", align: "left" },
    { field: "item_code",         label: "Item Code",    align: "left" },
    { field: "item_description",  label: "Item Desc",    align: "left" },
    { field: "category",          label: "Category",     align: "left" },
    { field: "material_type",     label: "Type",         align: "left" },
    { field: "uom",               label: "UOM",          align: "left" },
  ];
  const totalCols = fixedCols.length + years.length + 1;

  const aggregated = useMemo(() => aggregatePHByQty(data, years), [data, years]);
  const numericFields = useMemo(() => ["organization_id", ...years.map(y => `qty_${y}`), "total_qty"], [years]);

  const onSort = (field) => {
    setPage(1);
    const next = toggleSort(sortBy, sortDir, field);
    setSortBy(next.sortBy); setSortDir(next.sortDir);
  };

  const sorted = useMemo(() => sortRows(aggregated, sortBy, sortDir, numericFields), [aggregated, sortBy, sortDir, numericFields]);
  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleDownload = () => {
    const headers = [...fixedCols.map(c => c.label), ...years.map(y => `Qty ${y}`), "Total Qty"];
    const rows = sorted.map(r => [
      r.organization_id, r.organization_name, r.item_code, r.item_description,
      r.category, r.material_type, r.uom,
      ...years.map(y => r[`qty_${y}`] ?? 0),
      r.total_qty,
    ]);
    const amtCols = [];
    for (let i = fixedCols.length; i < headers.length; i++) amtCols.push(i);
    downloadExcel("purchase_history_detail_by_qty", headers, rows, amtCols);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">{aggregated.length} items — quantity merged across currencies</span>
        <button onClick={handleDownload} disabled={aggregated.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600/20 hover:bg-green-600/30 text-green-400 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          <Download size={12} /> Download Excel
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {fixedCols.map(c => (
                <SortableTH key={c.field} label={c.label} field={c.field} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align={c.align} />
              ))}
              {years.map(y => (
                <SortableTH key={y} label={`Qty ${y}`} field={`qty_${y}`} sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" />
              ))}
              <SortableTH label="Total Qty" field="total_qty" sortBy={sortBy} sortDir={sortDir} onSort={onSort} align="right" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-500"><Loader2 size={14} className="animate-spin inline mr-2" />Loading data...</td></tr>
            ) : error ? (
              <tr><td colSpan={totalCols} className="px-3 py-6 text-center text-xs text-red-400">{error}</td></tr>
            ) : aggregated.length === 0 ? (
              <tr><td colSpan={totalCols} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
            ) : paged.map((r, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                <td className={`${TD} text-gray-400 font-mono`}>{r.organization_id}</td>
                <td className={`${TD} text-gray-300 max-w-[120px] truncate`} title={r.organization_name}>{r.organization_name}</td>
                <td className={`${TD} font-mono text-blue-400`}>{r.item_code}</td>
                <td className={`${TD} text-gray-300 max-w-[180px] truncate`} title={r.item_description}>{r.item_description}</td>
                <td className={`${TD} text-gray-400`}>{r.category}</td>
                <td className={`${TD} text-gray-400`}>{r.material_type}</td>
                <td className={`${TD} text-gray-500`}>{r.uom}</td>
                {years.map(y => (
                  <td key={y} className={`${TD} text-right text-gray-300`}>{fmtQty(r[`qty_${y}`])}</td>
                ))}
                <td className={`${TD} text-right text-green-400 font-medium`}>{fmtQty(r.total_qty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={aggregated.length} page={page} onPage={setPage} />
    </div>
  );
}

/* ─── Purchase History: Summary View ────────────── */

function PHSummaryView({ data, loading, error }) {
  const TH = "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const TD = "px-3 py-2 text-xs";

  const summary = useMemo(() => {
    if (!data.length) return null;
    const totalIDR   = data.reduce((s, r) => s + (Number(r.amount_idr)  || 0), 0);
    const totalOrig  = data.reduce((s, r) => s + (Number(r.amount_orig) || 0), 0);
    const uniquePOs  = new Set(data.map(r => r.po_number)).size;
    const uniqueItems= new Set(data.map(r => r.item_code).filter(Boolean)).size;

    const byCat = {};
    const byType= {};
    const bySup = {};
    const byYear= {};
    data.forEach(r => {
      const cat  = r.category      || "(Uncategorized)";
      const type = r.material_type || "(Unknown)";
      const sup  = r.supplier_name || "(Unknown)";
      const yr   = r.creation_date ? r.creation_date.slice(0, 4) : "(Unknown)";
      const idr  = Number(r.amount_idr)  || 0;
      const orig = Number(r.amount_orig) || 0;
      const qty  = Number(r.quantity)    || 0;

      if (!byCat[cat])  byCat[cat]  = { label: cat,  idr: 0, orig: 0, qty: 0, lines: 0 };
      byCat[cat].idr   += idr; byCat[cat].orig += orig; byCat[cat].qty += qty; byCat[cat].lines++;

      if (!byType[type]) byType[type] = { label: type, idr: 0, orig: 0, qty: 0, lines: 0 };
      byType[type].idr  += idr; byType[type].orig += orig; byType[type].qty += qty; byType[type].lines++;

      if (!bySup[sup])  bySup[sup]  = { label: sup,  idr: 0, orig: 0, qty: 0, pos: new Set() };
      bySup[sup].idr   += idr; bySup[sup].orig += orig; bySup[sup].qty += qty; bySup[sup].pos.add(r.po_number);

      if (!byYear[yr])  byYear[yr]  = { label: yr,   idr: 0, orig: 0, qty: 0, lines: 0, pos: new Set() };
      byYear[yr].idr   += idr; byYear[yr].orig += orig; byYear[yr].qty += qty; byYear[yr].lines++; byYear[yr].pos.add(r.po_number);
    });

    const topCats = Object.values(byCat).sort((a, b) => b.idr - a.idr);
    const topSups = Object.values(bySup).map(s => ({ ...s, pos: s.pos.size })).sort((a, b) => b.idr - a.idr).slice(0, 15);
    const typeArr = Object.values(byType).sort((a, b) => b.idr - a.idr);
    const yearArr = Object.values(byYear).sort((a, b) => a.label.localeCompare(b.label))
                          .map(y => ({ ...y, pos: y.pos.size }));
    return { totalIDR, totalOrig, uniquePOs, uniqueItems, lines: data.length, topCats, topSups, typeArr, yearArr };
  }, [data]);

  if (loading) return (
    <div className="flex items-center justify-center py-12 text-gray-500 text-xs gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading...
    </div>
  );
  if (error)   return <div className="py-6 text-center text-xs text-red-400">{error}</div>;
  if (!summary) return <div className="py-10 text-center text-xs text-gray-600">No data. Run a search first.</div>;

  const pct = (v) => summary.totalIDR > 0 ? ((v / summary.totalIDR) * 100).toFixed(1) + "%" : "—";
  const KpiCard = ({ label, value, sub, color }) => (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard label="Total Amount IDR" value={fmtIDRShort(summary.totalIDR)} sub="All PO lines" color="text-green-400" />
        <KpiCard label="Total Amount (Orig)" value={fmtIDRShort(summary.totalOrig)} sub="Original currency" color="text-blue-400" />
        <KpiCard label="Unique POs" value={summary.uniquePOs.toLocaleString()} sub="Purchase orders" color="text-orange-400" />
        <KpiCard label="Unique Items" value={summary.uniqueItems.toLocaleString()} sub="Item codes" color="text-purple-400" />
        <KpiCard label="PO Lines" value={summary.lines.toLocaleString()} sub="Total rows" color="text-teal-400" />
      </div>

      {/* By Year */}
      {summary.yearArr.length > 1 && (
        <div className="rounded-xl border border-gray-800 overflow-hidden">
          <div className="px-4 py-2.5 bg-gray-800/60 text-xs font-semibold text-gray-400">By Year</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="bg-gray-800/40">
                <th className={TH}>Year</th>
                <th className={`${TH} text-right`}>Amount IDR</th>
                <th className={`${TH} text-right`}>% of Total</th>
                <th className={`${TH} text-right`}>Amount Orig</th>
                <th className={`${TH} text-right`}>Qty</th>
                <th className={`${TH} text-right`}>POs</th>
                <th className={`${TH} text-right`}>Lines</th>
              </tr></thead>
              <tbody>
                {summary.yearArr.map((y, i) => (
                  <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                    <td className={`${TD} font-semibold text-gray-200`}>{y.label}</td>
                    <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(y.idr)}</td>
                    <td className={`${TD} text-right text-gray-400`}>{pct(y.idr)}</td>
                    <td className={`${TD} text-right text-gray-300`}>{fmtIDR(y.orig)}</td>
                    <td className={`${TD} text-right text-gray-400`}>{fmtQty(y.qty)}</td>
                    <td className={`${TD} text-right text-blue-400`}>{y.pos}</td>
                    <td className={`${TD} text-right text-gray-500`}>{y.lines}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* By Material Type */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-800/60 text-xs font-semibold text-gray-400">By Material Type</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="bg-gray-800/40">
              <th className={TH}>Type</th>
              <th className={`${TH} text-right`}>Amount IDR</th>
              <th className={`${TH} text-right`}>% of Total</th>
              <th className={`${TH} text-right`}>Amount Orig</th>
              <th className={`${TH} text-right`}>Qty</th>
              <th className={`${TH} text-right`}>Lines</th>
            </tr></thead>
            <tbody>
              {summary.typeArr.map((t, i) => (
                <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className={`${TD} font-medium ${t.label?.toUpperCase() === "DIRECT MATERIAL" ? "text-emerald-400" : "text-blue-400"}`}>{t.label}</td>
                  <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(t.idr)}</td>
                  <td className={`${TD} text-right text-gray-400`}>{pct(t.idr)}</td>
                  <td className={`${TD} text-right text-gray-300`}>{fmtIDR(t.orig)}</td>
                  <td className={`${TD} text-right text-gray-400`}>{fmtQty(t.qty)}</td>
                  <td className={`${TD} text-right text-gray-500`}>{t.lines}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* By Category */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-800/60 text-xs font-semibold text-gray-400">By Category</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="bg-gray-800/40">
              <th className={`${TH} w-8`}>#</th>
              <th className={TH}>Category</th>
              <th className={`${TH} text-right`}>Amount IDR</th>
              <th className={`${TH} text-right`}>% of Total</th>
              <th className={`${TH} text-right`}>Amount Orig</th>
              <th className={`${TH} text-right`}>Qty</th>
              <th className={`${TH} text-right`}>Lines</th>
            </tr></thead>
            <tbody>
              {summary.topCats.map((c, i) => (
                <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className={`${TD} text-gray-600 text-center`}>{i + 1}</td>
                  <td className={`${TD} text-gray-200 max-w-[220px] truncate font-medium`} title={c.label}>{c.label}</td>
                  <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(c.idr)}</td>
                  <td className={`${TD} text-right`}>
                    <div className="flex items-center justify-end gap-1.5">
                      <div className="h-1.5 rounded-full bg-orange-500/30 overflow-hidden" style={{ width: 60 }}>
                        <div className="h-full rounded-full bg-orange-400" style={{ width: pct(c.idr) }} />
                      </div>
                      <span className="text-gray-400 w-10 text-right">{pct(c.idr)}</span>
                    </div>
                  </td>
                  <td className={`${TD} text-right text-gray-300`}>{fmtIDR(c.orig)}</td>
                  <td className={`${TD} text-right text-gray-400`}>{fmtQty(c.qty)}</td>
                  <td className={`${TD} text-right text-gray-500`}>{c.lines}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* By Supplier (top 15) */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-800/60 text-xs font-semibold text-gray-400">By Supplier (Top 15)</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="bg-gray-800/40">
              <th className={`${TH} w-8`}>#</th>
              <th className={TH}>Supplier</th>
              <th className={`${TH} text-right`}>Amount IDR</th>
              <th className={`${TH} text-right`}>% of Total</th>
              <th className={`${TH} text-right`}>Amount Orig</th>
              <th className={`${TH} text-right`}>Qty</th>
              <th className={`${TH} text-right`}>POs</th>
            </tr></thead>
            <tbody>
              {summary.topSups.map((s, i) => (
                <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className={`${TD} text-gray-600 text-center`}>{i + 1}</td>
                  <td className={`${TD} text-gray-200 max-w-[220px] truncate font-medium`} title={s.label}>{s.label}</td>
                  <td className={`${TD} text-right text-green-400 font-medium`}>{fmtIDR(s.idr)}</td>
                  <td className={`${TD} text-right`}>
                    <div className="flex items-center justify-end gap-1.5">
                      <div className="h-1.5 rounded-full bg-blue-500/30 overflow-hidden" style={{ width: 60 }}>
                        <div className="h-full rounded-full bg-blue-400" style={{ width: pct(s.idr) }} />
                      </div>
                      <span className="text-gray-400 w-10 text-right">{pct(s.idr)}</span>
                    </div>
                  </td>
                  <td className={`${TD} text-right text-gray-300`}>{fmtIDR(s.orig)}</td>
                  <td className={`${TD} text-right text-gray-400`}>{fmtQty(s.qty)}</td>
                  <td className={`${TD} text-right text-blue-400`}>{s.pos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ─── Purchase History: Graph View ──────────────── */

const PH_CHART_COLORS = ["#f97316","#34d399","#60a5fa","#a78bfa","#f59e0b","#fb923c","#4ade80","#38bdf8","#c084fc","#fbbf24"];

function PHGraphView({ data, loading, error, byItemData, byItemYears, bySupData, bySupYears }) {
  const chartData = useMemo(() => {
    if (!data.length) return null;

    const totalIDR = data.reduce((s, r) => s + (Number(r.amount_idr) || 0), 0);

    const byCat = {};
    const byType= {};
    const bySup = {};
    const byYear= {};
    data.forEach(r => {
      const cat  = r.category      || "(Uncategorized)";
      const type = r.material_type || "(Unknown)";
      const sup  = r.supplier_name || "(Unknown)";
      const yr   = r.creation_date ? r.creation_date.slice(0, 4) : "(Unknown)";
      const idr  = Number(r.amount_idr) || 0;

      if (!byCat[cat])  byCat[cat]  = { name: cat,  value: 0 };
      byCat[cat].value += idr;

      if (!byType[type]) byType[type] = { name: type, value: 0 };
      byType[type].value += idr;

      if (!bySup[sup])  bySup[sup]  = { name: sup,  value: 0 };
      bySup[sup].value += idr;

      if (!byYear[yr])  byYear[yr]  = { name: yr,   value: 0 };
      byYear[yr].value += idr;
    });

    const topCats = Object.values(byCat).sort((a, b) => b.value - a.value).slice(0, 10).reverse();
    const topSups = Object.values(bySup).sort((a, b) => b.value - a.value).slice(0, 10);
    const typeArr = Object.values(byType).sort((a, b) => b.value - a.value);
    const yearArr = Object.values(byYear).sort((a, b) => a.name.localeCompare(b.name));

    // Year trend from by-item pivot
    const itemYearTrend = byItemYears.map(yr => ({
      name: String(yr),
      value: byItemData.reduce((s, r) => s + (Number(r[`value_idr_${yr}`]) || 0), 0),
    }));

    // Year trend from by-supplier pivot
    const supYearTrend = bySupYears.map(yr => ({
      name: String(yr),
      direct:   bySupData.reduce((s, r) => s + (Number(r[`value_idr_${yr}`]) || 0), 0),
    }));

    return { totalIDR, topCats, topSups, typeArr, yearArr, itemYearTrend, supYearTrend };
  }, [data, byItemData, byItemYears, bySupData, bySupYears]);

  if (loading) return (
    <div className="flex items-center justify-center py-12 text-gray-500 text-xs gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading...
    </div>
  );
  if (error)    return <div className="py-6 text-center text-xs text-red-400">{error}</div>;
  if (!chartData) return <div className="py-10 text-center text-xs text-gray-600">No data. Run a search first.</div>;

  const ChartCard = ({ title, children, height = 260 }) => (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
      <p className="text-xs font-semibold text-gray-200 mb-3">{title}</p>
      <div style={{ height }}>{children}</div>
    </div>
  );

  const TICK  = { fill: "#d1d5db", fontSize: 10 };
  const TICK_DIM = { fill: "#9ca3af", fontSize: 10 };
  const tooltipStyle = {
    contentStyle: { borderRadius: 8, fontSize: 11 },
    labelStyle:   { color: "#1e293b", fontWeight: 600 },
    itemStyle:    { color: "#334155" },
    cursor:       { fill: "rgba(0,0,0,0.04)" },
  };

  return (
    <div className="space-y-4">
      {/* Yearly Spend Trend */}
      {chartData.yearArr.length > 1 && (
        <ChartCard title="Yearly Spend — Amount IDR" height={220}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData.yearArr} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={TICK} />
              <YAxis tickFormatter={fmtIDRShort} tick={TICK_DIM} width={72} />
              <Tooltip {...tooltipStyle} formatter={(v) => [fmtIDR(v), "Amount IDR"]} />
              <Bar dataKey="value" fill="#f97316" radius={[4, 4, 0, 0]} name="Amount IDR" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By Material Type */}
        <ChartCard title="By Material Type — Amount IDR" height={180}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData.typeArr} layout="vertical" margin={{ top: 4, right: 40, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
              <XAxis type="number" tickFormatter={fmtIDRShort} tick={TICK_DIM} />
              <YAxis type="category" dataKey="name" tick={TICK} width={130} />
              <Tooltip {...tooltipStyle} formatter={(v) => [fmtIDR(v), "Amount IDR"]} />
              <Bar dataKey="value" fill="#34d399" radius={[0, 4, 4, 0]} name="Amount IDR" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Spend Share by Type — progress bars */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-200">Spend Share by Type</p>
          {chartData.typeArr.map((t, i) => {
            const pct = chartData.totalIDR > 0 ? (t.value / chartData.totalIDR) * 100 : 0;
            const isDirect = t.name?.toUpperCase() === "DIRECT MATERIAL";
            const color = isDirect ? "bg-emerald-400" : "bg-blue-400";
            return (
              <div key={i} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className={isDirect ? "text-emerald-300 font-medium" : "text-blue-300 font-medium"}>{t.name}</span>
                  <span className="text-gray-200">{pct.toFixed(1)}% · {fmtIDRShort(t.value)}</span>
                </div>
                <div className="h-2 rounded-full bg-gray-800">
                  <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Top 10 Categories */}
      <ChartCard title="Top 10 Categories — Amount IDR" height={320}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData.topCats} layout="vertical" margin={{ top: 4, right: 60, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
            <XAxis type="number" tickFormatter={fmtIDRShort} tick={TICK_DIM} />
            <YAxis type="category" dataKey="name" tick={TICK} width={180} />
            <Tooltip {...tooltipStyle} formatter={(v) => [fmtIDR(v), "Amount IDR"]} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} name="Amount IDR">
              {chartData.topCats.map((_, i) => (
                <Cell key={i} fill={PH_CHART_COLORS[i % PH_CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Top 10 Suppliers */}
      <ChartCard title="Top 10 Suppliers — Amount IDR" height={320}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData.topSups} layout="vertical" margin={{ top: 4, right: 60, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
            <XAxis type="number" tickFormatter={fmtIDRShort} tick={TICK_DIM} />
            <YAxis type="category" dataKey="name" tick={TICK} width={200}
              tickFormatter={v => v.length > 28 ? v.slice(0, 28) + "…" : v} />
            <Tooltip {...tooltipStyle} formatter={(v) => [fmtIDR(v), "Amount IDR"]} />
            <Bar dataKey="value" fill="#60a5fa" radius={[0, 4, 4, 0]} name="Amount IDR" />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* By-Item Year Trend (from pivot) */}
      {chartData.itemYearTrend.length > 1 && (
        <ChartCard title="Yearly Spend Trend — By Item Pivot (IDR)" height={220}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData.itemYearTrend} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={TICK} />
              <YAxis tickFormatter={fmtIDRShort} tick={TICK_DIM} width={72} />
              <Tooltip {...tooltipStyle} formatter={(v) => [fmtIDR(v), "Amount IDR"]} />
              <Line type="monotone" dataKey="value" stroke="#f97316" strokeWidth={2} dot={{ fill: "#f97316", r: 4 }} name="Amount IDR" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  );
}

/* ─── Section: Monthly Spend ─────────────────────── */

/* ─── Monthly Spend helpers ──────────────────────── */

const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const fmtB  = (n) => n == null ? "—" : (Number(n) / 1_000_000_000).toFixed(2) + " B";
const fmtM  = (n) => n == null ? "—" : (Number(n) / 1_000_000).toFixed(1) + " M";
const fmtIDRShort = (n) => {
  if (n == null) return "—";
  const v = Number(n);
  if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(2) + "B";
  if (v >= 1_000_000)     return (v / 1_000_000).toFixed(1) + "M";
  return fmtIDR(v);
};

const MS_COLORS = {
  "Direct Material":   "#34d399",
  "Indirect Material": "#60a5fa",
  "Total":             "#a78bfa",
};

function MonthlySpendSection() {
  const cy = new Date().getFullYear();
  const [f, setF] = useState({
    org_id: "", year_from: cy - 2, year_to: cy,
    currency_code: "", material_type: "", exchange_rate_type: "Corporate",
  });
  const [orgs,     setOrgs]     = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const [rawData,  setRawData]  = useState([]);
  const [error,    setError]    = useState("");
  const [chartMode, setChartMode] = useState("stacked");   // "stacked" | "yoy"
  const [page,     setPage]     = useState(1);
  const [matTypes, setMatTypes] = useState([]);

  useEffect(() => {
    purchasingApi.getOrganizations().then(r => { if (r.success) setOrgs(r.data ?? []); }).catch(() => {});
    purchasingApi.getMaterialTypes().then(r => { if (r.success) setMatTypes(r.data ?? []); }).catch(() => {});
  }, []);

  const handleSearch = async () => {
    setLoading(true); setError(""); setPage(1);
    try {
      const p = {};
      if (f.org_id)             p.org_id             = f.org_id;
      if (f.year_from)          p.year_from          = f.year_from;
      if (f.year_to)            p.year_to            = f.year_to;
      if (f.currency_code)      p.currency_code      = f.currency_code;
      if (f.material_type)      p.material_type      = f.material_type;
      if (f.exchange_rate_type) p.exchange_rate_type = f.exchange_rate_type;
      const r = await purchasingApi.getMonthlySpend(p);
      if (r?.success) { setRawData(r.data || []); setSearched(true); }
      else setError(r?.error || "Request failed");
    } catch (e) {
      setError(e?.detail || e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setF({ org_id: "", year_from: cy - 2, year_to: cy, currency_code: "", material_type: "", exchange_rate_type: "Corporate" });
    setRawData([]); setSearched(false); setError(""); setPage(1);
  };

  // ── Pivot: stacked bar — [{label, direct, indirect, total, po_count}]
  const stackedData = useMemo(() => {
    const map = {};
    rawData.forEach(r => {
      const key = r.ym_label;
      if (!map[key]) map[key] = { label: key, yr: r.yr, mo: r.mo, direct: 0, indirect: 0, total: 0, po_count: 0 };
      const v = Number(r.spend_idr) || 0;
      if (r.material_type?.toUpperCase() === "DIRECT MATERIAL")   map[key].direct   += v;
      else                                                         map[key].indirect += v;
      map[key].total    += v;
      map[key].po_count += Number(r.po_count) || 0;
    });
    return Object.values(map).sort((a, b) => a.yr - b.yr || a.mo - b.mo);
  }, [rawData]);

  // ── Pivot: year-over-year line — [{mo: 1, label: "Jan", 2023: ..., 2024: ...}]
  const years = useMemo(() => [...new Set(rawData.map(r => r.yr))].sort(), [rawData]);
  const yoyData = useMemo(() => {
    const map = {};
    for (let m = 1; m <= 12; m++) map[m] = { mo: m, label: MONTH_NAMES[m - 1] };
    rawData.forEach(r => {
      const v = Number(r.spend_idr) || 0;
      map[r.mo][r.yr] = (map[r.mo][r.yr] || 0) + v;
    });
    return Object.values(map);
  }, [rawData]);

  // ── KPIs
  const kpi = useMemo(() => {
    if (!stackedData.length) return null;
    const total  = stackedData.reduce((s, r) => s + r.total, 0);
    const direct = stackedData.reduce((s, r) => s + r.direct, 0);
    const indir  = stackedData.reduce((s, r) => s + r.indirect, 0);
    const poCount= stackedData.reduce((s, r) => s + r.po_count, 0);
    const maxMo  = stackedData.reduce((a, b) => b.total > a.total ? b : a, stackedData[0]);
    return { total, direct, indir, poCount, maxMo };
  }, [stackedData]);

  // ── Table (paged)
  const tableData = stackedData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const TH = "px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";

  const handleDownload = () => {
    const cols = ["Month","Year","Direct Material (IDR)","Indirect Material (IDR)","Total (IDR)","PO Count"];
    const rows = stackedData.map(r => [r.label, r.yr, r.direct, r.indirect, r.total, r.po_count]);
    downloadExcel(`monthly_spend_${f.year_from}-${f.year_to}`, cols, rows, [2, 3, 4]);
  };

  const YOY_COLORS = ["#60a5fa","#34d399","#f59e0b","#f87171","#a78bfa","#fb923c"];

  return (
    <div className="space-y-4">
      {/* Filter Panel */}
      <SectionCard
        title="Monthly Spend — Trend"
        subtitle="PO spend per month from Oracle EBS · IDR equivalent"
        action={
          <div className="flex gap-2">
            <ActionBtn icon={RefreshCw} label="Reset" color="bg-gray-700 hover:bg-gray-600" onClick={handleReset} />
            <ActionBtn icon={loading ? Loader2 : Filter} label="Search" color="bg-green-600 hover:bg-green-700" onClick={handleSearch} />
          </div>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Field label="Organization">
            <select className={SELECT} value={f.org_id} onChange={e => setF(p => ({ ...p, org_id: e.target.value }))}>
              <option value="">— All —</option>
              {orgs.map(o => <option key={o.organization_id} value={o.organization_id}>{o.name}</option>)}
            </select>
          </Field>
          <Field label="Year From">
            <input className={INPUT} type="number" value={f.year_from} onChange={e => setF(p => ({ ...p, year_from: e.target.value }))} />
          </Field>
          <Field label="Year To">
            <input className={INPUT} type="number" value={f.year_to} onChange={e => setF(p => ({ ...p, year_to: e.target.value }))} />
          </Field>
          <Field label="Currency">
            <select className={SELECT} value={f.currency_code} onChange={e => setF(p => ({ ...p, currency_code: e.target.value }))}>
              <option value="">— All —</option>
              <option value="IDR">IDR</option>
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
            </select>
          </Field>
          <Field label="Material Type">
            <select className={SELECT} value={f.material_type} onChange={e => setF(p => ({ ...p, material_type: e.target.value }))}>
              <option value="">— All —</option>
              {matTypes.map(t => <option key={t.tag} value={t.tag}>{t.tag}</option>)}
            </select>
          </Field>
          <Field label="Exchange Rate">
            <input className={INPUT} value={f.exchange_rate_type} onChange={e => setF(p => ({ ...p, exchange_rate_type: e.target.value }))} placeholder="Corporate" />
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
          <Loader2 size={16} className="animate-spin" /> Loading data from Oracle EBS...
        </div>
      )}

      {searched && !loading && (
        <>
          {/* KPI Cards */}
          {kpi && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Total Spend (IDR)", value: fmtB(kpi.total),   color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20" },
                { label: "Direct Material",   value: fmtB(kpi.direct),  color: "text-emerald-400",bg: "bg-emerald-500/10",border: "border-emerald-500/20" },
                { label: "Indirect Material", value: fmtB(kpi.indir),   color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/20" },
                { label: "Total PO Count",    value: kpi.poCount.toLocaleString(), color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
              ].map(k => (
                <div key={k.label} className={`rounded-lg border ${k.border} ${k.bg} px-4 py-3`}>
                  <p className="text-xs text-gray-500 mb-1">{k.label}</p>
                  <p className={`text-xl font-bold ${k.color}`}>{k.value}</p>
                </div>
              ))}
            </div>
          )}

          {/* Chart Toggle */}
          <div className="flex gap-2">
            {[{ id: "stacked", label: "Stacked by Type" }, { id: "yoy", label: "Year-over-Year" }].map(m => (
              <button key={m.id} onClick={() => setChartMode(m.id)}
                className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                  chartMode === m.id
                    ? "bg-green-500/10 border-green-500/40 text-green-400"
                    : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
                }`}>{m.label}</button>
            ))}
          </div>

          {/* Chart */}
          {stackedData.length === 0 ? (
            <div className="rounded-lg border border-gray-800 py-12 text-center text-xs text-gray-600">No data found</div>
          ) : chartMode === "stacked" ? (
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
              <p className="text-xs text-gray-500 mb-3">Monthly PO Spend (IDR) — Direct vs Indirect</p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={stackedData} margin={{ top: 4, right: 16, left: 16, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                  <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} angle={-45} textAnchor="end" interval={0} />
                  <YAxis tickFormatter={fmtIDRShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                    formatter={(v, name) => [fmtIDR(v), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af", paddingTop: 8 }} />
                  <Bar dataKey="direct"   name="Direct Material"   stackId="a" fill={MS_COLORS["Direct Material"]}   radius={[0,0,0,0]} />
                  <Bar dataKey="indirect" name="Indirect Material" stackId="a" fill={MS_COLORS["Indirect Material"]} radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
              <p className="text-xs text-gray-500 mb-3">Year-over-Year Monthly Spend (IDR)</p>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={yoyData} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                  <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} />
                  <YAxis tickFormatter={fmtIDRShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                    formatter={(v, name) => [fmtIDR(v), `Year ${name}`]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                  {years.map((yr, i) => (
                    <Line key={yr} type="monotone" dataKey={yr} name={String(yr)}
                      stroke={YOY_COLORS[i % YOY_COLORS.length]} strokeWidth={2}
                      dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Summary Table */}
          <div className="rounded-lg border border-gray-800">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/50">
              <span className="text-xs text-gray-500">{stackedData.length} months</span>
              {stackedData.length > 0 && (
                <button onClick={handleDownload}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
                  <Download size={12} /> Download Excel
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-800/60">
                    {["Month","Direct Material (IDR)","Indirect Material (IDR)","Total (IDR)","PO Count"].map(h => (
                      <th key={h} className={TH}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableData.length === 0 ? (
                    <tr><td colSpan={5} className="px-3 py-10 text-center text-xs text-gray-600">No data</td></tr>
                  ) : tableData.map((r, i) => {
                    const pct = kpi?.total > 0 ? (r.total / kpi.total) * 100 : 0;
                    return (
                      <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                        <td className={`${TD} text-gray-300 font-medium`}>{r.label}</td>
                        <td className={`${TD} text-right text-emerald-400`}>{fmtIDR(r.direct)}</td>
                        <td className={`${TD} text-right text-blue-400`}>{fmtIDR(r.indirect)}</td>
                        <td className={`${TD} text-right text-gray-200 font-semibold`}>
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                              <div className="h-full rounded-full bg-green-500" style={{ width: `${pct}%` }} />
                            </div>
                            {fmtIDR(r.total)}
                          </div>
                        </td>
                        <td className={`${TD} text-right text-gray-400`}>{r.po_count}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination total={stackedData.length} page={page} onPage={setPage} />
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Section: Active Suppliers ──────────────────── */

const ACTIVE_SUP_COLS = [
  { key: "supplier_name",   label: "Supplier Name" },
  { key: "po_count",        label: "PO Count",      numeric: true },
  { key: "item_count",      label: "Items",         numeric: true },
  { key: "category_count",  label: "Categories",    numeric: true },
  { key: "last_po_date",    label: "Last PO" },
  { key: "direct_idr",      label: "Direct (IDR)",   numeric: true },
  { key: "indirect_idr",    label: "Indirect (IDR)", numeric: true },
  { key: "total_idr",       label: "Total (IDR)",    numeric: true },
];

function ActiveSuppliersSection() {
  const cy = new Date().getFullYear();
  const [f, setF] = useState({
    org_id: "", year_from: cy - 1, year_to: cy,
    vendor_name: "", material_type: "", exchange_rate_type: "Corporate",
  });
  const [orgs,     setOrgs]     = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const [rows,     setRows]     = useState([]);
  const [error,    setError]    = useState("");
  const [page,     setPage]     = useState(1);
  const [sort,     setSort]     = useState({ key: null, dir: "asc" });
  const [matTypes, setMatTypes] = useState([]);

  useEffect(() => {
    purchasingApi.getOrganizations().then(r => { if (r.success) setOrgs(r.data ?? []); }).catch(() => {});
    purchasingApi.getMaterialTypes().then(r => { if (r.success) setMatTypes(r.data ?? []); }).catch(() => {});
  }, []);

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const handleSearch = async () => {
    setLoading(true); setError(""); setPage(1);
    try {
      const p = {};
      if (f.org_id)             p.org_id             = f.org_id;
      if (f.year_from)          p.year_from          = f.year_from;
      if (f.year_to)            p.year_to            = f.year_to;
      if (f.vendor_name)        p.vendor_name        = f.vendor_name;
      if (f.material_type)      p.material_type      = f.material_type;
      if (f.exchange_rate_type) p.exchange_rate_type = f.exchange_rate_type;
      const r = await purchasingApi.getActiveSuppliers(p);
      if (r?.success) { setRows(r.data || []); setSearched(true); }
      else setError(r?.error || "Request failed");
    } catch (e) {
      setError(e?.detail || e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setF({ org_id: "", year_from: cy - 1, year_to: cy, vendor_name: "", material_type: "", exchange_rate_type: "Corporate" });
    setRows([]); setSearched(false); setError(""); setPage(1);
  };

  // KPIs
  const kpi = useMemo(() => {
    if (!rows.length) return null;
    const totalSpend = rows.reduce((s, r) => s + (Number(r.total_idr) || 0), 0);
    const totalPO    = rows.reduce((s, r) => s + (Number(r.po_count)  || 0), 0);
    const top        = rows[0];
    return { count: rows.length, totalSpend, totalPO, topName: top?.supplier_name, topSpend: top?.total_idr };
  }, [rows]);

  // Top 10 for bar chart
  const chartData = useMemo(() =>
    rows.slice(0, 10).map(r => ({
      name: r.supplier_name?.length > 18 ? r.supplier_name.slice(0, 18) + "…" : r.supplier_name,
      direct:   Number(r.direct_idr)   || 0,
      indirect: Number(r.indirect_idr) || 0,
      total:    Number(r.total_idr)    || 0,
    }))
  , [rows]);

  const sorted = useMemo(() => {
    if (!sort.key) return rows;
    const col = ACTIVE_SUP_COLS.find(c => c.key === sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (col?.numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [rows, sort]);

  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const TH = "px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap cursor-pointer select-none hover:text-gray-300";
  const TD = "px-3 py-2.5 text-xs whitespace-nowrap";
  const maxSpend = rows[0] ? (Number(rows[0].total_idr) || 1) : 1;

  const handleDownload = () => {
    const cols = ["Supplier Name","PO Count","Item Count","Category Count","Last PO Date",
                  "Direct (IDR)","Indirect (IDR)","Total (IDR)"];
    const data = sorted.map(r => [
      r.supplier_name, r.po_count, r.item_count, r.category_count, r.last_po_date,
      r.direct_idr, r.indirect_idr, r.total_idr,
    ]);
    downloadExcel(`active_suppliers_${f.year_from}-${f.year_to}`, cols, data, [5, 6, 7]);
  };

  return (
    <div className="space-y-4">
      {/* Filter Panel */}
      <SectionCard
        title="Active Suppliers"
        subtitle="Suppliers with approved POs in the selected period · Oracle EBS"
        action={
          <div className="flex gap-2">
            <ActionBtn icon={RefreshCw} label="Reset"  color="bg-gray-700 hover:bg-gray-600" onClick={handleReset} />
            <ActionBtn icon={loading ? Loader2 : Search} label="Search" color="bg-blue-600 hover:bg-blue-700" onClick={handleSearch} />
          </div>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Field label="Organization">
            <select className={SELECT} value={f.org_id} onChange={e => setF(p => ({ ...p, org_id: e.target.value }))}>
              <option value="">— All —</option>
              {orgs.map(o => <option key={o.organization_id} value={o.organization_id}>{o.name}</option>)}
            </select>
          </Field>
          <Field label="Year From">
            <input className={INPUT} type="number" value={f.year_from} onChange={e => setF(p => ({ ...p, year_from: e.target.value }))} />
          </Field>
          <Field label="Year To">
            <input className={INPUT} type="number" value={f.year_to} onChange={e => setF(p => ({ ...p, year_to: e.target.value }))} />
          </Field>
          <Field label="Supplier Name">
            <input className={INPUT} value={f.vendor_name} onChange={e => setF(p => ({ ...p, vendor_name: e.target.value }))} placeholder="partial search…" />
          </Field>
          <Field label="Material Type">
            <select className={SELECT} value={f.material_type} onChange={e => setF(p => ({ ...p, material_type: e.target.value }))}>
              <option value="">— All —</option>
              {matTypes.map(t => <option key={t.tag} value={t.tag}>{t.tag}</option>)}
            </select>
          </Field>
          <Field label="Exchange Rate">
            <input className={INPUT} value={f.exchange_rate_type} onChange={e => setF(p => ({ ...p, exchange_rate_type: e.target.value }))} placeholder="Corporate" />
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
          <Loader2 size={16} className="animate-spin" /> Loading from Oracle EBS...
        </div>
      )}

      {searched && !loading && (
        <>
          {/* KPI Cards */}
          {kpi && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Active Suppliers", value: kpi.count,                     color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/20" },
                { label: "Total Spend (IDR)", value: fmtB(kpi.totalSpend),         color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20" },
                { label: "Total PO Count",   value: kpi.totalPO.toLocaleString(),  color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
                { label: "Top Supplier",     value: kpi.topName ?? "—",            color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20",
                  sub: fmtIDRShort(kpi.topSpend) },
              ].map(k => (
                <div key={k.label} className={`rounded-lg border ${k.border} ${k.bg} px-4 py-3`}>
                  <p className="text-xs text-gray-500 mb-1">{k.label}</p>
                  <p className={`text-xl font-bold truncate ${k.color}`} title={String(k.value)}>{k.value}</p>
                  {k.sub && <p className="text-xs text-gray-500 mt-0.5">{k.sub} IDR</p>}
                </div>
              ))}
            </div>
          )}

          {/* Top 10 Bar Chart */}
          {chartData.length > 0 && (
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
              <p className="text-xs mb-3" style={{ color: "#e2e8f0" }}>Top {chartData.length} Suppliers by Spend (IDR)</p>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 60, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" horizontal={false} />
                  <XAxis type="number" tickFormatter={fmtIDRShort} tick={{ fill: "#cbd5e1", fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fill: "#e2e8f0", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                    formatter={(v, name) => [fmtIDR(v), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#e2e8f0" }} />
                  <Bar dataKey="direct"   name="Direct Material"   stackId="s" fill="#34d399" radius={[0,0,0,0]} />
                  <Bar dataKey="indirect" name="Indirect Material" stackId="s" fill="#60a5fa" radius={[0,4,4,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Table */}
          <div className="rounded-lg border border-gray-800">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/50">
              <span className="text-xs text-gray-500">{rows.length} suppliers</span>
              {rows.length > 0 && (
                <button onClick={handleDownload}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
                  <Download size={12} /> Download Excel
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-800/60">
                    <th className={TH.replace(" cursor-pointer select-none hover:text-gray-300", "")}>#</th>
                    {ACTIVE_SUP_COLS.map(c => (
                      <th key={c.key} className={TH} onClick={() => toggleSort(c.key)}>
                        <span className="inline-flex items-center gap-1">
                          {c.label}
                          {sort.key === c.key && <span className="text-orange-400">{sort.dir === "asc" ? "▲" : "▼"}</span>}
                        </span>
                      </th>
                    ))}
                    <th className={TH.replace(" cursor-pointer select-none hover:text-gray-300", "")}>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={10} className="px-3 py-10 text-center text-xs text-gray-600">No data found</td></tr>
                  ) : paged.map((r, i) => {
                    const rank  = (page - 1) * PAGE_SIZE + i + 1;
                    const share = maxSpend > 0 ? ((Number(r.total_idr) || 0) / maxSpend) * 100 : 0;
                    return (
                      <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                        <td className={`${TD} text-gray-600 text-center w-8`}>{rank}</td>
                        <td className={`${TD} text-gray-200 font-medium max-w-52 truncate`} title={r.supplier_name}>{r.supplier_name || "-"}</td>
                        <td className={`${TD} text-right text-gray-400`}>{r.po_count ?? "-"}</td>
                        <td className={`${TD} text-right text-gray-400`}>{r.item_count ?? "-"}</td>
                        <td className={`${TD} text-right text-gray-400`}>{r.category_count ?? "-"}</td>
                        <td className={`${TD} text-gray-500`}>{r.last_po_date || "-"}</td>
                        <td className={`${TD} text-right text-emerald-400`}>{fmtIDR(r.direct_idr)}</td>
                        <td className={`${TD} text-right text-blue-400`}>{fmtIDR(r.indirect_idr)}</td>
                        <td className={`${TD} text-right text-gray-200 font-semibold`}>{fmtIDR(r.total_idr)}</td>
                        <td className={`${TD} w-24`}>
                          <div className="flex items-center gap-1.5">
                            <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                              <div className="h-full rounded-full bg-blue-500" style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-gray-600 text-xs w-8 text-right">{share.toFixed(0)}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination total={rows.length} page={page} onPage={setPage} />
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Section: PO Price Analysis ────────────────────── */

const LINE_COLORS = ["#06b6d4","#f59e0b","#10b981","#f43f5e","#8b5cf6","#3b82f6","#ec4899","#84cc16"];
const fmtIDR2 = (v) => v == null ? "—" : new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(v);

function PriceAnalysisSection() {
  const [filters, setFilters] = useState({
    item_code: "", item_desc: "", vendor_name: "",
    year_from: CY - 1, year_to: CY,
    material_type: "", category: "", max_rows: 10,
  });
  const [data,    setData]    = useState([]);
  const [years,   setYears]   = useState([]);
  const [metals,  setMetals]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");
  const [searched, setSearched] = useState(false);
  const [matTypes, setMatTypes] = useState([]);

  // Fetch metals prices on mount
  useEffect(() => {
    purchasingApi.getMetalsLatest()
      .then(r => setMetals(r?.data || null))
      .catch(() => {});
    purchasingApi.getMaterialTypes().then(r => { if (r.success) setMatTypes(r.data ?? []); }).catch(() => {});
  }, []);

  const handleSearch = async () => {
    setLoading(true); setError("");
    try {
      const p = {};
      if (filters.item_code)    p.item_code   = filters.item_code;
      if (filters.item_desc)    p.item_desc   = filters.item_desc;
      if (filters.vendor_name)  p.vendor_name = filters.vendor_name;
      if (filters.year_from)    p.year_from   = filters.year_from;
      if (filters.year_to)      p.year_to     = filters.year_to;
      if (filters.material_type) p.material_type = filters.material_type;
      if (filters.category)     p.category    = filters.category;
      if (filters.max_rows)     p.max_rows    = filters.max_rows;
      const r = await purchasingApi.getPriceAnalysis(p);
      if (r?.success) {
        const newData = r.data || [];
        const actualYears = [...new Set(newData.map(d => d.trx_year))].sort((a, b) => a - b);
        setData(newData);
        setYears(actualYears.length > 0 ? actualYears : (r.years || []));
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

  // Build chart data: [{year: 2022, "Supplier A": 12000, "Supplier B": 14000}, ...]
  const chartData = useMemo(() => {
    if (!data.length) return [];
    const suppliers = [...new Set(data.map(r => r.supplier_name))];
    const yearMap = {};
    years.forEach(y => { yearMap[y] = { year: String(y) }; });
    data.forEach(r => {
      if (yearMap[r.trx_year]) {
        yearMap[r.trx_year][r.supplier_name] = r.avg_price_orig;
      }
    });
    return Object.values(yearMap);
  }, [data, years]);

  const suppliers = useMemo(() => [...new Set(data.map(r => r.supplier_name))], [data]);

  // Build summary table: rows=suppliers, cols=years
  const tableRows = useMemo(() => {
    if (!data.length) return [];
    const map = {};
    data.forEach(r => {
      const key = `${r.supplier_name}|||${r.item_code}`;
      if (!map[key]) map[key] = {
        supplier_name: r.supplier_name,
        item_code: r.item_code,
        item_desc: r.item_desc,
        uom: r.uom,
        currency: r.currency_code,
        country: r.country_of_origin,
        years: {},
      };
      map[key].years[r.trx_year] = {
        min_price_idr: r.min_price_idr,
        max_price_idr: r.max_price_idr,
        avg_price_idr: r.avg_price_idr,
        min_price_orig: r.min_price_orig,
        max_price_orig: r.max_price_orig,
        avg_price_orig: r.avg_price_orig,
        total_qty: r.total_qty,
        po_count: r.po_count,
      };
    });
    return Object.values(map);
  }, [data]);

  const handleDownload = () => {
    if (!tableRows.length) return;
    const headers = ["Supplier", "Item Code", "Description", "UOM", "Currency", "Country",
      ...years.flatMap(y => [`Min Price ${y}`, `Max Price ${y}`, `Avg Price ${y}`, `Qty ${y}`, `PO ${y}`])];
    const rows = tableRows.map(r => [
      r.supplier_name, r.item_code, r.item_desc, r.uom, r.currency, r.country,
      ...years.flatMap(y => [
        r.years[y]?.min_price_orig ?? "", r.years[y]?.max_price_orig ?? "",
        r.years[y]?.avg_price_orig ?? "",
        r.years[y]?.total_qty ?? "", r.years[y]?.po_count ?? "",
      ]),
    ]);
    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Price Analysis");
    XLSX.writeFile(wb, `price_analysis_${filters.item_code || "all"}.xlsx`);
  };

  const inp = "w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-2 focus:outline-none focus:border-cyan-500";
  const yearInp = "w-20 text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-3 py-2 focus:outline-none focus:border-cyan-500";
  const lbl = "text-xs text-gray-400 font-medium mb-1";

  return (
    <div className="space-y-4">
      {/* Metals Reference Panel */}
      {metals && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wider">
            Commodity Reference Price (metals.dev · USD/troy oz)
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Platinum",  val: metals.platinum  },
              { label: "Palladium", val: metals.palladium },
              { label: "Gold",      val: metals.gold      },
              { label: "Silver",    val: metals.silver    },
            ].map(m => (
              <div key={m.label} className="bg-gray-800 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-400">{m.label}</p>
                <p className="text-lg font-bold text-cyan-400">
                  ${m.val?.toLocaleString("en-US", { minimumFractionDigits: 2 }) ?? "—"}
                </p>
                <p className="text-xs text-gray-500">per troy oz</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-2">
            Updated: {metals.updated_at ? new Date(metals.updated_at).toLocaleString("id-ID") : "—"}
          </p>
        </div>
      )}

      {/* Filter Panel */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="col-span-2">
            <p className={lbl}>Item Code</p>
            <input className={inp} value={filters.item_code}
              onChange={e => setFilters(f => ({...f, item_code: e.target.value}))}
              placeholder="e.g. RM-0001" />
          </div>
          <div className="col-span-2">
            <p className={lbl}>Item Description</p>
            <input className={inp} value={filters.item_desc}
              onChange={e => setFilters(f => ({...f, item_desc: e.target.value}))}
              placeholder="e.g. Paracetamol" />
          </div>
          <div className="col-span-2">
            <p className={lbl}>Supplier</p>
            <input className={inp} value={filters.vendor_name}
              onChange={e => setFilters(f => ({...f, vendor_name: e.target.value}))}
              placeholder="Supplier name" />
          </div>
          <div>
            <p className={lbl}>Year From</p>
            <input className={yearInp} type="number" maxLength={4} value={filters.year_from}
              onChange={e => setFilters(f => ({...f, year_from: e.target.value}))} />
          </div>
          <div>
            <p className={lbl}>Year To</p>
            <input className={yearInp} type="number" maxLength={4} value={filters.year_to}
              onChange={e => setFilters(f => ({...f, year_to: e.target.value}))} />
          </div>
          <div>
            <p className={lbl}>Material Type</p>
            <select className={inp} value={filters.material_type}
              onChange={e => setFilters(f => ({...f, material_type: e.target.value}))}>
              <option value="">All</option>
              {matTypes.map(t => <option key={t.tag} value={t.tag}>{t.tag}</option>)}
            </select>
          </div>
          <div>
            <p className={lbl}>Max Data</p>
            <input className={yearInp} type="number" min={1} max={500} value={filters.max_rows}
              onChange={e => setFilters(f => ({...f, max_rows: e.target.value}))} />
          </div>
        </div>
        <div className="flex gap-2 mt-3">
          <button onClick={handleSearch} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-50">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {loading ? "Loading..." : "Search"}
          </button>
          {searched && data.length > 0 && (
            <button onClick={handleDownload}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs font-semibold">
              <Download size={13} /> Download Excel
            </button>
          )}
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>

      {/* Chart */}
      {searched && chartData.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-sm font-semibold text-gray-200">
            Average Purchase Price Trend (Original Currency/UOM) — by Supplier
          </p>
          <p className="text-xs text-gray-500 mb-4">
            Prices shown as-invoiced per supplier — not converted to IDR, so values aren't directly comparable across suppliers using different currencies (see "Curr" column below).
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 4, right: 20, left: 10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false}
                tickFormatter={v => fmtIDR2(v)} width={80} />
              <Tooltip
                contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                labelStyle={{ color: "#e5e7eb", fontWeight: 600 }}
                formatter={(v, name) => [fmtIDR2(v), name]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
              {suppliers.map((s, i) => (
                <Line key={s} type="monotone" dataKey={s}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Summary Table */}
      {searched && tableRows.length > 0 && (
        <PriceDetailTable tableRows={tableRows} years={years} />
      )}

      {searched && data.length === 0 && !loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-400 text-sm">
          No data found. Try adjusting filters.
        </div>
      )}

      {!searched && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500 text-sm">
          Set filters and click <span className="text-cyan-400 font-semibold">Search</span> to load price analysis data.
        </div>
      )}
    </div>
  );
}

const PRICE_FIXED_COLS = [
  { key: "supplier_name", label: "Supplier" },
  { key: "item_code",     label: "Item Code" },
  { key: "item_desc",     label: "Description" },
  { key: "uom",           label: "UOM" },
  { key: "currency",      label: "Curr" },
  { key: "country",       label: "Country" },
];
const PRICE_YEAR_METRICS = [
  { metric: "min_price_orig", label: "Min" },
  { metric: "max_price_orig", label: "Max" },
  { metric: "avg_price_orig", label: "Avg" },
  { metric: "total_qty",      label: "Qty" },
];

function PriceDetailTable({ tableRows, years }) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState({ key: null, dir: "asc" });

  const toggleSort = (key) => {
    setPage(1);
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sorted = useMemo(() => {
    if (!sort.key) return tableRows;
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...tableRows].sort((a, b) => {
      if (sort.key.startsWith("year:")) {
        const [, y, metric] = sort.key.split(":");
        const av = a.years[y]?.[metric];
        const bv = b.years[y]?.[metric];
        return ((av == null ? -Infinity : Number(av)) - (bv == null ? -Infinity : Number(bv))) * mul;
      }
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [tableRows, sort]);

  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const sortArrow = (key) => sort.key === key && (sort.dir === "asc" ? "▲" : "▼");

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800">
        <p className="text-sm font-semibold text-gray-200">
          Price Detail Table — {tableRows.length} supplier(s)
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-800/60">
              {PRICE_FIXED_COLS.map(c => (
                <th key={c.key} className="px-3 py-2 text-left text-gray-400 whitespace-nowrap cursor-pointer select-none hover:text-gray-200"
                    onClick={() => toggleSort(c.key)}>
                  {c.label} {sortArrow(c.key)}
                </th>
              ))}
              {years.map(y => (
                <th key={y} className="px-3 py-2 text-center text-gray-400 whitespace-nowrap" colSpan={4}>{y}</th>
              ))}
            </tr>
            <tr className="border-b border-gray-800 bg-gray-800/40">
              <th colSpan={6} />
              {years.map(y => (
                <>
                  {PRICE_YEAR_METRICS.map(m => (
                    <th key={`${y}-${m.metric}`}
                        className="px-3 py-1 text-center text-gray-500 whitespace-nowrap font-normal cursor-pointer select-none hover:text-gray-300"
                        onClick={() => toggleSort(`year:${y}:${m.metric}`)}>
                      {m.label} {sortArrow(`year:${y}:${m.metric}`)}
                    </th>
                  ))}
                </>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((r, i) => {
              const lastY = years[years.length - 1];
              const prevY = years[years.length - 2];
              const lastP = r.years[lastY]?.avg_price_orig;
              const prevP = r.years[prevY]?.avg_price_orig;
              const trend = lastP && prevP ? (lastP > prevP ? "up" : lastP < prevP ? "down" : "flat") : null;
              return (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                  <td className="px-3 py-2 text-gray-200 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      {trend === "up"   && <TrendingUp   size={11} className="text-red-400" />}
                      {trend === "down" && <TrendingDown size={11} className="text-green-400" />}
                      {r.supplier_name}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-cyan-400 font-mono whitespace-nowrap">{r.item_code}</td>
                  <td className="px-3 py-2 text-gray-300 max-w-xs truncate">{r.item_desc}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.uom}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.currency}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.country}</td>
                  {years.map(y => (
                    <>
                      <td key={`${y}-min`} className="px-3 py-2 text-right text-gray-300 whitespace-nowrap">
                        {fmtIDR2(r.years[y]?.min_price_orig)}
                      </td>
                      <td key={`${y}-max`} className="px-3 py-2 text-right text-gray-300 whitespace-nowrap">
                        {fmtIDR2(r.years[y]?.max_price_orig)}
                      </td>
                      <td key={`${y}-avg`} className="px-3 py-2 text-right text-gray-200 whitespace-nowrap">
                        {fmtIDR2(r.years[y]?.avg_price_orig)}
                      </td>
                      <td key={`${y}-q`} className="px-3 py-2 text-right text-gray-400 whitespace-nowrap">
                        {r.years[y]?.total_qty != null ? fmtIDR2(r.years[y].total_qty) : "—"}
                      </td>
                    </>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination total={tableRows.length} page={page} onPage={setPage} />
    </div>
  );
}

/* ─── Section: Manufacturer Master ───────────────── */

const MFR_COLS = [
  { key: "item_code",         label: "Item Code" },
  { key: "item_description",  label: "Item Description" },
  { key: "organization_id",   label: "Org ID",       numeric: true },
  { key: "manufacturer_name", label: "Manufacturer" },
  { key: "country_of_origin", label: "Country" },
  { key: "created_by",        label: "Created By" },
  { key: "creation_date",     label: "Date" },
];

function ManufacturerMasterSection() {
  const [data,       setData]       = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [showForm,   setShowForm]   = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [sort,       setSort]       = useState({ key: null, dir: "asc" });

  const toggleSort = (key) => {
    setSort(s => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  };

  const sorted = useMemo(() => {
    if (!sort.key) return data;
    const col = MFR_COLS.find(c => c.key === sort.key);
    const mul = sort.dir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      if (col?.numeric) return ((Number(a[sort.key]) || 0) - (Number(b[sort.key]) || 0)) * mul;
      const av = (a[sort.key] ?? "").toString().toLowerCase();
      const bv = (b[sort.key] ?? "").toString().toLowerCase();
      return av.localeCompare(bv) * mul;
    });
  }, [data, sort]);

  const loadList = async () => {
    setLoading(true); setError(null);
    try {
      const r = await purchasingApi.getManufacturerList();
      if (r.success) setData(r.data ?? []);
      else setError(r.error);
    } catch (e) {
      setError(String(e?.message ?? e));
    } finally { setLoading(false); }
  };

  useEffect(() => { loadList(); }, []);

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this record?")) return;
    setDeletingId(id);
    try {
      const r = await purchasingApi.deleteManufacturer(id);
      if (r.success) setData((prev) => prev.filter((row) => row.manufacturer_id !== id));
      else setError(r.error);
    } finally { setDeletingId(null); }
  };

  return (
    <>
      <SectionCard
        title="Manufacturer Master"
        subtitle="Factory/manufacturer master data per Oracle item"
        action={
          <div className="flex gap-2">
            <ActionBtn icon={loading ? Loader2 : RefreshCw} label="Refresh" color="bg-gray-700 hover:bg-gray-600" onClick={loadList} />
            <ActionBtn icon={Plus} label="Add" color="bg-purple-600 hover:bg-purple-700" onClick={() => setShowForm(true)} />
          </div>
        }
      >
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{error}</div>
        )}

        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800/60">
                {MFR_COLS.map((c) => (
                  <th key={c.key} onClick={() => toggleSort(c.key)}
                    className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap cursor-pointer select-none hover:text-gray-300">
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      {sort.key === c.key && <span className="text-orange-400">{sort.dir === "asc" ? "▲" : "▼"}</span>}
                    </span>
                  </th>
                ))}
                <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap" />
              </tr>
            </thead>
            <tbody>
              {data.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-10 text-center text-xs text-gray-600">
                    {loading ? "Loading data..." : "No data yet. Click Add to create a record."}
                  </td>
                </tr>
              ) : (
                sorted.map((row) => (
                  <tr key={row.manufacturer_id} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                    <td className="px-3 py-2.5 text-xs font-mono text-blue-400 whitespace-nowrap">{row.item_code}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-300 max-w-[200px] truncate" title={row.item_description}>{row.item_description}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-400 whitespace-nowrap">{row.organization_id}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-200 font-medium whitespace-nowrap">{row.manufacturer_name}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-400 whitespace-nowrap">{row.country_of_origin}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-500 whitespace-nowrap">{row.created_by}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-500 whitespace-nowrap">{row.creation_date}</td>
                    <td className="px-3 py-2.5">
                      <button
                        onClick={() => handleDelete(row.manufacturer_id)}
                        disabled={deletingId === row.manufacturer_id}
                        className="p-1.5 rounded text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                      >
                        {deletingId === row.manufacturer_id
                          ? <Loader2 size={13} className="animate-spin" />
                          : <Trash2 size={13} />}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {showForm && (
        <ManufacturerForm
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); loadList(); }}
        />
      )}
    </>
  );
}

/* ─── Manufacturer Input Form (Modal) ────────────── */

function ManufacturerForm({ onClose, onSaved }) {
  const [orgs,        setOrgs]        = useState([]);
  const [items,       setItems]       = useState([]);
  const [orgLoading,  setOrgLoading]  = useState(true);
  const [itemLoading, setItemLoading] = useState(false);
  const [saving,      setSaving]      = useState(false);
  const [error,       setError]       = useState(null);
  const [itemSearch,  setItemSearch]  = useState("");
  const [showDrop,    setShowDrop]    = useState(false);
  const searchTimer = useRef(null);

  const [form, setForm] = useState({
    organization_id:   "",
    item_id:           "",
    item_code:         "",
    item_description:  "",
    manufacturer_name: "",
    country_of_origin: "",
  });

  // Load organizations
  useEffect(() => {
    purchasingApi.getOrganizations()
      .then((r) => { if (r.success) setOrgs(r.data ?? []); })
      .catch(() => {})
      .finally(() => setOrgLoading(false));
  }, []);

  const searchItems = (orgId, search) => {
    if (!orgId) return;
    setItemLoading(true);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      try {
        const r = await purchasingApi.getItems(orgId, search);
        if (r.success) { setItems(r.data ?? []); setShowDrop(true); }
      } finally { setItemLoading(false); }
    }, 200);
  };

  const handleOrgChange = (e) => {
    setForm((p) => ({ ...p, organization_id: e.target.value, item_id: "", item_code: "", item_description: "" }));
    setItems([]);
    setItemSearch("");
    setShowDrop(false);
  };

  const handleItemInput = (e) => {
    const val = e.target.value;
    setItemSearch(val);
    setForm((p) => ({ ...p, item_id: "", item_code: val, item_description: "" }));
    searchItems(form.organization_id, val);
  };

  const selectItem = (item) => {
    setForm((p) => ({ ...p, item_id: item.item_id, item_code: item.item_code, item_description: item.item_description }));
    setItemSearch(item.item_code);
    setShowDrop(false);
  };

  const handleSave = async () => {
    if (!form.organization_id || !form.item_code.trim() || !form.manufacturer_name.trim()) {
      setError("Organization, Item Code, and Manufacturer Name are required");
      return;
    }
    setSaving(true); setError(null);
    try {
      const r = await purchasingApi.createManufacturer({
        item_id:           form.item_id ? Number(form.item_id) : 0,
        organization_id:   Number(form.organization_id),
        item_code:         form.item_code,
        item_description:  form.item_description,
        manufacturer_name: form.manufacturer_name,
        country_of_origin: form.country_of_origin,
      });
      if (r.success) onSaved();
      else setError(r.error);
    } catch (e) {
      setError(String(e?.message ?? e));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-xl border border-gray-700 bg-gray-900 shadow-2xl overflow-visible">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">Add Manufacturer Master</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-visible">
          {/* Organization dropdown */}
          <Field label="Organization *">
            {orgLoading ? (
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <Loader2 size={12} className="animate-spin" /> Loading organizations...
              </div>
            ) : (
              <select value={form.organization_id} onChange={handleOrgChange} className={SELECT}>
                <option value="">-- Select Organization --</option>
                {orgs.map((o) => (
                  <option key={o.organization_id} value={o.organization_id}>
                    {o.name}
                  </option>
                ))}
              </select>
            )}
          </Field>

          {/* Item Code searchable LOV */}
          <Field label="Item Code *">
            <div className="relative">
              <div className="relative">
                <input
                  className={INPUT}
                  value={itemSearch}
                  onChange={handleItemInput}
                  onFocus={() => { if (items.length > 0) setShowDrop(true); }}
                  onBlur={() => setTimeout(() => setShowDrop(false), 150)}
                  placeholder={form.organization_id ? "Type item code to search..." : "Select organization first"}
                  disabled={!form.organization_id}
                />
                <span className="absolute right-3 top-2 text-gray-600">
                  {itemLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                </span>
              </div>

              {showDrop && (
                <div className="absolute z-[200] w-full mt-1 rounded-lg border border-gray-700 bg-gray-800 shadow-xl max-h-52 overflow-y-auto">
                  {items.length > 0 ? items.map((item) => (
                    <button
                      key={item.item_id}
                      type="button"
                      onMouseDown={() => selectItem(item)}
                      className="w-full text-left px-3 py-2.5 hover:bg-gray-700 transition-colors border-b border-gray-700/50 last:border-0"
                    >
                      <p className="text-xs font-mono font-medium text-blue-400">{item.item_code}</p>
                      <p className="text-xs text-gray-400 truncate">{item.item_description}</p>
                    </button>
                  )) : (
                    <p className="px-3 py-2.5 text-xs text-gray-500">No items found in this organization</p>
                  )}
                </div>
              )}
            </div>
            {form.item_description && (
              <p className="mt-1 text-xs text-gray-500 truncate" title={form.item_description}>{form.item_description}</p>
            )}
          </Field>

          {/* Manufacturer Name */}
          <Field label="Manufacturer Name *">
            <input
              className={INPUT}
              value={form.manufacturer_name}
              onChange={(e) => setForm((p) => ({ ...p, manufacturer_name: e.target.value }))}
              placeholder="Factory / manufacturer name"
            />
          </Field>

          {/* Country of Origin */}
          <Field label="Country of Origin">
            <input
              className={INPUT}
              value={form.country_of_origin}
              onChange={(e) => setForm((p) => ({ ...p, country_of_origin: e.target.value }))}
              placeholder="e.g. Indonesia, Germany, USA"
            />
          </Field>

          {error && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
              <X size={13} /> {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-gray-800">
          <button onClick={onClose} className="px-3 py-1.5 rounded-md text-xs font-medium text-gray-400 hover:text-gray-200 transition-colors">
            Cancel
          </button>
          <ActionBtn
            icon={saving ? Loader2 : CheckCircle}
            label={saving ? "Saving..." : "Save"}
            color="bg-purple-600 hover:bg-purple-700"
            onClick={handleSave}
          />
        </div>
      </div>
    </div>
  );
}

/* ─── Shared UI ───────────────────────────────────── */

const INPUT  = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500 disabled:opacity-40";
const SELECT = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500";
const YEAR_INPUT = "w-20 rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500 disabled:opacity-40";

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  );
}

function SectionCard({ title, subtitle, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="flex items-start justify-between px-5 py-4 border-b border-gray-800">
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

function DataTable({ headers, rows = [], placeholder }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-800/60">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className="px-3 py-10 text-center text-xs text-gray-600">{placeholder}</td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-2.5 text-xs text-gray-300 whitespace-nowrap">{cell}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
