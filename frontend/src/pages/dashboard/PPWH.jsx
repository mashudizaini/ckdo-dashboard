/**
 * PPWH Dashboard — Inventory In / Inventory Out / Kartu Stok
 * ─────────────────────────────────────────
 * Reads eis.fact_inventory_txn, populated by app.tasks.eis_etl_tasks.
 * etl_inventory_txn (Oracle INV mtl_material_transactions). direction
 * ('IN'/'OUT') is derived server-side from the signed quantity, not a
 * hardcoded transaction-type list — see ppwh_service.py's docstring.
 * No dedicated Keycloak role exists for this team yet, so this page is
 * reachable by any authenticated user, same as Sales & Marketing/General.
 *
 * Local helpers mirror SalesMarketing.jsx's self-contained convention.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { RefreshCw, ArrowDownCircle, ArrowUpCircle, ClipboardList, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const PPWH_API = "/api/v1/dashboard/ppwh";
const DIR_COLOR = { IN: "#34d399", OUT: "#f87171" };

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

const fmtQty = (v) => {
  if (v === undefined || v === null) return "0";
  return Number(v).toLocaleString("id-ID", { maximumFractionDigits: 2 });
};

const defaultDateRange = () => {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 30);
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { from: fmt(from), to: fmt(to) };
};

function useOrganizations() {
  const { token } = useAuthStore();
  const [orgs, setOrgs] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${PPWH_API}/organizations`, { headers: { Authorization: `Bearer ${token}` } });
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
        {orgs.map((o) => <option key={o.organization_code} value={o.organization_code}>{o.organization_code} — {o.organization_name}</option>)}
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

/* ── Inventory In / Inventory Out — identical shape, different endpoint
   and direction, so one component covers both (see TABS below). ── */
function DirectionSection({ direction }) {
  const { token } = useAuthStore();
  const orgs = useOrganizations();
  const def = defaultDateRange();
  const [dateFrom, setDateFrom] = useState(def.from);
  const [dateTo, setDateTo] = useState(def.to);
  const [orgCode, setOrgCode] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [RC, setRC] = useState(null);

  useEffect(() => { import("recharts").then((mod) => setRC(mod)).catch(() => {}); }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (orgCode) params.set("organization_code", orgCode);
      const endpoint = direction === "IN" ? "inbound" : "outbound";
      const res = await fetch(`${PPWH_API}/${endpoint}?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, orgCode, direction]);

  useEffect(() => { load(); }, [load]);

  const trend = data?.trend || [];
  const byType = data?.by_type || [];
  const color = DIR_COLOR[direction];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <DateRangeInputs dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
        <OrgSelect orgs={orgs} value={orgCode} onChange={setOrgCode} />
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="Total Qty" value={fmtQty(data.total_qty)}
            color={direction === "IN" ? "text-green-400" : "text-red-400"}
            bg={direction === "IN" ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"} />
          <KpiCard label="Total Transaksi" value={String(data.total_txn_count)} color="text-gray-300" bg="bg-gray-800/40 border-gray-700" />
        </div>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
        <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">Trend Harian</p>
        {loading || !RC ? (
          <div className="py-10 text-center text-xs text-gray-500">Loading…</div>
        ) : trend.length === 0 ? (
          <div className="py-10 text-center text-xs text-gray-600">Tidak ada data untuk periode ini.</div>
        ) : (
          <RC.ResponsiveContainer width="100%" height={260}>
            <RC.BarChart data={trend} margin={{ top: 4, right: 16, bottom: 0, left: -10 }}>
              <RC.CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <RC.XAxis dataKey="txn_date" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
              <RC.YAxis tick={{ fill: "#cbd5e1", fontSize: 10 }} />
              <RC.Tooltip contentStyle={{ borderRadius: 8, fontSize: 11 }} formatter={(v) => fmtQty(v)} />
              <RC.Bar dataKey="qty" fill={color} radius={[3, 3, 0, 0]} />
            </RC.BarChart>
          </RC.ResponsiveContainer>
        )}
      </div>

      <div className="rounded-lg border border-gray-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left font-semibold">Jenis Transaksi</th>
              <th className="px-3 py-2 text-right font-semibold">Jumlah Transaksi</th>
              <th className="px-3 py-2 text-right font-semibold">Total Qty</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {byType.length === 0 ? (
              <tr><td colSpan={3} className="px-3 py-8 text-center text-gray-600">Tidak ada data.</td></tr>
            ) : byType.map((r) => (
              <tr key={r.transaction_type_name} className="hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.transaction_type_name}</td>
                <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{r.txn_count}</td>
                <td className="px-3 py-2 text-right text-gray-300 tabular-nums">{fmtQty(r.qty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StockCardSection() {
  const { token } = useAuthStore();
  const orgs = useOrganizations();
  const def = defaultDateRange();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null); // { item_code, item_description } | null
  const [dateFrom, setDateFrom] = useState(def.from);
  const [dateTo, setDateTo] = useState(def.to);
  const [orgCode, setOrgCode] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!query || query.length < 2 || (selectedItem && query === selectedItem.item_code)) { setSuggestions([]); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${PPWH_API}/items?q=${encodeURIComponent(query)}`, { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) setSuggestions((await res.json()).data);
      } catch (_) {}
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const load = useCallback(async () => {
    if (!selectedItem) return;
    setLoading(true);
    setData(null);
    try {
      const params = new URLSearchParams({ item_code: selectedItem.item_code, date_from: dateFrom, date_to: dateTo });
      if (orgCode) params.set("organization_code", orgCode);
      const res = await fetch(`${PPWH_API}/stock-card?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      setData(res.ok ? await res.json() : null);
    } catch (_) {
      setData(null);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedItem, dateFrom, dateTo, orgCode]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative">
          <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Item</label>
          <input value={query} onChange={(e) => { setQuery(e.target.value); setSelectedItem(null); }}
            placeholder="Cari item code / nama…"
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 w-64" />
          {suggestions.length > 0 && (
            <div className="absolute z-10 mt-1 w-96 max-h-64 overflow-y-auto rounded-lg border border-gray-700 bg-gray-900 shadow-lg">
              {suggestions.map((s) => (
                <button key={s.item_code} onClick={() => { setSelectedItem(s); setQuery(s.item_code); setSuggestions([]); }}
                  className="block w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-800">
                  <span className="font-semibold">{s.item_code}</span> — {s.item_description || "—"}
                </button>
              ))}
            </div>
          )}
        </div>
        <DateRangeInputs dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
        <OrgSelect orgs={orgs} value={orgCode} onChange={setOrgCode} />
      </div>

      {!selectedItem ? (
        <div className="py-16 text-center text-xs text-gray-600">Cari dan pilih item untuk melihat kartu stok.</div>
      ) : loading ? (
        <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>
      ) : !data ? (
        <div className="py-16 text-center text-xs text-gray-600">Gagal memuat data kartu stok.</div>
      ) : (
        <>
          <p className="text-sm text-gray-200 font-semibold">{data.item_code} — {data.item_description || "—"}</p>
          <div className="grid grid-cols-2 gap-3">
            <KpiCard label="Saldo Awal" value={fmtQty(data.saldo_awal)} color="text-gray-300" bg="bg-gray-800/40 border-gray-700" />
            <KpiCard label="Saldo Akhir" value={fmtQty(data.saldo_akhir)} color="text-blue-400" bg="bg-blue-500/10 border-blue-500/20" />
          </div>
          <div className="rounded-lg border border-gray-800 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-800/60 text-gray-500 uppercase tracking-wider">
                  <th className="px-3 py-2 text-left font-semibold">Tanggal</th>
                  <th className="px-3 py-2 text-left font-semibold">Jenis Transaksi</th>
                  <th className="px-3 py-2 text-left font-semibold">Subinventory</th>
                  <th className="px-3 py-2 text-right font-semibold">Qty</th>
                  <th className="px-3 py-2 text-right font-semibold">Saldo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {data.rows.length === 0 ? (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-600">Tidak ada mutasi pada periode ini.</td></tr>
                ) : data.rows.map((r) => (
                  <tr key={r.transaction_id} className="hover:bg-gray-800/30">
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.transaction_date?.slice(0, 10)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold mr-1.5 ${
                        r.direction === "IN" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"
                      }`}>{r.direction}</span>
                      <span className="text-gray-300">{r.transaction_type_name}</span>
                    </td>
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{r.subinventory_name || r.subinventory_code || "—"}</td>
                    <td className={`px-3 py-2 text-right tabular-nums whitespace-nowrap ${r.direction === "IN" ? "text-green-400" : "text-red-400"}`}>
                      {r.direction === "IN" ? "+" : ""}{fmtQty(r.quantity)}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-300 tabular-nums whitespace-nowrap">{fmtQty(r.running_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Root ─────────────────────────────────────────────────────────────── */

const TABS = [
  { id: "inbound",    label: "Inventory In",  icon: ArrowDownCircle },
  { id: "outbound",   label: "Inventory Out", icon: ArrowUpCircle },
  { id: "stock-card", label: "Kartu Stok",     icon: ClipboardList },
];

export default function PPWH() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeSection = TABS.map((t) => t.id).find((id) => location.pathname.endsWith(id)) ?? "inbound";

  useEffect(() => {
    if (location.pathname === "/dashboard/ppwh" || location.pathname === "/dashboard/ppwh/") {
      navigate("/dashboard/ppwh/inbound", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-6 space-y-4">
      <SubTabs tabs={TABS} active={activeSection} onChange={(id) => navigate(`/dashboard/ppwh/${id}`)} />
      {activeSection === "inbound" && (
        <SectionCard title="Inventory In (Penerimaan Barang)"><DirectionSection direction="IN" /></SectionCard>
      )}
      {activeSection === "outbound" && (
        <SectionCard title="Inventory Out (Pengeluaran Barang)"><DirectionSection direction="OUT" /></SectionCard>
      )}
      {activeSection === "stock-card" && (
        <SectionCard title="Kartu Stok"><StockCardSection /></SectionCard>
      )}
    </div>
  );
}
