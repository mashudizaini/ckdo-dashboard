/**
 * Site map C.9 — Overtime Calculation (HRGA only).
 *
 * Payable overtime for a cut-off period, the figure that goes to payroll.
 * Shows the same numbers three ways (detail / by department / by team /
 * by employee) and exports the lot to Excel.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Calculator, Download, RefreshCw } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, Empty, Field, Pill, SectionTitle, Select, Spinner, StatCard,
  Table, TEXT, TYPE_BADGE, errMsg, fmtDate, fmtGap, fmtIDR, gapColor,
} from "./ui";

const VIEWS = [
  { id: "detail",     label: "Show All Detail" },
  { id: "department", label: "By Department" },
  { id: "team",       label: "By Team" },
  { id: "employee",   label: "By Employee" },
];

export default function OvertimeCalculation() {
  const { token } = useAuthStore();
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState("");
  const [cutoff, setCutoff] = useState(null);
  const [lov, setLov] = useState({ departments: [], teams: [] });
  const [department, setDepartment] = useState("");
  const [team, setTeam] = useState("");
  const [data, setData] = useState(null);
  const [view, setView] = useState("detail");
  const [sortDir, setSortDir] = useState("desc");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [detailId, setDetailId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [p, l] = await Promise.all([overtimeApi.getPeriods(), overtimeApi.getLov()]);
        setPeriods(p.periods || []);
        setCutoff(p.cutoff);
        setLov(l);
        setPeriod(p.periods?.[0]?.key || "");
      } catch (e) {
        setError(errMsg(e, "Could not load cut-off periods."));
        setLoading(false);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    try {
      setData(await overtimeApi.getCalculation({ period, department: department || undefined, team: team || undefined }));
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not run the overtime calculation."));
    } finally {
      setLoading(false);
    }
  }, [period, department, team]);

  useEffect(() => { load(); }, [load]);

  const exportExcel = async () => {
    setExporting(true);
    let url;
    try {
      const res = await fetch(
        overtimeApi.exportCalculationUrl({ period, department, team }),
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error("export failed");
      url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `Overtime_Calculation_${period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (_) {
      setError("Could not export the calculation to Excel.");
    } finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExporting(false);
    }
  };

  const totals = data?.totals || {};
  const sortRows = (rows) => [...rows].sort((a, b) =>
    sortDir === "desc" ? b.total_hours - a.total_hours : a.total_hours - b.total_hours);

  const groupColumns = (key, label) => [
    { key, label, render: (r) => (
      <strong style={{ color: TEXT.strong }}>
        {key === "employee" ? (r[key] || "").split("|").slice(-1)[0] : r[key]}
      </strong>
    ) },
    ...(key === "employee" ? [{ key: "nik", label: "NIK", mono: true, render: (r) => (r.employee || "").split("|")[0] }] : []),
    { key: "employee_count", label: key === "employee" ? "" : "Employees", align: "right",
      render: (r) => (key === "employee" ? "" : r.employee_count) },
    { key: "entries", label: "Entries", align: "right" },
    { key: "weekday_hours", label: "Weekday (h)", align: "right", render: (r) => r.weekday_hours.toFixed(2) },
    { key: "weekend_hours", label: "Weekend (h)", align: "right", render: (r) => r.weekend_hours.toFixed(2) },
    { key: "total_hours", label: "Total Overtime Hours", align: "right",
      render: (r) => <strong style={{ color: "#1d4ed8" }}>{r.total_hours.toFixed(2)}</strong> },
    { key: "overtime_index", label: "OT Index (h)", align: "right", render: (r) => r.overtime_index.toFixed(2) },
    { key: "estimated_cost", label: "Estimated Cost", align: "right", render: (r) => fmtIDR(r.estimated_cost) },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <Card>
        <SectionTitle
          icon={Calculator}
          title="Overtime Calculation"
          subtitle={cutoff
            ? `Cut-off period runs from day ${cutoff.start_day} to day ${cutoff.end_day} of the following month`
            : "Payable overtime per cut-off period"}
          right={
            <div style={{ display: "flex", gap: 7 }}>
              <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
              <Btn icon={Download} variant="primary" onClick={exportExcel} loading={exporting}>Export to Excel</Btn>
            </div>
          }
        />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 11, marginBottom: 16 }}>
          <Field label="Select Cut-Off Period">
            <Select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {periods.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
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
          <Field label="Sort by total hours">
            <Select value={sortDir} onChange={(e) => setSortDir(e.target.value)}>
              <option value="desc">High to Low</option>
              <option value="asc">Low to High</option>
            </Select>
          </Field>
        </div>

        {loading && !data ? <Spinner label="Calculating..." /> : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 16 }}>
              <StatCard label="Total overtime" value={Number(totals.total_hours ?? 0).toFixed(2)} unit="hours" accent="#2563eb"
                hint={data?.period?.label} />
              <StatCard label="Weekday" value={Number(totals.weekday_hours ?? 0).toFixed(2)} unit="hours" accent="#0ea5e9" />
              <StatCard label="Weekend / holiday" value={Number(totals.weekend_hours ?? 0).toFixed(2)} unit="hours" accent="#7e22ce" />
              <StatCard label="Employees" value={totals.employee_count ?? 0} unit="people" accent="#16a34a"
                hint={`${totals.entries ?? 0} approved entries`} />
              <StatCard label="Estimated cost" value={fmtIDR(totals.estimated_cost)} accent="#f59e0b"
                hint={`OT index ${Number(totals.overtime_index ?? 0).toFixed(2)} h`} />
            </div>

            {totals.pending_in_period > 0 && (
              <Alert kind="warning">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
                  <AlertTriangle size={13} />
                  {totals.pending_in_period} realization(s) in this period are still in the approval chain and are
                  <strong> not</strong> included above. Close them before sending this period to payroll.
                </span>
              </Alert>
            )}

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 13 }}>
              {VIEWS.map((v) => {
                const on = view === v.id;
                return (
                  <button
                    key={v.id}
                    onClick={() => setView(v.id)}
                    style={{
                      padding: "5px 13px", borderRadius: 20, border: "none", cursor: "pointer",
                      fontSize: 11.5, fontWeight: 700,
                      background: on ? "#2563eb" : "#ffffff", color: on ? "#fff" : TEXT.body,
                      boxShadow: on ? "0 3px 8px rgba(37,99,235,0.30)" : "0 1px 2px rgba(15,23,42,0.08)",
                    }}
                  >
                    {v.label}
                  </button>
                );
              })}
            </div>

            {view === "detail" && (
              (data?.detail?.length ?? 0) === 0 ? (
                <Empty icon={Calculator} title="No approved overtime in this period"
                  hint="Only realizations that passed HRGA's final check are counted here." />
              ) : (
                <Table
                  maxHeight={520}
                  columns={[
                    { key: "request_no", label: "Request No", mono: true },
                    { key: "employee_id", label: "NIK", mono: true },
                    { key: "employee_name", label: "Name", render: (r) => <strong style={{ color: TEXT.strong }}>{r.employee_name}</strong> },
                    { key: "department", label: "Dept" },
                    { key: "team", label: "Team" },
                    { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
                    { key: "overtime_type", label: "Category", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
                    { key: "planned_hours", label: "Planned", align: "right", render: (r) => r.planned_hours.toFixed(2) },
                    { key: "actual_hours", label: "Actual", align: "right", render: (r) => r.actual_hours.toFixed(2) },
                    { key: "gap_hours", label: "Gap", align: "right",
                      render: (r) => <span style={{ color: gapColor(r.gap_hours) }}>{fmtGap(r.gap_hours)}</span> },
                    { key: "payable_hours", label: "Overtime Hours", align: "right",
                      render: (r) => <strong style={{ color: "#1d4ed8" }}>{r.payable_hours.toFixed(2)}</strong> },
                    { key: "overtime_index", label: "OT Index", align: "right", render: (r) => r.overtime_index.toFixed(2) },
                    { key: "estimated_cost", label: "Cost", align: "right", render: (r) => fmtIDR(r.estimated_cost) },
                  ]}
                  rows={data.detail}
                  rowKey={(r) => r.id}
                  onRowClick={(r) => setDetailId(r.id)}
                />
              )
            )}

            {view === "department" && <Table columns={groupColumns("department", "Department")} rows={sortRows(data?.by_department || [])} rowKey={(r) => r.department} />}
            {view === "team"       && <Table columns={groupColumns("team", "Team")}             rows={sortRows(data?.by_team || [])}       rowKey={(r) => r.team} />}
            {view === "employee"   && <Table columns={groupColumns("employee", "Employee")}     rows={sortRows(data?.by_employee || [])}   rowKey={(r) => r.employee} />}
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
