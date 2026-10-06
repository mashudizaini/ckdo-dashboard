/**
 * Oracle EBS Network Monitoring
 * ─────────────────────────────────────────
 * Why is EBS slow from HO? Measured from three vantage points — the server
 * on the Plant LAN (scheduled probes, FortiGate SD-WAN/tunnel, EBS/DB
 * health), the HO laptop's browser, and the generated PowerShell agent — and
 * classified into the Case A–D / NET-CLI-EBS-DB scheme of
 * sumber/Oracle_EBS_HO_Plant_Performance_Diagnostic_Script.md.
 */
import { useCallback, useEffect, useState } from "react";
import { ebsNetApi } from "@/api/dashboard";
import { useAuthStore } from "@/store/authStore";
import OverviewTab from "./OverviewTab";
import PathTab from "./PathTab";
import FortigateTab from "./FortigateTab";
import SdwanConfigTab from "./SdwanConfigTab";
import EbsTab from "./EbsTab";
import ClientTab from "./ClientTab";
import IncidentTab from "./IncidentTab";
import PlaybookTab from "./PlaybookTab";
import SetupTab from "./SetupTab";
import ReportTab from "./ReportTab";

const TABS = [
  ["overview", "Overview"],
  ["report", "Laporan & Kesimpulan"],
  ["path", "Jalur & Probe"],
  ["fortigate", "FortiGate / SD-WAN"],
  ["sdwancfg", "Konfigurasi SD-WAN"],
  ["ebs", "EBS Server"],
  ["client", "Client Test (Laptop)"],
  ["incidents", "Incident Log"],
  ["playbook", "Playbook & Rekomendasi"],
  ["setup", "Setup"],
];

const DEFAULT_T = { latency_warn: 50, latency_crit: 100, jitter_warn: 10, jitter_crit: 30, loss_warn: 0.1, loss_crit: 2, fgt_cpu_warn: 70, fgt_mem_warn: 80 };

export default function EbsNetworkMonitoring() {
  const [tab, setTab] = useState(() => {
    try { return localStorage.getItem("ebsnet_tab") || "overview"; } catch (_) { return "overview"; }
  });
  const [settings, setSettings] = useState(null);
  const [meta, setMeta] = useState(null);
  const user = useAuthStore((s) => s.user?.email || s.user?.username || "");

  const loadSettings = useCallback(async () => {
    try { setSettings(await ebsNetApi.getSettings()); } catch (_) {}
  }, []);
  useEffect(() => { loadSettings(); ebsNetApi.getMeta().then(setMeta).catch(() => {}); }, [loadSettings]);

  const goTo = (t) => {
    setTab(t);
    try { localStorage.setItem("ebsnet_tab", t); } catch (_) {}
  };
  const thresholds = { ...DEFAULT_T, ...(settings?.thresholds || {}) };

  return (
    <>
      <div className="flex gap-1 flex-wrap mb-4 p-1 rounded-xl" style={{ background: "#ffffff", boxShadow: "0 1px 3px rgba(15,23,42,0.08)" }}>
        {TABS.map(([id, label]) => (
          <button key={id} type="button" onClick={() => goTo(id)} className="rounded-lg transition-all"
            style={{
              padding: "6px 12px", fontSize: 12, fontWeight: 700, border: "none",
              background: tab === id ? "#2563eb" : "transparent", color: tab === id ? "#ffffff" : "#475569",
            }}>
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab goTo={goTo} />}
      {tab === "report" && <ReportTab settings={settings} onSettingsSaved={loadSettings} />}
      {tab === "path" && <PathTab thresholds={thresholds} />}
      {tab === "fortigate" && <FortigateTab thresholds={thresholds} goTo={goTo} />}
      {tab === "sdwancfg" && <SdwanConfigTab goTo={goTo} />}
      {tab === "ebs" && <EbsTab />}
      {tab === "client" && <ClientTab />}
      {tab === "incidents" && <IncidentTab meta={meta} thresholds={thresholds} />}
      {tab === "playbook" && <PlaybookTab settings={settings} user={user} />}
      {tab === "setup" && <SetupTab settings={settings} onSettingsSaved={loadSettings} />}
    </>
  );
}
