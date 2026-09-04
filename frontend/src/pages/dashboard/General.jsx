/**
 * General Dashboard
 * ─────────────────────────────────────────
 * Company-wide modules that don't belong to one department — reachable by
 * any authenticated user (unlike HR/IT/PAC/etc., not gated to a single
 * Keycloak role). Each sub-module applies its own access control instead;
 * Budget Monitoring restricts by the caller's own team.
 *
 * Budget Monitoring moved here from HRGA — it always accepted an arbitrary
 * ?dept=, so it was never really HRGA-only. Local helpers below are
 * duplicated from HR.jsx rather than shared/imported, matching this
 * codebase's convention for self-contained dashboard sections.
 */
import { useState, useEffect, useCallback, useMemo, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { RefreshCw, Download, Wallet, ChevronDown, Loader2, X, Lock, AlertTriangle } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { toggleSort, sortRows, SortableTH } from "@/components/SortableTH";

const BUDGET_API = "/api/v1/dashboard/general/budget";
const MONTHS_ID = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const NEU_TAB = {
  bg: "#f1f5f9",
  out: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  inset: "inset 0 1px 3px rgba(15,23,42,0.07)",
};

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
    <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          style={{
            padding: "7px 16px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
            background: NEU_TAB.bg, cursor: "pointer",
            color: active === t.id ? "#2563eb" : "#64748b",
            boxShadow: active === t.id ? NEU_TAB.inset : NEU_TAB.out,
            transition: "all 0.2s ease",
          }}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function SummaryChartCard({ title, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
      <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">{title}</p>
      {children}
    </div>
  );
}

function BudgetSummaryCard({ label, value, color, bg }) {
  return (
    <div className={`rounded-lg border px-4 py-3 space-y-1 ${bg}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-bold truncate ${color}`}>{value}</p>
    </div>
  );
}

/* Transaksi Expense Report + Purchase Requisition pendukung Actual satu
   periode — untuk transparansi sumber saja; jumlahnya tidak selalu persis
   sama dengan kolom Actual (Actual GL juga mencakup AP Invoice/payroll/dll
   yang tidak tercakup di dua sumber ini). */
function BudgetTransactionList({ items, monthName }) {
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };
  const sortedItems = sortRows(items, sortBy, sortDir, ["amount"]);
  const thSort = (label, field, extraStyle = {}) => (
    <th onClick={() => handleSort(field)} className="px-3 py-1.5 font-semibold" style={{ ...extraStyle, cursor: "pointer", userSelect: "none", color: sortBy === field ? "#818cf8" : undefined }}>
      {label} {sortBy === field && (sortDir === "asc" ? "▲" : "▼")}
    </th>
  );

  return (
    <div className="bg-gray-950 border-t border-b border-gray-800/60 px-3 py-2">
      <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">
        Transaksi {monthName} — bukan penjumlah langsung ke Actual GL, ditampilkan untuk transparansi sumber
      </p>
      {items.length === 0 ? (
        <p className="text-gray-700 italic py-2">No Expense Report / Purchase Requisition data for this period.</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 uppercase tracking-wider text-[10px]">
              <th className="px-3 py-1.5 text-left font-semibold" style={{ width: "14%" }}>Source</th>
              {thSort("Transaction", "description", { textAlign: "left", width: "42%" })}
              {thSort("Amount", "amount", { textAlign: "right", width: "16%" })}
              <th className="px-3 py-1.5 text-left font-semibold">Date / Ref</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/40">
            {sortedItems.map((item, idx) => (
              <tr key={idx} className="hover:bg-gray-800/20">
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap ${
                    item.source === "Purchase Requisition" ? "bg-amber-500/15 text-amber-400" : "bg-violet-500/15 text-violet-400"
                  }`}>
                    {item.source === "Purchase Requisition" ? "PR" : "Expense Report"}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-gray-300">{item.description}</td>
                <td className="px-3 py-1.5 text-right text-gray-300 tabular-nums">{(item.amount || 0).toLocaleString("id-ID")}</td>
                <td className="px-3 py-1.5 text-gray-500">{item.date || "—"}{item.report_num ? ` · ${item.report_num}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* Rincian per periode untuk 1 akun — layout sama persis dengan Oracle EBS
   "Period Balances (YTDE)": Period | Budget | Encumbrance | Actual | Funds
   Available, satu baris per bulan (dipotong sampai bulan filter YTD kalau
   ada), plus baris TOTAL. Klik satu baris untuk lihat transaksi Expense
   Report + Purchase Requisition yang membentuk Actual bulan itu. */
function BudgetPeriodBalances({ detail, fmtRp, accName }) {
  const [expandedMonth, setExpandedMonth] = useState(null);
  const { monthly, totals } = detail;

  return (
    <div className="rounded-lg border border-gray-800 overflow-hidden text-xs">
      <div className="bg-gray-800 px-3 py-1.5 flex items-center justify-between flex-wrap gap-1">
        <div>
          <span className="font-bold text-gray-200">Period Balances (YTDE)</span>
          <span className="text-gray-600 ml-2">{accName}</span>
        </div>
        <span className="text-gray-600">Klik baris untuk lihat transaksi Expense Report &amp; Purchase Requisition</span>
      </div>

      <table className="w-full">
        <thead>
          <tr className="bg-gray-800/40 text-gray-500 uppercase tracking-wider text-xs">
            <th className="px-3 py-2 text-left font-semibold">Period</th>
            <th className="px-3 py-2 text-right font-semibold">Budget</th>
            <th className="px-3 py-2 text-right font-semibold">Encumbrance</th>
            <th className="px-3 py-2 text-right font-semibold">Actual</th>
            <th className="px-3 py-2 text-right font-semibold">Funds Available</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {monthly.map((m) => {
            const isExp = expandedMonth === m.month;
            const faOk  = m.funds_available >= 0;
            return (
              <Fragment key={m.month}>
                <tr
                  className="hover:bg-gray-800/20 transition-colors cursor-pointer"
                  onClick={() => setExpandedMonth(isExp ? null : m.month)}
                >
                  <td className="px-3 py-2 text-gray-300 font-medium flex items-center gap-1.5">
                    <ChevronDown size={11} className={`text-gray-600 shrink-0 transition-transform ${isExp ? "rotate-180" : ""}`} />
                    {m.month_name}-{String(detail.year).slice(-2)}
                  </td>
                  <td className="px-3 py-2 text-right text-blue-400 tabular-nums">{fmtRp(m.budget)}</td>
                  <td className="px-3 py-2 text-right text-amber-400 tabular-nums">{fmtRp(m.encumbrance)}</td>
                  <td className="px-3 py-2 text-right text-violet-400 tabular-nums underline decoration-dotted underline-offset-4">{fmtRp(m.actual)}</td>
                  <td className={`px-3 py-2 text-right font-semibold tabular-nums ${faOk ? "text-green-400" : "text-red-400"}`}>{fmtRp(m.funds_available)}</td>
                </tr>
                {isExp && (
                  <tr>
                    <td colSpan={5} className="p-0">
                      <BudgetTransactionList items={m.items} monthName={`${m.month_name}-${String(detail.year).slice(-2)}`} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="bg-gray-800/60 font-bold">
            <td className="px-3 py-2 text-gray-300">TOTAL</td>
            <td className="px-3 py-2 text-right text-blue-400 tabular-nums">{fmtRp(totals.budget)}</td>
            <td className="px-3 py-2 text-right text-amber-400 tabular-nums">{fmtRp(totals.encumbrance)}</td>
            <td className="px-3 py-2 text-right text-violet-400 tabular-nums">{fmtRp(totals.actual)}</td>
            <td className={`px-3 py-2 text-right tabular-nums ${totals.funds_available >= 0 ? "text-green-400" : "text-red-400"}`}>{fmtRp(totals.funds_available)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function GLBudgetSection({ dept }) {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();

  const [year,          setYear]          = useState(curYear);
  const [month,         setMonth]         = useState(new Date().getMonth() + 1);
  const [account,       setAccount]       = useState("");
  const [accountInput,  setAccountInput]  = useState("");
  const [years,         setYears]         = useState([curYear, curYear - 1]);
  const [data,          setData]          = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [expandedCode,  setExpandedCode]  = useState(null);
  const [accountDetail, setAccountDetail] = useState({});
  const [uploadMsg,     setUploadMsg]     = useState(null);

  const loadYears = useCallback(async () => {
    if (!dept) return;
    try {
      const res = await fetch(`${BUDGET_API}/years?dept=${encodeURIComponent(dept)}`, { headers: hdrs });
      if (res.ok) {
        const ys = await res.json();
        if (ys.length) { setYears(ys); setYear(ys[0]); }
      }
    } catch (_) {}
  }, [dept]); // eslint-disable-line

  const load = useCallback(async () => {
    if (!dept) return;
    setLoading(true);
    setData(null);
    try {
      const params = new URLSearchParams({ dept, year });
      if (month) params.set("month", month);
      if (account) params.set("account", account);
      const res = await fetch(`${BUDGET_API}?${params}`, { headers: hdrs });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
  }, [dept, year, month, account]); // eslint-disable-line

  // Debounce the account code text field so every keystroke doesn't fire a
  // new Oracle query — matches the pattern of typing a code directly like
  // Oracle's own Funds Available Inquiry "Account" field.
  useEffect(() => {
    const t = setTimeout(() => setAccount(accountInput.trim()), 400);
    return () => clearTimeout(t);
  }, [accountInput]);

  useEffect(() => { loadYears(); }, [loadYears]);
  useEffect(() => { load(); }, [load]); // eslint-disable-line

  const loadDetail = async (code) => {
    const key = `${dept}_${code}_${year}_${month || "all"}`;
    if (accountDetail[key]) return;
    try {
      const params = new URLSearchParams({ dept, year });
      if (month) params.set("month", month);
      const res = await fetch(
        `${BUDGET_API}/account/${encodeURIComponent(code)}?${params}`,
        { headers: hdrs }
      );
      if (res.ok) {
        const d = await res.json();
        setAccountDetail(prev => ({ ...prev, [key]: d }));
      } else {
        const body = await res.json().catch(() => null);
        setAccountDetail(prev => ({ ...prev, [key]: { error: body?.detail || `Failed to load (HTTP ${res.status})` } }));
      }
    } catch (e) {
      setAccountDetail(prev => ({ ...prev, [key]: { error: e?.message || "Network error" } }));
    }
  };

  const handleExpand = async (code) => {
    if (expandedCode === code) { setExpandedCode(null); return; }
    setExpandedCode(code);
    await loadDetail(code);
  };

  const fmtRp = (v) => {
    if (v === undefined || v === null) return "Rp 0";
    return (v < 0 ? "-Rp " : "Rp ") + Math.abs(v).toLocaleString("id-ID");
  };

  const summary  = data?.summary;
  // Sembunyikan akun yang budget, encumbrance, dan actual-nya semua 0 (tidak ada aktivitas)
  const accounts = (data?.accounts || []).filter(a => a.budget !== 0 || a.encumbrance !== 0 || a.actual !== 0);

  return (
    <div className="space-y-4">

      {/* ── Controls ── */}
      <div className="flex flex-wrap items-center gap-2">

        <select
          value={year}
          onChange={e => { setYear(+e.target.value); setAccountDetail({}); }}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          {years.map(y => <option key={y} value={y}>{y}</option>)}
          {!years.includes(curYear) && <option value={curYear}>{curYear}</option>}
        </select>

        <select
          value={month}
          onChange={e => setMonth(+e.target.value)}
          title="Year-To-Date sampai bulan ini (mis. Maret = Jan-Mar dijumlah)"
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          <option value={0}>All Months (Jan-Des)</option>
          {MONTHS_ID.map((m, i) => <option key={i + 1} value={i + 1}>s.d. {m}</option>)}
        </select>

        <input
          value={accountInput}
          onChange={e => setAccountInput(e.target.value)}
          placeholder="Account code..."
          title="Filter per kode akun (segment4) — kosongkan untuk semua akun"
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 w-40"
        />

        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh from Oracle
        </button>

        <div className="flex-1" />

        <button
          onClick={() => {
            const p = new URLSearchParams({ dept, year });
            if (month) p.set("month", month);
            if (account) p.set("account", account);
            window.open(`${BUDGET_API}/export?${p}`, "_blank");
          }}
          disabled={!data}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-xs text-white disabled:opacity-40 transition-colors"
        >
          <Download size={12} /> Export Excel
        </button>
      </div>

      {/* ── Error message ── */}
      {uploadMsg && (
        <div className="rounded-lg px-4 py-2 text-xs flex items-center justify-between bg-red-500/10 text-red-400 border border-red-500/20">
          <span>{uploadMsg.text}</span>
          <button onClick={() => setUploadMsg(null)}><X size={12} /></button>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>}

      {/* ── Empty state ── */}
      {!loading && data && accounts.length === 0 && (
        <div className="py-16 text-center space-y-2">
          <Wallet size={32} className="mx-auto text-gray-700" />
          <p className="text-xs text-gray-600">
            No budget data for year {year}.
          </p>
        </div>
      )}

      {/* ── Summary cards (layout Oracle Funds Available Inquiry) ── */}
      {!loading && summary && accounts.length > 0 && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <BudgetSummaryCard label="Budget"      value={fmtRp(summary.total_budget)}      color="text-blue-400"   bg="bg-blue-500/10   border-blue-500/20" />
          <BudgetSummaryCard label="Encumbrance" value={fmtRp(summary.total_encumbrance)} color="text-amber-400"  bg="bg-amber-500/10  border-amber-500/20" />
          <BudgetSummaryCard label="Actual"      value={fmtRp(summary.total_actual)}      color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
          <BudgetSummaryCard
            label="Funds Available"
            value={fmtRp(summary.total_funds_available)}
            color={summary.total_funds_available >= 0 ? "text-green-400" : "text-red-400"}
            bg={summary.total_funds_available >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"}
          />
        </div>
      )}

      {/* ── Accounts table (ringkasan per akun) ── */}
      {!loading && accounts.length > 0 && (
        <div className="rounded-lg border border-gray-800 overflow-hidden">
          {/* Header */}
          <div className="bg-gray-800/60 grid grid-cols-12 px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            <div className="col-span-4">Account</div>
            <div className="col-span-2 text-right">Budget</div>
            <div className="col-span-2 text-right">Encumbrance</div>
            <div className="col-span-2 text-right" title="Klik baris untuk lihat transaksi Expense Report &amp; Purchase Requisition">Actual</div>
            <div className="col-span-2 text-right">Funds Available</div>
          </div>

          {accounts.map((acc) => {
            const isExp    = expandedCode === acc.account_code;
            const detail   = accountDetail[`${dept}_${acc.account_code}_${year}_${month || "all"}`];
            const remainOk = acc.funds_available >= 0;

            return (
              <div key={acc.account_code} className="border-t border-gray-800">

                {/* Summary row — klik di mana saja termasuk kolom Actual akan
                    membuka rincian transaksi (Expense Report + Purchase Requisition) */}
                <button
                  className={`w-full grid grid-cols-12 px-4 py-3 text-xs text-left transition-colors hover:bg-gray-800/40 ${isExp ? "bg-gray-800/30" : ""}`}
                  onClick={() => handleExpand(acc.account_code)}
                >
                  <div className="col-span-4 flex items-center gap-2">
                    <ChevronDown size={12} className={`text-gray-600 shrink-0 transition-transform ${isExp ? "rotate-180" : ""}`} />
                    <div>
                      <div className="font-medium text-gray-200 leading-tight">{acc.account_name}</div>
                      <div className="text-gray-600">{acc.account_code}</div>
                    </div>
                  </div>
                  <div className="col-span-2 text-right text-blue-400 font-semibold">{fmtRp(acc.budget)}</div>
                  <div className="col-span-2 text-right text-amber-400 font-semibold">{fmtRp(acc.encumbrance)}</div>
                  <div className="col-span-2 text-right text-violet-400 font-semibold underline decoration-dotted underline-offset-4" title="Klik untuk lihat transaksi">
                    {fmtRp(acc.actual)}
                  </div>
                  <div className={`col-span-2 text-right font-semibold ${remainOk ? "text-green-400" : "text-red-400"}`}>
                    {fmtRp(acc.funds_available)}
                  </div>
                </button>

                {/* ── Detail: tabel per bulan sesuai format laporan ── */}
                {isExp && (
                  <div className="border-t border-gray-800/60 bg-gray-950 px-4 py-3">
                    {!detail ? (
                      <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
                    ) : detail.error ? (
                      <div className="flex items-center justify-between py-4 px-2">
                        <p className="text-xs text-red-400">{detail.error}</p>
                        <button
                          onClick={() => { setAccountDetail(prev => { const n = { ...prev }; delete n[`${dept}_${acc.account_code}_${year}_${month || "all"}`]; return n; }); loadDetail(acc.account_code); }}
                          className="text-xs text-gray-400 hover:text-gray-200 underline"
                        >Retry</button>
                      </div>
                    ) : detail.monthly.length === 0 ? (
                      <p className="text-xs text-gray-600 text-center py-4">No monthly data for this account.</p>
                    ) : (
                      <BudgetPeriodBalances detail={detail} fmtRp={fmtRp} accName={acc.account_name} />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Budget Graph ─────────────────────────────────────────────────────────────
// Sama sekali tidak pakai data sendiri — chart di sini ambil dari endpoint yang
// SAMA dengan GL Budget (Oracle) tab (BUDGET_API), cuma disajikan sebagai
// grafik alih-alih tabel: bar chart Budget/Encumbrance/Actual per akun
// (get_summary), dan kalau satu akun difilter, ditambah trend bulanan
// (get_account_detail) — persis rincian "Period Balances" tapi berbentuk chart.

function BudgetGraphSection({ dept }) {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();

  const [year,         setYear]        = useState(curYear);
  const [month,        setMonth]       = useState(new Date().getMonth() + 1);
  const [account,      setAccount]     = useState("");
  const [accountInput, setAccountInput] = useState("");
  const [years,        setYears]       = useState([curYear, curYear - 1]);
  const [data,         setData]        = useState(null);
  const [detail,       setDetail]      = useState(null);
  const [loading,      setLoading]     = useState(false);
  const [RC,           setRC]          = useState(null);

  useEffect(() => { import("recharts").then((mod) => setRC(mod)).catch(() => {}); }, []);

  const loadYears = useCallback(async () => {
    if (!dept) return;
    try {
      const res = await fetch(`${BUDGET_API}/years?dept=${encodeURIComponent(dept)}`, { headers: hdrs });
      if (res.ok) {
        const ys = await res.json();
        if (ys.length) { setYears(ys); setYear(ys[0]); }
      }
    } catch (_) {}
  }, [dept]); // eslint-disable-line

  const load = useCallback(async () => {
    if (!dept) return;
    setLoading(true);
    setDetail(null);
    try {
      const params = new URLSearchParams({ dept, year });
      if (month) params.set("month", month);
      if (account) params.set("account", account);
      const res = await fetch(`${BUDGET_API}?${params}`, { headers: hdrs });
      if (res.ok) setData(await res.json());

      if (account) {
        const dParams = new URLSearchParams({ dept, year });
        if (month) dParams.set("month", month);
        const dRes = await fetch(`${BUDGET_API}/account/${encodeURIComponent(account)}?${dParams}`, { headers: hdrs });
        if (dRes.ok) setDetail(await dRes.json());
      }
    } catch (_) {}
    setLoading(false);
  }, [dept, year, month, account]); // eslint-disable-line

  // Debounce kode akun sama seperti GL Budget (Oracle) tab.
  useEffect(() => {
    const t = setTimeout(() => setAccount(accountInput.trim()), 400);
    return () => clearTimeout(t);
  }, [accountInput]);

  useEffect(() => { loadYears(); }, [loadYears]);
  useEffect(() => { load(); }, [load]);

  const fmtRp = (v) => {
    if (v === undefined || v === null) return "Rp 0";
    return (v < 0 ? "-Rp " : "Rp ") + Math.abs(Math.round(v)).toLocaleString("id-ID");
  };
  const fmtAxis = (v) => Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(0)}jt` : v;

  const accounts = (data?.accounts || []).filter(a => a.budget !== 0 || a.encumbrance !== 0 || a.actual !== 0);
  const accountChartData = accounts.map(a => ({
    name: a.account_name && a.account_name.length > 14 ? `${a.account_name.slice(0, 14)}…` : a.account_name,
    fullName: `${a.account_name} (${a.account_code})`,
    Budget: a.budget, Encumbrance: a.encumbrance, Actual: a.actual, "Funds Available": a.funds_available,
  }));
  const trendData = (detail?.monthly || []).map(m => ({
    period: m.month_name,
    Budget: m.budget, Encumbrance: m.encumbrance, Actual: m.actual, "Funds Available": m.funds_available,
  }));

  const tickStyle = { fill: "#cbd5e1", fontSize: 10 };
  const tooltipStyle = {
    contentStyle: { borderRadius: 8, fontSize: 11 },
    labelStyle: { color: "#1e293b", fontWeight: 600 },
    itemStyle: { color: "#334155" },
    cursor: { fill: "rgba(0,0,0,0.04)" },
  };

  const summary = data?.summary;

  return (
    <div className="space-y-4">
      {/* ── Controls — sama seperti GL Budget (Oracle) ── */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={year}
          onChange={e => setYear(+e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          {years.map(y => <option key={y} value={y}>{y}</option>)}
          {!years.includes(curYear) && <option value={curYear}>{curYear}</option>}
        </select>

        <select
          value={month}
          onChange={e => setMonth(+e.target.value)}
          title="Year-To-Date sampai bulan ini (mis. Maret = Jan-Mar dijumlah)"
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          <option value={0}>All Months (Jan-Des)</option>
          {MONTHS_ID.map((m, i) => <option key={i + 1} value={i + 1}>s.d. {m}</option>)}
        </select>

        <input
          value={accountInput}
          onChange={e => setAccountInput(e.target.value)}
          placeholder="Account code..."
          title="Filter per kode akun untuk lihat trend bulanan — kosongkan untuk bandingkan semua akun"
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 w-40"
        />

        {loading && <Loader2 size={16} className="animate-spin text-gray-600" />}
      </div>

      {loading && !data && <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>}

      {!loading && data && (
        <>
          {/* ── Summary cards (sama dengan GL Budget) ── */}
          {summary && accounts.length > 0 && (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
              <BudgetSummaryCard label="Budget"      value={fmtRp(summary.total_budget)}      color="text-blue-400"   bg="bg-blue-500/10   border-blue-500/20" />
              <BudgetSummaryCard label="Encumbrance" value={fmtRp(summary.total_encumbrance)} color="text-amber-400"  bg="bg-amber-500/10  border-amber-500/20" />
              <BudgetSummaryCard label="Actual"      value={fmtRp(summary.total_actual)}      color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
              <BudgetSummaryCard
                label="Funds Available"
                value={fmtRp(summary.total_funds_available)}
                color={summary.total_funds_available >= 0 ? "text-green-400" : "text-red-400"}
                bg={summary.total_funds_available >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"}
              />
            </div>
          )}

          {/* ── Bar chart per akun ── */}
          <SummaryChartCard title={`Budget vs Encumbrance vs Actual per Akun — ${year}${month ? ` (s.d. ${MONTHS_ID[month - 1]})` : ""}`}>
            {!RC ? (
              <div className="py-10 text-center text-xs text-gray-500">Loading chart…</div>
            ) : accountChartData.length === 0 ? (
              <div className="py-10 text-center text-xs text-gray-600">No budget data for year {year}.</div>
            ) : (
              <RC.ResponsiveContainer width="100%" height={Math.max(220, accountChartData.length * 42)}>
                <RC.BarChart data={accountChartData} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 4 }}>
                  <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <RC.XAxis type="number" tick={tickStyle} tickFormatter={fmtAxis} />
                  <RC.YAxis type="category" dataKey="name" tick={tickStyle} width={110} />
                  <RC.Tooltip {...tooltipStyle} formatter={(v, n) => [fmtRp(v), n]} labelFormatter={(_, p) => p?.[0]?.payload?.fullName} />
                  <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
                  <RC.Bar dataKey="Budget" fill="#60a5fa" radius={[0, 3, 3, 0]} />
                  <RC.Bar dataKey="Encumbrance" fill="#fbbf24" radius={[0, 3, 3, 0]} />
                  <RC.Bar dataKey="Actual" fill="#a78bfa" radius={[0, 3, 3, 0]} />
                </RC.BarChart>
              </RC.ResponsiveContainer>
            )}
          </SummaryChartCard>

          {/* ── Trend bulanan — hanya kalau 1 akun difilter ── */}
          {account && (
            <SummaryChartCard title={`Trend Bulanan — ${detail?.account_code || account}`}>
              {!RC || !detail ? (
                <div className="py-10 text-center text-xs text-gray-500">Loading chart…</div>
              ) : trendData.length === 0 ? (
                <div className="py-10 text-center text-xs text-gray-600">No monthly data for this account.</div>
              ) : (
                <RC.ResponsiveContainer width="100%" height={260}>
                  <RC.ComposedChart data={trendData} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
                    <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <RC.XAxis dataKey="period" tick={tickStyle} />
                    <RC.YAxis tick={tickStyle} tickFormatter={fmtAxis} />
                    <RC.Tooltip {...tooltipStyle} formatter={(v) => fmtRp(v)} />
                    <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
                    <RC.Bar dataKey="Budget" fill="#60a5fa" radius={[3, 3, 0, 0]} />
                    <RC.Bar dataKey="Encumbrance" fill="#fbbf24" radius={[3, 3, 0, 0]} />
                    <RC.Bar dataKey="Actual" fill="#a78bfa" radius={[3, 3, 0, 0]} />
                    <RC.Line type="monotone" dataKey="Funds Available" stroke="#34d399" strokeWidth={2.5} dot={{ r: 3, fill: "#34d399" }} />
                  </RC.ComposedChart>
                </RC.ResponsiveContainer>
              )}
            </SummaryChartCard>
          )}
        </>
      )}
    </div>
  );
}

// ── Team selector + access gate ─────────────────────────────────────────────
// Everyone can see Budget Monitoring, but each person defaults to (and is
// locked to) their own team's dept code, resolved server-side from their
// Employee record via GET /my-access. Only the IT team and a short list of
// exempted users get an enabled dropdown to browse any team.

function BudgetMonitoringSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const [sub, setSub] = useState("gl");
  const [access, setAccess] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [dept, setDept] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BUDGET_API}/my-access`, { headers: hdrs });
        if (res.ok) {
          const a = await res.json();
          setAccess(a);
          if (a.dept_code) setDept(a.dept_code);
        }
      } catch (_) {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BUDGET_API}/departments`, { headers: hdrs });
        if (res.ok) setDepartments(await res.json());
      } catch (_) {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Full-access users whose own team couldn't be resolved to a dept_code
  // (e.g. an exempted user with no matching Employee row) still need a
  // starting point — default to the first department once the LOV loads.
  useEffect(() => {
    if (access?.allowed_all && !dept && departments.length) setDept(departments[0].dept_code);
  }, [access, dept, departments]);

  if (!access) {
    return <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>;
  }

  if (!access.allowed_all && !access.dept_code) {
    return (
      <div className="py-16 text-center space-y-2">
        <Wallet size={32} className="mx-auto text-gray-700" />
        <p className="text-xs text-gray-600 max-w-sm mx-auto">
          Your team couldn't be matched to a budget department. Contact HR/IT to check your Employee record's Team field.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <label className="text-xs text-gray-500">Team</label>
        <select
          value={dept}
          onChange={e => setDept(e.target.value)}
          disabled={!access.allowed_all}
          title={access.allowed_all ? "Select a team to view its budget" : "You can only view your own team's budget"}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {departments.map(d => <option key={d.dept_code} value={d.dept_code}>{d.dept_name} ({d.dept_code})</option>)}
        </select>
        {!access.allowed_all && (
          <span className="flex items-center gap-1 text-[11px] text-gray-600">
            <Lock size={11} /> Locked to your team{access.team ? ` (${access.team})` : ""}
          </span>
        )}
      </div>
      <SubTabs
        tabs={[
          { id: "gl",    label: "GL Budget (Oracle)" },
          { id: "graph", label: "Budget Graph" },
        ]}
        active={sub} onChange={setSub}
      />
      {sub === "gl"    && <GLBudgetSection dept={dept} />}
      {sub === "graph" && <BudgetGraphSection dept={dept} />}
    </div>
  );
}

/* ── AP Outstanding with Payment ─────────────────────────────────────────
   Same Oracle data/filters as Accounting & Tax > AP Outstanding (AP_INVOICES_ALL
   + AP_PAYMENT_SCHEDULES_ALL), deliberately duplicated on the backend rather
   than shared so a change to one report can't silently break the other —
   extended with one row per (invoice, payment applied against it) via
   AP_INVOICE_PAYMENTS_ALL + AP_CHECKS_ALL. Placed under General (not gated
   to accounting_staff) per the request that payment visibility be
   company-wide. No revaluation/kurs columns here — this report is scoped to
   payment history, not currency revaluation (see AP Outstanding for that). */

const AP_PAYMENT_API = "/api/v1/dashboard/general/ap-payment";

const AP_PAYMENT_HEADERS = [
  { key: "supplier_name",        label: "Supplier" },
  { key: "transaction_type",     label: "Type" },
  { key: "transaction_number",   label: "Invoice No" },
  { key: "invoice_date",         label: "Invoice Date" },
  { key: "currency",             label: "Cur" },
  { key: "coa_number",           label: "Account" },
  { key: "coa_descpt",           label: "Account Desc" },
  { key: "payment_status",       label: "Status" },
  { key: "original_amount_idr",  label: "Orig Amt (IDR)",   num: true },
  { key: "remaining_amount_idr", label: "Remaining (IDR)",  num: true },
  { key: "payment_number",       label: "Payment No" },
  { key: "payment_date",         label: "Payment Date" },
  { key: "payment_amount",       label: "Payment Amount",   num: true },
  { key: "payment_method",       label: "Payment Method" },
  { key: "description",          label: "Description" },
];

function exportApPaymentCSV(rows) {
  if (!rows?.length) return;
  const lines = [
    "﻿" + AP_PAYMENT_HEADERS.map(h => h.label).join(","),
    ...rows.map(r => AP_PAYMENT_HEADERS.map(h => `"${String(r[h.key] ?? "").replace(/"/g, '""')}"`).join(",")),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "ap_outstanding_with_payment.csv"; a.click();
  URL.revokeObjectURL(url);
}

function APOutstandingWithPaymentSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const today = new Date().toISOString().slice(0, 10);

  const [asOfDate,        setAsOfDate]        = useState(today);
  const [dateFrom,        setDateFrom]        = useState("");
  const [dateTo,          setDateTo]          = useState("");
  const [supplierName,    setSupplierName]    = useState("");
  const [payStatusFilter, setPayStatusFilter] = useState("ALL");
  const [limit,           setLimit]           = useState(500);
  const [data,            setData]            = useState(null);
  const [loading,         setLoading]         = useState(false);
  const [error,           setError]           = useState(null);
  const [search,          setSearch]          = useState("");
  const [sortBy,          setSortBy]          = useState(null);
  const [sortDir,         setSortDir]         = useState("asc");

  const NUMERIC_KEYS = ["original_amount_idr", "remaining_amount_idr", "payment_amount"];

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ limit });
      if (asOfDate) params.set("as_of_date", asOfDate);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      if (supplierName) params.set("supplier_name", supplierName);
      if (payStatusFilter && payStatusFilter !== "ALL") params.set("payment_status", payStatusFilter);
      const res = await fetch(`${AP_PAYMENT_API}?${params}`, { headers: hdrs });
      const j = await res.json();
      if (res.ok && j.success) setData(j);
      else { setError(j.error || j.detail || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.message || String(e)); setData(null);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOfDate, dateFrom, dateTo, supplierName, payStatusFilter, limit]);

  useEffect(() => { loadData(); }, []); // eslint-disable-line

  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const filteredRows = (data?.data || []).filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.supplier_name       || "").toLowerCase().includes(q)
        || (r.transaction_number  || "").toLowerCase().includes(q)
        || (r.payment_number      || "").toLowerCase().includes(q)
        || (r.coa_descpt          || "").toLowerCase().includes(q);
  });
  const rows = useMemo(() => sortRows(filteredRows, sortBy, sortDir, NUMERIC_KEYS),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, search, sortBy, sortDir]);

  const fmtNum = (v) => v == null ? "" : Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const payBadge = (s) => {
    const cfg = {
      "Not Paid":       "bg-red-500/10 text-red-400",
      "Partially Paid": "bg-amber-500/10 text-amber-400",
    }[s] || "bg-gray-500/10 text-gray-400";
    return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap ${cfg}`}>{s}</span>;
  };

  const sm = data?.summary;
  const INPUT = "rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500";
  const LBL = "block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className={LBL}>As of Date</label>
          <input type="date" value={asOfDate} onChange={e => setAsOfDate(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL}>Period From</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL}>Period To</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL}>Supplier</label>
          <input value={supplierName} onChange={e => setSupplierName(e.target.value)} placeholder="Search supplier…"
            onKeyDown={e => e.key === "Enter" && loadData()} className={`${INPUT} w-48`} />
        </div>
        <div>
          <label className={LBL}>Pay Status</label>
          <select value={payStatusFilter} onChange={e => setPayStatusFilter(e.target.value)} className={`${INPUT} cursor-pointer`}>
            <option value="ALL">All Outstanding</option>
            <option value="Not Paid">Not Paid</option>
            <option value="Partially Paid">Partially Paid</option>
          </select>
        </div>
        <div>
          <label className={LBL}>Limit</label>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} className={`${INPUT} cursor-pointer`}>
            {[200, 500, 1000, 2000, 5000, 10000, 15000, 20000].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Load
        </button>
        <div className="flex-1" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter loaded rows…" className={`${INPUT} w-56`} />
        <button onClick={() => exportApPaymentCSV(rows)} disabled={!rows.length}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 px-3 py-1.5 text-xs text-white disabled:opacity-40 transition-colors">
          <Download size={12} /> Export CSV
        </button>
      </div>

      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {sm && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <BudgetSummaryCard label="Not Paid"        value={String(sm.not_paid_count)}     color="text-red-400"   bg="bg-red-500/10 border-red-500/20" />
          <BudgetSummaryCard label="Partially Paid"  value={String(sm.partial_paid_count)} color="text-amber-400" bg="bg-amber-500/10 border-amber-500/20" />
          <BudgetSummaryCard label="Invoices Shown"  value={String(data.invoice_count)}    color="text-blue-400"  bg="bg-blue-500/10 border-blue-500/20" />
          <BudgetSummaryCard label="Total Payment Applied (IDR)" value={`Rp ${fmtNum(sm.total_payment_applied_idr)}`} color="text-green-400" bg="bg-green-500/10 border-green-500/20" />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>
      ) : !data ? (
        <div className="py-16 text-center text-xs text-gray-600">Click Load to fetch data.</div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center text-xs text-gray-600">No rows match the current filters.</div>
      ) : (
        <div className="rounded-lg border border-gray-800 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-800/60">
                {AP_PAYMENT_HEADERS.map(h => (
                  <SortableTH key={h.key} label={h.label} field={h.key} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align={h.num ? "right" : "left"} />
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {rows.map((r, i) => (
                <tr key={`${r.invoice_id}-${r.payment_number || "none"}-${i}`} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.supplier_name}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.transaction_type}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.transaction_number}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.invoice_date}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.currency}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.coa_number}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.coa_descpt}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{payBadge(r.payment_status)}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtNum(r.original_amount_idr)}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtNum(r.remaining_amount_idr)}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.payment_number || "—"}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.payment_date || "—"}</td>
                  <td className="px-3 py-2 text-right text-green-400 tabular-nums whitespace-nowrap">{r.payment_amount != null ? fmtNum(r.payment_amount) : "—"}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.payment_method || "—"}</td>
                  <td className="px-3 py-2 text-gray-500">{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── AP List ──────────────────────────────────────────────────────────────
   Every AP transaction by GL Date, Paid and unpaid alike (unlike AP
   Outstanding with Payment above, which excludes Paid) — one row per
   invoice, format matching sumber/FORMAT LIST AP 2025.xlsx. DPP/VAT/WHT are
   a report-level calculation (DPP = invoice base, VAT = 11% of DPP computed
   fresh, WHT = real Oracle AWT distribution) confirmed against the
   reference file during planning — see AccountingService.get_ap_list's
   docstring for the full verification trail. Payment Status, by contrast,
   still comes from Oracle's real AP_PAYMENT_SCHEDULES_ALL state, same CASE
   logic as AP Outstanding with Payment, not derived from this report's own
   Total/Payment columns (the reference file's own status labels were found
   inconsistent with those). */

const AP_LIST_API = "/api/v1/dashboard/general/ap-list";

const AP_LIST_HEADERS = [
  { key: "row_no",            label: "No" },
  { key: "supplier_name",     label: "Supplier" },
  { key: "npwp",              label: "NPWP" },
  { key: "description",       label: "Description" },
  { key: "coa_number",        label: "COA" },
  { key: "coa_descpt",        label: "COA Desc" },
  { key: "transaction_type",  label: "Type" },
  { key: "transaction_number",label: "Transaction No" },
  { key: "invoice_date",      label: "Invoice Date" },
  { key: "gl_date",           label: "GL Date" },
  { key: "currency",          label: "Cur" },
  { key: "original_amount_orig", label: "Original Amount",  num: true },
  { key: "dpp",                label: "DPP",                num: true },
  { key: "vat",                label: "VAT",                num: true },
  { key: "wht",                label: "WHT",                num: true },
  { key: "total_ap",           label: "Total",              num: true },
  { key: "payment",            label: "Payment",            num: true },
  { key: "payment_rate",       label: "Payment Rate",       num: true },
  { key: "remaining_ap",       label: "Remaining AP",       num: true },
  { key: "payment_status",     label: "Status" },
];

function exportApListCSV(rows) {
  if (!rows?.length) return;
  const lines = [
    "﻿" + AP_LIST_HEADERS.map(h => h.label).join(","),
    ...rows.map(r => AP_LIST_HEADERS.map(h => `"${String(r[h.key] ?? "").replace(/"/g, '""')}"`).join(",")),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "ap_list.csv"; a.click();
  URL.revokeObjectURL(url);
}

function APListSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const today = new Date();
  const yearStart = `${today.getFullYear()}-01-01`;
  const todayStr = today.toISOString().slice(0, 10);

  const [glDateFrom,      setGlDateFrom]      = useState(yearStart);
  const [glDateTo,        setGlDateTo]        = useState(todayStr);
  const [paymentCutoff,   setPaymentCutoff]   = useState(todayStr);
  const [supplierName,    setSupplierName]    = useState("");
  const [payStatusFilter, setPayStatusFilter] = useState("ALL");
  const [limit,           setLimit]           = useState(500);
  const [data,            setData]            = useState(null);
  const [loading,         setLoading]         = useState(false);
  const [error,           setError]           = useState(null);
  const [search,          setSearch]          = useState("");
  const [sortBy,          setSortBy]          = useState(null);
  const [sortDir,         setSortDir]         = useState("asc");
  const [RC,              setRC]              = useState(null);

  useEffect(() => { import("recharts").then((mod) => setRC(mod)).catch(() => {}); }, []);

  const NUMERIC_KEYS = ["original_amount_orig", "dpp", "vat", "wht", "total_ap", "payment", "payment_rate", "remaining_ap"];

  const loadData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ limit });
      if (glDateFrom) params.set("gl_date_from", glDateFrom);
      if (glDateTo) params.set("gl_date_to", glDateTo);
      if (paymentCutoff) params.set("payment_date_cutoff", paymentCutoff);
      if (supplierName) params.set("supplier_name", supplierName);
      if (payStatusFilter && payStatusFilter !== "ALL") params.set("payment_status", payStatusFilter);
      const res = await fetch(`${AP_LIST_API}?${params}`, { headers: hdrs });
      const j = await res.json();
      if (res.ok && j.success) setData(j);
      else { setError(j.error || j.detail || "Failed to load"); setData(null); }
    } catch (e) {
      setError(e?.message || String(e)); setData(null);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glDateFrom, glDateTo, paymentCutoff, supplierName, payStatusFilter, limit]);

  useEffect(() => { loadData(); }, []); // eslint-disable-line

  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const filteredRows = (data?.data || []).filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.supplier_name       || "").toLowerCase().includes(q)
        || (r.transaction_number  || "").toLowerCase().includes(q)
        || (r.npwp                || "").toLowerCase().includes(q)
        || (r.coa_descpt          || "").toLowerCase().includes(q);
  });
  const rows = useMemo(() => sortRows(filteredRows, sortBy, sortDir, NUMERIC_KEYS),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, search, sortBy, sortDir]);

  const fmtNum = (v) => v == null ? "" : Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const payBadge = (s) => {
    const cfg = {
      "Not Paid":       "bg-red-500/10 text-red-400",
      "Partially Paid": "bg-amber-500/10 text-amber-400",
      "Paid":           "bg-green-500/10 text-green-400",
    }[s] || "bg-gray-500/10 text-gray-400";
    return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap ${cfg}`}>{s}</span>;
  };

  const sm = data?.summary;
  const INPUT = "rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500";
  const LBL = "block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className={LBL}>GL Date From</label>
          <input type="date" value={glDateFrom} onChange={e => setGlDateFrom(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL}>GL Date To</label>
          <input type="date" value={glDateTo} onChange={e => setGlDateTo(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL} title="Pembayaran setelah tanggal ini tidak dihitung sebagai Payment">Payment Date Cutoff</label>
          <input type="date" value={paymentCutoff} onChange={e => setPaymentCutoff(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label className={LBL}>Supplier</label>
          <input value={supplierName} onChange={e => setSupplierName(e.target.value)} placeholder="Search supplier…"
            onKeyDown={e => e.key === "Enter" && loadData()} className={`${INPUT} w-48`} />
        </div>
        <div>
          <label className={LBL}>Pay Status</label>
          <select value={payStatusFilter} onChange={e => setPayStatusFilter(e.target.value)} className={`${INPUT} cursor-pointer`}>
            <option value="ALL">All</option>
            <option value="Not Paid">Not Paid</option>
            <option value="Partially Paid">Partially Paid</option>
            <option value="Paid">Paid</option>
          </select>
        </div>
        <div>
          <label className={LBL}>Limit</label>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} className={`${INPUT} cursor-pointer`}>
            {[200, 500, 1000, 2000, 5000, 10000, 15000, 20000].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Load
        </button>
        <div className="flex-1" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter loaded rows…" className={`${INPUT} w-56`} />
        <button onClick={() => exportApListCSV(rows)} disabled={!rows.length}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 px-3 py-1.5 text-xs text-white disabled:opacity-40 transition-colors">
          <Download size={12} /> Export CSV
        </button>
      </div>

      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {data && data.total_count > data.count && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <AlertTriangle size={13} />
          Menampilkan {data.count.toLocaleString("id-ID")} dari total {data.total_count.toLocaleString("id-ID")} baris yang cocok dengan filter —
          naikkan Limit untuk menampilkan semuanya di tabel. Grafik &amp; kartu ringkasan di bawah selalu menghitung total sebenarnya, tidak dibatasi Limit.
        </div>
      )}

      {data?.monthly?.length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
          <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">Total AP per Bulan (sesuai filter, tidak dibatasi Limit)</p>
          {!RC ? (
            <div className="py-10 text-center text-xs text-gray-500">Loading chart…</div>
          ) : (
            <RC.ResponsiveContainer width="100%" height={260}>
              <RC.BarChart data={data.monthly} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
                <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <RC.XAxis dataKey="period" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
                <RC.YAxis tick={{ fill: "#cbd5e1", fontSize: 10 }} tickFormatter={(v) => `${(v / 1e6).toFixed(0)}jt`} />
                <RC.Tooltip contentStyle={{ borderRadius: 8, fontSize: 11 }} formatter={(v) => `Rp ${fmtNum(v)}`} />
                <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
                <RC.Bar dataKey="total_ap" name="Total AP" fill="#60a5fa" radius={[3, 3, 0, 0]} />
              </RC.BarChart>
            </RC.ResponsiveContainer>
          )}
        </div>
      )}

      {sm && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <BudgetSummaryCard label="Total DPP (IDR)"       value={`Rp ${fmtNum(sm.total_dpp)}`}       color="text-blue-400"   bg="bg-blue-500/10 border-blue-500/20" />
          <BudgetSummaryCard label="Total VAT (IDR)"       value={`Rp ${fmtNum(sm.total_vat)}`}       color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
          <BudgetSummaryCard label="Total WHT (IDR)"       value={`Rp ${fmtNum(sm.total_wht)}`}       color="text-amber-400"  bg="bg-amber-500/10 border-amber-500/20" />
          <BudgetSummaryCard label="Total AP (IDR)"        value={`Rp ${fmtNum(sm.total_ap)}`}        color="text-gray-200"   bg="bg-gray-800/40 border-gray-700" />
          <BudgetSummaryCard label="Total Payment (IDR)"   value={`Rp ${fmtNum(sm.total_payment)}`}   color="text-green-400"  bg="bg-green-500/10 border-green-500/20" />
          <BudgetSummaryCard label="Remaining AP (IDR)"    value={`Rp ${fmtNum(sm.total_remaining_ap)}`} color="text-red-400" bg="bg-red-500/10 border-red-500/20" />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>
      ) : !data ? (
        <div className="py-16 text-center text-xs text-gray-600">Click Load to fetch data.</div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center text-xs text-gray-600">No rows match the current filters.</div>
      ) : (
        <div className="rounded-lg border border-gray-800 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-800/60">
                {AP_LIST_HEADERS.map(h => (
                  <SortableTH key={h.key} label={h.label} field={h.key} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align={h.num ? "right" : "left"} />
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {rows.map((r, i) => (
                <tr key={`${r.invoice_id}-${i}`} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{r.row_no}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.supplier_name}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.npwp || "—"}</td>
                  <td className="px-3 py-2 text-gray-500">{r.description}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.coa_number}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.coa_descpt}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.transaction_type}</td>
                  <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.transaction_number}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.invoice_date}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.gl_date}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.currency}</td>
                  <td className="px-3 py-2 text-right text-gray-400 tabular-nums whitespace-nowrap">{r.original_amount_orig != null ? fmtNum(r.original_amount_orig) : "—"}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtNum(r.dpp)}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtNum(r.vat)}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtNum(r.wht)}</td>
                  <td className="px-3 py-2 text-right text-gray-200 tabular-nums font-semibold whitespace-nowrap">{fmtNum(r.total_ap)}</td>
                  <td className="px-3 py-2 text-right text-green-400 tabular-nums whitespace-nowrap">{fmtNum(r.payment)}</td>
                  <td className="px-3 py-2 text-right text-gray-400 tabular-nums whitespace-nowrap">{r.payment_rate != null ? fmtNum(r.payment_rate) : "—"}</td>
                  <td className="px-3 py-2 text-right text-red-400 tabular-nums whitespace-nowrap">{fmtNum(r.remaining_ap)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{payBadge(r.payment_status)}</td>
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

const GENERAL_TABS = ["budget", "ap-payment", "ap-list"];

export default function General() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeSection = GENERAL_TABS.find((id) => location.pathname.endsWith(id)) ?? "budget";

  useEffect(() => {
    if (location.pathname === "/dashboard/general" || location.pathname === "/dashboard/general/") {
      navigate("/dashboard/general/budget", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-6 space-y-4">
      {activeSection === "budget" && (
        <SectionCard>
          <BudgetMonitoringSection />
        </SectionCard>
      )}
      {activeSection === "ap-payment" && (
        <SectionCard title="AP Outstanding with Payment">
          <APOutstandingWithPaymentSection />
        </SectionCard>
      )}
      {activeSection === "ap-list" && (
        <SectionCard title="AP List">
          <APListSection />
        </SectionCard>
      )}
    </div>
  );
}
