/**
 * "Is now a good time to back up?" — the question an operator actually asks
 * before pressing Run, which capacity preflight does not answer.
 *
 * Both clocks are shown on purpose. The dashboard stores naive UTC while the
 * database server runs WIB: the failed run of 2026-10-06 is recorded as started
 * 12:55 and its files are stamped 19:55 — one moment written two ways. Someone
 * scheduling "22:00" without being told which clock that is would be seven
 * hours wrong, so the schedule field below reads the server clock and says so.
 */
import { useEffect, useState } from "react";
import { Loader2, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock } from "lucide-react";
import { ebsBackupApi } from "@/api/ebsBackup";

const LEVEL = {
  good:    { color: "#16a34a", bg: "rgba(22,163,74,0.12)",  Icon: CheckCircle2 },
  caution: { color: "#d97706", bg: "rgba(217,119,6,0.12)",  Icon: AlertTriangle },
  avoid:   { color: "#dc2626", bg: "rgba(220,38,38,0.12)",  Icon: XCircle },
};

export default function BackupReadiness({ onServerClock }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await ebsBackupApi.readiness();
      setData(d);
      // The parent's schedule field needs the server clock, not the browser's —
      // the browser may be in any timezone and is not the clock that matters.
      onServerClock?.(d?.clock?.db_server_time || null);
    } catch (e) {
      setError(e?.detail || e?.message || "Tidak bisa membaca kondisi database");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  // Refresh every 30s: the verdict is about right now, and a stale "quiet"
  // reading is exactly the kind of confident-but-wrong answer to avoid.
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 30000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (tick) load(); /* eslint-disable-next-line */ }, [tick]);

  if (!data && busy) {
    return (
      <p className="flex items-center gap-2" style={{ fontSize: 12, color: "#64748b" }}>
        <Loader2 size={13} className="animate-spin" /> membaca kondisi database…
      </p>
    );
  }
  if (error) return <p style={{ fontSize: 12, color: "#f87171" }}>{error}</p>;
  if (!data) return null;

  const v = data.verdict || {};
  const L = LEVEL[v.level] || LEVEL.caution;
  const s = data.sessions || {};
  const cr = data.concurrent_requests || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Clocks */}
      <div className="flex items-center gap-4 flex-wrap" style={{ fontSize: 11.5, color: "#94a3b8" }}>
        <span className="flex items-center gap-1.5">
          <Clock size={12} />
          <b style={{ color: "#e2e8f0" }}>{data.clock?.db_server_time}</b>
          <span>waktu server database ({data.clock?.db_server_tz_offset})</span>
        </span>
        <span>· dashboard UTC {data.clock?.dashboard_utc}</span>
        <button onClick={load} disabled={busy} title="Muat ulang"
          style={{ background: "none", border: "none", cursor: "pointer", color: "#60a5fa", lineHeight: 0 }}>
          {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
      </div>

      {/* Verdict */}
      <div style={{ background: L.bg, border: `1px solid ${L.color}55`, borderRadius: 10, padding: "10px 12px" }}>
        <p className="flex items-center gap-2" style={{ fontSize: 13, fontWeight: 700, color: L.color }}>
          <L.Icon size={15} /> {v.headline}
        </p>
        <ul style={{ margin: "6px 0 0 20px", fontSize: 11.5, color: "#cbd5e1", listStyle: "disc" }}>
          {(v.reasons || []).map((r, i) => <li key={i} style={{ marginTop: 2 }}>{r}</li>)}
        </ul>
      </div>

      {/* Numbers */}
      <div className="flex gap-3 flex-wrap" style={{ fontSize: 11.5 }}>
        <Stat label="Sesi user aktif" value={s.active_user} sub={`dari ${s.total_user ?? "?"} terhubung`} />
        <Stat label="Concurrent request" value={cr.running ?? "—"} sub="EBS, sedang berjalan" />
        <Stat label="Ukuran database" value={`${data.db_size_gb ?? "?"} GB`} sub="datafile" />
        <Stat label="Archivelog aktif" value={`${data.archivelog?.active_gb ?? "?"} GB`}
          sub={`${data.archivelog?.last_24h_gb ?? "?"} GB dalam 24 jam`} />
      </div>

      {/* Who is working right now */}
      {(s.longest_active || []).length > 0 && (
        <details>
          <summary style={{ fontSize: 11.5, color: "#94a3b8", cursor: "pointer" }}>
            Sesi yang sedang berjalan ({(s.longest_active || []).length} terlama)
          </summary>
          <table className="w-full" style={{ fontSize: 11, marginTop: 6 }}>
            <thead>
              <tr style={{ color: "#64748b", textAlign: "left" }}>
                <th style={{ padding: "2px 6px" }}>SID</th>
                <th style={{ padding: "2px 6px" }}>User</th>
                <th style={{ padding: "2px 6px" }}>Module</th>
                <th style={{ padding: "2px 6px", textAlign: "right" }}>Menit</th>
                <th style={{ padding: "2px 6px" }}>Event</th>
              </tr>
            </thead>
            <tbody>
              {s.longest_active.map((r) => (
                <tr key={r.sid} style={{ color: "#cbd5e1" }}>
                  <td style={{ padding: "2px 6px" }}>{r.sid}</td>
                  <td style={{ padding: "2px 6px" }}>{r.username}</td>
                  <td style={{ padding: "2px 6px" }}>{r.module}</td>
                  <td style={{ padding: "2px 6px", textAlign: "right" }}>{r.running_minutes}</td>
                  <td style={{ padding: "2px 6px", color: "#64748b" }}>{r.event}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {(cr.detail || []).length > 0 && (
        <details>
          <summary style={{ fontSize: 11.5, color: "#94a3b8", cursor: "pointer" }}>
            Concurrent request berjalan ({cr.detail.length})
          </summary>
          <ul style={{ margin: "6px 0 0 18px", fontSize: 11, color: "#cbd5e1" }}>
            {cr.detail.map((r) => (
              <li key={r.request_id}>#{r.request_id} {r.program} — {r.running_minutes} menit</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div style={{ background: "rgba(148,163,184,0.08)", borderRadius: 8, padding: "6px 10px", minWidth: 128 }}>
      <div style={{ fontSize: 10.5, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0" }}>{value}</div>
      <div style={{ fontSize: 10, color: "#64748b" }}>{sub}</div>
    </div>
  );
}
