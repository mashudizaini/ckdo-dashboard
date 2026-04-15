/**
 * CoretaxDownloader.jsx
 * Bulk download eBupot BPU dari Coretax DJP.
 *
 * Flow:
 *   1. User isi form → klik "Mulai"
 *   2. Backend buka browser, navigasi ke halaman login Coretax, screenshot CAPTCHA
 *   3. Status jadi "waiting_captcha" → komponen ini tampilkan gambar + input kode
 *   4. User isi kode CAPTCHA → klik "Submit CAPTCHA"
 *   5. Backend lanjut: isi form, login, pilih NPWP, download semua PDF, buat ZIP
 *   6. Status "done" → tombol Download ZIP muncul
 */

import { useState, useEffect, useRef } from "react";
import {
  FileText, LogIn, CheckCircle2,
  XCircle, Loader2, Archive, Trash2, AlertCircle, ShieldCheck
} from "lucide-react";

const BASE_URL = "/api/coretax";

const MASA_PAJAK_OPTIONS = [
  "Januari 2026","Februari 2026","Maret 2026","April 2026",
  "Mei 2026","Juni 2026","Juli 2026","Agustus 2026",
  "September 2026","Oktober 2026","November 2026","Desember 2026",
  "Januari 2025","Februari 2025","Maret 2025","April 2025",
  "Mei 2025","Juni 2025","Juli 2025","Agustus 2025",
  "September 2025","Oktober 2025","November 2025","Desember 2025",
];

const STATUS_COLOR = {
  pending:         { bg: "rgba(251,191,36,0.1)",  text: "#fbbf24", border: "rgba(251,191,36,0.3)"  },
  running:         { bg: "rgba(99,102,241,0.1)",  text: "#818cf8", border: "rgba(99,102,241,0.3)"  },
  waiting_captcha: { bg: "rgba(251,146,60,0.1)",  text: "#fb923c", border: "rgba(251,146,60,0.3)"  },
  done:            { bg: "rgba(52,211,153,0.1)",  text: "#34d399", border: "rgba(52,211,153,0.3)"  },
  error:           { bg: "rgba(248,113,113,0.1)", text: "#f87171", border: "rgba(248,113,113,0.3)" },
};

const STATUS_ICON = {
  pending:         <Loader2 size={14} className="animate-spin" />,
  running:         <Loader2 size={14} className="animate-spin" />,
  waiting_captcha: <ShieldCheck size={14} />,
  done:            <CheckCircle2 size={14} />,
  error:           <XCircle size={14} />,
};

const STATUS_LABEL = {
  pending:         "PENDING",
  running:         "BERJALAN",
  waiting_captcha: "TUNGGU CAPTCHA",
  done:            "SELESAI",
  error:           "ERROR",
};

const S = {
  page: { padding: "28px 32px", color: "#e2e8f0", fontFamily: "'DM Sans','Segoe UI',sans-serif", maxWidth: 860 },
  header: { display: "flex", alignItems: "center", gap: 12, marginBottom: 28 },
  iconBox: { width: 40, height: 40, borderRadius: 10, background: "linear-gradient(135deg,#6366f1,#8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" },
  title:    { fontSize: 20, fontWeight: 700, color: "#f1f5f9", margin: 0 },
  subtitle: { fontSize: 13, color: "#64748b", margin: 0 },
  card: { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 14, padding: "24px 28px", marginBottom: 20 },
  cardTitle: { fontSize: 13, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 18 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  label: { fontSize: 12, color: "#94a3b8", marginBottom: 6, display: "block", fontWeight: 500 },
  input: { width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#f1f5f9", fontSize: 14, outline: "none", boxSizing: "border-box", transition: "border-color 0.2s" },
  select: { width: "100%", background: "#1e1e2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#f1f5f9", fontSize: 14, outline: "none", boxSizing: "border-box", cursor: "pointer" },
  btnPrimary: { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#6366f1,#8b5cf6)", border: "none", borderRadius: 9, color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer" },
  btnOrange:  { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#f97316,#fb923c)", border: "none", borderRadius: 9, color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer" },
  btnDanger:  { display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", borderRadius: 8, color: "#f87171", fontSize: 13, cursor: "pointer" },
  btnDownload:{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.25)", borderRadius: 8, color: "#34d399", fontSize: 13, cursor: "pointer" },
  progressBar: { height: 6, borderRadius: 99, background: "rgba(255,255,255,0.07)", overflow: "hidden", marginTop: 10 },
  progressFill: (pct) => ({ height: "100%", width: `${pct}%`, borderRadius: 99, background: "linear-gradient(90deg,#6366f1,#8b5cf6)", transition: "width 0.5s ease" }),
  statusBadge: (status) => ({ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 99, fontSize: 12, fontWeight: 600, background: STATUS_COLOR[status]?.bg, color: STATUS_COLOR[status]?.text, border: `1px solid ${STATUS_COLOR[status]?.border}` }),
  logBox: { background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8, padding: "12px 16px", fontSize: 12, color: "#64748b", fontFamily: "'Fira Code','Courier New',monospace", minHeight: 44, marginTop: 10, lineHeight: 1.7, maxHeight: 160, overflowY: "auto" },
  statRow: { display: "flex", gap: 20, marginTop: 14 },
  statItem: { flex: 1, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: "14px 16px", textAlign: "center" },
  statNum:  { fontSize: 26, fontWeight: 700, color: "#f1f5f9", lineHeight: 1 },
  statLabel:{ fontSize: 11, color: "#475569", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.06em" },
  warning: { display: "flex", gap: 10, padding: "12px 16px", background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: 10, fontSize: 13, color: "#fbbf24", marginBottom: 20 },
};

export default function CoretaxDownloader() {
  const [form, setForm] = useState({
    username:   "",
    password:   "",
    npwp:       "0741325344011000",
    masa_pajak: "Maret 2026",
    max_pages:  "",
  });
  const [job,        setJob]        = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [logs,       setLogs]       = useState([]);
  const [captchaCode, setCaptchaCode] = useState("");
  const [captchaImg,  setCaptchaImg]  = useState(null);   // object URL
  const [captchaTs,   setCaptchaTs]   = useState(0);      // timestamp untuk force-reload
  const [debugImgs,   setDebugImgs]   = useState({});     // filename → object URL
  const pollRef  = useRef(null);
  const logRef   = useRef(null);

  // Helper: muat satu screenshot sebagai object URL
  const loadDebugImg = async (jobId, filename) => {
    try {
      const res = await fetch(`${BASE_URL}/debug/screenshot/${jobId}/${filename}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return null;
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    } catch (_) { return null; }
  };

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  useEffect(() => () => {
    clearInterval(pollRef.current);
    if (captchaImg) URL.revokeObjectURL(captchaImg);
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const addLog = (msg) =>
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString("id-ID")}] ${msg}`]);

  // ── Polling status ──────────────────────────────────────────────────────────
  const startPolling = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BASE_URL}/status/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();
        setJob(data);
        if (data.message) addLog(data.message);

        // Kalau masuk waiting_captcha, muat gambar CAPTCHA
        if (data.status === "waiting_captcha") {
          setCaptchaTs(Date.now());   // trigger re-fetch image
        }

        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          setLoading(false);
        }
      } catch (_) {}
    }, 2000);
  };

  // ── Load gambar CAPTCHA saat status waiting_captcha ─────────────────────────
  useEffect(() => {
    if (!job?.job_id || job.status !== "waiting_captcha" || captchaTs === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${BASE_URL}/captcha-image/${job.job_id}?t=${captchaTs}`,
          { cache: "no-store" }
        );
        if (!res.ok || cancelled) return;
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        setCaptchaImg((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, [captchaTs]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load screenshot debug saat status error ──────────────────────────────────
  useEffect(() => {
    if (!job?.job_id || job.status !== "error") return;
    let cancelled = false;
    const DEBUG_FILES = [
      "debug_login_fullpage.png",
      "debug_before_fill.png",
      "debug_form_filled.png",
      "debug_after_submit.png",
    ];
    (async () => {
      const results = {};
      for (const f of DEBUG_FILES) {
        if (cancelled) break;
        const url = await loadDebugImg(job.job_id, f);
        if (url) results[f] = url;
      }
      if (!cancelled) setDebugImgs(results);
    })();
    return () => { cancelled = true; };
  }, [job?.status]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Mulai job ────────────────────────────────────────────────────────────────
  const handleStart = async () => {
    if (!form.username || !form.password) {
      addLog("⚠ ID Pengguna dan Kata Sandi wajib diisi");
      return;
    }
    setLoading(true);
    setJob(null);
    setLogs([]);
    setCaptchaImg(null);
    setCaptchaCode("");
    setDebugImgs({});
    addLog("Mengirim permintaan ke server…");

    try {
      const body = {
        username:   form.username,
        password:   form.password,
        npwp:       form.npwp,
        masa_pajak: form.masa_pajak,
        ...(form.max_pages ? { max_pages: parseInt(form.max_pages) } : {}),
      };
      const res = await fetch(`${BASE_URL}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJob(data);
      addLog(`Job dimulai: ${data.job_id}`);
      startPolling(data.job_id);
    } catch (e) {
      addLog(`❌ Gagal memulai job: ${e.message}`);
      setLoading(false);
    }
  };

  // ── Submit kode CAPTCHA ──────────────────────────────────────────────────────
  const handleSubmitCaptcha = async () => {
    if (!captchaCode.trim()) { addLog("⚠ Kode CAPTCHA harus diisi"); return; }
    if (!job?.job_id) return;
    try {
      const res = await fetch(`${BASE_URL}/captcha/${job.job_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: captchaCode.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      addLog(`✓ CAPTCHA "${captchaCode}" dikirim, proses dilanjutkan…`);
      setCaptchaCode("");
    } catch (e) {
      addLog(`❌ Gagal kirim CAPTCHA: ${e.message}`);
    }
  };

  // ── Refresh gambar CAPTCHA ───────────────────────────────────────────────────
  const handleRefreshCaptcha = () => setCaptchaTs(Date.now());

  // ── Download ZIP ─────────────────────────────────────────────────────────────
  const handleDownloadZip = () => {
    if (job?.job_id) window.open(`${BASE_URL}/download/${job.job_id}`, "_blank");
  };

  // ── Reset / hapus job ────────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!job?.job_id) return;
    clearInterval(pollRef.current);
    await fetch(`${BASE_URL}/job/${job.job_id}`, { method: "DELETE" }).catch(() => {});
    setJob(null);
    setLogs([]);
    setLoading(false);
    setCaptchaImg(null);
    setCaptchaCode("");
    setDebugImgs((prev) => {
      Object.values(prev).forEach((u) => URL.revokeObjectURL(u));
      return {};
    });
    addLog("Job dihapus");
  };

  const pct = job
    ? job.total > 0
      ? Math.round((job.downloaded / job.total) * 100)
      : job.status === "done" ? 100 : job.status === "running" ? 40 : 0
    : 0;

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <div style={S.iconBox}><FileText size={18} color="#fff" /></div>
        <div>
          <p style={S.title}>Coretax Downloader</p>
          <p style={S.subtitle}>Bulk download eBupot BPU — coretaxdjp.pajak.go.id</p>
        </div>
      </div>

      {/* Info alur */}
      <div style={S.warning}>
        <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          Alur: <strong>Isi form → Klik Mulai → Lihat gambar CAPTCHA → Isi kode → Submit</strong>.
          Proses download berjalan otomatis setelah CAPTCHA berhasil.
        </span>
      </div>

      {/* Form konfigurasi */}
      <div style={S.card}>
        <p style={S.cardTitle}>Konfigurasi Akun Coretax</p>
        <div style={S.grid2}>
          <div>
            <label style={S.label}>ID Pengguna (NPWP Pribadi / Login)</label>
            <input
              style={S.input} type="text" placeholder="Contoh: 720203670489T0001"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
          <div>
            <label style={S.label}>Kata Sandi</label>
            <input
              style={S.input} type="password" placeholder="••••••••"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
          <div>
            <label style={S.label}>NPWP Perusahaan (untuk switch akun)</label>
            <input
              style={S.input} type="text" placeholder="Contoh: 0741325344011000"
              value={form.npwp}
              onChange={(e) => setForm({ ...form, npwp: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
          <div>
            <label style={S.label}>Masa Pajak</label>
            <select style={S.select} value={form.masa_pajak}
              onChange={(e) => setForm({ ...form, masa_pajak: e.target.value })}>
              {MASA_PAJAK_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label}>
              Maks. Halaman <span style={{ color: "#475569" }}>(opsional, kosong = semua)</span>
            </label>
            <input
              style={S.input} type="number" placeholder="contoh: 5" min={1}
              value={form.max_pages}
              onChange={(e) => setForm({ ...form, max_pages: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
        </div>

        <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
          <button
            style={{ ...S.btnPrimary, opacity: loading ? 0.55 : 1 }}
            onClick={handleStart}
            disabled={loading}
          >
            {loading
              ? <><Loader2 size={15} className="animate-spin" /> Sedang Berjalan…</>
              : <><LogIn size={15} /> Mulai Download</>}
          </button>
          {job && (
            <button style={S.btnDanger} onClick={handleDelete}>
              <Trash2 size={14} /> Reset
            </button>
          )}
        </div>
      </div>

      {/* ── CAPTCHA Panel ──────────────────────────────────────────────────────── */}
      {job?.status === "waiting_captcha" && (
        <div style={{ ...S.card, border: "1px solid rgba(251,146,60,0.35)", background: "rgba(251,146,60,0.05)" }}>
          <p style={{ ...S.cardTitle, color: "#fb923c" }}>
            <ShieldCheck size={14} style={{ display: "inline", marginRight: 6 }} />
            Isi Kode CAPTCHA
          </p>

          <p style={{ fontSize: 13, color: "#94a3b8", marginBottom: 16 }}>
            Browser sudah membuka halaman login Coretax. Lihat gambar di bawah,
            ketik angka/huruf yang terlihat, lalu klik <strong style={{ color: "#fb923c" }}>Submit CAPTCHA</strong>.
          </p>

          {/* Gambar CAPTCHA */}
          <div style={{ marginBottom: 16 }}>
            {captchaImg ? (
              <img
                src={captchaImg}
                alt="CAPTCHA Coretax"
                style={{ maxWidth: "100%", borderRadius: 8, border: "1px solid rgba(255,255,255,0.12)" }}
              />
            ) : (
              <div style={{ padding: "24px", textAlign: "center", color: "#475569", fontSize: 13, background: "rgba(0,0,0,0.2)", borderRadius: 8 }}>
                <Loader2 size={18} className="animate-spin" style={{ display: "inline", marginRight: 6 }} />
                Memuat gambar CAPTCHA…
              </div>
            )}
          </div>

          {/* Input + tombol */}
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={S.label}>Kode CAPTCHA</label>
              <input
                style={{ ...S.input, fontSize: 18, letterSpacing: "0.2em", textAlign: "center" }}
                type="text"
                placeholder="Ketik kode di atas"
                value={captchaCode}
                onChange={(e) => setCaptchaCode(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmitCaptcha()}
                autoFocus
                onFocus={(e) => (e.target.style.borderColor = "#fb923c")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
              />
            </div>
            <button style={S.btnOrange} onClick={handleSubmitCaptcha}>
              <ShieldCheck size={15} /> Submit CAPTCHA
            </button>
            <button
              style={{ ...S.btnDanger, padding: "10px 14px" }}
              onClick={handleRefreshCaptcha}
              title="Muat ulang gambar CAPTCHA"
            >
              ↻ Refresh
            </button>
          </div>

          <p style={{ fontSize: 11, color: "#475569", marginTop: 10 }}>
            Tekan <kbd style={{ background: "rgba(255,255,255,0.1)", padding: "1px 5px", borderRadius: 3 }}>Enter</kbd> untuk submit.
            Jika gambar tidak muncul, tunggu 3–5 detik lalu klik Refresh.
          </p>
        </div>
      )}

      {/* ── Status & Progress ──────────────────────────────────────────────────── */}
      {job && job.status !== "waiting_captcha" && (
        <div style={S.card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <p style={{ ...S.cardTitle, marginBottom: 0 }}>Status Job</p>
            <span style={S.statusBadge(job.status)}>
              {STATUS_ICON[job.status]}
              {STATUS_LABEL[job.status] || job.status.toUpperCase()}
            </span>
          </div>

          <div style={S.statRow}>
            <div style={S.statItem}>
              <div style={{ ...S.statNum, color: "#34d399" }}>{job.downloaded}</div>
              <div style={S.statLabel}>Berhasil</div>
            </div>
            <div style={S.statItem}>
              <div style={{ ...S.statNum, color: "#f87171" }}>{job.failed}</div>
              <div style={S.statLabel}>Gagal</div>
            </div>
            <div style={S.statItem}>
              <div style={{ ...S.statNum, color: "#818cf8" }}>{pct}%</div>
              <div style={S.statLabel}>Progress</div>
            </div>
          </div>

          <div style={S.progressBar}>
            <div style={S.progressFill(pct)} />
          </div>

          <div style={S.logBox} ref={logRef}>
            {logs.length === 0
              ? <span style={{ color: "#334155" }}>Menunggu log…</span>
              : logs.map((l, i) => <div key={i}>{l}</div>)}
          </div>

          {/* Download ZIP */}
          {job.zip_ready && (
            <div style={{ marginTop: 16, display: "flex", gap: 10 }}>
              <button style={S.btnDownload} onClick={handleDownloadZip}>
                <Archive size={14} /> Download ZIP ({job.downloaded} file)
              </button>
            </div>
          )}

          {/* Debug screenshots saat error — ditampilkan inline */}
          {job.status === "error" && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600, marginBottom: 12 }}>
                Screenshot Browser (untuk mendiagnosis penyebab error):
              </div>

              {Object.keys(debugImgs).length === 0 && (
                <div style={{ fontSize: 12, color: "#475569", display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={13} className="animate-spin" /> Memuat screenshot debug…
                </div>
              )}

              {/* Tampilkan setiap screenshot sebagai gambar inline */}
              {[
                { key: "debug_login_fullpage.png", label: "Halaman Login (awal)" },
                { key: "debug_before_fill.png",   label: "Sebelum isi form" },
                { key: "debug_form_filled.png",    label: "Setelah form diisi" },
                { key: "debug_after_submit.png",   label: "Setelah submit (penyebab error)" },
              ].map(({ key, label }) =>
                debugImgs[key] ? (
                  <div key={key} style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontWeight: 600, color: "#94a3b8" }}>{label}</span>
                      <a href={debugImgs[key]} target="_blank" rel="noreferrer"
                        style={{ fontSize: 11, color: "#818cf8", textDecoration: "underline" }}>
                        buka di tab baru ↗
                      </a>
                    </div>
                    <img
                      src={debugImgs[key]}
                      alt={label}
                      style={{ width: "100%", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", display: "block" }}
                    />
                  </div>
                ) : null
              )}
            </div>
          )}
        </div>
      )}

      {/* Log sisa saat job belum ada */}
      {!job && logs.length > 0 && (
        <div style={S.card}>
          <div style={S.logBox} ref={logRef}>
            {logs.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}
    </div>
  );
}
