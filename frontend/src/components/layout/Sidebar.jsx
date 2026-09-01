import { useState, useEffect } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import {
  Monitor, Users, Factory, Calculator,
  ShoppingCart, FileText, LogOut, LayoutGrid, TrendingUp, FileStack,
  ChevronDown, ChevronRight, Settings,
} from "lucide-react";
import RobotIcon from "@/components/icons/RobotIcon";
import logo from "@/assets/LOGO-ONLY.png";

// Each top-level module now expands into its own sections (formerly rendered
// as an in-page tab bar) — clicking a section navigates straight to its URL.
const NAV_ITEMS = [
  { label: "IT", path: "/dashboard/it", icon: Monitor, roles: ["it_staff"], children: [
    { label: "Oracle Server Monitoring", path: "/dashboard/it/server-monitoring" },
    { label: "Oracle Tablespace Monitoring", path: "/dashboard/it/tablespace-usage" },
    { label: "Oracle Storage Monitoring", path: "/dashboard/it/disk-usage" },
    { label: "Postgre DB Browser", path: "/dashboard/it/db-browser" },
    { label: "Oracle EBS Backup Recovery", path: "/dashboard/it/ebs-backup-recovery" },
    { label: "VPN Access Monitoring", path: "/dashboard/it/vpn-monitoring" },
  ] },
  { label: "HRGA", path: "/dashboard/hr", icon: Users, roles: ["hr_staff"], children: [
    { label: "Employee Data", path: "/dashboard/hr/employees" },
    { label: "Attendance Rate", path: "/dashboard/hr/attendance" },
    { label: "Working Calendar", path: "/dashboard/hr/workingcalendar" },
    { label: "To Do List", path: "/dashboard/hr/todo" },
    { label: "E-Recruitment", path: "/dashboard/hr/cv" },
    { label: "e-Magazine", path: "/dashboard/hr/emagazine" },
  ] },
  { label: "PAC", path: "/dashboard/pac", icon: Factory, roles: ["pac_staff"], children: [
    { label: "Business Plan", path: "/dashboard/pac/bizplan" },
    // Temporarily hidden — not in active use yet.
    // { label: "BCA MT940 Upload", path: "/dashboard/pac/mt940" },
    { label: "Exchange Rate", path: "/dashboard/pac/exchange" },
  ] },
  { label: "Accounting & Tax", path: "/dashboard/accounting", icon: Calculator, roles: ["accounting_staff"], children: [
    { label: "AP Autoinvoice", path: "/dashboard/accounting/ap-invoice" },
    // Temporarily hidden (2026-09-01 user request).
    // { label: "COGS Report", path: "/dashboard/accounting/cogs" },
    { label: "AP Outstanding", path: "/dashboard/accounting/profit" },
    { label: "AR Outstanding", path: "/dashboard/accounting/ar" },
    { label: "Financial Statement", path: "/dashboard/accounting/financial-statement" },
  ] },
  { label: "Purchasing", path: "/dashboard/purchasing", icon: ShoppingCart, roles: ["purchasing_staff"], children: [
    { label: "Open PR", path: "/dashboard/purchasing/open-pr" },
    { label: "Purchase History", path: "/dashboard/purchasing/purchase-history" },
    { label: "PO Price Analysis", path: "/dashboard/purchasing/price-analysis" },
    // Temporarily hidden — not in active use yet, see Purchasing.jsx's TABS comment.
    // { label: "Monthly Spend", path: "/dashboard/purchasing/monthly-spend" },
    { label: "Active Suppliers", path: "/dashboard/purchasing/active-suppliers" },
    { label: "Manufacturer Master", path: "/dashboard/purchasing/manufacturer-master" },
  ] },
  // No roles — reachable by any authenticated user (matches AI_ITEMS'
  // convention below). Sub-modules apply their own access control instead
  // of a Keycloak role gate — Budget Monitoring restricts by the caller's
  // own team, resolved server-side.
  { label: "General", path: "/dashboard/general", icon: LayoutGrid, roles: [], children: [
    { label: "Budget Monitoring", path: "/dashboard/general/budget" },
    // Temporarily hidden — not in active use yet.
    // { label: "Budget Usage Report", path: "/dashboard/general/budget-usage" },
    { label: "AP Outstanding with Payment", path: "/dashboard/general/ap-payment" },
  ] },
];

// SETUP — same team names as the DASHBOARD section above, one flat level
// (no further sub-items per team, unlike DASHBOARD's per-team feature
// list), open to any authenticated user for now: unlike DASHBOARD's
// per-team role gates, there's no per-child role field in this data shape
// to restrict SETUP > IT to it_staff only etc. — every team's Setup entry
// is visible to everyone until that's asked for.
const SETUP_ITEMS = [
  { label: "SETUP", path: "/setup", icon: Settings, roles: [], children: [
    { label: "IT", path: "/setup/it" },
    { label: "HRGA", path: "/setup/hr" },
    { label: "PAC", path: "/setup/pac" },
    { label: "Accounting & Tax", path: "/setup/accounting" },
    { label: "Purchasing", path: "/setup/purchasing" },
    { label: "General", path: "/setup/general" },
  ] },
];

// EIS is its own standalone executive dashboard, not one of the operational
// DASHBOARD modules above — kept as a separate sidebar section.
const EIS_ITEMS = [
  { label: "EIS", path: "/dashboard/eis", icon: TrendingUp, roles: ["management"], children: [
    { label: "Summary", path: "/dashboard/eis/summary" },
    { label: "Performance", path: "/dashboard/eis/performance" },
    { label: "Production", path: "/dashboard/eis/production" },
    { label: "Expansion", path: "/dashboard/eis/expansion" },
    { label: "Administration", path: "/dashboard/eis/administration" },
    // { label: "Business Plan", path: "/dashboard/eis/business-plan" }, // hidden — already covered by PAC dashboard
    { label: "Daily Sales", path: "/dashboard/eis/daily-sales" },
    { label: "Data Upload", path: "/dashboard/eis/data-upload" },
  ] },
];

const AI_ITEMS = [
  { label: "AI Chatbot",         path: "/ai/chatbot",             icon: RobotIcon,  roles: [] },
  { label: "Document Converter", path: "/ai/document-converter",  icon: FileStack,  roles: [] },
  { label: "Meeting Notes",      path: "/ai/meeting-notes",       icon: FileText,   roles: [] },
];

/* ── Leaf nav card — no children (AI Tools items, or a module with none) ── */
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

/* ── Tree nav item — module with children, expands to a sub-list ── */
function NavTreeItem({ item, isOpen, onToggle }) {
  const location = useLocation();
  const isParentActive = location.pathname.startsWith(item.path);

  return (
    <div>
      <NavLink
        to={item.path}
        className={`nav-card${isParentActive ? " nav-card--active" : ""}`}
        onClick={() => { if (!isOpen) onToggle(item.path); }}
      >
        <span className="nav-card__icon">
          <item.icon size={15} color={isParentActive ? "#ffffff" : "#2563eb"} />
        </span>
        <span className="nav-card__label" style={{ flex: 1 }}>{item.label}</span>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(item.path); }}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onToggle(item.path); } }}
          className="nav-card__chevron"
        >
          {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
      </NavLink>

      {isOpen && (
        <div className="nav-tree-children">
          {item.children.map((c) => (
            <NavLink
              key={c.path}
              to={c.path}
              className={({ isActive }) => `nav-subitem${isActive ? " nav-subitem--active" : ""}`}
            >
              {c.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  const { user, hasAnyRole, logout } = useAuthStore();
  const { theme: T } = useThemeStore();
  const navigate = useNavigate();
  const location = useLocation();

  const isVisible = (roles) => roles.length === 0 || hasAnyRole(...roles, "admin");

  // Whichever module matches the current URL starts expanded; user toggles freely afterward.
  const ALL_TREE_ITEMS = [...NAV_ITEMS, ...EIS_ITEMS, ...SETUP_ITEMS];

  const [expanded, setExpanded] = useState(() => new Set(
    ALL_TREE_ITEMS.filter((item) => location.pathname.startsWith(item.path)).map((item) => item.path)
  ));

  useEffect(() => {
    const active = ALL_TREE_ITEMS.find((item) => location.pathname.startsWith(item.path));
    if (active) setExpanded((prev) => (prev.has(active.path) ? prev : new Set(prev).add(active.path)));
  }, [location.pathname]); // eslint-disable-line

  const toggle = (path) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(path) ? next.delete(path) : next.add(path);
    return next;
  });

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
          cursor: pointer;
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
        .nav-card__chevron {
          display: flex; align-items: center; justify-content: center;
          width: 20px; height: 20px; border-radius: 6px;
          color: #94a3b8; flex-shrink: 0;
        }
        .nav-card__chevron:hover { background: rgba(37,99,235,0.1); color: #2563eb; }
        .nav-card--active { background: linear-gradient(135deg, #2563eb, #1d4ed8); border-color: #1d4ed8; box-shadow: 0 4px 12px rgba(37,99,235,0.35); }
        .nav-card--active:hover { background: linear-gradient(135deg, #2563eb, #1d4ed8); transform: none; }
        .nav-card--active .nav-card__icon { background: rgba(255,255,255,0.22); }
        .nav-card--active .nav-card__label { color: #ffffff; font-weight: 700; }
        .nav-card--active .nav-card__chevron { color: rgba(255,255,255,0.85); }
        .nav-card--active .nav-card__chevron:hover { background: rgba(255,255,255,0.18); color: #ffffff; }

        .nav-tree-children {
          display: flex; flex-direction: column; gap: 2px;
          margin: 4px 0 2px 20px;
          padding-left: 12px;
          border-left: 2px solid rgba(37,99,235,0.14);
        }
        .nav-subitem {
          display: block;
          padding: 7px 10px;
          border-radius: 8px;
          text-decoration: none;
          font-size: 11.5px;
          font-weight: 600;
          color: #64748b;
          transition: background 0.14s ease, color 0.14s ease;
        }
        .nav-subitem:hover { background: rgba(37,99,235,0.07); color: #2563eb; }
        .nav-subitem--active { background: rgba(37,99,235,0.1); color: #2563eb; font-weight: 700; }
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
              item.children?.length
                ? <NavTreeItem key={item.path} item={item} isOpen={expanded.has(item.path)} onToggle={toggle} />
                : <NavCard key={item.path} item={item} />
            ))}
          </div>
        </div>

        {/* EIS — standalone executive dashboard, not one of the DASHBOARD modules */}
        {EIS_ITEMS.filter((item) => isVisible(item.roles)).length > 0 && (
          <div>
            <p style={{ fontSize: 13, fontWeight: 800, color: "#334155", letterSpacing: "0.07em", marginBottom: 8, paddingLeft: 8 }}>
              EIS DASHBOARD
            </p>
            <div className="space-y-1.5">
              {EIS_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
                item.children?.length
                  ? <NavTreeItem key={item.path} item={item} isOpen={expanded.has(item.path)} onToggle={toggle} />
                  : <NavCard key={item.path} item={item} />
              ))}
            </div>
          </div>
        )}

        {/* SETUP — team names mirrored from DASHBOARD, one flat level of
            per-team configuration entries. */}
        {SETUP_ITEMS.filter((item) => isVisible(item.roles)).length > 0 && (
          <div>
            <p style={{ fontSize: 13, fontWeight: 800, color: "#334155", letterSpacing: "0.07em", marginBottom: 8, paddingLeft: 8 }}>
              SETUP
            </p>
            <div className="space-y-1.5">
              {SETUP_ITEMS.filter((item) => isVisible(item.roles)).map((item) => (
                item.children?.length
                  ? <NavTreeItem key={item.path} item={item} isOpen={expanded.has(item.path)} onToggle={toggle} />
                  : <NavCard key={item.path} item={item} />
              ))}
            </div>
          </div>
        )}

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
