import { useState, useEffect, useRef, useCallback } from "react";
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
        width: 88,
        background: NEU_BG,
        borderRadius: 14,
        padding: "12px 8px 10px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        boxShadow: pressed ? SHADOW_IN : SHADOW_OUT,
        transform: pressed ? "scale(0.97)" : "scale(1)",
        transition: "box-shadow 0.18s ease, transform 0.18s ease",
        userSelect: "none",
      }}
    >
      <div style={{
        width: 40, height: 40, borderRadius: 11,
        background: NEU_BG,
        boxShadow: pressed ? `inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff` : `4px 4px 10px #c5cad8, -4px -4px 10px #ffffff`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 20, transition: "box-shadow 0.18s ease", position: "relative",
      }}>
        {app.emoji}
        <div style={{
          position: "absolute", bottom: 2, right: 2,
          width: 8, height: 8, borderRadius: "50%",
          background: cfg.dot, border: `2px solid ${NEU_BG}`,
          boxShadow: app.status === "sso" ? `0 0 5px ${cfg.dot}` : "none",
          animation: app.status === "sso" ? "pulseDot 2s infinite" : "none",
        }} />
      </div>

      <p style={{ fontSize: 10, fontWeight: 700, color: "#2d3748", letterSpacing: "0.01em", lineHeight: 1.3, textAlign: "center", width: "100%" }}>
        {app.name}
      </p>

      <div style={{
        display: "inline-flex", alignItems: "center", gap: 3,
        padding: "2px 6px", borderRadius: 20,
        background: cfg.accent,
        boxShadow: `inset 2px 2px 4px ${cfg.dot}22, inset -1px -1px 3px #ffffff88`,
      }}>
        {app.status === "sso"     && <Shield size={7} color={cfg.color} />}
        {app.status === "pending" && <Clock size={7} color={cfg.color} />}
        {app.status === "direct"  && <ExternalLink size={7} color={cfg.color} />}
        <span style={{ fontSize: 7.5, color: cfg.color, fontWeight: 700, letterSpacing: "0.05em" }}>
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

// ─── Birthday row (one item in the announcement marquee) ──────────
function BirthdayRow({ emp }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "9px 12px", marginBottom: 8, borderRadius: 12,
      background: emp.is_today ? "linear-gradient(135deg, #fef3c7, #fde68a)" : "#fff",
      boxShadow: emp.is_today ? "0 0 0 1.5px #f59e0b, 3px 3px 8px #c5cad8" : "2px 2px 6px #c5cad8, -2px -2px 6px #ffffff",
    }}>
      <div style={{
        width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
        background: emp.is_today ? "#f59e0b" : "linear-gradient(135deg,#2563eb,#0891b2)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14,
      }}>
        🎂
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <p style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {emp.name}
        </p>
        <p style={{ fontSize: 10, color: "#64748b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {[emp.job_title, emp.department].filter(Boolean).join(" · ") || "—"}
        </p>
      </div>
      <div style={{
        flexShrink: 0, textAlign: "center", padding: "3px 9px", borderRadius: 10,
        background: emp.is_today ? "#f59e0b" : "#dbeafe",
        color: emp.is_today ? "#fff" : "#1d4ed8",
        fontSize: 10.5, fontWeight: 800,
      }}>
        {emp.is_today ? "TODAY" : new Date(emp.date + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" })}
      </div>
    </div>
  );
}

// ─── Auto-scrolling vertical marquee (loops seamlessly, pauses on hover) ──
function BirthdayMarquee({ items }) {
  if (!items.length) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500, textAlign: "center" }}>No birthdays this month.</p>
      </div>
    );
  }
  // Short lists don't need to scroll — only animate when content overflows.
  const shouldScroll = items.length > 4;
  const duration = Math.max(items.length * 3.2, 10);
  return (
    <div className="birthday-marquee" style={{ flex: 1, overflow: "hidden", position: "relative", minHeight: 0 }}>
      <div
        className={shouldScroll ? "birthday-marquee__track birthday-marquee__track--scroll" : "birthday-marquee__track"}
        style={shouldScroll ? { animationDuration: `${duration}s` } : undefined}
      >
        {(shouldScroll ? [...items, ...items] : items).map((emp, i) => (
          <BirthdayRow key={i} emp={emp} />
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
  const { user, logout, roles, token } = useAuthStore();
  const { pickRandomTheme } = useThemeStore();
  const navigate = useNavigate();
  const [time, setTime] = useState(new Date());
  const [qrLinks, setQrLinks] = useState([]);
  const [birthdays, setBirthdays] = useState([]);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    fetch("/e-magazine/magazines/index.json")
      .then(r => r.ok ? r.json() : [])
      .then(list => { if (list[0]?.qr_links?.length) setQrLinks(list[0].qr_links); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!token) return;
    fetch("/api/v1/dashboard/hr/employees/birthdays-this-month", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : [])
      .then(setBirthdays)
      .catch(() => {});
  }, [token]);

  const [splitPct, setSplitPct] = useState(22); // left panel width % (kept narrow by default so the e-magazine spread has room to breathe)
  const isDragging = useRef(false);
  const containerRef = useRef(null);

  const onDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMouseMove = (ev) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.round(((ev.clientX - rect.left) / rect.width) * 100);
      setSplitPct(Math.min(Math.max(pct, 20), 75)); // clamp 20–75%
    };
    const onMouseUp = () => {
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  const isAdmin     = roles.includes("admin");
  const allowedApps = APPS.filter((a) => isAdmin || roles.includes(a.role));

  let cardIndex = 0;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        @keyframes fadeUp  { from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulseDot{ 0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.8);} }
        @keyframes slideIn { from { opacity:0; transform:translateY(-14px); } to { opacity:1; transform:translateY(0); } }
        @keyframes marqueeUp { from { transform: translateY(0); } to { transform: translateY(-50%); } }
        .birthday-marquee__track { display: flex; flex-direction: column; }
        .birthday-marquee__track--scroll { animation-name: marqueeUp; animation-timing-function: linear; animation-iteration-count: infinite; }
        .birthday-marquee:hover .birthday-marquee__track--scroll { animation-play-state: paused; }
        * { box-sizing:border-box; margin:0; padding:0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #e8edf5; }
        ::-webkit-scrollbar-thumb { background: #c5cad8; border-radius: 4px; }
        .drag-divider:hover > div { background: linear-gradient(180deg, #2563eb88, #2563eb44, #2563eb88) !important; }
      `}</style>

      <div style={{ height: "100vh", background: NEU_BG, fontFamily: "'Inter', sans-serif", display: "flex", flexDirection: "column", overflow: "hidden" }}>

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

        {/* ── MAIN — split layout ── */}
        <main ref={containerRef} style={{ flex: 1, padding: "14px 20px 14px", display: "flex", gap: 0, minHeight: 0, overflow: "hidden" }}>

          {/* ── LEFT PANEL — App cards (draggable width) ── */}
          <div style={{
            width: `${splitPct}%`, flexShrink: 0, marginRight: 0,
            display: "flex", flexDirection: "column", gap: 10,
            animation: "fadeUp 0.5s ease 0.1s forwards", opacity: 0,
          }}>
            {/* Welcome strip */}
            <div style={{ background: NEU_BG, borderRadius: 12, padding: "7px 14px", boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`, flexShrink: 0 }}>
              <span style={{ fontSize: 9.5, color: "#2563eb", fontWeight: 700, letterSpacing: "0.1em" }}>WELCOME BACK</span>
              <p style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b", marginTop: 2 }}>{user?.fullName || user?.username || "User"}</p>
            </div>

            {/* Scrollable app list — all apps, no filter */}
            <div style={{
              flex: 1,
              background: NEU_BG,
              borderRadius: 18,
              padding: "14px 12px",
              boxShadow: `inset 4px 4px 12px #c5cad8, inset -4px -4px 12px #ffffff`,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}>
              {allowedApps.length === 0 ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flex: 1 }}>
                  <p style={{ color: "#94a3b8", fontSize: 12 }}>No apps available.</p>
                </div>
              ) : (
                CATEGORIES.map(cat => {
                  const catApps = allowedApps.filter(a => a.category === cat.id);
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
            <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 10, flexShrink: 0 }}>
              {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
                <div key={key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: cfg.dot, boxShadow: key === "sso" ? `0 0 5px ${cfg.dot}` : "none" }} />
                  <span style={{ fontSize: 9, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.04em" }}>{cfg.label.toUpperCase()}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── DRAG DIVIDER ── */}
          <div
            className="drag-divider"
            onMouseDown={onDividerMouseDown}
            style={{
              width: 14, flexShrink: 0, cursor: "col-resize",
              display: "flex", alignItems: "center", justifyContent: "center",
              position: "relative", zIndex: 10,
            }}
            title="Drag to resize"
          >
            <div style={{
              width: 4, height: "60%", minHeight: 80, borderRadius: 4,
              background: "linear-gradient(180deg, #c5cad8, #ffffff88, #c5cad8)",
              boxShadow: "1px 0 3px #c5cad888, -1px 0 3px #c5cad888",
              transition: "background 0.15s",
            }} />
          </div>

          {/* ── RIGHT PANEL — E-Magazine (remaining width) ── */}
          <div style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            animation: "fadeUp 0.5s ease 0.2s forwards", opacity: 0,
            minWidth: 0,
          }}>
            {/* Magazine header label */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <div style={{ background: NEU_BG, borderRadius: 10, padding: "6px 14px", boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 16 }}>📰</span>
                <div>
                  <span style={{ fontSize: 9.5, color: "#2563eb", fontWeight: 700, letterSpacing: "0.1em", display: "block" }}>INTERNAL MAGAZINE</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>CKDO e-Magazine Reading Room</span>
                </div>
              </div>
              <a
                href="/e-magazine/"
                target="_blank"
                rel="noopener noreferrer"
                style={{ padding: "6px 12px", borderRadius: 10, border: "none", background: NEU_BG, color: "#2563eb", fontSize: 11, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, boxShadow: SHADOW_OUT, textDecoration: "none", transition: "box-shadow 0.18s ease", flexShrink: 0 }}
              >
                <ExternalLink size={11} /> Open Full Screen
              </a>
              {qrLinks.map((ql, i) => (
                <a key={i} href={ql.url} target="_blank" rel="noopener noreferrer"
                  style={{ padding: "6px 12px", borderRadius: 10, border: "none", background: NEU_BG, color: "#d97706", fontSize: 11, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, boxShadow: SHADOW_OUT, textDecoration: "none", flexShrink: 0 }}
                >
                  <span style={{ fontSize: 12 }}>📷</span> {ql.label}
                </a>
              ))}
            </div>

            {/* Magazine iframe */}
            <div style={{
              flex: 1,
              background: NEU_BG,
              borderRadius: 18,
              boxShadow: `inset 4px 4px 12px #c5cad8, inset -4px -4px 12px #ffffff`,
              overflow: "hidden",
              minHeight: 0,
            }}>
              <iframe
                src="/e-magazine/?embed=1"
                title="CKDO e-Magazine"
                style={{ width: "100%", height: "100%", border: "none", borderRadius: 18, display: "block" }}
                allow="fullscreen"
              />
            </div>
          </div>

          {/* ── STATIC DIVIDER ── */}
          <div style={{ width: 14, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{
              width: 4, height: "60%", minHeight: 80, borderRadius: 4,
              background: "linear-gradient(180deg, #c5cad8, #ffffff88, #c5cad8)",
              boxShadow: "1px 0 3px #c5cad888, -1px 0 3px #c5cad888",
            }} />
          </div>

          {/* ── RIGHT PANEL — Announcement & Notification (same width as app-card column) ── */}
          <div style={{
            width: `${splitPct}%`, flexShrink: 0,
            display: "flex", flexDirection: "column", gap: 8,
            animation: "fadeUp 0.5s ease 0.3s forwards", opacity: 0,
            minWidth: 0,
          }}>
            {/* Header label */}
            <div style={{ background: NEU_BG, borderRadius: 10, padding: "6px 14px", boxShadow: `inset 2px 2px 6px #c5cad8, inset -2px -2px 6px #ffffff`, display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
              <span style={{ fontSize: 16 }}>📢</span>
              <div>
                <span style={{ fontSize: 9.5, color: "#2563eb", fontWeight: 700, letterSpacing: "0.1em", display: "block" }}>ANNOUNCEMENT & NOTIFICATION</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
                  🎂 Birthdays This Month — {time.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
                </span>
              </div>
            </div>

            {/* Marquee card */}
            <div style={{
              flex: 1,
              background: NEU_BG,
              borderRadius: 18,
              padding: "14px 12px",
              boxShadow: `inset 4px 4px 12px #c5cad8, inset -4px -4px 12px #ffffff`,
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}>
              <BirthdayMarquee items={birthdays} />
            </div>
          </div>
        </main>
      </div>
    </>
  );
}
