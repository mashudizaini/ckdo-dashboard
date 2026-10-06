/**
 * Oracle EBS Network Monitoring — shared UI for this module's tabs.
 * Same visual language as VpnAccessMonitoring.jsx (local Panel/Btn/Field),
 * kept in one file here because this module has eight tabs, not one.
 */
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from "lucide-react";

export const SERIES = ["#2a78d6", "#eb6834"];
export const STATUS = {
  ok:      { color: "#0ca30c", bg: "rgba(12,163,12,0.08)",  label: "Normal",   Icon: CheckCircle2 },
  warn:    { color: "#b77d00", bg: "rgba(250,178,25,0.14)", label: "Waspada",  Icon: AlertTriangle },
  crit:    { color: "#d03b3b", bg: "rgba(208,59,59,0.09)",  label: "Kritis",   Icon: XCircle },
  unknown: { color: "#64748b", bg: "rgba(100,116,139,0.08)", label: "Belum ada data", Icon: HelpCircle },
};

export function Panel({ title, subtitle, action, children, pad = true }) {
  return (
    <div style={{ background: "#ffffff", borderRadius: 16, boxShadow: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", marginBottom: 16 }}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 flex-wrap" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{title}</h3>
            {subtitle && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{subtitle}</p>}
          </div>
          <div className="flex gap-2 flex-wrap">{action}</div>
        </div>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </div>
  );
}

export function Btn({ onClick, children, variant = "default", disabled, icon: Icon, size = "md", type = "button", spin }) {
  const variants = {
    default: { bg: "#f1f5f9", color: "#334155" },
    primary: { bg: "#2563eb", color: "#ffffff" },
    danger: { bg: "#dc2626", color: "#ffffff" },
    ghost: { bg: "transparent", color: "#2563eb" },
  };
  const v = variants[variant] || variants.default;
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className="flex items-center gap-1.5 rounded-lg transition-all"
      style={{
        background: v.bg, color: v.color, fontWeight: 700, border: "none",
        padding: size === "sm" ? "5px 10px" : "7px 14px", fontSize: size === "sm" ? 11 : 12,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
      }}>
      {Icon && <Icon size={size === "sm" ? 12 : 13} className={spin ? "animate-spin" : ""} />}{children}
    </button>
  );
}

export const inputStyle = {
  width: "100%", padding: "7px 10px", borderRadius: 8, fontSize: 12.5,
  border: "1px solid rgba(15,23,42,0.14)", background: "#ffffff", color: "#0f172a",
};

export function Field({ label, hint, children }) {
  return (
    <div>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4 }}>{label}</label>
      {children}
      {hint && <p style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 3 }}>{hint}</p>}
    </div>
  );
}

export function Empty({ children }) {
  return <p style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "24px 0" }}>{children}</p>;
}

export function Spinner() {
  return <div className="flex justify-center py-16"><span className="animate-spin" style={{ width: 22, height: 22, border: "2px solid #cbd5e1", borderTopColor: "#2563eb", borderRadius: "50%" }} /></div>;
}

export function Level({ level = "unknown", label, size = "md" }) {
  const s = STATUS[level] || STATUS.unknown;
  const Icon = s.Icon;
  return (
    <span className="inline-flex items-center gap-1 rounded-full" style={{
      background: s.bg, color: s.color, fontWeight: 700,
      fontSize: size === "sm" ? 10.5 : 11.5, padding: size === "sm" ? "1px 7px" : "3px 9px",
    }}>
      <Icon size={size === "sm" ? 11 : 12} />{label || s.label}
    </span>
  );
}

export function Stat({ label, value, unit, level, hint }) {
  const s = level ? STATUS[level] : null;
  return (
    <div className="rounded-xl px-3.5 py-2.5" style={{ background: "#f8fafc", border: "1px solid rgba(0,0,0,0.05)", minWidth: 110 }}>
      <p style={{ fontSize: 10.5, color: "#64748b", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>{label}</p>
      <p style={{ fontSize: 17, fontWeight: 800, color: "#0f172a", marginTop: 2 }}>
        {value ?? "—"}{value != null && unit ? <span style={{ fontSize: 11, fontWeight: 600, color: "#64748b", marginLeft: 3 }}>{unit}</span> : null}
      </p>
      {(s || hint) && (
        <div className="flex items-center gap-1 mt-0.5" style={{ fontSize: 10.5, color: s ? s.color : "#94a3b8", fontWeight: 600 }}>
          {s && <s.Icon size={10} />}{hint || s?.label}
        </div>
      )}
    </div>
  );
}

export function Table({ columns, rows, empty = "Tidak ada data.", onRowClick }) {
  if (!rows?.length) return <Empty>{empty}</Empty>;
  return (
    <div className="rounded-xl overflow-x-auto" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
            {columns.map((c) => <td key={c.key} className="px-3 py-2 whitespace-nowrap" style={{ textAlign: c.align || "left" }}>{c.label}</td>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} onClick={onRowClick ? () => onRowClick(r) : undefined}
              style={{ borderTop: "1px solid rgba(0,0,0,0.05)", cursor: onRowClick ? "pointer" : "default" }}
              className={onRowClick ? "hover:bg-slate-50" : ""}>
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2" style={{ color: "#334155", textAlign: c.align || "left", whiteSpace: c.wrap ? "normal" : "nowrap" }}>
                  {c.render ? c.render(r) : (r[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RawBlock({ title = "Output mentah", text }) {
  if (!text) return null;
  return (
    <details className="mt-2">
      <summary style={{ fontSize: 11, color: "#64748b", cursor: "pointer" }}>{title}</summary>
      <pre style={{ background: "#0f172a", color: "#e2e8f0", fontSize: 10.5, padding: 10, borderRadius: 8, marginTop: 6, maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap" }}>{text}</pre>
    </details>
  );
}

export function Note({ children, tone = "info" }) {
  const tones = {
    info: { bg: "rgba(37,99,235,0.06)", color: "#1e40af" },
    warn: { bg: "rgba(250,178,25,0.12)", color: "#854d0e" },
  };
  const t = tones[tone] || tones.info;
  return <div className="rounded-xl px-4 py-3" style={{ background: t.bg, color: t.color, fontSize: 12, lineHeight: 1.55 }}>{children}</div>;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch (_) { return iso; }
}

export function fmtTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }); } catch (_) { return iso; }
}

export function errText(e, fallback = "Gagal") {
  const d = e?.response?.data?.detail ?? e?.detail;
  if (typeof d === "string") return d;
  return e?.message || fallback;
}

/** Same thresholds the backend uses (analysis.probe_level). */
export function probeLevel(p, t) {
  if (!p || p.skipped) return "unknown";
  if (p.loss_pct == null || p.loss_pct >= 100) return "crit";
  let lvl = "ok";
  const rank = { ok: 0, warn: 1, crit: 2 };
  const up = (l) => { if (rank[l] > rank[lvl]) lvl = l; };
  if (p.loss_pct >= t.loss_crit) up("crit"); else if (p.loss_pct >= t.loss_warn) up("warn");
  const avg = p.rtt_avg || 0, jit = p.jitter_ms || 0;
  if (avg >= t.latency_crit || jit >= t.jitter_crit) up("crit");
  else if (avg >= t.latency_warn || jit >= t.jitter_warn) up("warn");
  if (p.http_status >= 500) up("crit");
  return lvl;
}

export const VERDICT_LABEL = {
  A: { text: "Case A · LAN HO", level: "warn" },
  B: { text: "Case B · WAN/VPN", level: "crit" },
  C: { text: "Case C · EBS/DB", level: "warn" },
  D: { text: "Case D · Laptop", level: "warn" },
  OK: { text: "OK", level: "ok" },
};
