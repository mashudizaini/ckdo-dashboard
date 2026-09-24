import { useEffect, useState } from "react";
import { Activity, RefreshCw, ScrollText } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Button, Card, ErrorBox, Spinner, errMsg, fmtDate, fmtNum, inputCls } from "./shared";

const STATUSES = ["", "OK", "DENIED", "REJECTED", "ERROR", "TIMEOUT"];

export default function AuditTab() {
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState(null);
  const [filters, setFilters] = useState({ user_email: "", status: "", tool: "" });
  const [open, setOpen] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
      const [s, l] = await Promise.all([ebsMartApi.queryStats(30), ebsMartApi.queryLog({ ...params, limit: 200 })]);
      setStats(s.data);
      setRows(l.data);
      setError(null);
    } catch (e) {
      setError(errMsg(e));
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line

  if (!rows && !error) return <Spinner />;

  const totals = (stats?.per_tool || []).reduce(
    (a, t) => ({ calls: a.calls + t.calls, ok: a.ok + t.ok, errors: a.errors + t.errors, denied: a.denied + t.denied }),
    { calls: 0, ok: 0, errors: 0, denied: 0 });

  return (
    <div className="space-y-4">
      <ErrorBox>{error}</ErrorBox>
      {stats && (
        <Card title="Pemakaian 30 hari" icon={Activity}
          subtitle="Siklus perbaikan mingguan (blueprint §11): tinjau query gagal dan DENIED di sini → tambah sinonim → golden query → perjelas skill → jadikan intent tool.">
          <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ["Panggilan tool", totals.calls],
              ["Berhasil", totals.calls ? `${Math.round((totals.ok / totals.calls) * 100)}%` : "—"],
              ["Error / timeout", totals.errors],
              ["Ditolak akses", totals.denied],
            ].map(([label, v]) => (
              <div key={label} className="rounded-lg border border-gray-800 bg-gray-800/40 px-3 py-2">
                <p className="text-[10px] uppercase tracking-wider text-gray-500">{label}</p>
                <p className="text-lg font-semibold text-gray-100 tabular-nums">{fmtNum(v)}</p>
              </div>
            ))}
          </div>
          {stats.per_day.length > 0 && (
            <div className="px-4 pb-2 h-40">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.per_day} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} tickFormatter={(d) => String(d).slice(5)} />
                  <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }} />
                  <Bar dataKey="calls" name="Panggilan" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="not_ok" name="Tidak OK" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="bg-gray-800 text-gray-400">
                <tr>{["Tool", "Panggilan", "OK", "Error", "Ditolak guardrail", "Ditolak akses", "Median (ms)", "User"].map((h) => (
                  <th key={h} className="px-3 py-1.5 text-left font-semibold">{h}</th>))}</tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {stats.per_tool.map((t) => (
                  <tr key={t.tool_name}>
                    <td className="px-3 py-1.5 font-mono text-gray-200">{t.tool_name}</td>
                    {[t.calls, t.ok, t.errors, t.rejected, t.denied, Math.round(t.median_ms || 0), t.users].map((v, i) => (
                      <td key={i} className="px-3 py-1.5 tabular-nums text-gray-300">{fmtNum(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="Audit log (meta.chat_query_log)" icon={ScrollText}
        subtitle="Setiap panggilan tool — siapa, pertanyaan, SQL, jumlah baris, durasi, status."
        actions={<Button variant="ghost" icon={RefreshCw} onClick={load}>Muat ulang</Button>}>
        <div className="p-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            <input placeholder="Email user" value={filters.user_email} className={inputCls}
              onChange={(e) => setFilters({ ...filters, user_email: e.target.value })} />
            <input placeholder="Nama tool" value={filters.tool} className={inputCls}
              onChange={(e) => setFilters({ ...filters, tool: e.target.value })} />
            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className={inputCls}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || "Semua status"}</option>)}
            </select>
            <Button onClick={load}>Terapkan</Button>
          </div>
          <div className="rounded-lg border border-gray-800 divide-y divide-gray-800 max-h-[560px] overflow-auto">
            {(rows || []).map((r) => (
              <div key={r.id} className="px-3 py-2 text-[11px]">
                <button className="w-full text-left flex flex-wrap items-center gap-x-3 gap-y-1" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <span className="text-gray-500 w-36 shrink-0">{fmtDate(r.created_at)}</span>
                  <Badge>{r.status}</Badge>
                  <span className="font-mono text-gray-200">{r.tool_name}</span>
                  <span className="text-gray-400">{r.user_email || "—"}</span>
                  <span className="text-gray-600">{r.source}</span>
                  <span className="text-gray-500 tabular-nums">{r.row_count ?? "—"} baris · {r.duration_ms ?? "—"} ms{r.truncated ? " · dipotong" : ""}</span>
                  {r.question && <span className="text-gray-400 truncate max-w-md">“{r.question}”</span>}
                </button>
                {open === r.id && (
                  <div className="mt-2 space-y-1.5">
                    {r.error_msg && <p className="text-red-300">{r.error_msg}</p>}
                    <p className="text-gray-500">Grup: {(r.groups || []).join(", ") || "—"} · Mart: {(r.marts || []).join(", ") || "—"} · chat_id: {r.chat_id || "—"}</p>
                    {r.tool_args && Object.keys(r.tool_args).length > 0 && (
                      <pre className="bg-gray-950 rounded p-2 text-gray-400 whitespace-pre-wrap">{JSON.stringify(r.tool_args, null, 2)}</pre>
                    )}
                    {r.sql_text && <pre className="bg-gray-950 rounded p-2 text-gray-300 whitespace-pre-wrap">{r.sql_text}</pre>}
                  </div>
                )}
              </div>
            ))}
            {rows?.length === 0 && <p className="px-3 py-6 text-center text-xs text-gray-500">Belum ada panggilan.</p>}
          </div>
        </div>
      </Card>
    </div>
  );
}
