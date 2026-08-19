import { Settings } from "lucide-react";

// Placeholder — one per team under the new SETUP nav section (same team
// names as DASHBOARD). No configuration options exist yet; this just
// gives each nav entry a working page to land on instead of a dead link.
export default function SetupPage({ team }) {
  return (
    <div className="p-6">
      <div style={{
        background: "#f1f5f9",
        borderRadius: 20,
        boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
        padding: "56px 24px",
        textAlign: "center",
      }}>
        <div style={{
          width: 56, height: 56, borderRadius: 16,
          background: "rgba(37,99,235,0.09)",
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 16px",
        }}>
          <Settings size={26} style={{ color: "#2563eb" }} />
        </div>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1e293b", margin: 0 }}>{team} Setup</h2>
        <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 8 }}>
          Configuration options for {team} will appear here.
        </p>
      </div>
    </div>
  );
}
