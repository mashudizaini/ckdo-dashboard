/**
 * Site map C.10 — Overtime Monitoring & Report (HRGA only).
 *
 * Weekday vs weekend (year on year, and month by month), planned vs
 * realized trend by department/team/employee, overtime cost, and the
 * exception report.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { AlertTriangle, BarChart3, RefreshCw } from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, Empty, Field, RZ_STATUS, Pill, SectionTitle, Select, Spinner,
  StatCard, Table, TEXT, TYPE_BADGE, errMsg, fmtDate, fmtGap, fmtIDR, gapColor,
} from "./ui";

const COLORS = { weekday: "#2563eb", weekend: "#a855f7", planned: "#94a3b8", realized: "#16a34a", cost: "#f59e0b" };

const EXCEPTION_LABEL = {
  gap_over_threshold: "Realized over plan",
  under_realized:     "Realized under plan",
  not_realized:       "Never realized",
  approval_overdue:   "Approval overdue",
  hrga_adjusted:      "HRGA reduced payable",
};

const EXCEPTION_COLOR = {
  gap_over_threshold: { bg: "#fef3c7", color: "#b45309" },
  under_realized:     { bg: "#e0f2fe", color: "#0369a1" },
  not_realized:       { bg: "#fee2e2", color: "#b91c1c" },
  approval_overdue:   { bg: "#ffedd5", color: "#c2410c" },
  hrga_adjusted:      { bg: "#f3e8ff", color: "#7e22ce" },
};

const chartTooltip = {
  contentStyle: { borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 11.5, boxShadow: "0 4px 12px rgba(15,23,42,0.10)" },
};

const axis = { tick: { fontSize: 10.5, fill: "#94a3b8" }, axisLine: { stroke: "#e2e8f0" }, tickLine: false };

function ChartBox({ title, subtitle, children, height = 260 }) {
  return (
    <div style={{ background: "#ffffff", borderRadius: 13, padding: 15, boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
      <p style={{ fontSize: 12.5, fontWeight: 700, color: TEXT.strong, margin: 0 }}>{title}</p>
      {subtitle && <p style={{ fontSize: 10.5, color: TEXT.muted, margin: "3px 0 10px" }}>{subtitle}</p>}
      <div style={{ height, marginTop: subtitle ? 0 : 10 }}>
        <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
      </div>
    </div>
  );
}

export default function OvertimeMonitoring() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [compareYear, setCompareYear] = useState(currentYear - 1);
  const [scope, setScope] = useState("department");
  const [department, setDepartment] = useState("");
  const [team, setTeam] = useState("");
  const [lov, setLov] = useState({ departments: [], teams: [] });
  const [data, setData] = useState(null);
  const [exceptions, setExceptions] = useState(null);
  const [excMonth, setExcMonth] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailId, setDetailId] = useState(null);

  useEffect(() => {
    overtimeApi.getLov().then(setLov).catch(() => { /* filters degrade to "All" */ });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { year, compare_year: compareYear, department: department || undefined, team: team || undefined };
      const [m, e] = await Promise.all([
        overtimeApi.getMonitoring(params),
        overtimeApi.getExceptions({
          year, month: excMonth ? Number(excMonth) : undefined,
          department: department || undefined, team: team || undefined,
        }),
      ]);
      setData(m);
      setExceptions(e);
      setError("");
    } catch (err) {
      setError(errMsg(err, "Could not load overtime monitoring."));
    } finally {
      setLoading(false);
    }
  }, [year, compareYear, department, team, excMonth]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <Spinner label="Loading monitoring report..." />;

  const yearly = data?.yearly || [];
  const cur = yearly.find((y) => y.year === year) || {};
  const prev = yearly.find((y) => y.year === compareYear) || {};
  const delta = (Number(cur.total_hours || 0) - Number(prev.total_hours || 0));

  const monthlyCombined = (data?.monthly || []).map((m, i) => ({
    ...m,
    compare_hours: data?.monthly_compare?.[i]?.realized_hours ?? 0,
  }));

  const scopeRows = scope === "team" ? (data?.by_team || [])
    : scope === "employee" ? (data?.by_employee || [])
      : (data?.by_department || []);
  const scopeKey = scope === "team" ? "team" : scope === "employee" ? "employee" : "department";

  const years = Array.from({ length: 6 }, (_, i) => currentYear - i);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <Card>
        <SectionTitle
          icon={BarChart3}
          title="Overtime Monitoring & Report"
          subtitle="Planned vs realized, weekday vs weekend, and where overtime is concentrating"
          right={<Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>}
        />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 11, marginBottom: 16 }}>
          <Field label="Year">
            <Select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
          <Field label="Compare with">
            <Select value={compareYear} onChange={(e) => setCompareYear(Number(e.target.value))}>
              {years.filter((y) => y !== year).map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
          <Field label="Department">
            <Select value={department} onChange={(e) => setDepartment(e.target.value)}>
              <option value="">All Departments</option>
              {lov.departments.map((d) => <option key={d} value={d}>{d}</option>)}
            </Select>
          </Field>
          <Field label="Team">
            <Select value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">All Teams</option>
              {lov.teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          </Field>
          <Field label="Break down by">
            <Select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="department">Department Overtime</option>
              <option value="team">Team Overtime</option>
              <option value="employee">Employee Overtime</option>
            </Select>
          </Field>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 18 }}>
          <StatCard label={`${year} realized`} value={Number(cur.total_hours ?? 0).toFixed(2)} unit="hours" accent="#16a34a"
            hint={`${Number(cur.planned_hours ?? 0).toFixed(2)} h planned`} />
          <StatCard label={`${compareYear} realized`} value={Number(prev.total_hours ?? 0).toFixed(2)} unit="hours" accent="#94a3b8" />
          <StatCard label="Year on year" accent={delta > 0 ? "#dc2626" : "#16a34a"}
            value={`${delta > 0 ? "+" : ""}${delta.toFixed(2)}`} unit="hours"
            hint={prev.total_hours ? `${((delta / prev.total_hours) * 100).toFixed(1)}% vs ${compareYear}` : "no comparison base"} />
          <StatCard label="Weekday / Weekend" accent="#2563eb"
            value={`${Number(cur.weekday_hours ?? 0).toFixed(0)} / ${Number(cur.weekend_hours ?? 0).toFixed(0)}`} unit="hours" />
          <StatCard label="Estimated cost" value={fmtIDR(cur.estimated_cost)} accent="#f59e0b"
            hint={`${cur.entries ?? 0} approved orders in ${year}`} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 14 }}>
          <ChartBox title="Weekday vs Weekend — Yearly" subtitle={`${compareYear} vs ${year}, realized hours`}>
            <BarChart data={yearly} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="year" {...axis} />
              <YAxis {...axis} />
              <Tooltip {...chartTooltip} formatter={(v) => `${Number(v).toFixed(2)} h`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="weekday_hours" name="Weekday" fill={COLORS.weekday} radius={[5, 5, 0, 0]} />
              <Bar dataKey="weekend_hours" name="Weekend / Holiday" fill={COLORS.weekend} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ChartBox>

          <ChartBox title="Weekday vs Weekend — Monthly" subtitle={`All months of ${year}`}>
            <BarChart data={data?.monthly || []} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="month_label" {...axis} />
              <YAxis {...axis} />
              <Tooltip {...chartTooltip} formatter={(v) => `${Number(v).toFixed(2)} h`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="weekday_hours" name="Weekday" stackId="a" fill={COLORS.weekday} />
              <Bar dataKey="weekend_hours" name="Weekend / Holiday" stackId="a" fill={COLORS.weekend} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ChartBox>

          <ChartBox title="Planned vs Realized — Monthly Trend" subtitle={`${year}, with ${compareYear} realized for reference`}>
            <LineChart data={monthlyCombined} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="month_label" {...axis} />
              <YAxis {...axis} />
              <Tooltip {...chartTooltip} formatter={(v) => `${Number(v).toFixed(2)} h`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="planned_hours" name="Planned" stroke={COLORS.planned} strokeWidth={2} dot={false} strokeDasharray="4 3" />
              <Line type="monotone" dataKey="realized_hours" name={`Realized ${year}`} stroke={COLORS.realized} strokeWidth={2.4} dot={{ r: 2.5 }} />
              <Line type="monotone" dataKey="compare_hours" name={`Realized ${compareYear}`} stroke={COLORS.weekday} strokeWidth={1.6} dot={false} strokeDasharray="2 3" />
            </LineChart>
          </ChartBox>

          <ChartBox title="Overtime Cost — Monthly" subtitle={`Estimated, from the grade rates configured under System Setting`}>
            <BarChart data={data?.monthly || []} margin={{ top: 6, right: 8, left: 6, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="month_label" {...axis} />
              <YAxis {...axis} tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(0)}jt` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}rb` : v)} />
              <Tooltip {...chartTooltip} formatter={(v) => fmtIDR(v)} />
              <Bar dataKey="estimated_cost" name="Estimated cost" fill={COLORS.cost} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ChartBox>

          <ChartBox
            title={`Planned vs Realized — by ${scopeKey}`}
            subtitle={`${year}${department ? ` · ${department}` : ""}${team ? ` · ${team}` : ""}`}
            height={Math.max(240, Math.min(scopeRows.length * 26 + 60, 460))}
          >
            <BarChart data={scopeRows.slice(0, 14)} layout="vertical" margin={{ top: 6, right: 14, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" {...axis} />
              <YAxis type="category" dataKey={scopeKey} width={126} {...axis} />
              <Tooltip {...chartTooltip} formatter={(v) => `${Number(v).toFixed(2)} h`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="planned_hours" name="Planned" fill={COLORS.planned} radius={[0, 4, 4, 0]} />
              <Bar dataKey="realized_hours" name="Realized" fill={COLORS.realized} radius={[0, 4, 4, 0]}>
                {scopeRows.slice(0, 14).map((r, i) => (
                  <Cell key={i} fill={r.realized_hours > r.planned_hours ? "#f59e0b" : COLORS.realized} />
                ))}
              </Bar>
            </BarChart>
          </ChartBox>
        </div>

        <div style={{ marginTop: 16 }}>
          <p style={{ fontSize: 12.5, fontWeight: 700, color: TEXT.strong, margin: "0 0 9px" }}>
            Overtime Hours — by {scopeKey}
          </p>
          <Table
            columns={[
              { key: scopeKey, label: scopeKey.charAt(0).toUpperCase() + scopeKey.slice(1),
                render: (r) => <strong style={{ color: TEXT.strong }}>{r[scopeKey]}</strong> },
              { key: "employee_count", label: "Employees", align: "right" },
              { key: "entries", label: "Orders", align: "right" },
              { key: "planned_hours", label: "Planned (h)", align: "right", render: (r) => r.planned_hours.toFixed(2) },
              { key: "realized_hours", label: "Realized (h)", align: "right",
                render: (r) => <strong style={{ color: "#15803d" }}>{r.realized_hours.toFixed(2)}</strong> },
              { key: "variance_hours", label: "Variance", align: "right",
                render: (r) => <span style={{ color: gapColor(r.variance_hours) }}>{fmtGap(r.variance_hours)}</span> },
              { key: "weekday_hours", label: "Weekday (h)", align: "right", render: (r) => r.weekday_hours.toFixed(2) },
              { key: "weekend_hours", label: "Weekend (h)", align: "right", render: (r) => r.weekend_hours.toFixed(2) },
              { key: "estimated_cost", label: "Estimated Cost", align: "right", render: (r) => fmtIDR(r.estimated_cost) },
            ]}
            rows={scopeRows}
            rowKey={(r) => r[scopeKey]}
            empty={`No overtime recorded in ${year} for this filter.`}
          />
        </div>
      </Card>

      {/* ── Exception Report ── */}
      <Card>
        <SectionTitle
          icon={AlertTriangle}
          title="Exception Report"
          subtitle="Where realization diverged from the plan — including orders that were never realized at all"
          right={
            <div style={{ width: 160 }}>
              <Select value={excMonth} onChange={(e) => setExcMonth(e.target.value)}>
                <option value="">Whole year {year}</option>
                {["January","February","March","April","May","June","July","August","September","October","November","December"]
                  .map((m, i) => <option key={m} value={i + 1}>{m} {year}</option>)}
              </Select>
            </div>
          }
        />

        {(exceptions?.exceptions?.length ?? 0) === 0 ? (
          <Empty icon={AlertTriangle} title="No exceptions in this period"
            hint="Every approved order was realized within tolerance and cleared the approval chain." />
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 11, marginBottom: 14 }}>
              <StatCard label="Exceptions" value={exceptions.total} accent="#dc2626" hint={`threshold ${exceptions.threshold_minutes} min`} />
              {(exceptions.by_department || []).slice(0, 4).map((d) => (
                <StatCard key={d.department} label={d.department} value={d.count} unit="cases" accent="#f59e0b"
                  hint={`${fmtGap(d.gap_hours)} total gap`} />
              ))}
            </div>

            <Table
              maxHeight={420}
              columns={[
                { key: "request_no", label: "Request No", mono: true },
                { key: "employee_name", label: "Employee", render: (r) => <strong style={{ color: TEXT.strong }}>{r.employee_name}</strong> },
                { key: "department", label: "Dept" },
                { key: "team", label: "Team" },
                { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
                { key: "overtime_type", label: "Type", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
                { key: "planned_hours", label: "Planned", align: "right", render: (r) => r.planned_hours.toFixed(2) },
                { key: "actual_hours", label: "Realized", align: "right", render: (r) => r.actual_hours.toFixed(2) },
                { key: "gap_hours", label: "Gap", align: "right",
                  render: (r) => <span style={{ color: gapColor(r.gap_hours), fontWeight: 700 }}>{fmtGap(r.gap_hours)}</span> },
                { key: "rz_status", label: "Realization", render: (r) => <Pill map={RZ_STATUS} value={r.rz_status} /> },
                { key: "kinds", label: "Exception", render: (r) => (
                  <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
                    {r.kinds.map((k) => {
                      const c = EXCEPTION_COLOR[k] || { bg: "#e2e8f0", color: "#64748b" };
                      return (
                        <span key={k} style={{
                          padding: "2px 8px", borderRadius: 20, fontSize: 10.5, fontWeight: 700,
                          background: c.bg, color: c.color, whiteSpace: "nowrap",
                        }}>
                          {EXCEPTION_LABEL[k] || k}
                        </span>
                      );
                    })}
                  </span>
                ) },
                { key: "gap_reason", label: "Reason", wrap: true, maxWidth: 240,
                  render: (r) => <span title={r.gap_reason || ""}>{r.gap_reason || "—"}</span> },
              ]}
              rows={exceptions.exceptions}
              rowKey={(r) => r.id}
              onRowClick={(r) => setDetailId(r.id)}
            />
          </>
        )}
      </Card>

      <RequestDetail
        requestId={detailId}
        open={!!detailId}
        onClose={() => setDetailId(null)}
        footer={<Btn onClick={() => setDetailId(null)}>Close</Btn>}
      />
    </div>
  );
}
