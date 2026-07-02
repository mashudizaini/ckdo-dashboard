import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { LogOut, ExternalLink, Shield, Clock } from "lucide-react";
import logo from "@/assets/LOGO-ONLY.png";

// ─── App Data (grouped by category) ──────────────────────────────
const APPS = [
  // Business & Analytics
  { id: "dashboard",   category: "business", name: "CKDO Dashboard",         desc: "Monitoring & reporting",              url: "/dashboard/it",                                                    status: "sso",     emoji: "📊", role: "app:dashboard"   },
  { id: "eis",         category: "business", name: "EIS Dashboard",           desc: "Executive information system",        url: "http://172.21.2.209:8090",                                         status: "sso",     emoji: "📈", role: "app:eis"          },
  { id: "oracle-ebs",  category: "business", name: "Oracle EBS",              desc: "Enterprise resource planning",        url: "http://ckd-app.ckd-otto.com:8000/OA_HTML/AppsLocalLogin.jsp",     status: "direct",  emoji: "🔴", role: "app:oracle-ebs"   },

  // Human Resources
  { id: "portal-hr",   category: "hr",       name: "HR Portal",               desc: "Employee self-service",               url: "https://portal.ckd-otto.com/auth/login",                           status: "pending", emoji: "👥", role: "app:portal-hr"    },
  { id: "talenta",     category: "hr",       name: "Talenta HR",              desc: "Attendance & payroll",                url: "https://hr.talenta.co",                                            status: "pending", emoji: "🕐", role: "app:talenta"       },

  // IT Operations
  { id: "eticket",     category: "it-ops",   name: "E-Ticket System",         desc: "Helpdesk & ticketing",                url: "http://helpdesk.ckd-otto.com/dashboard",                           status: "sso",     emoji: "🎫", role: "app:eticket"       },
  { id: "SSO-Admin",   category: "it-ops",   name: "SSO Administration",      desc: "Keycloak SSO management",             url: "http://dashboard-dev.ckd-otto.com/auth/admin",                     status: "direct",  emoji: "🔐", role: "app:sso-admin"     },

  // Infrastructure
  { id: "ovm",         category: "infra",    name: "OVM Manager",             desc: "Oracle VM virtualization",            url: "https://172.21.2.200:7002/ovm/console/faces/login.jspx",           status: "direct",  emoji: "🖥️", role: "app:ovm"           },
  { id: "ebs-backup",  category: "infra",    name: "EBS Backup & Recovery",   desc: "Oracle EBS backup monitoring",        url: "http://172.21.2.209:28201/",                                       status: "direct",  emoji: "💾", role: "app:ebs-backup"   },
  { id: "myminio",     category: "infra",    name: "MinIO Storage",           desc: "Object storage management",           url: "http://172.21.2.157:9001",                                         status: "direct",  emoji: "🗄️", role: "app:myminio"       },
  { id: "synology",    category: "infra",    name: "Synology NAS",            desc: "Shared folder & file storage",        url: "http://172.21.2.207:5000/#/signin",                                status: "direct",  emoji: "📁", role: "app:synology"      },
  { id: "idrac",       category: "infra",    name: "Dell iDRAC",              desc: "Server remote management (199)",      url: "https://172.21.2.199/restgui/start.html?login",                    status: "direct",  emoji: "🔧", role: "app:idrac"         },
  { id: "idrac-98",    category: "infra",    name: "Dell iDRAC 98",           desc: "Server remote management (198)",      url: "https://172.21.2.198/restgui/start.html?login",                    status: "direct",  emoji: "🔧", role: "app:idrac-98"      },
  { id: "idrac-dev",   category: "infra",    name: "Dell iDRAC Dev",          desc: "Server remote management (197)",      url: "https://172.21.2.197/restgui/start.html?login",                    status: "direct",  emoji: "🔧", role: "app:idrac-dev"     },

  // External
  { id: "website",     category: "external", name: "Company Website",         desc: "ckd-otto.com public site",            url: "https://ckd-otto.com",                                             status: "direct",  emoji: "🌐", role: "app:website"       },
];

const CATEGORIES = [
  { id: "business", label: "Business & Analytics", short: "Business", emoji: "📊", color: "#2563eb", light: "#dbeafe" },
  { id: "hr",       label: "Human Resources",       short: "HR",       emoji: "👥", color: "#7c3aed", light: "#ede9fe" },
  { id: "it-ops",   label: "IT Operations",         short: "IT Ops",   emoji: "🛠️", color: "#ea580c", light: "#ffedd5" },
  { id: "infra",    label: "Infrastructure",         short: "Infra",    emoji: "🏗️", color: "#0891b2", light: "#cffafe" },
  { id: "external", label: "External",               short: "External", emoji: "🌐", color: "#16a34a", light: "#dcfce7" },
];

const STATUS_CONFIG = {
  sso:     { label: "SSO Active",  dot: "#2563eb", color: "#1d4ed8", accent: "#dbeafe" },
  pending: { label: "Integrating", dot: "#f59e0b", color: "#d97706", accent: "#fef3c7" },
  direct:  { label: "Direct Link", dot: "#8b5cf6", color: "#7c3aed", accent: "#ede9fe" },
};

const NEU_BG     = "#e8edf5";
const SHADOW_OUT = "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff";
const SHADOW_IN  = "inset 4px 4px 10px #c5cad8, inset -4px -4px 10px #ffffff";

// ─── App Card ────────────────────────────────────────────────────
function AppCard({ app, index, onNavigate, onDashboardClick }) {
  const [pressed, setPressed] = useState(false);
  const cfg = STATUS_CONFIG[app.status];

  const handleClick = () => {
    if (app.id === "dashboard") { onDashboardClick(); onNavigate(app.url); return; }
    if (app.id === "eis") { window.open(app.url, "_blank", "noopener,noreferrer"); return; }
    window.open(app.url, "_blank");
  };

  return (
    <div
      onClick={() => { setPressed(true); setTimeout(() => setPressed(false), 150); handleClick(); }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      onMouseLeave={() => setPressed(false)}
      style={{
        animation: `fadeUp 0.45s ease forwards`,
        animationDelay: `${index * 0.06}s`,
        opacity: 0,
        cursor: "pointer",
        width: 144,
        background: NEU_BG,
        borderRadius: 20,
        padding: "18px 12px 14px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 9,
        boxShadow: pressed ? SHADOW_IN : SHADOW_OUT,
        transform: pressed ? "scale(0.97)" : "scale(1)",
        transition: "box-shadow 0.18s ease, transform 0.18s ease",
        userSelect: "none",
      }}
    >
      <div style={{
        width: 54, height: 54, borderRadius: 15,
        background: NEU_BG,
        boxShadow: pressed ? `inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff` : `4px 4px 10px #c5cad8, -4px -4px 10px #ffffff`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 26, transition: "box-shadow 0.18s ease", position: "relative",
      }}>
        {app.emoji}
        <div style={{
          position: "absolute", bottom: 3, right: 3,
          width: 10, height: 10, borderRadius: "50%",
          background: cfg.dot, border: `2px solid ${NEU_BG}`,
          boxShadow: app.status === "sso" ? `0 0 6px ${cfg.dot}` : "none",
          animation: app.status === "sso" ? "pulseDot 2s infinite" : "none",
        }} />
      </div>

      <div style={{ textAlign: "center", width: "100%" }}>
        <p style={{ fontSize: 12, fontWeight: 700, color: "#2d3748", letterSpacing: "0.01em", marginBottom: 3, lineHeight: 1.3 }}>
          {app.name}
        </p>
        <p style={{ fontSize: 9.5, color: "#94a3b8", lineHeight: 1.4 }}>
          {app.desc}
        </p>
      </div>

      <div style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 9px", borderRadius: 20,
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

// ─── Category Section ─────────────────────────────────────────────
function CategorySection({ cat, apps, onNavigate, onDashboardClick, startIndex }) {
  if (apps.length === 0) return null;
  return (
    <div>
      {/* Section header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{ width: 3, height: 22, borderRadius: 2, background: cat.color, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 800, color: cat.color, letterSpacing: "0.1em" }}>
          {cat.emoji} {cat.label.toUpperCase()}
        </span>
        <div style={{
          fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 10,
          background: cat.light, color: cat.color,
        }}>
          {apps.length} app{apps.length > 1 ? "s" : ""}
        </div>
        <div style={{ flex: 1, height: 1, background: `linear-gradient(to right, ${cat.color}33, transparent)` }} />
      </div>

      {/* Cards */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, paddingLeft: 13 }}>
        {apps.map((app, i) => (
          <AppCard
            key={app.id}
            app={app}
            index={startIndex + i}
            onNavigate={onNavigate}
            onDashboardClick={onDashboardClick}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Filter Button ────────────────────────────────────────────────
function FilterBtn({ label, active, color, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 14px", borderRadius: 20, border: "none",
        background: NEU_BG,
        color: active ? (color || "#1d4ed8") : "#64748b",
        fontSize: 11, fontWeight: 700, letterSpacing: "0.03em",
        cursor: "pointer",
        boxShadow: active ? SHADOW_IN : SHADOW_OUT,
        transition: "all 0.2s ease",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

// ─── Main ─────────────────────────────────────────────────────────
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

  const isAdmin      = roles.includes("admin");
  const allowedApps  = APPS.filter((a) => isAdmin || roles.includes(a.role));
  const visibleApps  = filter === "all" ? allowedApps : allowedApps.filter((a) => a.category === filter);

  let cardIndex = 0;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        @keyframes fadeUp  { from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulseDot{ 0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.8);} }
        @keyframes slideIn { from { opacity:0; transform:translateY(-14px); } to { opacity:1; transform:translateY(0); } }
        * { box-sizing:border-box; margin:0; padding:0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #e8edf5; }
        ::-webkit-scrollbar-thumb { background: #c5cad8; border-radius: 4px; }
      `}</style>

      <div style={{ minHeight: "100vh", background: NEU_BG, fontFamily: "'Inter', sans-serif", display: "flex", flexDirection: "column" }}>

        {/* ── HEADER ── */}
        <header style={{
          background: NEU_BG, boxShadow: "0 4px 16px #c5cad8, 0 -2px 8px #ffffff",
          padding: "12px 32px", display: "flex", alignItems: "center", justifyContent: "space-between",
          position: "sticky", top: 0, zIndex: 20, animation: "slideIn 0.6s ease forwards",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 48, height: 48, borderRadius: 13, background: NEU_BG, boxShadow: SHADOW_OUT, display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}>
              <img src={logo} alt="CKD Otto" style={{ width: 36, height: 36, objectFit: "contain" }} />
            </div>
            <div>
              <p style={{ fontSize: 14, fontWeight: 700, color: "#1e293b", letterSpacing: "0.04em" }}>CKD OTTO PHARMACEUTICALS</p>
              <p style={{ fontSize: 9.5, color: "#2563eb", letterSpacing: "0.1em", fontWeight: 600 }}>INTERNAL APPLICATION PORTAL</p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <p style={{ fontSize: 10.5, color: "#2563eb", fontWeight: 700, letterSpacing: "0.06em", whiteSpace: "nowrap" }}>
              BETTER LIFE THROUGH BETTER MEDICINE
            </p>
            <div style={{ width: 1, height: 34, background: "#c5cad8" }} />
            <div style={{ background: NEU_BG, borderRadius: 10, padding: "5px 12px", boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`, textAlign: "right" }}>
              <p style={{ fontSize: 14, fontWeight: 600, color: "#1e293b", letterSpacing: "0.04em" }}>
                {time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
              <p style={{ fontSize: 9, color: "#94a3b8", letterSpacing: "0.03em" }}>
                {time.toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
              </p>
            </div>
            <div style={{ width: 1, height: 34, background: "#c5cad8" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "linear-gradient(135deg,#2563eb,#0891b2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "white", boxShadow: "3px 3px 8px #c5cad8,-2px -2px 6px #ffffff" }}>
                {user?.fullName?.charAt(0) || user?.username?.charAt(0) || "U"}
              </div>
              <div>
                <p style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>{user?.fullName || user?.username || "User"}</p>
                <p style={{ fontSize: 9.5, color: "#94a3b8" }}>{user?.email || ""}</p>
              </div>
            </div>
            <button
              onClick={logout}
              style={{ padding: "7px 12px", borderRadius: 10, border: "none", background: NEU_BG, color: "#dc2626", fontSize: 11.5, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, boxShadow: SHADOW_OUT, transition: "box-shadow 0.18s ease" }}
              onMouseDown={e => e.currentTarget.style.boxShadow = SHADOW_IN}
              onMouseUp={e => e.currentTarget.style.boxShadow = SHADOW_OUT}
              onMouseLeave={e => e.currentTarget.style.boxShadow = SHADOW_OUT}
            >
              <LogOut size={12} /> Sign Out
            </button>
          </div>
        </header>

        {/* ── MAIN ── */}
        <main style={{ flex: 1, padding: "14px 32px 14px", display: "flex", flexDirection: "column", gap: 12, minHeight: 0 }}>

          {/* Top bar */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", animation: "fadeUp 0.5s ease 0.1s forwards", opacity: 0, flexWrap: "wrap", gap: 10 }}>
            <div style={{ background: NEU_BG, borderRadius: 12, padding: "7px 16px", boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff` }}>
              <span style={{ fontSize: 10, color: "#2563eb", fontWeight: 700, letterSpacing: "0.1em" }}>WELCOME BACK</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginLeft: 10 }}>{user?.fullName || user?.username || "User"}</span>
              <span style={{ fontSize: 10.5, color: "#94a3b8", marginLeft: 8 }}>— Select an application to get started</span>
            </div>

            {/* Category filter */}
            <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
              <FilterBtn label="All Apps" active={filter === "all"} color="#1d4ed8" onClick={() => setFilter("all")} />
              {CATEGORIES.map(cat => (
                <FilterBtn
                  key={cat.id}
                  label={`${cat.emoji} ${cat.short}`}
                  active={filter === cat.id}
                  color={cat.color}
                  onClick={() => setFilter(cat.id)}
                />
              ))}
            </div>
          </div>

          {/* Category sections inside scrollable container */}
          <div style={{
            flex: 1,
            background: NEU_BG,
            borderRadius: 22,
            padding: "20px 24px",
            boxShadow: `inset 4px 4px 12px #c5cad8, inset -4px -4px 12px #ffffff`,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 24,
            animation: "fadeUp 0.5s ease 0.2s forwards",
            opacity: 0,
          }}>
            {visibleApps.length === 0 ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flex: 1 }}>
                <p style={{ color: "#94a3b8", fontSize: 13 }}>No applications available for your account.</p>
              </div>
            ) : (
              CATEGORIES.map(cat => {
                const catApps = visibleApps.filter(a => a.category === cat.id);
                if (catApps.length === 0) return null;
                const si = cardIndex;
                cardIndex += catApps.length;
                return (
                  <CategorySection
                    key={cat.id}
                    cat={cat}
                    apps={catApps}
                    onNavigate={navigate}
                    onDashboardClick={pickRandomTheme}
                    startIndex={si}
                  />
                );
              })
            )}
          </div>

          {/* Legend */}
          <div style={{ display: "flex", justifyContent: "center", gap: 18, animation: "fadeUp 0.5s ease 0.4s forwards", opacity: 0 }}>
            {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: cfg.dot, boxShadow: key === "sso" ? `0 0 5px ${cfg.dot}` : "none" }} />
                <span style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.04em" }}>{cfg.label.toUpperCase()}</span>
              </div>
            ))}
          </div>
        </main>
      </div>
    </>
  );
}
