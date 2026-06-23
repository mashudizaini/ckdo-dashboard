const STATUS_CONFIG = {
  NEW:        { label: "Baru",        color: "#6b7280", bg: "#f3f4f6" },
  VALIDATED:  { label: "Tervalidasi", color: "#1d4ed8", bg: "#dbeafe" },
  PROCESSING: { label: "Diproses",    color: "#d97706", bg: "#fef3c7" },
  INTERFACED: { label: "Interfaced",  color: "#7c3aed", bg: "#ede9fe" },
  SUBMITTED:  { label: "Submitted",   color: "#0369a1", bg: "#e0f2fe" },
  IMPORTED:   { label: "Selesai",     color: "#15803d", bg: "#dcfce7" },
  ERROR:      { label: "Error",       color: "#b91c1c", bg: "#fee2e2" },
};
export default function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: "#374151", bg: "#e5e7eb" };
  return (
    <span style={{ display:"inline-block", padding:"2px 10px", borderRadius:"12px",
      fontSize:"12px", fontWeight:"600", color:cfg.color, backgroundColor:cfg.bg }}>
      {cfg.label}
    </span>
  );
}
