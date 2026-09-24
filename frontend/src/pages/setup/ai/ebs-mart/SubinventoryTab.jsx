import { useEffect, useState } from "react";
import { Warehouse } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Card, ErrorBox, Spinner, errMsg, fmtDate, inputCls } from "./shared";

const TYPE_TONE = { GOOD: "OK", QUARANTINE: "TIMEOUT", REJECT: "FAILED" };

export default function SubinventoryTab() {
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setRows((await ebsMartApi.subinventories()).data);
    } catch (e) {
      setError(errMsg(e));
    }
  };
  useEffect(() => { load(); }, []);

  const set = async (code, type) => {
    setSaving(code);
    setError(null);
    try {
      await ebsMartApi.setSubinventory(code, { subinventory_type: type || null });
      await load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSaving(null);
    }
  };

  if (!rows && !error) return <Spinner />;
  const official = (rows || []).filter((r) => r.official_type).length;

  return (
    <Card title="Klasifikasi subinventory (org 121)" icon={Warehouse}
      subtitle={`Menentukan stok mana yang dihitung "bisa dipakai" (GOOD) versus karantina/reject di mart.inv_onhand_lot. Tebakan otomatis dari nama dan availability_type Oracle berlaku sampai Gudang/QA menetapkan daftar resmi di sini. ${official}/${rows?.length || 0} sudah resmi. Perubahan langsung me-refresh mart.`}>
      <div className="p-4 space-y-3">
        <ErrorBox>{error}</ErrorBox>
        {rows?.length === 0 && (
          <p className="text-xs text-gray-500">Belum ada data — jalankan "Tarik stok per lot" di tab Ringkasan.</p>
        )}
        <div className="overflow-auto rounded-lg border border-gray-800">
          <table className="w-full text-[11px]">
            <thead className="bg-gray-800 text-gray-400">
              <tr>{["Subinventory", "Deskripsi", "Nettable", "Tebakan", "Resmi", "Berlaku", "Diubah"].map((h) => (
                <th key={h} className="px-3 py-1.5 text-left font-semibold">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {(rows || []).map((r) => (
                <tr key={r.subinventory_code}>
                  <td className="px-3 py-1.5 font-mono text-gray-200">{r.subinventory_code}</td>
                  <td className="px-3 py-1.5 text-gray-400">{r.description}</td>
                  <td className="px-3 py-1.5 text-gray-500">{r.availability_type === 1 ? "Ya" : r.availability_type === 2 ? "Tidak" : "—"}</td>
                  <td className="px-3 py-1.5 text-gray-500">{r.guessed_type}</td>
                  <td className="px-3 py-1.5">
                    <select value={r.official_type || ""} disabled={saving === r.subinventory_code}
                      onChange={(e) => set(r.subinventory_code, e.target.value)} className={inputCls}>
                      <option value="">(pakai tebakan)</option>
                      <option>GOOD</option>
                      <option>QUARANTINE</option>
                      <option>REJECT</option>
                    </select>
                  </td>
                  <td className="px-3 py-1.5"><Badge tone={TYPE_TONE[r.effective_type]}>{r.effective_type}</Badge></td>
                  <td className="px-3 py-1.5 text-gray-500">{r.updated_by ? `${r.updated_by} · ${fmtDate(r.updated_at)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}
