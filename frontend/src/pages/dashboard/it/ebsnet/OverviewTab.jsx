import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Loader2, Laptop, Network, Waypoints, Building2, Globe2, Database, AppWindow, ChevronRight } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Level, Note, Panel, Spinner, Table, fmtDate, errText, VERDICT_LABEL, STATUS } from "./ui";

const ICONS = { laptop: Laptop, ho_lan: Network, wan: Waypoints, plant_lan: Building2, ebs_web: AppWindow, ebs_db: Database, internet: Globe2 };
const PATH = ["laptop", "ho_lan", "wan", "plant_lan", "ebs_web", "ebs_db"];

function SegmentCard({ seg, onClick }) {
  const Icon = ICONS[seg.key] || Network;
  const s = STATUS[seg.level] || STATUS.unknown;
  return (
    <button type="button" onClick={onClick} className="text-left rounded-xl p-3 transition-all hover:shadow-md"
      style={{ background: s.bg, border: `1px solid ${s.color}33`, minWidth: 150, flex: "1 1 150px" }}>
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={15} style={{ color: s.color }} />
        <span style={{ fontSize: 12, fontWeight: 800, color: "#0f172a" }}>{seg.label}</span>
      </div>
      <Level level={seg.level} size="sm" />
      {seg.notes?.filter(Boolean).slice(0, 2).map((n, i) => (
        <p key={i} style={{ fontSize: 10.5, color: "#475569", marginTop: 5, lineHeight: 1.4 }}>{n}</p>
      ))}
    </button>
  );
}

export default function OverviewTab({ goTo }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { setData(await ebsNetApi.getOverview()); } catch (e) { setData({ error: errText(e) }); }
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, [load]);

  const act = async (what) => {
    setBusy(what);
    try {
      if (what === "probe") await ebsNetApi.runProbes();
      if (what === "all") {
        await ebsNetApi.runProbes();
        await Promise.allSettled([ebsNetApi.captureEbs(), data?.configured?.fortigates ? ebsNetApi.captureFortigate() : null]);
      }
      await load();
    } catch (e) { alert(errText(e)); } finally { setBusy(""); }
  };

  if (!data) return <Spinner />;
  if (data.error) return <Panel title="Overview"><p style={{ color: "#dc2626", fontSize: 12 }}>{data.error}</p></Panel>;

  const segs = Object.fromEntries(data.segments.map((s) => [s.key, s]));
  const c = data.clients_24h;
  const laptopLevel = !c.count ? "unknown" : (c.by_verdict.D || c.by_verdict.A) ? "warn" : "ok";
  segs.laptop = {
    key: "laptop", label: "Laptop HO", level: laptopLevel,
    notes: [c.count ? `${c.count} laporan 24 jam · Case D: ${c.by_verdict.D || 0} · Case A: ${c.by_verdict.A || 0}` : "Belum ada tes laptop 24 jam terakhir"],
  };
  const tabFor = { laptop: "client", ho_lan: "client", wan: "fortigate", plant_lan: "path", ebs_web: "ebs", ebs_db: "ebs", internet: "path" };
  const dv = VERDICT_LABEL[data.diagnosis] || VERDICT_LABEL.OK;

  const missing = [];
  if (!data.configured.fortigates) missing.push("FortiGate HO/Plant belum dipilih (Setup) — SD-WAN SLA & status tunnel belum terbaca");
  if (!data.configured.ebs_web_url) missing.push("URL login EBS belum diisi (Setup) — agen tidak bisa mengukur waktu respons web tier");
  if (!data.probes.some((p) => p.segment === "wan" && p.enabled)) missing.push("Belum ada target aktif di segmen Jalur HO↔Plant (Setup) — isi IP LAN FortiGate HO");

  return (
    <>
      <Panel title="Kondisi jalur akses Oracle EBS dari HO"
        subtitle={`Diperbarui ${fmtDate(data.generated_at)} · server memprobe otomatis tiap 5 menit`}
        action={<>
          <Btn size="sm" icon={busy === "probe" ? Loader2 : RefreshCw} spin={busy === "probe"} disabled={!!busy} onClick={() => act("probe")}>Probe sekarang</Btn>
          <Btn size="sm" variant="primary" icon={busy === "all" ? Loader2 : RefreshCw} spin={busy === "all"} disabled={!!busy} onClick={() => act("all")}>Snapshot semua</Btn>
        </>}>
        <div className="flex items-stretch gap-1.5 flex-wrap">
          {PATH.map((k, i) => (
            <div key={k} className="flex items-center gap-1.5" style={{ flex: "1 1 150px" }}>
              <SegmentCard seg={segs[k]} onClick={() => goTo(tabFor[k])} />
              {i < PATH.length - 1 && <ChevronRight size={14} className="hidden xl:block" style={{ color: "#cbd5e1", flexShrink: 0 }} />}
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-3 flex-wrap items-start">
          <div style={{ flex: "0 0 200px" }}><SegmentCard seg={segs.internet} onClick={() => goTo("path")} /></div>
          <div className="flex-1" style={{ minWidth: 260 }}>
            <Note tone={data.diagnosis === "OK" ? "info" : "warn"}>
              <div className="flex items-center gap-2 mb-1"><Level level={dv.level} label={dv.text} /><b>Diagnosis otomatis</b></div>
              {data.diagnosis_text}
              <div style={{ marginTop: 6, fontSize: 11, opacity: 0.85 }}>
                Petunjuk arah investigasi, bukan kesimpulan. Ukur berulang di jam berbeda dan cocokkan timestamp sebelum mengubah konfigurasi VPN, routing, MTU, firewall, atau Oracle.
              </div>
            </Note>
          </div>
        </div>
        {missing.length > 0 && (
          <div className="mt-3">
            <Note tone="warn">
              <b>Belum lengkap:</b>
              <ul style={{ marginTop: 4, paddingLeft: 16, listStyle: "disc" }}>{missing.map((m) => <li key={m}>{m}</li>)}</ul>
              <button type="button" onClick={() => goTo("setup")} style={{ marginTop: 6, fontWeight: 700, textDecoration: "underline" }}>Buka Setup</button>
            </Note>
          </div>
        )}
      </Panel>

      <Panel title="Hasil probe terakhir" subtitle="TCP connect (1 RTT per sampel) atau TTFB HTTP dari server dashboard di Plant"
        action={<Btn size="sm" variant="ghost" onClick={() => goTo("path")}>Detail & grafik</Btn>}>
        <Table rows={data.probes.filter((p) => p.enabled)} empty="Belum ada target aktif."
          columns={[
            { key: "name", label: "Target" },
            { key: "segment", label: "Segmen", render: (r) => segs[r.segment]?.label || r.segment },
            { key: "status", label: "Status", render: (r) => <Level size="sm" level={segs[r.segment]?.targets?.find((x) => x.name === r.name)?.level || "unknown"} /> },
            { key: "avg", label: "Avg", align: "right", render: (r) => r.last?.rtt_avg != null ? `${r.last.rtt_avg} ms` : "—" },
            { key: "max", label: "Max", align: "right", render: (r) => r.last?.rtt_max != null ? `${r.last.rtt_max} ms` : "—" },
            { key: "jit", label: "Jitter", align: "right", render: (r) => r.last?.jitter_ms != null ? `${r.last.jitter_ms} ms` : "—" },
            { key: "loss", label: "Loss", align: "right", render: (r) => r.last?.loss_pct != null ? `${r.last.loss_pct}%` : "—" },
            { key: "day", label: "Avg 24 jam", align: "right", render: (r) => r.day?.rtt_avg != null ? `${r.day.rtt_avg} ms` : "—" },
            { key: "at", label: "Waktu", render: (r) => fmtDate(r.last?.checked_at) },
          ]} />
      </Panel>

      <Panel title="Tes laptop terbaru (24 jam)" action={<Btn size="sm" variant="ghost" onClick={() => goTo("client")}>Semua laporan</Btn>}>
        <Table rows={c.latest} empty="Belum ada laporan. Minta user HO membuka /dashboard/ebs-check atau jalankan agen PowerShell."
          columns={[
            { key: "created_at", label: "Waktu", render: (r) => fmtDate(r.created_at) },
            { key: "who", label: "User / Laptop", render: (r) => r.hostname || r.reported_by },
            { key: "source", label: "Sumber" },
            { key: "ebs_condition", label: "Kondisi EBS" },
            { key: "ebs_rtt_avg", label: "RTT", align: "right", render: (r) => r.ebs_rtt_avg != null ? `${r.ebs_rtt_avg} ms` : "—" },
            { key: "verdict", label: "Verdict", render: (r) => <Level size="sm" level={VERDICT_LABEL[r.verdict]?.level} label={VERDICT_LABEL[r.verdict]?.text} /> },
            { key: "codes", label: "Kode", render: (r) => r.codes.join(", ") || "—" },
          ]} />
      </Panel>
    </>
  );
}
