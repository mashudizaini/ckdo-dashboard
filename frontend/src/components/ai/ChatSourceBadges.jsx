const DEPT_COLORS = {
  General:    { bg: "#e2e8f0", color: "#475569" },
  HR:         { bg: "#fef3c7", color: "#d97706" },
  Accounting: { bg: "#dbeafe", color: "#1d4ed8" },
  PAC:        { bg: "#dcfce7", color: "#16a34a" },
  Purchasing: { bg: "#ede9fe", color: "#7c3aed" },
  IT:         { bg: "#fee2e2", color: "#dc2626" },
};

export function DeptBadge({ department }) {
  const cfg = DEPT_COLORS[department] || DEPT_COLORS.General;
  return (
    <span className="text-[10px] font-semibold rounded-full px-2 py-0.5" style={{ background: cfg.bg, color: cfg.color }}>
      {department}
    </span>
  );
}

export function ToolBadge({ source }) {
  const argsText = Object.entries(source.arguments || {})
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  const failed = !!source.error;
  return (
    <span
      title={failed ? source.error : `${source.row_count} row${source.row_count !== 1 ? "s" : ""} returned`}
      className={`text-[10px] rounded-full border px-2 py-0.5 ${
        failed
          ? "border-red-700/50 bg-red-500/10 text-red-400"
          : "border-gray-600 bg-gray-900 text-gray-400"
      }`}
    >
      🛠️ {source.tool}{argsText ? `(${argsText})` : ""}
    </span>
  );
}

/** modeKey: "oracle" — dispatches to the right badge. Policy Chat doesn't
 * show a source list (see Chatbot.jsx/ChatWidget.jsx — it shows follow-up
 * suggestion chips instead), so this is never called with modeKey
 * "policy". */
export function renderSource(modeKey, s, j) {
  if (modeKey === "oracle") return <ToolBadge key={j} source={s} />;
  return null;
}
