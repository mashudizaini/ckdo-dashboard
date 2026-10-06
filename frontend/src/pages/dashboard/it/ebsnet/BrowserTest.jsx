/**
 * In-browser connection test from an HO laptop — the dashboard backend sits
 * on the Plant LAN beside EBS, so every request here crosses the same
 * HO LAN -> tunnel -> Plant path EBS traffic does. Measures what Oracle's
 * EBS Network Test measures (round-trip time and data rate) plus jitter,
 * loss, upload rate and a small CPU benchmark, then files a laptop report.
 *
 * Used twice: inside IT > Oracle EBS Network Monitoring, and standalone at
 * /dashboard/ebs-check for any employee (see pages/EbsConnectionCheck.jsx).
 */
import { useEffect, useState } from "react";
import { Play, Loader2, Send } from "lucide-react";
import { ebsNetClientApi } from "@/api/dashboard";
import { Btn, Field, Level, Note, Stat, inputStyle, errText, probeLevel, VERDICT_LABEL } from "./ui";

const PING_COUNT = 30;
const DEFAULT_T = { latency_warn: 50, latency_crit: 100, jitter_warn: 10, jitter_crit: 30, loss_warn: 0.1, loss_crit: 2 };

function stats(rtts, attempts) {
  const ok = rtts.length;
  const out = { samples: attempts, ok_count: ok, loss_pct: attempts ? +(((attempts - ok) * 100) / attempts).toFixed(1) : null };
  if (ok) {
    const sorted = [...rtts].sort((a, b) => a - b);
    out.rtt_min = +sorted[0].toFixed(1);
    out.rtt_max = +sorted[ok - 1].toFixed(1);
    out.rtt_avg = +(rtts.reduce((a, b) => a + b, 0) / ok).toFixed(1);
    out.rtt_p95 = +sorted[Math.min(ok - 1, Math.floor(ok * 0.95))].toFixed(1);
    let d = 0;
    for (let i = 1; i < ok; i++) d += Math.abs(rtts[i] - rtts[i - 1]);
    out.jitter_ms = ok > 1 ? +(d / (ok - 1)).toFixed(1) : 0;
  }
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function randomBlob(bytes) {
  const buf = new Uint8Array(bytes);
  for (let i = 0; i < bytes; i += 65536) crypto.getRandomValues(buf.subarray(i, Math.min(i + 65536, bytes)));
  return new Blob([buf]);
}

function cpuBenchmark() {
  // Fixed workload: the time is comparable between laptops and spikes when
  // the laptop is busy (antivirus scan, Teams, many tabs).
  const start = performance.now();
  let x = 0;
  for (let i = 0; i < 3_000_000; i++) x += Math.sqrt(i) * Math.sin(i);
  return { ms: +(performance.now() - start).toFixed(0), _: x > 0 };
}

function imageProbe(url, samples = 5) {
  // Works cross-origin without CORS; onerror still means a round trip happened
  // (the server answered with something that is not an image).
  const one = () => new Promise((resolve) => {
    const img = new Image();
    const t0 = performance.now();
    const done = (ok) => resolve({ ok, ms: performance.now() - t0 });
    const timer = setTimeout(() => done(false), 8000);
    img.onload = () => { clearTimeout(timer); done(true); };
    img.onerror = () => { clearTimeout(timer); done(performance.now() - t0 < 7900); };
    img.src = `${url}${url.includes("?") ? "&" : "?"}_=${Date.now()}${Math.random()}`;
  });
  return (async () => {
    const rtts = [];
    for (let i = 0; i < samples; i++) {
      const r = await one();
      if (r.ok) rtts.push(r.ms);
      await sleep(150);
    }
    return stats(rtts, samples);
  })();
}

export default function BrowserTest({ onSubmitted, compact = false }) {
  const [cfg, setCfg] = useState({ browser_probe_url: "", thresholds: DEFAULT_T });
  const [form, setForm] = useState({ condition: "Normal", connection: "", hostname: "", note: "" });
  const [phase, setPhase] = useState("");
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { ebsNetClientApi.config().then((c) => setCfg({ ...c, thresholds: { ...DEFAULT_T, ...(c.thresholds || {}) } })).catch(() => {}); }, []);

  const run = async () => {
    setRunning(true); setResult(null); setSubmitted(null);
    try {
      setPhase("Pemanasan koneksi…");
      for (let i = 0; i < 2; i++) { try { await ebsNetClientApi.ping(); } catch (_) {} }

      const rtts = [];
      for (let i = 0; i < PING_COUNT; i++) {
        setPhase(`Mengukur latency ${i + 1}/${PING_COUNT}…`);
        const t0 = performance.now();
        try { await ebsNetClientApi.ping(); rtts.push(performance.now() - t0); } catch (_) {}
        await sleep(100);
      }
      const latency = stats(rtts, PING_COUNT);

      setPhase("Mengukur kecepatan download…");
      let down = null;
      for (const size of [1_000_000, 4_000_000]) {
        const t0 = performance.now();
        const buf = await ebsNetClientApi.download(size);
        const ms = performance.now() - t0;
        down = +((buf.byteLength * 8) / ms / 1000).toFixed(2);
        if (ms > 4000) break;
      }

      setPhase("Mengukur kecepatan upload…");
      const blob = randomBlob(2_000_000);
      const t1 = performance.now();
      await ebsNetClientApi.upload(blob);
      const up = +((blob.size * 8) / (performance.now() - t1) / 1000).toFixed(2);

      let ebsProbe = null;
      if (cfg.browser_probe_url) {
        setPhase("Probe langsung ke web EBS…");
        try { ebsProbe = await imageProbe(cfg.browser_probe_url); } catch (_) {}
      }

      setPhase("Benchmark CPU laptop…");
      const bench = cpuBenchmark();
      const conn = navigator.connection || {};
      setResult({
        latency, down_mbps: down, up_mbps: up, ebs_probe: ebsProbe,
        device: {
          cpu_bench_ms: bench.ms, cores: navigator.hardwareConcurrency || null,
          device_memory_gb: navigator.deviceMemory || null,
          net_effective_type: conn.effectiveType || null, net_downlink_mbps: conn.downlink ?? null, net_rtt_ms: conn.rtt ?? null,
          screen: `${window.screen.width}x${window.screen.height}`,
        },
        user_agent: navigator.userAgent,
        measured_at: new Date().toISOString(),
      });
      setPhase("");
    } catch (e) {
      setPhase(`Tes gagal: ${errText(e)}`);
    } finally {
      setRunning(false);
    }
  };

  const submit = async () => {
    if (!result) return;
    setSubmitting(true);
    try {
      const r = await ebsNetClientApi.report({ ...result, ...form, connection: form.connection || null });
      setSubmitted(r);
      onSubmitted?.(r);
    } catch (e) {
      alert(errText(e, "Gagal mengirim hasil"));
    } finally {
      setSubmitting(false);
    }
  };

  const t = cfg.thresholds;
  const lat = result?.latency;
  const latLevel = lat ? probeLevel(lat, t) : null;

  return (
    <div className="space-y-4">
      <div className={`grid gap-3 ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"}`}>
        <Field label="Kondisi EBS saat ini">
          <select style={inputStyle} value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })}>
            <option value="Normal">Normal</option>
            <option value="Slow">Lambat</option>
            <option value="Hang">Hang / tidak merespons</option>
            <option value="Restart">Harus restart browser</option>
          </select>
        </Field>
        <Field label="Koneksi laptop">
          <select style={inputStyle} value={form.connection} onChange={(e) => setForm({ ...form, connection: e.target.value })}>
            <option value="">Tidak tahu</option>
            <option value="LAN">Kabel LAN</option>
            <option value="Wi-Fi">Wi-Fi</option>
            <option value="VPN">VPN (FortiClient)</option>
          </select>
        </Field>
        <Field label="Nama laptop (opsional)">
          <input style={inputStyle} value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} placeholder="mis. HO-ACC-01" />
        </Field>
        <Field label="Modul / transaksi EBS (opsional)">
          <input style={inputStyle} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="mis. AP Invoice Workbench" />
        </Field>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <Btn variant="primary" icon={running ? Loader2 : Play} spin={running} disabled={running} onClick={run}>
          {running ? "Sedang mengetes…" : result ? "Ulangi Tes" : "Mulai Tes (±20 detik)"}
        </Btn>
        {phase && <span style={{ fontSize: 12, color: "#64748b" }}>{phase}</span>}
      </div>

      {result && (
        <>
          <div className="flex gap-2.5 flex-wrap">
            <Stat label="RTT rata-rata" value={lat.rtt_avg} unit="ms" level={latLevel} />
            <Stat label="RTT p95 / max" value={lat.rtt_p95 != null ? `${lat.rtt_p95} / ${lat.rtt_max}` : null} unit="ms" />
            <Stat label="Jitter" value={lat.jitter_ms} unit="ms"
              level={lat.jitter_ms >= t.jitter_crit ? "crit" : lat.jitter_ms >= t.jitter_warn ? "warn" : "ok"} />
            <Stat label="Request gagal" value={lat.loss_pct} unit="%"
              level={lat.loss_pct >= t.loss_crit ? "crit" : lat.loss_pct >= t.loss_warn ? "warn" : "ok"} />
            <Stat label="Download" value={result.down_mbps} unit="Mbps" />
            <Stat label="Upload" value={result.up_mbps} unit="Mbps" />
            <Stat label="CPU benchmark" value={result.device.cpu_bench_ms} unit="ms" hint="makin kecil makin baik" />
            {result.ebs_probe && <Stat label="Web EBS langsung" value={result.ebs_probe.rtt_avg} unit="ms" />}
          </div>
          <p style={{ fontSize: 11, color: "#94a3b8" }}>
            RTT diukur dari browser ke server dashboard di Plant (jalur yang sama dengan EBS), termasuk ±2–5 ms waktu proses server.
            Untuk Forms EBS, stabilitas (jitter &amp; loss) lebih menentukan daripada kecepatan download.
          </p>
          {!submitted ? (
            <Btn icon={submitting ? Loader2 : Send} spin={submitting} disabled={submitting} onClick={submit}>
              {submitting ? "Mengirim…" : "Kirim hasil ke tim IT"}
            </Btn>
          ) : (
            <Note tone={submitted.verdict === "OK" ? "info" : "warn"}>
              <div className="flex items-center gap-2 mb-1">
                <Level level={VERDICT_LABEL[submitted.verdict]?.level} label={VERDICT_LABEL[submitted.verdict]?.text} />
                <span style={{ fontWeight: 700 }}>Terkirim — laporan #{submitted.id}</span>
              </div>
              {submitted.verdict_text}
              {submitted.codes?.length > 0 && <div style={{ marginTop: 4 }}>Indikasi: {submitted.codes.join(", ")}</div>}
            </Note>
          )}
        </>
      )}
    </div>
  );
}
