import { useState, useEffect, useCallback, useMemo } from "react";
import * as XLSX from "xlsx";
import {
  Users, UserCheck, BarChart2, RefreshCw,
  Upload, Search, ChevronLeft, ChevronRight, X, Loader2, CalendarCheck,
  Wallet, Download, ChevronDown, ChevronUp, ListChecks, FileSearch, BookOpen, Trash2,
  QrCode, Plus, ArrowUpDown, Pencil, ZoomIn, ZoomOut, Maximize2, Minimize2, Network,
} from "lucide-react";
import EmployeeUpload from "./EmployeeUpload";
import AttendanceUpload from "./AttendanceUpload";
import LeaveUpload from "./LeaveUpload";
import HRTodoList from "./HRTodoList";
import HRCvScreening from "./HRCvScreening";
import { useAuthStore } from "@/store/authStore";
import { hrApi } from "@/api/dashboard";
import { SortableTH, toggleSort, sortRows } from "@/components/SortableTH";

const API        = "/api/v1/dashboard/hr/employees";
const BUDGET_API = "/api/v1/dashboard/hr/budget";

const MONTHS_ID = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ── Employee List Excel export — field list shown in the download picker ──
const EMPLOYEE_COLS = [
  { key: "user_id",          label: "NIK" },
  { key: "full_name",        label: "Name" },
  { key: "level",            label: "Level" },
  { key: "department",       label: "Department" },
  { key: "division",         label: "Division" },
  { key: "team",             label: "Team" },
  { key: "job_title",        label: "Position" },
  { key: "work_placement",   label: "Placement" },
  { key: "status",           label: "Status" },
  { key: "sex",              label: "Gender" },
  { key: "employee_grade",   label: "Grade" },
  { key: "education_degree", label: "Education" },
  { key: "marital_status",   label: "Marital" },
  { key: "date_of_joining",  label: "Join Date" },
  { key: "end_pkwt",         label: "End PKWT" },
  { key: "phone_number",     label: "Phone" },
];

const NEU_TAB = {
  bg: "#e8edf5",
  out: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  inset: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
};

function SubTabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          style={{
            padding: "7px 16px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
            background: NEU_TAB.bg, cursor: "pointer",
            color: active === t.id ? "#2563eb" : "#64748b",
            boxShadow: active === t.id ? NEU_TAB.inset : NEU_TAB.out,
            transition: "all 0.2s ease",
          }}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export default function HRDashboard() {
  const [activeSection, setActiveSection] = useState("employees");
  const [empSub, setEmpSub] = useState("list");
  const [attSub, setAttSub] = useState("summary");

  const kpiCards = [
    { id: "employees",  icon: Users,         color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Employee Data" },
    { id: "attendance", icon: BarChart2,     color: "text-indigo-400", bg: "bg-indigo-500/10", activeBorder: "border-indigo-500/40", label: "Attendance Rate" },
    { id: "todo",       icon: ListChecks,    color: "text-rose-400",   bg: "bg-rose-500/10",   activeBorder: "border-rose-500/40",   label: "To Do List" },
    { id: "cv",         icon: FileSearch,    color: "text-cyan-400",   bg: "bg-cyan-500/10",   activeBorder: "border-cyan-500/40",   label: "E-Recruitment" },
    { id: "budget",     icon: Wallet,        color: "text-orange-400", bg: "bg-orange-500/10", activeBorder: "border-orange-500/40", label: "Budget Monitoring" },
    { id: "emagazine",  icon: BookOpen,      color: "text-teal-400",   bg: "bg-teal-500/10",   activeBorder: "border-teal-500/40",   label: "e-Magazine" },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons — 6 tabs */}
      <div className="grid grid-cols-2 xl:grid-cols-7 gap-2">
        {kpiCards.map((c) => (
          <button
            key={c.id}
            onClick={() => setActiveSection(activeSection === c.id ? null : c.id)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 transition-all ${
              activeSection === c.id
                ? `${c.bg} ${c.activeBorder} ring-1 ring-inset ${c.activeBorder}`
                : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
            }`}
          >
            <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${c.bg} border ${c.activeBorder}`}>
              <c.icon size={14} className={c.color} />
            </div>
            <span className={`text-sm font-semibold leading-tight ${activeSection === c.id ? "text-white" : "text-gray-400"}`}>
              {c.label}
            </span>
          </button>
        ))}
      </div>

      {/* ── Employee Data (list + upload) ── */}
      {activeSection === "employees" && (
        <SectionCard>
          <SubTabs
            tabs={[
              { id: "list",     label: "Employee List" },
              { id: "summary",  label: "Employee Summary" },
              { id: "graph",    label: "Employee Graph" },
              { id: "orgchart", label: "Organization Chart" },
              { id: "turnover", label: "Turnover Report" },
              { id: "upload",   label: "Upload Excel" },
            ]}
            active={empSub} onChange={setEmpSub}
          />
          {empSub === "list"     && <EmployeeTable />}
          {empSub === "summary"  && <EmployeeSummarySection />}
          {empSub === "graph"    && <EmployeeGraphSection />}
          {empSub === "orgchart" && <OrganizationChartSection />}
          {empSub === "turnover" && <TurnoverSection />}
          {empSub === "upload"   && <EmployeeUpload />}
        </SectionCard>
      )}

      {/* ── Attendance Rate (summary/detail + leave + upload) ── */}
      {activeSection === "attendance" && (
        <SectionCard>
          <AttendanceRateSection />
        </SectionCard>
      )}

      {activeSection === "todo" && (
        <SectionCard>
          <HRTodoList />
        </SectionCard>
      )}

      {activeSection === "cv" && (
        <SectionCard>
          <HRCvScreening />
        </SectionCard>
      )}

      {activeSection === "budget" && (
        <SectionCard>
          <BudgetMonitoringSection />
        </SectionCard>
      )}

      {activeSection === "emagazine" && (
        <SectionCard>
          <EMagazineSection />
        </SectionCard>
      )}
    </div>
  );
}

// ── Tabel karyawan dengan search + filter + pagination ────────────────────────
function EmployeeTable() {
  const { token }    = useAuthStore();
  const headers      = { Authorization: `Bearer ${token}` };

  const [data,       setData]       = useState({ employees: [], total: 0, pages: 1 });
  const [loading,    setLoading]    = useState(false);
  const [page,       setPage]       = useState(1);
  const [search,     setSearch]     = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [genderFilter, setGenderFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [departments, setDepartments]   = useState([]);
  const [teams,       setTeams]         = useState([]);
  const [summary,    setSummary]    = useState(null);
  const [sortBy,     setSortBy]     = useState("full_name");
  const [sortDir,    setSortDir]    = useState("asc");
  const [showExportPicker, setShowExportPicker] = useState(false);
  const [exportFields, setExportFields] = useState(() => Object.fromEntries(EMPLOYEE_COLS.map(c => [c.key, true])));
  const [exporting, setExporting] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [employeeNames, setEmployeeNames] = useState([]);

  const PAGE_SIZE = 8;

  const fetchDepts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/departments`, { headers });
      if (res.ok) setDepartments(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  const fetchEmployeeNames = useCallback(async () => {
    try { setEmployeeNames((await hrApi.getEmployeeNames()).data || []); } catch (_) {}
  }, []); // eslint-disable-line

  const fetchTeams = useCallback(async (dept) => {
    try {
      const url = dept ? `${API}/teams?department=${encodeURIComponent(dept)}` : `${API}/teams`;
      const res = await fetch(url, { headers });
      if (res.ok) setTeams(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API}/summary`, { headers });
      if (res.ok) setSummary(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page:      page,
        page_size: PAGE_SIZE,
        sort_by:   sortBy,
        sort_dir:  sortDir,
        ...(search       ? { search }               : {}),
        ...(deptFilter   ? { department: deptFilter } : {}),
        ...(statusFilter ? { status: statusFilter }  : {}),
        ...(teamFilter   ? { team: teamFilter }      : {}),
        ...(genderFilter ? { sex: genderFilter === "Male" ? "M" : "F" } : {}),
      });
      const res = await fetch(`${API}?${params}`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, search, deptFilter, statusFilter, teamFilter, genderFilter, sortBy, sortDir]); // eslint-disable-line

  useEffect(() => { fetchDepts(); fetchSummary(); fetchTeams(""); fetchEmployeeNames(); }, []); // eslint-disable-line
  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  const [activeCard, setActiveCard] = useState("");

  const handleSearch   = (v) => { setSearch(v);       setPage(1); };
  const handleDept     = (v) => { setDeptFilter(v);   setTeamFilter(""); fetchTeams(v); setPage(1); };
  const handleStatus   = (v) => { setStatusFilter(v); setPage(1); };
  const handleTeam     = (v) => { setTeamFilter(v);   setPage(1); };

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir((d) => d === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
    setPage(1);
  };

  const handleCardClick = (id) => {
    if (activeCard === id) {
      setActiveCard(""); setStatusFilter(""); setGenderFilter(""); setPage(1);
    } else {
      setActiveCard(id);
      if (id === "permanent")  { setStatusFilter("Permanent"); setGenderFilter(""); }
      else if (id === "contract")  { setStatusFilter("Contract");  setGenderFilter(""); }
      else if (id === "probation") { setStatusFilter("Probation"); setGenderFilter(""); }
      else if (id === "male")   { setStatusFilter(""); setGenderFilter("Male"); }
      else if (id === "female") { setStatusFilter(""); setGenderFilter("Female"); }
      else { setStatusFilter(""); setGenderFilter(""); }
      setPage(1);
    }
  };

  const STATUS_BADGE = {
    "Permanent": "bg-green-500/15 text-green-400 border-green-500/30",
    "Contract":  "bg-amber-500/15 text-amber-400 border-amber-500/30",
    "Probation": "bg-purple-500/15 text-purple-400 border-purple-500/30",
  };

  const toggleExportField = (key) => setExportFields(p => ({ ...p, [key]: !p[key] }));
  const setAllExportFields = (val) => setExportFields(Object.fromEntries(EMPLOYEE_COLS.map(c => [c.key, val])));

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams({
        page: 1, page_size: 5000, sort_by: sortBy, sort_dir: sortDir,
        ...(search       ? { search }                : {}),
        ...(deptFilter   ? { department: deptFilter } : {}),
        ...(statusFilter ? { status: statusFilter }   : {}),
        ...(teamFilter   ? { team: teamFilter }        : {}),
        ...(genderFilter ? { sex: genderFilter === "Male" ? "M" : "F" } : {}),
      });
      const res = await fetch(`${API}?${params}`, { headers });
      const body = await res.json();
      const rows = body.employees ?? [];
      const cols = EMPLOYEE_COLS.filter(c => exportFields[c.key]);
      const fmtDate = (v) => v ? new Date(v).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }) : "";
      const cellValue = (e, key) => {
        if (key === "date_of_joining" || key === "end_pkwt") return fmtDate(e[key]);
        if (key === "sex") return e.sex === "M" ? "Male" : e.sex === "F" ? "Female" : "";
        return e[key] ?? "";
      };
      const aoa = [cols.map(c => c.label), ...rows.map(e => cols.map(c => cellValue(e, c.key)))];
      const ws = XLSX.utils.aoa_to_sheet(aoa);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, "Employees");
      XLSX.writeFile(wb, `employee_data_${new Date().toISOString().slice(0, 10)}.xlsx`);
      setShowExportPicker(false);
    } catch (_) {
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Summary cards — clickable */}
      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
          {[
            { id: "total",      label: "Total Employees", val: summary.total,      color: "#2563eb", icon: "👥" },
            { id: "permanent",  label: "Permanent",       val: summary.permanent,  color: "#22c55e", icon: "✓" },
            { id: "contract",   label: "Contract",        val: summary.contract,   color: "#f59e0b", icon: "📋" },
            { id: "probation",  label: "Probation",       val: summary.probation,  color: "#a855f7", icon: "⏳" },
            { id: "male",       label: "Male",            val: summary.male,       color: "#3b82f6", icon: "♂" },
            { id: "female",     label: "Female",          val: summary.female,     color: "#ec4899", icon: "♀" },
          ].map(({ id, label, val, color, icon }) => {
            const isActive = activeCard === id;
            return (
              <button key={id} onClick={() => handleCardClick(id)}
                style={{
                  padding: "6px 8px", borderRadius: 10, border: "none",
                  background: isActive ? color : "#e8edf5",
                  boxShadow: isActive
                    ? "inset 2px 2px 4px rgba(0,0,0,0.2)"
                    : "3px 3px 7px #c5cad8, -3px -3px 7px #ffffff",
                  cursor: "pointer", textAlign: "center",
                  transform: isActive ? "scale(0.97)" : "scale(1)",
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ fontSize: 15, fontWeight: 800, color: isActive ? "#fff" : color }}>{val}</div>
                <div style={{ fontSize: 9, fontWeight: 700, color: isActive ? "rgba(255,255,255,0.85)" : "#64748b", marginTop: 1 }}>{label}</div>
              </button>
            );
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search name / NIK / position..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-8 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 transition-colors"
          />
          {search && (
            <button onClick={() => handleSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400">
              <X size={13} />
            </button>
          )}
        </div>

        <select
          value={deptFilter}
          onChange={(e) => handleDept(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="">All Departments</option>
          {departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => handleStatus(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="">All Statuses</option>
          <option value="Permanent">Permanent</option>
          <option value="Contract">Contract</option>
          <option value="Probation">Probation</option>
        </select>

        <select
          value={teamFilter}
          onChange={(e) => handleTeam(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="">All Teams</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <button
          onClick={() => fetchEmployees()}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-400 hover:border-gray-600 hover:text-gray-200 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>

        <div className="relative">
          <button
            onClick={() => setShowExportPicker(v => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-700/50 bg-emerald-900/20 px-3 py-2 text-sm text-emerald-400 hover:border-emerald-600 hover:bg-emerald-900/30 transition-colors"
          >
            <Download size={13} /> Download Excel
          </button>
          {showExportPicker && (
            <>
              <div onClick={() => setShowExportPicker(false)} className="fixed inset-0 z-20" />
              <div className="absolute right-0 top-full mt-2 z-30 w-64 rounded-xl border border-gray-700 bg-gray-900 shadow-2xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-300">Select fields to export</span>
                  <div className="flex gap-2">
                    <button onClick={() => setAllExportFields(true)} className="text-[10px] text-indigo-400 hover:text-indigo-300">All</button>
                    <button onClick={() => setAllExportFields(false)} className="text-[10px] text-gray-500 hover:text-gray-400">None</button>
                  </div>
                </div>
                <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
                  {EMPLOYEE_COLS.map(c => (
                    <label key={c.key} className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer hover:text-white px-1 py-0.5 rounded">
                      <input type="checkbox" checked={!!exportFields[c.key]} onChange={() => toggleExportField(c.key)}
                        className="accent-emerald-500" />
                      {c.label}
                    </label>
                  ))}
                </div>
                <button
                  onClick={handleExport}
                  disabled={exporting || !Object.values(exportFields).some(Boolean)}
                  className="w-full mt-3 flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-3 py-1.5 text-xs font-semibold text-white transition-colors"
                >
                  {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  {exporting ? "Exporting..." : "Download"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Tabel */}
      {(() => {
        const COLS = [
          { label: "NIK",             field: "user_id",          align: "left" },
          { label: "Name",            field: "full_name",         align: "left" },
          { label: "Level",           field: "level",             align: "left" },
          { label: "Department",      field: "department",        align: "left" },
          { label: "Division / Team", field: "division",          align: "left" },
          { label: "Position",        field: "job_title",         align: "left" },
          { label: "Placement",       field: "work_placement",    align: "left" },
          { label: "Status",          field: "status",            align: "left" },
          { label: "Gender",          field: "sex",               align: "center" },
          { label: "Grade",           field: "employee_grade",    align: "center" },
          { label: "Education",       field: "education_degree",  align: "left" },
          { label: "Marital",         field: "marital_status",    align: "left" },
          { label: "Join Date",       field: "date_of_joining",   align: "left" },
          { label: "End PKWT",        field: "end_pkwt",          align: "left" },
          { label: "Phone",           field: "phone_number",      align: "left" },
        ];
        const fmtDate = (v) => v
          ? new Date(v).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })
          : "—";
        return (
          <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 480 }}>
            <table className="w-full text-sm" style={{ minWidth: 1400 }}>
              <thead className="sticky top-0 z-10">
                <tr className="bg-gray-800">
                  {COLS.map(({ label, field, align }) => {
                    const active = sortBy === field;
                    return (
                      <th
                        key={field}
                        onClick={() => handleSort(field)}
                        className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider whitespace-nowrap cursor-pointer select-none group"
                        style={{ color: active ? "#a5b4fc" : "#6b7280", textAlign: align }}
                      >
                        <span className={`inline-flex items-center gap-1 ${align === "center" ? "justify-center" : ""}`}>
                          {label}
                          <span className={`transition-opacity ${active ? "opacity-100" : "opacity-0 group-hover:opacity-50"}`}>
                            {active
                              ? (sortDir === "asc" ? <ChevronUp size={11} className="text-indigo-400" /> : <ChevronDown size={11} className="text-indigo-400" />)
                              : <ArrowUpDown size={10} />}
                          </span>
                        </span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {loading ? (
                  <tr><td colSpan={COLS.length} className="py-12 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></td></tr>
                ) : data.employees.length === 0 ? (
                  <tr><td colSpan={COLS.length} className="py-12 text-center text-xs text-gray-600">
                    {search || deptFilter || statusFilter || genderFilter ? "No employees matching filter" : "No employee data yet. Upload Excel in Employee Upload tab."}
                  </td></tr>
                ) : data.employees.map((e) => (
                  <tr key={e.user_id} onClick={() => setSelectedEmployee(e)} className="hover:bg-gray-800/40 transition-colors cursor-pointer">
                    <td className="px-3 py-2.5 font-mono text-xs text-gray-500 whitespace-nowrap">{e.user_id}</td>
                    <td className="px-3 py-2.5 font-medium text-gray-200 whitespace-nowrap">{e.full_name}</td>
                    <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap text-xs">{e.level || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{e.department || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 text-xs whitespace-nowrap">{[e.division, e.team].filter(Boolean).join(" / ") || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap max-w-[200px] truncate" title={e.job_title}>{e.job_title || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{e.work_placement || "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {e.status
                        ? <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[e.status] || "bg-gray-700 text-gray-400 border-gray-600"}`}>{e.status}</span>
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-center text-xs text-gray-500">
                      {e.sex === "M" ? <span className="text-blue-400 font-semibold">M</span> : e.sex === "F" ? <span className="text-pink-400 font-semibold">F</span> : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-center text-xs text-gray-400 font-mono">{e.employee_grade || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-xs">{e.education_degree || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-xs">{e.marital_status || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-xs">{fmtDate(e.date_of_joining)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-xs">
                      {e.end_pkwt
                        ? <span className={`${new Date(e.end_pkwt) < new Date() ? "text-red-400" : "text-amber-400"}`}>{fmtDate(e.end_pkwt)}</span>
                        : <span className="text-gray-700">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-xs font-mono">{e.phone_number || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })()}

      {/* Pagination */}
      {data.pages > 1 && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 0", fontSize: 12,
        }}>
          <span style={{ color: "#475569", fontWeight: 600 }}>
            {data.total} employees · page {page} of {data.pages}
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === 1 ? "not-allowed" : "pointer",
                background: "#e8edf5", color: page === 1 ? "#cbd5e1" : "#475569",
                boxShadow: "2px 2px 5px #c5cad8, -2px -2px 5px #ffffff",
              }}
            >
              <ChevronLeft size={13} />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === data.pages ? "not-allowed" : "pointer",
                background: "#e8edf5", color: page === data.pages ? "#cbd5e1" : "#475569",
                boxShadow: "2px 2px 5px #c5cad8, -2px -2px 5px #ffffff",
              }}
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {selectedEmployee && (
        <EmployeeDetailModal
          employee={selectedEmployee}
          onClose={() => setSelectedEmployee(null)}
          employeeNames={employeeNames}
          onSupervisorSaved={() => fetchEmployeeNames()}
        />
      )}
    </div>
  );
}

// ── Employee List row click → full-detail popup, split into 4 columns ─────────
const EMPLOYEE_DETAIL_FIELDS = [
  { section: "Identity", fields: [
    ["user_id", "NIK"], ["full_name", "Full Name"], ["sex", "Gender"], ["place_of_birth", "Place of Birth"],
    ["date_of_birth", "Date of Birth"], ["religion", "Religion"], ["blood_type", "Blood Type"], ["marital_status", "Marital Status"],
  ] },
  { section: "Employment", fields: [
    ["level", "Level"], ["department", "Department"], ["division", "Division"], ["team", "Team"],
    ["job_title", "Position"], ["supervisor_id", "Direct Supervisor"], ["work_placement", "Placement"], ["status", "Status"], ["employee_grade", "Grade"],
    ["date_of_joining", "Join Date"], ["pkwt_ke", "PKWT Ke"], ["starting_pkwt", "Starting PKWT"], ["end_pkwt", "End PKWT"],
    ["permanent_date", "Permanent Date"], ["resign_date", "Resign Date"], ["retire_date", "Retire Date"],
  ] },
  { section: "Education & Experience", fields: [
    ["education_degree", "Education Degree"], ["education_school", "School"], ["education_major", "Major"],
    ["working_experience_years", "Work Experience (yrs)"], ["previous_company", "Previous Company"],
  ] },
  { section: "Contact", fields: [
    ["phone_number", "Phone"], ["emergency_phone", "Emergency Phone"], ["company_email", "Company Email"],
    ["personal_email", "Personal Email"], ["address", "Address"],
  ] },
  { section: "Administrative", fields: [
    ["no_bpjs_health", "BPJS Kesehatan"], ["no_bpjs_employee", "BPJS Ketenagakerjaan"], ["npwp_number", "NPWP"],
    ["bank_account_bca", "Bank Account (BCA)"], ["bank_account_name", "Bank Account Name"],
  ] },
];

const EMPLOYEE_DETAIL_DATE_KEYS = new Set([
  "date_of_joining", "date_of_birth", "retire_date", "end_pkwt", "starting_pkwt", "permanent_date", "resign_date",
]);

function fmtEmployeeDetailValue(key, val) {
  if (val === null || val === undefined || val === "") return "—";
  if (EMPLOYEE_DETAIL_DATE_KEYS.has(key)) {
    return new Date(val).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
  }
  if (key === "sex") return val === "M" ? "Male" : val === "F" ? "Female" : val;
  return val;
}

function EmployeeDetailModal({ employee, onClose, employeeNames = [], onSupervisorSaved }) {
  const [supervisorId, setSupervisorId] = useState(employee.supervisor_id || null);
  const [editingSupervisor, setEditingSupervisor] = useState(false);
  const [supervisorQuery, setSupervisorQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const supervisorName = employeeNames.find(n => n.user_id === supervisorId)?.full_name;

  const matches = employeeNames
    .filter(n => n.user_id !== employee.user_id)
    .filter(n => !supervisorQuery.trim() || n.full_name?.toLowerCase().includes(supervisorQuery.trim().toLowerCase()))
    .slice(0, 8);

  const saveSupervisor = async (newId) => {
    setSaving(true);
    setSaveError("");
    try {
      await hrApi.setSupervisor(employee.user_id, newId);
      setSupervisorId(newId);
      setEditingSupervisor(false);
      setSupervisorQuery("");
      onSupervisorSaved?.(employee.user_id, newId);
    } catch (err) {
      setSaveError(err?.response?.data?.detail || "Failed to update supervisor");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,23,42,0.6)" }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl max-h-[85vh] overflow-y-auto rounded-2xl"
        style={{ background: "#e8edf5", boxShadow: "8px 8px 20px #c5cad8, -8px -8px 20px #ffffff" }}
      >
        <div
          className="sticky top-0 z-10 flex items-center justify-between px-6 py-4"
          style={{ background: "linear-gradient(135deg, #2563eb, #3b82f6)", borderRadius: "16px 16px 0 0" }}
        >
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 800, color: "#fff" }}>{employee.full_name || "—"}</h3>
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.85)", fontWeight: 600, marginTop: 2 }}>
              {employee.user_id} · {employee.job_title || "—"}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ padding: 6, borderRadius: 8, border: "none", background: "rgba(255,255,255,0.2)", color: "#fff", cursor: "pointer" }}
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {EMPLOYEE_DETAIL_FIELDS.map(({ section, fields }) => (
            <div key={section}>
              <h4 style={{ fontSize: 11, fontWeight: 800, color: "#2563eb", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
                {section}
              </h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "10px 16px" }}>
                {fields.map(([key, label]) => {
                  const isSupervisor = key === "supervisor_id";
                  return (
                    <div
                      key={key}
                      style={{
                        padding: "8px 12px", borderRadius: 10, background: "#e8edf5",
                        boxShadow: "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff",
                        gridColumn: (key === "address" || (isSupervisor && editingSupervisor)) ? "1 / -1" : undefined,
                      }}
                    >
                      <div style={{ fontSize: 9, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        {label}
                      </div>

                      {!isSupervisor ? (
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b", marginTop: 2, wordBreak: "break-word" }}>
                          {fmtEmployeeDetailValue(key, employee[key])}
                        </div>
                      ) : !editingSupervisor ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                          <span style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b", wordBreak: "break-word" }}>
                            {supervisorId ? (supervisorName || supervisorId) : "— (Top of chart)"}
                          </span>
                          <button
                            onClick={() => setEditingSupervisor(true)}
                            title="Change supervisor"
                            style={{ padding: 3, borderRadius: 6, border: "none", background: "rgba(37,99,235,0.12)", color: "#2563eb", cursor: "pointer", flexShrink: 0 }}
                          >
                            <Pencil size={10} />
                          </button>
                        </div>
                      ) : (
                        <div style={{ marginTop: 4 }}>
                          <input
                            autoFocus
                            value={supervisorQuery}
                            onChange={(e) => setSupervisorQuery(e.target.value)}
                            placeholder="Search employee name..."
                            style={{ width: "100%", fontSize: 12, fontWeight: 600, padding: "6px 8px", borderRadius: 8, border: "none", background: "#fff", color: "#334155", outline: "none" }}
                          />
                          <div style={{ maxHeight: 150, overflowY: "auto", marginTop: 4, borderRadius: 8, background: "#fff" }}>
                            <div
                              onClick={() => saveSupervisor(null)}
                              style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#dc2626", cursor: "pointer" }}
                            >
                              — No supervisor (top of chart)
                            </div>
                            {matches.map((n) => (
                              <div
                                key={n.user_id}
                                onClick={() => saveSupervisor(n.user_id)}
                                style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#1e293b", cursor: "pointer" }}
                              >
                                {n.full_name} <span style={{ color: "#94a3b8", fontWeight: 500 }}>· {n.department || "—"}</span>
                              </div>
                            ))}
                            {matches.length === 0 && (
                              <div style={{ padding: "6px 10px", fontSize: 11, color: "#94a3b8" }}>No matches</div>
                            )}
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                            <button
                              onClick={() => { setEditingSupervisor(false); setSupervisorQuery(""); setSaveError(""); }}
                              style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", background: "none", border: "none", cursor: "pointer" }}
                            >
                              Cancel
                            </button>
                            {saving && <Loader2 size={12} className="animate-spin" style={{ color: "#2563eb" }} />}
                            {saveError && <span style={{ fontSize: 10, color: "#dc2626", fontWeight: 600 }}>{saveError}</span>}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Organization Chart (Employee Data) ─────────────────────────────────────────
const ORG_DEPT_COLORS = {
  "Director":              "#ef4444",
  "Sales & Marketing":     "#3b82f6",
  "Strategy Development":  "#a855f7",
  "Plant":                 "#f59e0b",
  "Administration":        "#10b981",
};
const ORG_DEFAULT_COLOR = "#64748b";
const orgDeptColor = (dept) => ORG_DEPT_COLORS[dept] || ORG_DEFAULT_COLOR;

function orgInitials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase();
}

function orgCollectIds(node, set) {
  if (!node) return;
  set.add(node.user_id);
  node.children?.forEach((c) => orgCollectIds(c, set));
}

function OrgNode({ node, expanded, toggle, matchIds, onOpenDetail }) {
  const hasChildren = !!node.children?.length;
  const isOpen = expanded.has(node.user_id);
  const isMatch = matchIds.has(node.user_id);
  const isPlaceholder = node.user_id === "__unassigned__";
  const color = isPlaceholder ? "#94a3b8" : orgDeptColor(node.department);

  return (
    <li>
      <div
        onClick={() => !isPlaceholder && onOpenDetail(node.user_id)}
        style={{
          width: 172, borderRadius: 12, padding: "10px 12px",
          cursor: isPlaceholder ? "default" : "pointer",
          background: "#e8edf5",
          boxShadow: isMatch
            ? `0 0 0 2px ${color}, 4px 4px 10px #c5cad8, -4px -4px 10px #ffffff`
            : "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
          position: "relative",
        }}
      >
        {isPlaceholder ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 30, height: 30, borderRadius: "50%", flexShrink: 0, background: "#cbd5e1", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>
              <UserCheck size={13} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: "#64748b" }}>Unassigned</div>
              <div style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600 }}>{node.children.length} employee{node.children.length !== 1 ? "s" : ""}</div>
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                background: `linear-gradient(135deg, ${color}, ${color}cc)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#fff", fontSize: 11, fontWeight: 800,
              }}>
                {orgInitials(node.full_name)}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 800, color: "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={node.full_name}>
                  {node.full_name || "—"}
                </div>
                <div style={{ fontSize: 9.5, color: "#64748b", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={node.job_title || ""}>
                  {node.job_title || node.level || "—"}
                </div>
              </div>
            </div>
            <div style={{ marginTop: 6, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
              <span style={{
                fontSize: 8.5, fontWeight: 700, color, background: color + "1a", padding: "1px 6px", borderRadius: 5,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 110,
              }}>
                {node.team || node.division || node.department || "—"}
              </span>
              {hasChildren && <span style={{ fontSize: 8.5, fontWeight: 700, color: "#94a3b8", flexShrink: 0 }}>{node.direct_count}</span>}
            </div>
          </>
        )}

        {hasChildren && (
          <button
            onClick={(e) => { e.stopPropagation(); toggle(node.user_id); }}
            title={isOpen ? "Collapse" : "Expand"}
            style={{
              position: "absolute", bottom: -10, left: "50%", transform: "translateX(-50%)",
              width: 20, height: 20, borderRadius: "50%", border: "2px solid #e8edf5",
              background: color, color: "#fff", cursor: "pointer", display: "flex",
              alignItems: "center", justifyContent: "center", boxShadow: "2px 2px 5px rgba(0,0,0,0.2)",
              zIndex: 2, padding: 0,
            }}
          >
            {isOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        )}
      </div>

      {hasChildren && isOpen && (
        <ul>
          {node.children.map((c) => (
            <OrgNode key={c.user_id} node={c} expanded={expanded} toggle={toggle} matchIds={matchIds} onOpenDetail={onOpenDetail} />
          ))}
        </ul>
      )}
    </li>
  );
}

function OrganizationChartSection() {
  const [root, setRoot]         = useState(null);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState(() => new Set());
  const [search, setSearch]     = useState("");
  const [zoom, setZoom]         = useState(1);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [employeeNames, setEmployeeNames]       = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await hrApi.getOrgChart();
      setRoot(res.data.root || null);
      setTotal(res.data.total || 0);
      if (res.data.root) {
        const ids = new Set();
        const walk = (node, depth) => {
          if (!node) return;
          ids.add(node.user_id);
          if (depth < 2) node.children?.forEach((c) => walk(c, depth + 1));
        };
        walk(res.data.root, 0);
        setExpanded(ids);
      }
    } catch (err) {
      setRoot(null);
      setError(err?.response?.data?.detail || "Failed to load organization chart. Please try refreshing.");
    } finally { setLoading(false); }
  }, []);

  const loadNames = useCallback(() => {
    hrApi.getEmployeeNames().then((r) => setEmployeeNames(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => { load(); loadNames(); }, [load, loadNames]);

  const toggle = (id) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const q = search.trim().toLowerCase();
  const matchIds = useMemo(() => {
    const found = new Set();
    if (!q || !root) return found;
    const walk = (node) => {
      if (!node) return;
      if ((node.full_name || "").toLowerCase().includes(q)) found.add(node.user_id);
      node.children?.forEach(walk);
    };
    walk(root);
    return found;
  }, [q, root]);

  useEffect(() => {
    if (!q || !root || matchIds.size === 0) return;
    const parentOf = {};
    const build = (node, parent) => {
      if (!node) return;
      if (parent) parentOf[node.user_id] = parent.user_id;
      node.children?.forEach((c) => build(c, node));
    };
    build(root, null);
    setExpanded((prev) => {
      const next = new Set(prev);
      matchIds.forEach((id) => {
        let cur = id;
        while (cur) { next.add(cur); cur = parentOf[cur]; }
      });
      return next;
    });
  }, [matchIds]); // eslint-disable-line

  const openDetail = async (userId) => {
    try {
      const res = await hrApi.getEmployee(userId);
      setSelectedEmployee(res.data);
    } catch (_) {}
  };

  const deptsPresent = useMemo(() => {
    const set = new Set();
    const walk = (node) => {
      if (!node || node.user_id === "__unassigned__") return;
      if (node.department) set.add(node.department);
      node.children?.forEach(walk);
    };
    walk(root);
    return [...set];
  }, [root]);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  if (error) {
    return (
      <div style={{ padding: "40px 0", textAlign: "center" }}>
        <p style={{ fontSize: 12, color: "#dc2626", fontWeight: 600 }}>{error}</p>
        <button onClick={load} style={{ marginTop: 10, fontSize: 11.5, fontWeight: 700, color: "#2563eb", background: "none", border: "none", cursor: "pointer" }}>
          Retry
        </button>
      </div>
    );
  }
  if (!root) return <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No employee data yet. Upload Excel in Employee Data → Upload Excel.</p>;

  return (
    <div className="space-y-4">
      <div style={{
        borderRadius: 14, padding: "12px 0", textAlign: "center",
        background: "linear-gradient(135deg, #2563eb, #3b82f6)",
        boxShadow: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: "0.12em", textTransform: "uppercase" }}>
          <Network size={13} style={{ display: "inline", marginRight: 6, verticalAlign: -2 }} />
          Organization Chart
        </h2>
        <p style={{ fontSize: 10.5, color: "rgba(255,255,255,0.85)", fontWeight: 600, marginTop: 2 }}>{total} employees</p>
      </div>

      {/* Toolbar */}
      <div style={{
        display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        padding: "10px 14px", borderRadius: 14,
        background: "#e8edf5", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
      }}>
        <div style={{ position: "relative", minWidth: 220 }}>
          <Search size={12} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search employee name..."
            style={{ width: "100%", fontSize: 12, fontWeight: 600, padding: "7px 10px 7px 28px", borderRadius: 8, border: "none", background: "#fff", color: "#334155", outline: "none" }}
          />
        </div>
        {q && (
          <span style={{ fontSize: 11, fontWeight: 700, color: matchIds.size ? "#2563eb" : "#dc2626" }}>
            {matchIds.size} match{matchIds.size !== 1 ? "es" : ""}
          </span>
        )}
        <div style={{ flex: 1 }} />

        {[
          { icon: ZoomOut,   title: "Zoom out",     onClick: () => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2))) },
          { icon: ZoomIn,    title: "Zoom in",      onClick: () => setZoom((z) => Math.min(1.5, +(z + 0.1).toFixed(2))) },
          { icon: Maximize2, title: "Expand all",   onClick: () => { const ids = new Set(); orgCollectIds(root, ids); setExpanded(ids); } },
          { icon: Minimize2, title: "Collapse all", onClick: () => setExpanded(new Set([root.user_id])) },
          { icon: RefreshCw, title: "Refresh",      onClick: load },
        ].map(({ icon: Icon, title, onClick }) => (
          <button key={title} onClick={onClick} title={title}
            style={{ padding: 8, borderRadius: 8, border: "none", cursor: "pointer", background: "#e8edf5", color: "#64748b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff" }}>
            <Icon size={13} />
          </button>
        ))}
        <span style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", minWidth: 34, textAlign: "center" }}>{Math.round(zoom * 100)}%</span>
      </div>

      {/* Legend */}
      {deptsPresent.length > 0 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 10.5, fontWeight: 600, color: "#64748b" }}>
          {deptsPresent.map((d) => (
            <span key={d} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 9, height: 9, borderRadius: 3, background: orgDeptColor(d), display: "inline-block" }} />
              {d}
            </span>
          ))}
        </div>
      )}

      {/* Tree */}
      <div style={{ overflow: "auto", borderRadius: 14, background: "#dfe5ed", padding: "30px 20px 50px", maxHeight: "70vh" }}>
        <div style={{ transform: `scale(${zoom})`, transformOrigin: "top center", display: "inline-block", minWidth: "100%" }}>
          <ul className="org-tree">
            <OrgNode node={root} expanded={expanded} toggle={toggle} matchIds={matchIds} onOpenDetail={openDetail} />
          </ul>
        </div>
      </div>

      {selectedEmployee && (
        <EmployeeDetailModal
          employee={selectedEmployee}
          onClose={() => setSelectedEmployee(null)}
          employeeNames={employeeNames}
          onSupervisorSaved={() => { loadNames(); load(); }}
        />
      )}
    </div>
  );
}

// ── Shared: fetch monthly-summary (dipakai Employee Summary & Employee Graph) ──
function useMonthlySummary(month, year) {
  const { token } = useAuthStore();
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg]   = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (month) params.set("month", month);
    if (year)  params.set("year", year);
    const qs = params.toString() ? `?${params}` : "";
    setLoading(true);
    fetch(`/api/v1/dashboard/hr/employees/monthly-summary${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body?.detail ?? `HTTP ${r.status}`);
        return body;
      })
      .then((d) => setData(d))
      .catch((e) => setErrMsg(e.message || "Network error"))
      .finally(() => setLoading(false));
  }, [month, year]); // eslint-disable-line

  return { data, loading, errMsg };
}

const SUMMARY_COLORS = ["#6366f1","#34d399","#f59e0b","#f43f5e","#60a5fa","#a78bfa","#fb923c","#4ade80","#38bdf8","#c084fc"];

function SummaryChartCard({ title, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
      <p className="text-xs font-semibold text-gray-200 uppercase tracking-wider mb-3">{title}</p>
      {children}
    </div>
  );
}

function SummaryHBarList({ items, max }) {
  return (
    <div className="space-y-1.5">
      {items.slice(0, 15).map((it, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <div className="w-28 text-gray-300 truncate shrink-0" title={it.name}>{it.name}</div>
          <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
            <div className="h-3 rounded-full" style={{ width: `${Math.round((it.total / max) * 100)}%`, background: SUMMARY_COLORS[i % SUMMARY_COLORS.length] }} />
          </div>
          <div className="w-8 text-right font-bold text-white">{it.total}</div>
        </div>
      ))}
      {items.length === 0 && <p className="text-xs text-gray-400">No data.</p>}
    </div>
  );
}

// ── Employee Summary — data (KPI + breakdown), tanpa chart ─────────────────────
function EmployeeSummarySection() {
  const curYear = new Date().getFullYear();
  const [fMonth, setFMonth] = useState("");
  const [fYear,  setFYear]  = useState("");
  const { data, loading, errMsg } = useMonthlySummary(fMonth, fYear);

  const filterBar = (
    <div className="flex flex-wrap items-end gap-2">
      <div>
        <label className="text-xs text-gray-500 block mb-1">Month</label>
        <select value={fMonth} onChange={e => setFMonth(e.target.value)}
          className="text-xs rounded-lg border border-gray-700 bg-gray-900 text-gray-200 px-2 py-1.5">
          <option value="">All</option>
          {MONTHS_ID.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs text-gray-500 block mb-1">Year</label>
        <select value={fYear} onChange={e => setFYear(e.target.value)}
          className="text-xs rounded-lg border border-gray-700 bg-gray-900 text-gray-200 px-2 py-1.5">
          <option value="">Current</option>
          {[curYear, curYear - 1, curYear - 2, curYear - 3].map(y => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      {(fMonth || fYear) && (
        <button onClick={() => { setFMonth(""); setFYear(""); }}
          className="text-xs font-semibold text-red-400 hover:text-red-300 px-3 py-1.5">
          Reset
        </button>
      )}
    </div>
  );

  if (loading) return <div className="space-y-3 mt-2">{filterBar}<div className="py-16 text-center"><Loader2 size={20} className="mx-auto animate-spin text-gray-300" /></div></div>;
  if (errMsg || !data) return (
    <div className="space-y-3 mt-2">
      {filterBar}
      <div className="py-10 text-center space-y-2">
        <p className="text-xs text-red-400 font-semibold">Failed to load summary data</p>
        {errMsg && <pre className="text-xs text-gray-300 max-w-xl mx-auto whitespace-pre-wrap text-left bg-gray-900 rounded p-3">{errMsg}</pre>}
      </div>
    </div>
  );

  const {
    monthly_joins = [],
    by_dept = [], by_level = [], by_education = [],
    by_marital = [], by_status = [], by_grade = [], by_gender = [],
    period = {},
  } = data;

  const totalEmployees = period.total_employees ?? 0;
  const isFiltered = !!(fMonth || fYear);
  const avgJoin12 = Math.round(monthly_joins.slice(-12).reduce((s, m) => s + m.joins, 0) / 12);

  const joinsLabel = isFiltered ? `New Joins — ${period.label}` : "Avg. Joins/Month";
  const joinsValue = isFiltered ? (period.joins_in_month ?? 0) : avgJoin12;
  const joinsSub   = isFiltered ? (fMonth ? "this month" : "this year") : "last 12 months";

  const deptMax   = Math.max(...by_dept.map(d => d.total), 1);
  const levelMax  = Math.max(...by_level.map(d => d.total), 1);
  const eduMax    = Math.max(...by_education.map(d => d.total), 1);
  const gradeMax  = Math.max(...by_grade.map(d => d.total), 1);
  const statusMax  = Math.max(...by_status.map(d => d.total), 1);
  const maritalMax = Math.max(...by_marital.map(d => d.total), 1);

  return (
    <div className="space-y-4 mt-2">
      {filterBar}

      {isFiltered && (
        <p className="text-xs text-indigo-300">
          Showing active-employee roster as of <strong>{period.label}</strong> (snapshot date {period.snapshot_date}). Attribute values (department, status, etc.) reflect each employee's current record.
        </p>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total Employees",    val: totalEmployees, sub: period.label || "Current", color: "#818cf8" },
          { label: joinsLabel,           val: joinsValue,      sub: joinsSub,  color: "#34d399" },
          { label: "Male",               val: by_gender.find(g => g.name === "Male")?.total ?? 0,  sub: "M", color: "#60a5fa" },
          { label: "Female",             val: by_gender.find(g => g.name === "Female")?.total ?? 0,  sub: "F", color: "#fb7185" },
        ].map(({ label, val, sub, color }) => (
          <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-2xl font-bold" style={{ color }}>{val}</div>
            <div className="text-xs font-semibold text-gray-100 mt-0.5">{label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{sub}</div>
          </div>
        ))}
      </div>

      {/* Breakdown lists row 1 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryChartCard title="By Department">
          <SummaryHBarList items={by_dept} max={deptMax} />
        </SummaryChartCard>
        <SummaryChartCard title="By Job Level">
          <SummaryHBarList items={by_level} max={levelMax} />
        </SummaryChartCard>
        <SummaryChartCard title="By Education">
          <SummaryHBarList items={by_education} max={eduMax} />
        </SummaryChartCard>
      </div>

      {/* Breakdown lists row 2 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryChartCard title="By Grade">
          <SummaryHBarList items={by_grade} max={gradeMax} />
        </SummaryChartCard>
        <SummaryChartCard title="Employee Status">
          <SummaryHBarList items={by_status} max={statusMax} />
        </SummaryChartCard>
        <SummaryChartCard title="Marital Status">
          <SummaryHBarList items={by_marital} max={maritalMax} />
        </SummaryChartCard>
      </div>
    </div>
  );
}

// ── Employee Graph — semua chart (area/bar/pie) ─────────────────────────────────
function EmployeeGraphSection() {
  const { data, loading, errMsg } = useMonthlySummary();
  const [RC, setRC] = useState(null);

  useEffect(() => {
    import("recharts").then((mod) => setRC(mod)).catch(() => {});
  }, []);

  if (loading) return <div className="py-20 text-center"><Loader2 size={20} className="mx-auto animate-spin text-gray-300" /></div>;
  if (errMsg || !data) return (
    <div className="py-10 text-center space-y-2">
      <p className="text-xs text-red-400 font-semibold">Failed to load graph data</p>
      {errMsg && <pre className="text-xs text-gray-300 max-w-xl mx-auto whitespace-pre-wrap text-left bg-gray-900 rounded p-3">{errMsg}</pre>}
    </div>
  );

  const {
    headcount_trend = [], monthly_joins = [],
    by_marital = [], by_status = [], by_gender = [],
  } = data;

  const CHART_H = 200;

  const tickStyle = { fill: "#cbd5e1", fontSize: 10 };
  const tooltipStyle = {
    contentStyle: { borderRadius: 8, fontSize: 11 },
    labelStyle: { color: "#1e293b", fontWeight: 600 },
    itemStyle: { color: "#334155" },
    cursor: { fill: "rgba(0,0,0,0.04)" },
  };
  if (!RC) return <div className="py-6 text-center text-xs text-gray-300">Loading charts…</div>;

  // Recharts' default pie-slice label ignores the `style` prop and renders
  // dark text, which is unreadable on this dark background — render it manually.
  const renderPieLabel = ({ cx, cy, midAngle, outerRadius, percent, name }) => {
    const RADIAN = Math.PI / 180;
    const radius = outerRadius + 14;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);
    return (
      <text x={x} y={y} fill="#f1f5f9" fontSize={10} fontWeight={600} textAnchor={x > cx ? "start" : "end"} dominantBaseline="central">
        {`${name} ${(percent * 100).toFixed(0)}%`}
      </text>
    );
  };

  return (
    <div className="space-y-4 mt-2">
      {/* Charts row 1: headcount trend + monthly joins */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SummaryChartCard title="Headcount Trend (36 Months)">
          <RC.ResponsiveContainer width="100%" height={CHART_H}>
            <RC.AreaChart data={headcount_trend} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="hcGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <RC.XAxis dataKey="label" tick={tickStyle} interval={5} />
              <RC.YAxis tick={tickStyle} />
              <RC.Tooltip {...tooltipStyle} formatter={(v) => [v, "Headcount"]} />
              <RC.Area type="monotone" dataKey="count" stroke="#818cf8" strokeWidth={2} fill="url(#hcGrad)" dot={false} />
            </RC.AreaChart>
          </RC.ResponsiveContainer>
        </SummaryChartCard>

        <SummaryChartCard title="New Hires per Month (24 Months)">
          <RC.ResponsiveContainer width="100%" height={CHART_H}>
            <RC.BarChart data={monthly_joins} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
              <RC.XAxis dataKey="label" tick={tickStyle} interval={3} />
              <RC.YAxis tick={tickStyle} allowDecimals={false} />
              <RC.Tooltip {...tooltipStyle} formatter={(v) => [v, "New Hires"]} />
              <RC.Bar dataKey="joins" fill="#34d399" radius={[3, 3, 0, 0]}>
                {monthly_joins.map((_, i) => <RC.Cell key={i} fill={i === monthly_joins.length - 1 ? "#818cf8" : "#34d399"} />)}
              </RC.Bar>
            </RC.BarChart>
          </RC.ResponsiveContainer>
        </SummaryChartCard>
      </div>

      {/* Charts row 2: status + gender + marital */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryChartCard title="Employee Status">
          <RC.ResponsiveContainer width="100%" height={170}>
            <RC.PieChart>
              <RC.Pie data={by_status} cx="50%" cy="50%" outerRadius={65} dataKey="total" nameKey="name" label={renderPieLabel} labelLine={false}>
                {by_status.map((_, i) => <RC.Cell key={i} fill={SUMMARY_COLORS[i % SUMMARY_COLORS.length]} />)}
              </RC.Pie>
              <RC.Tooltip {...tooltipStyle} />
              <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
            </RC.PieChart>
          </RC.ResponsiveContainer>
        </SummaryChartCard>

        <SummaryChartCard title="Gender">
          <RC.ResponsiveContainer width="100%" height={170}>
            <RC.PieChart>
              <RC.Pie data={by_gender} cx="50%" cy="50%" outerRadius={65} dataKey="total" nameKey="name" label={renderPieLabel} labelLine={false}>
                <RC.Cell fill="#60a5fa" />
                <RC.Cell fill="#fb7185" />
              </RC.Pie>
              <RC.Tooltip {...tooltipStyle} />
              <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
            </RC.PieChart>
          </RC.ResponsiveContainer>
        </SummaryChartCard>

        <SummaryChartCard title="Marital Status">
          <RC.ResponsiveContainer width="100%" height={170}>
            <RC.PieChart>
              <RC.Pie data={by_marital} cx="50%" cy="50%" outerRadius={65} dataKey="total" nameKey="name" label={renderPieLabel} labelLine={false}>
                {by_marital.map((_, i) => <RC.Cell key={i} fill={SUMMARY_COLORS[i % SUMMARY_COLORS.length]} />)}
              </RC.Pie>
              <RC.Tooltip {...tooltipStyle} />
              <RC.Legend wrapperStyle={{ fontSize: 11, color: "#f1f5f9" }} />
            </RC.PieChart>
          </RC.ResponsiveContainer>
        </SummaryChartCard>
      </div>
    </div>
  );
}

// ── Turnover Report ───────────────────────────────────────────────────────────
function TurnoverSection() {
  const { token } = useAuthStore();
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg]   = useState("");
  // Semua hook harus dipanggil unconditionally di setiap render — RC dideklarasikan
  // di sini (sebelum early-return loading/error), bukan setelahnya.
  const [RC, setRC] = useState(null);

  useEffect(() => {
    fetch("/api/v1/dashboard/hr/employees/turnover-summary", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body?.detail ?? `HTTP ${r.status}`);
        return body;
      })
      .then((d) => setData(d))
      .catch((e) => setErrMsg(e.message || "Network error"))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line

  useEffect(() => {
    import("recharts").then((mod) => setRC(mod)).catch(() => {});
  }, []);

  if (loading) return <div className="py-20 text-center"><Loader2 size={20} className="mx-auto animate-spin text-gray-300" /></div>;
  if (errMsg || !data) return (
    <div className="py-10 text-center space-y-2">
      <p className="text-xs text-red-400 font-semibold">Failed to load turnover report</p>
      {errMsg && <pre className="text-xs text-gray-300 max-w-xl mx-auto whitespace-pre-wrap text-left bg-gray-900 rounded p-3">{errMsg}</pre>}
    </div>
  );

  const {
    resign_trend = [], annual_turnover_rate = 0, total_resigns_12m = 0,
    avg_tenure_years = 0, current_headcount = 0,
    by_dept = [], by_level = [], by_status = [],
  } = data;

  const CHART_H = 200;

  const tickStyle = { fill: "#cbd5e1", fontSize: 10 };
  const tooltipStyle = {
    contentStyle: { borderRadius: 8, fontSize: 11 },
    labelStyle: { color: "#1e293b", fontWeight: 600 },
    itemStyle: { color: "#334155" },
    cursor: { fill: "rgba(0,0,0,0.04)" },
  };

  const deptMax   = Math.max(...by_dept.map(d => d.total), 1);
  const levelMax  = Math.max(...by_level.map(d => d.total), 1);
  const statusMax = Math.max(...by_status.map(d => d.total), 1);

  return (
    <div className="space-y-4 mt-2">
      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Turnover Rate (12 Mo)",  val: `${annual_turnover_rate}%`, sub: "annualized",              color: "#fb7185" },
          { label: "Total Resigned (12 Mo)", val: total_resigns_12m,          sub: "employees left",          color: "#fbbf24" },
          { label: "Avg. Tenure",            val: `${avg_tenure_years} yrs`,  sub: "of resigned employees",   color: "#818cf8" },
          { label: "Current Headcount",      val: current_headcount,          sub: "active employees",        color: "#34d399" },
        ].map(({ label, val, sub, color }) => (
          <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-2xl font-bold" style={{ color }}>{val}</div>
            <div className="text-xs font-semibold text-gray-100 mt-0.5">{label}</div>
            <div className="text-xs text-gray-400 mt-0.5">{sub}</div>
          </div>
        ))}
      </div>

      {/* Chart: resign trend + turnover rate */}
      {RC ? (
        <>
          <SummaryChartCard title="Resign & Turnover Rate Trend (24 Months)">
            <RC.ResponsiveContainer width="100%" height={CHART_H}>
              <RC.ComposedChart data={resign_trend} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
                <RC.XAxis dataKey="label" tick={tickStyle} interval={3} />
                <RC.YAxis yAxisId="left" tick={tickStyle} allowDecimals={false} />
                <RC.YAxis yAxisId="right" orientation="right" tick={tickStyle} unit="%" />
                <RC.Tooltip {...tooltipStyle} formatter={(v, name) => name === "turnover_rate" ? [`${v}%`, "Turnover Rate"] : [v, "Resigned"]} />
                <RC.Bar yAxisId="left" dataKey="resigns" fill="#fb7185" radius={[3, 3, 0, 0]} />
                <RC.Line yAxisId="right" type="monotone" dataKey="turnover_rate" stroke="#fbbf24" strokeWidth={2} dot={false} />
              </RC.ComposedChart>
            </RC.ResponsiveContainer>
          </SummaryChartCard>

          {/* Breakdown lists row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryChartCard title="Resigned by Department (12 Mo)">
              <SummaryHBarList items={by_dept} max={deptMax} />
            </SummaryChartCard>
            <SummaryChartCard title="Resigned by Job Level (12 Mo)">
              <SummaryHBarList items={by_level} max={levelMax} />
            </SummaryChartCard>
            <SummaryChartCard title="Resigned by Employee Status (12 Mo)">
              <SummaryHBarList items={by_status} max={statusMax} />
            </SummaryChartCard>
          </div>
        </>
      ) : (
        <div className="py-6 text-center text-xs text-gray-300">Loading charts…</div>
      )}
    </div>
  );
}

// ── Tabel detail Dept + Team ──────────────────────────────────────────────────
function DeptTeamTable({ data }) {
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  if (!data) return null;
  const { departments, grand_total } = data;

  const handleSort = (field) => {
    const r = toggleSort(sortBy, sortDir, field);
    setSortBy(r.sortBy); setSortDir(r.sortDir);
  };
  const NUMERIC = ["employees", "plan", "actual", "rate"];
  const thCls = "px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700";

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-800/70">
            <th className="px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Dept.</th>
            <SortableTH label="Div. / Team" field="team"      sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className={thCls} />
            <SortableTH label="Employees"   field="employees" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
            <SortableTH label="Plan"        field="plan"      sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
            <SortableTH label="Act"         field="actual"    sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
            <SortableTH label="%"           field="rate"      sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
          </tr>
        </thead>
        <tbody>
          {departments.map((dept) => [
            ...sortRows(dept.teams, sortBy, sortDir, NUMERIC).map((team, ti) => (
              <tr key={`${dept.department}-${team.team}`} className="hover:bg-gray-800/20">
                {ti === 0 && (
                  <td
                    rowSpan={dept.teams.length + 1}
                    className="px-3 py-2 font-semibold text-gray-200 border border-gray-700 align-middle text-left whitespace-nowrap"
                  >
                    {dept.department}
                  </td>
                )}
                <td className="px-3 py-2 text-gray-400 border border-gray-700">{team.team}</td>
                <td className="px-3 py-2 text-center text-gray-400 border border-gray-700">{team.employees}</td>
                <td className="px-3 py-2 text-center text-blue-400 border border-gray-700">{team.plan}</td>
                <td className="px-3 py-2 text-center text-orange-400 font-semibold border border-gray-700">{team.actual}</td>
                <td className={`px-3 py-2 text-center font-semibold border border-gray-700 ${team.rate >= 95 ? "text-green-400" : team.rate >= 80 ? "text-amber-400" : "text-red-400"}`}>
                  {team.rate}%
                </td>
              </tr>
            )),
            <tr key={`${dept.department}-total`} className="bg-gray-800/50">
              <td className="px-3 py-2 text-xs font-bold text-gray-300 uppercase tracking-wider border border-gray-600">TOTAL</td>
              <td className="px-3 py-2 text-center font-bold text-gray-200 border border-gray-600">{dept.total.employees}</td>
              <td className="px-3 py-2 text-center font-bold text-blue-300 border border-gray-600">{dept.total.plan}</td>
              <td className="px-3 py-2 text-center font-bold text-orange-300 border border-gray-600">{dept.total.actual}</td>
              <td className={`px-3 py-2 text-center font-bold border border-gray-600 ${dept.total.rate >= 95 ? "text-green-300" : dept.total.rate >= 80 ? "text-amber-300" : "text-red-300"}`}>
                {dept.total.rate}%
              </td>
            </tr>,
          ])}
          <tr className="bg-gray-700/60">
            <td className="px-3 py-2.5 font-bold text-gray-100 uppercase tracking-wider border border-gray-600" colSpan={2}>GRAND TOTAL</td>
            <td className="px-3 py-2.5 text-center font-bold text-gray-100 border border-gray-600">{grand_total.employees}</td>
            <td className="px-3 py-2.5 text-center font-bold text-blue-200 border border-gray-600">{grand_total.plan}</td>
            <td className="px-3 py-2.5 text-center font-bold text-orange-200 border border-gray-600">{grand_total.actual}</td>
            <td className={`px-3 py-2.5 text-center font-bold border border-gray-600 ${grand_total.rate >= 95 ? "text-green-200" : grand_total.rate >= 80 ? "text-amber-200" : "text-red-200"}`}>
              {grand_total.rate}%
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ── Kehadiran Hari Ini ────────────────────────────────────────────────────────
function AttendanceTodaySection() {
  const { token } = useAuthStore();
  const headers   = { Authorization: `Bearer ${token}` };
  const ATT_API   = "/api/v1/dashboard/hr/attendance";

  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [innerTab,    setInnerTab]    = useState("today");
  const [teamData,    setTeamData]    = useState(null);
  const [loadingTeam,  setLoadingTeam]  = useState(false);
  const [activeFilter, setActiveFilter] = useState(null);
  const [employees,    setEmployees]    = useState([]);
  const [loadingEmps,  setLoadingEmps]  = useState(false);
  const [selectedDate, setSelectedDate] = useState(""); // "" = today / latest available
  const [empSortBy,  setEmpSortBy]  = useState(null);
  const [empSortDir, setEmpSortDir] = useState("asc");
  const [deptSortBy,  setDeptSortBy]  = useState(null);
  const [deptSortDir, setDeptSortDir] = useState("asc");
  const handleEmpSort  = (f) => { const r = toggleSort(empSortBy, empSortDir, f);   setEmpSortBy(r.sortBy);  setEmpSortDir(r.sortDir); };
  const handleDeptSort = (f) => { const r = toggleSort(deptSortBy, deptSortDir, f); setDeptSortBy(r.sortBy); setDeptSortDir(r.sortDir); };

  const fetchData = async (targetDate = selectedDate) => {
    setLoading(true);
    try {
      const params = targetDate ? `?target_date=${targetDate}` : "";
      const res = await fetch(`${ATT_API}/today${params}`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  };

  const handleDateChange = (v) => {
    setSelectedDate(v);
    setActiveFilter(null); setEmployees([]);
    fetchData(v);
  };

  const fetchTeamData = async () => {
    if (teamData) return;
    setLoadingTeam(true);
    try {
      const res = await fetch(`${ATT_API}/dept-team-summary`, { headers });
      if (res.ok) setTeamData(await res.json());
    } catch (_) {}
    finally { setLoadingTeam(false); }
  };

  const switchTab = (tab) => {
    setInnerTab(tab);
    if (tab === "team") fetchTeamData();
  };

  const fetchEmployees = async (filter, targetDate) => {
    setLoadingEmps(true);
    try {
      const params = new URLSearchParams({ filter });
      if (targetDate) params.append("target_date", targetDate);
      const res = await fetch(`${ATT_API}/today/employees?${params}`, { headers });
      if (res.ok) { const r = await res.json(); setEmployees(r.employees || []); }
    } catch (_) {}
    finally { setLoadingEmps(false); }
  };

  const handleCardClick = (filter) => {
    if (activeFilter === filter) { setActiveFilter(null); setEmployees([]); return; }
    setActiveFilter(filter);
    fetchEmployees(filter, data?.actual_date);
  };

  useEffect(() => { fetchData(); }, []); // eslint-disable-line

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
    catch (_) { return iso; }
  };

  const noData = !loading && (!data || !data.has_data);

  return (
    <div className="space-y-4">
      {/* Inner tabs */}
      <div className="flex gap-0 border-b border-gray-800">
        {[["today", "Attendance Today"], ["team", "Team Summary"]].map(([id, label]) => (
          <button key={id} onClick={() => switchTab(id)}
            className={`px-4 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${
              innerTab === id ? "border-green-500 text-green-400" : "border-transparent text-gray-500 hover:text-gray-300"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab: Kehadiran Hari Ini ── */}
      {innerTab === "today" && (
        <>
          {/* Date picker — lets you view attendance for any specific date instead of only "today"/latest */}
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <CalendarCheck size={14} className="text-green-400" />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => handleDateChange(e.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-green-500 transition-colors"
              />
              {selectedDate && (
                <button onClick={() => handleDateChange("")} className="text-xs text-gray-500 hover:text-gray-300 underline">
                  Reset to latest
                </button>
              )}
            </div>
            <button onClick={() => fetchData()} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
              <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
          </div>

          {loading && <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>}
          {noData && (
            <p className="py-10 text-center text-xs text-gray-600">
              No attendance data for {selectedDate ? fmtDate(selectedDate) : "this period"}. Upload Excel in Attendance Upload tab, or pick a different date.
            </p>
          )}
          {data && data.has_data && (() => {
            const { summary, actual_date, is_today } = data;
            return (
              <div className="space-y-4">
                {/* Date confirmation badge */}
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-200">Showing: {fmtDate(actual_date)}</span>
                  {!is_today && !selectedDate && (
                    <span className="rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-xs text-amber-400">
                      Latest available data
                    </span>
                  )}
                </div>

                {/* Summary cards — clickable */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { filter: "all",   label: "Total Employees", val: summary.total, color: "text-blue-400",  bg: "bg-blue-500/10",  activeBg: "bg-blue-500/25",  ring: "ring-blue-500/50"  },
                    { filter: "hadir", label: "Present",        val: summary.hadir, color: "text-green-400", bg: "bg-green-500/10", activeBg: "bg-green-500/25", ring: "ring-green-500/50" },
                    { filter: "absen", label: "Absent",         val: summary.absen, color: "text-red-400",   bg: "bg-red-500/10",   activeBg: "bg-red-500/25",   ring: "ring-red-500/50"   },
                  ].map(({ filter, label, val, color, bg, activeBg, ring }) => (
                    <button
                      key={filter}
                      onClick={() => handleCardClick(filter)}
                      className={`rounded-lg border px-4 py-3 text-center transition-all hover:scale-[1.02] active:scale-[0.98] ${
                        activeFilter === filter
                          ? `${activeBg} border-transparent ring-2 ${ring}`
                          : `${bg} border-white/5 hover:border-white/10`
                      }`}
                    >
                      <div className={`text-2xl font-bold ${color}`}>{val}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
                      <div className="text-xs text-gray-600 mt-1">
                        {activeFilter === filter ? "▲ close" : "▼ view details"}
                      </div>
                    </button>
                  ))}
                </div>

                {/* Rate bar */}
                <div className="rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs text-gray-500">Overall Attendance Rate</span>
                    <span className="text-sm font-bold text-green-400">{summary.attendance_rate}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-gray-700 overflow-hidden">
                    <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${summary.attendance_rate}%` }} />
                  </div>
                </div>

                {/* Employee list detail */}
                {activeFilter && (
                  <div className="rounded-xl border border-gray-800 bg-gray-900">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
                      <h4 className="text-xs font-semibold text-gray-300">
                        {activeFilter === "all" ? "All Employees" : activeFilter === "hadir" ? "Present Employees" : "Absent Employees"}
                        <span className="text-gray-600 ml-1.5">({employees.length})</span>
                      </h4>
                      <button onClick={() => { setActiveFilter(null); setEmployees([]); }}
                        className="text-gray-600 hover:text-gray-400 transition-colors">
                        <X size={13} />
                      </button>
                    </div>
                    {loadingEmps ? (
                      <div className="flex justify-center py-8">
                        <Loader2 size={16} className="animate-spin text-gray-600" />
                      </div>
                    ) : (
                      <div className="overflow-x-auto max-h-72">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-gray-800/90">
                            <tr>
                              <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">No</th>
                              <SortableTH label="Name"       field="name"       sortBy={empSortBy} sortDir={empSortDir} onSort={handleEmpSort} />
                              <SortableTH label="Department" field="department" sortBy={empSortBy} sortDir={empSortDir} onSort={handleEmpSort} />
                              <SortableTH label="Check-In"   field="checkin"    sortBy={empSortBy} sortDir={empSortDir} onSort={handleEmpSort} />
                              <SortableTH label="Check-Out"  field="checkout"   sortBy={empSortBy} sortDir={empSortDir} onSort={handleEmpSort} />
                              <SortableTH label="Notes"      field="notes"      sortBy={empSortBy} sortDir={empSortDir} onSort={handleEmpSort} />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-800/50">
                            {employees.length === 0 ? (
                              <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-600">No data</td></tr>
                            ) : sortRows(employees, empSortBy, empSortDir, []).map((emp, i) => (
                              <tr key={`${emp.id}-${i}`} className="hover:bg-gray-800/40 transition-colors">
                                <td className="px-3 py-2 text-gray-600 text-center w-8">{i + 1}</td>
                                <td className="px-3 py-2 font-medium text-gray-200 whitespace-nowrap">{emp.name || "—"}</td>
                                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{emp.department || "—"}</td>
                                <td className={`px-3 py-2 font-mono whitespace-nowrap font-semibold ${emp.checkin ? "text-green-400" : "text-red-400"}`}>
                                  {emp.checkin || "—"}
                                </td>
                                <td className="px-3 py-2 font-mono text-gray-500 whitespace-nowrap">{emp.checkout || "—"}</td>
                                <td className="px-3 py-2 text-gray-600 max-w-[160px] truncate">{emp.notes || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {/* Table per department */}
                <div className="overflow-x-auto rounded-lg border border-gray-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-800/60">
                        <SortableTH label="Department" field="department" sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} className="px-3 py-2.5 text-xs" />
                        <SortableTH label="Total"       field="total"     sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} className="px-3 py-2.5 text-xs" />
                        <SortableTH label="Present"     field="hadir"     sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} className="px-3 py-2.5 text-xs" />
                        <SortableTH label="Absent"      field="absen"     sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} className="px-3 py-2.5 text-xs" />
                        <SortableTH label="Rate"        field="rate"      sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} className="px-3 py-2.5 text-xs" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {data.data.length === 0 ? (
                        <tr><td colSpan={5} className="py-10 text-center text-xs text-gray-600">No working day data</td></tr>
                      ) : sortRows(data.data, deptSortBy, deptSortDir, ["total", "hadir", "absen", "rate"]).map((row) => (
                        <tr key={row.department} className="hover:bg-gray-800/40 transition-colors">
                          <td className="px-3 py-2.5 font-medium text-gray-200">{row.department}</td>
                          <td className="px-3 py-2.5 text-gray-400 text-center">{row.total}</td>
                          <td className="px-3 py-2.5 text-green-400 font-semibold text-center">{row.hadir}</td>
                          <td className="px-3 py-2.5 text-red-400 font-semibold text-center">{row.absen}</td>
                          <td className="px-3 py-2.5 text-center">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                                <div className="h-full rounded-full bg-green-500" style={{ width: `${row.rate}%` }} />
                              </div>
                              <span className="text-xs text-gray-400 w-10 text-right">{row.rate}%</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}
        </>
      )}

      {/* ── Tab: Rekap per Tim ── */}
      {innerTab === "team" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500">Attendance summary per department & team (all available data)</p>
            <button onClick={() => { setTeamData(null); fetchTeamData(); }}
              className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
              <RefreshCw size={11} className={loadingTeam ? "animate-spin" : ""} /> Refresh
            </button>
          </div>
          {loadingTeam && <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>}
          {!loadingTeam && teamData && <DeptTeamTable data={teamData} />}
          {!loadingTeam && !teamData && (
            <p className="py-10 text-center text-xs text-gray-600">No data yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sub-komponen untuk Attendance Ratio ───────────────────────────────────────

const NEU_CARD = {
  background: "#e8edf5",
  borderRadius: 16,
  boxShadow: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  padding: 16,
};
const NEU_IN = { background: "#e8edf5", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" };

function DeptBarChart({ data }) {
  if (!data.length) return <p style={{ padding: "24px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>No data</p>;
  const maxVal = Math.max(...data.map((d) => d.plan), 1);
  const BAR_H  = 130;
  const manyDepts = data.length > 8; // beyond this, fixed-width bars + horizontal scroll stay readable instead of squishing
  return (
    <div style={NEU_CARD}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Attendance Ratio per Department</h4>
        <div style={{ display: "flex", gap: 14, fontSize: 11, color: "#64748b", fontWeight: 600 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 10, height: 10, borderRadius: 3, background: "#3b82f6" }} /> Plan</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 10, height: 10, borderRadius: 3, background: "#f97316" }} /> Actual</span>
        </div>
      </div>
      <div style={{ overflowX: manyDepts ? "auto" : "visible" }}>
        <div style={{
          display: "flex", alignItems: "flex-end",
          justifyContent: manyDepts ? "flex-start" : "space-around",
          gap: manyDepts ? 10 : 4, height: BAR_H + 50,
          minWidth: manyDepts ? data.length * 64 : "auto",
        }}>
          {data.map((dept) => {
            const planH   = Math.max(Math.round((dept.plan / maxVal) * BAR_H), 4);
            const actualH = Math.max(Math.round((dept.actual / maxVal) * BAR_H), dept.actual > 0 ? 4 : 0);
            const short   = dept.department.split(/[\s/&]/)[0];
            return (
              <div key={dept.department} style={{ flex: manyDepts ? "0 0 56px" : 1, display: "flex", flexDirection: "column", alignItems: "center" }} title={dept.department}>
                <div style={{ width: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 2, height: BAR_H }}>
                  <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "#1e293b", fontWeight: 700 }}>{dept.plan}</span>
                    <div style={{ width: "100%", height: planH, background: "linear-gradient(180deg, #60a5fa, #3b82f6)", borderRadius: "6px 6px 0 0", boxShadow: "2px 2px 4px #c5cad8" }} />
                  </div>
                  <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "#ea580c", fontWeight: 700 }}>{dept.actual}</span>
                    <div style={{ width: "100%", height: actualH, background: "linear-gradient(180deg, #fb923c, #f97316)", borderRadius: "6px 6px 0 0", boxShadow: "2px 2px 4px #c5cad8" }} />
                  </div>
                </div>
                <p style={{ fontSize: 10, color: "#475569", fontWeight: 600, marginTop: 4, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "center" }}>{short}</p>
                <p style={{ fontSize: 12, fontWeight: 800, color: "#ea580c" }}>{dept.rate}%</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function WhosOffWidget({ data }) {
  const fmtShort = (iso) => {
    if (!iso) return "";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" }); }
    catch (_) { return iso; }
  };
  return (
    <div style={NEU_CARD}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <h4 style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>Who's Off</h4>
        {data.date && <span style={{ fontSize: 11, color: "#64748b", fontWeight: 600 }}>{fmtShort(data.date)}</span>}
      </div>
      {!data.data?.length ? (
        <p style={{ fontSize: 12, color: "#94a3b8", padding: "8px 0", textAlign: "center" }}>All present</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.data.slice(0, 5).map((emp, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 26, height: 26, borderRadius: "50%",
                background: "linear-gradient(135deg, #3b82f6, #60a5fa)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 700, color: "#fff", flexShrink: 0,
                boxShadow: "2px 2px 4px #c5cad8",
              }}>
                {emp.name?.charAt(0) || "?"}
              </div>
              <div style={{ minWidth: 0 }}>
                <p style={{ fontSize: 12, fontWeight: 600, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{emp.name}</p>
                <p style={{ fontSize: 10, color: "#64748b", fontWeight: 500 }}>{emp.reason}</p>
              </div>
            </div>
          ))}
          {data.data.length > 5 && (
            <p style={{ fontSize: 11, color: "#94a3b8", textAlign: "center", fontWeight: 500 }}>+{data.data.length - 5} more</p>
          )}
        </div>
      )}
    </div>
  );
}

function StatBreakdown({ title, data }) {
  return (
    <div style={NEU_CARD}>
      <h4 style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>{title}</h4>
      {!data?.length ? (
        <p style={{ fontSize: 12, color: "#94a3b8", padding: "8px 0", textAlign: "center" }}>—</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {data.map((item) => (
            <div key={item.label}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                <span style={{ color: "#334155", fontWeight: 600, maxWidth: "65%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.label}</span>
                <span style={{ color: "#2563eb", fontWeight: 800 }}>{item.rate}%</span>
              </div>
              <div style={{ height: 18, borderRadius: 99, ...NEU_IN, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 99,
                  background: "linear-gradient(90deg, #3b82f6, #60a5fa)",
                  width: `${Math.max(item.rate, 2)}%`,
                  boxShadow: "2px 2px 4px #c5cad8",
                  transition: "width 0.5s ease",
                }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MiniBarChart({ data }) {
  if (!data?.length) return null;
  const maxVal = Math.max(...data.map((d) => d.plan), 1);
  const H = 140;
  return (
    <div style={NEU_CARD}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Monthly Attendance</h4>
        <div style={{ display: "flex", gap: 12, fontSize: 11, color: "#64748b", fontWeight: 600 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 10, height: 10, borderRadius: 3, background: "#3b82f6" }} />Plan</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 10, height: 10, borderRadius: 3, background: "#f97316" }} />Actual</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: H }}>
        {data.map((m) => {
          const planH   = Math.max(Math.round((m.plan / maxVal) * (H - 40)), 4);
          const actualH = Math.max(Math.round((m.actual / maxVal) * (H - 40)), m.actual > 0 ? 4 : 0);
          return (
            <div key={m.period} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ width: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 2, height: H - 40 }}>
                <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "#475569", fontWeight: 700 }}>{m.plan}</span>
                  <div style={{ width: "100%", height: planH, background: "linear-gradient(180deg, #60a5fa, #3b82f6)", borderRadius: "5px 5px 0 0", boxShadow: "2px 2px 4px #c5cad8" }} />
                </div>
                <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "#ea580c", fontWeight: 700 }}>{m.actual}</span>
                  <div style={{ width: "100%", height: actualH, background: "linear-gradient(180deg, #fb923c, #f97316)", borderRadius: "5px 5px 0 0", boxShadow: "2px 2px 4px #c5cad8" }} />
                </div>
              </div>
              <p style={{ fontSize: 10, color: "#475569", fontWeight: 600, marginTop: 3 }}>{m.period}</p>
              <p style={{ fontSize: 11, fontWeight: 800, color: "#ea580c" }}>{m.rate}%</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EmployeeDetailPanel({ headers, apiBase }) {
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState([]);
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [absSortBy,  setAbsSortBy]  = useState(null);
  const [absSortDir, setAbsSortDir] = useState("asc");
  const handleAbsSort = (f) => { const r = toggleSort(absSortBy, absSortDir, f); setAbsSortBy(r.sortBy); setAbsSortDir(r.sortDir); };

  const doSearch = async (q) => {
    if (q.length < 2) { setResults([]); return; }
    try {
      const res = await fetch(`${apiBase}/search-employees?q=${encodeURIComponent(q)}`, { headers });
      if (res.ok) setResults(await res.json());
    } catch (_) {}
  };

  const loadDetail = async (emp) => {
    setResults([]); setQuery(emp.name || emp.id); setLoading(true);
    try {
      const res = await fetch(`${apiBase}/employee/${emp.id}/detail`, { headers });
      if (res.ok) setDetail(await res.json());
    } catch (_) {}
    setLoading(false);
  };

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }); }
    catch (_) { return iso; }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
      {/* Left: search + info + absence */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ position: "relative" }}>
          <Search size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); doSearch(e.target.value); }}
            placeholder="Type employee name..."
            style={{
              width: "100%", paddingLeft: 32, paddingRight: 12, padding: "9px 12px 9px 32px",
              borderRadius: 12, border: "none", fontSize: 13, fontWeight: 500,
              color: "#1e293b", background: "#e8edf5",
              boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
              outline: "none", boxSizing: "border-box",
            }}
          />
          {results.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, marginTop: 4,
              borderRadius: 12, background: "#fff", boxShadow: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
              maxHeight: 200, overflowY: "auto",
            }}>
              {results.map((r) => (
                <button key={r.id} onClick={() => loadDetail(r)}
                  style={{
                    width: "100%", textAlign: "left", padding: "8px 12px", border: "none",
                    background: "transparent", cursor: "pointer", borderBottom: "1px solid rgba(0,0,0,0.04)",
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(37,99,235,0.06)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <p style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{r.name}</p>
                  <p style={{ fontSize: 11, color: "#64748b" }}>{r.id} · {r.department}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {loading && <div style={{ display: "flex", justifyContent: "center", padding: "32px 0" }}><Loader2 size={18} className="animate-spin" style={{ color: "#94a3b8" }} /></div>}

        {detail && !loading && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { label: "ID",         val: detail.employee.id },
                { label: "Department", val: detail.employee.department },
                { label: "Team",       val: detail.employee.team },
                { label: "Location",   val: detail.employee.work_placement },
              ].map(({ label, val }) => (
                <div key={label} style={{
                  padding: "8px 12px", borderRadius: 12, background: "#e8edf5",
                  boxShadow: "4px 4px 8px #c5cad8, -4px -4px 8px #ffffff",
                }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{val || "—"}</p>
                </div>
              ))}
            </div>

            <div>
              <h4 style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>Absence Records</h4>
              <div style={{ maxHeight: 200, overflowY: "auto", borderRadius: 12, boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)", position: "sticky", top: 0 }}>
                      {[["Date", "date"], ["Note", "reason"]].map(([h, field]) => (
                        <th key={h} onClick={() => handleAbsSort(field)}
                          style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 700, color: absSortBy === field ? "#2563eb" : "#374151", textTransform: "uppercase", letterSpacing: "0.05em", cursor: "pointer", userSelect: "none" }}>
                          {h} {absSortBy === field && (absSortDir === "asc" ? "▲" : "▼")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {!detail.absences.length ? (
                      <tr><td colSpan={2} style={{ padding: "16px 12px", textAlign: "center", color: "#94a3b8", fontSize: 12 }}>No absence records</td></tr>
                    ) : sortRows(detail.absences, absSortBy, absSortDir, []).map((a, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                        <td style={{ padding: "6px 12px", fontSize: 12, color: "#475569", fontWeight: 500, whiteSpace: "nowrap" }}>{fmtDate(a.date)}</td>
                        <td style={{ padding: "6px 12px", fontSize: 12, color: "#64748b", fontWeight: 500 }}>{a.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {!detail && !loading && (
          <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>Type employee name to view attendance details</p>
        )}
      </div>

      {/* Right: monthly chart */}
      <div>
        {detail?.monthly?.length > 0
          ? <MiniBarChart data={detail.monthly} />
          : (
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "center", height: 200,
              borderRadius: 16, background: "#e8edf5",
              boxShadow: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
            }}>
              <p style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>Monthly chart will appear after selecting an employee</p>
            </div>
          )
        }
      </div>
    </div>
  );
}

// ── Target vs Achievement (Attendance Ratio formula) ──────────────────────────
// Target (Man-Days) = Total Employees x Effective Working Days
// Achievement         = man-days hadir aktual
function TargetAchievementPanel({ apiBase, headers }) {
  const curYear = new Date().getFullYear();
  const [year, setYear]   = useState(curYear);
  const [rows, setRows]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  useEffect(() => {
    setLoading(true);
    fetch(`${apiBase}/target-vs-achievement?year=${year}`, { headers })
      .then((r) => r.ok ? r.json() : { months: [] })
      .then((d) => setRows(d.months || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [year]); // eslint-disable-line

  const years = Array.from({ length: 5 }, (_, i) => curYear - i);

  return (
    <div style={NEU_CARD}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, flexWrap: "wrap", gap: 8 }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Target vs Achievement</h4>
        <select value={year} onChange={(e) => setYear(Number(e.target.value))}
          style={{ fontSize: 11, fontWeight: 700, padding: "5px 12px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#2563eb", boxShadow: NEU_IN.boxShadow, outline: "none", cursor: "pointer" }}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      <p style={{ fontSize: 10.5, color: "#64748b", marginBottom: 12 }}>
        Target (Man-Days) = Total Employees × Effective Working Days &nbsp;·&nbsp; Achievement = actual man-days present
      </p>

      {loading ? (
        <div style={{ padding: "30px 0", textAlign: "center" }}><Loader2 size={16} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
      ) : !rows.length ? (
        <p style={{ padding: "20px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No data available for this year yet.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
            <thead>
              <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                {[["Month", "period"], ["Employees", "headcount"], ["Effective Working Days", "working_days"], ["Target (Man-Days)", "target"], ["Achievement", "achievement"], ["Rate", "rate"]].map(([h, field]) => (
                  <th key={h} onClick={() => handleSort(field)}
                    style={{ padding: "8px 10px", textAlign: h === "Month" ? "left" : "center", fontSize: 10, fontWeight: 700, color: sortBy === field ? "#2563eb" : "#374151", textTransform: "uppercase", letterSpacing: "0.04em", cursor: "pointer", userSelect: "none" }}>
                    {h} {sortBy === field && (sortDir === "asc" ? "▲" : "▼")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortRows(rows, sortBy, sortDir, ["headcount", "working_days", "target", "achievement", "rate"]).map((m, i) => (
                <tr key={m.period} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                  <td style={{ padding: "7px 10px", fontWeight: 700, color: "#1e293b" }}>{m.period}</td>
                  <td style={{ padding: "7px 10px", textAlign: "center", color: "#475569" }}>{m.headcount}</td>
                  <td style={{ padding: "7px 10px", textAlign: "center", color: "#475569" }}>{m.working_days}</td>
                  <td style={{ padding: "7px 10px", textAlign: "center", fontWeight: 700, color: "#2563eb" }}>{m.target.toLocaleString()}</td>
                  <td style={{ padding: "7px 10px", textAlign: "center", fontWeight: 700, color: "#16a34a" }}>{m.achievement.toLocaleString()}</td>
                  <td style={{ padding: "7px 10px", textAlign: "center" }}>
                    <span style={{
                      padding: "2px 10px", borderRadius: 20, fontSize: 11, fontWeight: 800,
                      background: m.rate >= 80 ? "#dcfce7" : m.rate >= 60 ? "#fef3c7" : "#fee2e2",
                      color:      m.rate >= 80 ? "#16a34a" : m.rate >= 60 ? "#d97706" : "#dc2626",
                    }}>
                      {m.rate}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Attendance Ratio Dashboard ─────────────────────────────────────────────────
function AttendanceRateSection() {
  const { token }  = useAuthStore();
  const headers    = { Authorization: `Bearer ${token}` };
  const ATT_API    = "/api/v1/dashboard/hr/attendance";

  const curYear = new Date().getFullYear();
  const curMonth = new Date().getMonth() + 1;

  const [activeTab, setActiveTab] = useState("summary");
  const [deptData,  setDeptData]  = useState([]);
  const [whosOff,   setWhosOff]   = useState({ date: null, data: [] });
  const [workforce, setWorkforce] = useState({ by_gender: [], by_location: [] });
  const [monthly,   setMonthly]   = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [departments, setDepartments] = useState([]);
  const [fDept,  setFDept]  = useState("");
  const [fMonth, setFMonth] = useState("");
  const [fYear,  setFYear]  = useState(curYear);

  useEffect(() => {
    fetch(`${ATT_API}/departments`, { headers }).then(r => r.ok ? r.json() : []).then(setDepartments).catch(() => {});
  }, []); // eslint-disable-line

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (fDept)  p.set("department", fDept);
      if (fMonth) p.set("month", fMonth);
      if (fYear)  p.set("year", fYear);
      const qs = p.toString() ? `?${p}` : "";

      const [d, w, ws, m] = await Promise.all([
        fetch(`${ATT_API}/dept-summary${qs}`,    { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${ATT_API}/whos-off`,             { headers }).then((r) => r.ok ? r.json() : { date: null, data: [] }),
        fetch(`${ATT_API}/workforce-stats`,      { headers }).then((r) => r.ok ? r.json() : { by_gender: [], by_location: [] }),
        fetch(`${ATT_API}/monthly-rate?${new URLSearchParams({ ...(fDept ? {department: fDept} : {}), ...(fYear ? {year: fYear} : {}) })}`, { headers }).then((r) => r.ok ? r.json() : []),
      ]);
      setDeptData(d); setWhosOff(w); setWorkforce(ws); setMonthly(m);
    } catch (_) {}
    finally { setLoading(false); }
  }, [fDept, fMonth, fYear]); // eslint-disable-line

  useEffect(() => { loadSummary(); }, [loadSummary]);

  if (loading && !deptData.length) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  if (!loading && !deptData.length && !monthly.length) return <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No attendance data yet. Upload Excel in the Upload tab.</p>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div style={{
        borderRadius: 14, padding: "12px 0", textAlign: "center",
        background: "linear-gradient(135deg, #2563eb, #3b82f6)",
        boxShadow: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: "0.12em", textTransform: "uppercase" }}>Attendance Ratio</h2>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {[["summary", "Summary"], ["today", "Attendance Today"], ["detail", "Detail"], ["calendar", "Working Calendar"], ["leaveData", "Leave Data"], ["leaveUpload", "Upload Leave"], ["upload", "Upload"]].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{
              padding: "8px 20px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
              background: "#e8edf5", cursor: "pointer",
              color: activeTab === id ? "#2563eb" : "#64748b",
              boxShadow: activeTab === id
                ? "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff"
                : "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff",
              transition: "all 0.2s ease",
            }}>
            {label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={loadSummary} style={{
          padding: 8, borderRadius: 8, border: "none", cursor: "pointer",
          background: "#e8edf5", color: "#64748b",
          boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff",
        }}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Filters */}
      {activeTab === "summary" && (
        <div style={{
          display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap",
          padding: "12px 16px", borderRadius: 14,
          background: "#e8edf5", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
        }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Department</label>
            <select value={fDept} onChange={e => setFDept(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", cursor: "pointer", outline: "none" }}>
              <option value="">All Departments</option>
              {departments.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Month</label>
            <select value={fMonth} onChange={e => setFMonth(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", cursor: "pointer", outline: "none" }}>
              <option value="">All Months</option>
              {MONTHS_ID.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Year</label>
            <select value={fYear} onChange={e => setFYear(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", cursor: "pointer", outline: "none" }}>
              {[curYear, curYear - 1, curYear - 2].map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          {(fDept || fMonth) && (
            <button onClick={() => { setFDept(""); setFMonth(""); setFYear(curYear); }}
              style={{ fontSize: 11, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#dc2626", cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff" }}>
              Reset
            </button>
          )}
          {loading && <Loader2 size={14} className="animate-spin" style={{ color: "#2563eb" }} />}
        </div>
      )}

      {/* ── Summary ── */}
      {activeTab === "summary" && (
        <div className="space-y-4">
        <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 16 }}>
          {/* Left: dept chart + bottom row */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <DeptBarChart data={deptData} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <WhosOffWidget data={whosOff} />
              <StatBreakdown title="Based on Gender"        data={workforce.by_gender}   />
              <StatBreakdown title="Based on Work Location" data={workforce.by_location} />
            </div>
          </div>

          {/* Right: monthly overall */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={NEU_CARD}>
              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 12 }}>Monthly Overall Rate</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[...monthly].reverse().map((m) => {
                  const barColor = m.rate >= 80 ? "linear-gradient(90deg, #22c55e, #4ade80)" : m.rate >= 60 ? "linear-gradient(90deg, #f59e0b, #fbbf24)" : "linear-gradient(90deg, #ef4444, #f87171)";
                  return (
                    <div key={m.period} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: "#475569", fontWeight: 600, width: 52, textAlign: "right", flexShrink: 0 }}>{m.period}</span>
                      <div style={{ flex: 1, height: 22, borderRadius: 99, position: "relative", ...NEU_IN, overflow: "hidden" }}>
                        <div style={{
                          height: "100%", borderRadius: 99, background: barColor,
                          width: `${m.rate}%`, transition: "width 0.5s ease",
                          boxShadow: "2px 2px 4px rgba(0,0,0,0.1)",
                        }} />
                        <span style={{
                          position: "absolute", inset: 0, display: "flex", alignItems: "center",
                          paddingLeft: 10, fontSize: 11, fontWeight: 800, color: "#fff",
                          textShadow: "0 1px 2px rgba(0,0,0,0.3)",
                        }}>{m.rate}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ ...NEU_CARD, padding: 12 }}>
              <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#475569", fontWeight: 600 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 12, height: 12, borderRadius: 3, background: "#22c55e" }} /> ≥ 80%</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 12, height: 12, borderRadius: 3, background: "#f59e0b" }} /> 60–79%</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 12, height: 12, borderRadius: 3, background: "#ef4444" }} /> &lt; 60%</span>
              </div>
            </div>
          </div>
        </div>

        <TargetAchievementPanel apiBase={ATT_API} headers={headers} />
        </div>
      )}

      {/* ── Detail ── */}
      {activeTab === "today" && (
        <AttendanceTodaySection />
      )}

      {activeTab === "detail" && (
        <EmployeeDetailPanel headers={headers} apiBase={ATT_API} />
      )}

      {/* ── Upload ── */}
      {activeTab === "calendar" && (
        <WorkingCalendarPanel />
      )}

      {/* ── Leave (moved from the former standalone Leave tab) ── */}
      {activeTab === "leaveData" && (
        <LeaveDataSection />
      )}

      {activeTab === "leaveUpload" && (
        <LeaveUpload />
      )}

      {activeTab === "upload" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AttendanceUpload kind="intercom" />
          <AttendanceUpload kind="talenta" />
        </div>
      )}
    </div>
  );
}

// ── Budget Monitoring ─────────────────────────────────────────────────────────
// Live query ke Oracle EBS GL_BALANCES (bukan upload):
//   - Budget  → GL_BALANCES actual_flag='B'
//   - Actual  → GL_BALANCES actual_flag='A' — sama dengan Oracle "Funds Available
//               Inquiry", mencakup semua sumber posting (AP Invoice, payroll, dll)
//   - Item AP Invoice per bulan (drill-down) tetap dari AP_INVOICE_DISTRIBUTIONS_ALL
//     sebagai referensi detail — ini subset dari Actual (GL), bisa tidak menjumlah
//     persis jika ada posting non-AP-Invoice.
//
// Kalkulasi:  Remain = Budget − Total Actual (GL)

const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const WDAY_LABELS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const HTYPE_CFG = {
  national:   { label: "National Holiday",  color: "#dc2626", bg: "#fee2e2" },
  collective: { label: "Collective Leave",   color: "#16a34a", bg: "#dcfce7" },
  company:    { label: "Company Holiday",    color: "#2563eb", bg: "#dbeafe" },
};

const WDAY_LABELS_SUN = ["SUN","MON","TUE","WED","THU","FRI","SAT"];
const MONTH_NAMES_SHORT = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"];
// Colors sampled directly from the reference "2026 working calendar.pdf"
const HTYPE_PRINT_COLOR = {
  national: "#cc1f3d", collective: "#79bb57", company: "#008dde",
};
const PRINT_BORDER = "#000";
const PRINT_MONTH_HEADER_BG = "linear-gradient(180deg, #e5e7eb, #9ca3af)";
const PRINT_DOW_HEADER_BG = "#b9e1eb";

function PrintableWorkingCalendar({ year, holidays, summary }) {
  const holidayMap = {};
  holidays.forEach(h => { holidayMap[h.holiday_date] = h; });

  const buildMonthSun = (m) => {
    const daysInMonth = new Date(year, m + 1, 0).getDate();
    const startDay = new Date(year, m, 1).getDay(); // 0=Sun
    const cells = [];
    for (let i = 0; i < startDay; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    return cells;
  };

  const holidaysByMonth = Array.from({ length: 12 }, (_, m) =>
    holidays
      .filter(h => new Date(h.holiday_date + "T00:00:00").getMonth() === m)
      .sort((a, b) => a.holiday_date.localeCompare(b.holiday_date))
  );

  return (
    <div id="working-calendar-print" style={{ fontFamily: "Arial, sans-serif", color: "#000", padding: 10, width: "100%", boxSizing: "border-box" }}>
      <div style={{ textAlign: "center", marginBottom: 10 }}>
        <h1 style={{ fontSize: 16, fontWeight: 800, margin: 0 }}>PT CKD OTTO PHARMACEUTICALS</h1>
        <h2 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>YEAR {year} WORKING CALENDAR</h2>
      </div>

      {/* 3 rows x 4 months, with holiday list to the right of each row */}
      {[0, 1, 2].map(rowIdx => (
        <div key={rowIdx} style={{
          display: "grid", gridTemplateColumns: "repeat(4, 1fr) 145px", gap: 8,
          marginBottom: 8, width: "100%", boxSizing: "border-box", alignItems: "start",
        }}>
          {[0, 1, 2, 3].map(col => {
            const m = rowIdx * 4 + col;
            // Always render 6 week-rows so every month block has equal height
            const cells = buildMonthSun(m);
            while (cells.length < 42) cells.push(null);
            return (
              <div key={m} style={{
                border: `1.5px solid ${PRINT_BORDER}`, boxSizing: "border-box",
                WebkitPrintColorAdjust: "exact", printColorAdjust: "exact",
              }}>
                {/* Month title bar */}
                <div style={{
                  background: PRINT_MONTH_HEADER_BG, textAlign: "center", padding: "4px 0",
                  fontSize: 9.5, fontWeight: 800, letterSpacing: "0.04em",
                  borderBottom: `1.5px solid ${PRINT_BORDER}`, boxSizing: "border-box",
                }}>
                  {MONTH_NAMES_SHORT[m]}
                </div>

                {/* Day-of-week header row */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
                  {WDAY_LABELS_SUN.map((w, i) => (
                    <div key={w} style={{
                      background: PRINT_DOW_HEADER_BG, fontWeight: 800, fontSize: 7,
                      padding: "2px 0 2px 3px", textAlign: "left", boxSizing: "border-box",
                      borderRight: i < 6 ? `1px solid ${PRINT_BORDER}` : "none",
                      borderBottom: `1px solid ${PRINT_BORDER}`,
                    }}>{w}</div>
                  ))}
                </div>

                {/* Date grid */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
                  {cells.map((day, idx) => {
                    const colIdx = idx % 7;
                    const rowIdx2 = Math.floor(idx / 7);
                    const isLastRow = rowIdx2 === 5;
                    const baseBorder = {
                      borderRight: colIdx < 6 ? `1px solid ${PRINT_BORDER}` : "none",
                      borderBottom: isLastRow ? "none" : `1px solid ${PRINT_BORDER}`,
                      boxSizing: "border-box",
                    };
                    if (day === null) {
                      return <div key={idx} style={{ ...baseBorder, background: "#fff", padding: "1px 0" }} />;
                    }
                    const dt = `${year}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                    const dow = new Date(year, m, day).getDay();
                    const isWeekend = dow === 0 || dow === 6;
                    const hol = holidayMap[dt];
                    let bg = "#fff";
                    let color = isWeekend ? "#cc1f3d" : "#000";
                    if (hol) { bg = HTYPE_PRINT_COLOR[hol.holiday_type] || "#cc1f3d"; color = "#000"; }
                    return (
                      <div key={idx} style={{
                        ...baseBorder, padding: "1px 0", textAlign: "center", fontSize: 8.5,
                        background: bg, color, fontWeight: hol ? 800 : (isWeekend ? 700 : 500),
                        WebkitPrintColorAdjust: "exact", printColorAdjust: "exact",
                      }}>
                        {day}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Holiday list for this row's months */}
          <div style={{ fontSize: 6.5, width: "145px", boxSizing: "border-box", overflow: "hidden", paddingLeft: 4 }}>
            {[0, 1, 2, 3].map(col => {
              const m = rowIdx * 4 + col;
              const list = holidaysByMonth[m];
              if (!list.length) return null;
              return (
                <div key={m} style={{ marginBottom: 4 }}>
                  <p style={{ fontWeight: 800, margin: 0, fontSize: 7 }}>{MONTH_NAMES[m]}</p>
                  {list.map(h => (
                    <p key={h.id} style={{ margin: 0, paddingLeft: 4, wordBreak: "break-word" }}>
                      {new Date(h.holiday_date + "T00:00:00").getDate()} : {h.name}
                    </p>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Legend */}
      <table style={{ borderCollapse: "collapse", fontSize: 8, marginTop: 8, width: "55%" }}>
        <tbody>
          <tr>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, background: HTYPE_PRINT_COLOR.national, width: 18 }} />
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 6px", fontWeight: 700 }}>National Holidays</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 10px", textAlign: "right", fontWeight: 800 }}>{summary.totals.national}</td>
          </tr>
          <tr>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, background: HTYPE_PRINT_COLOR.collective }} />
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 6px", fontWeight: 700 }}>Collective Leave</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 10px", textAlign: "right", fontWeight: 800 }}>{summary.totals.collective}</td>
          </tr>
          <tr>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, background: HTYPE_PRINT_COLOR.company }} />
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 6px", fontWeight: 700 }}>Company Holiday</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 10px", textAlign: "right", fontWeight: 800 }}>{summary.totals.company}</td>
          </tr>
          <tr>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, background: "#fff" }} />
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 6px", fontWeight: 700 }}>Working Days <span style={{ color: "#cc1f3d", fontWeight: 500 }}>(red text = weekend)</span></td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "2px 10px", textAlign: "right", fontWeight: 800 }}>{summary.totals.working_days}</td>
          </tr>
        </tbody>
      </table>

      {/* Summary table */}
      <table style={{ borderCollapse: "collapse", fontSize: 8, marginTop: 8 }}>
        <thead>
          <tr>
            {["Year", "Calendar Days", "Week End Days", "Working Days", "National Holidays", "Collective Leave", "Company Holiday", "Total Days"].map(h => (
              <th key={h} style={{ border: `1.5px solid ${PRINT_BORDER}`, padding: "4px 10px", background: PRINT_MONTH_HEADER_BG, fontWeight: 800 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", fontWeight: 700, background: "#fff" }}>{year}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", background: "#fff" }}>{summary.totals.calendar_days}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", background: "#fff" }}>{summary.totals.weekends}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", fontWeight: 700, background: "#fff" }}>{summary.totals.working_days}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", background: "#fff" }}>{summary.totals.national}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", background: "#fff" }}>{summary.totals.collective}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", background: "#fff" }}>{summary.totals.company}</td>
            <td style={{ border: `1px solid ${PRINT_BORDER}`, padding: "3px 10px", textAlign: "center", fontWeight: 700, background: "#fff" }}>
              {summary.totals.weekends + summary.totals.national + summary.totals.collective + summary.totals.company}
            </td>
          </tr>
        </tbody>
      </table>

      {/* Signature block */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 60, marginTop: 30, fontSize: 9 }}>
        <div style={{ textAlign: "center" }}>
          <p style={{ margin: 0 }}>Prepared by,</p>
          <div style={{ height: 40 }} />
          <p style={{ margin: 0, borderTop: `1px solid ${PRINT_BORDER}`, paddingTop: 2, fontWeight: 700 }}>HR</p>
        </div>
        <div style={{ textAlign: "center" }}>
          <p style={{ margin: 0 }}>Approved by,</p>
          <div style={{ height: 40 }} />
          <p style={{ margin: 0, borderTop: `1px solid ${PRINT_BORDER}`, paddingTop: 2, fontWeight: 700 }}>Administration GM</p>
        </div>
      </div>
    </div>
  );
}

function WorkingCalendarPanel() {
  const curYear = new Date().getFullYear();
  const [year, setYear] = useState(curYear);
  const [holidays, setHolidays] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ holiday_date: "", name: "", holiday_type: "national" });
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [h, s] = await Promise.all([
        hrApi.getCalendarHolidays(year),
        hrApi.getCalendarSummary(year),
      ]);
      setHolidays(h); setSummary(s);
    } catch (_) {}
    finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!form.holiday_date || !form.name) return;
    setAdding(true);
    try {
      await hrApi.addCalendarHoliday(form);
      setForm({ holiday_date: "", name: "", holiday_type: "national" });
      load();
    } catch (_) {}
    finally { setAdding(false); }
  };

  const handleDelete = async (id) => {
    try { await hrApi.deleteCalendarHoliday(id); load(); } catch (_) {}
  };

  const holidayMap = {};
  holidays.forEach(h => { holidayMap[h.holiday_date] = h; });

  const buildMonth = (m) => {
    const first = new Date(year, m, 1);
    const daysInMonth = new Date(year, m + 1, 0).getDate();
    let startDay = first.getDay();
    startDay = startDay === 0 ? 6 : startDay - 1;
    const cells = [];
    for (let i = 0; i < startDay; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    return cells;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h3 style={{ fontSize: 16, fontWeight: 800, color: "#1e293b", margin: 0 }}>
            PT CKD OTTO PHARMACEUTICALS
          </h3>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#64748b" }}>Year {year} Working Calendar</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", cursor: "pointer", outline: "none" }}>
            {[curYear - 1, curYear, curYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <button onClick={() => setShowForm(!showForm)}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff" }}>
            + Add Holiday
          </button>
          <button onClick={() => window.print()} disabled={!summary}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#059669", color: "#fff", cursor: summary ? "pointer" : "not-allowed", opacity: summary ? 1 : 0.5, boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff" }}>
            🖨 Print Calendar
          </button>
        </div>
      </div>

      {summary && <PrintableWorkingCalendar year={year} holidays={holidays} summary={summary} />}

      {/* Add form */}
      {showForm && (
        <div style={{
          display: "flex", gap: 8, alignItems: "flex-end", padding: "12px 16px", borderRadius: 14,
          background: "#e8edf5", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
        }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>DATE</label>
            <input type="date" value={form.holiday_date} onChange={e => setForm(p => ({ ...p, holiday_date: e.target.value }))}
              style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", outline: "none" }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>HOLIDAY NAME</label>
            <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Eid al-Fitr"
              style={{ width: "100%", fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box" }} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>TYPE</label>
            <select value={form.holiday_type} onChange={e => setForm(p => ({ ...p, holiday_type: e.target.value }))}
              style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#e8edf5", color: "#1e293b", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", cursor: "pointer", outline: "none" }}>
              {Object.entries(HTYPE_CFG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <button onClick={handleAdd} disabled={adding || !form.holiday_date || !form.name}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 16px", borderRadius: 8, border: "none", background: "#059669", color: "#fff", cursor: "pointer", boxShadow: "3px 3px 6px #c5cad8, -3px -3px 6px #ffffff", opacity: adding ? 0.5 : 1 }}>
            {adding ? "..." : "Save"}
          </button>
        </div>
      )}

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, fontSize: 11, fontWeight: 600 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 14, height: 14, borderRadius: 3, background: "#e2e8f0" }} /> Weekend</span>
        {Object.entries(HTYPE_CFG).map(([k, v]) => (
          <span key={k} style={{ display: "flex", alignItems: "center", gap: 5, color: "#475569" }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: v.bg, border: `2px solid ${v.color}` }} /> {v.label}
          </span>
        ))}
      </div>

      {/* 12-month grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {Array.from({ length: 12 }, (_, m) => {
          const cells = buildMonth(m);
          return (
            <div key={m} style={{ ...NEU_CARD, padding: 10 }}>
              <h4 style={{ fontSize: 12, fontWeight: 800, color: "#1e293b", textAlign: "center", marginBottom: 6, textTransform: "uppercase" }}>
                {MONTH_NAMES[m]}
              </h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 1, textAlign: "center" }}>
                {WDAY_LABELS.map(w => (
                  <div key={w} style={{ fontSize: 9, fontWeight: 700, color: "#94a3b8", padding: "2px 0" }}>{w}</div>
                ))}
                {cells.map((day, i) => {
                  if (day === null) return <div key={`e${i}`} />;
                  const dt = `${year}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                  const dow = new Date(year, m, day).getDay();
                  const isWeekend = dow === 0 || dow === 6;
                  const hol = holidayMap[dt];

                  let bg = "#fff";
                  let color = "#1e293b";
                  let border = "1px solid transparent";
                  let title = "";

                  if (hol) {
                    const cfg = HTYPE_CFG[hol.holiday_type];
                    bg = cfg?.bg || "#fee2e2";
                    color = cfg?.color || "#dc2626";
                    border = `1.5px solid ${cfg?.color || "#dc2626"}`;
                    title = `${hol.name} (${cfg?.label})`;
                  } else if (isWeekend) {
                    bg = "#e2e8f0";
                    color = "#94a3b8";
                  }

                  return (
                    <div key={day} title={title || `${dt}`}
                      style={{
                        fontSize: 10, fontWeight: hol ? 800 : 600, color, background: bg, border,
                        borderRadius: 4, padding: "3px 0", cursor: hol ? "pointer" : "default",
                        position: "relative",
                      }}
                      onClick={() => hol && handleDelete(hol.id)}
                    >
                      {day}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary table */}
      {summary && (
        <div style={{ ...NEU_CARD }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>Summary — {year}</h4>
          <div style={{ borderRadius: 12, overflow: "hidden", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                  {[["Month", "month"], ["Calendar Days", "calendar_days"], ["Weekends", "weekends"], ["National Holidays", "national"], ["Collective Leave", "collective"], ["Company Holiday", "company"], ["Working Days", "working_days"]].map(([h, field]) => (
                    <th key={h} onClick={() => handleSort(field)}
                      style={{ padding: "10px 10px", fontSize: 10, fontWeight: 700, color: sortBy === field ? "#2563eb" : "#374151", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: h === "Month" ? "left" : "center", borderBottom: "2px solid rgba(0,0,0,0.06)", cursor: "pointer", userSelect: "none" }}>
                      {h} {sortBy === field && (sortDir === "asc" ? "▲" : "▼")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortRows(summary.months, sortBy, sortDir, ["month", "calendar_days", "weekends", "national", "collective", "company", "working_days"]).map((m, i) => (
                  <tr key={m.month} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 700, color: "#1e293b" }}>{MONTH_NAMES[m.month - 1]}</td>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "center" }}>{m.calendar_days}</td>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "center" }}>{m.weekends}</td>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 700, color: m.national > 0 ? "#dc2626" : "#94a3b8", textAlign: "center" }}>{m.national}</td>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 700, color: m.collective > 0 ? "#16a34a" : "#94a3b8", textAlign: "center" }}>{m.collective}</td>
                    <td style={{ padding: "8px 10px", fontSize: 12, fontWeight: 700, color: m.company > 0 ? "#2563eb" : "#94a3b8", textAlign: "center" }}>{m.company}</td>
                    <td style={{ padding: "8px 10px", fontSize: 13, fontWeight: 800, color: "#1e293b", textAlign: "center" }}>{m.working_days}</td>
                  </tr>
                ))}
                <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                  <td style={{ padding: "10px 10px", fontSize: 12, fontWeight: 800, color: "#1e293b" }}>TOTAL</td>
                  <td style={{ padding: "10px 10px", fontSize: 13, fontWeight: 800, color: "#1e293b", textAlign: "center" }}>{summary.totals.calendar_days}</td>
                  <td style={{ padding: "10px 10px", fontSize: 13, fontWeight: 800, color: "#475569", textAlign: "center" }}>{summary.totals.weekends}</td>
                  <td style={{ padding: "10px 10px", fontSize: 13, fontWeight: 800, color: "#dc2626", textAlign: "center" }}>{summary.totals.national}</td>
                  <td style={{ padding: "10px 10px", fontSize: 13, fontWeight: 800, color: "#16a34a", textAlign: "center" }}>{summary.totals.collective}</td>
                  <td style={{ padding: "10px 10px", fontSize: 13, fontWeight: 800, color: "#2563eb", textAlign: "center" }}>{summary.totals.company}</td>
                  <td style={{ padding: "10px 10px", fontSize: 14, fontWeight: 800, color: "#1e293b", textAlign: "center" }}>{summary.totals.working_days}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Holiday list */}
      {holidays.length > 0 && (
        <div style={{ ...NEU_CARD }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>Holiday List — {year} ({holidays.length})</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {holidays.map(h => {
              const cfg = HTYPE_CFG[h.holiday_type];
              return (
                <div key={h.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "6px 12px", borderRadius: 8,
                  background: cfg?.bg || "#f1f5f9",
                  border: `1px solid ${cfg?.color || "#cbd5e1"}20`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#475569", minWidth: 80 }}>{h.holiday_date}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>{h.name}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: cfg?.color || "#64748b", padding: "1px 8px", borderRadius: 10, background: "#fff" }}>
                      {cfg?.label || h.holiday_type}
                    </span>
                  </div>
                  <button onClick={() => handleDelete(h.id)}
                    style={{ fontSize: 11, fontWeight: 600, color: "#dc2626", background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}>
                    ✕
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// Modul ini khusus HR — department dikunci ke HR (dept_code 14), tidak lagi
// jadi parameter yang bisa diganti user.
const HR_DEPT_CODE = "14";

function BudgetMonitoringSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();
  const dept = HR_DEPT_CODE;

  const [year,          setYear]          = useState(curYear);
  const [month,         setMonth]         = useState(new Date().getMonth() + 1);
  const [years,         setYears]         = useState([curYear, curYear - 1]);
  const [data,          setData]          = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [expandedCode,  setExpandedCode]  = useState(null);
  const [accountDetail, setAccountDetail] = useState({});
  const [uploadMsg,     setUploadMsg]     = useState(null);

  const loadYears = useCallback(async () => {
    try {
      const res = await fetch(`${BUDGET_API}/years?dept=${encodeURIComponent(dept)}`, { headers: hdrs });
      if (res.ok) {
        const ys = await res.json();
        if (ys.length) { setYears(ys); setYear(ys[0]); }
      }
    } catch (_) {}
  }, []); // eslint-disable-line

  const load = useCallback(async () => {
    setLoading(true);
    setData(null);
    try {
      const params = new URLSearchParams({ dept, year });
      if (month) params.set("month", month);
      const res = await fetch(`${BUDGET_API}?${params}`, { headers: hdrs });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
  }, [year, month]); // eslint-disable-line

  useEffect(() => { loadYears(); }, [loadYears]);
  useEffect(() => { load(); }, [load]); // eslint-disable-line

  const loadDetail = async (code) => {
    const key = `${dept}_${code}_${year}`;
    if (accountDetail[key]) return;
    try {
      const res = await fetch(
        `${BUDGET_API}/account/${encodeURIComponent(code)}?dept=${encodeURIComponent(dept)}&year=${year}`,
        { headers: hdrs }
      );
      if (res.ok) {
        const d = await res.json();
        setAccountDetail(prev => ({ ...prev, [key]: d }));
      } else {
        const body = await res.json().catch(() => null);
        setAccountDetail(prev => ({ ...prev, [key]: { error: body?.detail || `Failed to load (HTTP ${res.status})` } }));
      }
    } catch (e) {
      setAccountDetail(prev => ({ ...prev, [key]: { error: e?.message || "Network error" } }));
    }
  };

  const handleExpand = async (code) => {
    if (expandedCode === code) { setExpandedCode(null); return; }
    setExpandedCode(code);
    await loadDetail(code);
  };

  const fmtRp = (v) => {
    if (v === undefined || v === null) return "Rp 0";
    return (v < 0 ? "-Rp " : "Rp ") + Math.abs(v).toLocaleString("id-ID");
  };

  const summary  = data?.summary;
  // Sembunyikan akun yang budget dan actual-nya sama-sama 0 (tidak ada aktivitas)
  const accounts = (data?.accounts || []).filter(a => a.budget !== 0 || a.actual !== 0);

  return (
    <div className="space-y-4">

      {/* ── Controls ── */}
      <div className="flex flex-wrap items-center gap-2">

        <select
          value={year}
          onChange={e => { setYear(+e.target.value); setAccountDetail({}); }}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          {years.map(y => <option key={y} value={y}>{y}</option>)}
          {!years.includes(curYear) && <option value={curYear}>{curYear}</option>}
        </select>

        <select
          value={month}
          onChange={e => setMonth(+e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500"
        >
          <option value={0}>All Months</option>
          {MONTHS_ID.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
        </select>

        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh from Oracle
        </button>

        <div className="flex-1" />

        <button
          onClick={() => {
            const p = new URLSearchParams({ dept, year });
            if (month) p.set("month", month);
            window.open(`${BUDGET_API}/export?${p}`, "_blank");
          }}
          disabled={!data}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-xs text-white disabled:opacity-40 transition-colors"
        >
          <Download size={12} /> Export Excel
        </button>
      </div>

      {/* ── Error message ── */}
      {uploadMsg && (
        <div className="rounded-lg px-4 py-2 text-xs flex items-center justify-between bg-red-500/10 text-red-400 border border-red-500/20">
          <span>{uploadMsg.text}</span>
          <button onClick={() => setUploadMsg(null)}><X size={12} /></button>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>}

      {/* ── Empty state ── */}
      {!loading && data && accounts.length === 0 && (
        <div className="py-16 text-center space-y-2">
          <Wallet size={32} className="mx-auto text-gray-700" />
          <p className="text-xs text-gray-600">
            No budget data for year {year}.
          </p>
        </div>
      )}

      {/* ── Summary cards ── */}
      {!loading && summary && accounts.length > 0 && (
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          <BudgetSummaryCard label="Total Budget (GL)"    value={fmtRp(summary.total_budget)} color="text-blue-400"  bg="bg-blue-500/10  border-blue-500/20" />
          <BudgetSummaryCard label="Total Actual (GL)" value={fmtRp(summary.total_actual)} color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
          <BudgetSummaryCard
            label="Remaining (Budget − Actual)"
            value={fmtRp(summary.total_remain)}
            color={summary.total_remain >= 0 ? "text-green-400" : "text-red-400"}
            bg={summary.total_remain >= 0 ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"}
          />
        </div>
      )}

      {/* ── Accounts table (ringkasan per akun) ── */}
      {!loading && accounts.length > 0 && (
        <div className="rounded-lg border border-gray-800 overflow-hidden">
          {/* Header */}
          <div className="bg-gray-800/60 grid grid-cols-12 px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            <div className="col-span-5">Account</div>
            <div className="col-span-3 text-right">Budget (GL)</div>
            <div className="col-span-2 text-right">Actual (GL)</div>
            <div className="col-span-2 text-right">Remaining</div>
          </div>

          {accounts.map((acc) => {
            const isExp    = expandedCode === acc.account_code;
            const detail   = accountDetail[`${dept}_${acc.account_code}_${year}`];
            const remainOk = acc.remain >= 0;

            return (
              <div key={acc.account_code} className="border-t border-gray-800">

                {/* Summary row */}
                <button
                  className={`w-full grid grid-cols-12 px-4 py-3 text-xs text-left transition-colors hover:bg-gray-800/40 ${isExp ? "bg-gray-800/30" : ""}`}
                  onClick={() => handleExpand(acc.account_code)}
                >
                  <div className="col-span-5 flex items-center gap-2">
                    <ChevronDown size={12} className={`text-gray-600 shrink-0 transition-transform ${isExp ? "rotate-180" : ""}`} />
                    <div>
                      <div className="font-medium text-gray-200 leading-tight">{acc.account_name}</div>
                      <div className="text-gray-600">{acc.account_code}</div>
                    </div>
                  </div>
                  <div className="col-span-3 text-right text-blue-600 font-semibold">{fmtRp(acc.budget)}</div>
                  <div className="col-span-2 text-right text-violet-600 font-semibold">{fmtRp(acc.actual)}</div>
                  <div className={`col-span-2 text-right font-semibold ${remainOk ? "text-green-400" : "text-red-400"}`}>
                    {fmtRp(acc.remain)}
                  </div>
                </button>

                {/* ── Detail: tabel per bulan sesuai format laporan ── */}
                {isExp && (
                  <div className="border-t border-gray-800/60 bg-gray-950 px-4 py-3">
                    {!detail ? (
                      <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
                    ) : detail.error ? (
                      <div className="flex items-center justify-between py-4 px-2">
                        <p className="text-xs text-red-400">{detail.error}</p>
                        <button
                          onClick={() => { setAccountDetail(prev => { const n = { ...prev }; delete n[`${dept}_${acc.account_code}_${year}`]; return n; }); loadDetail(acc.account_code); }}
                          className="text-xs text-gray-400 hover:text-gray-200 underline"
                        >Retry</button>
                      </div>
                    ) : detail.monthly.length === 0 ? (
                      <p className="text-xs text-gray-600 text-center py-4">No monthly data for this account.</p>
                    ) : (
                      <div className="space-y-4">
                        {detail.monthly.map((m) => (
                          <BudgetMonthTable key={m.month} m={m} fmtRp={fmtRp} accName={acc.account_name} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* Kertas kerja per bulan — Budget/Encumbrance/Reclass dari GL, item expense dari
   Expense Report HRGA. Layout meniru format kertas kerja HRGA:
   [Bulan] Budget | Actual Expense (list + total) | Available | Reclass | Remain | Note */
function BudgetMonthTable({ m, fmtRp, accName }) {
  const remainOk  = m.remain >= 0;
  const spanRows  = m.items.length + 1; // baris item + 1 baris total
  const monthName = m.month_name || MONTHS_ID[m.month - 1];
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };
  const sortedItems = sortRows(m.items, sortBy, sortDir, ["amount"]);
  const thSort = (label, field, extraStyle = {}) => (
    <th onClick={() => handleSort(field)} className="px-3 py-2 font-semibold" style={{ ...extraStyle, cursor: "pointer", userSelect: "none", color: sortBy === field ? "#818cf8" : undefined }}>
      {label} {sortBy === field && (sortDir === "asc" ? "▲" : "▼")}
    </th>
  );

  return (
    <div className="rounded-lg border border-gray-800 overflow-hidden text-xs">
      <div className="bg-gray-800 px-3 py-1.5">
        <span className="font-bold text-gray-200">{monthName}</span>
        <span className="text-gray-600 ml-2">{accName}</span>
      </div>

      <table className="w-full">
        <thead>
          <tr className="bg-gray-800/40 text-gray-500 uppercase tracking-wider text-xs">
            <th className="px-3 py-2 text-right font-semibold" style={{width:"12%"}}>{monthName} Budget</th>
            {thSort("Actual Expense", "description", { textAlign: "left", width: "28%" })}
            {thSort("Amount", "amount", { textAlign: "right", width: "12%" })}
            <th className="px-3 py-2 text-right font-semibold" style={{width:"12%"}}>Available</th>
            <th className="px-3 py-2 text-right font-semibold" style={{width:"12%"}}>Reclass</th>
            <th className="px-3 py-2 text-right font-semibold" style={{width:"12%"}}>Remain</th>
            <th className="px-3 py-2 text-left font-semibold">Note</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {m.items.length === 0 ? (
            <tr>
              <td className="px-3 py-2 text-right text-blue-600 font-semibold align-top">{fmtRp(m.budget)}</td>
              <td colSpan={2} className="px-3 py-3 text-gray-700 italic">No Expense Report data for this period.</td>
              <td className="px-3 py-2 text-right text-gray-300 align-top">{fmtRp(m.available)}</td>
              <td className="px-3 py-2 text-right text-gray-300 align-top">{fmtRp(m.reclass)}</td>
              <td className={`px-3 py-2 text-right font-bold align-top ${remainOk ? "text-green-400" : "text-red-400"}`}>{fmtRp(m.remain)}</td>
              <td className="px-3 py-2 text-gray-500 align-top">{m.note || "—"}</td>
            </tr>
          ) : (
            <>
              {sortedItems.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-800/20 transition-colors">
                  {idx === 0 && (
                    <td className="px-3 py-2 text-right text-blue-600 font-semibold align-top" rowSpan={spanRows}>
                      {fmtRp(m.budget)}
                    </td>
                  )}
                  <td className="px-3 py-2 text-gray-300">{item.description}</td>
                  <td className="px-3 py-2 text-right text-gray-300 tabular-nums">
                    {(item.amount || 0).toLocaleString("id-ID")}
                  </td>
                  {idx === 0 && (
                    <>
                      <td className="px-3 py-2 text-right text-gray-300 align-top" rowSpan={spanRows}>{fmtRp(m.available)}</td>
                      <td className="px-3 py-2 text-right text-gray-300 align-top" rowSpan={spanRows}>{fmtRp(m.reclass)}</td>
                      <td className={`px-3 py-2 text-right font-bold align-top ${remainOk ? "text-green-400" : "text-red-400"}`} rowSpan={spanRows}>
                        {fmtRp(m.remain)}
                      </td>
                      <td className="px-3 py-2 text-gray-500 align-top" rowSpan={spanRows}>{m.note || "—"}</td>
                    </>
                  )}
                </tr>
              ))}

              {/* Baris total actual expense */}
              <tr className="bg-gray-800/40 font-semibold">
                <td colSpan={2} className="px-3 py-2 text-right text-gray-400 uppercase tracking-wider">Total Actual</td>
                <td className="px-3 py-2 text-right text-violet-700 tabular-nums">
                  {m.total_actual.toLocaleString("id-ID")}
                </td>
              </tr>
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

function BudgetSummaryCard({ label, value, color, bg }) {
  return (
    <div className={`rounded-lg border px-4 py-3 space-y-1 ${bg}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-bold truncate ${color}`}>{value}</p>
    </div>
  );
}

// ── Shared helpers ─────────────────────────────────────────────────────────────
function Loader({ size = 16, className = "" }) {
  return <Loader2 size={size} className={className} />;
}

const LEAVE_CODES = [
  { code: "SL",   label: "Sick Leave",         color: "#ef4444" },
  { code: "AL",   label: "Annual Leave",       color: "#3b82f6" },
  { code: "ALAB", label: "Annual Leave",       color: "#60a5fa" },
  { code: "EM",   label: "Employee Marriage",  color: "#f59e0b" },
  { code: "UL",   label: "Unpaid Leave",       color: "#8b5cf6" },
  { code: "ULBB", label: "Unpaid Leave",       color: "#a78bfa" },
  { code: "ML",   label: "Maternity Leave",    color: "#ec4899" },
  { code: "BT",   label: "Business Trip",      color: "#06b6d4" },
];

function EmployeeLeaveDataCard({ employee }) {
  if (!employee) {
    return (
      <div style={{
        ...NEU_CARD, display: "flex", alignItems: "center", justifyContent: "center",
        minHeight: 260,
      }}>
        <p style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500, textAlign: "center", padding: "0 20px" }}>
          Click a row in the table to view employee leave data
        </p>
      </div>
    );
  }

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }); }
    catch (_) { return iso; }
  };

  const rows = [
    ["Name", employee.employee.name || employee.employee.id],
    ["ID", employee.employee.id],
    ["Job Title", employee.employee.job_title || "—"],
    ["Department", employee.employee.department || "—"],
    ["Join Date", fmtDate(employee.employee.date_of_joining)],
    ["Annual Leave Amount", `${employee.annual_leave_amount} days`],
    ["Annual Leave Remaining", `${employee.annual_leave_remaining} days`],
  ];

  return (
    <div style={NEU_CARD}>
      <div style={{
        borderRadius: 12, overflow: "hidden",
        border: "2px solid #3b82f6",
      }}>
        <div style={{
          background: "linear-gradient(135deg, #2563eb, #3b82f6)",
          padding: "10px 14px",
        }}>
          <h4 style={{ fontSize: 13, fontWeight: 800, color: "#fff" }}>Employee Data</h4>
        </div>
        <div style={{ background: "#fff" }}>
          {rows.map(([label, val], i) => (
            <div key={label} style={{
              display: "grid", gridTemplateColumns: "150px 1fr",
              padding: "7px 14px", background: i % 2 === 0 ? "#eff6ff" : "#fff",
              borderBottom: i < rows.length - 1 ? "1px solid #dbeafe" : "none",
            }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>{label}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>: {val}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function LeaveDataSection() {
  const { token } = useAuthStore();
  const [data, setData] = useState({ data: [], total: 0, pages: 1 });
  const [summary, setSummary] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [selectedEmp, setSelectedEmp] = useState(null);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };
  const [filters, setFilters] = useState({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    leave_code: "",
    organization: "",
    search: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = { page, page_size: 25 };
      if (filters.year)         p.year = filters.year;
      if (filters.month)        p.month = filters.month;
      if (filters.leave_code)   p.leave_code = filters.leave_code;
      if (filters.organization) p.organization = filters.organization;
      if (filters.search)       p.search = filters.search;
      const res = await hrApi.getLeaveData(p);
      setData(res);
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, filters]);

  const fetchSummary = useCallback(async () => {
    try {
      const p = {};
      if (filters.year)  p.year = filters.year;
      if (filters.month) p.month = filters.month;
      const res = await hrApi.getLeaveSummary(p);
      setSummary(res);
    } catch (_) {}
  }, [filters.year, filters.month]);

  useEffect(() => {
    hrApi.getLeaveOrgs().then(setOrgs).catch(() => {});
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const handleFilter = (k, v) => { setFilters(p => ({ ...p, [k]: v })); setPage(1); };

  const handleRowClick = async (r) => {
    try {
      const detail = await hrApi.getLeaveEmployeeDetail(r.employee_id, filters.year);
      setSelectedEmp(detail);
    } catch (_) {}
  };

  const codeBadge = (code) => {
    const c = LEAVE_CODES.find(l => l.code === code);
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600,
        background: c ? `${c.color}18` : "#e2e8f0",
        color: c?.color || "#64748b",
        border: `1px solid ${c ? `${c.color}30` : "#cbd5e1"}`,
      }}>
        {code} — {c?.label || code}
      </span>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Top: Employee Data (left) + Leave Distribution (right) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Employee Data — appears when a row is clicked */}
        <EmployeeLeaveDataCard employee={selectedEmp} />

        {/* Leave Distribution chart with total — click a bar to filter the table below */}
        {summary && summary.by_code?.length > 0 ? (
          <div style={NEU_CARD}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Leave Distribution</h4>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#64748b" }}>
                Total: <span style={{ fontSize: 16, fontWeight: 800, color: "#2563eb" }}>{summary.total}</span> days
              </span>
            </div>
            <p style={{ fontSize: 10.5, color: "#94a3b8", fontWeight: 500, marginBottom: 10 }}>
              Click a leave type to filter the table below{filters.leave_code ? " — click again to clear" : ""}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {summary.by_code.map(c => {
                const cfg = LEAVE_CODES.find(l => l.code === c.code);
                const pct = summary.total > 0 ? Math.round((c.count / summary.total) * 100) : 0;
                const isActive = filters.leave_code === c.code;
                return (
                  <div key={c.code}
                    onClick={() => handleFilter("leave_code", isActive ? "" : c.code)}
                    style={{
                      cursor: "pointer", padding: "6px 8px", borderRadius: 10,
                      background: isActive ? `${cfg?.color || "#94a3b8"}14` : "transparent",
                      boxShadow: isActive ? `inset 0 0 0 1.5px ${cfg?.color || "#94a3b8"}` : "none",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                      <span style={{ fontWeight: isActive ? 800 : 600, color: "#334155" }}>
                        <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: cfg?.color || "#94a3b8", marginRight: 6, verticalAlign: "middle" }} />
                        {c.code} — {cfg?.label || c.code}
                      </span>
                      <span style={{ fontWeight: 800, color: cfg?.color || "#64748b" }}>{c.count} <span style={{ fontWeight: 500, color: "#94a3b8" }}>({pct}%)</span></span>
                    </div>
                    <div style={{ height: 14, borderRadius: 99, ...NEU_IN, overflow: "hidden" }}>
                      <div style={{
                        height: "100%", borderRadius: 99,
                        background: `linear-gradient(90deg, ${cfg?.color || "#94a3b8"}, ${cfg?.color || "#94a3b8"}aa)`,
                        width: `${Math.max(pct, 2)}%`, transition: "width 0.5s ease",
                        boxShadow: "1px 1px 3px rgba(0,0,0,0.1)",
                      }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div style={{ ...NEU_CARD, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 260 }}>
            <p style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>No leave data for this period</p>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Year</label>
          <select value={filters.year} onChange={e => handleFilter("year", e.target.value ? Number(e.target.value) : "")}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            {[2024,2025,2026,2027].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Month</label>
          <select value={filters.month} onChange={e => handleFilter("month", e.target.value ? Number(e.target.value) : "")}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {Array.from({length:12},(_,i)=>i+1).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Leave Code</label>
          <select value={filters.leave_code} onChange={e => handleFilter("leave_code", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {LEAVE_CODES.map(c => <option key={c.code} value={c.code}>{c.code} — {c.label}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Organization</label>
          <select value={filters.organization} onChange={e => handleFilter("organization", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {orgs.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Search</label>
          <input value={filters.search} onChange={e => handleFilter("search", e.target.value)}
            placeholder="Name / ID..."
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5 w-36" />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {[["Employee ID","employee_id"],["Name","employee_name"],["Organization","organization"],["Position","job_position"],["Date","leave_date"],["Leave Code","leave_code"],["Leave Type","leave_type"]].map(([h, field]) => (
                <SortableTH key={h} label={h} field={field} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr><td colSpan={7} className="py-10 text-center"><Loader2 size={14} className="animate-spin inline mr-2 text-gray-500" />Loading...</td></tr>
            ) : data.data.length === 0 ? (
              <tr><td colSpan={7} className="py-10 text-center text-xs text-gray-600">
                No leave data. Upload Talenta Excel in the Leave Upload tab.
              </td></tr>
            ) : sortRows(data.data, sortBy, sortDir, []).map((r, i) => (
              <tr key={i} onClick={() => handleRowClick(r)}
                className="hover:bg-gray-800/40 transition-colors" style={{ cursor: "pointer" }}>
                <td className="px-3 py-2 text-xs font-mono text-gray-500">{r.employee_id}</td>
                <td className="px-3 py-2 text-sm font-medium text-gray-200 whitespace-nowrap">{r.employee_name}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{r.organization || "—"}</td>
                <td className="px-3 py-2 text-xs text-gray-400 max-w-[180px] truncate" title={r.job_position}>{r.job_position || "—"}</td>
                <td className="px-3 py-2 text-xs text-gray-300 whitespace-nowrap">{r.leave_date}</td>
                <td className="px-3 py-2">{codeBadge(r.leave_code)}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{r.leave_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.pages > 1 && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 0", fontSize: 12,
        }}>
          <span style={{ color: "#475569", fontWeight: 600 }}>
            {data.total} records · page {page} of {data.pages}
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === 1 ? "not-allowed" : "pointer",
                background: "#e8edf5", color: page === 1 ? "#cbd5e1" : "#475569",
                boxShadow: "2px 2px 5px #c5cad8, -2px -2px 5px #ffffff",
              }}>
              <ChevronLeft size={13} />
            </button>
            <button onClick={() => setPage(p => Math.min(data.pages, p + 1))} disabled={page === data.pages}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === data.pages ? "not-allowed" : "pointer",
                background: "#e8edf5", color: page === data.pages ? "#cbd5e1" : "#475569",
                boxShadow: "2px 2px 5px #c5cad8, -2px -2px 5px #ffffff",
              }}>
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SectionCard({ title, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color }) {
  return (
    <button className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors ${color}`}>
      <Icon size={13} />{label}
    </button>
  );
}

function DataTable({ headers, rows, placeholder }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-800/60">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {rows?.length ? (
            rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-800/40 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className={`px-3 py-3 text-gray-300 ${j === 0 ? "font-medium text-gray-200" : ""}`}>{cell}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length} className="px-3 py-10 text-center text-xs text-gray-600">
                {placeholder || "No data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── E-Magazine Management ─────────────────────────────────────────────────────
function EMagazineSection() {
  const [list,          setList]          = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [uploading,     setUploading]     = useState(false);
  const [deleting,      setDeleting]      = useState(null);
  const [error,         setError]         = useState("");
  const [success,       setSuccess]       = useState("");
  const [title,         setTitle]         = useState("");
  const [dateLbl,       setDateLbl]       = useState("");
  const [file,          setFile]          = useState(null);
  const [uploadQrLinks, setUploadQrLinks] = useState([]);
  const [editQr,        setEditQr]        = useState(null); // {filename, links:[{label,url}]}
  const [savingQr,      setSavingQr]      = useState(null);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const { data } = await hrApi.eMagazineList();
      setList(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load e-magazine list.");
      setList([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file || !title.trim()) { setError("Title and PDF file are required."); return; }
    setError(""); setSuccess(""); setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", title.trim());
      form.append("date_label", dateLbl.trim());
      form.append("qr_links_json", JSON.stringify(uploadQrLinks.filter(q => q.url.trim())));
      await hrApi.eMagazineUpload(form);
      setSuccess(`"${title}" uploaded successfully.`);
      setTitle(""); setDateLbl(""); setFile(null); setUploadQrLinks([]);
      e.target.reset();
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Upload failed.");
    } finally { setUploading(false); }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Delete "${filename}"?`)) return;
    setDeleting(filename); setError(""); setSuccess("");
    try {
      await hrApi.eMagazineDelete(filename);
      setSuccess(`"${filename}" deleted successfully.`);
      if (editQr?.filename === filename) setEditQr(null);
      load();
    } catch {
      setError("Failed to delete file.");
    } finally { setDeleting(null); }
  };

  const openEditQr = (ed) => {
    const links = (ed.qr_links || []).map(q => ({ label: q.label || "", url: q.url || "" }));
    setEditQr({ filename: ed.filename, links });
  };

  const handleSaveQr = async () => {
    if (!editQr) return;
    setSavingQr(editQr.filename);
    try {
      await hrApi.eMagazineUpdateQR(editQr.filename, editQr.links.filter(q => q.url.trim()));
      setSuccess("QR links saved successfully.");
      setEditQr(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to save QR links.");
    } finally { setSavingQr(null); }
  };

  const addQrRow    = (setter)          => setter(prev => [...prev, { label: "", url: "" }]);
  const removeQrRow = (setter, idx)     => setter(prev => prev.filter((_, i) => i !== idx));
  const updateQrRow = (setter, idx, field, val) =>
    setter(prev => prev.map((q, i) => i === idx ? { ...q, [field]: val } : q));

  const fmtDate = (iso) => {
    if (!iso) return "-";
    try { return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  };

  const QrLinksEditor = ({ links, setter }) => (
    <div className="space-y-2">
      {links.map((q, idx) => (
        <div key={idx} className="flex gap-2 items-center">
          <input
            type="text"
            placeholder="Label (e.g. Check Game)"
            value={q.label}
            onChange={e => updateQrRow(setter, idx, "label", e.target.value)}
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:border-teal-500 focus:outline-none"
          />
          <input
            type="url"
            placeholder="URL (https://…)"
            value={q.url}
            onChange={e => updateQrRow(setter, idx, "url", e.target.value)}
            className="flex-[2] rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:border-teal-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => removeQrRow(setter, idx)}
            className="rounded p-1 text-red-400 hover:bg-red-500/10"
          ><Trash2 size={12} /></button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => addQrRow(setter)}
        className="flex items-center gap-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
      >
        <Plus size={12} /> Add QR Link
      </button>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Upload form */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h3 className="text-sm font-semibold text-teal-400 mb-4 flex items-center gap-2">
          <Upload size={14} /> Upload New e-Magazine
        </h3>
        <form onSubmit={handleUpload} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">Edition Title *</label>
              <input
                type="text"
                placeholder="e.g. 2nd Edition"
                value={title}
                onChange={e => setTitle(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-teal-500 focus:outline-none"
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">Period</label>
              <input
                type="text"
                placeholder="e.g. August 2026"
                value={dateLbl}
                onChange={e => setDateLbl(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-teal-500 focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-gray-400 font-medium">PDF File * (max 100 MB)</label>
              <input
                type="file"
                accept="application/pdf"
                onChange={e => setFile(e.target.files[0] || null)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-400 file:mr-3 file:rounded file:border-0 file:bg-teal-600 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-white focus:outline-none"
                required
              />
            </div>
          </div>
          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
            <label className="text-xs text-gray-400 font-medium mb-2 flex items-center gap-1.5">
              <QrCode size={11} /> QR Code Link (optional)
            </label>
            <QrLinksEditor links={uploadQrLinks} setter={setUploadQrLinks} />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={uploading}
              className="flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-50 transition-colors"
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {uploading ? "Uploading…" : "Upload"}
            </button>
            {success && <span className="text-xs text-teal-400">{success}</span>}
            {error   && <span className="text-xs text-red-400">{error}</span>}
          </div>
        </form>
      </div>

      {/* Edition list */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <div className="bg-gray-800/60 px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <BookOpen size={14} className="text-teal-400" /> Edition List ({list.length})
          </span>
          <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-teal-400 transition-colors">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-teal-400" />
          </div>
        ) : list.length === 0 ? (
          <p className="py-10 text-center text-xs text-gray-600">No e-magazines yet. Upload a PDF above.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800/40">
                <SortableTH label="Title"     field="title"       sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="px-4 py-2.5" />
                <SortableTH label="Period"    field="date"        sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="px-4 py-2.5" />
                <SortableTH label="File Name" field="filename"    sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="px-4 py-2.5" />
                <SortableTH label="Uploaded"  field="uploaded_at" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="px-4 py-2.5" />
                <th className="px-4 py-2.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {sortRows(list, sortBy, sortDir, []).map((ed, i) => (
                <>
                  <tr key={i} className="hover:bg-gray-800/40 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-200">{ed.title}</td>
                    <td className="px-4 py-3 text-gray-400">{ed.date || "-"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs font-mono">{ed.filename}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(ed.uploaded_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => editQr?.filename === ed.filename ? setEditQr(null) : openEditQr(ed)}
                          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                            editQr?.filename === ed.filename
                              ? "bg-teal-500/20 text-teal-300"
                              : "text-teal-400 hover:bg-teal-500/10"
                          }`}
                        >
                          <QrCode size={11} />
                          QR{(ed.qr_links?.length || 0) > 0 && (
                            <span className="rounded-full bg-teal-600/40 px-1">{ed.qr_links.length}</span>
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(ed.filename)}
                          disabled={deleting === ed.filename}
                          className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold text-red-400 hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                        >
                          {deleting === ed.filename ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editQr?.filename === ed.filename && (
                    <tr key={`${i}-qr`}>
                      <td colSpan={5} className="px-4 py-3 bg-gray-900/80 border-t border-teal-800/40">
                        <div className="max-w-2xl space-y-3">
                          <p className="text-xs font-semibold text-teal-400 flex items-center gap-1.5">
                            <QrCode size={11} /> Edit QR Link — {ed.title}
                          </p>
                          <QrLinksEditor
                            links={editQr.links}
                            setter={(fn) =>
                              setEditQr(prev =>
                                prev ? { ...prev, links: typeof fn === "function" ? fn(prev.links) : fn } : prev
                              )
                            }
                          />
                          <div className="flex items-center gap-2 pt-1">
                            <button
                              onClick={handleSaveQr}
                              disabled={!!savingQr}
                              className="flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-teal-500 disabled:opacity-50 transition-colors"
                            >
                              {savingQr ? <Loader2 size={11} className="animate-spin" /> : null}
                              Save
                            </button>
                            <button
                              onClick={() => setEditQr(null)}
                              className="rounded-lg px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-gray-200 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
