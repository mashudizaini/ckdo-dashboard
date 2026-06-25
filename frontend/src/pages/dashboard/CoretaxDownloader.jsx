/**
 * CoretaxDownloader.jsx
 * Bulk download eBupot BPU dari Coretax DJP.
 *
 * UX flow:
 *   Pertama kali pakai (atau cookie expired):
 *     → User login ke Coretax di Chrome seperti biasa
 *     → F12 → Network → copy Cookie header → paste di sini → Simpan & Mulai
 *   Selanjutnya (cookie masih valid):
 *     → Pilih masa pajak → klik Start Download (tanpa F12)
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
  running:         "RUNNING",
  waiting_captcha: "WAITING CAPTCHA",
  done:            "DONE",
  error:           "ERROR",
};

const S = {
  page:      { padding: "28px 32px", color: "#1e293b", fontFamily: "'DM Sans','Segoe UI',sans-serif", maxWidth: 860 },
  header:    { display: "flex", alignItems: "center", gap: 12, marginBottom: 28 },
  iconBox:   { width: 40, height: 40, borderRadius: 12, background: "linear-gradient(135deg,#2563eb,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" },
  title:     { fontSize: 20, fontWeight: 800, color: "#1e293b", margin: 0, letterSpacing: "0.01em" },
  subtitle:  { fontSize: 13, color: "#64748b", margin: 0 },
  card:      { background: "#e8edf5", border: "none", borderRadius: 18, padding: "24px 28px", marginBottom: 20, boxShadow: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff" },
  cardTitle: { fontSize: 13, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 18 },
  grid2:     { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  label:     { fontSize: 12, color: "#64748b", marginBottom: 6, display: "block", fontWeight: 500 },
  input:     { width: "100%", background: "#e8edf5", border: "none", borderRadius: 10, padding: "10px 14px", color: "#1e293b", fontSize: 14, fontWeight: 500, outline: "none", boxSizing: "border-box", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" },
  textarea:  { width: "100%", background: "#e8edf5", border: "none", borderRadius: 10, padding: "10px 14px", color: "#1e293b", fontSize: 12, fontWeight: 500, outline: "none", boxSizing: "border-box", resize: "vertical", fontFamily: "'Fira Code','Courier New',monospace", lineHeight: 1.6, boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" },
  select:    { width: "100%", background: "#e8edf5", border: "none", borderRadius: 10, padding: "10px 14px", color: "#1e293b", fontSize: 14, fontWeight: 500, outline: "none", boxSizing: "border-box", cursor: "pointer", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" },
  btnPrimary:  { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#2563eb,#3b82f6)", border: "none", borderRadius: 12, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" },
  btnGreen:    { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#059669,#10b981)", border: "none", borderRadius: 12, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" },
  btnOrange:   { display: "flex", alignItems: "center", gap: 8, padding: "11px 22px", background: "linear-gradient(135deg,#f97316,#fb923c)", border: "none", borderRadius: 12, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" },
  btnSecondary:{ display: "flex", alignItems: "center", gap: 6, padding: "9px 16px", background: "#e8edf5", border: "none", borderRadius: 10, color: "#475569", fontSize: 13, fontWeight: 600, cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff" },
  btnDanger:   { display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)", borderRadius: 8, color: "#dc2626", fontSize: 13, cursor: "pointer" },
  btnDownload: { display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", background: "rgba(52,211,153,0.08)", border: "1px solid rgba(52,211,153,0.2)", borderRadius: 8, color: "#059669", fontSize: 13, cursor: "pointer" },
  progressBar:  { height: 7, borderRadius: 99, background: "#e8edf5", boxShadow: "inset 2px 2px 4px #c5cad8, inset -2px -2px 4px #ffffff", overflow: "hidden", marginTop: 10 },
  progressFill: (pct) => ({ height: "100%", width: `${pct}%`, borderRadius: 99, background: "linear-gradient(90deg,#2563eb,#3b82f6)", transition: "width 0.5s ease" }),
  statusBadge:  (s) => ({ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 99, fontSize: 12, fontWeight: 600, background: STATUS_COLOR[s]?.bg, color: STATUS_COLOR[s]?.text, border: `1px solid ${STATUS_COLOR[s]?.border}` }),
  logBox:  { background: "#e8edf5", border: "none", borderRadius: 12, padding: "12px 16px", fontSize: 12, color: "#475569", fontWeight: 500, fontFamily: "'Fira Code','Courier New',monospace", minHeight: 44, marginTop: 10, lineHeight: 1.7, maxHeight: 160, overflowY: "auto", boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff" },
  statRow: { display: "flex", gap: 20, marginTop: 14 },
  statItem:{ flex: 1, background: "#e8edf5", border: "none", borderRadius: 14, padding: "14px 16px", textAlign: "center", boxShadow: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff" },
  statNum: { fontSize: 26, fontWeight: 800, color: "#1e293b", lineHeight: 1 },
  statLabel:{ fontSize: 11, color: "#64748b", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.06em" },
  stepItem: { display: "flex", gap: 10, marginBottom: 8, fontSize: 13, color: "#475569", fontWeight: 500, alignItems: "flex-start" },
  stepNum:  { minWidth: 24, height: 24, borderRadius: "50%", background: "linear-gradient(135deg,#2563eb,#3b82f6)", color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1, boxShadow: "2px 2px 4px #c5cad8, -1px -1px 3px #ffffff" },
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
      addLog("✓ Cookie saved. Ready to download.");
    } catch (e) {
      addLog(`❌ Failed to save cookie: ${e.message}`);
    } finally {
      setSavingCookie(false);
    }
  };

  // ── Hapus cookie tersimpan ────────────────────────────────────────────────────
  const handleDeleteCookie = async () => {
    await fetch(`${BASE_URL}/saved-cookie`, { method: "DELETE" }).catch(() => {});
    setSavedAt(null);
    setUiMode("setup");
    addLog("Cookie deleted. Please paste a new cookie.");
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
      addLog("⚠ User ID and Password are required");
      return;
    }
    setLoading(true);
    setJob(null);
    setLogs([]);
    setCaptchaImg(null);
    setCaptchaCode("");
    setDebugImgs({});
    addLog("Sending request to server...");

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
      addLog(`Job started: ${data.job_id}`);
      startPolling(data.job_id);
    } catch (e) {
      addLog(`❌ Failed to start job: ${e.message}`);
      setLoading(false);
    }
  };

  const handleSubmitCaptcha = async () => {
    if (!captchaCode.trim()) { addLog("⚠ CAPTCHA code is required"); return; }
    if (!job?.job_id) return;
    try {
      const res = await fetch(`${BASE_URL}/captcha/${job.job_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: captchaCode.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      addLog(`✓ CAPTCHA "${captchaCode}" submitted...`);
      setCaptchaCode("");
    } catch (e) {
      addLog(`❌ Failed to submit CAPTCHA: ${e.message}`);
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
    addLog("Job deleted");
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
        <Loader2 size={18} className="animate-spin" /> Checking session status...
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
                <div style={{ fontSize: 14, fontWeight: 600, color: "#34d399" }}>Coretax Session Saved</div>
                <div style={{ fontSize: 12, color: "#475569" }}>
                  Saved: {fmtDate(savedAt)}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button style={S.btnSecondary} onClick={() => setShowSetup((v) => !v)}>
                <RefreshCw size={13} />
                Update Cookie
                {showSetup ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              </button>
              <button style={S.btnDanger} onClick={handleDeleteCookie} title="Delete saved session">
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          {/* Panel perbarui cookie (collapsed by default) */}
          {showSetup && (
            <div style={{ background: "#e8edf5", borderRadius: 16, padding: "20px 22px", marginBottom: 20, boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff" }}>
              <CookieGuide />
              <label style={{ ...S.label, marginTop: 4 }}>Paste Cookie value here</label>
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
                  ? <><Loader2 size={14} className="animate-spin" /> Saving...</>
                  : <><Cookie size={14} /> Save New Cookie</>}
              </button>
            </div>
          )}

          {/* Parameter download */}
          <div style={S.grid2}>
            <div>
              <label style={S.label}>Company Tax ID</label>
              <input style={S.input} type="text" placeholder="0741325344011000"
                value={form.npwp} onChange={(e) => setForm({ ...form, npwp: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Tax Period</label>
              <select style={S.select} value={form.masa_pajak}
                onChange={(e) => setForm({ ...form, masa_pajak: e.target.value })}>
                {MASA_PAJAK_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label style={S.label}>
                Max Pages <span style={{ color: "#475569", fontWeight: 400 }}>(blank = all)</span>
              </label>
              <input style={S.input} type="number" placeholder="e.g. 5" min={1}
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
                ? <><Loader2 size={15} className="animate-spin" /> Running...</>
                : <><LogIn size={15} /> Start Download</>}
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
              If download fails with "Cookie expired" message, click{" "}
              <strong style={{ color: "#94a3b8" }}>Update Cookie</strong> above.
              Only needed when Coretax session has expired (not every download).
            </span>
          </div>
        </div>
      )}

      {/* ── PANEL SETUP: Belum ada cookie → tampilkan petunjuk F12 ─────────────── */}
      {uiMode === "setup" && (
        <div style={S.card}>
          <p style={S.cardTitle}>
            <Cookie size={13} style={{ display: "inline", marginRight: 6 }} />
            Setup Coretax Session — One-time Setup
          </p>

          <div style={{ display: "flex", gap: 10, padding: "12px 16px", background: "rgba(99,102,241,0.08)",
                        border: "1px solid rgba(99,102,241,0.2)", borderRadius: 10, fontSize: 13,
                        color: "#818cf8", marginBottom: 22 }}>
            <Info size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              After this setup is complete, subsequent downloads only require clicking{" "}
              <strong>"Start Download"</strong> — no need to open DevTools again.
              Cookie only needs updating when Coretax session expires.
            </span>
          </div>

          <CookieGuide />

          <label style={S.label}>Paste Cookie value here</label>
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
                ? <><Loader2 size={14} className="animate-spin" /> Saving...</>
                : <><Cookie size={14} /> Save & Continue</>}
            </button>
            <button
              style={{ ...S.btnSecondary }}
              onClick={() => setUiMode("login")}
            >
              <LogIn size={13} /> Use Auto Login
            </button>
          </div>
        </div>
      )}

      {/* ── PANEL LOGIN OTOMATIS ────────────────────────────────────────────────── */}
      {uiMode === "login" && (
        <div style={S.card}>
          <p style={S.cardTitle}>
            <LogIn size={13} style={{ display: "inline", marginRight: 6 }} />
            Auto Login
          </p>

          <div style={{ display: "flex", gap: 8, padding: "10px 14px", background: "rgba(251,191,36,0.06)",
                        border: "1px solid rgba(251,191,36,0.2)", borderRadius: 8, fontSize: 12,
                        color: "#fbbf24", marginBottom: 16 }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Requires manual CAPTCHA entry after clicking Start. Less reliable as it
              depends on Coretax server response.{" "}
              <button
                style={{ background: "none", border: "none", color: "#fbbf24", textDecoration: "underline", cursor: "pointer", fontSize: 12, padding: 0 }}
                onClick={() => setUiMode("setup")}
              >
                Use Cookie mode?
              </button>
            </span>
          </div>

          <div style={S.grid2}>
            <div>
              <label style={S.label}>User ID (Personal Tax ID / Login)</label>
              <input style={S.input} type="text" placeholder="e.g. 720203670489T0001"
                value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Password</label>
              <input style={S.input} type="password" placeholder="••••••••"
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Company Tax ID</label>
              <input style={S.input} type="text"
                value={form.npwp} onChange={(e) => setForm({ ...form, npwp: e.target.value })}
                onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
                onBlur={(e)  => (e.target.style.borderColor = "rgba(255,255,255,0.1)")} />
            </div>
            <div>
              <label style={S.label}>Tax Period</label>
              <select style={S.select} value={form.masa_pajak}
                onChange={(e) => setForm({ ...form, masa_pajak: e.target.value })}>
                {MASA_PAJAK_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label style={S.label}>Max Pages <span style={{ color: "#475569", fontWeight: 400 }}>(blank = all)</span></label>
              <input style={S.input} type="number" placeholder="e.g. 5" min={1}
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
                ? <><Loader2 size={15} className="animate-spin" /> Running...</>
                : <><LogIn size={15} /> Start Auto Login</>}
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
            Enter CAPTCHA Code
          </p>
          <p style={{ fontSize: 13, color: "#94a3b8", marginBottom: 16 }}>
            Browser has opened the login page. View the CAPTCHA image, type the code, then click{" "}
            <strong style={{ color: "#fb923c" }}>Submit</strong>.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 600 }}>CAPTCHA (zoom)</div>
              {captchaImg ? (
                <img src={captchaImg} alt="CAPTCHA"
                  style={{ width: "100%", borderRadius: 8, border: "2px solid rgba(251,146,60,0.5)", imageRendering: "pixelated" }} />
              ) : (
                <div style={{ padding: "32px 16px", textAlign: "center", color: "#475569", fontSize: 12, background: "#e8edf5", borderRadius: 12, boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff" }}>
                  <Loader2 size={16} className="animate-spin" style={{ display: "inline", marginRight: 6 }} />Loading...
                </div>
              )}
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 600 }}>Login page (context)</div>
              <DebugImage jobId={job.job_id} filename="debug_login_fullpage.png" />
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={S.label}>CAPTCHA Code</label>
              <input
                style={{ ...S.input, fontSize: 18, letterSpacing: "0.2em", textAlign: "center" }}
                type="text" placeholder="Type code above"
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
              onClick={() => setCaptchaTs(Date.now())} title="Reload CAPTCHA">
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
              <div style={S.statLabel}>Success</div>
            </div>
            <div style={S.statItem}>
              <div style={{ ...S.statNum, color: "#f87171" }}>{job.failed}</div>
              <div style={S.statLabel}>Failed</div>
            </div>
            <div style={S.statItem}>
              <div style={{ ...S.statNum, color: "#818cf8" }}>{pct}%</div>
              <div style={S.statLabel}>Progress</div>
            </div>
          </div>

          <div style={S.progressBar}><div style={S.progressFill(pct)} /></div>

          <div style={S.logBox} ref={logRef}>
            {logs.length === 0
              ? <span style={{ color: "#334155" }}>Waiting for logs...</span>
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
              <span>Session cookie expired.</span>
              <button
                style={{ background: "none", border: "none", color: "#fbbf24", textDecoration: "underline", cursor: "pointer", fontSize: 13, padding: 0 }}
                onClick={() => setShowSetup(true)}
              >
                Click Update Cookie above
              </button>
            </div>
          )}

          {/* Debug screenshots saat error */}
          {job.status === "error" && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600, marginBottom: 12 }}>
                Browser Screenshots (for diagnosing errors):
              </div>
              {Object.keys(debugImgs).length === 0 && (
                <div style={{ fontSize: 12, color: "#475569", display: "flex", alignItems: "center", gap: 6 }}>
                  <Loader2 size={13} className="animate-spin" /> Loading debug screenshots...
                </div>
              )}
              {[
                { key: "debug_cookie_redirect.png", label: "Cookie redirect to login" },
                { key: "debug_issued_page.png",      label: "eBupot page (after login)" },
                { key: "debug_login_fullpage.png",   label: "Login page" },
                { key: "debug_before_fill.png",      label: "Before filling form" },
                { key: "debug_form_filled.png",      label: "After form filled" },
                { key: "debug_after_submit.png",     label: "After submit" },
              ].map(({ key, label }) =>
                debugImgs[key] ? (
                  <div key={key} style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontWeight: 600, color: "#94a3b8" }}>{label}</span>
                      <a href={debugImgs[key]} target="_blank" rel="noreferrer"
                        style={{ fontSize: 11, color: "#818cf8", textDecoration: "underline" }}>
                        open in new tab ↗
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
      title: "Login to Coretax in Chrome",
      detail: <>
        Open <strong style={{ color: "#e2e8f0" }}>coretaxdjp.pajak.go.id</strong> in Chrome and login as usual using NPWP + password + CAPTCHA.
        After logging in, <strong style={{ color: "#e2e8f0" }}>select company NPWP</strong> from the dropdown in the top right corner.
        Make sure the Coretax main page is displayed (not the login page).
      </>,
    },
    {
      title: "Open Chrome DevTools",
      detail: <>
        Press <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontSize: 13, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>F12</code>{" "}
        on your keyboard (or right-click on the page and select <em>Inspect</em>).
        The DevTools window will appear at the bottom or side of the browser.
      </>,
    },
    {
      title: "Open Network tab",
      detail: <>
        At the top of DevTools, click the {tag("Network", "#818cf8")} tab.
        If the Network tab is open but the list is empty, press{" "}
        <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontSize: 13, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>F5</code>{" "}
        or refresh the Coretax page so requests appear. You will see many request rows.
      </>,
    },
    {
      title: "Click a Coretax request",
      detail: <>
        In the request list (Name column), find a row with an address containing{" "}
        {code("coretaxdjp.pajak.go.id")} — usually the top row after refresh.
        Click <strong style={{ color: "#e2e8f0" }}>once</strong> on that row.
        A detail panel will appear on the right.
      </>,
    },
    {
      title: "Find Cookie in Request Headers",
      detail: <>
        In the right panel, click the {tag("Headers", "#818cf8")} tab.
        Scroll down until you find the{" "}
        <strong style={{ color: "#e2e8f0" }}>Request Headers</strong> section.
        Look for the row labeled {code("cookie:")} or {code("Cookie:")}.
        The value to its right is a long text containing many name=value pairs separated by semicolons.
        <div style={{ marginTop: 6, padding: "6px 10px", background: "rgba(0,0,0,0.3)", borderRadius: 6, fontSize: 11, color: "#64748b", fontFamily: "monospace" }}>
          Example: JSESSIONID=abc123; __RequestVerif...=xyz; DNT=1; ...
        </div>
      </>,
    },
    {
      title: "Copy Cookie value",
      detail: <>
        <strong style={{ color: "#e2e8f0" }}>Right-click</strong> directly on the cookie value (the long text to the right of {code("cookie:")}).
        Select {tag("Copy value", "#34d399")} from the context menu.
        <br /><br />
        <span style={{ color: "#fbbf24" }}>⚠ Do not right-click on the "cookie:" label — right-click on the value (the long text to its right).</span>
      </>,
    },
    {
      title: "Paste in the box below and Save",
      detail: <>
        Click inside the text box below, then press{" "}
        <code style={{ background: "rgba(255,255,255,0.1)", color: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700, border: "1px solid rgba(255,255,255,0.2)" }}>Ctrl+V</code>{" "}
        to paste. Click the {tag("Save", "#6366f1")} button.
        Done — subsequent downloads only require clicking Start without opening DevTools again.
      </>,
    },
  ];

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 14 }}>
        Steps to get Cookie from Chrome
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
  if (err)  return <div style={{ padding: "12px", textAlign: "center", fontSize: 11, color: "#334155", background: "rgba(0,0,0,0.15)", borderRadius: 8 }}>Not available</div>;
  if (!src) return <div style={{ padding: "12px", textAlign: "center", fontSize: 11, color: "#475569", background: "rgba(0,0,0,0.15)", borderRadius: 8 }}><Loader2 size={14} className="animate-spin" style={{ display: "inline", marginRight: 4 }} />Loading...</div>;
  return <img src={src} alt={filename} style={{ width: "100%", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", display: "block", cursor: "pointer" }} onClick={() => window.open(src, "_blank")} title="Click to open in new tab" />;
}
