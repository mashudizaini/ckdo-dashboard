/**
 * Site map A — Dashboard: My Overtime Summary, Upcoming Overtime, Rules.
 */
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen, CalendarClock, CheckCircle2, Clock, FileClock, Hourglass,
  RefreshCw, ThumbsDown, ClipboardCheck,
} from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import {
  Alert, Btn, Card, CATEGORY_BADGE, Empty, PLAN_STATUS, Pill, SectionTitle, Spinner,
  StatCard, Table, TEXT, TYPE_BADGE, errMsg, fmtDate, fmtHours,
} from "./ui";

export default function OvertimeDashboard({ me, goTo }) {
  const [summary, setSummary] = useState(null);
  const [upcoming, setUpcoming] = useState([]);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, u, r] = await Promise.all([
        overtimeApi.getSummary(month),
        overtimeApi.getUpcoming(8),
        overtimeApi.getRules(),
      ]);
      setSummary(s);
      setUpcoming(u || []);
      setRules(r || []);
    } catch (e) {
      setError(errMsg(e, "Could not load the overtime dashboard."));
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => { load(); }, [load]);

  if (loading && !summary) return <Spinner label="Loading your overtime summary..." />;

  const monthLabel = new Date(`${month}-01T00:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      {/* ── A.1 My Overtime Summary ── */}
      <Card>
        <SectionTitle
          icon={Clock}
          title="My Overtime Summary"
          subtitle={monthLabel}
          right={
            <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                style={{
                  fontSize: 12, padding: "6px 10px", borderRadius: 9, border: "none",
                  background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
                  color: TEXT.strong, outline: "none",
                }}
              />
              <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
            </div>
          }
        />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(168px, 1fr))", gap: 12 }}>
          <StatCard
            icon={Clock} label="This month" accent="#2563eb"
            value={Number(summary?.this_month_hours ?? 0).toFixed(2)} unit="hours"
            hint={`${Number(summary?.this_month_planned_hours ?? 0).toFixed(2)} h planned`}
          />
          <StatCard
            icon={FileClock} label="Pending order" accent="#f59e0b"
            value={summary?.pending_orders ?? 0} unit={(summary?.pending_orders ?? 0) === 1 ? "time" : "times"}
            hint="Awaiting approval" onClick={() => goTo("orders")}
          />
          <StatCard
            icon={ClipboardCheck} label="Realization" accent="#0ea5e9"
            value={summary?.realizations ?? 0} unit={(summary?.realizations ?? 0) === 1 ? "time" : "times"}
            hint={`${summary?.pending_realizations ?? 0} still in approval`} onClick={() => goTo("realization")}
          />
          <StatCard
            icon={CheckCircle2} label="Approved" accent="#16a34a"
            value={summary?.approved ?? 0} unit={(summary?.approved ?? 0) === 1 ? "time" : "times"}
            hint="Orders approved this month"
          />
          <StatCard
            icon={ThumbsDown} label="Rejected" accent="#dc2626"
            value={summary?.rejected ?? 0} unit={(summary?.rejected ?? 0) === 1 ? "time" : "times"}
            hint="Order or realization"
          />
        </div>

        {(summary?.to_be_realized > 0 || summary?.pending_approvals > 0) && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 13 }}>
            {summary.to_be_realized > 0 && (
              <Alert kind="warning" style={{ marginBottom: 0, flex: "1 1 260px" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <Hourglass size={13} />
                  {summary.to_be_realized} approved overtime {summary.to_be_realized === 1 ? "order" : "orders"} still
                  need a realization.
                  <button onClick={() => goTo("realization")} style={linkBtn}>Fill it in →</button>
                </span>
              </Alert>
            )}
            {summary.pending_approvals > 0 && (
              <Alert kind="info" style={{ marginBottom: 0, flex: "1 1 260px" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <CheckCircle2 size={13} />
                  {summary.pending_approvals} {summary.pending_approvals === 1 ? "request is" : "requests are"} waiting
                  for your approval.
                  <button onClick={() => goTo("approvals")} style={linkBtn}>Review →</button>
                </span>
              </Alert>
            )}
          </div>
        )}
      </Card>

      {/* ── A.2 Upcoming Overtime ── */}
      <Card>
        <SectionTitle icon={CalendarClock} title="Upcoming Overtime" subtitle="Your scheduled overtime from today onwards" />
        <Table
          columns={[
            { key: "no", label: "No", align: "center", render: (r) => r.__no },
            { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
            { key: "overtime_type", label: "Category", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
            { key: "work_category", label: "Work", render: (r) => <Pill map={CATEGORY_BADGE} value={r.work_category} /> },
            { key: "task_description", label: "Task / Target Result", wrap: true, maxWidth: 320,
              render: (r) => <span title={r.task_description}>{r.task_description}</span> },
            { key: "time", label: "Time", mono: true, render: (r) => `${r.plan_start} – ${r.plan_finish}` },
            { key: "planned_hours", label: "Duration", align: "right", render: (r) => fmtHours(r.planned_hours) },
            { key: "plan_status", label: "Status", render: (r) => <Pill map={PLAN_STATUS} value={r.plan_status} /> },
          ]}
          rows={upcoming.map((r, i) => ({ ...r, __no: i + 1 }))}
          empty="No upcoming overtime scheduled."
        />
      </Card>

      {/* ── A.3 Overtime Rules ── */}
      <Card>
        <SectionTitle icon={BookOpen} title="Overtime Rules" subtitle="Company policy, maintained by HRGA" />
        {rules.length === 0 ? (
          <Empty
            icon={BookOpen}
            title="No overtime rules published yet"
            hint={me?.is_hrga_admin
              ? "Add them under System Setting > Overtime Rules so every employee can see them here."
              : "HRGA has not published the overtime rules in this system yet."}
            action={me?.is_hrga_admin ? <Btn variant="primary" onClick={() => goTo("settings")}>Go to System Setting</Btn> : null}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {rules.map((r, i) => (
              <div key={r.id} style={{
                display: "flex", gap: 11, padding: "11px 13px", borderRadius: 11,
                background: "#ffffff", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
              }}>
                <span style={{
                  width: 22, height: 22, borderRadius: 7, background: "rgba(37,99,235,0.10)", color: "#2563eb",
                  fontSize: 11, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                  {i + 1}
                </span>
                <div>
                  <p style={{ fontSize: 12.5, fontWeight: 700, color: TEXT.strong, margin: 0 }}>{r.title}</p>
                  {r.content && (
                    <p style={{ fontSize: 11.5, color: TEXT.body, margin: "4px 0 0", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>
                      {r.content}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

const linkBtn = {
  background: "none", border: "none", padding: 0, cursor: "pointer",
  fontSize: 12, fontWeight: 800, color: "inherit", textDecoration: "underline",
};
