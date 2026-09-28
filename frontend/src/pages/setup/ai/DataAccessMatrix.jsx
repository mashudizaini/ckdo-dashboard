import { useEffect, useMemo, useState } from "react";
import { Grid3x3, Loader2, Plus, Trash2, Info, EyeOff } from "lucide-react";
import api from "@/api/client";

// Data access matrix for EBS chat — backend: app/services/ebs_mart/policy.py,
// endpoints /ai/ebs-mart/access-policy*. Each cell is one role × one data set:
//   —      no access
//   Qty    quantities, dates and names only; price / value / amount columns
//          are removed from every answer and run_sql may not read them
//   Full   every column
// System Administration data (sa_*) is not here: it follows the IT email
// allowlist only.

const DOMAIN_LABEL = {
  AP: "Hutang (AP)", AR: "Piutang (AR)", PO: "Pembelian (PO/PR)", INV: "Persediaan", OM: "Penjualan (OM)",
  OPM: "Produksi (OPM)", GL: "Buku besar (GL)", CE: "Kas & bank", FA: "Aset tetap", MASTER: "Master data",
};
const DOMAIN_ORDER = ["INV", "PO", "AP", "OM", "AR", "OPM", "GL", "CE", "FA", "MASTER"];

const LEVEL_STYLE = {
  "": "border-gray-800 bg-gray-900 text-gray-600",
  qty: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  full: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
};

const errText = (e) => {
  const d = e?.detail ?? e?.response?.data?.detail;
  return d ? (typeof d === "string" ? d : JSON.stringify(d)) : e?.message || "Terjadi kesalahan";
};

export default function DataAccessMatrix({ onRolesChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(null); // "role|mart" of the cell being saved
  const [newRole, setNewRole] = useState({ code: "", label: "" });
  const [addingRole, setAddingRole] = useState(false);

  const load = async () => {
    try {
      setData(await api.get("/ai/ebs-mart/access-policy"));
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  };
  useEffect(() => { load(); }, []);

  const grantOf = useMemo(() => {
    const m = {};
    (data?.grants || []).forEach((g) => { m[`${g.role_code}|${g.mart}`] = g.level; });
    return m;
  }, [data]);

  const byDomain = useMemo(() => {
    const groups = {};
    (data?.marts || []).forEach((m) => { (groups[m.domain] ||= []).push(m); });
    return DOMAIN_ORDER.filter((d) => groups[d]).map((d) => [d, groups[d]])
      .concat(Object.keys(groups).filter((d) => !DOMAIN_ORDER.includes(d)).map((d) => [d, groups[d]]));
  }, [data]);

  const setLevel = async (role, mart, level) => {
    const key = `${role}|${mart}`;
    setSaving(key);
    setError(null);
    try {
      await api.put("/ai/ebs-mart/access-policy/grant", { role_code: role, mart, level: level || null });
      setData((d) => ({
        ...d,
        grants: [...d.grants.filter((g) => !(g.role_code === role && g.mart === mart)),
                 ...(level ? [{ role_code: role, mart, level }] : [])],
      }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setSaving(null);
    }
  };

  const addRole = async (e) => {
    e.preventDefault();
    const code = newRole.code.trim().toLowerCase();
    if (!code || !newRole.label.trim()) return;
    setAddingRole(true);
    setError(null);
    try {
      await api.put(`/ai/ebs-mart/access-policy/roles/${encodeURIComponent(code)}`,
        { label: newRole.label.trim(), all_access: false });
      setNewRole({ code: "", label: "" });
      await load();
      onRolesChange?.();
    } catch (err) {
      setError(errText(err));
    } finally {
      setAddingRole(false);
    }
  };

  const deleteRole = async (code) => {
    setError(null);
    try {
      await api.delete(`/ai/ebs-mart/access-policy/roles/${encodeURIComponent(code)}`);
      await load();
      onRolesChange?.();
    } catch (err) {
      setError(errText(err));
    }
  };

  if (!data && !error) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 flex justify-center">
        <Loader2 size={18} className="animate-spin text-gray-500" />
      </div>
    );
  }

  const roles = data?.roles || [];
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="px-5 py-3 border-b border-gray-800 flex items-start gap-2.5">
        <Grid3x3 size={16} className="text-blue-400 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-200">Hak akses data per peran</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Berlaku untuk EBS Analyst, EBS Finance Controller dan EBS Support di CoChat — diperiksa dashboard di
            setiap panggilan tool, tidak bergantung pada prompt. Perubahan aktif dalam 30 detik.
          </p>
        </div>
      </div>

      <div className="px-5 py-3 border-b border-gray-800 flex flex-wrap gap-x-5 gap-y-1.5 text-[11px] text-gray-400">
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE[""]}`}>—</span> tidak ada akses</span>
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE.qty}`}>Qty</span> hanya kuantitas, tanggal, nama — kolom nilai/harga disembunyikan</span>
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE.full}`}>Full</span> semua kolom</span>
        <span className="flex items-center gap-1.5 text-gray-500"><Info size={12} /> Data System Administration hanya untuk allowlist email tim IT, tidak diatur di sini.</span>
      </div>

      {error && <div className="mx-5 mt-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="sticky left-0 z-10 bg-gray-900 text-left font-medium text-gray-500 px-4 py-2 min-w-[240px]">Data</th>
              {roles.map((r) => (
                <th key={r.role_code} className="px-2 py-2 text-center align-bottom min-w-[92px]">
                  <div className="font-mono text-[11px] text-gray-300">{r.role_code.replace(/^ebs-/, "")}</div>
                  <div className="text-[10px] font-normal text-gray-600">{r.users} user</div>
                  {!r.all_access && r.users === 0 && (
                    <button onClick={() => deleteRole(r.role_code)} title={`Hapus peran ${r.role_code}`}
                      className="mt-1 text-gray-600 hover:text-red-400"><Trash2 size={12} /></button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {byDomain.map(([domain, marts]) => (
              [
                <tr key={`h-${domain}`} className="bg-gray-950/40">
                  <td colSpan={roles.length + 1} className="sticky left-0 px-4 pt-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-gray-500">
                    {DOMAIN_LABEL[domain] || domain}
                  </td>
                </tr>,
                ...marts.map((m) => (
                  <tr key={m.mart} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                    <td className="sticky left-0 z-10 bg-gray-900 px-4 py-1.5">
                      <div className="font-mono text-[11px] text-gray-300">{m.mart}</div>
                      <div className="text-[10px] text-gray-600 line-clamp-1 max-w-[320px]" title={m.description}>{m.description}</div>
                      {m.money_columns.length > 0 && (
                        <div className="text-[10px] text-gray-600 flex items-center gap-1" title={m.money_columns.join(", ")}>
                          <EyeOff size={10} /> disembunyikan saat Qty: {m.money_columns.slice(0, 4).join(", ")}
                          {m.money_columns.length > 4 ? ` +${m.money_columns.length - 4}` : ""}
                        </div>
                      )}
                    </td>
                    {roles.map((r) => {
                      const key = `${r.role_code}|${m.mart}`;
                      if (r.all_access) {
                        return <td key={key} className="px-2 py-1.5 text-center"><span className={`rounded border px-2 py-0.5 ${LEVEL_STYLE.full}`}>Semua</span></td>;
                      }
                      const level = grantOf[key] || "";
                      return (
                        <td key={key} className="px-2 py-1.5 text-center">
                          <select id={`acl-${key}`} aria-label={`${r.role_code} ${m.mart}`} value={level}
                            disabled={saving === key}
                            onChange={(e) => setLevel(r.role_code, m.mart, e.target.value)}
                            className={`rounded border px-1.5 py-0.5 text-[11px] focus:outline-none focus:ring-1 focus:ring-blue-500 ${LEVEL_STYLE[level]}`}>
                            <option value="">—</option>
                            <option value="qty" disabled={m.money_columns.length === 0}>Qty</option>
                            <option value="full">Full</option>
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                )),
              ]
            ))}
          </tbody>
        </table>
      </div>

      <form onSubmit={addRole} className="px-5 py-3 border-t border-gray-800 flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="new-role-code" className="block text-[10px] font-bold uppercase tracking-wider text-gray-600 mb-1">Kode peran baru</label>
          <input id="new-role-code" value={newRole.code} placeholder="ebs-purchasing-stok"
            onChange={(e) => setNewRole((r) => ({ ...r, code: e.target.value }))}
            className="rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 w-48" />
        </div>
        <div className="flex-1 min-w-[180px]">
          <label htmlFor="new-role-label" className="block text-[10px] font-bold uppercase tracking-wider text-gray-600 mb-1">Nama</label>
          <input id="new-role-label" value={newRole.label} placeholder="Purchasing — lihat stok"
            onChange={(e) => setNewRole((r) => ({ ...r, label: e.target.value }))}
            className="rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 w-full" />
        </div>
        <button type="submit" disabled={addingRole || !newRole.code.trim() || !newRole.label.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-white">
          {addingRole ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Tambah peran
        </button>
        <p className="w-full text-[10px] text-gray-600">
          Peran yang dipakai user tidak bisa dihapus. Peran dengan akses "Semua" (manajemen) otomatis mendapat data baru.
        </p>
      </form>
    </div>
  );
}
