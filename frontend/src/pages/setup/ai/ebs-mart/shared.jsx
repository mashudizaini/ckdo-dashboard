import { useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";

export const errMsg = (e) => e?.response?.data?.detail || e?.message || "Terjadi kesalahan";

export const fmtNum = (v) =>
  typeof v === "number" ? v.toLocaleString("id-ID", { maximumFractionDigits: 2 }) : v ?? "—";

export const fmtDate = (v) => {
  if (!v) return "—";
  const d = new Date(String(v).replace(" ", "T"));
  return isNaN(d) ? v : d.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
};

export function Card({ title, subtitle, icon: Icon, actions, children, className = "" }) {
  return (
    <div className={`rounded-xl border border-gray-800 bg-gray-900 ${className}`}>
      {(title || actions) && (
        <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between gap-3">
          <div className="flex items-start gap-2.5 min-w-0">
            {Icon && <Icon size={16} className="text-blue-400 shrink-0 mt-0.5" />}
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
              {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

const STATUS_STYLE = {
  OK: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  RUNNING: "border-blue-500/40 bg-blue-500/10 text-blue-300",
  FAILED: "border-red-500/40 bg-red-500/10 text-red-300",
  ERROR: "border-red-500/40 bg-red-500/10 text-red-300",
  TIMEOUT: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  DENIED: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  REJECTED: "border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-300",
  SKIPPED: "border-gray-600 bg-gray-800 text-gray-400",
};

export function Badge({ children, tone }) {
  const cls = STATUS_STYLE[tone || children] || "border-gray-700 bg-gray-800 text-gray-400";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${cls}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, loading, disabled, variant = "primary", icon: Icon, type = "button", title }) {
  const styles = {
    primary: "bg-blue-600 hover:bg-blue-500 text-white",
    ghost: "border border-gray-700 bg-gray-800 hover:border-gray-600 text-gray-300",
    danger: "border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled || loading} title={title}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${styles[variant]}`}>
      {loading ? <Loader2 size={13} className="animate-spin" /> : Icon ? <Icon size={13} /> : null}
      {children}
    </button>
  );
}

export function CopyButton({ text, label = "Salin" }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <Button variant="ghost" icon={done ? Check : Copy} onClick={copy}>
      {done ? "Tersalin" : label}
    </Button>
  );
}

export function Spinner() {
  return (
    <div className="p-8 flex justify-center">
      <Loader2 size={20} className="animate-spin text-gray-600" />
    </div>
  );
}

export function ErrorBox({ children }) {
  if (!children) return null;
  return (
    <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-300 whitespace-pre-wrap">
      {children}
    </div>
  );
}

/** Tool result: {as_of, columns, rows, row_count, truncated, sql_used}. */
export function ResultTable({ result }) {
  if (!result) return null;
  if (!result.columns) {
    return (
      <pre className="text-[11px] text-gray-300 bg-gray-950 rounded-lg p-3 overflow-auto max-h-96">
        {JSON.stringify(result, null, 2)}
      </pre>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
        <Badge tone="OK">{result.row_count} baris</Badge>
        {result.truncated && <Badge tone="TIMEOUT">dipotong di 500 baris</Badge>}
        <span>Data per <b className="text-gray-300">{result.as_of || "belum pernah di-load"}</b></span>
        {result.marts?.length > 0 && <span className="text-gray-600">· {result.marts.map((m) => `mart.${m}`).join(", ")}</span>}
      </div>
      <div className="overflow-auto max-h-[420px] rounded-lg border border-gray-800">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-gray-800 text-gray-400">
            <tr>{result.columns.map((c) => <th key={c} className="px-2.5 py-1.5 text-left font-semibold whitespace-nowrap">{c}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {result.rows.map((r, i) => (
              <tr key={i} className="hover:bg-gray-800/40">
                {r.map((v, j) => (
                  <td key={j} className={`px-2.5 py-1 whitespace-nowrap ${typeof v === "number" ? "text-right tabular-nums text-gray-200" : "text-gray-300"}`}>
                    {v === null ? <span className="text-gray-600">∅</span> : fmtNum(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {result.rows.length === 0 && <p className="px-3 py-6 text-center text-xs text-gray-500">Tidak ada baris.</p>}
      </div>
      {result.sql_used && (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-gray-500 hover:text-gray-300">SQL yang dipakai</summary>
          <pre className="mt-1 bg-gray-950 rounded-lg p-3 text-gray-300 whitespace-pre-wrap">{result.sql_used}</pre>
        </details>
      )}
    </div>
  );
}

export const inputCls =
  "rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-200 outline-none focus:border-blue-500";
