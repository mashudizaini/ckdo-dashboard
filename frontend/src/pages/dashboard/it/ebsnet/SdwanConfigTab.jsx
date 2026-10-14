/**
 * Konfigurasi SD-WAN — the running SD-WAN / IPsec / route / shaping config
 * of both FortiGates, read live over the read-only SSH login (backend
 * sdwan_config.py), with the HO↔Plant check that EBS keeps one tunnel for
 * both directions. Read-only: nothing here changes the firewalls.
 */
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Loader2, ArrowRight, ArrowLeftRight } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Level, Note, Panel, RawBlock, Spinner, Stat, Table, fmtDate, errText } from "./ui";

const CHECK_LEVEL = { ok: "ok", warn: "warn", crit: "crit", info: "unknown" };
const CHECK_LABEL = { ok: "OK", warn: "Warning", crit: "Critical", info: "Info" };
const ROLES = ["HO", "Plant"];

const join = (v) => (Array.isArray(v) ? v.join(", ") : v) || "—";
const h4 = { fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 6 };

function memberName(dev, seq) {
  if (seq === 0) return "all";
  const m = dev.members.find((x) => x.seq === seq);
  return m ? `${seq} · ${m.interface}` : `${seq}`;
}

function Chip({ children, tone = "slate" }) {
  const tones = {
    slate: { bg: "#f1f5f9", color: "#334155" },
    blue: { bg: "rgba(37,99,235,0.1)", color: "#1d4ed8" },
    green: { bg: "rgba(12,163,12,0.1)", color: "#0a7d0a" },
  };
  const t = tones[tone] || tones.slate;
  return <span className="inline-block rounded-md" style={{ background: t.bg, color: t.color, fontSize: 11, fontWeight: 700, padding: "1px 7px", marginRight: 4 }}>{children}</span>;
}

function Findings({ checks }) {
  if (!checks.length) return <Empty>No findings.</Empty>;
  return (
    <div className="space-y-2">
      {checks.map((c, i) => (
        <div key={i} className="rounded-xl px-3.5 py-2.5" style={{ border: "1px solid rgba(0,0,0,0.06)", background: "#fbfdff" }}>
          <div className="flex items-center gap-2 flex-wrap">
            <Level size="sm" level={CHECK_LEVEL[c.level]} label={CHECK_LABEL[c.level]} />
            <Chip>{c.device}</Chip>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>{c.title}</span>
          </div>
          <p style={{ fontSize: 12, color: "#475569", marginTop: 4, lineHeight: 1.5 }}>{c.detail}</p>
        </div>
      ))}
    </div>
  );
}

function FlowCard({ f }) {
  return (
    <div className="rounded-xl px-4 py-3" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.05)" }}>
      <p style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>{f.label}</p>
      <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{f.src || "laptop HO"} → {f.dst}</p>
      <div style={{ fontSize: 12, color: "#334155", marginTop: 8, lineHeight: 1.6 }}>
        {f.via === "rule" ? (
          <>SD-WAN rule <b>#{f.rule_id} {f.rule_name || ""}</b> · mode <b>{f.mode}</b>{f.note ? ` · ${f.note}` : ""}</>
        ) : f.route ? (
          <>No SD-WAN rule matches → <b>routing table</b>: {f.route.dst} via {f.route.device || join(f.route.sdwan_zone)} (distance {f.route.distance})</>
        ) : <>Neither an SD-WAN rule nor a static route matches.</>}
      </div>
      <div className="flex items-center gap-1 flex-wrap mt-2">
        {f.order.length ? f.order.map((o, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ArrowRight size={11} color="#94a3b8" />}
            <Chip tone={i === 0 ? "blue" : "slate"}>{i === 0 ? "primary" : "backup"} · {o.interface}{o.zone ? " (zone)" : ""}</Chip>
          </span>
        )) : <span style={{ fontSize: 11.5, color: "#94a3b8" }}>—</span>}
      </div>
      {f.slas?.length > 0 && (
        <p style={{ fontSize: 11.5, color: "#475569", marginTop: 6 }}>
          SLA: {f.slas.map((s) => `${s.health_check}#${s.id} — latency ${s.latency_ms ?? "?"} ms, jitter ${s.jitter_ms ?? "?"} ms, loss ${s.loss_pct ?? "?"}% (${join(s.link_cost_factor)})`).join("; ")}
        </p>
      )}
      {f.live_first_alive && <p style={{ fontSize: 11.5, color: "#0a7d0a", marginTop: 4, fontWeight: 600 }}>Live: first member alive right now = {f.live_first_alive}</p>}
    </div>
  );
}

function PathPanel({ analysis }) {
  const { pairs, flows, ebs_ips, ho_lans } = analysis;
  const first = (label) => flows.find((f) => f.label.startsWith(label))?.order?.[0]?.interface;
  const hoMain = first("User HO"), plMain = first("Server EBS");
  return (
    <Panel title="EBS path — outbound & return" subtitle={`EBS: ${ebs_ips.join(", ") || "not set in Setup"} · HO LANs detected: ${ho_lans.join(", ") || "—"}`}>
      <Note>SD-WAN rules only steer sessions <b>opened</b> from that side. HO users open EBS, so the <b>HO FGT</b> chooses the tunnel; the Plant FGT replies along that session.
        For the path to be one and the same both ways, the tunnel order and SLA thresholds on both sides must be identical.</Note>
      <div className="mt-4">
        <p style={h4}>HO ↔ Plant tunnel pairs</p>
        <Table rows={pairs} empty="No tunnel pairs read yet."
          columns={[
            { key: "ho", label: "Tunnel HO", render: (r) => <span><b>{r.ho}</b>{r.ho === hoMain && <> <Chip tone="blue">EBS primary at HO</Chip></>}</span> },
            { key: "ho_path", label: "HO path" },
            { key: "x", label: "", render: () => <ArrowLeftRight size={13} color="#94a3b8" /> },
            { key: "plant", label: "Tunnel Plant", render: (r) => <span><b>{r.plant}</b>{r.plant === plMain && <> <Chip tone="blue">primary to HO at Plant</Chip></>}</span> },
            { key: "plant_path", label: "Plant path" },
            { key: "by", label: "Paired by" },
          ]} />
      </div>
      <div className="grid gap-3 mt-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        {flows.map((f) => <FlowCard key={f.label} f={f} />)}
      </div>
    </Panel>
  );
}

function DeviceDetail({ snap }) {
  const d = snap.summary;
  const liveOf = (iface) => (d.live_health || []).find((h) => h.member === iface);
  const ph2 = (name) => (d.phase2 || []).filter((p) => p.phase1name === name);
  const sections = [
    ["Zone & member", (
      <>
        <p style={{ fontSize: 12, color: "#475569", marginBottom: 6 }}>Zone: {d.zones.map((z) => <Chip key={z}>{z}</Chip>)}{!d.zones.length && "—"}</p>
        <Table rows={d.members} empty="No SD-WAN members."
          columns={[
            { key: "seq", label: "Seq" },
            { key: "interface", label: "Interface", render: (r) => <span><b>{r.interface}</b>{d.interfaces?.[r.interface]?.alias ? ` (${d.interfaces[r.interface].alias})` : ""}</span> },
            { key: "zone", label: "Zone" },
            { key: "gateway", label: "Gateway" },
            { key: "priority", label: "Priority", align: "right" },
            { key: "cost", label: "Cost", align: "right" },
            { key: "status", label: "Status", render: (r) => <Level size="sm" level={r.status === "enable" ? "ok" : "unknown"} label={r.status} /> },
            { key: "live", label: "Live SLA", render: (r) => { const l = liveOf(r.interface); return l ? <span><Level size="sm" level={l.state === "alive" ? "ok" : "crit"} label={l.state} /> {l.latency_ms ?? "-"} ms · {l.jitter_ms ?? "-"} ms · {l.loss_pct ?? "-"}%</span> : "—"; } },
            { key: "comment", label: "Notes", wrap: true },
          ]} />
      </>
    )],
    ["Performance SLA (health check)", (
      <Table rows={d.health_checks} empty="No health checks."
        columns={[
          { key: "name", label: "Name", render: (r) => <b>{r.name}</b> },
          { key: "server", label: "Server", render: (r) => join(r.server) },
          { key: "protocol", label: "Protocol" },
          { key: "interval_ms", label: "Interval", align: "right", render: (r) => r.interval_ms != null ? `${r.interval_ms} ms` : "—" },
          { key: "ft", label: "Fail / recovery", render: (r) => `${r.failtime ?? "—"} / ${r.recoverytime ?? "—"}` },
          { key: "members", label: "Member", wrap: true, render: (r) => r.members.map((s) => memberName(d, s)).join(", ") || "—" },
          { key: "sla", label: "Target SLA", wrap: true, render: (r) => r.sla.length ? r.sla.map((s) => `#${s.id}: ${s.latency_ms} ms / ${s.jitter_ms} ms / ${s.loss_pct}% (${join(s.link_cost_factor)})`).join("; ") : "—" },
          { key: "update_static_route", label: "Update route" },
        ]} />
    )],
    ["SD-WAN rules (order = evaluation order)", (
      <Table rows={d.services} empty="No SD-WAN rules — all traffic follows the implicit rule (routing table)."
        columns={[
          { key: "id", label: "#" },
          { key: "name", label: "Name", render: (r) => <b>{r.name || "—"}</b> },
          { key: "mode", label: "Mode" },
          { key: "src", label: "Source", wrap: true, render: (r) => `${r.src_negate ? "NOT " : ""}${join(r.src)}` },
          { key: "dst", label: "Destination", wrap: true, render: (r) => `${r.dst_negate ? "NOT " : ""}${r.internet_service ? "internet service" : join(r.dst)}` },
          { key: "pm", label: "Member order", wrap: true, render: (r) => r.priority_members.length ? r.priority_members.map((s) => memberName(d, s)).join(" → ") : (r.priority_zone.length ? `zone ${join(r.priority_zone)}` : "—") },
          { key: "sla", label: "SLA", render: (r) => r.sla.map((s) => `${s.health_check}#${s.id}`).join(", ") || "—" },
          { key: "live", label: "Live", wrap: true, render: (r) => { const l = (d.live_services || []).find((x) => x.id === r.id); return l ? l.members.map((m) => `${m.interface} (${m.state})`).join(" → ") : "—"; } },
          { key: "status", label: "Status" },
        ]} />
    )],
    ["Tunnel IPsec", (
      <Table rows={d.phase1} empty="No IPsec tunnels."
        columns={[
          { key: "name", label: "Tunnel", render: (r) => <b>{r.name}</b> },
          { key: "if", label: "Via", render: (r) => `${r.interface || "—"} ${r.local_ip || ""}` },
          { key: "remote_gw", label: "Remote GW", render: (r) => r.type === "dynamic" ? "dialup (dynamic)" : (r.remote_gw || "—") },
          { key: "ike_version", label: "IKE", render: (r) => r.ike_version ? `v${r.ike_version}` : "—" },
          { key: "proposal", label: "Proposal", wrap: true, render: (r) => join(r.proposal) },
          { key: "dhgrp", label: "DH", render: (r) => join(r.dhgrp) },
          { key: "dpd", label: "DPD", render: (r) => r.dpd ? `${r.dpd}${r.dpd_retryinterval ? ` / ${r.dpd_retryinterval}s` : ""}` : "—" },
          { key: "tip", label: "IP tunnel", render: (r) => r.tunnel_ip ? `${r.tunnel_ip.split(" ")[0]} → ${(r.tunnel_remote_ip || "").split(" ")[0] || "—"}` : "—" },
          { key: "psr", label: "Preserve session route", render: (r) => r.preserve_session_route },
          { key: "p2", label: "Phase 2", wrap: true, render: (r) => ph2(r.name).map((p) => `${p.name}: auto-neg ${p.auto_negotiate || "—"}, keepalive ${p.keepalive || "—"}`).join("; ") || "—" },
        ]} />
    )],
    ["Static route", (
      <Table rows={d.static_routes} empty="No static routes."
        columns={[
          { key: "seq", label: "Seq" },
          { key: "dst", label: "Destination", render: (r) => r.dst || r.dstaddr || "—" },
          { key: "gateway", label: "Gateway" },
          { key: "via", label: "Interface / zone", render: (r) => r.device || (r.sdwan_zone.length ? `zone ${join(r.sdwan_zone)}` : (r.blackhole ? "blackhole" : "—")) },
          { key: "distance", label: "Distance", align: "right" },
          { key: "priority", label: "Priority", align: "right" },
          { key: "status", label: "Status" },
          { key: "comment", label: "Notes", wrap: true },
        ]} />
    )],
    ["Traffic shaping", (
      <div className="space-y-3">
        <Table rows={d.shapers} empty="No traffic shapers."
          columns={[
            { key: "name", label: "Shaper", render: (r) => <b>{r.name}</b> },
            { key: "guaranteed_kbps", label: "Guaranteed", align: "right", render: (r) => `${(r.guaranteed_kbps / 1000).toFixed(1)} Mbps` },
            { key: "maximum_kbps", label: "Maximum", align: "right", render: (r) => r.maximum_kbps ? `${(r.maximum_kbps / 1000).toFixed(1)} Mbps` : "unlimited" },
            { key: "priority", label: "Priority" },
          ]} />
        <Table rows={d.shaping_policies} empty="No shaping policies."
          columns={[
            { key: "id", label: "#" },
            { key: "name", label: "Name" },
            { key: "srcaddr", label: "Source", wrap: true, render: (r) => join(r.srcaddr) },
            { key: "dstaddr", label: "Destination", wrap: true, render: (r) => join(r.dstaddr) },
            { key: "traffic_shaper", label: "Shaper" },
            { key: "traffic_shaper_reverse", label: "Shaper reverse", render: (r) => r.traffic_shaper_reverse || <span style={{ color: "#b77d00", fontWeight: 700 }}>not set</span> },
            { key: "status", label: "Status" },
          ]} />
      </div>
    )],
  ];
  return (
    <div className="space-y-5">
      {sections.map(([title, body]) => <div key={title}><p style={h4}>{title}</p>{body}</div>)}
      {snap.raw && Object.entries(snap.raw).map(([k, v]) => <RawBlock key={k} title={`Raw output: ${k}`} text={v} />)}
    </div>
  );
}

export default function SdwanConfigTab({ goTo }) {
  const [view, setView] = useState(null);
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("HO");

  const load = useCallback(async () => {
    try { setView(await ebsNetApi.getSdwanConfig()); } catch (e) { setView({ devices: {}, analysis: null, configured: 0 }); alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const capture = async () => {
    setBusy(true);
    try { setView(await ebsNetApi.captureSdwanConfig()); } catch (e) { alert(errText(e)); } finally { setBusy(false); }
  };

  if (!view) return <Spinner />;
  const devices = view.devices || {};
  const any = ROLES.some((r) => devices[r]);
  const snap = devices[role];

  return (
    <>
      <Panel title="SD-WAN configuration (live from FortiGate)"
        subtitle={`Read-only SSH · show full-configuration system sdwan / vpn ipsec, router static, shaping · PSK & ENC values hidden · ${ROLES.map((r) => `${r}: ${devices[r] ? fmtDate(devices[r].checked_at) : "not read yet"}`).join(" · ")}`}
        action={<Btn size="sm" variant="primary" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy || !view.configured} onClick={capture}>Read configuration now</Btn>}>
        {!view.configured ? (
          <Note>Choose the HO and Plant FortiGates in <button type="button" style={{ textDecoration: "underline", fontWeight: 700 }} onClick={() => goTo("setup")}>Setup</button> (the same login as the FortiGate / SD-WAN tab).
            The read-only account needs read access to <code>netgrp</code> (SD-WAN, route, interface), <code>vpngrp</code> (IPsec) and <code>fwgrp</code> (address, shaping).</Note>
        ) : !any ? (
          <Empty>Never read yet. Click <b>Read configuration now</b> — about 10–30 seconds per FortiGate.</Empty>
        ) : (
          <div className="flex gap-2.5 flex-wrap">
            {ROLES.map((r) => {
              const s = devices[r];
              if (!s) return <Stat key={r} label={r} value="not read yet" />;
              if (!s.ok) return <Stat key={r} label={r} value="failed" level="crit" hint={s.error?.slice(0, 60)} />;
              const d = s.summary;
              return (
                <div key={r} className="rounded-xl px-3.5 py-2.5" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.05)", minWidth: 260 }}>
                  <p style={{ fontSize: 10.5, color: "#64748b", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>{r} · {d.hostname || s.name}</p>
                  <p style={{ fontSize: 11.5, color: "#475569", marginTop: 2 }}>{d.version || "—"}</p>
                  <div className="flex gap-1.5 flex-wrap mt-1.5">
                    <Level size="sm" level={d.sdwan_status === "enable" ? "ok" : "unknown"} label={`SD-WAN ${d.sdwan_status}`} />
                    <Chip>{d.members.length} member</Chip><Chip>{d.services.length} rules</Chip><Chip>{d.phase1.length} tunnel</Chip>
                    {d.asymroute === "enable" && <Level size="sm" level="warn" label="asymroute on" />}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {view.analysis && any && (
        <>
          <Panel title="Findings" subtitle="Checked against the CKDO SD-WAN Runbook — above all: does EBS use one and the same tunnel both ways">
            <Findings checks={view.analysis.checks} />
          </Panel>
          {view.analysis.flows.length > 0 && <PathPanel analysis={view.analysis} />}
        </>
      )}

      {any && (
        <Panel title="Configuration detail" subtitle="Values exactly as running on the device (full-configuration for SD-WAN & IPsec)"
          action={ROLES.map((r) => <Btn key={r} size="sm" variant={role === r ? "primary" : "default"} onClick={() => setRole(r)}>{r}</Btn>)}>
          {!snap ? <Empty>The {role} configuration has not been read yet.</Empty>
            : !snap.ok ? <><p style={{ color: "#dc2626", fontSize: 12 }}>{snap.error}</p>{snap.raw && Object.entries(snap.raw).map(([k, v]) => <RawBlock key={k} title={`Raw output: ${k}`} text={v} />)}</>
              : <DeviceDetail snap={snap} />}
        </Panel>
      )}
    </>
  );
}
