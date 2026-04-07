import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { LogOut, ExternalLink, Shield, Clock } from "lucide-react";
import logo from "@/assets/LOGO-ONLY.png";

const APPS = [
  { id: "dashboard",  name: "CKDO Dashboard",   desc: "Monitoring & reporting",       url: "/dashboard/it",  status: "sso",     emoji: "📊", role: "app:dashboard"  },
  { id: "eticket",    name: "E-Ticket System",   desc: "Helpdesk & ticketing",         url: "http://helpdesk.ckd-otto.com/login", status: "sso", emoji: "🎫", role: "app:eticket" },
  { id: "portal-hr",  name: "HR Portal",         desc: "Employee self-service",        url: "https://portal.ckd-otto.com/auth/login", status: "pending", emoji: "👥", role: "app:portal-hr" },
  { id: "talenta",    name: "Talenta HR",         desc: "Attendance & payroll",         url: "https://hr.talenta.co", status: "pending", emoji: "🕐", role: "app:talenta" },
  { id: "oracle-ebs", name: "Oracle EBS",         desc: "Enterprise resource planning", url: "http://ckd-app.ckd-otto.com:8000/OA_HTML/AppsLocalLogin.jsp", status: "direct", emoji: "🔴", role: "app:oracle-ebs" },
  { id: "ovm",        name: "OVM Manager",        desc: "Oracle VM virtualization",     url: "https://172.21.2.200:7002/ovm/console/faces/login.jspx", status: "direct", emoji: "🖥️", role: "app:ovm" },
  { id: "idrac",      name: "Dell iDRAC",         desc: "Server remote management",     url: "https://172.21.2.199/restgui/start.html?login", status: "direct", emoji: "🔧", role: "app:idrac" },
  { id: "idrac-98",   name: "Dell iDRAC 98",      desc: "Server remote management",     url: "https://172.21.2.198/restgui/start.html?login", status: "direct", emoji: "🔧", role: "app:idrac-98" },
  { id: "website",    name: "Company Website",    desc: "ckd-otto.com public site",     url: "https://ckd-otto.com", status: "direct", emoji: "🌐", role: "app:website" },
  { id: "myminio",    name: "MinIO Storage",      desc: "Object storage management",    url: "http://172.21.2.157:9001", status: "direct", emoji: "🗄️", role: "app:myminio" },
];

const STATUS_CONFIG = {
  sso:     { label: "SSO Active",  dot: "#2563eb", color: "#1d4ed8", accent: "#dbeafe" },
  pending: { label: "Integrating", dot: "#f59e0b", color: "#d97706", accent: "#fef3c7" },
  direct:  { label: "Direct Link", dot: "#8b5cf6", color: "#7c3aed", accent: "#ede9fe" },
};

// ─── Neumorphic App Card ──────────────────────────────────────────
function AppCard({ app, index, onNavigate, onDashboardClick }) {
  const [pressed, setPressed] = useState(false);
  const cfg = STATUS_CONFIG[app.status];

  const NEU_BG   = "#e8edf5";
  const SHADOW_OUT = "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff";
  const SHADOW_IN  = "inset 4px 4px 10px #c5cad8, inset -4px -4px 10px #ffffff";

  const handleClick = () => {
    if (app.id === "dashboard") { onDashboardClick(); onNavigate(app.url); return; }
    window.open(app.url, "_blank");
  };

  return (
    <div
      onClick={() => { setPressed(true); setTimeout(() => setPressed(false), 150); handleClick(); }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      onMouseLeave={() => setPressed(false)}
      style={{
        animation: `fadeUp 0.5s ease forwards`,
        animationDelay: `${index * 0.07}s`,
        opacity: 0,
        cursor: "pointer",
        width: 148,
        background: NEU_BG,
        borderRadius: 20,
        padding: "20px 12px 16px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
        boxShadow: pressed ? SHADOW_IN : SHADOW_OUT,
        transform: pressed ? "scale(0.97)" : "scale(1)",
        transition: "box-shadow 0.18s ease, transform 0.18s ease",
        userSelect: "none",
      }}
    >
      {/* Icon bubble */}
      <div style={{
        width: 58, height: 58,
        borderRadius: 16,
        background: NEU_BG,
        boxShadow: pressed
          ? `inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff`
          : `4px 4px 10px #c5cad8, -4px -4px 10px #ffffff`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 28,
        transition: "box-shadow 0.18s ease",
        position: "relative",
      }}>
        {app.emoji}
        {/* Status dot */}
        <div style={{
          position: "absolute", bottom: 4, right: 4,
          width: 10, height: 10, borderRadius: "50%",
          background: cfg.dot,
          border: `2px solid ${NEU_BG}`,
          boxShadow: app.status === "sso" ? `0 0 6px ${cfg.dot}` : "none",
          animation: app.status === "sso" ? "pulseDot 2s infinite" : "none",
        }} />
      </div>

      {/* Name */}
      <div style={{ textAlign: "center", width: "100%" }}>
        <p style={{
          fontSize: 12.5,
          fontWeight: 700,
          color: "#2d3748",
          letterSpacing: "0.01em",
          marginBottom: 3,
          lineHeight: 1.3,
        }}>
          {app.name}
        </p>
        <p style={{ fontSize: 10, color: "#94a3b8", lineHeight: 1.4 }}>
          {app.desc}
        </p>
      </div>

      {/* Status pill */}
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 10px",
        borderRadius: 20,
        background: cfg.accent,
        boxShadow: `inset 2px 2px 4px ${cfg.dot}22, inset -1px -1px 3px #ffffff88`,
      }}>
        {app.status === "sso"     && <Shield size={9} color={cfg.color} />}
        {app.status === "pending" && <Clock size={9} color={cfg.color} />}
        {app.status === "direct"  && <ExternalLink size={9} color={cfg.color} />}
        <span style={{ fontSize: 9, color: cfg.color, fontWeight: 700, letterSpacing: "0.05em" }}>
          {cfg.label.toUpperCase()}
        </span>
      </div>
    </div>
  );
}

// ─── Filter Button ────────────────────────────────────────────────
function FilterBtn({ label, active, onClick }) {
  const NEU_BG = "#e8edf5";
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 16px",
        borderRadius: 20,
        border: "none",
        background: NEU_BG,
        color: active ? "#1d4ed8" : "#64748b",
        fontSize: 11.5,
        fontWeight: 700,
        letterSpacing: "0.03em",
        cursor: "pointer",
        boxShadow: active
          ? "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff"
          : "3px 3px 8px #c5cad8, -3px -3px 8px #ffffff",
        transition: "all 0.2s ease",
      }}
    >
      {label}
    </button>
  );
}

// ─── Main App Launcher ────────────────────────────────────────────
export default function AppLauncher() {
  const { user, logout, roles } = useAuthStore();
  const { pickRandomTheme } = useThemeStore();
  const navigate = useNavigate();
  const [time, setTime] = useState(new Date());
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const isAdmin    = roles.includes("admin");
  const allowedApps = APPS.filter((a) => isAdmin || roles.includes(a.role));
  const filtered    = filter === "all" ? allowedApps : allowedApps.filter((a) => a.status === filter);

  const NEU_BG     = "#e8edf5";
  const SHADOW_OUT = "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff";

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.5; transform: scale(0.8); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
      `}</style>

      <div style={{
        minHeight: "100vh",
        background: NEU_BG,
        fontFamily: "'Inter', sans-serif",
        display: "flex",
        flexDirection: "column",
      }}>

        {/* ── HEADER ── */}
        <header style={{
          background: NEU_BG,
          boxShadow: "0 4px 16px #c5cad8, 0 -2px 8px #ffffff",
          padding: "14px 36px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          position: "sticky", top: 0, zIndex: 20,
          animation: "slideIn 0.6s ease forwards",
        }}>
          {/* Brand */}
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: NEU_BG,
              boxShadow: SHADOW_OUT,
              display: "flex", alignItems: "center", justifyContent: "center",
              padding: 4,
            }}>
              <img src={logo} alt="CKD Otto" style={{ width: 40, height: 40, objectFit: "contain" }} />
            </div>
            <div>
              <p style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", letterSpacing: "0.04em" }}>
                CKD OTTO PHARMACEUTICALS
              </p>
              <p style={{ fontSize: 10, color: "#2563eb", letterSpacing: "0.1em", fontWeight: 600 }}>
                INTERNAL APPLICATION PORTAL
              </p>
            </div>
          </div>

          {/* Right side */}
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            {/* Tagline */}
            <p style={{
              fontSize: 11, color: "#2563eb", fontWeight: 700,
              letterSpacing: "0.06em", whiteSpace: "nowrap",
              textShadow: "0 1px 2px rgba(37,99,235,0.15)",
            }}>
              BETTER LIFE THROUGH BETTER MEDICINE
            </p>

            {/* Separator */}
            <div style={{ width: 1, height: 36, background: "#c5cad8" }} />

            {/* Clock */}
            <div style={{
              background: NEU_BG,
              borderRadius: 12,
              padding: "6px 14px",
              boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`,
              textAlign: "right",
            }}>
              <p style={{ fontSize: 15, fontWeight: 600, color: "#1e293b", letterSpacing: "0.04em" }}>
                {time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
              <p style={{ fontSize: 9.5, color: "#94a3b8", letterSpacing: "0.03em" }}>
                {time.toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
              </p>
            </div>

            {/* Separator */}
            <div style={{ width: 1, height: 36, background: "#c5cad8" }} />

            {/* User */}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 38, height: 38, borderRadius: "50%",
                background: "linear-gradient(135deg, #2563eb, #0891b2)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, fontWeight: 700, color: "white",
                boxShadow: "3px 3px 8px #c5cad8, -2px -2px 6px #ffffff",
              }}>
                {user?.fullName?.charAt(0) || user?.username?.charAt(0) || "U"}
              </div>
              <div>
                <p style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>
                  {user?.fullName || user?.username || "User"}
                </p>
                <p style={{ fontSize: 10, color: "#94a3b8" }}>{user?.email || ""}</p>
              </div>
            </div>

            {/* Logout */}
            <button
              onClick={logout}
              style={{
                padding: "8px 14px",
                borderRadius: 12,
                border: "none",
                background: NEU_BG,
                color: "#dc2626",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                display: "flex", alignItems: "center", gap: 6,
                boxShadow: SHADOW_OUT,
                transition: "box-shadow 0.18s ease",
              }}
              onMouseDown={e => e.currentTarget.style.boxShadow = "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff"}
              onMouseUp={e => e.currentTarget.style.boxShadow = SHADOW_OUT}
              onMouseLeave={e => e.currentTarget.style.boxShadow = SHADOW_OUT}
            >
              <LogOut size={13} />
              Sign Out
            </button>
          </div>
        </header>

        {/* ── MAIN ── */}
        <main style={{
          flex: 1,
          padding: "16px 36px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 14,
          overflow: "hidden",
        }}>

          {/* Top bar: Welcome + Filter (satu baris horizontal) */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            animation: "fadeUp 0.5s ease 0.1s forwards", opacity: 0,
          }}>
            {/* Welcome inline */}
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{
                background: NEU_BG, borderRadius: 12, padding: "7px 16px",
                boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`,
              }}>
                <span style={{ fontSize: 10, color: "#2563eb", fontWeight: 700, letterSpacing: "0.1em" }}>
                  WELCOME BACK
                </span>
                <span style={{ fontSize: 14, fontWeight: 700, color: "#1e293b", marginLeft: 10 }}>
                  {user?.fullName || user?.username || "User"}
                </span>
                <span style={{ fontSize: 11, color: "#94a3b8", marginLeft: 8 }}>
                  — Select an application to get started
                </span>
              </div>
            </div>

            {/* Filter */}
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { key: "all",     label: "All" },
                { key: "sso",     label: "SSO Active" },
                { key: "pending", label: "Integrating" },
                { key: "direct",  label: "Direct Link" },
              ].map((f) => (
                <FilterBtn
                  key={f.key}
                  label={f.label}
                  active={filter === f.key}
                  onClick={() => setFilter(f.key)}
                />
              ))}
            </div>
          </div>

          {/* App Grid — flex 1 agar mengisi sisa tinggi layar */}
          <div style={{
            flex: 1,
            background: NEU_BG,
            borderRadius: 24,
            padding: "20px 24px",
            boxShadow: `inset 4px 4px 12px #c5cad8, inset -4px -4px 12px #ffffff`,
            display: "flex",
            flexWrap: "wrap",
            gap: "16px",
            justifyContent: "center",
            alignContent: "center",
            animation: "fadeUp 0.5s ease 0.2s forwards",
            opacity: 0,
          }}>
            {filtered.length === 0 ? (
              <p style={{ color: "#94a3b8", fontSize: 13 }}>
                No applications available for your account.
              </p>
            ) : (
              filtered.map((app, i) => (
                <AppCard key={app.id} app={app} index={i} onNavigate={navigate} onDashboardClick={pickRandomTheme} />
              ))
            )}
          </div>

          {/* Legend */}
          <div style={{
            display: "flex", justifyContent: "center", gap: 20,
            animation: "fadeUp 0.5s ease 0.4s forwards", opacity: 0,
          }}>
            {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{
                  width: 7, height: 7, borderRadius: "50%",
                  background: cfg.dot,
                  boxShadow: key === "sso" ? `0 0 5px ${cfg.dot}` : "none",
                }} />
                <span style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.04em" }}>
                  {cfg.label.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </main>
      </div>
    </>
  );
}
