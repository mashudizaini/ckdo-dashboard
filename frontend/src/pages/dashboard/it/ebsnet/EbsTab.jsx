import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Level, Note, Panel, Spinner, Stat, Table, fmtDate, fmtTime, errText, SERIES } from "./ui";

const axis = { fontSize: 10.5, fill: "#64748b" };

function MiniChart({ title, data, keys }) {
  return (
    <div className="flex-1" style={{ minWidth: 280 }}>
      <p style={{ fontSize: 11.5, fontWeight: 700, color: "#334155", marginBottom: 4 }}>{title}</p>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={data} margin={{ top: 6, right: 10, left: -14, bottom: 0 }}>
          <CartesianGrid stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="t" tick={axis} minTickGap={40} />
          <YAxis tick={axis} width={42} />
          <Tooltip contentStyle={{ fontSize: 11.5, borderRadius: 8 }} labelFormatter={(_, p) => p?.[0]?.payload?.at || ""} />
          {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {keys.map(([k, label], i) => <Line key={k} type="monotone" dataKey={k} name={label} stroke={SERIES[i]} strokeWidth={2} dot={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function EbsTab() {
  const [snap, setSnap] = useState(undefined);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([ebsNetApi.getEbs(), ebsNetApi.ebsHistory(24)]);
      setSnap(s); setHist(h.map((r) => ({ ...r, t: fmtTime(r.checked_at), at: fmtDate(r.checked_at) })));
    } catch (e) { setSnap(null); alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const capture = async () => {
    setBusy(true);
    try { await ebsNetApi.captureEbs(); await load(); } catch (e) { alert(errText(e)); } finally { setBusy(false); }
  };

  if (snap === undefined) return <Spinner />;
  const s = snap?.summary || {};

  return (
    <>
      <Panel title="Kesehatan Oracle EBS (application & database tier)"
        subtitle={snap ? `Lingkungan: ${s.environment || "?"} · ${fmtDate(snap.checked_at)} · otomatis tiap 5 menit (app tier tiap 15 menit)` : "Belum ada snapshot"}
        action={<Btn size="sm" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy} onClick={capture}>Snapshot sekarang</Btn>}>
        {!snap ? <Empty>Belum ada snapshot. Klik "Snapshot sekarang".</Empty> : !snap.ok ? (
          <p style={{ color: "#dc2626", fontSize: 12 }}>{snap.error}</p>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-2.5 flex-wrap">
              <Stat label="Koneksi DB" value={s.db_connect_ms} unit="ms" hint="dari server dashboard" />
              <Stat label="Sesi aktif / total" value={s.sessions_total != null ? `${s.sessions_active} / ${s.sessions_total}` : null} />
              <Stat label="Sesi Forms" value={s.forms_sessions} />
              <Stat label="User web 15 mnt" value={s.web_users_15m} />
              <Stat label="Sesi terblokir" value={s.sessions_blocked} level={s.sessions_blocked ? (s.sessions_blocked >= 5 ? "crit" : "warn") : "ok"} />
              <Stat label="CPU host DB" value={s.host_cpu_pct} unit="%" level={s.host_cpu_pct >= 85 ? "warn" : s.host_cpu_pct != null ? "ok" : undefined} />
              <Stat label="Avg active sessions" value={s.avg_active_sessions} />
              <Stat label="DB wait ratio" value={s.db_wait_ratio} unit="%" />
              <Stat label="Single-block read" value={s.single_block_read_ms} unit="ms" level={s.single_block_read_ms >= 20 ? "warn" : s.single_block_read_ms != null ? "ok" : undefined} />
            </div>
            <div className="flex gap-2.5 flex-wrap">
              <Stat label="Internal Manager" value={s.icm_up == null ? null : s.icm_up ? "UP" : "DOWN"} level={s.icm_up == null ? undefined : s.icm_up ? "ok" : "crit"} />
              <Stat label="Request pending" value={s.requests_pending} level={s.requests_pending > 50 ? "warn" : "ok"} />
              <Stat label="Request running" value={s.requests_running} />
              <Stat label="Running > 1 jam" value={s.requests_long_running} level={s.requests_long_running ? "warn" : "ok"} />
              <Stat label="Error 1 jam" value={s.requests_errors_1h} />
            </div>
            {Object.keys(s.query_errors || {}).length > 0 && (
              <Note tone="warn">Sebagian query gagal (biasanya grant v$ view untuk user APPS): {Object.entries(s.query_errors).map(([k, v]) => `${k}: ${v}`).join(" · ")}</Note>
            )}
          </div>
        )}
      </Panel>

      {hist.length > 1 && (
        <Panel title="Tren 24 jam">
          <div className="flex gap-4 flex-wrap">
            <MiniChart title="Sesi aktif & Forms" data={hist} keys={[["sessions_active", "Sesi aktif"], ["forms_sessions", "Sesi Forms"]]} />
            <MiniChart title="CPU host DB (%)" data={hist} keys={[["host_cpu_pct", "CPU"]]} />
            <MiniChart title="Waktu koneksi DB dari server (ms)" data={hist} keys={[["db_connect_ms", "Connect"]]} />
          </div>
        </Panel>
      )}

      {snap?.ok && (
        <>
          <Panel title="Wait event aktif saat ini" subtitle="Sesi user ACTIVE, non-Idle — apa yang sedang ditunggu database">
            <Table rows={s.waits} empty="Tidak ada sesi aktif yang menunggu (bagus)."
              columns={[{ key: "event", label: "Event" }, { key: "wait_class", label: "Class" },
                { key: "sessions", label: "Sesi", align: "right" }, { key: "max_wait_s", label: "Max tunggu (s)", align: "right" }]} />
          </Panel>
          <Panel title="Sesi terblokir (lock)">
            <Table rows={s.blocking} empty="Tidak ada blocking."
              columns={[{ key: "sid", label: "SID" }, { key: "username", label: "User DB" }, { key: "module", label: "Module" },
                { key: "blocking_session", label: "Diblokir oleh SID" }, { key: "seconds_in_wait", label: "Tunggu (s)", align: "right" }, { key: "event", label: "Event" }]} />
          </Panel>
          <Panel title="SQL aktif > 5 menit">
            <Table rows={s.long_sql} empty="Tidak ada."
              columns={[{ key: "sid", label: "SID" }, { key: "username", label: "User" }, { key: "module", label: "Module" },
                { key: "sql_id", label: "SQL ID" }, { key: "seconds_active", label: "Aktif (s)", align: "right" }, { key: "event", label: "Event" }]} />
          </Panel>
          <Panel title="Concurrent Managers" subtitle="Target vs actual process">
            <Table rows={s.managers} empty="Tidak terbaca."
              columns={[{ key: "name", label: "Manager" }, { key: "short_name", label: "Kode" },
                { key: "target", label: "Target", align: "right" }, { key: "actual", label: "Actual", align: "right" },
                { key: "st", label: "Status", render: (r) => <Level size="sm" level={(r.actual || 0) >= (r.target || 0) ? "ok" : (r.actual || 0) === 0 ? "crit" : "warn"} label={(r.actual || 0) >= (r.target || 0) ? "OK" : "Kurang"} /> }]} />
          </Panel>
          <Panel title="Server EBS (OS)" subtitle="Server bertanda 'monitor' di Server Control — sama dengan Server Process Monitoring">
            <Table rows={s.app_tier} empty="Belum ada data app tier di snapshot ini (diambil tiap 15 menit)."
              columns={[{ key: "server_label", label: "Server" }, { key: "server_ip", label: "IP" },
                { key: "status", label: "Status", render: (r) => <Level size="sm" level={r.status === "online" ? "ok" : "crit"} label={r.status} /> },
                { key: "cpu", label: "CPU %", align: "right" }, { key: "memory_percent", label: "Mem %", align: "right" },
                { key: "swap_percent", label: "Swap %", align: "right" }, { key: "load", label: "Load", align: "right" },
                { key: "cpu_count", label: "vCPU", align: "right" }, { key: "uptime", label: "Uptime" }]} />
          </Panel>
        </>
      )}
    </>
  );
}
