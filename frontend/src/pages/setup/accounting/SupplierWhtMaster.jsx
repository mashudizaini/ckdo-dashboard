import { useState, useEffect, useMemo } from "react";
import { Search, Loader2, AlertTriangle, RefreshCw, Plus, Trash2, Pencil, X, DatabaseZap } from "lucide-react";
import { supplierWhtApi } from "@/api/dashboard";

const EMPTY_FORM = { vendor_id: "", vendor_name: "", awt_group_id: "", awt_group_name: "", tax_rate: "" };

// Sourced from real AP transaction history, not Oracle's (unused, empty)
// automatic-AWT config: each supplier's most-recent AWT-type invoice line
// (ap_invoice_lines_all.line_type_lookup_code = 'AWT') is read via
// supplier_wht_service.seed_from_oracle(). A row here with source="manual"
// was added/edited by hand and a Sync from Oracle never overwrites it.
export default function SupplierWhtMaster() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const load = async (q) => {
    setLoading(true);
    setError(null);
    try {
      const res = await supplierWhtApi.list(q);
      setRows(res.items || []);
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal memuat data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  useEffect(() => {
    const t = setTimeout(() => load(search || undefined), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const doSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    setError(null);
    try {
      const res = await supplierWhtApi.sync();
      setSyncResult(res);
      await load(search || undefined);
    } catch (e) {
      setError(e?.detail || e?.message || "Sync gagal");
    } finally {
      setSyncing(false);
    }
  };

  const openAdd = () => { setForm(EMPTY_FORM); setModalOpen(true); };
  const openEdit = (r) => {
    setForm({
      vendor_id: r.vendor_id, vendor_name: r.vendor_name || "",
      awt_group_id: r.awt_group_id ?? "", awt_group_name: r.awt_group_name || "",
      tax_rate: r.tax_rate ?? "",
    });
    setModalOpen(true);
  };

  const save = async () => {
    if (!form.vendor_id || !form.vendor_name || !form.tax_rate) return;
    setSaving(true);
    setError(null);
    try {
      await supplierWhtApi.upsert({
        vendor_id: Number(form.vendor_id),
        vendor_name: form.vendor_name,
        awt_group_id: form.awt_group_id ? Number(form.awt_group_id) : null,
        awt_group_name: form.awt_group_name,
        tax_rate: Number(form.tax_rate),
        updated_by: "manual",
      });
      setModalOpen(false);
      await load(search || undefined);
    } catch (e) {
      setError(e?.detail || e?.message || "Simpan gagal");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Hapus data WHT supplier ini?")) return;
    setDeletingId(id);
    try {
      await supplierWhtApi.remove(id);
      setRows(prev => prev.filter(r => r.id !== id));
    } catch (e) {
      setError(e?.detail || e?.message || "Hapus gagal");
    } finally {
      setDeletingId(null);
    }
  };

  const stats = useMemo(() => ({
    total: rows.length,
    oracle: rows.filter(r => r.source === "oracle").length,
    manual: rows.filter(r => r.source === "manual").length,
  }), [rows]);

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500 leading-relaxed max-w-3xl">
        Master rate PPh (withholding tax) per supplier. "Sync from Oracle" membaca histori transaksi
        AP nyata di EBS — baris invoice bertipe AWT (Automatic Withholding Tax) — dan mengambil grup/rate
        PPh yang PALING TERAKHIR dipakai untuk tiap supplier. Baris hasil edit manual (source: manual)
        tidak akan ditimpa oleh sync berikutnya.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Cari nama supplier atau grup PPh..."
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
          />
        </div>
        <button onClick={doSync} disabled={syncing}
          className="flex items-center gap-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-200 text-xs font-semibold px-3 py-2 transition-colors border border-gray-700">
          {syncing ? <Loader2 size={13} className="animate-spin" /> : <DatabaseZap size={13} />}
          Sync from Oracle
        </button>
        <button onClick={openAdd}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-2 transition-colors">
          <Plus size={13} /> Tambah Manual
        </button>
      </div>

      {syncResult && (
        <div className="rounded-lg px-4 py-2.5 text-xs bg-green-500/10 text-green-400 border border-green-500/20">
          Sync selesai — {syncResult.suppliers_found_in_oracle} supplier ditemukan di Oracle,
          {" "}{syncResult.upserted} baris diperbarui.
        </div>
      )}

      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      <div className="flex gap-3 text-[11px] text-gray-500">
        <span>{stats.total} supplier</span>
        <span className="text-gray-700">·</span>
        <span>{stats.oracle} dari Oracle</span>
        <span className="text-gray-700">·</span>
        <span>{stats.manual} manual</span>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center text-xs text-gray-600">
            Belum ada data. Klik "Sync from Oracle" untuk mengambil histori PPh dari transaksi AP.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 uppercase tracking-wider text-[10px]">
                <th className="text-left px-4 py-2.5 font-semibold">Vendor ID</th>
                <th className="text-left px-4 py-2.5 font-semibold">Supplier</th>
                <th className="text-left px-4 py-2.5 font-semibold">Grup PPh</th>
                <th className="text-right px-4 py-2.5 font-semibold">Rate</th>
                <th className="text-left px-4 py-2.5 font-semibold">Terakhir Dipakai</th>
                <th className="text-left px-4 py-2.5 font-semibold">Sumber</th>
                <th className="text-right px-4 py-2.5 font-semibold">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {rows.map(r => (
                <tr key={r.id} className="hover:bg-gray-800/40 transition-colors">
                  <td className="px-4 py-2.5 text-gray-400 font-mono">{r.vendor_id}</td>
                  <td className="px-4 py-2.5 text-gray-200">{r.vendor_name}</td>
                  <td className="px-4 py-2.5 text-gray-400">{r.awt_group_name || "—"}</td>
                  <td className="px-4 py-2.5 text-right text-gray-200 tabular-nums">
                    {r.tax_rate != null ? `${r.tax_rate}%` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">{r.last_used_date || "—"}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                      r.source === "oracle"
                        ? "border-blue-500/30 bg-blue-500/10 text-blue-300"
                        : "border-amber-500/30 bg-amber-500/10 text-amber-300"
                    }`}>
                      {r.source}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1">
                      <button onClick={() => openEdit(r)} className="p-1.5 rounded text-gray-500 hover:text-gray-200 hover:bg-gray-800">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => remove(r.id)} disabled={deletingId === r.id}
                        className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-gray-800 disabled:opacity-50">
                        {deletingId === r.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-md rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">Data WHT Supplier</h3>
              <button onClick={() => setModalOpen(false)} className="text-gray-500 hover:text-gray-200">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3">
              <Field label="Vendor ID (Oracle)">
                <input type="number" value={form.vendor_id}
                  onChange={e => setForm(f => ({ ...f, vendor_id: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </Field>
              <Field label="Nama Supplier">
                <input value={form.vendor_name}
                  onChange={e => setForm(f => ({ ...f, vendor_name: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </Field>
              <Field label="Grup PPh (mis. PPh23-2%-104)">
                <input value={form.awt_group_name}
                  onChange={e => setForm(f => ({ ...f, awt_group_name: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </Field>
              <Field label="Tax Rate (%)">
                <input type="number" step="0.01" value={form.tax_rate}
                  onChange={e => setForm(f => ({ ...f, tax_rate: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </Field>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setModalOpen(false)}
                className="rounded-lg border border-gray-700 px-3 py-2 text-xs font-semibold text-gray-400 hover:bg-gray-800">
                Batal
              </button>
              <button onClick={save} disabled={saving || !form.vendor_id || !form.vendor_name || !form.tax_rate}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2">
                {saving ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} className="hidden" />}
                Simpan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-semibold text-gray-500 mb-1">{label}</span>
      {children}
    </label>
  );
}
