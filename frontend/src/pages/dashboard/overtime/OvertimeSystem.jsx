/**
 * Digital Overtime Management System — module shell.
 *
 * One page, role-aware tabs. Which tabs exist comes from GET /overtime/me
 * (resolved server-side from the Employee master + approval matrix), not
 * from Keycloak roles — an ordinary employee, a Team Head and an HRGA
 * administrator all open the same URL and get the screens that apply to
 * them. The server re-checks every one of those rights on each call; the
 * tab list is a convenience, never the access control.
 */
import { useCallback, useEffect, useState } from "react";
import {
  BarChart3, Bell, CalendarClock, CheckSquare, ClipboardList, Clock,
  Calculator, Settings, ShieldAlert,
} from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import { Alert, Card, Empty, Spinner, Tabs, TEXT, NEU, ROLE_LABEL, errMsg } from "./ui";
import OvertimeDashboard from "./OvertimeDashboard";
import OvertimeOrders from "./OvertimeOrders";
import OvertimeRealization from "./OvertimeRealization";
import OvertimeApprovals from "./OvertimeApprovals";
import OvertimeCalculation from "./OvertimeCalculation";
import OvertimeMonitoring from "./OvertimeMonitoring";
import OvertimeSettings from "./OvertimeSettings";
import OvertimeNotifications from "./OvertimeNotifications";

export default function OvertimeSystem() {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("dashboard");
  const [counts, setCounts] = useState({ approvals: 0, notifications: 0 });

  const loadMe = useCallback(async () => {
    try {
      const data = await overtimeApi.me();
      setMe(data);
      setCounts((c) => ({ ...c, notifications: data.unread_notifications || 0 }));
      return data;
    } catch (e) {
      setError(errMsg(e, "Could not load your overtime profile."));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshBadges = useCallback(async (profile) => {
    const p = profile || me;
    if (!p) return;
    try {
      const notif = await overtimeApi.getNotifications({ unread_only: true, limit: 1 });
      setCounts((c) => ({ ...c, notifications: notif.unread || 0 }));
    } catch (_) { /* badge only — never block the page on it */ }
    if (p.is_team_head || p.is_dept_head || p.is_hrga_admin) {
      try {
        const inbox = await overtimeApi.getApprovals();
        setCounts((c) => ({ ...c, approvals: inbox.counts?.total || 0 }));
      } catch (_) { /* same */ }
    }
  }, [me]);

  useEffect(() => { loadMe().then((p) => p && refreshBadges(p)); }, []); // eslint-disable-line

  if (loading) return <Spinner label="Loading overtime module..." />;

  if (error) {
    return (
      <Card>
        <Alert kind="error">{error}</Alert>
      </Card>
    );
  }

  if (!me?.employee_linked) {
    return (
      <Card>
        <Empty
          icon={ShieldAlert}
          title="Your login is not linked to an employee record"
          hint="Overtime is filed against your employee master data. Ask HRGA to set your company email on Employee Data, then reload this page."
        />
      </Card>
    );
  }

  const isApprover = me.is_team_head || me.is_dept_head || me.is_hrga_admin;

  const tabs = [
    { id: "dashboard",    label: "Dashboard",        icon: Clock },
    { id: "orders",       label: "Overtime Order",   icon: ClipboardList },
    { id: "realization",  label: "Realization",      icon: CalendarClock },
    ...(isApprover ? [{ id: "approvals", label: "Approvals", icon: CheckSquare, badge: counts.approvals }] : []),
    ...(me.is_hrga_admin ? [
      { id: "calculation", label: "Calculation",     icon: Calculator },
      { id: "monitoring",  label: "Monitoring & Report", icon: BarChart3 },
      { id: "settings",    label: "System Setting",  icon: Settings },
    ] : []),
    { id: "notifications", label: "Notification", icon: Bell, badge: counts.notifications },
  ];

  const shared = { me, refreshBadges: () => refreshBadges(me), goTo: setTab };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div>
          <h2 style={{ fontSize: 17, fontWeight: 800, color: TEXT.strong, margin: 0 }}>
            Digital Overtime Management System
          </h2>
          <p style={{ fontSize: 11.5, color: TEXT.muted, margin: "3px 0 0" }}>
            Plan, realize and approve overtime — from the employee's order through to HRGA's payable calculation.
          </p>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
          borderRadius: 12, background: NEU.bg, boxShadow: NEU.outSm,
        }}>
          <div style={{ textAlign: "right" }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: TEXT.strong, margin: 0 }}>{me.full_name}</p>
            <p style={{ fontSize: 10.5, color: TEXT.muted, margin: 0 }}>
              {me.employee_id} · {me.team || me.department || "—"} · {ROLE_LABEL[me.role_level] || me.role_level}
            </p>
          </div>
        </div>
      </div>

      {!me.matrix_configured && (
        <Alert kind="warning">
          No approval matrix is configured for you yet — you can save drafts, but submitting needs a Team Head and
          Department Head. Ask HRGA to set them under Overtime &gt; System Setting &gt; Approval Matrix.
        </Alert>
      )}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === "dashboard"     && <OvertimeDashboard {...shared} />}
      {tab === "orders"        && <OvertimeOrders {...shared} />}
      {tab === "realization"   && <OvertimeRealization {...shared} />}
      {tab === "approvals"     && <OvertimeApprovals {...shared} />}
      {tab === "calculation"   && <OvertimeCalculation {...shared} />}
      {tab === "monitoring"    && <OvertimeMonitoring {...shared} />}
      {tab === "settings"      && <OvertimeSettings {...shared} />}
      {tab === "notifications" && <OvertimeNotifications {...shared} />}
    </div>
  );
}
