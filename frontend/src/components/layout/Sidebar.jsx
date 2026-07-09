import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import {
  Monitor, Users, Factory, Calculator,
  ShoppingCart, FileText, LogOut, LayoutGrid
} from "lucide-react";
import RobotIcon from "@/components/icons/RobotIcon";
import logo from "@/assets/LOGO-ONLY.png";

const NAV_ITEMS = [
  { label: "IT",          path: "/dashboard/it",         icon: Monitor,      roles: ["it_staff"] },
  { label: "HR",          path: "/dashboard/hr",         icon: Users,        roles: ["hr_staff"] },
  { label: "PAC",         path: "/dashboard/pac",        icon: Factory,      roles: ["pac_staff"] },
  { label: "Accounting",  path: "/dashboard/accounting", icon: Calculator,   roles: ["accounting_staff"] },
  { label: "Purchasing",  path: "/dashboard/purchasing", icon: ShoppingCart, roles: ["purchasing_staff"] },
];

const AI_ITEMS = [
  { label: "AI Chatbot",    path: "/ai/chatbot",       icon: RobotIcon, roles: [] },
  { label: "Meeting Notes", path: "/ai/meeting-notes", icon: FileText,  roles: [] },
];

/* ── One nav card — shared between the Dashboard and AI Tools groups ── */
function NavCard({ item }) {
  return (
    <NavLink
      to={item.path}
      className={({ isActive }) => `nav-card${isActive ? " nav-card--active" : ""}`}
    >
      {({ isActive }) => (
        <>
          <span className="nav-card__icon">
            <item.icon size={15} color={isActive ? "#ffffff" : "#2563eb"} />
          </span>
          <span className="nav-card__label">{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

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
      <style>{`
        .nav-card {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 10px;
          border-radius: 12px;
          text-decoration: none;
          background: #ffffff;
          border: 1px solid rgba(37,99,235,0.14);
          box-shadow: 0 1px 2px rgba(15,23,42,0.04);
          transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.1s ease;
        }
        .nav-card:hover {
          background: #eff6ff;
          border-color: rgba(37,99,235,0.32);
          transform: translateX(1px);
        }
        .nav-card__icon {
          width: 28px; height: 28px; border-radius: 8px;
          background: rgba(37,99,235,0.09);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
          transition: background 0.16s ease;
        }
        .nav-card__label {
          font-size: 12.5px;
          font-weight: 600;
          color: #475569;
        }
        .nav-card--active {
          background: linear-gradient(135deg, #2563eb, #1d4ed8);
          border-color: #1d4ed8;
          box-shadow: 0 4px 12px rgba(37,99,235,0.35);
        }
        .nav-card--active:hover { background: linear-gradient(135deg, #2563eb, #1d4ed8); transform: none; }
        .nav-card--active .nav-card__icon { background: rgba(255,255,255,0.22); }
        .nav-card--active .nav-card__label { color: #ffffff; font-weight: 700; }
      `}</style>

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
            <p style={{ fontSize: 15, fontWeight: 800, color: "#1e293b", letterSpacing: "0.02em", lineHeight: 1.15 }}>
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
          Application Center
        </button>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {/* Dashboard */}
        <div>
          <p style={{ fontSize: 13, fontWeight: 800, color: "#334155", letterSpacing: "0.07em", marginBottom: 8, paddingLeft: 8 }}>
            DASHBOARD
          </p>
          <div className="space-y-1.5">
            {NAV_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavCard key={item.path} item={item} />
            ))}
          </div>
        </div>

        {/* AI Tools */}
        <div>
          <p style={{ fontSize: 13, fontWeight: 800, color: "#334155", letterSpacing: "0.07em", marginBottom: 8, paddingLeft: 8 }}>
            AI TOOLS
          </p>
          <div className="space-y-1.5">
            {AI_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
              <NavCard key={item.path} item={item} />
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
