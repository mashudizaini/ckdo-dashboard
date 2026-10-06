import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Level, Note, Panel, Spinner, Table, fmtDate, fmtTime, errText, inputStyle, probeLevel, SERIES } from "./ui";

const SEG_LABEL = {
  ho_lan: "LAN HO", wan: "Jalur HO ↔ Plant", plant_lan: "LAN Plant",
  ebs_web: "EBS Web / App", ebs_db: "EBS Database", internet: "Internet / ISP",
};

const axis = { fontSize: 10.5, fill: "#64748b" };
const tooltipStyle = { fontSize: 11.5, borderRadius: 8, border: "1px solid #e2e8f0" };

export default function PathTab({ thresholds }) {
  const [targets, setTargets] = useState(null);
  const [sel, setSel] = useState(null);
  const [hours, setHours] = useState(24);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await ebsNetApi.listTargets();
      setTargets(rows);
      setSel((cur) => cur && rows.some((r) => r.id === cur) ? cur : rows.find((r) => r.enabled)?.id ?? null);
    } catch (e) { setTargets([]); alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!sel) return;
    ebsNetApi.targetHistory(sel, hours).then((rows) => setHist(rows.map((r) => ({ ...r, t: fmtTime(r.checked_at), at: fmtDate(r.checked_at) })))).catch(() => setHist([]));
  }, [sel, hours]);

  const runAll = async () => {
    setBusy(true);
    try { await ebsNetApi.runProbes(); await load(); if (sel) setHist((await ebsNetApi.targetHistory(sel, hours)).map((r) => ({ ...r, t: fmtTime(r.checked_at), at: fmtDate(r.checked_at) }))); }
    catch (e) { alert(errText(e)); } finally { setBusy(false); }
  };

  if (!targets) return <Spinner />;
  const target = targets.find((t) => t.id === sel);

  return (
    <>
      <Note>
        Probe berjalan dari <b>server dashboard (LAN Plant, satu subnet dengan EBS)</b>. Target di segmen <i>Jalur HO ↔ Plant</i> (mis. IP LAN FortiGate HO)
        diukur melewati tunnel, jadi angkanya mewakili kesehatan WAN/VPN. Kondisi LAN HO sendiri hanya terlihat dari laptop di HO — lihat tab Client Test.
      </Note>
      <div className="h-4" />
      <Panel title="Target probe" subtitle="Klik baris untuk melihat riwayat · tambah/ubah target di Setup"
        action={<Btn size="sm" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy} onClick={runAll}>Probe semua sekarang</Btn>}>
        <Table rows={targets} onRowClick={(r) => setSel(r.id)} empty="Belum ada target."
          columns={[
            { key: "name", label: "Target", render: (r) => <span style={{ fontWeight: r.id === sel ? 800 : 500 }}>{r.name}</span> },
            { key: "segment", label: "Segmen", render: (r) => SEG_LABEL[r.segment] || r.segment },
            { key: "addr", label: "Alamat", render: (r) => r.check_type === "http" ? (r.url || "—") : `${r.host || "?"}:${r.port || "?"}` },
            { key: "status", label: "Status", render: (r) => r.enabled ? <Level size="sm" level={probeLevel(r.last, thresholds)} /> : <span style={{ color: "#94a3b8" }}>nonaktif</span> },
            { key: "avg", label: "Avg", align: "right", render: (r) => r.last?.rtt_avg != null ? `${r.last.rtt_avg} ms` : "—" },
            { key: "jit", label: "Jitter", align: "right", render: (r) => r.last?.jitter_ms != null ? `${r.last.jitter_ms} ms` : "—" },
            { key: "loss", label: "Loss", align: "right", render: (r) => r.last?.loss_pct != null ? `${r.last.loss_pct}%` : "—" },
            { key: "d", label: "24 jam: avg / max / loss", align: "right", render: (r) => r.day?.runs ? `${r.day.rtt_avg ?? "—"} / ${r.day.rtt_max ?? "—"} ms / ${r.day.loss_avg ?? 0}%` : "—" },
            { key: "err", label: "Error terakhir", wrap: true, render: (r) => <span style={{ color: "#dc2626" }}>{r.last?.error || ""}</span> },
          ]} />
      </Panel>

      {target && (
        <Panel title={`Riwayat — ${target.name}`} subtitle={target.notes || undefined}
          action={<select style={{ ...inputStyle, width: "auto" }} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={6}>6 jam</option><option value={24}>24 jam</option><option value={72}>3 hari</option><option value={168}>7 hari</option>
          </select>}>
          {!hist.length ? <Empty>Belum ada data untuk rentang ini.</Empty> : (
            <>
              <p style={{ fontSize: 11.5, fontWeight: 700, color: "#334155", marginBottom: 4 }}>Latency (ms)</p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={hist} margin={{ top: 6, right: 12, left: -10, bottom: 0 }}>
                  <CartesianGrid stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="t" tick={axis} minTickGap={40} />
                  <YAxis tick={axis} width={44} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(_, p) => p?.[0]?.payload?.at || ""} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="rtt_avg" name="Rata-rata" stroke={SERIES[0]} strokeWidth={2} dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="rtt_max" name="Maksimum" stroke={SERIES[1]} strokeWidth={2} dot={false} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
              <p style={{ fontSize: 11.5, fontWeight: 700, color: "#334155", margin: "12px 0 4px" }}>Packet / connect loss (%)</p>
              <ResponsiveContainer width="100%" height={110}>
                <BarChart data={hist} margin={{ top: 4, right: 12, left: -10, bottom: 0 }}>
                  <XAxis dataKey="t" tick={axis} minTickGap={40} />
                  <YAxis tick={axis} width={44} domain={[0, 100]} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(_, p) => p?.[0]?.payload?.at || ""} formatter={(v) => [`${v}%`, "Loss"]} />
                  <Bar dataKey="loss_pct" fill={SERIES[0]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
        </Panel>
      )}
    </>
  );
}
