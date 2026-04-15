/**
 * CoretaxDownloader.jsx
 * Halaman bulk download eBupot BPU dari Coretax DJP.
 * Pasang di sidebar Accounting sebagai sub-menu "Coretax Downloader".
 *
 * Requirement: npm install lucide-react
 * API base URL: sesuaikan BASE_URL di bawah
 */

import { useState, useEffect, useRef } from "react";
import {
  Download, FileText, LogIn, RefreshCw, CheckCircle2,
  XCircle, Loader2, Archive, Trash2, AlertCircle, ChevronDown
} from "lucide-react";

// ── Sesuaikan dengan base URL FastAPI Anda ───────────────────────────────────
const BASE_URL = "/api/coretax";

// ── Daftar masa pajak ────────────────────────────────────────────────────────
const MASA_PAJAK_OPTIONS = [
  "Januari 2026","Februari 2026","Maret 2026","April 2026",
  "Mei 2026","Juni 2026","Juli 2026","Agustus 2026",
  "September 2026","Oktober 2026","November 2026","Desember 2026",
  "Januari 2025","Februari 2025","Maret 2025","April 2025",
  "Mei 2025","Juni 2025","Juli 2025","Agustus 2025",
  "September 2025","Oktober 2025","November 2025","Desember 2025",
];

// ── Warna status ─────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  pending:  { bg: "rgba(251,191,36,0.1)",  text: "#fbbf24", border: "rgba(251,191,36,0.3)"  },
  running:  { bg: "rgba(99,102,241,0.1)",  text: "#818cf8", border: "rgba(99,102,241,0.3)"  },
  done:     { bg: "rgba(52,211,153,0.1)",  text: "#34d399", border: "rgba(52,211,153,0.3)"  },
  error:    { bg: "rgba(248,113,113,0.1)", text: "#f87171", border: "rgba(248,113,113,0.3)" },
};

const STATUS_ICON = {
  pending:  <Loader2 size={14} className="animate-spin" />,
  running:  <Loader2 size={14} className="animate-spin" />,
  done:     <CheckCircle2 size={14} />,
  error:    <XCircle size={14} />,
};

// ── Styles (inline, cocok dengan dark theme dashboard) ───────────────────────
const S = {
  page: {
    padding: "28px 32px",
    color: "#e2e8f0",
    fontFamily: "'DM Sans', 'Segoe UI', sans-serif",
    maxWidth: 860,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginBottom: 28,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 20,
    fontWeight: 700,
    color: "#f1f5f9",
    margin: 0,
  },
  subtitle: {
    fontSize: 13,
    color: "#64748b",
    margin: 0,
  },
  card: {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 14,
    padding: "24px 28px",
    marginBottom: 20,
  },
  cardTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    marginBottom: 18,
  },
  grid2: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 16,
  },
  label: {
    fontSize: 12,
    color: "#94a3b8",
    marginBottom: 6,
    display: "block",
    fontWeight: 500,
  },
  input: {
    width: "100%",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "10px 14px",
    color: "#f1f5f9",
    fontSize: 14,
    outline: "none",
    boxSizing: "border-box",
    transition: "border-color 0.2s",
  },
  select: {
    width: "100%",
    background: "#1e1e2e",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "10px 14px",
    color: "#f1f5f9",
    fontSize: 14,
    outline: "none",
    boxSizing: "border-box",
    cursor: "pointer",
  },
  btnPrimary: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "11px 22px",
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    border: "none",
    borderRadius: 9,
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.2s, transform 0.1s",
  },
  btnGhost: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 16px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    color: "#94a3b8",
    fontSize: 13,
    cursor: "pointer",
    transition: "background 0.2s",
  },
  btnDanger: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 14px",
    background: "rgba(248,113,113,0.1)",
    border: "1px solid rgba(248,113,113,0.25)",
    borderRadius: 8,
    color: "#f87171",
    fontSize: 13,
    cursor: "pointer",
  },
  btnDownload: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 14px",
    background: "rgba(52,211,153,0.1)",
    border: "1px solid rgba(52,211,153,0.25)",
    borderRadius: 8,
    color: "#34d399",
    fontSize: 13,
    cursor: "pointer",
  },
  progressBar: (pct) => ({
    height: 6,
    borderRadius: 99,
    background: "rgba(255,255,255,0.07)",
    overflow: "hidden",
    marginTop: 10,
  }),
  progressFill: (pct) => ({
    height: "100%",
    width: `${pct}%`,
    borderRadius: 99,
    background: "linear-gradient(90deg, #6366f1, #8b5cf6)",
    transition: "width 0.5s ease",
  }),
  statusBadge: (status) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    padding: "3px 10px",
    borderRadius: 99,
    fontSize: 12,
    fontWeight: 600,
    background: STATUS_COLOR[status]?.bg,
    color: STATUS_COLOR[status]?.text,
    border: `1px solid ${STATUS_COLOR[status]?.border}`,
  }),
  logBox: {
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    padding: "12px 16px",
    fontSize: 12,
    color: "#64748b",
    fontFamily: "'Fira Code', 'Courier New', monospace",
    minHeight: 44,
    marginTop: 10,
    lineHeight: 1.7,
    maxHeight: 140,
    overflowY: "auto",
  },
  statRow: {
    display: "flex",
    gap: 20,
    marginTop: 14,
  },
  statItem: {
    flex: 1,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.07)",
    borderRadius: 10,
    padding: "14px 16px",
    textAlign: "center",
  },
  statNum: {
    fontSize: 26,
    fontWeight: 700,
    color: "#f1f5f9",
    lineHeight: 1,
  },
  statLabel: {
    fontSize: 11,
    color: "#475569",
    marginTop: 4,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  divider: {
    height: 1,
    background: "rgba(255,255,255,0.06)",
    margin: "20px 0",
  },
  warning: {
    display: "flex",
    gap: 10,
    padding: "12px 16px",
    background: "rgba(251,191,36,0.07)",
    border: "1px solid rgba(251,191,36,0.2)",
    borderRadius: 10,
    fontSize: 13,
    color: "#fbbf24",
    marginBottom: 20,
  },
};

// ── Main Component ────────────────────────────────────────────────────────────
export default function CoretaxDownloader() {
  const [form, setForm] = useState({
    username: "",
    password: "",
    masa_pajak: "Maret 2026",
    max_pages: "",
  });
  const [job, setJob] = useState(null);          // job object dari API
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);
  const pollRef = useRef(null);
  const logRef = useRef(null);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Cleanup polling
  useEffect(() => () => clearInterval(pollRef.current), []);

  const addLog = (msg) =>
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString("id-ID")}] ${msg}`]);

  const startPolling = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BASE_URL}/status/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();
        setJob(data);
        if (data.message) addLog(data.message);
        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          setLoading(false);
        }
      } catch (_) {}
    }, 2000);
  };

  const handleStart = async () => {
    if (!form.username || !form.password) {
      addLog("⚠ Username dan password wajib diisi");
      return;
    }
    setLoading(true);
    setJob(null);
    setLogs([]);
    addLog("Mengirim permintaan ke server…");

    try {
      const body = {
        username: form.username,
        password: form.password,
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

  const handleDownloadZip = () => {
    if (!job?.job_id) return;
    window.open(`${BASE_URL}/download/${job.job_id}`, "_blank");
  };

  const handleDelete = async () => {
    if (!job?.job_id) return;
    clearInterval(pollRef.current);
    await fetch(`${BASE_URL}/job/${job.job_id}`, { method: "DELETE" }).catch(() => {});
    setJob(null);
    setLogs([]);
    setLoading(false);
    addLog("Job dihapus");
  };

  const pct = job
    ? job.total > 0
      ? Math.round((job.downloaded / job.total) * 100)
      : job.status === "done" ? 100 : job.status === "running" ? 50 : 0
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

      {/* Warning */}
      <div style={S.warning}>
        <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          Pastikan server backend sudah menginstall Playwright:{" "}
          <code style={{ background: "rgba(0,0,0,0.3)", padding: "1px 6px", borderRadius: 4 }}>
            pip install playwright && playwright install chromium
          </code>
        </span>
      </div>

      {/* Form Login & Konfigurasi */}
      <div style={S.card}>
        <p style={S.cardTitle}>Konfigurasi</p>
        <div style={S.grid2}>
          <div>
            <label style={S.label}>Username Coretax</label>
            <input
              style={S.input}
              type="text"
              placeholder="NPWP / username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
          <div>
            <label style={S.label}>Password</label>
            <input
              style={S.input}
              type="password"
              placeholder="••••••••"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
          <div>
            <label style={S.label}>Masa Pajak</label>
            <select
              style={S.select}
              value={form.masa_pajak}
              onChange={(e) => setForm({ ...form, masa_pajak: e.target.value })}
            >
              {MASA_PAJAK_OPTIONS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={S.label}>Maks. Halaman <span style={{ color: "#475569" }}>(opsional, kosong = semua)</span></label>
            <input
              style={S.input}
              type="number"
              placeholder="contoh: 5"
              min={1}
              value={form.max_pages}
              onChange={(e) => setForm({ ...form, max_pages: e.target.value })}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>
        </div>

        <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
          <button
            style={{ ...S.btnPrimary, opacity: loading ? 0.6 : 1 }}
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

      {/* Status & Progress */}
      {job && (
        <div style={S.card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <p style={{ ...S.cardTitle, marginBottom: 0 }}>Status Job</p>
            <span style={S.statusBadge(job.status)}>
              {STATUS_ICON[job.status]}
              {job.status.toUpperCase()}
            </span>
          </div>

          {/* Stats */}
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

          {/* Progress bar */}
          <div style={S.progressBar(pct)}>
            <div style={S.progressFill(pct)} />
          </div>

          {/* Log */}
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
        </div>
      )}

      {/* Empty log state */}
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
