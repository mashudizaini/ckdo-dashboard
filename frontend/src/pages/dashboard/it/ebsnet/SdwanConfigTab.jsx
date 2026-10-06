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
const CHECK_LABEL = { ok: "OK", warn: "Waspada", crit: "Kritis", info: "Info" };
const ROLES = ["HO", "Plant"];

const join = (v) => (Array.isArray(v) ? v.join(", ") : v) || "—";
const h4 = { fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 6 };

function memberName(dev, seq) {
  if (seq === 0) return "semua";
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
  if (!checks.length) return <Empty>Tidak ada temuan.</Empty>;
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
          <>Aturan SD-WAN <b>#{f.rule_id} {f.rule_name || ""}</b> · mode <b>{f.mode}</b>{f.note ? ` · ${f.note}` : ""}</>
        ) : f.route ? (
          <>Tidak ada aturan SD-WAN yang cocok → <b>routing table</b>: {f.route.dst} via {f.route.device || join(f.route.sdwan_zone)} (distance {f.route.distance})</>
        ) : <>Tidak ada aturan SD-WAN maupun static route yang cocok.</>}
      </div>
      <div className="flex items-center gap-1 flex-wrap mt-2">
        {f.order.length ? f.order.map((o, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ArrowRight size={11} color="#94a3b8" />}
            <Chip tone={i === 0 ? "blue" : "slate"}>{i === 0 ? "utama" : "cadangan"} · {o.interface}{o.zone ? " (zone)" : ""}</Chip>
          </span>
        )) : <span style={{ fontSize: 11.5, color: "#94a3b8" }}>—</span>}
      </div>
      {f.slas?.length > 0 && (
        <p style={{ fontSize: 11.5, color: "#475569", marginTop: 6 }}>
          SLA: {f.slas.map((s) => `${s.health_check}#${s.id} — latency ${s.latency_ms ?? "?"} ms, jitter ${s.jitter_ms ?? "?"} ms, loss ${s.loss_pct ?? "?"}% (${join(s.link_cost_factor)})`).join("; ")}
        </p>
      )}
      {f.live_first_alive && <p style={{ fontSize: 11.5, color: "#0a7d0a", marginTop: 4, fontWeight: 600 }}>Live: member pertama yang alive sekarang = {f.live_first_alive}</p>}
    </div>
  );
}

function PathPanel({ analysis }) {
  const { pairs, flows, ebs_ips, ho_lans } = analysis;
  const first = (label) => flows.find((f) => f.label.startsWith(label))?.order?.[0]?.interface;
  const hoMain = first("User HO"), plMain = first("Server EBS");
  return (
    <Panel title="Jalur EBS — pergi & pulang" subtitle={`EBS: ${ebs_ips.join(", ") || "belum diisi di Setup"} · LAN HO terdeteksi: ${ho_lans.join(", ") || "—"}`}>
      <Note>Aturan SD-WAN hanya mengarahkan sesi yang <b>dibuka</b> dari sisi itu. User HO membuka EBS, jadi <b>FGT HO</b> yang memilih tunnel; FGT Plant membalas mengikuti sesi tersebut.
        Supaya jalurnya satu dan sama bolak-balik, urutan tunnel dan ambang SLA di kedua sisi harus identik.</Note>
      <div className="mt-4">
        <p style={h4}>Pasangan tunnel HO ↔ Plant</p>
        <Table rows={pairs} empty="Belum ada pasangan tunnel yang terbaca."
          columns={[
            { key: "ho", label: "Tunnel HO", render: (r) => <span><b>{r.ho}</b>{r.ho === hoMain && <> <Chip tone="blue">utama EBS di HO</Chip></>}</span> },
            { key: "ho_path", label: "Jalur HO" },
            { key: "x", label: "", render: () => <ArrowLeftRight size={13} color="#94a3b8" /> },
            { key: "plant", label: "Tunnel Plant", render: (r) => <span><b>{r.plant}</b>{r.plant === plMain && <> <Chip tone="blue">utama ke HO di Plant</Chip></>}</span> },
            { key: "plant_path", label: "Jalur Plant" },
            { key: "by", label: "Dipasangkan via" },
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
        <Table rows={d.members} empty="Belum ada member SD-WAN."
          columns={[
            { key: "seq", label: "Seq" },
            { key: "interface", label: "Interface", render: (r) => <span><b>{r.interface}</b>{d.interfaces?.[r.interface]?.alias ? ` (${d.interfaces[r.interface].alias})` : ""}</span> },
            { key: "zone", label: "Zone" },
            { key: "gateway", label: "Gateway" },
            { key: "priority", label: "Priority", align: "right" },
            { key: "cost", label: "Cost", align: "right" },
            { key: "status", label: "Status", render: (r) => <Level size="sm" level={r.status === "enable" ? "ok" : "unknown"} label={r.status} /> },
            { key: "live", label: "Live SLA", render: (r) => { const l = liveOf(r.interface); return l ? <span><Level size="sm" level={l.state === "alive" ? "ok" : "crit"} label={l.state} /> {l.latency_ms ?? "-"} ms · {l.jitter_ms ?? "-"} ms · {l.loss_pct ?? "-"}%</span> : "—"; } },
            { key: "comment", label: "Catatan", wrap: true },
          ]} />
      </>
    )],
    ["Performance SLA (health check)", (
      <Table rows={d.health_checks} empty="Belum ada health check."
        columns={[
          { key: "name", label: "Nama", render: (r) => <b>{r.name}</b> },
          { key: "server", label: "Server", render: (r) => join(r.server) },
          { key: "protocol", label: "Protokol" },
          { key: "interval_ms", label: "Interval", align: "right", render: (r) => r.interval_ms != null ? `${r.interval_ms} ms` : "—" },
          { key: "ft", label: "Fail / recovery", render: (r) => `${r.failtime ?? "—"} / ${r.recoverytime ?? "—"}` },
          { key: "members", label: "Member", wrap: true, render: (r) => r.members.map((s) => memberName(d, s)).join(", ") || "—" },
          { key: "sla", label: "Target SLA", wrap: true, render: (r) => r.sla.length ? r.sla.map((s) => `#${s.id}: ${s.latency_ms} ms / ${s.jitter_ms} ms / ${s.loss_pct}% (${join(s.link_cost_factor)})`).join("; ") : "—" },
          { key: "update_static_route", label: "Update route" },
        ]} />
    )],
    ["Aturan SD-WAN (urutan = urutan evaluasi)", (
      <Table rows={d.services} empty="Belum ada aturan SD-WAN — semua trafik mengikuti implicit rule (routing table)."
        columns={[
          { key: "id", label: "#" },
          { key: "name", label: "Nama", render: (r) => <b>{r.name || "—"}</b> },
          { key: "mode", label: "Mode" },
          { key: "src", label: "Sumber", wrap: true, render: (r) => `${r.src_negate ? "NOT " : ""}${join(r.src)}` },
          { key: "dst", label: "Tujuan", wrap: true, render: (r) => `${r.dst_negate ? "NOT " : ""}${r.internet_service ? "internet service" : join(r.dst)}` },
          { key: "pm", label: "Urutan member", wrap: true, render: (r) => r.priority_members.length ? r.priority_members.map((s) => memberName(d, s)).join(" → ") : (r.priority_zone.length ? `zone ${join(r.priority_zone)}` : "—") },
          { key: "sla", label: "SLA", render: (r) => r.sla.map((s) => `${s.health_check}#${s.id}`).join(", ") || "—" },
          { key: "live", label: "Live", wrap: true, render: (r) => { const l = (d.live_services || []).find((x) => x.id === r.id); return l ? l.members.map((m) => `${m.interface} (${m.state})`).join(" → ") : "—"; } },
          { key: "status", label: "Status" },
        ]} />
    )],
    ["Tunnel IPsec", (
      <Table rows={d.phase1} empty="Tidak ada tunnel IPsec."
        columns={[
          { key: "name", label: "Tunnel", render: (r) => <b>{r.name}</b> },
          { key: "if", label: "Lewat", render: (r) => `${r.interface || "—"} ${r.local_ip || ""}` },
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
      <Table rows={d.static_routes} empty="Tidak ada static route."
        columns={[
          { key: "seq", label: "Seq" },
          { key: "dst", label: "Tujuan", render: (r) => r.dst || r.dstaddr || "—" },
          { key: "gateway", label: "Gateway" },
          { key: "via", label: "Interface / zone", render: (r) => r.device || (r.sdwan_zone.length ? `zone ${join(r.sdwan_zone)}` : (r.blackhole ? "blackhole" : "—")) },
          { key: "distance", label: "Distance", align: "right" },
          { key: "priority", label: "Priority", align: "right" },
          { key: "status", label: "Status" },
          { key: "comment", label: "Catatan", wrap: true },
        ]} />
    )],
    ["Traffic shaping", (
      <div className="space-y-3">
        <Table rows={d.shapers} empty="Tidak ada traffic shaper."
          columns={[
            { key: "name", label: "Shaper", render: (r) => <b>{r.name}</b> },
            { key: "guaranteed_kbps", label: "Dijamin", align: "right", render: (r) => `${(r.guaranteed_kbps / 1000).toFixed(1)} Mbps` },
            { key: "maximum_kbps", label: "Maksimum", align: "right", render: (r) => r.maximum_kbps ? `${(r.maximum_kbps / 1000).toFixed(1)} Mbps` : "tanpa batas" },
            { key: "priority", label: "Prioritas" },
          ]} />
        <Table rows={d.shaping_policies} empty="Tidak ada shaping policy."
          columns={[
            { key: "id", label: "#" },
            { key: "name", label: "Nama" },
            { key: "srcaddr", label: "Sumber", wrap: true, render: (r) => join(r.srcaddr) },
            { key: "dstaddr", label: "Tujuan", wrap: true, render: (r) => join(r.dstaddr) },
            { key: "traffic_shaper", label: "Shaper" },
            { key: "traffic_shaper_reverse", label: "Shaper reverse", render: (r) => r.traffic_shaper_reverse || <span style={{ color: "#b77d00", fontWeight: 700 }}>tidak diisi</span> },
            { key: "status", label: "Status" },
          ]} />
      </div>
    )],
  ];
  return (
    <div className="space-y-5">
      {sections.map(([title, body]) => <div key={title}><p style={h4}>{title}</p>{body}</div>)}
      {snap.raw && Object.entries(snap.raw).map(([k, v]) => <RawBlock key={k} title={`Output mentah: ${k}`} text={v} />)}
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
      <Panel title="Konfigurasi SD-WAN (live dari FortiGate)"
        subtitle={`SSH baca-saja · show full-configuration system sdwan / vpn ipsec, router static, shaping · PSK & nilai ENC disembunyikan · ${ROLES.map((r) => `${r}: ${devices[r] ? fmtDate(devices[r].checked_at) : "belum dibaca"}`).join(" · ")}`}
        action={<Btn size="sm" variant="primary" icon={busy ? Loader2 : RefreshCw} spin={busy} disabled={busy || !view.configured} onClick={capture}>Baca konfigurasi sekarang</Btn>}>
        {!view.configured ? (
          <Note>Pilih FortiGate HO dan Plant di <button type="button" style={{ textDecoration: "underline", fontWeight: 700 }} onClick={() => goTo("setup")}>Setup</button> (login yang sama dengan tab FortiGate / SD-WAN).
            Akun read-only perlu akses baca <code>netgrp</code> (SD-WAN, route, interface), <code>vpngrp</code> (IPsec) dan <code>fwgrp</code> (address, shaping).</Note>
        ) : !any ? (
          <Empty>Belum pernah dibaca. Klik <b>Baca konfigurasi sekarang</b> — sekitar 10–30 detik per FortiGate.</Empty>
        ) : (
          <div className="flex gap-2.5 flex-wrap">
            {ROLES.map((r) => {
              const s = devices[r];
              if (!s) return <Stat key={r} label={r} value="belum dibaca" />;
              if (!s.ok) return <Stat key={r} label={r} value="gagal" level="crit" hint={s.error?.slice(0, 60)} />;
              const d = s.summary;
              return (
                <div key={r} className="rounded-xl px-3.5 py-2.5" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.05)", minWidth: 260 }}>
                  <p style={{ fontSize: 10.5, color: "#64748b", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>{r} · {d.hostname || s.name}</p>
                  <p style={{ fontSize: 11.5, color: "#475569", marginTop: 2 }}>{d.version || "—"}</p>
                  <div className="flex gap-1.5 flex-wrap mt-1.5">
                    <Level size="sm" level={d.sdwan_status === "enable" ? "ok" : "unknown"} label={`SD-WAN ${d.sdwan_status}`} />
                    <Chip>{d.members.length} member</Chip><Chip>{d.services.length} aturan</Chip><Chip>{d.phase1.length} tunnel</Chip>
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
          <Panel title="Temuan" subtitle="Dicek terhadap Runbook SD-WAN CKDO — terutama: apakah EBS memakai satu tunnel yang sama untuk pergi dan pulang">
            <Findings checks={view.analysis.checks} />
          </Panel>
          {view.analysis.flows.length > 0 && <PathPanel analysis={view.analysis} />}
        </>
      )}

      {any && (
        <Panel title="Detail konfigurasi" subtitle="Nilai persis seperti yang berjalan di perangkat (full-configuration untuk SD-WAN & IPsec)"
          action={ROLES.map((r) => <Btn key={r} size="sm" variant={role === r ? "primary" : "default"} onClick={() => setRole(r)}>{r}</Btn>)}>
          {!snap ? <Empty>Konfigurasi {role} belum dibaca.</Empty>
            : !snap.ok ? <><p style={{ color: "#dc2626", fontSize: 12 }}>{snap.error}</p>{snap.raw && Object.entries(snap.raw).map(([k, v]) => <RawBlock key={k} title={`Output mentah: ${k}`} text={v} />)}</>
              : <DeviceDetail snap={snap} />}
        </Panel>
      )}
    </>
  );
}
