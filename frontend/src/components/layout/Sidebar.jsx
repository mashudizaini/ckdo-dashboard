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
      style={{
        background: "#ffffff",
        borderRight: "1px solid rgba(0,0,0,0.06)",
        boxShadow: "2px 0 12px rgba(0,0,0,0.03)",
      }}
    >
      {/* ── Logo + Brand ── */}
      <div className="px-4 pt-5 pb-4" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div className="flex items-center gap-3 mb-4">
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: "linear-gradient(135deg, #eff6ff, #dbeafe)",
            border: "1px solid #bfdbfe",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
            boxShadow: "0 2px 8px rgba(37,99,235,0.1)",
          }}>
            <img
              src={logo}
              alt="CKD Otto"
              style={{ width: 28, height: 28, objectFit: "contain" }}
            />
          </div>
          <div>
            <p style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", letterSpacing: "0.04em", lineHeight: 1.2 }}>
              CKD OTTO
            </p>
            <p style={{ fontSize: 9.5, fontWeight: 600, color: "#2563eb", letterSpacing: "0.06em" }}>
              PHARMACEUTICALS
            </p>
          </div>
        </div>

        {/* Back to portal */}
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition-all"
          style={{
            color: "#475569",
            background: "rgba(37,99,235,0.06)",
            border: "1px solid rgba(37,99,235,0.1)",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "rgba(37,99,235,0.12)";
            e.currentTarget.style.color = "#2563eb";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "rgba(37,99,235,0.06)";
            e.currentTarget.style.color = "#475569";
          }}
        >
          <LayoutGrid size={12} />
          App Portal
        </button>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {/* Dashboard */}
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 8 }}>
            DASHBOARD
          </p>
          <div className="space-y-0.5">
            {NAV_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${isActive ? "nav-active" : "nav-inactive"}`}
                style={({ isActive }) => isActive
                  ? { background: "rgba(37,99,235,0.08)", color: "#2563eb", fontWeight: 600 }
                  : { color: "#64748b" }
                }
                onMouseEnter={e => {
                  if (!e.currentTarget.classList.contains("nav-active")) {
                    e.currentTarget.style.background = "rgba(0,0,0,0.03)";
                    e.currentTarget.style.color = "#1e293b";
                  }
                }}
                onMouseLeave={e => {
                  if (!e.currentTarget.classList.contains("nav-active")) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "#64748b";
                  }
                }}
              >
                <div style={{
                  width: 30, height: 30, borderRadius: 8,
                  background: "rgba(37,99,235,0.06)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <item.icon size={14} style={{ color: "inherit" }} />
                </div>
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>

        {/* AI Tools */}
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 8 }}>
            AI TOOLS
          </p>
          <div className="space-y-0.5">
            {AI_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${isActive ? "nav-active" : "nav-inactive"}`}
                style={({ isActive }) => isActive
                  ? { background: "rgba(37,99,235,0.08)", color: "#2563eb", fontWeight: 600 }
                  : { color: "#64748b" }
                }
                onMouseEnter={e => {
                  if (!e.currentTarget.classList.contains("nav-active")) {
                    e.currentTarget.style.background = "rgba(0,0,0,0.03)";
                    e.currentTarget.style.color = "#1e293b";
                  }
                }}
                onMouseLeave={e => {
                  if (!e.currentTarget.classList.contains("nav-active")) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "#64748b";
                  }
                }}
              >
                <div style={{
                  width: 30, height: 30, borderRadius: 8,
                  background: "rgba(37,99,235,0.06)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <item.icon size={14} style={{ color: "inherit" }} />
                </div>
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      {/* ── User + Logout ── */}
      <div className="p-3" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 10px", borderRadius: 10,
          background: "#f8fafc",
        }}>
          {/* Avatar */}
          <div style={{
            width: 32, height: 32, borderRadius: "50%",
            background: "linear-gradient(135deg, #2563eb, #0891b2)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: "white", flexShrink: 0,
            boxShadow: "0 2px 6px rgba(37,99,235,0.25)",
          }}>
            {user?.fullName?.charAt(0) || user?.username?.charAt(0) || "U"}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user?.fullName || user?.username}
            </p>
            <p style={{ fontSize: 10, color: "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user?.email}
            </p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg p-1.5 transition-all flex-shrink-0"
            style={{ color: "#94a3b8" }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.08)"; e.currentTarget.style.color = "#ef4444"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
            title="Logout"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
