import { useEffect, useState } from "react";
import { Database, Play, RefreshCw, Workflow, Users, ShieldCheck } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Button, Card, ErrorBox, Spinner, errMsg, fmtDate, fmtNum } from "./shared";

const DOMAIN_TONE = {
  AP: "text-sky-300", AR: "text-teal-300", INV: "text-emerald-300", PO: "text-violet-300",
  OM: "text-pink-300", OPM: "text-amber-300", GL: "text-orange-300",
};

export default function OverviewTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = async () => {
    try {
      const r = await ebsMartApi.overview();
      setData(r.data);
      setError(null);
    } catch (e) {
      setError(errMsg(e));
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const trigger = async (job, fullRefresh = false) => {
    setBusy(job + (fullRefresh ? "-full" : ""));
    setNotice(null);
    try {
      const r = await ebsMartApi.trigger(job, { full_refresh: fullRefresh });
      setNotice(r.data.message + " — status muncul di riwayat di bawah.");
      setTimeout(load, 1500);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  };

  if (!data && !error) return <Spinner />;

  const phases = [1, 2, 3, 4, 5];
  return (
    <div className="space-y-4">
      <ErrorBox>{error}</ErrorBox>
      {notice && <div className="rounded-md bg-blue-500/10 border border-blue-500/30 px-3 py-2 text-xs text-blue-300">{notice}</div>}

      {data && (
        <>
          <Card title="Katalog mart" icon={Database}
            subtitle="Satu sumber kebenaran untuk chat dan dashboard. LLM hanya melihat mart.* — tidak pernah Oracle, core.*, atau eis.*.">
            <div className="p-4 space-y-4">
              {phases.map((ph) => {
                const marts = data.marts.filter((m) => m.phase === ph);
                return (
                  <div key={ph}>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-gray-600 mb-2">
                      Fase {ph} {ph === 1 ? "· aktif" : "· direncanakan"}
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
                      {marts.map((m) => (
                        <div key={m.mart}
                          className={`rounded-lg border px-3 py-2.5 ${m.built ? "border-gray-700 bg-gray-800/60" : "border-dashed border-gray-800 opacity-60"}`}>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-mono text-gray-200 truncate">mart.{m.mart}</p>
                            <span className={`text-[10px] font-bold ${DOMAIN_TONE[m.domain] || "text-gray-400"}`}>{m.domain}</span>
                          </div>
                          <p className="text-[11px] text-gray-500 mt-0.5 line-clamp-2">{m.grain}</p>
                          {m.built ? (
                            <div className="flex items-center justify-between mt-2 text-[11px]">
                              <span className="text-gray-300 tabular-nums">{fmtNum(m.row_count)} baris</span>
                              <span className={m.as_of ? "text-gray-400" : "text-amber-400"}>{m.as_of || "belum di-load"}</span>
                            </div>
                          ) : (
                            <p className="text-[11px] text-gray-600 mt-2">Sumber: {m.sources}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card title="ETL & refresh" icon={Workflow}
            subtitle="Tombol manual memakai advisory lock — kalau job yang sama sedang jalan (jadwal), tarikan manual tercatat 'skipped', bukan dobel."
            actions={<Button variant="ghost" icon={RefreshCw} onClick={load}>Muat ulang</Button>}>
            <div className="p-4 flex flex-wrap gap-2 border-b border-gray-800">
              <Button icon={Play} loading={busy === "etl_mart_ap"} onClick={() => trigger("etl_mart_ap")}>Tarik AP (incremental)</Button>
              <Button variant="ghost" icon={Play} loading={busy === "etl_mart_ap-full"} onClick={() => trigger("etl_mart_ap", true)}
                title="Reload penuh + rekonsiliasi delete (otomatis tiap Minggu 01:00)">AP full reload</Button>
              <Button icon={Play} loading={busy === "etl_mart_inventory"} onClick={() => trigger("etl_mart_inventory")}>Tarik stok per lot</Button>
              <Button variant="ghost" icon={Play} loading={busy === "etl_inventory_txn"} onClick={() => trigger("etl_inventory_txn")}>Tarik mutasi inventory</Button>
              <Button variant="ghost" icon={RefreshCw} loading={busy === "refresh_ebs_marts"} onClick={() => trigger("refresh_ebs_marts")}>Refresh semua mart</Button>
            </div>
            {data.watermarks.length > 0 && (
              <div className="px-4 py-2 border-b border-gray-800 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-gray-500">
                {data.watermarks.map((w) => (
                  <span key={w.job_name + w.stream}>
                    Watermark <b className="text-gray-400">{w.job_name}/{w.stream}</b>: {fmtDate(w.watermark)}
                  </span>
                ))}
              </div>
            )}
            <div className="overflow-auto max-h-80">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-gray-800 text-gray-400">
                  <tr>
                    {["Job", "Pemicu", "Status", "Dibaca", "Upsert", "Watermark", "Mulai", "Durasi", "Catatan"].map((h) => (
                      <th key={h} className="px-3 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {data.runs.map((r) => (
                    <tr key={r.run_id}>
                      <td className="px-3 py-1.5 font-mono text-gray-300">{r.job_name}</td>
                      <td className="px-3 py-1.5 text-gray-400">{r.trigger_type}{r.triggered_by ? ` · ${r.triggered_by}` : ""}</td>
                      <td className="px-3 py-1.5"><Badge>{r.status}</Badge></td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-gray-300">{fmtNum(r.rows_read)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-gray-300">{fmtNum(r.rows_upserted)}</td>
                      <td className="px-3 py-1.5 text-gray-500 whitespace-nowrap">{r.watermark_from ? `${fmtDate(r.watermark_from)} →` : "full"} {r.watermark_to ? fmtDate(r.watermark_to) : ""}</td>
                      <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap">{fmtDate(r.started_at)}</td>
                      <td className="px-3 py-1.5 text-gray-400 tabular-nums">{r.duration_secs != null ? `${r.duration_secs} dtk` : "—"}</td>
                      <td className="px-3 py-1.5 text-red-300 max-w-xs truncate" title={r.error_msg || ""}>{r.error_msg || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.runs.length === 0 && <p className="px-3 py-6 text-center text-xs text-gray-500">Belum ada run.</p>}
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Grup → domain mart" icon={Users}
              subtitle="Diberikan per email di tab EBS Chat Access, atau lewat claim groups token Keycloak.">
              <div className="divide-y divide-gray-800">
                {data.groups.map((g) => (
                  <div key={g.group} className="px-4 py-2 text-xs">
                    <p className="font-mono text-gray-200">{g.group}</p>
                    <p className="text-gray-500">{g.label}</p>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Guardrail aktif" icon={ShieldCheck}>
              <ul className="p-4 space-y-1.5 text-xs text-gray-400 list-disc list-inside">
                <li>run_sql: satu SELECT, semua tabel harus mart.* (diperiksa dengan sqlglot; SQL hasil parse yang dieksekusi)</li>
                <li>Koneksi read-only, statement_timeout <b className="text-gray-200">{data.guardrails.statement_timeout}</b>, maksimal <b className="text-gray-200">{data.guardrails.max_rows}</b> baris (flag truncated)</li>
                <li>Akses per grup ebs-* dicek sebelum query — 403 tidak bergantung pada kepatuhan model</li>
                <li>Setiap panggilan (termasuk yang ditolak) dicatat di meta.chat_query_log</li>
                <li>Setiap hasil membawa as_of, sql_used, row_count</li>
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
