import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import {
  Monitor, Users, Factory, Calculator,
  ShoppingCart, MessageSquare, FileText, LogOut, LayoutGrid
} from "lucide-react";
import logo from "@/assets/LOGO-ONLY.png";

const NAV_ITEMS = [
  { label: "IT",          path: "/dashboard/it",         icon: Monitor,      roles: ["it_staff"] },
  { label: "HR",          path: "/dashboard/hr",         icon: Users,        roles: ["hr_staff"] },
  { label: "PAC",         path: "/dashboard/pac",        icon: Factory,      roles: ["pac_staff"] },
  { label: "Accounting",  path: "/dashboard/accounting", icon: Calculator,   roles: ["accounting_staff"] },
  { label: "Purchasing",  path: "/dashboard/purchasing", icon: ShoppingCart, roles: ["purchasing_staff"] },
];

const AI_ITEMS = [
  { label: "AI Chatbot",    path: "/ai/chatbot",       icon: MessageSquare, roles: [] },
  { label: "Meeting Notes", path: "/ai/meeting-notes", icon: FileText,      roles: [] },
];

export default function Sidebar() {
  const { user, hasAnyRole, logout } = useAuthStore();
  const { theme: T } = useThemeStore();
  const navigate = useNavigate();

  const isVisible = (roles) => roles.length === 0 || hasAnyRole(...roles, "admin");

  return (
    <aside
      className="flex h-screen w-56 flex-col flex-shrink-0"
      style={{ background: T.bgSidebar, borderRight: `1px solid ${T.sidebarBorder}` }}
    >
      {/* ── Logo + Brand ── */}
      <div className="px-4 pt-5 pb-4" style={{ borderBottom: `1px solid ${T.sidebarDivider}` }}>
        <div className="flex items-center gap-3 mb-4">
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: `rgba(${T.vars["--accent-rgb"]}, 0.15)`,
            border: `1px solid rgba(${T.vars["--accent-rgb"]}, 0.25)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <img
              src={logo}
              alt="CKD Otto"
              style={{ width: 26, height: 26, objectFit: "contain", filter: T.logoFilter }}
            />
          </div>
          <div>
            <p style={{ fontSize: 12, fontWeight: 700, color: T.textPrimary, letterSpacing: "0.04em", lineHeight: 1.2 }}>
              CKD OTTO
            </p>
            <p style={{ fontSize: 9.5, fontWeight: 600, color: T.accentColor, letterSpacing: "0.06em" }}>
              PHARMACEUTICALS
            </p>
          </div>
        </div>

        {/* Theme badge */}
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "3px 10px", borderRadius: 20,
          background: `rgba(${T.vars["--accent-rgb"]}, 0.12)`,
          border: `1px solid rgba(${T.vars["--accent-rgb"]}, 0.2)`,
          marginBottom: 10,
        }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.accentColor, boxShadow: `0 0 6px ${T.accentColor}` }} />
          <span style={{ fontSize: 9, fontWeight: 700, color: T.accentColor, letterSpacing: "0.06em" }}>
            {T.name.toUpperCase()}
          </span>
        </div>

        {/* Back to portal */}
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition-all"
          style={{ color: T.btnBackColor, background: T.btnBackBg, border: `1px solid ${T.btnBackBorder}` }}
          onMouseEnter={e => { e.currentTarget.style.background = `rgba(${T.vars["--accent-rgb"]}, 0.15)`; e.currentTarget.style.color = T.accentColor; }}
          onMouseLeave={e => { e.currentTarget.style.background = T.btnBackBg; e.currentTarget.style.color = T.btnBackColor; }}
        >
          <LayoutGrid size={12} />
          App Portal
        </button>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {/* Dashboard */}
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: T.textMuted, letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 8 }}>
            DASHBOARD
          </p>
          <div className="space-y-0.5">
            {NAV_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${isActive ? "nav-active" : "nav-inactive"}`}
                style={({ isActive }) => isActive
                  ? { background: T.navActiveBg, color: T.navActiveColor, fontWeight: 600 }
                  : { color: T.navItemColor }
                }
                onMouseEnter={e => { if (!e.currentTarget.classList.contains("nav-active")) { e.currentTarget.style.background = T.navHoverBg; e.currentTarget.style.color = T.navHoverColor; } }}
                onMouseLeave={e => { if (!e.currentTarget.classList.contains("nav-active")) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.navItemColor; } }}
              >
                <div style={{
                  width: 28, height: 28, borderRadius: 8,
                  background: "rgba(255,255,255,0.05)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <item.icon size={14} />
                </div>
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>

        {/* AI Tools */}
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: T.textMuted, letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 8 }}>
            AI TOOLS
          </p>
          <div className="space-y-0.5">
            {AI_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${isActive ? "nav-active" : "nav-inactive"}`}
                style={({ isActive }) => isActive
                  ? { background: T.navActiveBg, color: T.navActiveColor, fontWeight: 600 }
                  : { color: T.navItemColor }
                }
                onMouseEnter={e => { if (!e.currentTarget.classList.contains("nav-active")) { e.currentTarget.style.background = T.navHoverBg; e.currentTarget.style.color = T.navHoverColor; } }}
                onMouseLeave={e => { if (!e.currentTarget.classList.contains("nav-active")) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.navItemColor; } }}
              >
                <div style={{
                  width: 28, height: 28, borderRadius: 8,
                  background: "rgba(255,255,255,0.05)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <item.icon size={14} />
                </div>
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      {/* ── User + Logout ── */}
      <div className="p-3" style={{ borderTop: `1px solid ${T.sidebarDivider}` }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 10px", borderRadius: 10,
          background: "rgba(255,255,255,0.04)",
        }}>
          {/* Avatar */}
          <div style={{
            width: 30, height: 30, borderRadius: "50%",
            background: `linear-gradient(135deg, ${T.accentColor}, rgba(${T.vars["--accent-rgb"]}, 0.5))`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 12, fontWeight: 700, color: "white", flexShrink: 0,
          }}>
            {user?.fullName?.charAt(0) || user?.username?.charAt(0) || "U"}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: T.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user?.fullName || user?.username}
            </p>
            <p style={{ fontSize: 10, color: T.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user?.email}
            </p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg p-1.5 transition-all flex-shrink-0"
            style={{ color: T.textMuted }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.15)"; e.currentTarget.style.color = "#f87171"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.textMuted; }}
            title="Logout"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
