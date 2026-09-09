/**
 * Shared presentation primitives for the Overtime module.
 *
 * Matches the light neumorphic language already used by HRTodoList.jsx /
 * HRCvScreening.jsx (inline styles, NEU shadow tokens, #f1f5f9 surface)
 * rather than the older dark Tailwind cards elsewhere in HR.jsx — this
 * module is one of the newest screens and the rest of HR is migrating this
 * way.
 */
import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";

export const NEU = {
  bg: "#f1f5f9",
  surface: "#ffffff",
  out: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  outSm: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  in: "inset 0 1px 3px rgba(15,23,42,0.07)",
  inDeep: "inset 0 2px 5px rgba(15,23,42,0.09)",
};

export const TEXT = { strong: "#1e293b", body: "#475569", muted: "#94a3b8" };

/* ── Status vocabulary. Kept in one place so the same state never renders
      under two different names on two different tabs. ──────────────────── */
export const PLAN_STATUS = {
  draft:       { label: "Draft",             bg: "#e2e8f0", color: "#475569" },
  submitted:   { label: "Waiting Team Head", bg: "#fef3c7", color: "#b45309" },
  th_approved: { label: "Waiting Dept Head", bg: "#fde68a", color: "#a16207" },
  revision:    { label: "Revision Required", bg: "#ffedd5", color: "#c2410c" },
  approved:    { label: "Approved",          bg: "#dcfce7", color: "#15803d" },
  rejected:    { label: "Rejected",          bg: "#fee2e2", color: "#b91c1c" },
  cancelled:   { label: "Cancelled",         bg: "#e2e8f0", color: "#64748b" },
};

export const RZ_STATUS = {
  pending:     { label: "To Be Realized",    bg: "#dbeafe", color: "#1d4ed8" },
  draft:       { label: "Draft",             bg: "#e2e8f0", color: "#475569" },
  submitted:   { label: "Waiting Team Head", bg: "#fef3c7", color: "#b45309" },
  th_approved: { label: "Waiting Dept Head", bg: "#fde68a", color: "#a16207" },
  dh_approved: { label: "Waiting HRGA",      bg: "#e9d5ff", color: "#7e22ce" },
  revision:    { label: "Revision Required", bg: "#ffedd5", color: "#c2410c" },
  approved:    { label: "Approved (Final)",  bg: "#dcfce7", color: "#15803d" },
  rejected:    { label: "Rejected",          bg: "#fee2e2", color: "#b91c1c" },
};

export const TYPE_BADGE = {
  weekday: { label: "Weekday",           bg: "#e0f2fe", color: "#0369a1" },
  weekend: { label: "Weekend / Holiday", bg: "#f3e8ff", color: "#7e22ce" },
};

export const CATEGORY_BADGE = {
  adhoc:   { label: "Ad Hoc",  bg: "#fef9c3", color: "#a16207" },
  routine: { label: "Routine", bg: "#ecfccb", color: "#4d7c0f" },
};

export const ROLE_LABEL = {
  member: "Member", team_head: "Team Head", dept_head: "Department Head", hrga_admin: "HRGA Admin",
};

export function Pill({ map, value, fallback }) {
  const cfg = map?.[value] || { label: fallback ?? value ?? "—", bg: "#e2e8f0", color: "#64748b" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "3px 10px", borderRadius: 20,
      fontSize: 11, fontWeight: 700, background: cfg.bg, color: cfg.color, whiteSpace: "nowrap",
    }}>
      {cfg.label}
    </span>
  );
}

export function Card({ children, style, padding = 18 }) {
  return (
    <div style={{ background: NEU.bg, boxShadow: NEU.out, borderRadius: 16, padding, ...style }}>
      {children}
    </div>
  );
}

export function SectionTitle({ icon: Icon, title, subtitle, right }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
        {Icon && (
          <span style={{
            width: 30, height: 30, borderRadius: 9, background: "rgba(37,99,235,0.10)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <Icon size={15} color="#2563eb" />
          </span>
        )}
        <div>
          <h3 style={{ fontSize: 13.5, fontWeight: 700, color: TEXT.strong, margin: 0 }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 11.5, color: TEXT.muted, margin: "3px 0 0" }}>{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

const BTN_VARIANTS = {
  primary: { background: "linear-gradient(135deg,#2563eb,#1d4ed8)", color: "#fff", shadow: "0 3px 10px rgba(37,99,235,0.32)" },
  success: { background: "linear-gradient(135deg,#16a34a,#15803d)", color: "#fff", shadow: "0 3px 10px rgba(22,163,74,0.30)" },
  danger:  { background: "linear-gradient(135deg,#dc2626,#b91c1c)", color: "#fff", shadow: "0 3px 10px rgba(220,38,38,0.28)" },
  warning: { background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#fff", shadow: "0 3px 10px rgba(245,158,11,0.28)" },
  ghost:   { background: NEU.bg, color: TEXT.body, shadow: NEU.outSm },
};

export function Btn({ icon: Icon, children, variant = "ghost", loading, disabled, style, ...rest }) {
  const v = BTN_VARIANTS[variant] || BTN_VARIANTS.ghost;
  const off = disabled || loading;
  return (
    <button
      disabled={off}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
        padding: "7px 14px", borderRadius: 10, border: "none", cursor: off ? "not-allowed" : "pointer",
        fontSize: 12, fontWeight: 700, background: v.background, color: v.color,
        boxShadow: off ? "none" : v.shadow, opacity: off ? 0.55 : 1,
        transition: "opacity .15s ease, transform .1s ease", whiteSpace: "nowrap", ...style,
      }}
      {...rest}
    >
      {loading ? <Loader2 size={13} style={{ animation: "spin 0.9s linear infinite" }} /> : Icon ? <Icon size={13} /> : null}
      {children}
    </button>
  );
}

export function Field({ label, required, hint, children, style }) {
  return (
    <div style={style}>
      <label style={{ fontSize: 10, fontWeight: 700, color: TEXT.muted, display: "block", marginBottom: 4, letterSpacing: "0.04em" }}>
        {label}{required && <span style={{ color: "#dc2626" }}> *</span>}
      </label>
      {children}
      {hint && <p style={{ fontSize: 10.5, color: TEXT.muted, margin: "4px 0 0" }}>{hint}</p>}
    </div>
  );
}

const inputBase = {
  width: "100%", fontSize: 12.5, padding: "8px 11px", borderRadius: 10, border: "none",
  background: NEU.bg, color: TEXT.strong, boxShadow: NEU.in, outline: "none", boxSizing: "border-box",
};

export const Input    = (p) => <input    {...p} style={{ ...inputBase, ...p.style }} />;
export const Textarea = (p) => <textarea {...p} style={{ ...inputBase, resize: "vertical", ...p.style }} />;
export const Select   = (p) => (
  <select {...p} style={{ ...inputBase, boxShadow: NEU.outSm, cursor: "pointer", ...p.style }} />
);

export function StatCard({ icon: Icon, label, value, unit, accent = "#2563eb", hint, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: NEU.bg, boxShadow: NEU.out, borderRadius: 14, padding: "14px 16px",
        cursor: onClick ? "pointer" : "default", display: "flex", flexDirection: "column", gap: 8,
        borderLeft: `3px solid ${accent}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        {Icon && <Icon size={13} color={accent} />}
        <span style={{ fontSize: 10.5, fontWeight: 700, color: TEXT.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>
          {label}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
        <span style={{ fontSize: 24, fontWeight: 800, color: TEXT.strong, lineHeight: 1 }}>{value}</span>
        {unit && <span style={{ fontSize: 11.5, fontWeight: 700, color: TEXT.muted }}>{unit}</span>}
      </div>
      {hint && <span style={{ fontSize: 10.5, color: TEXT.muted }}>{hint}</span>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
      {tabs.map((t) => {
        const on = active === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "7px 15px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
              background: NEU.bg, cursor: "pointer", color: on ? "#2563eb" : TEXT.body,
              boxShadow: on ? NEU.inDeep : NEU.outSm, transition: "all .18s ease",
            }}
          >
            {t.icon && <t.icon size={13} />}
            {t.label}
            {t.badge > 0 && (
              <span style={{
                minWidth: 17, height: 17, padding: "0 5px", borderRadius: 9, background: "#dc2626",
                color: "#fff", fontSize: 10, fontWeight: 800, display: "inline-flex",
                alignItems: "center", justifyContent: "center",
              }}>
                {t.badge > 99 ? "99+" : t.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Table({ columns, rows, empty = "No data.", rowKey = (r, i) => r.id ?? i, onRowClick, maxHeight }) {
  return (
    <div style={{
      borderRadius: 12, background: NEU.surface, boxShadow: NEU.outSm,
      overflowX: "auto", overflowY: maxHeight ? "auto" : "visible", maxHeight,
    }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "#f8fafc", position: maxHeight ? "sticky" : "static", top: 0, zIndex: 1 }}>
            {columns.map((c) => (
              <th key={c.key} style={{
                padding: "9px 11px", textAlign: c.align || "left", fontSize: 10,
                fontWeight: 800, color: TEXT.muted, letterSpacing: "0.05em", textTransform: "uppercase",
                whiteSpace: "nowrap", borderBottom: "1px solid #e2e8f0",
              }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} style={{ padding: "26px 12px", textAlign: "center", color: TEXT.muted, fontSize: 12 }}>
                {empty}
              </td>
            </tr>
          ) : rows.map((r, i) => (
            <tr
              key={rowKey(r, i)}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              style={{ borderBottom: "1px solid #f1f5f9", cursor: onRowClick ? "pointer" : "default" }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "#f8fafc"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              {columns.map((c) => (
                <td key={c.key} style={{
                  padding: "9px 11px", textAlign: c.align || "left", color: TEXT.body,
                  whiteSpace: c.wrap ? "normal" : "nowrap", fontFamily: c.mono ? "ui-monospace, monospace" : undefined,
                  maxWidth: c.maxWidth,
                }}>
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

export function Modal({ open, title, onClose, children, width = 620, footer }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 60,
        display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: width, background: NEU.bg, borderRadius: 16,
          boxShadow: "0 20px 50px rgba(15,23,42,0.28)", overflow: "hidden",
        }}
      >
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 18px", borderBottom: "1px solid #e2e8f0", background: NEU.surface,
        }}>
          <h3 style={{ fontSize: 13.5, fontWeight: 700, color: TEXT.strong, margin: 0 }}>{title}</h3>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: TEXT.muted, display: "flex" }}>
            <X size={17} />
          </button>
        </div>
        <div style={{ padding: 18 }}>{children}</div>
        {footer && (
          <div style={{
            display: "flex", justifyContent: "flex-end", gap: 8, padding: "12px 18px",
            borderTop: "1px solid #e2e8f0", background: NEU.surface,
          }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

const ALERT_CFG = {
  error:   { bg: "#fee2e2", color: "#b91c1c", Icon: AlertTriangle },
  success: { bg: "#dcfce7", color: "#15803d", Icon: CheckCircle2 },
  info:    { bg: "#dbeafe", color: "#1d4ed8", Icon: Info },
  warning: { bg: "#fef3c7", color: "#b45309", Icon: AlertTriangle },
};

export function Alert({ kind = "info", children, onClose, style }) {
  if (!children) return null;
  const cfg = ALERT_CFG[kind] || ALERT_CFG.info;
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 12px", borderRadius: 10,
      background: cfg.bg, color: cfg.color, fontSize: 12, fontWeight: 600, marginBottom: 12, ...style,
    }}>
      <cfg.Icon size={14} style={{ flexShrink: 0, marginTop: 1 }} />
      <span style={{ flex: 1 }}>{children}</span>
      {onClose && (
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: cfg.color, display: "flex" }}>
          <X size={13} />
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading..." }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 30, color: TEXT.muted, fontSize: 12 }}>
      <Loader2 size={15} style={{ animation: "spin 0.9s linear infinite" }} />
      {label}
    </div>
  );
}

export function Empty({ icon: Icon, title, hint, action }) {
  return (
    <div style={{ textAlign: "center", padding: "34px 16px" }}>
      {Icon && <Icon size={30} color="#cbd5e1" style={{ marginBottom: 10 }} />}
      <p style={{ fontSize: 13, fontWeight: 700, color: TEXT.body, margin: 0 }}>{title}</p>
      {hint && <p style={{ fontSize: 11.5, color: TEXT.muted, margin: "5px 0 0" }}>{hint}</p>}
      {action && <div style={{ marginTop: 13 }}>{action}</div>}
    </div>
  );
}

/* ── Formatting helpers shared by every tab ─────────────────────────────── */

export const fmtDate = (iso) => (iso
  ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
  : "—");

export const fmtDateTime = (iso) => (iso
  ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
  : "—");

export const fmtHours = (h) => `${Number(h ?? 0).toFixed(2)} h`;

export const fmtIDR = (n) => (Number(n) || 0).toLocaleString("id-ID", {
  style: "currency", currency: "IDR", minimumFractionDigits: 0, maximumFractionDigits: 0,
});

/** Axios error -> the message the backend actually sent, never "[object Object]". */
export const errMsg = (e, fallback = "Something went wrong.") => {
  const d = e?.detail ?? e?.response?.data?.detail ?? e?.message;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join("; ");
  return fallback;
};

/** Signed hours, so a gap reads "+0.50 h" / "-0.25 h" instead of just a number. */
export const fmtGap = (h) => {
  const n = Number(h ?? 0);
  if (Math.abs(n) < 0.005) return "0.00 h";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)} h`;
};

export const gapColor = (h) => {
  const n = Number(h ?? 0);
  if (Math.abs(n) < 0.005) return TEXT.muted;
  return n > 0 ? "#b45309" : "#0369a1";
};
