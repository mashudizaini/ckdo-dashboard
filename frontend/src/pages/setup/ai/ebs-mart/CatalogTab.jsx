import { useEffect, useMemo, useState } from "react";
import { BookText, Pencil, Save, X } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Button, Card, ErrorBox, Spinner, errMsg, inputCls } from "./shared";

export default function CatalogTab() {
  const [rows, setRows] = useState(null);
  const [mart, setMart] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null); // {mart_name, column_name, description_id, synonyms(text)}
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const r = await ebsMartApi.catalog();
      setRows(r.data);
    } catch (e) {
      setError(errMsg(e));
    }
  };
  useEffect(() => { load(); }, []);

  const marts = useMemo(() => [...new Set((rows || []).map((r) => r.mart_name))], [rows]);
  const filtered = (rows || []).filter((r) =>
    (!mart || r.mart_name === mart) &&
    (!q || `${r.column_name} ${r.description_id || ""} ${(r.synonyms || []).join(" ")}`.toLowerCase().includes(q.toLowerCase())));
  const missingSyn = (rows || []).filter((r) => !r.synonyms?.length).length;

  const save = async () => {
    setSaving(true);
    try {
      await ebsMartApi.updateCatalog(editing.mart_name, editing.column_name, {
        description_id: editing.description_id,
        synonyms: editing.synonyms.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setEditing(null);
      await load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  if (!rows && !error) return <Spinner />;

  return (
    <Card title="Katalog kolom (meta.column_catalog)" icon={BookText}
      subtitle={`Deskripsi Bahasa Indonesia dan sinonim dibaca find_marts untuk memetakan bahasa user ke kolom. ${missingSyn} kolom belum punya sinonim — kriteria selesai blueprint: setiap kolom punya deskripsi dan minimal 1 sinonim.`}>
      <div className="p-4 space-y-3">
        <ErrorBox>{error}</ErrorBox>
        <div className="flex flex-wrap gap-2">
          <select value={mart} onChange={(e) => setMart(e.target.value)} className={inputCls}>
            <option value="">Semua mart</option>
            {marts.map((m) => <option key={m} value={m}>mart.{m}</option>)}
          </select>
          <input placeholder="Cari kolom / deskripsi / sinonim" value={q} onChange={(e) => setQ(e.target.value)} className={`${inputCls} w-72`} />
        </div>
        <div className="overflow-auto max-h-[560px] rounded-lg border border-gray-800">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-gray-800 text-gray-400">
              <tr>
                {["Mart", "Kolom", "Tipe", "Deskripsi", "Sinonim", "Nilai contoh", ""].map((h) => (
                  <th key={h} className="px-3 py-1.5 text-left font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {filtered.map((r) => {
                const isEdit = editing && editing.mart_name === r.mart_name && editing.column_name === r.column_name;
                return (
                  <tr key={r.mart_name + r.column_name} className="align-top">
                    <td className="px-3 py-1.5 font-mono text-gray-500 whitespace-nowrap">{r.mart_name}</td>
                    <td className="px-3 py-1.5 font-mono text-gray-200 whitespace-nowrap">{r.column_name}</td>
                    <td className="px-3 py-1.5 text-gray-500 whitespace-nowrap">{r.data_type}</td>
                    <td className="px-3 py-1.5 text-gray-300 min-w-[240px]">
                      {isEdit ? (
                        <textarea rows={2} value={editing.description_id || ""} className={`${inputCls} w-full`}
                          onChange={(e) => setEditing({ ...editing, description_id: e.target.value })} />
                      ) : r.description_id || <span className="text-amber-400">— belum ada —</span>}
                    </td>
                    <td className="px-3 py-1.5 min-w-[200px]">
                      {isEdit ? (
                        <input value={editing.synonyms} className={`${inputCls} w-full`} placeholder="pisahkan dengan koma"
                          onChange={(e) => setEditing({ ...editing, synonyms: e.target.value })} />
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {(r.synonyms || []).map((s) => (
                            <span key={s} className="rounded bg-blue-500/10 border border-blue-500/30 px-1.5 text-blue-300">{s}</span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-gray-500 max-w-[200px]">{(r.sample_values || []).join(", ")}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      {isEdit ? (
                        <div className="flex gap-1">
                          <Button icon={Save} loading={saving} onClick={save}>Simpan</Button>
                          <Button variant="ghost" icon={X} onClick={() => setEditing(null)} />
                        </div>
                      ) : (
                        <button onClick={() => setEditing({ ...r, synonyms: (r.synonyms || []).join(", ") })}
                          className="text-gray-500 hover:text-blue-300"><Pencil size={13} /></button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}
