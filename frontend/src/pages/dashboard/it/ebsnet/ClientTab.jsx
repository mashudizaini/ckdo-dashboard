import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Upload, Loader2, Trash2, Copy, X } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import BrowserTest from "./BrowserTest";
import { Btn, Field, Level, Note, Panel, Stat, Table, fmtDate, errText, inputStyle, VERDICT_LABEL } from "./ui";

function AgentPanel({ onUploaded }) {
  const [opt, setOpt] = useState({ count: 100, label: "", valid_days: 14 });
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const download = async () => {
    setBusy(true);
    try {
      const text = await ebsNetApi.agentScript({ ...opt, count: Number(opt.count) || 100, valid_days: Number(opt.valid_days) || 14, base_url: window.location.origin });
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url; a.download = "EBS_HO_Diagnostic.ps1"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { alert(errText(e, "Gagal membuat script")); } finally { setBusy(false); }
  };

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const json = JSON.parse((await file.text()).replace(/^﻿/, ""));
      const r = await ebsNetApi.uploadReport(json);
      alert(`Laporan #${r.id} tersimpan — ${r.verdict_text}`);
      onUploaded?.();
    } catch (e) { alert(errText(e, "File bukan summary.json yang valid")); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const cmd = "powershell -ExecutionPolicy Bypass -File .\\EBS_HO_Diagnostic.ps1";

  return (
    <Panel title="Agen PowerShell (diagnosis mendalam laptop)"
      subtitle="Versi 2 dari script baseline: ping gateway & EBS, jitter/p95, MTU path, TCP+HTTP ke EBS, Wi-Fi, proxy, Java, CPU/RAM — hasil terkirim otomatis">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
        <Field label="Jumlah ping" hint="100 = ±25 detik per target; 1000 untuk gangguan intermiten">
          <input type="number" style={inputStyle} value={opt.count} onChange={(e) => setOpt({ ...opt, count: e.target.value })} />
        </Field>
        <Field label="Label (mis. nama user / lantai)">
          <input style={inputStyle} value={opt.label} onChange={(e) => setOpt({ ...opt, label: e.target.value })} />
        </Field>
        <Field label="Token berlaku (hari)">
          <input type="number" style={inputStyle} value={opt.valid_days} onChange={(e) => setOpt({ ...opt, valid_days: e.target.value })} />
        </Field>
        <div className="flex items-end gap-2">
          <Btn variant="primary" icon={busy ? Loader2 : Download} spin={busy} disabled={busy} onClick={download}>Unduh script</Btn>
        </div>
      </div>
      <Note>
        <ol style={{ paddingLeft: 16, listStyle: "decimal", lineHeight: 1.7 }}>
          <li>Salin <code>EBS_HO_Diagnostic.ps1</code> ke laptop HO yang bermasalah — <b>jalankan saat EBS sedang lambat, jangan tutup browser EBS dulu</b>.</li>
          <li>Buka PowerShell (tidak perlu Administrator) di folder file, jalankan:
            <span className="inline-flex items-center gap-1 ml-1">
              <code style={{ background: "#fff", padding: "1px 6px", borderRadius: 4 }}>{cmd}</code>
              <button type="button" title="Salin" onClick={() => navigator.clipboard?.writeText(cmd)}><Copy size={12} /></button>
            </span>
          </li>
          <li>Opsi: <code>-Pathping</code> (tambah ±5 menit), <code>-Count 1000</code>, <code>-Condition Slow</code>, <code>-NoUpload</code>.</li>
          <li>Hasil terkirim ke tabel di bawah. Folder + zip lengkap tetap tersimpan di Desktop user. Kalau upload gagal (sertifikat / jaringan), upload <code>summary.json</code> di sini:</li>
        </ol>
        <div className="mt-2">
          <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
          <Btn size="sm" icon={uploading ? Loader2 : Upload} spin={uploading} disabled={uploading} onClick={() => fileRef.current?.click()}>Upload summary.json</Btn>
        </div>
      </Note>
    </Panel>
  );
}

function ReportDetail({ id, onClose, onDeleted }) {
  const [r, setR] = useState(null);
  useEffect(() => { ebsNetApi.getReport(id).then(setR).catch((e) => alert(errText(e))); }, [id]);
  if (!r) return null;
  const d = r.detail || {};
  const del = async () => {
    if (!confirm("Hapus laporan ini?")) return;
    try { await ebsNetApi.deleteReport(id); onDeleted(); } catch (e) { alert(errText(e)); }
  };
  const isAgent = r.source === "agent";
  return (
    <Panel title={`Laporan #${r.id} — ${r.hostname || r.reported_by || "?"}`} subtitle={`${fmtDate(r.created_at)} · sumber ${r.source} · kondisi EBS: ${r.ebs_condition || "—"}${r.note ? ` · ${r.note}` : ""}`}
      action={<><Btn size="sm" variant="ghost" icon={Trash2} onClick={del}>Hapus</Btn><Btn size="sm" icon={X} onClick={onClose}>Tutup</Btn></>}>
      <div className="space-y-3">
        <Note tone={r.verdict === "OK" ? "info" : "warn"}>
          <div className="flex items-center gap-2 mb-1"><Level level={VERDICT_LABEL[r.verdict]?.level} label={VERDICT_LABEL[r.verdict]?.text} /></div>
          {r.verdict_text}
          {r.codes.length > 0 && <div style={{ marginTop: 4 }}>{r.codes.map((c) => `${c} ${r.code_labels?.[c] || ""}`).join(" · ")}</div>}
        </Note>
        <div className="flex gap-2.5 flex-wrap">
          {isAgent && <Stat label="Gateway avg / loss" value={r.gw_rtt_avg != null ? `${r.gw_rtt_avg} / ${r.gw_loss_pct}%` : null} unit="ms" />}
          <Stat label="EBS avg / max" value={r.ebs_rtt_avg != null ? `${r.ebs_rtt_avg} / ${r.ebs_rtt_max ?? "—"}` : null} unit="ms" />
          <Stat label="EBS jitter" value={r.ebs_jitter_ms} unit="ms" />
          <Stat label="EBS loss" value={r.ebs_loss_pct} unit="%" />
          <Stat label={isAgent ? "HTTP EBS" : "Web EBS langsung"} value={r.http_ttfb_ms} unit="ms" />
          {!isAgent && <Stat label="Down / Up" value={r.down_mbps != null ? `${r.down_mbps} / ${r.up_mbps}` : null} unit="Mbps" />}
          {isAgent && <Stat label="Path MTU" value={r.path_mtu} />}
          <Stat label="Koneksi" value={r.connection} />
          {r.wifi_signal != null && <Stat label="Sinyal Wi-Fi" value={r.wifi_signal} unit="%" />}
          {isAgent && <Stat label="CPU / RAM bebas" value={r.cpu_pct != null ? `${r.cpu_pct} / ${r.ram_avail_pct}` : null} unit="%" />}
        </div>
        {isAgent && (
          <div className="grid md:grid-cols-2 gap-3" style={{ fontSize: 11.5, color: "#334155" }}>
            <div>
              <p style={{ fontWeight: 700, marginBottom: 4 }}>Sistem</p>
              <p>{d.system?.manufacturer} {d.system?.model} · {d.system?.cpu} · RAM {d.system?.ram_gb} GB</p>
              <p>{d.system?.os} · uptime {d.system?.uptime_hours} jam</p>
              <p style={{ whiteSpace: "pre-wrap" }}>{d.system?.power_plan}</p>
              <p>Browser default: {d.client?.browser || "—"} · Java: {(d.client?.java || []).join("; ") || "tidak terdeteksi"}</p>
              <p>Koneksi TCP aktif ke EBS: {d.client?.ebs_established ?? "—"}</p>
            </div>
            <div>
              <p style={{ fontWeight: 700, marginBottom: 4 }}>Jaringan</p>
              <p>{d.network?.adapter} · {d.network?.link_speed} · gateway {d.network?.gateway}</p>
              {d.network?.wifi && <p>Wi-Fi {d.network.wifi.ssid} · {d.network.wifi.radio} · ch {d.network.wifi.channel} · {d.network.wifi.rx_mbps} Mbps · BSSID {d.network.wifi.bssid}</p>}
              <p>Proxy: {d.network?.proxy?.enabled ? `${d.network.proxy.server || ""} ${d.network.proxy.pac || ""}` : "tidak aktif"}</p>
              <p>DNS resolve: {d.dns_ms != null ? `${d.dns_ms} ms` : "—"} · hop tracert: {d.tracert_hops}</p>
              <p>TCP ke EBS: {(d.tcp_ebs || []).map((t) => `:${t.port} ${t.avg ?? "gagal"} ms (loss ${t.loss_pct}%)`).join(" · ") || "—"}</p>
              <p>Pembanding: {(d.ping_compare || []).map((p) => `${p.host} ${p.avg ?? "—"} ms / ${p.loss_pct}%`).join(" · ") || "—"}</p>
            </div>
            <div className="md:col-span-2">
              <p style={{ fontWeight: 700, marginBottom: 4 }}>Proses teratas</p>
              <p>CPU: {(d.resources?.top_cpu || []).map((p) => `${p.name} ${p.cpu_pct}%`).join(" · ")}</p>
              <p>RAM: {(d.resources?.top_mem || []).map((p) => `${p.name} ${p.mem_mb} MB`).join(" · ")}</p>
            </div>
            {d.tracert && <pre className="md:col-span-2" style={{ background: "#0f172a", color: "#e2e8f0", fontSize: 10.5, padding: 10, borderRadius: 8, maxHeight: 220, overflow: "auto" }}>{d.tracert}</pre>}
          </div>
        )}
        {!isAgent && d.device && (
          <p style={{ fontSize: 11.5, color: "#334155" }}>
            CPU benchmark {d.device.cpu_bench_ms} ms · {d.device.cores} core · RAM≥{d.device.device_memory_gb ?? "?"} GB · koneksi browser {d.device.net_effective_type || "?"} · {d.user_agent}
          </p>
        )}
      </div>
    </Panel>
  );
}

function HourMatrix({ reports }) {
  // Section 9 of the script: test at 08:00 / 11:00 / 14:00 / 15:00-16:00.
  const rows = useMemo(() => {
    const by = {};
    reports.forEach((r) => {
      const h = new Date(r.created_at).getHours();
      (by[h] ||= []).push(r);
    });
    return Object.keys(by).map(Number).sort((a, b) => a - b).map((h) => {
      const list = by[h];
      const rtts = list.map((r) => r.ebs_rtt_avg).filter((v) => v != null);
      return {
        id: h, hour: `${String(h).padStart(2, "0")}:00`, count: list.length,
        avg: rtts.length ? (rtts.reduce((a, b) => a + b, 0) / rtts.length).toFixed(1) : "—",
        max: rtts.length ? Math.max(...rtts).toFixed(1) : "—",
        slow: list.filter((r) => ["Slow", "Hang", "Restart"].includes(r.ebs_condition)).length,
        issues: list.filter((r) => r.verdict !== "OK").length,
      };
    });
  }, [reports]);
  return (
    <Table rows={rows} empty="Belum ada laporan."
      columns={[{ key: "hour", label: "Jam" }, { key: "count", label: "Tes", align: "right" },
        { key: "avg", label: "RTT avg (ms)", align: "right" }, { key: "max", label: "RTT avg tertinggi", align: "right" },
        { key: "slow", label: "User lapor lambat", align: "right" }, { key: "issues", label: "Verdict ≠ OK", align: "right" }]} />
  );
}

export default function ClientTab() {
  const [hours, setHours] = useState(168);
  const [reports, setReports] = useState([]);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try { setReports(await ebsNetApi.listReports(hours)); } catch (e) { alert(errText(e)); }
  }, [hours]);
  useEffect(() => { load(); }, [load]);

  const link = `${window.location.origin}/dashboard/ebs-check`;

  return (
    <>
      <Panel title="Tes koneksi dari browser laptop ini"
        subtitle="Setara EBS Network Test (RTT + data rate) melalui jalur HO → tunnel → Plant">
        <Note>
          Link untuk user HO (siapa pun yang bisa login dashboard, tanpa akses IT):{" "}
          <code style={{ background: "#fff", padding: "1px 6px", borderRadius: 4 }}>{link}</code>{" "}
          <button type="button" title="Salin" onClick={() => navigator.clipboard?.writeText(link)}><Copy size={12} /></button>
        </Note>
        <div className="h-4" />
        <BrowserTest onSubmitted={load} />
      </Panel>

      <AgentPanel onUploaded={load} />

      {openId && <ReportDetail id={openId} onClose={() => setOpenId(null)} onDeleted={() => { setOpenId(null); load(); }} />}

      <Panel title="Laporan laptop" subtitle="Klik baris untuk detail · Case D terdeteksi juga dengan membandingkan RTT laptop ini terhadap median laptop lain 24 jam"
        action={<select style={{ ...inputStyle, width: "auto" }} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          <option value={24}>24 jam</option><option value={168}>7 hari</option><option value={720}>30 hari</option>
        </select>}>
        <Table rows={reports} onRowClick={(r) => setOpenId(r.id)} empty="Belum ada laporan."
          columns={[
            { key: "created_at", label: "Waktu", render: (r) => fmtDate(r.created_at) },
            { key: "who", label: "Laptop / User", render: (r) => <>{r.hostname || "—"}<div style={{ fontSize: 10.5, color: "#94a3b8" }}>{r.reported_by}</div></> },
            { key: "source", label: "Sumber" },
            { key: "connection", label: "Koneksi" },
            { key: "ebs_condition", label: "Kondisi EBS" },
            { key: "gw", label: "Gateway", align: "right", render: (r) => r.gw_rtt_avg != null ? `${r.gw_rtt_avg} ms` : "—" },
            { key: "ebs", label: "EBS avg", align: "right", render: (r) => r.ebs_rtt_avg != null ? `${r.ebs_rtt_avg} ms` : "—" },
            { key: "jit", label: "Jitter", align: "right", render: (r) => r.ebs_jitter_ms != null ? `${r.ebs_jitter_ms} ms` : "—" },
            { key: "loss", label: "Loss", align: "right", render: (r) => r.ebs_loss_pct != null ? `${r.ebs_loss_pct}%` : "—" },
            { key: "verdict", label: "Verdict", render: (r) => <Level size="sm" level={VERDICT_LABEL[r.verdict]?.level} label={VERDICT_LABEL[r.verdict]?.text} /> },
            { key: "codes", label: "Kode", render: (r) => r.codes.join(", ") || "—" },
          ]} />
      </Panel>

      <Panel title="Matriks waktu tes" subtitle="Target minimal 4× sehari: 08:00, 11:00, 14:00, 15:00–16:00 — pola per jam menunjukkan congestion jam sibuk">
        <HourMatrix reports={reports} />
      </Panel>
    </>
  );
}
