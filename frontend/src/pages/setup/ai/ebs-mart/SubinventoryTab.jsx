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
      setRows(await ebsMartApi.subinventories());
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
    <Card title="Subinventory classification (org 121)" icon={Warehouse}
      subtitle={`Decides which stock counts as "usable" (GOOD) versus quarantine/reject in mart.inv_onhand_lot. An automatic guess from the name and Oracle's availability_type applies until the Warehouse/QA sets the official list here. ${official}/${rows?.length || 0} are official. Changes refresh the mart immediately.`}>
      <div className="p-4 space-y-3">
        <ErrorBox>{error}</ErrorBox>
        {rows?.length === 0 && (
          <p className="text-xs text-gray-500">No data yet — run "Pull stock by lot" in the Overview tab.</p>
        )}
        <div className="overflow-auto rounded-lg border border-gray-800">
          <table className="w-full text-[11px]">
            <thead className="bg-gray-800 text-gray-400">
              <tr>{["Subinventory", "Description", "Nettable", "Guess", "Official", "Effective", "Changed"].map((h) => (
                <th key={h} className="px-3 py-1.5 text-left font-semibold">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {(rows || []).map((r) => (
                <tr key={r.subinventory_code}>
                  <td className="px-3 py-1.5 font-mono text-gray-200">{r.subinventory_code}</td>
                  <td className="px-3 py-1.5 text-gray-400">{r.description}</td>
                  <td className="px-3 py-1.5 text-gray-500">{r.availability_type === 1 ? "Yes" : r.availability_type === 2 ? "No" : "—"}</td>
                  <td className="px-3 py-1.5 text-gray-500">{r.guessed_type}</td>
                  <td className="px-3 py-1.5">
                    <select value={r.official_type || ""} disabled={saving === r.subinventory_code}
                      onChange={(e) => set(r.subinventory_code, e.target.value)} className={inputCls}>
                      <option value="">(use the guess)</option>
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
