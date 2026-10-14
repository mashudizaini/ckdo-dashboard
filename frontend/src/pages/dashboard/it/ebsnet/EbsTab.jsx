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
      <Panel title="Oracle EBS health (application & database tier)"
        subtitle={snap ? `Environment: ${s.environment || "?"} · ${fmtDate(snap.checked_at)} · automatic every 5 minutes (app tier every 15 minutes)` : "No snapshot yet"}
        action={<Btn size="sm" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy} onClick={capture}>Snapshot now</Btn>}>
        {!snap ? <Empty>No snapshot yet. Click "Snapshot now".</Empty> : !snap.ok ? (
          <p style={{ color: "#dc2626", fontSize: 12 }}>{snap.error}</p>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-2.5 flex-wrap">
              <Stat label="DB connect" value={s.db_connect_ms} unit="ms" hint="from the dashboard server" />
              <Stat label="Active / total sessions" value={s.sessions_total != null ? `${s.sessions_active} / ${s.sessions_total}` : null} />
              <Stat label="Forms sessions" value={s.forms_sessions} />
              <Stat label="User web 15 mnt" value={s.web_users_15m} />
              <Stat label="Blocked sessions" value={s.sessions_blocked} level={s.sessions_blocked ? (s.sessions_blocked >= 5 ? "crit" : "warn") : "ok"} />
              <Stat label="CPU host DB" value={s.host_cpu_pct} unit="%" level={s.host_cpu_pct >= 85 ? "warn" : s.host_cpu_pct != null ? "ok" : undefined} />
              <Stat label="Avg active sessions" value={s.avg_active_sessions} />
              <Stat label="DB wait ratio" value={s.db_wait_ratio} unit="%" />
              <Stat label="Single-block read" value={s.single_block_read_ms} unit="ms" level={s.single_block_read_ms >= 20 ? "warn" : s.single_block_read_ms != null ? "ok" : undefined} />
            </div>
            <div className="flex gap-2.5 flex-wrap">
              <Stat label="Internal Manager" value={s.icm_up == null ? null : s.icm_up ? "UP" : "DOWN"} level={s.icm_up == null ? undefined : s.icm_up ? "ok" : "crit"} />
              <Stat label="Request pending" value={s.requests_pending} level={s.requests_pending > 50 ? "warn" : "ok"} />
              <Stat label="Request running" value={s.requests_running} />
              <Stat label="Running > 1 hour" value={s.requests_long_running} level={s.requests_long_running ? "warn" : "ok"} />
              <Stat label="Errors, 1 hour" value={s.requests_errors_1h} />
            </div>
            {Object.keys(s.query_errors || {}).length > 0 && (
              <Note tone="warn">Some queries failed (usually the v$ view grants for the APPS user): {Object.entries(s.query_errors).map(([k, v]) => `${k}: ${v}`).join(" · ")}</Note>
            )}
          </div>
        )}
      </Panel>

      {hist.length > 1 && (
        <Panel title="24-hour trend">
          <div className="flex gap-4 flex-wrap">
            <MiniChart title="Active & Forms sessions" data={hist} keys={[["sessions_active", "Active sessions"], ["forms_sessions", "Forms sessions"]]} />
            <MiniChart title="CPU host DB (%)" data={hist} keys={[["host_cpu_pct", "CPU"]]} />
            <MiniChart title="DB connect time from the server (ms)" data={hist} keys={[["db_connect_ms", "Connect"]]} />
          </div>
        </Panel>
      )}

      {snap?.ok && (
        <>
          <Panel title="Current wait events" subtitle="ACTIVE, non-Idle user sessions — what the database is waiting on">
            <Table rows={s.waits} empty="No active sessions waiting (good)."
              columns={[{ key: "event", label: "Event" }, { key: "wait_class", label: "Class" },
                { key: "sessions", label: "Sessions", align: "right" }, { key: "max_wait_s", label: "Max wait (s)", align: "right" }]} />
          </Panel>
          <Panel title="Blocked sessions (locks)">
            <Table rows={s.blocking} empty="No blocking."
              columns={[{ key: "sid", label: "SID" }, { key: "username", label: "User DB" }, { key: "module", label: "Module" },
                { key: "blocking_session", label: "Blocked by SID" }, { key: "seconds_in_wait", label: "Wait (s)", align: "right" }, { key: "event", label: "Event" }]} />
          </Panel>
          <Panel title="SQL active > 5 minutes">
            <Table rows={s.long_sql} empty="None."
              columns={[{ key: "sid", label: "SID" }, { key: "username", label: "User" }, { key: "module", label: "Module" },
                { key: "sql_id", label: "SQL ID" }, { key: "seconds_active", label: "Active (s)", align: "right" }, { key: "event", label: "Event" }]} />
          </Panel>
          <Panel title="Concurrent Managers" subtitle="Target vs actual process">
            <Table rows={s.managers} empty="Could not be read."
              columns={[{ key: "name", label: "Manager" }, { key: "short_name", label: "Code" },
                { key: "target", label: "Target", align: "right" }, { key: "actual", label: "Actual", align: "right" },
                { key: "st", label: "Status", render: (r) => <Level size="sm" level={(r.actual || 0) >= (r.target || 0) ? "ok" : (r.actual || 0) === 0 ? "crit" : "warn"} label={(r.actual || 0) >= (r.target || 0) ? "OK" : "Short"} /> }]} />
          </Panel>
          <Panel title="EBS servers (OS)" subtitle="Servers marked 'monitor' in Server Control — the same as Server Process Monitoring">
            <Table rows={s.app_tier} empty="No app tier data in this snapshot yet (taken every 15 minutes)."
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
