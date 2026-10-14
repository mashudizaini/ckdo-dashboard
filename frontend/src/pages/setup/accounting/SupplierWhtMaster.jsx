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
  const [activeBusyId, setActiveBusyId] = useState(null);

  const load = async (q) => {
    setLoading(true);
    setError(null);
    try {
      const res = await supplierWhtApi.list(q);
      setRows(res.items || []);
    } catch (e) {
      setError(e?.detail || e?.message || "Failed to load data");
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
      setError(e?.detail || e?.message || "Sync failed");
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
      setError(e?.detail || e?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (r) => {
    setActiveBusyId(r.id);
    try {
      await supplierWhtApi.setActive(r.id, !r.is_active);
      setRows(prev => prev.map(row => row.id === r.id ? { ...row, is_active: !r.is_active } : row));
    } catch (e) {
      setError(e?.detail || e?.message || "Failed to update the active flag");
    } finally {
      setActiveBusyId(null);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this supplier's WHT data?")) return;
    setDeletingId(id);
    try {
      await supplierWhtApi.remove(id);
      setRows(prev => prev.filter(r => r.id !== id));
    } catch (e) {
      setError(e?.detail || e?.message || "Delete failed");
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
        PPh (withholding tax) rate master per supplier. "Sync from Oracle" reads the real AP transaction
        history in EBS — invoice lines of type AWT (Automatic Withholding Tax) — and takes the PPh group/rate
        MOST RECENTLY used for each supplier. Manually edited rows (source: manual) are not overwritten by
        later syncs. If a supplier has more than one vendor ID in Oracle with the same group/rate, only one
        row is kept; if the group/rate differs, every row is kept but only one is marked
        <strong className="text-gray-300"> Active</strong> (default: the most recently used) — the Active
        tick can be changed manually at any time.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search supplier name or PPh group..."
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
          <Plus size={13} /> Add Manually
        </button>
      </div>

      {syncResult && (
        <div className="rounded-lg px-4 py-2.5 text-xs bg-green-500/10 text-green-400 border border-green-500/20">
          Sync done — {syncResult.suppliers_found_in_oracle} suppliers found in Oracle,
          {" "}{syncResult.upserted} rows updated.
          {syncResult.internal_employee_suppliers_excluded > 0 &&
            ` ${syncResult.internal_employee_suppliers_excluded} internal (employee) suppliers excluded.`}
          {syncResult.duplicate_entries_collapsed > 0 &&
            ` ${syncResult.duplicate_entries_collapsed} duplicate rows (same group/rate) merged.`}
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
        <span>{stats.oracle} from Oracle</span>
        <span className="text-gray-700">·</span>
        <span>{stats.manual} manual</span>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center text-xs text-gray-600">
            No data yet. Click "Sync from Oracle" to pull the PPh history from AP transactions.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 uppercase tracking-wider text-[10px]">
                <th className="text-left px-4 py-2.5 font-semibold">Vendor ID</th>
                <th className="text-left px-4 py-2.5 font-semibold">Supplier</th>
                <th className="text-left px-4 py-2.5 font-semibold">PPh Group</th>
                <th className="text-right px-4 py-2.5 font-semibold">Rate</th>
                <th className="text-left px-4 py-2.5 font-semibold">Last Used</th>
                <th className="text-left px-4 py-2.5 font-semibold">Source</th>
                <th className="text-center px-4 py-2.5 font-semibold">Active</th>
                <th className="text-right px-4 py-2.5 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {rows.map(r => (
                <tr key={r.id} className={`hover:bg-gray-800/40 transition-colors ${r.is_active ? "" : "opacity-50"}`}>
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
                  <td className="px-4 py-2.5 text-center">
                    {activeBusyId === r.id ? (
                      <Loader2 size={13} className="animate-spin text-gray-500 mx-auto" />
                    ) : (
                      <input type="checkbox" checked={!!r.is_active} onChange={() => toggleActive(r)}
                        title="This row is used when the same supplier has several Vendor IDs"
                        className="w-3.5 h-3.5 cursor-pointer" />
                    )}
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
              <Field label="Supplier Name">
                <input value={form.vendor_name}
                  onChange={e => setForm(f => ({ ...f, vendor_name: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </Field>
              <Field label="PPh Group (e.g. PPh23-2%-104)">
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
                Cancel
              </button>
              <button onClick={save} disabled={saving || !form.vendor_id || !form.vendor_name || !form.tax_rate}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2">
                {saving ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} className="hidden" />}
                Save
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
