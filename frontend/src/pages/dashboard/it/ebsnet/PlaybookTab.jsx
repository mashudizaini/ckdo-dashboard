/**
 * Playbook — the improvement backlog for EBS access from HO, as a shared
 * checklist (state in ebsnet_settings.playbook_checklist, so every IT staff
 * member sees the same ticks). Order inside a group = suggested priority.
 */
import { useEffect, useState } from "react";
import { CheckSquare, Square } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Note, Panel, errText, fmtDate } from "./ui";

const GROUPS = [
  {
    title: "1 · Measure first (baseline before changing anything)",
    items: [
      ["base-agent", "Run the PowerShell agent on 3–5 HO laptops at 08:00, 11:00, 14:00 and 15:00–16:00 for one week.", "Separates a single-laptop problem (Case D) from a path problem (Case B), and shows the busy-hour pattern in the Test time matrix."],
      ["base-ebs-test", "Record Oracle EBS's built-in Network Test (RTT + data rate) at the same time as the agent.", "Official Oracle figures that compare directly with the dashboard probes."],
      ["base-incident", "For every “EBS is slow” complaint: log an incident RIGHT THEN with the snapshot ticked.", "An exact timestamp = correlation across firewall / VPN / app server / DB. Without it, the root cause is just a guess."],
      ["base-change", "Rule: no VPN, routing, MTU, firewall or Oracle change without a before & after baseline.", "Avoids “we changed it but don't know what it did”."],
    ],
  },
  {
    title: "2 · HO ↔ Plant path (FortiGate 121G / SD-WAN)",
    items: [
      ["fg-sla", "Create an EBS-specific SD-WAN performance SLA: ping + HTTP probe to the EBS server (172.21.2.x) through the tunnel, target latency ≤ 50 ms, jitter ≤ 10 ms, loss ≤ 1 %.", "The FortiGate itself becomes a 24-hour sensor; the results show in the FortiGate tab."],
      ["fg-rule", "An SD-WAN rule for the EBS subnet with the Lowest Cost (SLA) / Best Quality strategy — not load-balance, which can move a session mid-way.", "One Forms TCP session that moves link = Forms hang / FRM-92101. Load-balance suits internet traffic, not EBS."],
      ["fg-dual-tunnel", "A second IPsec tunnel over iForte at Plant as an SD-WAN member, with automatic failover; test failover outside working hours.", "Today one tunnel = one point of failure. iForte radio is rain-sensitive, so use it as an SLA-based backup, not the primary path."],
      ["fg-mss", "Set tcp-mss (≈1350) on the EBS tunnel policy and check the tunnel MTU; compare with the Path MTU from the agent.", "IPsec packet fragmentation (NET-06) has a typical symptom: login is fine, large screens/LOVs freeze."],
      ["fg-qos", "Traffic shaping: priority + guaranteed bandwidth for the EBS ports; limit Windows Update, OneDrive/backup and streaming during working hours, especially on the 30 Mbps Plant link.", "Forms is very sensitive to queuing (bufferbloat) — one large upload can raise the RTT for every EBS user."],
      ["fg-ttl", "EBS policy session-TTL longer than the ICX Session Timeout and the Forms heartbeat; DPD on-idle enabled.", "A firewall that silently cuts idle sessions makes Forms “hang” when users come back from a meeting."],
      ["fg-offload", "Make sure the EBS tunnel is NPU-offloaded and does not go through proxy-based / deep SSL inspection.", "Inspection adds latency & firewall CPU and disables hardware offload for trusted internal traffic."],
      ["fg-license", "Renew the FortiGuard licence (expires 11 May 2026).", "IPS/AV/Web Filter no longer update — not a cause of slowness, but a security risk on the same device."],
      ["fg-snmp", "Monitor WAN & tunnel utilisation (SNMP / FortiAnalyzer) with an alarm at > 70–80 %.", "Bandwidth saturation (NET-05) can only be proven with a utilisation graph at the time of the incident."],
      ["fg-ho-isp", "Consider a second link at HO (currently CBN only).", "If the HO link goes down, all of HO loses EBS even though Plant has two ISPs."],
    ],
  },
  {
    title: "3 · HO LAN & laptops",
    items: [
      ["cli-wired", "Heavy Forms users (Finance, Purchasing, PPIC) use wired LAN; Wi-Fi only on 5 GHz with signal > 70 %.", "Wi-Fi adds jitter at the first hop — if the gateway already has jitter, the rest of the path cannot fix it (Case A)."],
      ["cli-wifi-survey", "HO Wi-Fi survey: channel overlap, clients per AP, 802.11k/v/r roaming.", "Agent reports showing high jitter to the gateway on many laptops = an AP problem, not a laptop problem."],
      ["cli-ram", "Laptop standard: RAM ≥ 8 GB (16 GB for Excel + Teams + EBS users), SSD.", "The agent flags CLI-02 when free RAM < 20 % — Java Forms ends up swapping."],
      ["cli-java", "Standardise Java for Forms 12.2 (JRE 8 / Java Web Start) with the same version on every laptop.", "Different versions force the Forms jars to be downloaded again over the WAN and trigger security prompts that make users close the session."],
      ["cli-proxy-dns", "Bypass the proxy for the EBS hostname and make sure internal DNS resolves EBS to its private IP.", "A proxy or hairpin through a public IP adds hops & latency to every request."],
      ["cli-power-av", "Balanced/High performance power plan when plugged in; turn off NIC power saving; exclude the Java/Forms cache from real-time antivirus scanning.", "CPU throttling & antivirus scans feel like slow EBS (CLI-01/CLI-05)."],
      ["cli-browser", "A dedicated browser profile for EBS without heavy extensions; clear the Java/JNLP cache when a single laptop complains.", "A common cause of Case D (CLI-04)."],
    ],
  },
  {
    title: "4 · Oracle EBS 12.2 (application & database tier)",
    items: [
      ["ebs-forms-retry", "Set Forms networkRetries and heartBeat through AutoConfig (not by editing formsweb.cfg by hand).", "Lets Forms survive a brief tunnel drop instead of going straight to FRM-92101/92102."],
      ["ebs-compress", "Enable HTTP compression & cache headers for static files on OHS for OAF pages.", "Reduces the bytes crossing the 30 Mbps Plant link without changing the application."],
      ["ebs-schedule", "Schedule heavy requests (Gather Schema Statistics, purges, large reports) outside HO working hours; send large report output via email/NAS.", "Heavy concurrent requests raise DB CPU/I/O while HO users are working (DB-01/DB-03)."],
      ["ebs-purge", "Routine purge of FND_CONCURRENT_REQUESTS, Workflow & logs; scheduled Gather Stats.", "Bloated FND/WF tables slow down screens in a way that looks like “network”."],
      ["ebs-jvm", "Review heap & the number of oacore/forms managed servers against the number of users.", "A JVM full GC feels exactly like a hang of a few seconds (EBS-02/EBS-03)."],
      ["ebs-awr", "During a Case C incident: take AWR/ASH for the incident time window (Top SQL, wait events, blocking).", "The EBS Server tab gives a quick picture; AWR gives proof."],
    ],
  },
  {
    title: "5 · If HO → Plant RTT really cannot come down",
    items: [
      ["arch-rds", "A jump host / RDS / Citrix at Plant for Forms power users.", "Only screen images cross the WAN; Forms talks to the server over the Plant LAN (~1 ms). Most effective for “chatty” Forms."],
      ["arch-oaf", "Steer transactions to OAF/self-service (HTML) pages where available.", "HTML pages tolerate latency far better than the Forms Java applet."],
      ["arch-isp-sla", "Ask the ISP for a written latency/jitter/loss SLA, attaching the baseline from this module.", "24/7 probe data is the evidence when escalating to the ISP (NET-08)."],
    ],
  },
  {
    title: "Questions for the Network Team (script §12)",
    items: [
      ["q-provider", "Which provider does EBS traffic go through, and which provider does the VPN tunnel use?", "Check in the FortiGate tab: the “Route to EBS via” column."],
      ["q-lb", "Do the two providers load-balance, and can one TCP session move between providers?", ""],
      ["q-failover", "How does failover work, and when was it last tested?", ""],
      ["q-metrics", "What are the current latency, loss, jitter, tunnel utilisation and tunnel MTU/MSS?", "Most of these are already read automatically in the FortiGate & Path tabs."],
    ],
  },
];
export default function PlaybookTab({ settings, user }) {
  const [state, setState] = useState(settings?.playbook_checklist || {});
  useEffect(() => { setState(settings?.playbook_checklist || {}); }, [settings]);

  const toggle = async (id) => {
    const next = { ...state };
    if (next[id]?.done) delete next[id];
    else next[id] = { done: true, by: user, at: new Date().toISOString() };
    setState(next);
    try { await ebsNetApi.putSettings({ playbook_checklist: next }); }
    catch (e) { alert(errText(e, "Save failed")); setState(state); }
  };

  const total = GROUPS.reduce((n, g) => n + g.items.length, 0);
  const done = Object.values(state).filter((v) => v?.done).length;

  return (
    <>
      <Note>
        Recommendations for stable Oracle EBS access from HO. The principle: <b>EBS Forms is sensitive to round-trips and stability, not bandwidth</b> —
        one Forms screen can take hundreds of round-trips, so 60 ms × 200 = 12 seconds. Bring jitter & loss down, keep TCP sessions from switching paths, and prove every
        change with before/after data. Progress: <b>{done}/{total}</b> done.
      </Note>
      <div className="h-4" />
      {GROUPS.map((g) => (
        <Panel key={g.title} title={g.title}>
          <div className="space-y-2.5">
            {g.items.map(([id, text, why]) => {
              const st = state[id];
              const Icon = st?.done ? CheckSquare : Square;
              return (
                <button key={id} type="button" onClick={() => toggle(id)} className="flex items-start gap-2.5 text-left w-full rounded-lg p-2 hover:bg-slate-50">
                  <Icon size={16} style={{ color: st?.done ? "#0ca30c" : "#94a3b8", flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <p style={{ fontSize: 12.5, color: "#0f172a", fontWeight: 600, textDecoration: st?.done ? "line-through" : "none", opacity: st?.done ? 0.7 : 1 }}>{text}</p>
                    {why && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{why}</p>}
                    {st?.done && <p style={{ fontSize: 10.5, color: "#0ca30c", marginTop: 2 }}>Done · {st.by} · {fmtDate(st.at)}</p>}
                  </div>
                </button>
              );
            })}
          </div>
        </Panel>
      ))}
    </>
  );
}
