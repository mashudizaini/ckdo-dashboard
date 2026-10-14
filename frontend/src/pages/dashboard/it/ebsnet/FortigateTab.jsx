import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Level, Note, Panel, RawBlock, Spinner, Stat, Table, fmtDate, fmtTime, errText, SERIES } from "./ui";

const axis = { fontSize: 10.5, fill: "#64748b" };

function FgCard({ snap, t }) {
  const s = snap.summary || {};
  return (
    <Panel title={snap.name} subtitle={snap.ok ? `${s.hostname || ""} · ${s.version || ""} · ${fmtDate(snap.checked_at)}` : fmtDate(snap.checked_at)}>
      {!snap.ok ? <p style={{ color: "#dc2626", fontSize: 12 }}>{snap.error}</p> : (
        <div className="space-y-4">
          <div className="flex gap-2.5 flex-wrap">
            <Stat label="CPU" value={s.cpu_pct} unit="%" level={s.cpu_pct >= t.fgt_cpu_warn ? "warn" : "ok"} />
            <Stat label="Memory" value={s.mem_pct} unit="%" level={s.mem_pct >= t.fgt_mem_warn ? "warn" : "ok"} hint={s.mem_pct >= 80 ? "conserve mode ~88%" : undefined} />
            <Stat label="Sessions (1 min)" value={s.sessions?.toLocaleString("en-US")} />
            <Stat label="Traffic in / out" value={s.net_in_kbps != null ? `${(s.net_in_kbps / 1000).toFixed(1)} / ${(s.net_out_kbps / 1000).toFixed(1)}` : null} unit="Mbps" />
            <Stat label="Uptime" value={s.uptime} />
            <Stat label="Route to EBS via" value={s.ebs_route_via?.join(", ") || null} />
          </div>

          <div>
            <p style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 6 }}>SD-WAN performance SLA</p>
            <Table rows={s.sdwan} empty="No SD-WAN health checks (or SD-WAN not configured). Create a performance SLA that probes the EBS server / the FortiGate on the other side."
              columns={[
                { key: "check", label: "Health check" },
                { key: "member", label: "Member" },
                { key: "state", label: "State", render: (r) => <Level size="sm" level={r.state === "alive" ? "ok" : "crit"} label={r.state} /> },
                { key: "latency_ms", label: "Latency", align: "right", render: (r) => r.latency_ms != null ? `${r.latency_ms} ms` : "—" },
                { key: "jitter_ms", label: "Jitter", align: "right", render: (r) => r.jitter_ms != null ? `${r.jitter_ms} ms` : "—" },
                { key: "loss_pct", label: "Loss", align: "right", render: (r) => r.loss_pct != null ? `${r.loss_pct}%` : "—" },
                { key: "mos", label: "MOS", align: "right" },
                { key: "sla_map", label: "SLA map" },
              ]} />
          </div>

          <div>
            <p style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 6 }}>Tunnel IPsec</p>
            <Table rows={(s.tunnels || []).map((tun) => ({ ...tun, ...(s.tunnel_detail || []).find((d) => d.name === tun.name) }))}
              empty="No IPsec tunnels read."
              columns={[
                { key: "name", label: "Tunnel" },
                { key: "peer", label: "Peer" },
                { key: "up", label: "Status", render: (r) => <Level size="sm" level={r.up ? "ok" : "crit"} label={r.up ? "UP" : "DOWN"} /> },
                { key: "sel", label: "Selector up", render: (r) => `${r.selectors_up}/${r.selectors_total}` },
                { key: "err", label: "Err rx / tx", align: "right", render: (r) => `${r.rx_err} / ${r.tx_err}` },
                { key: "mtu", label: "MTU", align: "right", render: (r) => r.mtu ?? "—" },
                { key: "dpd", label: "DPD", render: (r) => r.dpd_mode ? `${r.dpd_mode} (failed ${r.dpd_fail_count ?? 0})` : "—" },
                { key: "npu", label: "NPU offload", render: (r) => r.npu_offload ? "yes" : "no" },
              ]} />
          </div>
          {snap.raw && Object.entries(snap.raw).map(([k, v]) => <RawBlock key={k} title={`Raw output: ${k}`} text={v} />)}
        </div>
      )}
    </Panel>
  );
}

export default function FortigateTab({ thresholds, goTo }) {
  const [snaps, setSnaps] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([ebsNetApi.getFortigate(), ebsNetApi.fortigateHistory(24)]);
      setSnaps(s); setHist(h);
    } catch (e) { setSnaps([]); alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const capture = async () => {
    setBusy(true);
    try { await ebsNetApi.captureFortigate(); await load(); } catch (e) { alert(errText(e)); } finally { setBusy(false); }
  };

  // One chart per FortiGate+SLA member would multiply fast — chart the SLA
  // latency of every member of the first FortiGate that reports SD-WAN, at
  // most two members (one per categorical slot).
  const chart = useMemo(() => {
    const withSla = hist.filter((h) => h.sdwan?.length);
    if (!withSla.length) return null;
    const name = withSla[0].name;
    const rows = withSla.filter((h) => h.name === name);
    const members = [...new Set(rows.flatMap((h) => h.sdwan.map((m) => `${m.check} · ${m.member}`)))].slice(0, 2);
    const data = rows.map((h) => {
      const d = { t: fmtTime(h.checked_at), at: fmtDate(h.checked_at) };
      h.sdwan.forEach((m) => { const k = `${m.check} · ${m.member}`; if (members.includes(k)) d[k] = m.latency_ms; });
      return d;
    });
    return { name, members, data };
  }, [hist]);

  if (!snaps) return <Spinner />;

  return (
    <>
      <Panel title="HO & Plant FortiGates" subtitle="Read-only SSH (get / diagnose) with credentials from Server Control · automatic snapshot every 5 minutes"
        action={<Btn size="sm" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy} onClick={capture}>Snapshot now</Btn>}>
        {!snaps.length ? (
          <>
            <Empty>No FortiGate snapshot yet.</Empty>
            <Note>Register both FortiGates in <b>Server Control</b> (LAN IP + read-only admin account, SSH port), then choose them in <button type="button" style={{ textDecoration: "underline", fontWeight: 700 }} onClick={() => goTo("setup")}>Setup</button>.
              A dedicated read-only admin profile is recommended (<code>sysgrp read, netgrp read, vpngrp read</code>) — this module never changes the configuration.</Note>
          </>
        ) : (
          <p style={{ fontSize: 12, color: "#475569" }}>Commands run: <code>get system status</code>, <code>get system performance status</code>, <code>diagnose sys sdwan health-check / member / service</code>, <code>get vpn ipsec tunnel summary</code>, <code>diagnose vpn tunnel list</code>, <code>get router info routing-table details &lt;EBS IP&gt;</code>.</p>
        )}
      </Panel>

      {chart && (
        <Panel title={`SD-WAN SLA latency, 24 hours — ${chart.name}`} subtitle="Measured by the FortiGate itself (performance SLA), separate from the server probes">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chart.data} margin={{ top: 6, right: 12, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="t" tick={axis} minTickGap={40} />
              <YAxis tick={axis} width={44} unit=" ms" />
              <Tooltip contentStyle={{ fontSize: 11.5, borderRadius: 8 }} labelFormatter={(_, p) => p?.[0]?.payload?.at || ""} />
              {chart.members.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
              {chart.members.map((m, i) => <Line key={m} type="monotone" dataKey={m} stroke={SERIES[i]} strokeWidth={2} dot={false} />)}
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {snaps.map((s) => <FgCard key={s.id} snap={s} t={thresholds} />)}
    </>
  );
}
