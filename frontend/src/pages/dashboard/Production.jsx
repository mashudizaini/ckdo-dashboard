/**
 * Production Dashboard — Batch Status / Batch Yield / Schedule Adherence
 * ─────────────────────────────────────────
 * Reads eis.fact_batch, populated by app.tasks.eis_etl_tasks.etl_batches
 * (Oracle OPM gme_batch_header + gme_material_details's produced-item
 * line — this company runs Process Manufacturing batches, not discrete
 * WIP jobs, confirmed live before building). Yield is derived from
 * plan_qty/actual_qty on the product line, not gme_batch_steps' native
 * yield columns — those were checked live and found unpopulated (always
 * 0) in this instance. See production_service.py's docstring.
 * No dedicated Keycloak role exists for this team yet, so this page is
 * reachable by any authenticated user, same as PPWH/Sales & Marketing.
 *
 * Local helpers mirror PPWH.jsx's self-contained convention.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { RefreshCw, ListChecks, Percent, Clock, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const PRODUCTION_API = "/api/v1/dashboard/production";
const STATUS_COLOR = {
  Closed: "bg-green-500/15 text-green-400",
  Completed: "bg-blue-500/15 text-blue-400",
  WIP: "bg-amber-500/15 text-amber-400",
  Pending: "bg-gray-500/15 text-gray-400",
  Cancelled: "bg-red-500/15 text-red-400",
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

function StatusBadge({ status }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${STATUS_COLOR[status] || "bg-gray-500/15 text-gray-400"}`}>
      {status || "—"}
    </span>
  );
}

const fmtQty = (v) => {
  if (v === undefined || v === null) return "0";
  return Number(v).toLocaleString("id-ID", { maximumFractionDigits: 2 });
};
const fmtDate = (v) => (v ? String(v).slice(0, 10) : "—");
const fmtPct = (v) => (v === undefined || v === null ? "—" : `${v}%`);

const defaultDateRange = () => {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 90);
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { from: fmt(from), to: fmt(to) };
};

function useOrganizations() {
  const { token } = useAuthStore();
  const [orgs, setOrgs] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${PRODUCTION_API}/organizations`, { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) setOrgs(await res.json());
      } catch (_) {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return orgs;
}

function OrgSelect({ orgs, value, onChange }) {
  return (
    <div>
      <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Organisasi</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 cursor-pointer">
        <option value="">Semua</option>
        {orgs.map((o) => <option key={o.organization_id} value={o.organization_id}>{o.organization_name}</option>)}
      </select>
    </div>
  );
}

function DateRangeInputs({ dateFrom, setDateFrom, dateTo, setDateTo }) {
  return (
    <>
      <div>
        <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Dari</label>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500" />
      </div>
      <div>
        <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Sampai</label>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500" />
      </div>
    </>
  );
}

function StatusOverviewSection() {
  const { token } = useAuthStore();
  const orgs = useOrganizations();
  const def = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(def.from);
  const [dateTo, setDateTo] = useState(def.to);
  const [orgId, setOrgId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [RC, setRC] = useState(null);

  useEffect(() => { import("recharts").then((mod) => setRC(mod)).catch(() => {}); }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (orgId) params.set("organization_id", orgId);
      const res = await fetch(`${PRODUCTION_API}/status-overview?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, orgId]);

  useEffect(() => { load(); }, [load]);

  const trend = data?.trend || [];
  const byStatus = data?.by_status || [];
  const rows = data?.rows || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <DateRangeInputs dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
        <OrgSelect orgs={orgs} value={orgId} onChange={setOrgId} />
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="Total Batch" value={String(data.total_batches)} color="text-blue-400" bg="bg-blue-500/10 border-blue-500/20" />
          <KpiCard label="Tingkat Pembatalan" value={fmtPct(data.cancellation_rate)}
            color={data.cancellation_rate > 15 ? "text-red-400" : "text-green-400"}
            bg={data.cancellation_rate > 15 ? "bg-red-500/10 border-red-500/20" : "bg-green-500/10 border-green-500/20"} />
        </div>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
        <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">Trend Batch Dimulai</p>
        {loading || !RC ? (
          <div className="py-10 text-center text-xs text-gray-500">Loading…</div>
        ) : trend.length === 0 ? (
          <div className="py-10 text-center text-xs text-gray-600">Tidak ada data untuk periode ini.</div>
        ) : (
          <RC.ResponsiveContainer width="100%" height={220}>
            <RC.BarChart data={trend} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
              <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <RC.XAxis dataKey="txn_date" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
              <RC.YAxis tick={{ fill: "#cbd5e1", fontSize: 10 }} allowDecimals={false} />
              <RC.Tooltip contentStyle={{ borderRadius: 8, fontSize: 11 }} />
              <RC.Bar dataKey="batch_count" fill="#60a5fa" radius={[3, 3, 0, 0]} />
            </RC.BarChart>
          </RC.ResponsiveContainer>
        )}
      </div>

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Status</th>
              <th className="px-3 py-2 text-right font-semibold">Jumlah Batch</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {byStatus.length === 0 ? (
              <tr><td colSpan={2} className="px-3 py-8 text-center text-gray-600">Tidak ada data.</td></tr>
            ) : byStatus.map((r) => (
              <tr key={r.batch_status_name} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 whitespace-nowrap"><StatusBadge status={r.batch_status_name} /></td>
                <td className="px-3 py-2 text-right text-gray-300 tabular-nums">{r.batch_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Batch No</th>
              <th className="px-3 py-2 text-left font-semibold">Produk</th>
              <th className="px-3 py-2 text-left font-semibold">Status</th>
              <th className="px-3 py-2 text-left font-semibold">Plan Mulai</th>
              <th className="px-3 py-2 text-left font-semibold">Selesai Aktual</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {rows.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-600">Tidak ada batch pada periode ini.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.batch_id} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.batch_no}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.product_item_code} — {r.product_item_description || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap"><StatusBadge status={r.batch_status_name} /></td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtDate(r.plan_start_date)}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtDate(r.actual_cmplt_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function YieldSection() {
  const { token } = useAuthStore();
  const orgs = useOrganizations();
  const def = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(def.from);
  const [dateTo, setDateTo] = useState(def.to);
  const [orgId, setOrgId] = useState("");
  const [productCode, setProductCode] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (orgId) params.set("organization_id", orgId);
      if (productCode) params.set("product_code", productCode);
      const res = await fetch(`${PRODUCTION_API}/yield?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, orgId, productCode]);

  useEffect(() => { load(); }, [load]);

  const byProduct = data?.by_product || [];
  const rows = data?.rows || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <DateRangeInputs dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
        <OrgSelect orgs={orgs} value={orgId} onChange={setOrgId} />
        <div>
          <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Kode Produk</label>
          <input value={productCode} onChange={(e) => setProductCode(e.target.value)} placeholder="Semua produk…"
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 w-44" />
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="Yield Keseluruhan" value={fmtPct(data.overall_yield_pct)}
            color={data.overall_yield_pct >= 90 ? "text-green-400" : "text-amber-400"}
            bg={data.overall_yield_pct >= 90 ? "bg-green-500/10 border-green-500/20" : "bg-amber-500/10 border-amber-500/20"} />
          <KpiCard label="Jumlah Produk" value={String(byProduct.length)} color="text-gray-300" bg="bg-gray-800/40 border-gray-700" />
        </div>
      )}

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Produk</th>
              <th className="px-3 py-2 text-right font-semibold">Jumlah Batch</th>
              <th className="px-3 py-2 text-right font-semibold">Plan Qty</th>
              <th className="px-3 py-2 text-right font-semibold">Actual Qty</th>
              <th className="px-3 py-2 text-right font-semibold">Yield %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {loading ? (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-500"><Loader2 size={16} className="animate-spin inline" /></td></tr>
            ) : byProduct.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-600">Tidak ada data batch selesai pada periode ini.</td></tr>
            ) : byProduct.map((r) => (
              <tr key={r.product_item_code} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.product_item_code} — {r.product_item_description || "—"}</td>
                <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{r.batch_count}</td>
                <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{fmtQty(r.total_plan_qty)}</td>
                <td className="px-3 py-2 text-right text-gray-300 tabular-nums">{fmtQty(r.total_actual_qty)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-semibold ${
                  r.yield_pct >= 90 ? "text-green-400" : r.yield_pct >= 70 ? "text-amber-400" : "text-red-400"
                }`}>{fmtPct(r.yield_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Batch No</th>
              <th className="px-3 py-2 text-left font-semibold">Produk</th>
              <th className="px-3 py-2 text-left font-semibold">Selesai</th>
              <th className="px-3 py-2 text-right font-semibold">Plan Qty</th>
              <th className="px-3 py-2 text-right font-semibold">Actual Qty</th>
              <th className="px-3 py-2 text-right font-semibold">Yield %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {rows.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-600">Tidak ada data.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.batch_id} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.batch_no}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.product_item_code}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtDate(r.actual_cmplt_date)}</td>
                <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{fmtQty(r.product_plan_qty)}</td>
                <td className="px-3 py-2 text-right text-gray-300 tabular-nums">{fmtQty(r.product_actual_qty)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-semibold ${
                  r.yield_pct >= 90 ? "text-green-400" : r.yield_pct >= 70 ? "text-amber-400" : "text-red-400"
                }`}>{fmtPct(r.yield_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScheduleAdherenceSection() {
  const { token } = useAuthStore();
  const orgs = useOrganizations();
  const def = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(def.from);
  const [dateTo, setDateTo] = useState(def.to);
  const [orgId, setOrgId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (orgId) params.set("organization_id", orgId);
      const res = await fetch(`${PRODUCTION_API}/schedule-adherence?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, orgId]);

  useEffect(() => { load(); }, [load]);

  const rows = data?.rows || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <DateRangeInputs dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
        <OrgSelect orgs={orgs} value={orgId} onChange={setOrgId} />
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <KpiCard label="Batch Selesai" value={String(data.total_batches)} color="text-gray-300" bg="bg-gray-800/40 border-gray-700" />
          <KpiCard label="Tepat Waktu" value={fmtPct(data.on_time_rate)}
            color={data.on_time_rate >= 80 ? "text-green-400" : "text-amber-400"}
            bg={data.on_time_rate >= 80 ? "bg-green-500/10 border-green-500/20" : "bg-amber-500/10 border-amber-500/20"} />
          <KpiCard label="Rata-rata Keterlambatan (hari)" value={data.avg_delay_days != null ? String(data.avg_delay_days) : "—"}
            color={data.avg_delay_days > 0 ? "text-red-400" : "text-green-400"}
            bg={data.avg_delay_days > 0 ? "bg-red-500/10 border-red-500/20" : "bg-green-500/10 border-green-500/20"} />
        </div>
      )}

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Batch No</th>
              <th className="px-3 py-2 text-left font-semibold">Produk</th>
              <th className="px-3 py-2 text-left font-semibold">Plan Selesai</th>
              <th className="px-3 py-2 text-left font-semibold">Selesai Aktual</th>
              <th className="px-3 py-2 text-right font-semibold">Keterlambatan (hari)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {loading ? (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-500"><Loader2 size={16} className="animate-spin inline" /></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-600">Tidak ada batch selesai pada periode ini.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.batch_id} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.batch_no}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.product_item_code} — {r.product_item_description || "—"}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtDate(r.plan_cmplt_date)}</td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtDate(r.actual_cmplt_date)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-semibold ${r.delay_days > 0 ? "text-red-400" : "text-green-400"}`}>
                  {r.delay_days > 0 ? "+" : ""}{r.delay_days}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Root ─────────────────────────────────────────────────────────────── */

const TABS = [
  { id: "status",   label: "Batch Status",       icon: ListChecks },
  { id: "yield",    label: "Batch Yield",        icon: Percent },
  { id: "schedule", label: "Schedule Adherence", icon: Clock },
];

export default function Production() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeSection = TABS.map((t) => t.id).find((id) => location.pathname.endsWith(id)) ?? "status";

  useEffect(() => {
    if (location.pathname === "/dashboard/production" || location.pathname === "/dashboard/production/") {
      navigate("/dashboard/production/status", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-6 space-y-4">
      <SubTabs tabs={TABS} active={activeSection} onChange={(id) => navigate(`/dashboard/production/${id}`)} />
      {activeSection === "status" && (
        <SectionCard title="Batch Status Overview"><StatusOverviewSection /></SectionCard>
      )}
      {activeSection === "yield" && (
        <SectionCard title="Batch Yield Performance"><YieldSection /></SectionCard>
      )}
      {activeSection === "schedule" && (
        <SectionCard title="Schedule Adherence"><ScheduleAdherenceSection /></SectionCard>
      )}
    </div>
  );
}
