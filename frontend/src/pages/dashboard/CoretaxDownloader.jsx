/**
 * CoretaxDownloader.jsx
 * Bulk download eBupot BPU dari Coretax DJP.
 *
 * UX flow:
 *   Pertama kali pakai (atau cookie expired):
 *     → User login ke Coretax di Chrome seperti biasa
 *     → F12 → Network → copy Cookie header → paste di sini → Simpan & Mulai
 *   Selanjutnya (cookie masih valid):
 *     → Pilih masa pajak → klik Mulai Download (tanpa F12)
 */

import { useState, useEffect, useRef } from "react";
import {
  FileText, LogIn, CheckCircle2, XCircle, Loader2,
  Archive, Trash2, AlertCircle, ShieldCheck, Cookie,
  ChevronDown, ChevronUp, RefreshCw, Info
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
  page:      { padding: "28px 32px", color: "#e2e8f0", fontFamily: "'DM Sans','Segoe UI',sans-serif", maxWidth: 860 },
  header:    { display: "flex", alignItems: "center", gap: 12, marginBottom: 28 },
  iconBox:   { width: 40, height: 40, borderRadius: 10, background: "linear-gradient(135deg,#6366f1,#8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" },
  title:     { fontSize: 20, fontWeight: 700, color: "#f1f5f9", margin: 0 },
  subtitle:  { fontSize: 13, color: "#64748b", margin: 0 },
  card:      { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 14, padding: "24px 28px", marginBottom: 20 },
  cardTitle: { fontSize: 13, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 18 },
  grid2:     { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  label:     { fontSize: 12, color: "#94a3b8", marginBottom: 6, display: "block", fontWeight: 500 },
  input:     { width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#f1f5f9", fontSize: 14, outline: "none", boxSizing: "border-box" },
  textarea:  { width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#f1f5f9", fontSize: 12, outline: "none", boxSizing: "border-box", resize: "vertical", fontFamily: "'Fira Code','Courier New',monospace", lineHeight: 1.6 },
  select:    { width: "100%", background: "#1e1e2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px", color: "#f1f5f9", fontSize: 14, outline: "none", boxSizing: "border-box", cursor: "pointer" },
  btnPrimary:  { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#6366f1,#8b5cf6)", border: "none", borderRadius: 9, color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer" },
  btnGreen:    { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#059669,#10b981)", border: "none", borderRadius: 9, color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer" },
  btnOrange:   { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#f97316,#fb923c)", border: "none", borderRadius: 9, color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer" },
  btnSecondary:{ display: "flex", alignItems: "center", gap: 6, padding: "9px 16px", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, color: "#94a3b8", fontSize: 13, cursor: "pointer" },
  btnDanger:   { display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", borderRadius: 8, color: "#f87171", fontSize: 13, cursor: "pointer" },
  btnDownload: { display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.25)", borderRadius: 8, color: "#34d399", fontSize: 13, cursor: "pointer" },
  progressBar:  { height: 6, borderRadius: 99, background: "rgba(255,255,255,0.07)", overflow: "hidden", marginTop: 10 },
  progressFill: (pct) => ({ height: "100%", width: `${pct}%`, borderRadius: 99, background: "linear-gradient(90deg,#6366f1,#8b5cf6)", transition: "width 0.5s ease" }),
  statusBadge:  (s) => ({ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 99, fontSize: 12, fontWeight: 600, background: STATUS_COLOR[s]?.bg, color: STATUS_COLOR[s]?.text, border: `1px solid ${STATUS_COLOR[s]?.border}` }),
  logBox:  { background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8, padding: "12px 16px", fontSize: 12, color: "#64748b", fontFamily: "'Fira Code','Courier New',monospace", minHeight: 44, marginTop: 10, lineHeight: 1.7, maxHeight: 160, overflowY: "auto" },
  statRow: { display: "flex", gap: 20, marginTop: 14 },
  statItem:{ flex: 1, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: "14px 16px", textAlign: "center" },
  statNum: { fontSize: 26, fontWeight: 700, color: "#f1f5f9", lineHeight: 1 },
  statLabel:{ fontSize: 11, color: "#475569", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.06em" },
  stepItem: { display: "flex", gap: 10, marginBottom: 8, fontSize: 13, color: "#94a3b8", alignItems: "flex-start" },
  stepNum:  { minWidth: 22, height: 22, borderRadius: "50%", background: "rgba(99,102,241,0.25)", color: "#818cf8", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 },
};

export default function CoretaxDownloader() {
  // Modus UI: "ready" (cookie tersimpan) | "setup" (perlu paste cookie) | "login" (login otomatis)
  const [uiMode, setUiMode]       = useState("checking");  // checking | ready | setup | login
  const [savedAt, setSavedAt]     = useState(null);
  const [showSetup, setShowSetup] = useState(false);       // expand/collapse panel setup cookie
  const [cookieDraft, setCookieDraft] = useState("");      // textarea cookie baru
  const [savingCookie, setSavingCookie] = useState(false);

  const [form, setForm] = useState({
    npwp:       "0741325344011000",
    masa_pajak: "Maret 2026",
    max_pages:  "",
    username:   "",
    password:   "",
  });

  const [job,         setJob]         = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [logs,        setLogs]        = useState([]);
  const [captchaCode, setCaptchaCode] = useState("");
  const [captchaImg,  setCaptchaImg]  = useState(null);
  const [captchaTs,   setCaptchaTs]   = useState(0);
  const [debugImgs,   setDebugImgs]   = useState({});
  const pollRef = useRef(null);
  const logRef  = useRef(null);

  // ── Cek status cookie tersimpan saat komponen load ───────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/saved-cookie`);
        const data = await res.json();
        if (data.has_cookie) {
          setSavedAt(data.saved_at);
          setUiMode("ready");
        } else {
          setUiMode("setup");
        }
      } catch (_) {
        setUiMode("setup");
      }
    })();
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  useEffect(() => () => {
    clearInterval(pollRef.current);
    if (captchaImg) URL.revokeObjectURL(captchaImg);
  }, []);  // eslint-disable-line

  const addLog = (msg) =>
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString("id-ID")}] ${msg}`]);

  // ── Simpan cookie baru ke server ─────────────────────────────────────────────
  const handleSaveCookie = async () => {
    if (!cookieDraft.trim()) return;
    setSavingCookie(true);
    try {
      const res = await fetch(`${BASE_URL}/save-cookie`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookie_string: cookieDraft.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSavedAt(data.saved_at);
      setUiMode("ready");
      setShowSetup(false);
      setCookieDraft("");
      addLog("✓ Cookie disimpan. Siap download.");
    } catch (e) {
      addLog(`❌ Gagal simpan cookie: ${e.message}`);
    } finally {
      setSavingCookie(false);
    }
  };

  // ── Hapus cookie tersimpan ────────────────────────────────────────────────────
  const handleDeleteCookie = async () => {
    await fetch(`${BASE_URL}/saved-cookie`, { method: "DELETE" }).catch(() => {});
    setSavedAt(null);
    setUiMode("setup");
    addLog("Cookie dihapus. Silakan paste cookie baru.");
  };

  // ── Polling status job ────────────────────────────────────────────────────────
  const startPolling = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BASE_URL}/status/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();
        setJob(data);
        if (data.message) addLog(data.message);
        if (data.status === "waiting_captcha") setCaptchaTs(Date.now());
        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          setLoading(false);
        }
      } catch (_) {}
    }, 2000);
  };

  // ── Load gambar CAPTCHA ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!job?.job_id || job.status !== "waiting_captcha" || captchaTs === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/captcha-image/${job.job_id}?t=${captchaTs}`, { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const url = URL.createObjectURL(await res.blob());
        setCaptchaImg((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, [captchaTs]);  // eslint-disable-line

  // ── Load debug screenshots saat error ────────────────────────────────────────
  useEffect(() => {
    if (!job?.job_id || job.status !== "error") return;
    let cancelled = false;
    const FILES = [
      "debug_cookie_redirect.png", "debug_issued_page.png",
      "debug_login_fullpage.png",  "debug_before_fill.png",
      "debug_form_filled.png",     "debug_after_submit.png",
    ];
    (async () => {
      const results = {};
      for (const f of FILES) {
        if (cancelled) break;
        try {
          const res = await fetch(`${BASE_URL}/debug/screenshot/${job.job_id}/${f}?t=${Date.now()}`, { cache: "no-store" });
          if (res.ok) results[f] = URL.createObjectURL(await res.blob());
        } catch (_) {}
      }
      if (!cancelled) setDebugImgs(results);
    })();
    return () => { cancelled = true; };
  }, [job?.status]);  // eslint-disable-line

  // ── Mulai download ────────────────────────────────────────────────────────────
  const handleStart = async (mode) => {
    if (mode === "login" && (!form.username || !form.password)) {
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
        npwp:       form.npwp,
        masa_pajak: form.masa_pajak,
        ...(form.max_pages ? { max_pages: parseInt(form.max_pages) } : {}),
        ...(mode === "saved"
          ? { use_saved_cookie: true }
          : mode === "login"
          ? { username: form.username, password: form.password }
          : {}),
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
      addLog(`✓ CAPTCHA "${captchaCode}" dikirim…`);
      setCaptchaCode("");
    } catch (e) {
      addLog(`❌ Gagal kirim CAPTCHA: ${e.message}`);
    }
  };

  const handleDownloadZip = () => {
    if (job?.job_id) window.open(`${BASE_URL}/download/${job.job_id}`, "_blank");
  };

  const handleDeleteJob = async () => {
    if (!job?.job_id) return;
    clearInterval(pollRef.current);
    await fetch(`${BASE_URL}/job/${job.job_id}`, { method: "DELETE" }).catch(() => {});
    setJob(null); setLogs([]); setLoading(false);
    setCaptchaImg(null); setCaptchaCode("");
    setDebugImgs((prev) => { Object.values(prev).forEach(URL.revokeObjectURL); return {}; });
    addLog("Job dihapus");
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); }
    catch (_) { return iso.slice(0, 16).replace("T", " "); }
  };

  const pct = job
    ? job.total > 0
      ? Math.round((job.downloaded / job.total) * 100)
      : job.status === "done" ? 100 : job.status === "running" ? 40 : 0
    : 0;

  if (uiMode === "checking") {
    return (
      <div style={{ ...S.page, display: "flex", alignItems: "center", gap: 10, color: "#64748b" }}>
        <Loader2 size={18} className="animate-spin" /> Memeriksa status sesi…
      </div>
    );
  }

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

      {/* ── PANEL UTAMA: Cookie tersimpan → satu klik download ─────────────────── */}
      {uiMode === "ready" && (
        <div style={{ ...S.card, border: "1px solid rgba(52,211,153,0.25)", background: "rgba(52,211,153,0.04)" }}>
          {/* Status sesi */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Cookie size={18} color="#34d399" />
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#34d399" }}>Sesi Coretax Tersimpan</div>
                <div style={{ fontSize: 12, color: "#475569" }}>
                  Disimpan: {fmtDate(savedAt)}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button style={S.btnSecondary} onClick={() => setShowSetup((v) => !v)}>
                <RefreshCw size={13} />
                Perbarui Cookie
                {showSetup ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              </button>
              <button style={S.btnDanger} onClick={handleDeleteCookie} title="Hapus sesi tersimpan">
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          {/* Panel perbarui cookie (collapsed by default) */}
          {showSetup && (
            <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: 10, padding: "20px 22px", marginBottom: 20, border: "1px solid rgba(255,255,255,0.06)" }}>
              <CookieGuide />
              <label style={{ ...S.label, marginTop: 4 }}>Paste nilai Cookie di sini</label>
              <textarea
                style={{ ...S.textarea, minHeight: 80 }}
                placeholder="JSESSIONID=...; __RequestVerificationToken=...; ..."
                value={cookieDraft}
                onChange={(e) => setCookieDraft(e.target.value)}
                onFocus={(e)  => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)   => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
                spellCheck={false}
              />
              <button
                style={{ ...S.btnPrimary, marginTop: 12, opacity: savingCookie || !cookieDraft.trim() ? 0.5 : 1 }}
                onClick={handleSaveCookie}
                disabled={savingCookie || !cookieDraft.trim()}
              >
                {savingCookie
                  ? <><Loader2 size={14} className="animate-spin" /> Menyimpan…</>
                  : <><Cookie size={14} /> Simpan Cookie Baru</>}
              </button>
            </div>
          )}

          {/* Parameter download */}
          <div style={S.grid2}>
            <div>
              <label style={S.label}>NPWP Perusahaan</label>
              <input style={S.input} type="text" placeholder="0741325344011000"
                value={form.npwp} onChange={(e) => setForm({ ...form, npwp: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
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
                Maks. Halaman <span style={{ color: "#475569", fontWeight: 400 }}>(kosong = semua)</span>
              </label>
              <input style={S.input} type="number" placeholder="contoh: 5" min={1}
                value={form.max_pages} onChange={(e) => setForm({ ...form, max_pages: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
          </div>

          <div style={{ marginTop: 20, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              style={{ ...S.btnGreen, opacity: loading ? 0.55 : 1 }}
              onClick={() => handleStart("saved")}
              disabled={loading}
            >
              {loading
                ? <><Loader2 size={15} className="animate-spin" /> Sedang Berjalan…</>
                : <><LogIn size={15} /> Mulai Download</>}
            </button>
            {job && (
              <button style={S.btnDanger} onClick={handleDeleteJob}>
                <Trash2 size={14} /> Reset
              </button>
            )}
          </div>

          {/* Hint jika cookie expired */}
          <div style={{ display: "flex", gap: 8, marginTop: 14, padding: "10px 14px",
                        background: "rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12, color: "#475569" }}>
            <Info size={13} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Jika download gagal dengan pesan "Cookie kedaluwarsa", klik{" "}
              <strong style={{ color: "#94a3b8" }}>Perbarui Cookie</strong> di atas.
              Cukup dilakukan saat sesi Coretax expired (bukan setiap download).
            </span>
          </div>
        </div>
      )}

      {/* ── PANEL SETUP: Belum ada cookie → tampilkan petunjuk F12 ─────────────── */}
      {uiMode === "setup" && (
        <div style={S.card}>
          <p style={S.cardTitle}>
            <Cookie size={13} style={{ display: "inline", marginRight: 6 }} />
            Setup Sesi Coretax — Lakukan Satu Kali
          </p>

          <div style={{ display: "flex", gap: 10, padding: "12px 16px", background: "rgba(99,102,241,0.08)",
                        border: "1px solid rgba(99,102,241,0.2)", borderRadius: 10, fontSize: 13,
                        color: "#818cf8", marginBottom: 22 }}>
            <Info size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Setelah setup ini selesai, download berikutnya cukup klik{" "}
              <strong>"Mulai Download"</strong> — tidak perlu buka DevTools lagi.
              Cookie hanya perlu diperbarui jika sesi Coretax expired.
            </span>
          </div>

          <CookieGuide />

          <label style={S.label}>Paste nilai Cookie di sini</label>
          <textarea
            style={{ ...S.textarea, minHeight: 90 }}
            placeholder="JSESSIONID=abc123; __RequestVerificationToken=xyz; DNT=1; ..."
            value={cookieDraft}
            onChange={(e) => setCookieDraft(e.target.value)}
            onFocus={(e)  => (e.target.style.borderColor = "#6366f1")}
            onBlur={(e)   => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            spellCheck={false}
          />

          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            <button
              style={{ ...S.btnPrimary, opacity: savingCookie || !cookieDraft.trim() ? 0.5 : 1 }}
              onClick={handleSaveCookie}
              disabled={savingCookie || !cookieDraft.trim()}
            >
              {savingCookie
                ? <><Loader2 size={14} className="animate-spin" /> Menyimpan…</>
                : <><Cookie size={14} /> Simpan & Lanjutkan</>}
            </button>
            <button
              style={{ ...S.btnSecondary }}
              onClick={() => setUiMode("login")}
            >
              <LogIn size={13} /> Pakai Login Otomatis
            </button>
          </div>
        </div>
      )}

      {/* ── PANEL LOGIN OTOMATIS ────────────────────────────────────────────────── */}
      {uiMode === "login" && (
        <div style={S.card}>
          <p style={S.cardTitle}>
            <LogIn size={13} style={{ display: "inline", marginRight: 6 }} />
            Login Otomatis
          </p>

          <div style={{ display: "flex", gap: 8, padding: "10px 14px", background: "rgba(251,191,36,0.06)",
                        border: "1px solid rgba(251,191,36,0.2)", borderRadius: 8, fontSize: 12,
                        color: "#fbbf24", marginBottom: 16 }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Memerlukan pengisian CAPTCHA manual setelah klik Mulai. Kurang andal karena
              tergantung respons server Coretax.{" "}
              <button
                style={{ background: "none", border: "none", color: "#fbbf24", textDecoration: "underline", cursor: "pointer", fontSize: 12, padding: 0 }}
                onClick={() => setUiMode("setup")}
              >
                Gunakan mode Cookie?
              </button>
            </span>
          </div>

          <div style={S.grid2}>
            <div>
              <label style={S.label}>ID Pengguna (NPWP Pribadi / Login)</label>
              <input style={S.input} type="text" placeholder="Contoh: 720203670489T0001"
                value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Kata Sandi</label>
              <input style={S.input} type="password" placeholder="••••••••"
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>NPWP Perusahaan</label>
              <input style={S.input} type="text"
                value={form.npwp} onChange={(e) => setForm({ ...form, npwp: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Masa Pajak</label>
              <select style={S.select} value={form.masa_pajak}
                onChange={(e) => setForm({ ...form, masa_pajak: e.target.value })}>
                {MASA_PAJAK_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label style={S.label}>Maks. Halaman <span style={{ color: "#475569", fontWeight: 400 }}>(kosong = semua)</span></label>
              <input style={S.input} type="number" placeholder="contoh: 5" min={1}
                value={form.max_pages} onChange={(e) => setForm({ ...form, max_pages: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
          </div>

          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
            <button
              style={{ ...S.btnPrimary, opacity: loading ? 0.55 : 1 }}
              onClick={() => handleStart("login")}
              disabled={loading}
            >
              {loading
                ? <><Loader2 size={15} className="animate-spin" /> Sedang Berjalan…</>
                : <><LogIn size={15} /> Mulai Login Otomatis</>}
            </button>
            {job && <button style={S.btnDanger} onClick={handleDeleteJob}><Trash2 size={14} /> Reset</button>}
          </div>
        </div>
      )}

      {/* ── CAPTCHA Panel (hanya mode login) ─────────────────────────────────── */}
      {job?.status === "waiting_captcha" && (
        <div style={{ ...S.card, border: "1px solid rgba(251,146,60,0.35)", background: "rgba(251,146,60,0.05)" }}>
          <p style={{ ...S.cardTitle, color: "#fb923c" }}>
            <ShieldCheck size={14} style={{ display: "inline", marginRight: 6 }} />
            Isi Kode CAPTCHA
          </p>
          <p style={{ fontSize: 13, color: "#94a3b8", marginBottom: 16 }}>
            Browser sudah membuka halaman login. Lihat gambar CAPTCHA, ketik kode, lalu klik{" "}
            <strong style={{ color: "#fb923c" }}>Submit</strong>.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 600 }}>CAPTCHA (zoom)</div>
              {captchaImg ? (
                <img src={captchaImg} alt="CAPTCHA"
                  style={{ width: "100%", borderRadius: 8, border: "2px solid rgba(251,146,60,0.5)", imageRendering: "pixelated" }} />
              ) : (
                <div style={{ padding: "32px 16px", textAlign: "center", color: "#475569", fontSize: 12, background: "rgba(0,0,0,0.2)", borderRadius: 8 }}>
                  <Loader2 size={16} className="animate-spin" style={{ display: "inline", marginRight: 6 }} />Memuat…
                </div>
              )}
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 600 }}>Halaman login (konteks)</div>
              <DebugImage jobId={job.job_id} filename="debug_login_fullpage.png" />
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={S.label}>Kode CAPTCHA</label>
              <input
                style={{ ...S.input, fontSize: 18, letterSpacing: "0.2em", textAlign: "center" }}
                type="text" placeholder="Ketik kode di atas"
                value={captchaCode}
                onChange={(e) => setCaptchaCode(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmitCaptcha()}
                autoFocus
                onFocus={(e) => (e.target.style.borderColor = "#fb923c")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
              />
            </div>
            <button style={S.btnOrange} onClick={handleSubmitCaptcha}>
              <ShieldCheck size={15} /> Submit
            </button>
            <button style={{ ...S.btnDanger, padding: "10px 14px" }}
              onClick={() => setCaptchaTs(Date.now())} title="Muat ulang CAPTCHA">
              ↻
            </button>
          </div>
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

          <div style={S.progressBar}><div style={S.progressFill(pct)} /></div>

          <div style={S.logBox} ref={logRef}>
            {logs.length === 0
              ? <span style={{ color: "#334155" }}>Menunggu log…</span>
              : logs.map((l, i) => <div key={i}>{l}</div>)}
          </div>

          {job.zip_ready && (
            <div style={{ marginTop: 16 }}>
              <button style={S.btnDownload} onClick={handleDownloadZip}>
                <Archive size={14} /> Download ZIP ({job.downloaded} file)
              </button>
            </div>
          )}

          {/* Jika cookie expired: tampilkan shortcut ke panel perbarui cookie */}
          {job.status === "error" && job.message?.includes("kedaluwarsa") && uiMode === "ready" && (
            <div style={{ marginTop: 14, display: "flex", gap: 10, padding: "12px 14px",
                          background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.2)",
                          borderRadius: 10, fontSize: 13, color: "#fbbf24", alignItems: "center" }}>
              <AlertCircle size={14} style={{ flexShrink: 0 }} />
              <span>Cookie sesi expired. </span>
              <button
                style={{ background: "none", border: "none", color: "#fbbf24", textDecoration: "underline", cursor: "pointer", fontSize: 13, padding: 0 }}
                onClick={() => setShowSetup(true)}
              >
                Klik Perbarui Cookie di atas →
              </button>
            </div>
          )}

          {/* Debug screenshots saat error */}
          {job.status === "error" && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600, marginBottom: 12 }}>
                Screenshot Browser (untuk mendiagnosis error):
              </div>
              {Object.keys(debugImgs).length === 0 && (
                <div style={{ fontSize: 12, color: "#475569", display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={13} className="animate-spin" /> Memuat screenshot debug…
                </div>
              )}
              {[
                { key: "debug_cookie_redirect.png", label: "Cookie redirect ke login" },
                { key: "debug_issued_page.png",      label: "Halaman eBupot (setelah login)" },
                { key: "debug_login_fullpage.png",   label: "Halaman Login" },
                { key: "debug_before_fill.png",      label: "Sebelum isi form" },
                { key: "debug_form_filled.png",      label: "Setelah form diisi" },
                { key: "debug_after_submit.png",     label: "Setelah submit" },
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
                    <img src={debugImgs[key]} alt={label}
                      style={{ width: "100%", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", display: "block" }} />
                  </div>
                ) : null
              )}
            </div>
          )}
        </div>
      )}

      {/* Log sebelum job ada */}
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

// ── Panduan langkah-demi-langkah cara copy Cookie dari Chrome ────────────────
function CookieGuide() {
  const code = (text) => (
    <code style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", padding: "1px 6px", borderRadius: 4, fontSize: 12, fontFamily: "monospace" }}>
      {text}
    </code>
  );
  const tag = (text, color = "#34d399") => (
    <span style={{ background: `${color}18`, color, border: `1px solid ${color}30`, borderRadius: 4, padding: "1px 7px", fontSize: 11, fontWeight: 600, whiteSpace: "nowrap" }}>
      {text}
    </span>
  );

  const steps = [
    {
      title: "Login ke Coretax di Chrome",
      detail: <>
        Buka <strong style={{ color: "#e2e8f0" }}>coretaxdjp.pajak.go.id</strong> di Chrome dan login seperti biasa menggunakan NPWP + password + CAPTCHA.
        Setelah masuk, <strong style={{ color: "#e2e8f0" }}>pilih NPWP perusahaan</strong> dari dropdown di pojok kanan atas halaman.
        Pastikan sudah tampil halaman utama Coretax (bukan halaman login).
      </>,
    },
    {
      title: "Buka DevTools Chrome",
      detail: <>
        Tekan tombol <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontSize: 13, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>F12</code>{" "}
        di keyboard (atau klik kanan di halaman → <em>Inspect</em>).
        Jendela DevTools akan muncul di bagian bawah atau samping browser.
      </>,
    },
    {
      title: "Buka tab Network",
      detail: <>
        Di bagian atas DevTools, klik tab {tag("Network", "#818cf8")}.
        Jika tab Network sudah terbuka tapi daftarnya kosong, tekan{" "}
        <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontSize: 13, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>F5</code>{" "}
        atau refresh halaman Coretax agar request muncul. Akan terlihat banyak baris request.
      </>,
    },
    {
      title: "Klik salah satu request Coretax",
      detail: <>
        Di daftar request (kolom Name), cari baris yang alamatnya mengandung{" "}
        {code("coretaxdjp.pajak.go.id")} — biasanya baris paling atas setelah refresh.
        Klik <strong style={{ color: "#e2e8f0" }}>satu kali</strong> pada baris tersebut.
        Panel detail akan muncul di sebelah kanan.
      </>,
    },
    {
      title: "Temukan baris Cookie di Request Headers",
      detail: <>
        Di panel kanan, klik tab {tag("Headers", "#818cf8")}.
        Scroll ke bawah sampai menemukan bagian{" "}
        <strong style={{ color: "#e2e8f0" }}>Request Headers</strong>.
        Cari baris berlabel {code("cookie:")} atau {code("Cookie:")}.
        Nilai di sebelah kanannya adalah teks panjang berisi banyak nama=nilai dipisah titik koma.
        <div style={{ marginTop: 6, padding: "6px 10px", background: "rgba(0,0,0,0.3)", borderRadius: 6, fontSize: 11, color: "#64748b", fontFamily: "monospace" }}>
          Contoh: JSESSIONID=abc123; __RequestVerif...=xyz; DNT=1; …
        </div>
      </>,
    },
    {
      title: "Copy nilai Cookie",
      detail: <>
        <strong style={{ color: "#e2e8f0" }}>Klik kanan</strong> tepat pada nilai cookie (teks panjang di sebelah kanan {code("cookie:")}).
        Pilih {tag("Copy value", "#34d399")} dari menu yang muncul.
        <br /><br />
        <span style={{ color: "#fbbf24" }}>⚠ Jangan klik kanan pada tulisan "cookie:" — klik kanan pada nilainya (teks panjang di sebelah kanannya).</span>
      </>,
    },
    {
      title: "Paste di kotak di bawah → Simpan",
      detail: <>
        Klik di dalam kotak teks di bawah, lalu tekan{" "}
        <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>Ctrl+V</code>{" "}
        untuk paste. Klik tombol {tag("Simpan", "#6366f1")}.
        Selesai — download berikutnya cukup klik Mulai tanpa perlu buka DevTools lagi.
      </>,
    },
  ];

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 14 }}>
        Langkah-langkah mendapatkan Cookie dari Chrome
      </div>
      {steps.map((step, i) => (
        <div key={i} style={{ display: "flex", gap: 14, marginBottom: 14 }}>
          {/* Nomor + garis vertikal */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
            <div style={{ width: 26, height: 26, borderRadius: "50%", background: "linear-gradient(135deg,#6366f1,#8b5cf6)", color: "#fff", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {i + 1}
            </div>
            {i < steps.length - 1 && (
              <div style={{ width: 2, flex: 1, minHeight: 12, background: "rgba(99,102,241,0.2)", marginTop: 4 }} />
            )}
          </div>
          {/* Konten */}
          <div style={{ paddingBottom: i < steps.length - 1 ? 4 : 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", marginBottom: 4 }}>
              {step.title}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7 }}>
              {step.detail}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DebugImage({ jobId, filename }) {
  const [src, setSrc] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (!jobId || !filename) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/debug/screenshot/${jobId}/${filename}?t=${Date.now()}`, { cache: "no-store" });
        if (!res.ok || cancelled) { setErr(true); return; }
        if (!cancelled) setSrc(URL.createObjectURL(await res.blob()));
      } catch (_) { if (!cancelled) setErr(true); }
    })();
    return () => { cancelled = true; setSrc((p) => { if (p) URL.revokeObjectURL(p); return null; }); };
  }, [jobId, filename]);
  if (err)  return <div style={{ padding: "12px", textAlign: "center", fontSize: 11, color: "#334155", background: "rgba(0,0,0,0.15)", borderRadius: 8 }}>Tidak tersedia</div>;
  if (!src) return <div style={{ padding: "12px", textAlign: "center", fontSize: 11, color: "#475569", background: "rgba(0,0,0,0.15)", borderRadius: 8 }}><Loader2 size={14} className="animate-spin" style={{ display: "inline", marginRight: 4 }} />Memuat…</div>;
  return <img src={src} alt={filename} style={{ width: "100%", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", display: "block", cursor: "pointer" }} onClick={() => window.open(src, "_blank")} title="Klik untuk buka di tab baru" />;
}
