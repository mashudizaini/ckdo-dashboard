import { useState, useEffect, useCallback, useMemo, useRef, Fragment } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toPng } from "html-to-image";
import {
  UserCheck, RefreshCw,
  Upload, Search, ChevronLeft, ChevronRight, X, Loader2, CalendarCheck,
  Wallet, Download, ChevronDown, ChevronUp, ListChecks, FileSearch, BookOpen, Trash2,
  QrCode, Plus, Minus, ArrowUpDown, Pencil, ZoomIn, ZoomOut, Maximize2, Minimize2, Network,
  SlidersHorizontal, User, Camera, History, FileText, Sparkles, CheckCircle2,
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

const MONTHS_ID = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const STATUS_BADGE = {
  "Permanent": "bg-green-500/15 text-green-400 border-green-500/30",
  "Contract":  "bg-amber-500/15 text-amber-400 border-amber-500/30",
  "Probation": "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

const EMPLOYMENT_STATUS_BADGE = {
  "Active": "bg-green-500/15 text-green-400 border-green-500/30",
  "Resign": "bg-red-500/15 text-red-400 border-red-500/30",
};

// ── Every field on the Employee record, one column each — shared by the
// Employee List tab AND the Summary drill-down modal so both always show
// exactly the same data, in the same order (used to drift out of sync when
// each screen kept its own column list) ──────────────────────────────────
const _fmtEmpDate = (v) => v
  ? new Date(v).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })
  : "—";
const _empBadge = (val, map) => val
  ? <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${map[val] || "bg-gray-700 text-gray-400 border-gray-600"}`}>{val}</span>
  : "—";
const _empTruncated = (val) => (
  <span className="block max-w-[220px] truncate" title={val || ""}>{val || "—"}</span>
);

function getEmployeeFullCols(employeeNames) {
  return [
    { label: "Photo",            field: "__photo",           align: "center", noSort: true,
      render: (e) => <EmployeePhotoThumb userId={e.user_id} hasPhoto={e.has_photo} size={28} /> },
    { label: "NIK",              field: "user_id",          mono: true, bold: true },
    { label: "Name",             field: "full_name",        bold: true },
    { label: "Gender",           field: "sex",               align: "center",
      render: (e) => e.sex === "M" ? <span className="text-blue-400 font-semibold">M</span> : e.sex === "F" ? <span className="text-pink-400 font-semibold">F</span> : "—" },
    { label: "Place of Birth",   field: "place_of_birth" },
    { label: "Date of Birth",    field: "date_of_birth",     render: (e) => _fmtEmpDate(e.date_of_birth) },
    { label: "Religion",         field: "religion" },
    { label: "Blood Type",       field: "blood_type",        align: "center" },
    { label: "Marital",          field: "marital_status" },
    { label: "Level",            field: "level" },
    { label: "Department",       field: "department" },
    { label: "Division",         field: "division" },
    { label: "Team",             field: "team" },
    { label: "Position",         field: "job_title",         render: (e) => _empTruncated(e.job_title) },
    { label: "Supervisor",       field: "supervisor_id",
      render: (e) => e.supervisor_id ? (employeeNames.find(n => n.user_id === e.supervisor_id)?.full_name || e.supervisor_id) : "—" },
    { label: "Placement",        field: "work_placement" },
    { label: "Status",           field: "status",            render: (e) => _empBadge(e.status, STATUS_BADGE) },
    { label: "Employment",       field: "employment_status", render: (e) => _empBadge(e.employment_status, EMPLOYMENT_STATUS_BADGE) },
    { label: "Grade",            field: "employee_grade",    align: "center", mono: true },
    { label: "Join Date",        field: "date_of_joining",   render: (e) => _fmtEmpDate(e.date_of_joining) },
    { label: "PKWT Ke",          field: "pkwt_ke" },
    { label: "Starting PKWT",    field: "starting_pkwt",     render: (e) => _fmtEmpDate(e.starting_pkwt) },
    { label: "End PKWT",         field: "end_pkwt",
      render: (e) => e.end_pkwt
        ? <span className={new Date(e.end_pkwt) < new Date() ? "text-red-400" : "text-amber-400"}>{_fmtEmpDate(e.end_pkwt)}</span>
        : <span className="text-gray-700">—</span> },
    { label: "Permanent Date",   field: "permanent_date",    render: (e) => _fmtEmpDate(e.permanent_date) },
    { label: "Resign Date",      field: "resign_date",       render: (e) => e.employment_status === "Active" ? "—" : _fmtEmpDate(e.resign_date) },
    { label: "Resign Reason",    field: "resign_reason",     render: (e) => _empTruncated(e.resign_reason) },
    { label: "Retire Date",      field: "retire_date",       render: (e) => _fmtEmpDate(e.retire_date) },
    { label: "Education",        field: "education_degree" },
    { label: "School",           field: "education_school" },
    { label: "Major",            field: "education_major" },
    { label: "Work Experience",  field: "working_experience_years", align: "center" },
    { label: "Previous Company", field: "previous_company",  render: (e) => _empTruncated(e.previous_company) },
    { label: "Phone",            field: "phone_number",      mono: true },
    { label: "Emergency Phone",  field: "emergency_phone",   mono: true },
    { label: "Company Email",    field: "company_email" },
    { label: "Personal Email",   field: "personal_email" },
    { label: "Address",          field: "address",           render: (e) => _empTruncated(e.address) },
    { label: "BPJS Health",      field: "no_bpjs_health",    mono: true },
    { label: "BPJS Employee",    field: "no_bpjs_employee",  mono: true },
    { label: "NPWP",             field: "npwp_number",       mono: true },
    { label: "Bank Account (BCA)", field: "bank_account_bca", mono: true },
    { label: "Bank Account Name", field: "bank_account_name" },
  ];
}

// ── Employee List Excel export — field list shown in the download picker.
// Derived from getEmployeeFullCols() (minus the Photo column, which has no
// exportable value) so the export always matches what's on screen. ───────
const EMPLOYEE_COLS = getEmployeeFullCols(null)
  .filter(c => c.field !== "__photo")
  .map(c => ({ key: c.field, label: c.label }));

const NEU_TAB = {
  bg: "#f1f5f9",
  out: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  inset: "inset 0 1px 3px rgba(15,23,42,0.07)",
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

// ── Authenticated employee photo thumbnail (photo endpoint is role-gated, so
// plain <img src> won't carry the bearer token — fetch as a blob instead) ──
function EmployeePhotoThumb({ userId, hasPhoto, size = 32 }) {
  const { token } = useAuthStore();
  const [src, setSrc] = useState(null);

  useEffect(() => {
    if (!hasPhoto || !userId) { setSrc(null); return; }
    let cancelled = false;
    let objUrl = null;
    (async () => {
      try {
        const res = await fetch(`${API}/${userId}/photo`, { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) {
          const blob = await res.blob();
          objUrl = URL.createObjectURL(blob);
          if (!cancelled) setSrc(objUrl);
        }
      } catch (_) {}
    })();
    return () => { cancelled = true; if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [userId, hasPhoto, token]);

  return (
    <div
      style={{
        width: size, height: size, borderRadius: "50%", overflow: "hidden", flexShrink: 0,
        background: "#334155", display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {src
        ? <img src={src} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        : <User size={Math.round(size * 0.55)} className="text-gray-500" />}
    </div>
  );
}

const HR_TABS = ["employees", "attendance", "workingcalendar", "todo", "cv", "emagazine"];

export default function HRDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const [empSub, setEmpSub] = useState("summary");

  // Derive active section from URL — navigation now lives in the sidebar tree menu.
  const activeSection = HR_TABS.find((id) => location.pathname.endsWith(id)) ?? "employees";

  useEffect(() => {
    if (location.pathname === "/dashboard/hr" || location.pathname === "/dashboard/hr/") {
      navigate("/dashboard/hr/employees", { replace: true });
    }
  }, []); // eslint-disable-line

  return (
    <div className="p-6 space-y-4">
      {/* ── Employee Data (list + upload) ── */}
      {activeSection === "employees" && (
        <SectionCard>
          <SubTabs
            tabs={[
              { id: "summary",  label: "Employee Summary" },
              { id: "list",     label: "Employee List" },
              { id: "graph",    label: "Employee Graph" },
              { id: "orgchart", label: "Organization Chart" },
              { id: "turnover", label: "Turnover Report" },
            ]}
            active={empSub} onChange={setEmpSub}
          />
          {empSub === "list"     && <EmployeeTable />}
          {empSub === "summary"  && <EmployeeSummarySection />}
          {empSub === "graph"    && <EmployeeGraphSection />}
          {empSub === "orgchart" && <OrganizationChartSection />}
          {empSub === "turnover" && <TurnoverSection />}
        </SectionCard>
      )}

      {/* ── Attendance Rate (summary/detail + leave + upload) ── */}
      {activeSection === "attendance" && (
        <SectionCard>
          <AttendanceRateSection />
        </SectionCard>
      )}

      {/* ── Working Calendar (moved out of Attendance Rate into its own section) ── */}
      {activeSection === "workingcalendar" && (
        <SectionCard>
          <WorkingCalendarPanel />
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
  const [employmentStatusFilter, setEmploymentStatusFilter] = useState("Active");
  const [joinMonthFilter, setJoinMonthFilter] = useState(() => String(new Date().getMonth() + 1));
  const [joinYearFilter, setJoinYearFilter] = useState(() => String(new Date().getFullYear()));
  const [teamFilter, setTeamFilter] = useState("");
  const [departments, setDepartments]   = useState([]);
  const [teams,       setTeams]         = useState([]);
  const [joinYears,   setJoinYears]     = useState([]);
  const [summary,    setSummary]    = useState(null);
  const [sortBy,     setSortBy]     = useState("date_of_joining");
  const [sortDir,    setSortDir]    = useState("asc");
  const [showExportPicker, setShowExportPicker] = useState(false);
  const [showFiltersPanel, setShowFiltersPanel] = useState(false);
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const [exportFields, setExportFields] = useState(() => Object.fromEntries(EMPLOYEE_COLS.map(c => [c.key, true])));
  const [exporting, setExporting] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [addingEmployee, setAddingEmployee] = useState(false);
  const [resigningEmployee, setResigningEmployee] = useState(null);
  const [employeeNames, setEmployeeNames] = useState([]);

  const PAGE_SIZE = 8;

  const fetchDepts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/departments`, { headers });
      if (res.ok) setDepartments(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  const fetchEmployeeNames = useCallback(async () => {
    try { setEmployeeNames((await hrApi.getEmployeeNames()) || []); } catch (_) {}
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
      const params = new URLSearchParams({
        ...(search       ? { search }                : {}),
        ...(deptFilter   ? { department: deptFilter } : {}),
        ...(statusFilter ? { status: statusFilter }   : {}),
        ...(employmentStatusFilter ? { employment_status: employmentStatusFilter } : {}),
        ...(joinMonthFilter ? { join_month: joinMonthFilter } : {}),
        ...(joinYearFilter  ? { join_year: joinYearFilter }   : {}),
        ...(teamFilter   ? { team: teamFilter }        : {}),
      });
      const res = await fetch(`${API}/summary?${params}`, { headers });
      if (res.ok) setSummary(await res.json());
    } catch (_) {}
  }, [search, deptFilter, statusFilter, employmentStatusFilter, joinMonthFilter, joinYearFilter, teamFilter]); // eslint-disable-line

  const fetchJoinYears = useCallback(async () => {
    try {
      const res = await fetch(`${API}/join-years`, { headers });
      if (res.ok) setJoinYears(await res.json());
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
        ...(employmentStatusFilter ? { employment_status: employmentStatusFilter } : {}),
        ...(joinMonthFilter ? { join_month: joinMonthFilter } : {}),
        ...(joinYearFilter  ? { join_year: joinYearFilter }   : {}),
        ...(teamFilter   ? { team: teamFilter }      : {}),
      });
      const res = await fetch(`${API}?${params}`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, search, deptFilter, statusFilter, employmentStatusFilter, joinMonthFilter, joinYearFilter, teamFilter, sortBy, sortDir]); // eslint-disable-line

  useEffect(() => { fetchDepts(); fetchTeams(""); fetchEmployeeNames(); fetchJoinYears(); }, []); // eslint-disable-line
  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  const [activeCard, setActiveCard] = useState("active");

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
      setActiveCard(""); setStatusFilter(""); setEmploymentStatusFilter(""); setPage(1);
    } else {
      setActiveCard(id);
      setStatusFilter(""); setEmploymentStatusFilter("");
      if (id === "active")         setEmploymentStatusFilter("Active");
      else if (id === "resign")    setEmploymentStatusFilter("Resign");
      else if (id === "permanent") setStatusFilter("Permanent");
      else if (id === "contract")  setStatusFilter("Contract");
      else if (id === "probation") setStatusFilter("Probation");
      setPage(1);
    }
  };

  const toggleExportField = (key) => setExportFields(p => ({ ...p, [key]: !p[key] }));
  const setAllExportFields = (val) => setExportFields(Object.fromEntries(EMPLOYEE_COLS.map(c => [c.key, val])));

  const handleExport = async () => {
    setExporting(true);
    try {
      const cols = EMPLOYEE_COLS.filter(c => exportFields[c.key]);
      const params = new URLSearchParams({
        sort_by: sortBy, sort_dir: sortDir, fields: cols.map(c => c.key).join(","),
        ...(search       ? { search }                : {}),
        ...(deptFilter   ? { department: deptFilter } : {}),
        ...(statusFilter ? { status: statusFilter }   : {}),
        ...(employmentStatusFilter ? { employment_status: employmentStatusFilter } : {}),
        ...(joinMonthFilter ? { join_month: joinMonthFilter } : {}),
        ...(joinYearFilter  ? { join_year: joinYearFilter }   : {}),
        ...(teamFilter   ? { team: teamFilter }        : {}),
      });
      const res = await fetch(`${API}/export?${params}`, { headers });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `employee_data_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
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
            { id: "active",     label: "Active",          val: summary.active,     color: "#16a34a", icon: "🟢" },
            { id: "resign",     label: "Resign",          val: summary.resign,     color: "#dc2626", icon: "🔴" },
            { id: "permanent",  label: "Permanent",       val: summary.permanent,  color: "#22c55e", icon: "✓" },
            { id: "contract",   label: "Contract",        val: summary.contract,   color: "#f59e0b", icon: "📋" },
            { id: "probation",  label: "Probation",       val: summary.probation,  color: "#a855f7", icon: "⏳" },
          ].map(({ id, label, val, color, icon }) => {
            const isActive = activeCard === id;
            return (
              <button key={id} onClick={() => handleCardClick(id)}
                style={{
                  padding: "6px 8px", borderRadius: 10, border: "none",
                  background: isActive ? color : "#f1f5f9",
                  boxShadow: isActive
                    ? "inset 2px 2px 4px rgba(0,0,0,0.2)"
                    : "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
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

      {/* Toolbar — Refresh + search + Filters popup + actions */}
      <div className="flex flex-wrap items-end gap-2">
        <button
          onClick={() => { fetchEmployees(); fetchSummary(); }}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-semibold text-gray-400 hover:border-gray-600 hover:text-gray-200 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>

        <div className="relative w-48">
          <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Search</label>
          <Search size={13} className="absolute left-2.5 top-[30px] text-gray-500" />
          <input
            type="text"
            placeholder="Name / NIK / position..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-8 pr-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 transition-colors"
          />
          {search && (
            <button onClick={() => handleSearch("")} className="absolute right-2 top-[30px] text-gray-600 hover:text-gray-400">
              <X size={13} />
            </button>
          )}
        </div>

        <div className="relative">
          <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">&nbsp;</label>
          <button
            onClick={() => setShowFiltersPanel(v => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-semibold text-gray-300 hover:border-indigo-500 hover:text-white transition-colors"
          >
            <SlidersHorizontal size={13} /> Filters
          </button>
          {showFiltersPanel && (
            <>
              <div onClick={() => setShowFiltersPanel(false)} className="fixed inset-0 z-20" />
              <div className="absolute left-0 top-full mt-2 z-30 w-64 rounded-xl border border-gray-700 bg-gray-900 shadow-2xl p-4">
                <div className="flex flex-col gap-3">
                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Department</label>
                    <select
                      value={deptFilter}
                      onChange={(e) => handleDept(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      {departments.map((d) => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Team</label>
                    <select
                      value={teamFilter}
                      onChange={(e) => handleTeam(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      {teams.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Status</label>
                    <select
                      value={statusFilter}
                      onChange={(e) => handleStatus(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      <option value="Permanent">Permanent</option>
                      <option value="Contract">Contract</option>
                      <option value="Probation">Probation</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Employment State</label>
                    <select
                      value={employmentStatusFilter}
                      onChange={(e) => { setEmploymentStatusFilter(e.target.value); setActiveCard(""); setPage(1); }}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      <option value="Active">Active</option>
                      <option value="Resign">Inactive</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide" title="Shows employees who joined on or before the selected Month/Year">
                      Joined up to (Month)
                    </label>
                    <select
                      value={joinMonthFilter}
                      onChange={(e) => { setJoinMonthFilter(e.target.value); setPage(1); }}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      {MONTHS_ID.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide" title="Shows employees who joined on or before the selected Month/Year">
                      Joined up to (Year)
                    </label>
                    <select
                      value={joinYearFilter}
                      onChange={(e) => { setJoinYearFilter(e.target.value); setPage(1); }}
                      className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">All</option>
                      {joinYears.map((y) => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex-1" />

        <button
          onClick={() => setAddingEmployee(true)}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-2 text-xs font-semibold text-white transition-colors"
        >
          <Plus size={14} /> Add Employee
        </button>

        <button
          onClick={() => setShowUploadPanel(v => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-semibold text-gray-300 hover:border-indigo-500 hover:text-white transition-colors"
        >
          <Upload size={13} /> {showUploadPanel ? "Hide Upload Employee" : "Upload Employee"}
        </button>

        <div className="relative">
          <button
            onClick={() => setShowExportPicker(v => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-700/50 bg-emerald-900/20 px-3 py-2 text-xs font-semibold text-emerald-400 hover:border-emerald-600 hover:bg-emerald-900/30 transition-colors"
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
                <div className="max-h-80 overflow-y-auto space-y-1 pr-1">
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

      {/* Upload Employee — moved here from the old standalone "Upload Excel" tab */}
      {showUploadPanel && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <EmployeeUpload onUploaded={() => { fetchEmployees(); fetchSummary(); fetchDepts(); fetchTeams(deptFilter); fetchJoinYears(); fetchEmployeeNames(); }} />
        </div>
      )}

      {/* Tabel — every field on the Employee record gets its own column */}
      {(() => {
        const COLS = getEmployeeFullCols(employeeNames);

        return (
          <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 480 }}>
            <table className="w-full text-sm" style={{ minWidth: 4200 }}>
              <thead className="sticky top-0 z-10">
                <tr className="bg-gray-800">
                  {COLS.map(({ label, field, noSort }) => {
                    const active = !noSort && sortBy === field;
                    return (
                      <th
                        key={field}
                        onClick={() => !noSort && handleSort(field)}
                        className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wider whitespace-nowrap select-none group ${noSort ? "" : "cursor-pointer"}`}
                        style={{ color: active ? "#a5b4fc" : "#6b7280", textAlign: "center" }}
                      >
                        {noSort ? label : (
                          <span className="inline-flex items-center gap-1 justify-center">
                            {label}
                            <span className={`transition-opacity ${active ? "opacity-100" : "opacity-0 group-hover:opacity-50"}`}>
                              {active
                                ? (sortDir === "asc" ? <ChevronUp size={11} className="text-indigo-400" /> : <ChevronDown size={11} className="text-indigo-400" />)
                                : <ArrowUpDown size={10} />}
                            </span>
                          </span>
                        )}
                      </th>
                    );
                  })}
                  <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider whitespace-nowrap text-center" style={{ color: "#6b7280" }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {loading ? (
                  <tr><td colSpan={COLS.length + 1} className="py-12 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></td></tr>
                ) : data.employees.length === 0 ? (
                  <tr><td colSpan={COLS.length + 1} className="py-12 text-center text-xs text-gray-600">
                    {search || deptFilter || statusFilter || employmentStatusFilter || joinMonthFilter || joinYearFilter || teamFilter ? "No employees matching filter" : "No employee data yet. Upload Excel in Employee Upload tab."}
                  </td></tr>
                ) : data.employees.map((e) => (
                  <tr key={e.user_id} onClick={() => setSelectedEmployee(e)} className="hover:bg-gray-800/40 transition-colors cursor-pointer">
                    {COLS.map(({ field, align, mono, bold, render }) => (
                      <td
                        key={field}
                        className={`px-3 py-2.5 whitespace-nowrap text-xs ${mono ? "font-mono" : ""} ${bold ? "font-medium text-gray-200" : "text-gray-500"}`}
                        style={{ textAlign: align || "left" }}
                      >
                        {render ? render(e) : (e[field] || "—")}
                      </td>
                    ))}
                    <td className="px-3 py-2.5 text-center whitespace-nowrap">
                      {e.employment_status !== "Resign" && (
                        <button
                          onClick={(ev) => { ev.stopPropagation(); setResigningEmployee(e); }}
                          className="rounded-md border border-red-800/50 bg-red-950/40 px-2.5 py-1 text-xs font-semibold text-red-400 hover:bg-red-900/50 hover:border-red-700 transition-colors"
                        >
                          Resign
                        </button>
                      )}
                    </td>
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
                background: "#f1f5f9", color: page === 1 ? "#cbd5e1" : "#475569",
                boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
              }}
            >
              <ChevronLeft size={13} />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === data.pages ? "not-allowed" : "pointer",
                background: "#f1f5f9", color: page === data.pages ? "#cbd5e1" : "#475569",
                boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
              }}
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {(selectedEmployee || addingEmployee) && (
        <EmployeeDetailModal
          employee={addingEmployee ? null : selectedEmployee}
          onClose={() => { setSelectedEmployee(null); setAddingEmployee(false); }}
          employeeNames={employeeNames}
          onSaved={() => {
            setSelectedEmployee(null); setAddingEmployee(false);
            fetchEmployees(); fetchEmployeeNames(); fetchSummary(); fetchDepts(); fetchTeams(deptFilter);
          }}
        />
      )}

      {resigningEmployee && (
        <ResignEmployeeModal
          employee={resigningEmployee}
          onClose={() => setResigningEmployee(null)}
          onSaved={() => {
            setResigningEmployee(null);
            fetchEmployees(); fetchEmployeeNames(); fetchSummary();
          }}
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
    ["job_title", "Position"], ["supervisor_id", "Direct Supervisor"], ["work_placement", "Placement"], ["status", "Status"],
    ["employment_status", "Employment Status"], ["employee_grade", "Grade"],
    ["date_of_joining", "Join Date"], ["pkwt_ke", "PKWT Ke"], ["starting_pkwt", "Starting PKWT"], ["end_pkwt", "End PKWT"],
    ["permanent_date", "Permanent Date"], ["resign_date", "Resign Date"], ["resign_reason", "Resign Reason"], ["retire_date", "Retire Date"],
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

const EMPLOYEE_SELECT_OPTIONS = {
  sex: [["M", "Male"], ["F", "Female"]],
  status: [["Permanent", "Permanent"], ["Contract", "Contract"], ["Probation", "Probation"]],
  employment_status: [["Active", "Active"], ["Resign", "Resign"]],
};

const EMPTY_EMPLOYEE_FORM = Object.fromEntries(
  EMPLOYEE_DETAIL_FIELDS.flatMap(({ fields }) => fields.map(([key]) => [key, ""]))
);

// Editable employee form — used both for editing an existing employee (row
// click in Employee List) and adding a brand new one (Add Employee button).
function EmployeeDetailModal({ employee, onClose, employeeNames = [], onSaved }) {
  const isNew = !employee;
  const [form, setForm] = useState(() => ({
    ...EMPTY_EMPLOYEE_FORM,
    ...(employee || {}),
  }));
  const [editingSupervisor, setEditingSupervisor] = useState(false);
  const [supervisorQuery, setSupervisorQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [hasPhoto, setHasPhoto] = useState(!!employee?.has_photo);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const photoInputRef = useRef(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const handlePhotoSelect = async (file) => {
    if (!file || isNew) return;
    setUploadingPhoto(true);
    try {
      await hrApi.uploadEmployeePhoto(employee.user_id, file);
      setHasPhoto(true);
      setPhotoVersion((v) => v + 1);
    } catch (_) {
    } finally {
      setUploadingPhoto(false);
      if (photoInputRef.current) photoInputRef.current.value = "";
    }
  };

  const handlePhotoRemove = async () => {
    if (isNew) return;
    setUploadingPhoto(true);
    try {
      await hrApi.deleteEmployeePhoto(employee.user_id);
      setHasPhoto(false);
      setPhotoVersion((v) => v + 1);
    } catch (_) {
    } finally {
      setUploadingPhoto(false);
    }
  };

  const loadHistory = async () => {
    if (isNew) return;
    setLoadingHistory(true);
    try { setHistory((await hrApi.getEmployeeHistory(employee.user_id)) || []); }
    catch (_) {}
    finally { setLoadingHistory(false); }
  };

  const toggleHistory = () => {
    setShowHistory((v) => {
      const next = !v;
      if (next) loadHistory();
      return next;
    });
  };

  const supervisorName = employeeNames.find(n => n.user_id === form.supervisor_id)?.full_name;

  const matches = employeeNames
    .filter(n => n.user_id !== form.user_id)
    .filter(n => !supervisorQuery.trim() || n.full_name?.toLowerCase().includes(supervisorQuery.trim().toLowerCase()))
    .slice(0, 8);

  const handleSave = async () => {
    if (!form.full_name?.trim()) { setSaveError("Full name is required"); return; }
    if (isNew && !form.user_id?.trim()) { setSaveError("NIK is required"); return; }

    setSaving(true);
    setSaveError("");
    try {
      if (isNew) await hrApi.createEmployee(form);
      else await hrApi.updateEmployee(employee.user_id, form);
      onSaved?.();
    } catch (err) {
      setSaveError(err?.detail || "Failed to save");
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
        style={{ background: "#f1f5f9", boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)" }}
      >
        <div
          className="sticky top-0 z-10 flex items-center justify-between px-6 py-4"
          style={{ background: "linear-gradient(135deg, #2563eb, #3b82f6)", borderRadius: "16px 16px 0 0" }}
        >
          <div className="flex items-center gap-3">
            {!isNew && (
              <div className="relative" style={{ flexShrink: 0 }}>
                <EmployeePhotoThumb key={photoVersion} userId={employee.user_id} hasPhoto={hasPhoto} size={52} />
                <button
                  onClick={() => photoInputRef.current?.click()}
                  disabled={uploadingPhoto}
                  title="Change photo"
                  style={{
                    position: "absolute", bottom: -2, right: -2, padding: 4, borderRadius: "50%",
                    border: "2px solid #2563eb", background: "#fff", color: "#2563eb", cursor: "pointer", lineHeight: 0,
                  }}
                >
                  {uploadingPhoto ? <Loader2 size={11} className="animate-spin" /> : <Camera size={11} />}
                </button>
                <input ref={photoInputRef} type="file" accept="image/*" className="hidden"
                  onChange={(e) => handlePhotoSelect(e.target.files[0])} />
              </div>
            )}
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 800, color: "#fff" }}>{isNew ? "Add Employee" : (form.full_name || "—")}</h3>
              {!isNew && (
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.85)", fontWeight: 600, marginTop: 2, display: "flex", alignItems: "center", gap: 8 }}>
                  <span>{employee.user_id} · {form.job_title || "—"}</span>
                  {hasPhoto && (
                    <button onClick={handlePhotoRemove} style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.75)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                      Remove photo
                    </button>
                  )}
                </p>
              )}
            </div>
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
                  const isDate = EMPLOYEE_DETAIL_DATE_KEYS.has(key);
                  const selectOptions = EMPLOYEE_SELECT_OPTIONS[key];
                  const isUserId = key === "user_id";
                  const inputStyle = {
                    width: "100%", fontSize: 12.5, fontWeight: 600, padding: "5px 6px", marginTop: 2,
                    borderRadius: 6, border: "none", background: "#fff", color: "#1e293b", outline: "none",
                  };
                  return (
                    <div
                      key={key}
                      style={{
                        padding: "8px 12px", borderRadius: 10, background: "#f1f5f9",
                        boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
                        gridColumn: (key === "address" || (isSupervisor && editingSupervisor)) ? "1 / -1" : undefined,
                      }}
                    >
                      <div style={{ fontSize: 9, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        {label}{isUserId && isNew && " *"}
                      </div>

                      {isSupervisor ? (
                        !editingSupervisor ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                            <span style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b", wordBreak: "break-word" }}>
                              {form.supervisor_id ? (supervisorName || form.supervisor_id) : "— (Top of chart)"}
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
                                onClick={() => { setField("supervisor_id", null); setEditingSupervisor(false); setSupervisorQuery(""); }}
                                style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#dc2626", cursor: "pointer" }}
                              >
                                — No supervisor (top of chart)
                              </div>
                              {matches.map((n) => (
                                <div
                                  key={n.user_id}
                                  onClick={() => { setField("supervisor_id", n.user_id); setEditingSupervisor(false); setSupervisorQuery(""); }}
                                  style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#1e293b", cursor: "pointer" }}
                                >
                                  {n.full_name} <span style={{ color: "#94a3b8", fontWeight: 500 }}>· {n.department || "—"}</span>
                                </div>
                              ))}
                              {matches.length === 0 && (
                                <div style={{ padding: "6px 10px", fontSize: 11, color: "#94a3b8" }}>No matches</div>
                              )}
                            </div>
                            <button
                              onClick={() => { setEditingSupervisor(false); setSupervisorQuery(""); }}
                              style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", background: "none", border: "none", cursor: "pointer", marginTop: 4 }}
                            >
                              Cancel
                            </button>
                          </div>
                        )
                      ) : selectOptions ? (
                        <select
                          value={form[key] || ""}
                          onChange={(e) => setField(key, e.target.value)}
                          style={{ ...inputStyle, cursor: "pointer" }}
                        >
                          <option value="">—</option>
                          {selectOptions.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      ) : isDate ? (
                        <input
                          type="date"
                          value={form[key] || ""}
                          onChange={(e) => setField(key, e.target.value)}
                          style={inputStyle}
                        />
                      ) : (
                        <input
                          type="text"
                          value={form[key] || ""}
                          disabled={isUserId && !isNew}
                          onChange={(e) => setField(key, e.target.value)}
                          style={{ ...inputStyle, ...(isUserId && !isNew ? { opacity: 0.6, cursor: "not-allowed" } : {}) }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {!isNew && (
            <div style={{ borderRadius: 10, background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)", overflow: "hidden" }}>
              <button
                onClick={toggleHistory}
                style={{
                  width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "10px 14px", border: "none", background: "transparent", cursor: "pointer",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 800, color: "#2563eb", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  <History size={13} /> Movement History
                </span>
                {showHistory ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
              </button>
              {showHistory && (
                <div style={{ padding: "0 14px 14px" }}>
                  {loadingHistory ? (
                    <div className="flex justify-center py-4"><Loader2 size={15} className="animate-spin text-gray-400" /></div>
                  ) : history.length === 0 ? (
                    <p style={{ fontSize: 11.5, color: "#94a3b8", padding: "6px 0" }}>No recorded changes yet</p>
                  ) : (
                    <div style={{ maxHeight: 220, overflowY: "auto" }}>
                      <table className="w-full" style={{ fontSize: 11.5 }}>
                        <thead>
                          <tr style={{ textAlign: "left", color: "#94a3b8", fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                            <th style={{ padding: "4px 6px" }}>When</th>
                            <th style={{ padding: "4px 6px" }}>Field</th>
                            <th style={{ padding: "4px 6px" }}>From</th>
                            <th style={{ padding: "4px 6px" }}>To</th>
                            <th style={{ padding: "4px 6px" }}>By</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history.map((h) => (
                            <tr key={h.id} style={{ borderTop: "1px solid rgba(148,163,184,0.25)" }}>
                              <td style={{ padding: "5px 6px", color: "#64748b", whiteSpace: "nowrap" }}>
                                {h.changed_at ? new Date(h.changed_at).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }) : "—"}
                              </td>
                              <td style={{ padding: "5px 6px", color: "#334155", fontWeight: 700, textTransform: "capitalize" }}>
                                {(h.field || "").replace(/_/g, " ")}
                              </td>
                              <td style={{ padding: "5px 6px", color: "#dc2626" }}>{h.old_value || "—"}</td>
                              <td style={{ padding: "5px 6px", color: "#16a34a", fontWeight: 600 }}>{h.new_value || "—"}</td>
                              <td style={{ padding: "5px 6px", color: "#64748b" }}>{h.changed_by || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            {saveError && <span style={{ fontSize: 11.5, color: "#dc2626", fontWeight: 600 }}>{saveError}</span>}
            <button
              onClick={onClose}
              style={{ fontSize: 12, fontWeight: 700, color: "#64748b", background: "none", border: "none", cursor: "pointer" }}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700, color: "#fff",
                padding: "9px 20px", borderRadius: 10, border: "none", cursor: saving ? "wait" : "pointer",
                background: "#2563eb", boxShadow: "3px 3px 8px rgba(37,99,235,0.3)",
              }}
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              {isNew ? "Add Employee" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Mark an employee as resigned — resign date + reason ────────────────────────
function ResignEmployeeModal({ employee, onClose, onSaved }) {
  const [resignDate, setResignDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!resignDate) { setError("Resign date is required"); return; }
    setSaving(true); setError("");
    try {
      await hrApi.resignEmployee(employee.user_id, { resign_date: resignDate, reason: reason.trim() || null });
      onSaved?.();
    } catch (err) {
      setError(err?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(15,23,42,0.6)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-2xl" style={{ background: "#f1f5f9", boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)" }}>
        <div className="flex items-center justify-between px-6 py-4" style={{ background: "linear-gradient(135deg, #dc2626, #ef4444)", borderRadius: "16px 16px 0 0" }}>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 800, color: "#fff" }}>Mark as Resigned</h3>
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.85)", fontWeight: 600, marginTop: 2 }}>
              {employee.full_name} · {employee.user_id}
            </p>
          </div>
          <button onClick={onClose} style={{ padding: 6, borderRadius: 8, border: "none", background: "rgba(255,255,255,0.2)", color: "#fff", cursor: "pointer" }}>
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="text-xs font-semibold text-gray-500">Resign Date *</label>
            <input
              type="date"
              value={resignDate}
              onChange={(e) => setResignDate(e.target.value)}
              className="w-full mt-1 rounded-lg border-none bg-white px-3 py-2 text-sm text-gray-800 outline-none"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-500">Reason</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              placeholder="Optional — reason for resignation..."
              className="w-full mt-1 rounded-lg border-none bg-white px-3 py-2 text-sm text-gray-800 outline-none resize-none"
            />
          </div>

          {error && <p style={{ fontSize: 11.5, color: "#dc2626", fontWeight: 600 }}>{error}</p>}

          <div className="flex items-center justify-end gap-3 pt-1">
            <button onClick={onClose} style={{ fontSize: 12, fontWeight: 700, color: "#64748b", background: "none", border: "none", cursor: "pointer" }}>
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700, color: "#fff",
                padding: "9px 18px", borderRadius: 10, border: "none", cursor: saving ? "wait" : "pointer",
                background: "#dc2626", boxShadow: "3px 3px 8px rgba(220,38,38,0.3)",
              }}
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              Confirm Resign
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Organization Chart (Employee Data) ─────────────────────────────────────────
const ORG_DEPT_COLORS = {
  "Board of Commissioners": "#0f172a",
  "Board of Directors":     "#ef4444",
  "Sales & Marketing":      "#3b82f6",
  "Strategy Development":   "#a855f7",
  "Plant":                  "#f59e0b",
  "Administration":         "#10b981",
};
const ORG_DEPT_ORDER = {
  "Board of Commissioners": 0, "Board of Directors": 1, "Sales & Marketing": 2,
  "Strategy Development": 3, "Plant": 4, "Administration": 5,
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
  set.add(node.id);
  node.children?.forEach((c) => orgCollectIds(c, set));
}

// General Manager level and above (root, Board/President Director, General
// Managers, and each GM's direct team leads) stays in the original
// horizontal fan-out layout — proportional and print-friendly at the top,
// where sibling counts stay small. Anything below that (actual team/staff
// listings, which can run to dozens of siblings) renders as a vertical
// indented tree instead, which scales far better than fanning out sideways.
const GM_TIER_RE = /general manager|president director|\bdirector\b|board of/i;
const isGmTierOrAbove = (position) => GM_TIER_RE.test((position || "").trim());

function OrgCard({ node, isPlaceholder, color, isMatch, groupLabel, onNodeClick, hasChildren, width }) {
  return (
    <div
      onClick={() => !isPlaceholder && onNodeClick(node)}
      style={{
        width, borderRadius: 6, overflow: "hidden",
        cursor: isPlaceholder ? "default" : "pointer",
        background: "#fff",
        border: `1.5px solid ${isMatch ? color : "#c4cddb"}`,
        boxShadow: isMatch ? `0 0 0 2px ${color}55` : "2px 3px 6px rgba(30,41,59,0.12)",
      }}
    >
      {isPlaceholder ? (
        <div style={{ padding: "8px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <UserCheck size={12} color="#64748b" />
            <span style={{ fontSize: 11.5, fontWeight: 800, color: "#64748b" }}>{node.full_name}</span>
          </div>
          <div style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, marginTop: 2 }}>{node.children.length} branch{node.children.length !== 1 ? "es" : ""}</div>
        </div>
      ) : (
        <>
          {groupLabel && (
            <div style={{
              background: color, color: "#fff", fontSize: 9.5, fontWeight: 800,
              padding: "4px 10px", textAlign: "center", textTransform: "uppercase", letterSpacing: "0.02em",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }} title={groupLabel}>
              {groupLabel}
            </div>
          )}
          <div style={{ padding: "7px 10px 9px", textAlign: "center" }}>
            <div style={{
              fontSize: 10, fontWeight: 700, color: "#475569", textDecoration: "underline",
              textDecorationColor: color, textUnderlineOffset: 2,
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }} title={node.position || ""}>
              {node.position || "—"}
            </div>
            <div style={{
              fontSize: 12, fontWeight: 700, color: "#1e293b", marginTop: 3,
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }} title={node.full_name}>
              {node.full_name || "—"}
            </div>
            {hasChildren && (
              <div style={{ fontSize: 8.5, fontWeight: 700, color: "#94a3b8", marginTop: 2 }}>
                {node.children.length} direct report{node.children.length !== 1 ? "s" : ""}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function OrgNode({ node, mode, expanded, toggle, matchIds, onNodeClick, visibleIds }) {
  if (visibleIds && !visibleIds.has(node.id)) return null;

  const hasChildren = !!node.children?.length;
  const isOpen = expanded.has(node.id);
  const isMatch = matchIds.has(node.id);
  const isPlaceholder = node.id === null;
  const color = isPlaceholder ? "#94a3b8" : orgDeptColor(node.department);
  const groupLabel = node.sub_team || node.division || node.department || "";
  // Placeholder ("N branches") nodes have no real position, so just carry
  // the parent's own mode forward instead of falling through to "vertical".
  const childMode = isPlaceholder ? mode : (isGmTierOrAbove(node.position) ? "h" : "v");
  const childList = hasChildren && isOpen && (
    <ul className={childMode === "h" ? "org-tree-h" : "org-tree"}>
      {node.children.map((c) => (
        <OrgNode key={c.id} node={c} mode={childMode} expanded={expanded} toggle={toggle} matchIds={matchIds} onNodeClick={onNodeClick} visibleIds={visibleIds} />
      ))}
    </ul>
  );

  if (mode === "h") {
    return (
      <li>
        <div style={{ position: "relative" }}>
          <OrgCard node={node} isPlaceholder={isPlaceholder} color={color} isMatch={isMatch} groupLabel={groupLabel} onNodeClick={onNodeClick} hasChildren={hasChildren} width={168} />
          {hasChildren && (
            <button
              onClick={(e) => { e.stopPropagation(); toggle(node.id); }}
              title={isOpen ? "Collapse" : "Expand"}
              style={{
                position: "absolute", bottom: -10, left: "50%", transform: "translateX(-50%)",
                width: 20, height: 20, borderRadius: "50%", border: "2px solid #fff",
                background: color, color: "#fff", cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center", boxShadow: "2px 2px 5px rgba(0,0,0,0.2)",
                zIndex: 2, padding: 0,
              }}
            >
              {isOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
          )}
        </div>
        {childList}
      </li>
    );
  }

  return (
    <li>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); toggle(node.id); }}
            title={isOpen ? "Collapse" : "Expand"}
            style={{
              flexShrink: 0, width: 20, height: 20, borderRadius: "50%", border: "none",
              background: color, color: "#fff", cursor: "pointer", display: "flex",
              alignItems: "center", justifyContent: "center", boxShadow: "1px 2px 4px rgba(0,0,0,0.18)",
              padding: 0,
            }}
          >
            {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </button>
        ) : (
          <span style={{ flexShrink: 0, width: 20, height: 20 }} />
        )}

        <OrgCard node={node} isPlaceholder={isPlaceholder} color={color} isMatch={isMatch} groupLabel={groupLabel} onNodeClick={onNodeClick} hasChildren={hasChildren} width={190} />
      </div>

      {childList}
    </li>
  );
}

// ── Add/Edit/Delete a single org structure position — shared by the chart's
// click-to-edit and the Manage Structure table's Add/Edit actions ──────────
function OrgNodeFormModal({ node, onClose, onSaved, onDeleted }) {
  const isNew = !node?.id;
  const [form, setForm] = useState({
    full_name:     node?.full_name || "",
    position:      node?.position || "",
    department:    node?.department || "",
    division:      node?.division || "",
    sub_team:      node?.sub_team || "",
    join_date:     node?.join_date || "",
    supervisor_id: node?.supervisor_id ?? null,
  });
  const [saving, setSaving]     = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError]       = useState("");
  const [lov, setLov]           = useState([]);
  const [positionLov, setPositionLov] = useState([]);
  const [departmentLov, setDepartmentLov] = useState([]);
  const [divisionLov, setDivisionLov] = useState([]);
  const [subTeamLov, setSubTeamLov] = useState([]);
  const [supQuery, setSupQuery] = useState("");
  const [supOpen, setSupOpen]   = useState(false);
  const [customFields, setCustomFields] = useState(() => new Set());

  useEffect(() => {
    hrApi.getOrgStructureLov().then((r) => setLov(r || [])).catch(() => {});
    hrApi.getOrgStructurePositions().then((r) => setPositionLov(r || [])).catch(() => {});
    hrApi.getOrgStructureDepts().then((r) => setDepartmentLov(r || [])).catch(() => {});
    hrApi.getOrgStructureDivisions().then((r) => setDivisionLov(r || [])).catch(() => {});
    hrApi.getOrgStructureSubTeams().then((r) => setSubTeamLov(r || [])).catch(() => {});
  }, []);

  const supervisorName = lov.find((n) => n.id === form.supervisor_id)?.full_name;
  const matches = lov
    .filter((n) => n.id !== node?.id)
    .filter((n) => !supQuery.trim() || n.full_name?.toLowerCase().includes(supQuery.trim().toLowerCase()))
    .slice(0, 8);

  const handleSave = async () => {
    if (!form.full_name.trim()) { setError("Name is required"); return; }
    setSaving(true); setError("");
    try {
      if (isNew) await hrApi.createOrgStructureNode(form);
      else await hrApi.updateOrgStructureNode(node.id, form);
      onSaved?.();
    } catch (err) {
      setError(err?.detail || "Failed to save");
    } finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete "${node.full_name}"? Their direct reports will be reassigned to their supervisor's supervisor.`)) return;
    setDeleting(true); setError("");
    try {
      await hrApi.deleteOrgStructureNode(node.id);
      onDeleted?.();
    } catch (err) {
      setError(err?.detail || "Failed to delete");
    } finally { setDeleting(false); }
  };

  const field = (key, label, extra) => (
    <div key={key} style={extra?.full ? { gridColumn: "1 / -1" } : undefined}>
      <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b" }}>{label}</label>
      <input
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        style={{ width: "100%", fontSize: 12.5, fontWeight: 600, padding: "8px 10px", borderRadius: 8, border: "none", background: "#fff", color: "#1e293b", outline: "none", marginTop: 2 }}
      />
    </div>
  );

  // ── LOV dropdown for position/department/division/sub_team — a plain
  // <select> (not <datalist>, whose "type first, then see suggestions"
  // behavior isn't discoverable enough — HR expects a clickable list like
  // every other LOV in this app). allowCustom fields fall back to a free-
  // text input, via "+ Type new value..." or automatically when the saved
  // value isn't in the list (e.g. an older record) so nothing gets silently
  // blanked out. Department has no escape hatch — it's a small fixed
  // taxonomy and free-typing it is exactly what caused it to fragment
  // before (see department_taxonomy memory). ─────────────────────────────
  const NEW_VALUE = "__new__";
  const selectField = (key, label, options, extra) => {
    const isCustom = customFields.has(key) || (form[key] && options.length > 0 && !options.includes(form[key]));
    return (
      <div key={key} style={extra?.full ? { gridColumn: "1 / -1" } : undefined}>
        <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b" }}>{label}</label>
        {isCustom ? (
          <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
            <input
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              placeholder="Type value..."
              style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, padding: "8px 10px", borderRadius: 8, border: "none", background: "#fff", color: "#1e293b", outline: "none" }}
            />
            {options.length > 0 && (
              <button type="button" title="Pick from list instead"
                onClick={() => { setCustomFields((p) => { const n = new Set(p); n.delete(key); return n; }); setForm({ ...form, [key]: "" }); }}
                style={{ padding: "0 10px", borderRadius: 8, border: "none", background: "#e2e8f0", color: "#475569", cursor: "pointer", fontSize: 11, fontWeight: 700 }}>
                List
              </button>
            )}
          </div>
        ) : (
          <select
            value={form[key] || ""}
            onChange={(e) => {
              if (e.target.value === NEW_VALUE) {
                setCustomFields((p) => new Set(p).add(key));
                setForm({ ...form, [key]: "" });
              } else {
                setForm({ ...form, [key]: e.target.value });
              }
            }}
            style={{ width: "100%", fontSize: 12.5, fontWeight: 600, padding: "8px 10px", borderRadius: 8, border: "none", background: "#fff", color: "#1e293b", outline: "none", marginTop: 2, cursor: "pointer" }}
          >
            <option value="">— Select —</option>
            {options.map((o) => <option key={o} value={o}>{o}</option>)}
            {extra?.allowCustom && <option value={NEW_VALUE}>+ Type new value...</option>}
          </select>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(15,23,42,0.6)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl" style={{ background: "#f1f5f9", boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)" }}>
        <div className="flex items-center justify-between px-6 py-4" style={{ background: "linear-gradient(135deg, #2563eb, #3b82f6)", borderRadius: "16px 16px 0 0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 800, color: "#fff" }}>{isNew ? "Add Position" : "Edit Position"}</h3>
          <button onClick={onClose} style={{ padding: 6, borderRadius: 8, border: "none", background: "rgba(255,255,255,0.2)", color: "#fff", cursor: "pointer" }}><X size={16} /></button>
        </div>

        <div className="p-6 space-y-3">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 12px" }}>
            {field("full_name", "Full Name *", { full: true })}
            {selectField("position", "Position", positionLov, { allowCustom: true })}
            {selectField("department", "Department", departmentLov)}
            {selectField("division", "Division", divisionLov, { allowCustom: true })}
            {selectField("sub_team", "Sub-team / Region", subTeamLov, { allowCustom: true })}
            <div>
              <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b" }}>Join Date</label>
              <input type="date" value={form.join_date || ""} onChange={(e) => setForm({ ...form, join_date: e.target.value })}
                style={{ width: "100%", fontSize: 12.5, fontWeight: 600, padding: "8px 10px", borderRadius: 8, border: "none", background: "#fff", color: "#1e293b", outline: "none", marginTop: 2 }} />
            </div>
          </div>

          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#64748b" }}>Direct Supervisor</label>
            <input
              value={supOpen ? supQuery : (supervisorName || "")}
              onFocus={() => { setSupOpen(true); setSupQuery(""); }}
              onChange={(e) => setSupQuery(e.target.value)}
              placeholder="Search name... (leave empty = top of chart)"
              style={{ width: "100%", fontSize: 12.5, fontWeight: 600, padding: "8px 10px", borderRadius: 8, border: "none", background: "#fff", color: "#1e293b", outline: "none", marginTop: 2 }}
            />
            {supOpen && (
              <div style={{ maxHeight: 150, overflowY: "auto", marginTop: 4, borderRadius: 8, background: "#fff" }}>
                <div onClick={() => { setForm({ ...form, supervisor_id: null }); setSupOpen(false); }}
                  style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#dc2626", cursor: "pointer" }}>
                  — No supervisor (top of chart)
                </div>
                {matches.map((n) => (
                  <div key={n.id} onClick={() => { setForm({ ...form, supervisor_id: n.id }); setSupOpen(false); }}
                    style={{ padding: "6px 10px", fontSize: 11.5, fontWeight: 600, color: "#1e293b", cursor: "pointer" }}>
                    {n.full_name} <span style={{ color: "#94a3b8", fontWeight: 500 }}>· {n.department || "—"}</span>
                  </div>
                ))}
                {matches.length === 0 && <div style={{ padding: "6px 10px", fontSize: 11, color: "#94a3b8" }}>No matches</div>}
                <div onClick={() => setSupOpen(false)} style={{ padding: "6px 10px", fontSize: 11, fontWeight: 700, color: "#64748b", cursor: "pointer", textAlign: "center" }}>Close</div>
              </div>
            )}
          </div>

          {error && <p style={{ fontSize: 11.5, color: "#dc2626", fontWeight: 600 }}>{error}</p>}

          <div className="flex items-center justify-between pt-2">
            {!isNew ? (
              <button onClick={handleDelete} disabled={deleting || saving}
                style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, fontWeight: 700, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete
              </button>
            ) : <span />}
            <div className="flex items-center gap-3">
              <button onClick={onClose} style={{ fontSize: 11.5, fontWeight: 700, color: "#64748b", background: "none", border: "none", cursor: "pointer" }}>Cancel</button>
              <button onClick={handleSave} disabled={saving || deleting}
                style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: "#fff", padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer", background: "#2563eb" }}>
                {saving && <Loader2 size={13} className="animate-spin" />} {isNew ? "Add" : "Save"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function OrgChartView() {
  const [root, setRoot]         = useState(null);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState(() => new Set());
  const [search, setSearch]     = useState("");
  const [zoom, setZoom]         = useState(1);
  const [selectedNode, setSelectedNode] = useState(null);
  const [error, setError]       = useState("");
  const [exportingImage, setExportingImage] = useState(false);
  const chartRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await hrApi.getOrgStructureTree();
      setRoot(res.root || null);
      setTotal(res.total || 0);
      if (res.root) {
        const ids = new Set();
        const walk = (node, depth) => {
          if (!node) return;
          ids.add(node.id);
          if (depth < 2) node.children?.forEach((c) => walk(c, depth + 1));
        };
        walk(res.root, 0);
        setExpanded(ids);
      }
    } catch (err) {
      setRoot(null);
      setError(err?.detail || "Failed to load organization chart. Please try refreshing.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

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
      if ((node.full_name || "").toLowerCase().includes(q)) found.add(node.id);
      node.children?.forEach(walk);
    };
    walk(root);
    return found;
  }, [q, root]);

  // While searching: only the matched person(s), their full supervisor chain
  // (ancestors), and their full subordinate chain (descendants) stay visible —
  // everything else is hidden rather than just highlighted. null = show everything.
  const visibleIds = useMemo(() => {
    if (!q || !root) return null;
    if (matchIds.size === 0) return new Set();

    const parentOf = {};
    const byId = {};
    const index = (node, parent) => {
      if (!node) return;
      byId[node.id] = node;
      if (parent) parentOf[node.id] = parent.id;
      node.children?.forEach((c) => index(c, node));
    };
    index(root, null);

    const visible = new Set();
    matchIds.forEach((id) => {
      let cur = id;
      while (cur != null) { visible.add(cur); cur = parentOf[cur]; }
    });
    const addDescendants = (node) => {
      if (!node) return;
      node.children?.forEach((c) => { visible.add(c.id); addDescendants(c); });
    };
    matchIds.forEach((id) => addDescendants(byId[id]));

    return visible;
  }, [q, root, matchIds]);

  useEffect(() => {
    if (!visibleIds || visibleIds.size === 0) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }, [visibleIds]); // eslint-disable-line

  const deptsPresent = useMemo(() => {
    const set = new Set();
    const walk = (node) => {
      if (!node || node.id === null) return;
      if (node.department) set.add(node.department);
      node.children?.forEach(walk);
    };
    walk(root);
    return [...set].sort((a, b) => (ORG_DEPT_ORDER[a] ?? 99) - (ORG_DEPT_ORDER[b] ?? 99));
  }, [root]);

  const handleDownloadImage = async () => {
    if (!chartRef.current) return;
    setExportingImage(true);
    const prevZoom = zoom;
    setZoom(1);
    await new Promise((r) => setTimeout(r, 60)); // let the zoom=1 re-render paint before capture
    try {
      const dataUrl = await toPng(chartRef.current, { backgroundColor: "#dfe5ed", pixelRatio: 2 });
      const link = document.createElement("a");
      link.download = `organization-structure_${new Date().toISOString().slice(0, 10)}.png`;
      link.href = dataUrl;
      link.click();
    } catch (_) {
      alert("Failed to export image");
    } finally {
      setZoom(prevZoom);
      setExportingImage(false);
    }
  };

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
  if (!root) return <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No organization structure data yet. Add a position or import Excel in the Manage Structure tab.</p>;

  return (
    <div className="space-y-4">
      <div style={{
        borderRadius: 14, padding: "12px 0", textAlign: "center",
        background: "linear-gradient(135deg, #2563eb, #3b82f6)",
        boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: "0.12em", textTransform: "uppercase" }}>
          <Network size={13} style={{ display: "inline", marginRight: 6, verticalAlign: -2 }} />
          Organization Chart
        </h2>
        <p style={{ fontSize: 10.5, color: "rgba(255,255,255,0.85)", fontWeight: 600, marginTop: 2 }}>{total} positions</p>
      </div>

      {/* Toolbar */}
      <div style={{
        display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        padding: "10px 14px", borderRadius: 14,
        background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
      }}>
        <div style={{ position: "relative", minWidth: 220 }}>
          <Search size={12} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name..."
            style={{ width: "100%", fontSize: 12, fontWeight: 600, padding: "7px 10px 7px 28px", borderRadius: 8, border: "none", background: "#fff", color: "#334155", outline: "none" }}
          />
        </div>
        {q && (
          <span style={{ fontSize: 11, fontWeight: 700, color: matchIds.size ? "#2563eb" : "#dc2626" }}>
            {matchIds.size} match{matchIds.size !== 1 ? "es" : ""}
          </span>
        )}
        <div style={{ flex: 1 }} />

        <button onClick={handleDownloadImage} disabled={exportingImage} title="Download as image"
          className="flex items-center gap-1.5"
          style={{ padding: "7px 12px", borderRadius: 8, border: "none", cursor: exportingImage ? "wait" : "pointer", background: "#2563eb", color: "#fff", fontSize: 11.5, fontWeight: 700, boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
          {exportingImage ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
          {exportingImage ? "Exporting..." : "Download Image"}
        </button>

        {[
          { icon: ZoomOut,   title: "Zoom out",     onClick: () => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2))) },
          { icon: ZoomIn,    title: "Zoom in",      onClick: () => setZoom((z) => Math.min(1.5, +(z + 0.1).toFixed(2))) },
          { icon: Maximize2, title: "Expand all",   onClick: () => { const ids = new Set(); orgCollectIds(root, ids); setExpanded(ids); } },
          { icon: Minimize2, title: "Collapse all", onClick: () => setExpanded(new Set([root.id])) },
          { icon: RefreshCw, title: "Refresh",      onClick: load },
        ].map(({ icon: Icon, title, onClick }) => (
          <button key={title} onClick={onClick} title={title}
            style={{ padding: 8, borderRadius: 8, border: "none", cursor: "pointer", background: "#f1f5f9", color: "#64748b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
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
        {visibleIds && visibleIds.size === 0 ? (
          <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
            No one found matching "{search}".
          </p>
        ) : (
          <div ref={chartRef} style={{ transform: `scale(${zoom})`, transformOrigin: "top center", display: "inline-block", minWidth: "100%", background: "#dfe5ed" }}>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              <OrgNode node={root} mode="h" expanded={expanded} toggle={toggle} matchIds={matchIds} onNodeClick={setSelectedNode} visibleIds={visibleIds} />
            </ul>
          </div>
        )}
      </div>

      {selectedNode && (
        <OrgNodeFormModal
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onSaved={() => { setSelectedNode(null); load(); }}
          onDeleted={() => { setSelectedNode(null); load(); }}
        />
      )}
    </div>
  );
}

function OrgManageView() {
  const [nodes, setNodes]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [departments, setDepartments] = useState([]);
  const [modalNode, setModalNode] = useState(null); // null=closed, {}=new, {...}=edit
  const [sortBy, setSortBy]   = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const [file, setFile]           = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError]   = useState(null);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      if (deptFilter) params.department = deptFilter;
      const res = await hrApi.getOrgStructureList(params);
      setNodes(res || []);
    } catch (_) {}
    finally { setLoading(false); }
  }, [search, deptFilter]);

  const loadDepts = useCallback(async () => {
    try { setDepartments((await hrApi.getOrgStructureDepts()) || []); } catch (_) {}
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadDepts(); }, [loadDepts]);

  const handleDelete = async (n) => {
    if (!confirm(`Delete "${n.full_name}"? Their direct reports will be reassigned to their supervisor's supervisor.`)) return;
    try {
      await hrApi.deleteOrgStructureNode(n.id);
      load(); loadDepts();
    } catch (err) { alert(err?.detail || "Failed to delete"); }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true); setUploadError(null); setUploadResult(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await hrApi.importOrgStructure(fd);
      setUploadResult(res);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      load(); loadDepts();
    } catch (err) {
      setUploadError(err?.detail || "Upload failed");
    } finally { setUploading(false); }
  };

  const sorted = sortRows(nodes, sortBy, sortDir, []);

  return (
    <div className="space-y-4">
      {/* Import */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Import from Excel</h3>
            <p className="text-xs text-gray-500 mt-1">
              Upload the "Daftar Karyawan" template (Departemen, Divisi/Tim, Wilayah/Sub-Tim, Nama, Posisi, Tanggal Bergabung, Atasan Langsung).
              This <strong className="text-gray-400">replaces the entire structure</strong>.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input ref={inputRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={(e) => setFile(e.target.files[0])} />
            <button onClick={() => inputRef.current?.click()} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-300 hover:border-gray-600 transition-colors">
              <FileSearch size={13} /> {file ? file.name : "Choose File"}
            </button>
            <button onClick={handleUpload} disabled={!file || uploading}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-3 py-2 text-xs font-semibold text-white transition-colors">
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} {uploading ? "Uploading..." : "Import"}
            </button>
          </div>
        </div>
        {uploadError && <p className="text-xs text-red-400 mt-2">{uploadError}</p>}
        {uploadResult && <p className="text-xs text-emerald-400 mt-2">{uploadResult.message}</p>}
      </div>

      {/* Filter bar + Add button */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name / position..."
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-8 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
        <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer">
          <option value="">ALL</option>
          {departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <button onClick={() => setModalNode({})} className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-2 text-sm font-semibold text-white transition-colors">
          <Plus size={14} /> Add Position
        </button>
      </div>

      {/* Table */}
      <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 520 }}>
        <table className="w-full text-sm" style={{ minWidth: 900 }}>
          <thead className="sticky top-0 z-10 bg-gray-800">
            <tr>
              <SortableTH label="Name" field="full_name" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortableTH label="Position" field="position" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortableTH label="Department" field="department" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-500">Division / Sub-team</th>
              <SortableTH label="Join Date" field="join_date" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-500">Supervisor</th>
              <th className="px-3 py-2.5 w-12"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr><td colSpan={7} className="py-12 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></td></tr>
            ) : sorted.length === 0 ? (
              <tr><td colSpan={7} className="py-12 text-center text-xs text-gray-600">No structure data yet. Add a position or import Excel.</td></tr>
            ) : sorted.map((n) => (
              <tr key={n.id} onClick={() => setModalNode(n)} className="hover:bg-gray-800/40 cursor-pointer transition-colors">
                <td className="px-3 py-2.5 font-medium text-gray-200 whitespace-nowrap">{n.full_name}</td>
                <td className="px-3 py-2.5 text-gray-400 text-xs whitespace-nowrap">{n.position || "—"}</td>
                <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{n.department || "—"}</td>
                <td className="px-3 py-2.5 text-gray-500 text-xs whitespace-nowrap">{[n.division, n.sub_team].filter(Boolean).join(" / ") || "—"}</td>
                <td className="px-3 py-2.5 text-gray-500 text-xs whitespace-nowrap">{n.join_date || "—"}</td>
                <td className="px-3 py-2.5 text-gray-500 text-xs whitespace-nowrap">{n.supervisor_name || "—"}</td>
                <td className="px-3 py-2.5">
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(n); }} className="p-1 text-gray-600 hover:text-red-400">
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalNode && (
        <OrgNodeFormModal
          node={modalNode.id ? modalNode : null}
          onClose={() => setModalNode(null)}
          onSaved={() => { setModalNode(null); load(); loadDepts(); }}
          onDeleted={() => { setModalNode(null); load(); loadDepts(); }}
        />
      )}
    </div>
  );
}

function OrganizationChartSection() {
  const [view, setView] = useState("chart"); // "chart" | "manage"
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {[
          { id: "chart", label: "Chart", icon: Network },
          { id: "manage", label: "Manage Structure", icon: ListChecks },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
              view === id ? "bg-indigo-600 text-white" : "bg-gray-900 border border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>
      {view === "chart" ? <OrgChartView /> : <OrgManageView />}
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

function EmployeeSummarySection() {
  const [drillYear, setDrillYear] = useState(null); // null = Yearly Summary; a year = Monthly Summary for that year
  const [listModal, setListModal] = useState(null); // drill-down filter payload, or null

  return (
    <div className="space-y-4 mt-2">
      {drillYear == null ? (
        <EmployeeYearSummaryTable onYearClick={setDrillYear} />
      ) : (
        <div className="space-y-3">
          <button
            onClick={() => setDrillYear(null)}
            className="flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
          >
            <ChevronLeft size={13} /> Back to Yearly Summary
          </button>
          <EmployeeMonthSummaryTable
            year={drillYear}
            onDrillDown={(department, division, team, month, year) =>
              setListModal({ department, division, team, month, year })
            }
          />
        </div>
      )}

      {listModal && (
        <EmployeeListModal initialFilters={listModal} onClose={() => setListModal(null)} />
      )}
    </div>
  );
}

// ── Employee List — opened as a modal from a Summary per Month drill-down
// click, filtered to exactly the employees behind that number ("active as
// of" that month, same windowing the summary cell was computed with) ──────
function EmployeeListModal({ initialFilters, onClose }) {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const [data, setData] = useState({ employees: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState(initialFilters?.department || "");
  const [divisionFilter, setDivisionFilter] = useState(initialFilters?.division || "");
  const [educationFilter, setEducationFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState(initialFilters?.team || "");
  const [employmentStatusFilter, setEmploymentStatusFilter] = useState("");
  const [maritalFilter, setMaritalFilter] = useState("");
  const [sexFilter, setSexFilter] = useState("");
  const [asOfMonth, setAsOfMonth] = useState(() => String(initialFilters?.month || new Date().getMonth() + 1));
  const [asOfYear, setAsOfYear] = useState(() => String(initialFilters?.year || new Date().getFullYear()));
  const [departments, setDepartments] = useState([]);
  const [educations, setEducations] = useState([]);
  const [levels, setLevels] = useState([]);
  const [teams, setTeams] = useState([]);
  const [maritalStatuses, setMaritalStatuses] = useState([]);
  const [joinYears, setJoinYears] = useState([]);
  const [sortBy, setSortBy] = useState("date_of_joining");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [employeeNames, setEmployeeNames] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [showFiltersPanel, setShowFiltersPanel] = useState(false);

  const PAGE_SIZE = 8;

  const fetchLov = useCallback(async () => {
    try {
      const [d, e, l, m, y] = await Promise.all([
        fetch(`${API}/departments`, { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${API}/educations`, { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${API}/levels`, { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${API}/marital-statuses`, { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${API}/join-years`, { headers }).then((r) => r.ok ? r.json() : []),
      ]);
      setDepartments(d); setEducations(e); setLevels(l); setMaritalStatuses(m); setJoinYears(y);
    } catch (_) {}
  }, []); // eslint-disable-line

  const fetchTeams = useCallback(async (dept) => {
    try {
      const url = dept ? `${API}/teams?department=${encodeURIComponent(dept)}` : `${API}/teams`;
      const res = await fetch(url, { headers });
      if (res.ok) setTeams(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  const handleSearch = (v) => { setSearch(v); setPage(1); };
  const handleDeptFilter = (v) => { setDeptFilter(v); setDivisionFilter(""); setTeamFilter(""); fetchTeams(v); setPage(1); };

  const fetchEmployeeNames = useCallback(async () => {
    try { setEmployeeNames((await hrApi.getEmployeeNames()) || []); } catch (_) {}
  }, []); // eslint-disable-line

  const summaryParams = useCallback(() => ({
    ...(search ? { search } : {}),
    ...(deptFilter ? { department: deptFilter } : {}),
    ...(divisionFilter ? { division: divisionFilter } : {}),
    ...(educationFilter ? { education: educationFilter } : {}),
    ...(levelFilter ? { level: levelFilter } : {}),
    ...(teamFilter ? { team: teamFilter } : {}),
    ...(employmentStatusFilter ? { employment_status: employmentStatusFilter } : {}),
    ...(maritalFilter ? { marital_status: maritalFilter } : {}),
    ...(sexFilter ? { sex: sexFilter } : {}),
    ...(asOfMonth ? { snapshot_month: asOfMonth } : {}),
    ...(asOfYear  ? { snapshot_year: asOfYear }   : {}),
  }), [search, deptFilter, divisionFilter, educationFilter, levelFilter, teamFilter, employmentStatusFilter, maritalFilter, sexFilter, asOfMonth, asOfYear]);

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page, page_size: PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir,
        ...summaryParams(),
      });
      const res = await fetch(`${API}?${params}`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, summaryParams, sortBy, sortDir]); // eslint-disable-line

  const handleExport = async () => {
    setExporting(true);
    try {
      const fields = EMPLOYEE_COLS.map(c => c.key).join(",");
      const params = new URLSearchParams({ sort_by: sortBy, sort_dir: sortDir, fields, ...summaryParams() });
      const res = await fetch(`${API}/export?${params}`, { headers });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `employee_summary_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (_) {
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    fetchLov(); fetchEmployeeNames();
    if (initialFilters?.department) fetchTeams(initialFilters.department);
  }, []); // eslint-disable-line
  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  const handleSort = (field) => {
    if (sortBy === field) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortBy(field); setSortDir("asc"); }
    setPage(1);
  };

  const filterSelect = (label, value, onChange, options) => (
    <div>
      <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">{label}</label>
      <select
        value={value}
        onChange={(e) => { onChange(e.target.value); setPage(1); }}
        className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
      >
        <option value="">All</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );

  const COLS = getEmployeeFullCols(employeeNames);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="w-full max-w-6xl max-h-[90vh] overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-200">Employee List</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300">
            <X size={16} />
          </button>
        </div>

        {/* Total + Download */}
        <div className="flex items-center justify-between">
          <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-1.5 inline-block">
            <span className="text-base font-bold text-indigo-400">{data.total}</span>
            <span className="text-[10px] font-semibold text-gray-400 ml-1.5">Employees Shown</span>
          </div>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 rounded-lg border border-green-700/50 bg-green-500/10 px-3 py-1.5 text-xs font-medium text-green-400 hover:bg-green-500/20 transition-colors disabled:opacity-50"
          >
            {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            Download Excel
          </button>
        </div>

        {/* Toolbar — Refresh + search + Filters popup, same layout as the Employee List tab */}
        <div className="flex flex-wrap items-end gap-2">
          <button
            onClick={fetchEmployees}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-semibold text-gray-400 hover:border-gray-600 hover:text-gray-200 transition-colors"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
          </button>

          <div className="relative w-48">
            <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Search</label>
            <Search size={13} className="absolute left-2.5 top-[30px] text-gray-500" />
            <input
              type="text"
              placeholder="Name / NIK / position..."
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-8 pr-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 transition-colors"
            />
            {search && (
              <button onClick={() => handleSearch("")} className="absolute right-2 top-[30px] text-gray-600 hover:text-gray-400">
                <X size={13} />
              </button>
            )}
          </div>

          <div className="relative">
            <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">&nbsp;</label>
            <button
              onClick={() => setShowFiltersPanel(v => !v)}
              className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-semibold text-gray-300 hover:border-indigo-500 hover:text-white transition-colors"
            >
              <SlidersHorizontal size={13} /> Filters
            </button>
            {showFiltersPanel && (
              <>
                <div onClick={() => setShowFiltersPanel(false)} className="fixed inset-0 z-20" />
                <div className="absolute left-0 top-full mt-2 z-30 w-64 rounded-xl border border-gray-700 bg-gray-900 shadow-2xl p-4">
                  <div className="flex flex-col gap-3">
                    {filterSelect("Department", deptFilter, handleDeptFilter, departments)}
                    {filterSelect("Team", teamFilter, (v) => { setTeamFilter(v); setPage(1); }, teams)}
                    {filterSelect("Education", educationFilter, setEducationFilter, educations)}
                    {filterSelect("Level", levelFilter, setLevelFilter, levels)}
                    <div>
                      <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Employment State</label>
                      <select
                        value={employmentStatusFilter}
                        onChange={(e) => { setEmploymentStatusFilter(e.target.value); setPage(1); }}
                        className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="">All</option>
                        <option value="Active">Active</option>
                        <option value="Resign">Inactive</option>
                      </select>
                    </div>
                    {filterSelect("Marital Status", maritalFilter, setMaritalFilter, maritalStatuses)}
                    <div>
                      <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Sex</label>
                      <select
                        value={sexFilter}
                        onChange={(e) => { setSexFilter(e.target.value); setPage(1); }}
                        className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="">All</option>
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                      </select>
                    </div>
                    <div title="Shows employees active as of the end of the selected Month/Year (joined on/before, not yet resigned)">
                      <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">As of (Month)</label>
                      <select
                        value={asOfMonth}
                        onChange={(e) => { setAsOfMonth(e.target.value); setPage(1); }}
                        className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="">All</option>
                        {MONTHS_ID.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                      </select>
                    </div>
                    <div title="Shows employees active as of the end of the selected Month/Year (joined on/before, not yet resigned)">
                      <label className="mb-1 block text-[11px] font-semibold text-gray-400 uppercase tracking-wide">As of (Year)</label>
                      <select
                        value={asOfYear}
                        onChange={(e) => { setAsOfYear(e.target.value); setPage(1); }}
                        className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="">All</option>
                        {joinYears.map((y) => <option key={y} value={y}>{y}</option>)}
                      </select>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Table — every field on the Employee record, same columns as the Employee List tab */}
        <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 480 }}>
          <table className="w-full text-sm" style={{ minWidth: 4200 }}>
            <thead className="sticky top-0 z-10">
              <tr className="bg-gray-800">
                {COLS.map(({ label, field, noSort }) => {
                  const active = !noSort && sortBy === field;
                  return (
                    <th
                      key={field}
                      onClick={() => !noSort && handleSort(field)}
                      className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wider whitespace-nowrap select-none group ${noSort ? "" : "cursor-pointer"}`}
                      style={{ color: active ? "#a5b4fc" : "#6b7280", textAlign: "center" }}
                    >
                      {noSort ? label : (
                        <span className="inline-flex items-center gap-1 justify-center">
                          {label}
                          <span className={`transition-opacity ${active ? "opacity-100" : "opacity-0 group-hover:opacity-50"}`}>
                            {active
                              ? (sortDir === "asc" ? <ChevronUp size={11} className="text-indigo-400" /> : <ChevronDown size={11} className="text-indigo-400" />)
                              : <ArrowUpDown size={10} />}
                          </span>
                        </span>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {loading ? (
                <tr><td colSpan={COLS.length} className="py-12 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></td></tr>
              ) : data.employees.length === 0 ? (
                <tr><td colSpan={COLS.length} className="py-12 text-center text-xs text-gray-600">No employees matching filter</td></tr>
              ) : data.employees.map((e) => (
                <tr key={e.user_id} onClick={() => setSelectedEmployee(e)} className="hover:bg-gray-800/40 transition-colors cursor-pointer">
                  {COLS.map(({ field, mono, bold, align, render }) => (
                    <td
                      key={field}
                      className={`px-3 py-2.5 whitespace-nowrap text-xs ${mono ? "font-mono" : ""} ${bold ? "font-medium text-gray-200" : "text-gray-500"}`}
                      style={{ textAlign: align || "left" }}
                    >
                      {render ? render(e) : (e[field] || "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="flex items-center justify-between" style={{ padding: "10px 0", fontSize: 12 }}>
            <span style={{ color: "#94a3b8", fontWeight: 600 }}>
              {data.total} employees · page {page} of {data.pages}
            </span>
            <div className="flex gap-1">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
                className="rounded-lg border border-gray-700 bg-gray-900 p-1.5 text-gray-400 disabled:opacity-40">
                <ChevronLeft size={13} />
              </button>
              <button onClick={() => setPage((p) => Math.min(data.pages, p + 1))} disabled={page === data.pages}
                className="rounded-lg border border-gray-700 bg-gray-900 p-1.5 text-gray-400 disabled:opacity-40">
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
            onSaved={() => {
              setSelectedEmployee(null);
              fetchEmployees(); fetchEmployeeNames(); fetchLov();
            }}
          />
        )}
      </div>
    </div>
  );
}

// ── Employee Summary: Summary per Year — headcount by dept, Beginning/Ending
// per year (format reference: SUMMARY sheet, "Yearly" block) ──────────────
function EmployeeYearSummaryTable({ onYearClick }) {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsedDepts, setCollapsedDepts] = useState(() => new Set());
  const [collapsedDivisions, setCollapsedDivisions] = useState(() => new Set());

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/summary/by-year`, { headers })
      .then((r) => r.ok ? r.json() : null)
      .then(setD)
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line

  const toggleSet = (setFn) => (key) => setFn((prev) => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });
  const toggleDept = toggleSet(setCollapsedDepts);
  const toggleDivision = toggleSet(setCollapsedDivisions);
  const divKey = (dept, division) => `${dept}::${division}`;

  const visibleRows = d ? d.rows.filter((row) => {
    if (collapsedDepts.has(row.department)) return row.division == null && row.team == null;
    if (row.division && row.team && collapsedDivisions.has(divKey(row.department, row.division))) return false;
    return true;
  }) : [];

  if (loading) return <div className="py-16 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></div>;
  if (!d) return <div className="py-16 text-center text-xs text-gray-600">Failed to load</div>;

  const TH = "px-2.5 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap text-center border-b border-gray-800";
  const TD = "px-2.5 py-2 text-xs text-right whitespace-nowrap";

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-gray-600">Click + to expand a department's teams · click a year to view its monthly breakdown</p>
      <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 480 }}>
      <table className="text-sm" style={{ minWidth: 220 + d.years.length * 140 }}>
        <thead className="sticky top-0 z-10 bg-gray-800">
          <tr>
            <th className={`${TH} text-left sticky left-0 bg-gray-800 z-20`} rowSpan={2}>Department / Division / Team</th>
            {d.years.map((y) => (
              <th
                key={y}
                colSpan={2}
                onClick={() => onYearClick && onYearClick(y)}
                className={`${TH} ${onYearClick ? "cursor-pointer select-none hover:text-indigo-300 hover:bg-gray-700/60" : ""}`}
                title={onYearClick ? `View monthly summary for ${y}` : undefined}
              >
                {y}
              </th>
            ))}
          </tr>
          <tr>
            {d.years.map((y) => ([
              <th key={`${y}-b`} className={TH}>Beginning</th>,
              <th key={`${y}-e`} className={TH}>Ending</th>,
            ]))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {visibleRows.map((row) => {
            const level = row.team ? 2 : row.division ? 1 : 0;
            const hasChildren = level === 0
              ? d.rows.some((r) => r.department === row.department && (r.division || r.team))
              : level === 1
                ? d.rows.some((r) => r.department === row.department && r.division === row.division && r.team)
                : false;
            const toggleKey = level === 0 ? row.department : divKey(row.department, row.division);
            const isOpen = hasChildren && !(level === 0 ? collapsedDepts : collapsedDivisions).has(toggleKey);
            const label = row.team || row.division || row.department;
            const pad = level === 0 ? "" : level === 1 ? "pl-6" : "pl-9";
            const rowClass = level === 0 ? "bg-gray-800/30 font-semibold" : level === 1 ? "bg-gray-900/40 font-medium hover:bg-gray-800/30" : "hover:bg-gray-800/30";
            return (
            <tr key={`${row.department}-${row.division || ""}-${row.team || ""}`} className={rowClass}>
              <td
                onClick={hasChildren ? () => (level === 0 ? toggleDept(toggleKey) : toggleDivision(toggleKey)) : undefined}
                className={`px-2.5 py-2 text-xs whitespace-nowrap sticky left-0 ${pad} ${level === 2 ? "text-gray-400 bg-gray-900" : level === 1 ? "text-gray-300 bg-gray-900/40" : "text-gray-200 bg-gray-800/30"} ${hasChildren ? "cursor-pointer select-none hover:text-indigo-300" : ""}`}
                title={hasChildren && level === 0 ? (isOpen ? "Collapse team list" : "Expand team list") : undefined}
              >
                {hasChildren && (
                  level === 0
                    ? (isOpen
                        ? <Minus size={11} className="inline mr-1 -mt-0.5 text-indigo-400" />
                        : <Plus size={11} className="inline mr-1 -mt-0.5 text-indigo-400" />)
                    : (isOpen
                        ? <ChevronDown size={11} className="inline mr-1 -mt-0.5" />
                        : <ChevronRight size={11} className="inline mr-1 -mt-0.5" />)
                )}
                {label}
              </td>
              {d.years.map((y) => ([
                <td key={`${y}-b`} className={`${TD} ${level === 0 ? "text-gray-500" : "text-gray-500"}`}>{row.by_year[y]?.beginning ?? "—"}</td>,
                <td key={`${y}-e`} className={`${TD} ${level === 0 ? "text-gray-300" : "text-gray-400"}`}>{row.by_year[y]?.ending ?? "—"}</td>,
              ]))}
            </tr>
            );
          })}
          <tr className="bg-gray-800/60 font-bold">
            <td className="px-2.5 py-2 text-xs text-gray-200 whitespace-nowrap sticky left-0 bg-gray-800/60">TOTAL</td>
            {d.years.map((y) => ([
              <td key={`${y}-b`} className={`${TD} text-gray-300`}>{d.total[y]?.beginning ?? "—"}</td>,
              <td key={`${y}-e`} className={`${TD} text-indigo-300`}>{d.total[y]?.ending ?? "—"}</td>,
            ]))}
          </tr>
          <tr>
            <td className="px-2.5 py-2 text-xs text-gray-500 whitespace-nowrap sticky left-0 bg-gray-900">Growth (YoY)</td>
            {d.years.map((y) => {
              const g = d.growth[y];
              return (
                <td key={y} colSpan={2} className={`${TD} ${g == null ? "text-gray-600" : g > 0 ? "text-green-400" : g < 0 ? "text-red-400" : "text-gray-500"}`}>
                  {g == null ? "—" : g > 0 ? `+${g}` : g}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
      </div>
    </div>
  );
}

// ── Employee Summary: Summary per Month — headcount by dept, end-of-month
// snapshot (format reference: SUMMARY sheet, "Monthly" block) ─────────────
function EmployeeMonthSummaryTable({ year, onDrillDown }) {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsedDepts, setCollapsedDepts] = useState(() => new Set());
  const [collapsedDivisions, setCollapsedDivisions] = useState(() => new Set());

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/summary/by-month?year=${year}`, { headers })
      .then((r) => r.ok ? r.json() : null)
      .then(setD)
      .finally(() => setLoading(false));
  }, [year]); // eslint-disable-line

  const toggleSet = (setFn) => (key) => setFn((prev) => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });
  const toggleDept = toggleSet(setCollapsedDepts);
  const toggleDivision = toggleSet(setCollapsedDivisions);
  const divKey = (dept, division) => `${dept}::${division}`;

  const visibleRows = d ? d.rows.filter((row) => {
    if (collapsedDepts.has(row.department)) return row.division == null && row.team == null; // dept row itself always shows
    if (row.division && row.team && collapsedDivisions.has(divKey(row.department, row.division))) return false;
    return true;
  }) : [];

  const TH = "px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap text-center border-b border-gray-800";
  const TD = "px-3 py-2 text-xs text-right whitespace-nowrap";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">Monthly Summary · {year}</h3>
        <p className="text-[10px] text-gray-600">Click + to expand a department's teams · click a value to view that exact list of employees</p>
      </div>

      {loading ? (
        <div className="py-16 text-center"><Loader2 size={16} className="mx-auto animate-spin text-gray-600" /></div>
      ) : !d ? (
        <div className="py-16 text-center text-xs text-gray-600">Failed to load</div>
      ) : (
        <div className="overflow-auto rounded-lg border border-gray-800" style={{ maxHeight: 480 }}>
          <table className="w-full text-sm" style={{ minWidth: 900 }}>
            <thead className="sticky top-0 z-10 bg-gray-800">
              <tr>
                <th className={`${TH} text-left sticky left-0 bg-gray-800 z-20`}>Department / Division / Team</th>
                {d.months.map((m) => <th key={m} className={TH}>{MONTHS_ID[m - 1]}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {visibleRows.map((row) => {
                const level = row.team ? 2 : row.division ? 1 : 0;
                const hasChildren = level === 0
                  ? d.rows.some((r) => r.department === row.department && (r.division || r.team))
                  : level === 1
                    ? d.rows.some((r) => r.department === row.department && r.division === row.division && r.team)
                    : false;
                const toggleKey = level === 0 ? row.department : divKey(row.department, row.division);
                const isOpen = hasChildren && !(level === 0 ? collapsedDepts : collapsedDivisions).has(toggleKey);
                const label = row.team || row.division || row.department;
                const pad = level === 0 ? "" : level === 1 ? "pl-6" : "pl-9";
                const rowClass = level === 0 ? "bg-gray-800/30 font-semibold" : level === 1 ? "bg-gray-900/40 font-medium hover:bg-gray-800/30" : "hover:bg-gray-800/30";
                return (
                <tr key={`${row.department}-${row.division || ""}-${row.team || ""}`} className={rowClass}>
                  <td
                    onClick={hasChildren ? () => (level === 0 ? toggleDept(toggleKey) : toggleDivision(toggleKey)) : undefined}
                    className={`px-3 py-2 text-xs whitespace-nowrap sticky left-0 ${pad} ${level === 2 ? "text-gray-400 bg-gray-900" : level === 1 ? "text-gray-300 bg-gray-900/40" : "text-gray-200 bg-gray-800/30"} ${hasChildren ? "cursor-pointer select-none hover:text-indigo-300" : ""}`}
                    title={hasChildren && level === 0 ? (isOpen ? "Collapse team list" : "Expand team list") : undefined}
                  >
                    {hasChildren && (
                      level === 0
                        ? (isOpen
                            ? <Minus size={11} className="inline mr-1 -mt-0.5 text-indigo-400" />
                            : <Plus size={11} className="inline mr-1 -mt-0.5 text-indigo-400" />)
                        : (isOpen
                            ? <ChevronDown size={11} className="inline mr-1 -mt-0.5" />
                            : <ChevronRight size={11} className="inline mr-1 -mt-0.5" />)
                    )}
                    {label}
                  </td>
                  {d.months.map((m) => {
                    const val = row.by_month[m];
                    const clickable = onDrillDown && val != null;
                    return (
                      <td
                        key={m}
                        onClick={clickable ? () => onDrillDown(row.department, row.division, row.team, m, year) : undefined}
                        className={`${TD} ${level === 0 ? "text-gray-200" : "text-gray-400"} ${clickable ? "cursor-pointer hover:bg-indigo-500/20 hover:text-indigo-300" : ""}`}
                        title={clickable ? `View the ${val} employee(s) behind this number` : val == null ? "Month not reached yet" : undefined}
                      >
                        {val ?? "—"}
                      </td>
                    );
                  })}
                </tr>
                );
              })}
              <tr className="bg-gray-800/60 font-bold">
                <td className="px-3 py-2 text-xs text-gray-200 whitespace-nowrap sticky left-0 bg-gray-800/60">GRAND TOTAL</td>
                {d.months.map((m) => (
                  <td key={m} className={`${TD} text-indigo-300`}>{d.total[m] ?? "—"}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
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
  const headers = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();

  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg]   = useState("");
  const [RC, setRC] = useState(null);

  const [yearFilter, setYearFilter] = useState(curYear);
  const [monthFilter, setMonthFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [departments, setDepartments] = useState([]);
  const [teams, setTeams] = useState([]);

  const fetchTeams = useCallback(async (dept) => {
    try {
      const url = dept ? `${API}/teams?department=${encodeURIComponent(dept)}` : `${API}/teams`;
      const res = await fetch(url, { headers });
      if (res.ok) setTeams(await res.json());
    } catch (_) {}
  }, []); // eslint-disable-line

  useEffect(() => {
    fetch(`${API}/departments`, { headers }).then((r) => r.ok ? r.json() : []).then(setDepartments).catch(() => {});
    fetchTeams("");
  }, []); // eslint-disable-line

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      year: yearFilter,
      ...(monthFilter ? { month: monthFilter } : {}),
      ...(deptFilter ? { department: deptFilter } : {}),
      ...(teamFilter ? { team: teamFilter } : {}),
    });
    fetch(`/api/v1/dashboard/hr/employees/turnover-summary?${params}`, { headers })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body?.detail ?? `HTTP ${r.status}`);
        return body;
      })
      .then((d) => setData(d))
      .catch((e) => setErrMsg(e.message || "Network error"))
      .finally(() => setLoading(false));
  }, [yearFilter, monthFilter, deptFilter, teamFilter]); // eslint-disable-line

  useEffect(() => {
    import("recharts").then((mod) => setRC(mod)).catch(() => {});
  }, []);

  const filterBar = (
    <div className="flex flex-wrap items-end gap-2">
      <div className="w-28">
        <label className="mb-1 block text-[10px] font-medium text-gray-500">Year</label>
        <select value={yearFilter} onChange={(e) => setYearFilter(Number(e.target.value))}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer">
          {[curYear, curYear - 1, curYear - 2, curYear - 3, curYear - 4].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      <div className="w-28">
        <label className="mb-1 block text-[10px] font-medium text-gray-500">Month</label>
        <select value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer">
          <option value="">All</option>
          {MONTHS_ID.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
      <div className="w-32">
        <label className="mb-1 block text-[10px] font-medium text-gray-500">Department</label>
        <select value={deptFilter} onChange={(e) => { setDeptFilter(e.target.value); setTeamFilter(""); fetchTeams(e.target.value); }}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer">
          <option value="">All</option>
          {departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <div className="w-32">
        <label className="mb-1 block text-[10px] font-medium text-gray-500">Team</label>
        <select value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 cursor-pointer">
          <option value="">All</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
    </div>
  );

  if (loading) return <div className="space-y-3 mt-2">{filterBar}<div className="py-16 text-center"><Loader2 size={20} className="mx-auto animate-spin text-gray-300" /></div></div>;
  if (errMsg || !data) return (
    <div className="space-y-3 mt-2">
      {filterBar}
      <div className="py-10 text-center space-y-2">
        <p className="text-xs text-red-400 font-semibold">Failed to load turnover report</p>
        {errMsg && <pre className="text-xs text-gray-300 max-w-xl mx-auto whitespace-pre-wrap text-left bg-gray-900 rounded p-3">{errMsg}</pre>}
      </div>
    </div>
  );

  const {
    resign_trend = [], annual_turnover_rate = 0, total_resigns_period = 0,
    avg_tenure_years = 0, current_headcount = 0,
    by_dept = [], by_level = [], by_status = [], year = curYear, month = null,
  } = data;

  const CHART_H = 200;
  const periodLabel = month ? `${MONTHS_ID[month - 1]} ${year}` : `${year}`;

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
      {filterBar}

      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: `Turnover Rate (${year})`,      val: `${annual_turnover_rate}%`, sub: "annualized",              color: "#fb7185" },
          { label: `Total Resigned (${periodLabel})`, val: total_resigns_period,     sub: "employees left",          color: "#fbbf24" },
          { label: "Avg. Tenure",                  val: `${avg_tenure_years} yrs`,  sub: "of resigned employees",   color: "#818cf8" },
          { label: "Current Headcount",            val: current_headcount,          sub: "active employees",        color: "#34d399" },
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
          <SummaryChartCard title={`Resign & Turnover Rate Trend (Jan–Dec ${year})`}>
            <RC.ResponsiveContainer width="100%" height={CHART_H}>
              <RC.ComposedChart data={resign_trend} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
                <RC.XAxis dataKey="label" tick={tickStyle} />
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
            <SummaryChartCard title={`Resigned by Department (${periodLabel})`}>
              <SummaryHBarList items={by_dept} max={deptMax} />
            </SummaryChartCard>
            <SummaryChartCard title={`Resigned by Job Level (${periodLabel})`}>
              <SummaryHBarList items={by_level} max={levelMax} />
            </SummaryChartCard>
            <SummaryChartCard title={`Resigned by Employee Status (${periodLabel})`}>
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
  const NUMERIC = ["employees", "plan", "actual", "rate", "late", "late_rate", "sick", "sick_rate", "leave", "leave_rate"];
  const thCls = "px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700";
  // Late/Sick/Leave are all "lower is better" — unlike the attendance Rate
  // column, so the color thresholds run the opposite direction.
  const badRateColor = (r) => r <= 5 ? "text-green-400" : r <= 15 ? "text-amber-400" : "text-red-400";
  const badRateColorTot = (r) => r <= 5 ? "text-green-300" : r <= 15 ? "text-amber-300" : "text-red-300";
  const badRateColorGrand = (r) => r <= 5 ? "text-green-200" : r <= 15 ? "text-amber-200" : "text-red-200";

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
            <SortableTH label="Late"        field="late_rate"  sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
            <SortableTH label="Sick"        field="sick_rate"  sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
            <SortableTH label="Leave"       field="leave_rate" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} align="center" className={thCls} />
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
                <td className={`px-3 py-2 text-center border border-gray-700 ${badRateColor(team.late_rate)}`}>
                  {team.late} <span className="text-gray-600">({team.late_rate}%)</span>
                </td>
                <td className={`px-3 py-2 text-center border border-gray-700 ${badRateColor(team.sick_rate)}`}>
                  {team.sick} <span className="text-gray-600">({team.sick_rate}%)</span>
                </td>
                <td className={`px-3 py-2 text-center border border-gray-700 ${badRateColor(team.leave_rate)}`}>
                  {team.leave} <span className="text-gray-600">({team.leave_rate}%)</span>
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
              <td className={`px-3 py-2 text-center font-bold border border-gray-600 ${badRateColorTot(dept.total.late_rate)}`}>
                {dept.total.late} <span className="text-gray-500">({dept.total.late_rate}%)</span>
              </td>
              <td className={`px-3 py-2 text-center font-bold border border-gray-600 ${badRateColorTot(dept.total.sick_rate)}`}>
                {dept.total.sick} <span className="text-gray-500">({dept.total.sick_rate}%)</span>
              </td>
              <td className={`px-3 py-2 text-center font-bold border border-gray-600 ${badRateColorTot(dept.total.leave_rate)}`}>
                {dept.total.leave} <span className="text-gray-500">({dept.total.leave_rate}%)</span>
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
            <td className={`px-3 py-2.5 text-center font-bold border border-gray-600 ${badRateColorGrand(grand_total.late_rate)}`}>
              {grand_total.late} <span className="text-gray-400">({grand_total.late_rate}%)</span>
            </td>
            <td className={`px-3 py-2.5 text-center font-bold border border-gray-600 ${badRateColorGrand(grand_total.sick_rate)}`}>
              {grand_total.sick} <span className="text-gray-400">({grand_total.sick_rate}%)</span>
            </td>
            <td className={`px-3 py-2.5 text-center font-bold border border-gray-600 ${badRateColorGrand(grand_total.leave_rate)}`}>
              {grand_total.leave} <span className="text-gray-400">({grand_total.leave_rate}%)</span>
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

  const curYear = new Date().getFullYear();
  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [issuesData,  setIssuesData]  = useState(null);
  const [innerTab,    setInnerTab]    = useState("today");
  const [teamData,    setTeamData]    = useState(null);
  const [teamYear,    setTeamYear]    = useState(curYear);
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

  // Monthly Summary — per-employee Late/Sick Leave/Unpaid Leave for a
  // whole month (the monthly companion to the day-scoped table above).
  const curMonth = new Date().getMonth() + 1;
  const [monthlyData,   setMonthlyData]   = useState(null);
  const [loadingMonthly, setLoadingMonthly] = useState(false);
  const [monthlyMonth,  setMonthlyMonth]  = useState(curMonth);
  const [monthlyYear,   setMonthlyYear]   = useState(curYear);
  const [monthlyDept,   setMonthlyDept]   = useState("");
  const [monthlyDepts,  setMonthlyDepts]  = useState([]);

  useEffect(() => {
    fetch(`${ATT_API}/departments`, { headers }).then(r => r.ok ? r.json() : []).then(setMonthlyDepts).catch(() => {});
  }, []); // eslint-disable-line

  const fetchMonthlyData = async (month = monthlyMonth, year = monthlyYear, dept = monthlyDept) => {
    setLoadingMonthly(true);
    try {
      const params = new URLSearchParams({ month, year });
      if (dept) params.set("department", dept);
      const res = await fetch(`${ATT_API}/monthly-employee-summary?${params}`, { headers });
      if (res.ok) setMonthlyData(await res.json());
    } catch (_) {}
    finally { setLoadingMonthly(false); }
  };

  // Yearly Summary — month-by-month (Jan-Dec) company-wide attendance
  // report, the annual companion to Monthly Summary's per-employee view.
  const [yearlyData,    setYearlyData]    = useState(null);
  const [loadingYearly, setLoadingYearly] = useState(false);
  const [yearlyYear,    setYearlyYear]    = useState(curYear);
  const [yearlyDept,    setYearlyDept]    = useState("");

  const fetchYearlyData = async (year = yearlyYear, dept = yearlyDept) => {
    setLoadingYearly(true);
    try {
      const params = new URLSearchParams({ year });
      if (dept) params.set("department", dept);
      const res = await fetch(`${ATT_API}/yearly-summary?${params}`, { headers });
      if (res.ok) setYearlyData(await res.json());
    } catch (_) {}
    finally { setLoadingYearly(false); }
  };

  // Employee lookup — search for one person and see just their status for
  // the selected date, independent of the Total/Present/Absent card drill-down.
  const [empQuery,        setEmpQuery]        = useState("");
  const [empSearchResults, setEmpSearchResults] = useState([]);
  const [empLookup,        setEmpLookup]        = useState(null);
  const [loadingLookup,    setLoadingLookup]     = useState(false);

  const fetchData = async (targetDate = selectedDate) => {
    setLoading(true);
    try {
      const params = targetDate ? `?target_date=${targetDate}` : "";
      const [res, issuesRes] = await Promise.all([
        fetch(`${ATT_API}/today${params}`, { headers }),
        fetch(`${ATT_API}/today/attendance-issues${params}`, { headers }),
      ]);
      if (res.ok) setData(await res.json());
      setIssuesData(issuesRes.ok ? await issuesRes.json() : null);
    } catch (_) {}
    finally { setLoading(false); }
  };

  const handleDateChange = (v) => {
    setSelectedDate(v);
    setActiveFilter(null); setEmployees([]);
    setEmpQuery(""); setEmpSearchResults([]); setEmpLookup(null);
    fetchData(v);
  };

  const doEmpSearch = async (q) => {
    setEmpQuery(q);
    if (q.length < 2) { setEmpSearchResults([]); return; }
    try {
      const res = await fetch(`${ATT_API}/search-employees?q=${encodeURIComponent(q)}`, { headers });
      if (res.ok) setEmpSearchResults(await res.json());
    } catch (_) {}
  };

  const selectEmpLookup = async (emp) => {
    setEmpSearchResults([]); setEmpQuery(emp.name || emp.id); setLoadingLookup(true);
    try {
      const params = new URLSearchParams({ filter: "all" });
      if (data?.actual_date) params.append("target_date", data.actual_date);
      const res = await fetch(`${ATT_API}/today/employees?${params}`, { headers });
      if (res.ok) {
        const r = await res.json();
        const found = (r.employees || []).find((e) => e.id === emp.id);
        setEmpLookup(found || { id: emp.id, name: emp.name, department: emp.department, checkin: null, checkout: null, notes: "No record for this date" });
      }
    } catch (_) {}
    setLoadingLookup(false);
  };

  const clearEmpLookup = () => { setEmpQuery(""); setEmpSearchResults([]); setEmpLookup(null); };

  const fetchTeamData = async (y = teamYear) => {
    setLoadingTeam(true);
    try {
      const res = await fetch(`${ATT_API}/dept-team-summary?year=${y}`, { headers });
      if (res.ok) setTeamData(await res.json());
    } catch (_) {}
    finally { setLoadingTeam(false); }
  };

  const handleTeamYearChange = (y) => {
    setTeamYear(y);
    fetchTeamData(y);
  };

  const switchTab = (tab) => {
    setInnerTab(tab);
    if (tab === "team" && !teamData) fetchTeamData();
    if (tab === "monthly" && !monthlyData) fetchMonthlyData();
    if (tab === "yearly" && !yearlyData) fetchYearlyData();
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
        {[["today", "Attendance Today"], ["team", "Team Summary"], ["monthly", "Monthly Summary"], ["yearly", "Yearly Summary"]].map(([id, label]) => (
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
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  value={empQuery}
                  onChange={(e) => doEmpSearch(e.target.value)}
                  placeholder="Find employee..."
                  className="w-48 rounded-lg border border-gray-700 bg-gray-900 pl-7 pr-2.5 py-1.5 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-green-500 transition-colors"
                />
                {empQuery && (
                  <button onClick={clearEmpLookup} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400">
                    <X size={12} />
                  </button>
                )}
                {empSearchResults.length > 0 && (
                  <div className="absolute top-full left-0 right-0 z-20 mt-1 max-h-48 overflow-y-auto rounded-lg border border-gray-700 bg-gray-900 shadow-2xl">
                    {empSearchResults.map((r) => (
                      <button key={r.id} onClick={() => selectEmpLookup(r)}
                        className="block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-800 transition-colors">
                        <div className="font-medium text-gray-200">{r.name}</div>
                        <div className="text-gray-500">{r.id} · {r.department || "—"}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => fetchData()} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </div>

          {(loadingLookup || empLookup) && (
            <div className="rounded-lg border border-green-800/40 bg-green-900/10 px-4 py-3">
              {loadingLookup ? (
                <div className="flex justify-center"><Loader2 size={14} className="animate-spin text-gray-600" /></div>
              ) : (
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <div className="text-sm font-semibold text-gray-200">{empLookup.name || empLookup.id}</div>
                    <div className="text-xs text-gray-500">{empLookup.id} · {empLookup.department || "—"}</div>
                  </div>
                  <div className="flex items-center gap-4 text-xs">
                    <span>Check-In: <span className={`font-mono font-semibold ${empLookup.checkin ? "text-green-400" : "text-red-400"}`}>{empLookup.checkin || "—"}</span></span>
                    <span>Check-Out: <span className="font-mono text-gray-400">{empLookup.checkout || "—"}</span></span>
                    <span>Notes: <span className="text-gray-400">{empLookup.notes || "—"}</span></span>
                  </div>
                  <button onClick={clearEmpLookup} className="text-gray-600 hover:text-gray-400">
                    <X size={13} />
                  </button>
                </div>
              )}
            </div>
          )}

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

                {/* Table per employee — Late / Sick Leave / Unpaid Leave for
                    the selected date (replaces the old per-department
                    Total/Present/Absent/Rate table, which only ever showed
                    Administration and Plant). Only employees with at least
                    one issue that day are listed, same convention as
                    Who's Off. */}
                <div className="overflow-x-auto rounded-lg border border-gray-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-800/60">
                        <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Name</th>
                        <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Department</th>
                        <th colSpan={4} className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider text-center border-b border-gray-700">Attendance</th>
                        <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">%</th>
                      </tr>
                      <tr className="bg-gray-800/60">
                        <SortableTH label="Late"          field="late"   sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} align="center" />
                        <SortableTH label="Sick Leave"    field="sick"   sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} align="center" />
                        <SortableTH label="Unpaid Leave"  field="unpaid" sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} align="center" />
                        <SortableTH label="Total"         field="total"  sortBy={deptSortBy} sortDir={deptSortDir} onSort={handleDeptSort} align="center" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {!issuesData?.data?.length ? (
                        <tr><td colSpan={7} className="py-10 text-center text-xs text-gray-600">No Late / Sick Leave / Unpaid Leave records for this date</td></tr>
                      ) : sortRows(issuesData.data, deptSortBy, deptSortDir, ["late", "sick", "unpaid", "total", "rate"]).map((row) => (
                        <tr key={row.id} className="hover:bg-gray-800/40 transition-colors">
                          <td className="px-3 py-2.5 font-medium text-gray-200 whitespace-nowrap">{row.name}</td>
                          <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{row.department}</td>
                          <td className="px-3 py-2.5 text-center text-amber-400 font-semibold">{row.late || "-"}</td>
                          <td className="px-3 py-2.5 text-center text-red-400 font-semibold">{row.sick || "-"}</td>
                          <td className="px-3 py-2.5 text-center text-purple-400 font-semibold">{row.unpaid || "-"}</td>
                          <td className="px-3 py-2.5 text-center text-gray-200 font-bold">{row.total}</td>
                          <td className="px-3 py-2.5 text-center text-gray-400">{row.rate}%</td>
                        </tr>
                      ))}
                    </tbody>
                    {issuesData?.data?.length > 0 && (
                      <tfoot>
                        <tr className="bg-gray-800/80 font-bold">
                          <td className="px-3 py-2.5 text-gray-300" colSpan={2}>TOTAL</td>
                          <td className="px-3 py-2.5 text-center text-amber-400">{issuesData.totals.late}</td>
                          <td className="px-3 py-2.5 text-center text-red-400">{issuesData.totals.sick}</td>
                          <td className="px-3 py-2.5 text-center text-purple-400">{issuesData.totals.unpaid}</td>
                          <td className="px-3 py-2.5 text-center text-gray-200">{issuesData.totals.total}</td>
                          <td className="px-3 py-2.5 text-center text-gray-300">{issuesData.totals.rate}%</td>
                        </tr>
                      </tfoot>
                    )}
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
            <p className="text-xs text-gray-500">Attendance summary per department & team — Year {teamYear}</p>
            <div className="flex items-center gap-2">
              <select value={teamYear} onChange={(e) => handleTeamYearChange(Number(e.target.value))}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                {[curYear, curYear - 1, curYear - 2].map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <button onClick={() => fetchTeamData()}
                className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                <RefreshCw size={11} className={loadingTeam ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </div>
          {loadingTeam && <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>}
          {!loadingTeam && teamData && <DeptTeamTable data={teamData} />}
          {!loadingTeam && !teamData && (
            <p className="py-10 text-center text-xs text-gray-600">No data yet.</p>
          )}
        </div>
      )}

      {/* ── Tab: Monthly Summary — per-employee Late/Sick Leave/Unpaid
          Leave for a whole month, the monthly companion to the day-scoped
          table under "Attendance Today". Dept/Team columns render as
          merged cells (Excel-style) since rows arrive pre-sorted by
          department/team/name — sorting by another column would break
          that grouping, so this table intentionally isn't sortable. ── */}
      {innerTab === "monthly" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs text-gray-500">
              Per-employee Late / Sick Leave / Unpaid Leave — {MONTHS_ID[monthlyMonth - 1]} {monthlyYear}
            </p>
            <div className="flex items-center gap-2">
              <select value={monthlyDept} onChange={(e) => { setMonthlyDept(e.target.value); fetchMonthlyData(monthlyMonth, monthlyYear, e.target.value); }}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                <option value="">All Departments</option>
                {monthlyDepts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <select value={monthlyMonth} onChange={(e) => { const m = Number(e.target.value); setMonthlyMonth(m); fetchMonthlyData(m, monthlyYear, monthlyDept); }}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                {MONTHS_ID.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
              </select>
              <select value={monthlyYear} onChange={(e) => { const y = Number(e.target.value); setMonthlyYear(y); fetchMonthlyData(monthlyMonth, y, monthlyDept); }}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                {[curYear, curYear - 1, curYear - 2].map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <button onClick={() => fetchMonthlyData()}
                className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                <RefreshCw size={11} className={loadingMonthly ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </div>

          {loadingMonthly ? (
            <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>
          ) : !monthlyData?.data?.length ? (
            <p className="py-10 text-center text-xs text-gray-600">No attendance data for this month.</p>
          ) : (() => {
            const rows = monthlyData.data;
            const deptSpan = new Array(rows.length).fill(0);
            const teamSpan = new Array(rows.length).fill(0);
            for (let i = 0; i < rows.length; ) {
              let j = i + 1;
              while (j < rows.length && rows[j].department === rows[i].department) j++;
              deptSpan[i] = j - i;
              i = j;
            }
            for (let i = 0; i < rows.length; ) {
              let j = i + 1;
              while (j < rows.length && rows[j].department === rows[i].department && rows[j].team === rows[i].team) j++;
              teamSpan[i] = j - i;
              i = j;
            }
            const t = monthlyData.totals;
            return (
              <div className="overflow-x-auto rounded-lg border border-gray-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-800/60">
                      <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Dept</th>
                      <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Team</th>
                      <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Name</th>
                      <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Working Days</th>
                      <th colSpan={4} className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider text-center border-b border-gray-700">Attendance</th>
                      <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">%</th>
                    </tr>
                    <tr className="bg-gray-800/60">
                      <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Late</th>
                      <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Sick Leave</th>
                      <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Unpaid Leave</th>
                      <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {rows.map((row, i) => (
                      <tr key={row.employee_id || i} className="hover:bg-gray-800/40 transition-colors">
                        {deptSpan[i] > 0 && <td rowSpan={deptSpan[i]} className="px-3 py-2.5 font-medium text-gray-200 align-top whitespace-nowrap border-r border-gray-800/60">{row.department}</td>}
                        {teamSpan[i] > 0 && <td rowSpan={teamSpan[i]} className="px-3 py-2.5 text-gray-300 align-top whitespace-nowrap border-r border-gray-800/60">{row.team}</td>}
                        <td className="px-3 py-2.5 text-gray-200 whitespace-nowrap">{row.name}</td>
                        <td className="px-3 py-2.5 text-center text-gray-400">{row.working_days}</td>
                        <td className="px-3 py-2.5 text-center text-amber-400 font-semibold">{row.late || "-"}</td>
                        <td className="px-3 py-2.5 text-center text-red-400 font-semibold">{row.sick || "-"}</td>
                        <td className="px-3 py-2.5 text-center text-purple-400 font-semibold">{row.unpaid || "-"}</td>
                        <td className="px-3 py-2.5 text-center text-gray-200 font-bold">{row.total}</td>
                        <td className="px-3 py-2.5 text-center text-gray-400">{row.rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-gray-800/80 font-bold">
                      <td className="px-3 py-2.5 text-gray-300" colSpan={3}>TOTAL</td>
                      <td className="px-3 py-2.5 text-center text-gray-300">{t.working_days}</td>
                      <td className="px-3 py-2.5 text-center text-amber-400">{t.late}</td>
                      <td className="px-3 py-2.5 text-center text-red-400">{t.sick}</td>
                      <td className="px-3 py-2.5 text-center text-purple-400">{t.unpaid}</td>
                      <td className="px-3 py-2.5 text-center text-gray-200">{t.total}</td>
                      <td className="px-3 py-2.5 text-center text-gray-300">{t.rate}%</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            );
          })()}
        </div>
      )}

      {/* ── Tab: Yearly Summary — month-by-month (Jan-Dec), company-wide
          report. Reverse-engineered/verified against the user's reference
          screenshot: Expected Man-Days = Total Employees x Working Days,
          Present Man-Days = Expected - (Late+Sick+Unpaid). ── */}
      {innerTab === "yearly" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs text-gray-500">
              {(() => {
                const withData = (yearlyData?.months || []).filter(m => m.total_employees > 0);
                const range = withData.length
                  ? `${withData[0].month_label.slice(0, 3).toUpperCase()}-${withData[withData.length - 1].month_label.slice(0, 3).toUpperCase()}`
                  : "";
                return `SUMMARY REPORT ATTENDANCE ${range ? range + " " : ""}${yearlyYear}`;
              })()}
            </p>
            <div className="flex items-center gap-2">
              <select value={yearlyDept} onChange={(e) => { setYearlyDept(e.target.value); fetchYearlyData(yearlyYear, e.target.value); }}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                <option value="">All Departments</option>
                {monthlyDepts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <select value={yearlyYear} onChange={(e) => { const y = Number(e.target.value); setYearlyYear(y); fetchYearlyData(y, yearlyDept); }}
                className="rounded-lg border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-green-500 cursor-pointer">
                {[curYear, curYear - 1, curYear - 2].map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <button onClick={() => fetchYearlyData()}
                className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                <RefreshCw size={11} className={loadingYearly ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </div>

          {loadingYearly ? (
            <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>
          ) : !yearlyData ? (
            <p className="py-10 text-center text-xs text-gray-600">No data yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-800/60">
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left align-bottom whitespace-nowrap">Month</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Total Employees</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Working Days</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Expected Man-Days</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Present Man-Days</th>
                    <th colSpan={4} className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider text-center border-b border-gray-700">Attendance</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Attendance Ratio</th>
                    <th rowSpan={2} className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center align-bottom whitespace-nowrap">Absence Ratio</th>
                  </tr>
                  <tr className="bg-gray-800/60">
                    <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Late</th>
                    <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Sick</th>
                    <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Unpaid</th>
                    <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center whitespace-nowrap">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {yearlyData.months.map((m) => (
                    <tr key={m.month} className="hover:bg-gray-800/40 transition-colors">
                      <td className="px-3 py-2.5 font-medium text-gray-200 whitespace-nowrap">{m.month_label}</td>
                      <td className="px-3 py-2.5 text-center text-gray-400">{m.total_employees || "—"}</td>
                      <td className="px-3 py-2.5 text-center text-gray-400">{m.working_days || "—"}</td>
                      <td className="px-3 py-2.5 text-center text-gray-400">{m.expected_man_days || "—"}</td>
                      <td className="px-3 py-2.5 text-center text-gray-400">{m.present_man_days || "—"}</td>
                      <td className="px-3 py-2.5 text-center text-amber-400 font-semibold">{m.late || "-"}</td>
                      <td className="px-3 py-2.5 text-center text-red-400 font-semibold">{m.sick || "-"}</td>
                      <td className="px-3 py-2.5 text-center text-purple-400 font-semibold">{m.unpaid || "-"}</td>
                      <td className="px-3 py-2.5 text-center text-gray-200 font-bold">{m.total || "-"}</td>
                      <td className={`px-3 py-2.5 text-center font-semibold ${m.attendance_ratio == null ? "text-gray-600" : m.attendance_ratio >= 95 ? "text-green-400" : "text-amber-400"}`}>
                        {m.attendance_ratio == null ? "—" : `${m.attendance_ratio}%`}
                      </td>
                      <td className="px-3 py-2.5 text-center text-gray-400">
                        {m.absence_ratio == null ? "—" : `${m.absence_ratio}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800/80 font-bold">
                    <td className="px-3 py-2.5 text-gray-300">TOTAL (ANNUAL)</td>
                    <td className="px-3 py-2.5 text-center text-gray-300">{yearlyData.annual.total_employees}</td>
                    <td className="px-3 py-2.5 text-center text-gray-300">{yearlyData.annual.working_days}</td>
                    <td className="px-3 py-2.5 text-center text-gray-300">{yearlyData.annual.expected_man_days}</td>
                    <td className="px-3 py-2.5 text-center text-gray-300">{yearlyData.annual.present_man_days}</td>
                    <td className="px-3 py-2.5 text-center text-amber-400">{yearlyData.annual.late}</td>
                    <td className="px-3 py-2.5 text-center text-red-400">{yearlyData.annual.sick}</td>
                    <td className="px-3 py-2.5 text-center text-purple-400">{yearlyData.annual.unpaid}</td>
                    <td className="px-3 py-2.5 text-center text-gray-200">{yearlyData.annual.total}</td>
                    <td className="px-3 py-2.5 text-center text-green-400">
                      {yearlyData.annual.attendance_ratio == null ? "—" : `${yearlyData.annual.attendance_ratio}%`}
                    </td>
                    <td className="px-3 py-2.5 text-center text-gray-300">
                      {yearlyData.annual.absence_ratio == null ? "—" : `${yearlyData.annual.absence_ratio}%`}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sub-komponen untuk Attendance Ratio ───────────────────────────────────────

const NEU_CARD = {
  background: "#f1f5f9",
  borderRadius: 16,
  boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  padding: 16,
};
const NEU_IN = { background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)" };

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
                    <div style={{ width: "100%", height: planH, background: "linear-gradient(180deg, #60a5fa, #3b82f6)", borderRadius: "6px 6px 0 0", boxShadow: "0 1px 2px rgba(15,23,42,0.08)" }} />
                  </div>
                  <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "#ea580c", fontWeight: 700 }}>{dept.actual}</span>
                    <div style={{ width: "100%", height: actualH, background: "linear-gradient(180deg, #fb923c, #f97316)", borderRadius: "6px 6px 0 0", boxShadow: "0 1px 2px rgba(15,23,42,0.08)" }} />
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
                boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
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
                  <div style={{ width: "100%", height: planH, background: "linear-gradient(180deg, #60a5fa, #3b82f6)", borderRadius: "5px 5px 0 0", boxShadow: "0 1px 2px rgba(15,23,42,0.08)" }} />
                </div>
                <div style={{ width: "40%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "#ea580c", fontWeight: 700 }}>{m.actual}</span>
                  <div style={{ width: "100%", height: actualH, background: "linear-gradient(180deg, #fb923c, #f97316)", borderRadius: "5px 5px 0 0", boxShadow: "0 1px 2px rgba(15,23,42,0.08)" }} />
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
  const curYear = new Date().getFullYear();
  const { user } = useAuthStore();
  const [query,   setQuery]   = useState(user?.fullName || "");
  const [results, setResults] = useState([]);
  const [detail,  setDetail]  = useState(null);
  const [selected, setSelected] = useState(null);
  const [year,    setYear]    = useState(curYear);
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

  const loadDetail = async (emp, forYear) => {
    setResults([]); setQuery(emp.name || emp.id); setSelected(emp); setLoading(true);
    try {
      const res = await fetch(`${apiBase}/employee/${emp.id}/detail?year=${forYear ?? year}`, { headers });
      if (res.ok) setDetail(await res.json());
    } catch (_) {}
    setLoading(false);
  };

  // Default the search to the logged-in HR user's own name so Detail opens
  // with something useful already loaded, instead of an empty prompt.
  useEffect(() => {
    if (!user?.fullName) return;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/search-employees?q=${encodeURIComponent(user.fullName)}`, { headers });
        if (res.ok) {
          const matches = await res.json();
          if (matches.length > 0) loadDetail(matches[0]);
        }
      } catch (_) {}
    })();
  }, []); // eslint-disable-line

  const handleYearChange = (y) => {
    setYear(y);
    if (selected) loadDetail(selected, y);
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
              color: "#1e293b", background: "#f1f5f9",
              boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
              outline: "none", boxSizing: "border-box",
            }}
          />
          {results.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, marginTop: 4,
              borderRadius: 12, background: "#fff", boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
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

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Year</label>
          <select value={year} onChange={e => handleYearChange(Number(e.target.value))}
            style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
            {[curYear, curYear - 1, curYear - 2, curYear - 3].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
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
                  padding: "8px 12px", borderRadius: 12, background: "#f1f5f9",
                  boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
                }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{val || "—"}</p>
                </div>
              ))}
            </div>

            <div>
              <h4 style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>Absence Records</h4>
              <div style={{ maxHeight: 200, overflowY: "auto", borderRadius: 12, boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)" }}>
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
                      <tr key={i} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}>
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

      {/* Right: monthly chart — always scoped to the selected Year */}
      <div>
        {detail?.monthly?.length > 0
          ? (
            <>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                Year {year} Monthly Rate
              </p>
              <MiniBarChart data={detail.monthly} />
            </>
          )
          : (
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "center", height: 200,
              borderRadius: 16, background: "#f1f5f9",
              boxShadow: "inset 0 2px 5px rgba(15,23,42,0.09)",
            }}>
              <p style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>Monthly chart will appear after selecting an employee</p>
            </div>
          )
        }
      </div>
    </div>
  );
}

// ── Manual data correction ─────────────────────────────────────────────────────
// Browses AttendanceRecord (the same master table every upload writes to)
// and lets HR fix a wrong value or add a day that was never covered by any
// upload at all. A later Excel upload for the same employee+date can still
// overwrite whatever is set here — there's no lock — but every manual change
// is logged and viewable via "History" in the edit modal.
function AttendanceCorrectionSection({ departments }) {
  const [filters, setFilters] = useState({ employee_id: "", department: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ records: [], total: 0, pages: 1 });
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = { page, page_size: 25 };
      if (filters.employee_id) p.employee_id = filters.employee_id;
      if (filters.department)  p.department = filters.department;
      if (filters.date_from)   p.date_from = filters.date_from;
      if (filters.date_to)     p.date_to = filters.date_to;
      const res = await hrApi.getAttendance(p);
      setData(res);
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, filters]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleFilter = (k, v) => { setFilters(p => ({ ...p, [k]: v })); setPage(1); };

  const sourceBadge = (source) => (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
      source === "manual" ? "bg-amber-500/15 text-amber-400" : "bg-gray-700/50 text-gray-400"
    }`}>
      {source || "—"}
    </span>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Employee ID</label>
          <input value={filters.employee_id} onChange={e => handleFilter("employee_id", e.target.value)}
            placeholder="e.g. P24019"
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5 w-32" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Department</label>
          <select value={filters.department} onChange={e => handleFilter("department", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {departments.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">From</label>
          <input type="date" value={filters.date_from} onChange={e => handleFilter("date_from", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">To</label>
          <input type="date" value={filters.date_to} onChange={e => handleFilter("date_to", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
        </div>
        {loading && <Loader2 size={14} className="animate-spin text-gray-500" />}
        <div className="flex-1" />
        <button onClick={() => setEditing({ employee_id: "", attendance_date: "", _isNew: true })}
          className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white">
          <Plus size={13} /> Manual Entry
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-800/60">
              {[["Date","attendance_date"],["Employee ID","employee_id"],["Name","employee_name"],["Department","department"],["Check In","actual_checkin"],["Check Out","actual_checkout"],["Status","attendance_status"],["Leave","leave_code"],["Source","source"]].map(([h, field]) => (
                <SortableTH key={h} label={h} field={field} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr><td colSpan={10} className="py-10 text-center"><Loader2 size={14} className="animate-spin inline mr-2 text-gray-500" />Loading...</td></tr>
            ) : data.records.length === 0 ? (
              <tr><td colSpan={10} className="py-10 text-center text-xs text-gray-600">No records match these filters.</td></tr>
            ) : sortRows(data.records, sortBy, sortDir, []).map((r) => (
              <tr key={r.id} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{r.attendance_date}</td>
                <td className="px-3 py-2 font-mono text-gray-500">{r.employee_id}</td>
                <td className="px-3 py-2 text-gray-200 whitespace-nowrap">{r.employee_name}</td>
                <td className="px-3 py-2 text-gray-400">{r.department || "—"}</td>
                <td className="px-3 py-2 text-gray-400">{r.actual_checkin || "—"}</td>
                <td className="px-3 py-2 text-gray-400">{r.actual_checkout || "—"}</td>
                <td className="px-3 py-2 text-gray-400">{r.attendance_status || "—"}</td>
                <td className="px-3 py-2 text-gray-400">{r.leave_code || "—"}</td>
                <td className="px-3 py-2">{sourceBadge(r.source)}</td>
                <td className="px-3 py-2">
                  <button onClick={() => setEditing(r)} title="Edit"
                    className="text-gray-500 hover:text-blue-400">
                    <Pencil size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.pages > 1 && (
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{data.total} records · page {page} of {data.pages}</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="px-2 py-1 rounded bg-gray-800 disabled:opacity-40">Prev</button>
            <button onClick={() => setPage(p => Math.min(data.pages, p + 1))} disabled={page === data.pages}
              className="px-2 py-1 rounded bg-gray-800 disabled:opacity-40">Next</button>
          </div>
        </div>
      )}

      {editing && (
        <AttendanceEditModal
          record={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchData(); }}
        />
      )}
    </div>
  );
}

function AttendanceEditModal({ record, onClose, onSaved }) {
  const isNew = !!record._isNew;
  const knownEmployee = isNew && !!record.employee_id;
  const [employeeId, setEmployeeId] = useState(record.employee_id || "");
  const [attDate, setAttDate] = useState(record.attendance_date || "");
  const [form, setForm] = useState({
    attendance_status: record.attendance_status || "",
    actual_checkin:    record.actual_checkin || "",
    actual_checkout:   record.actual_checkout || "",
    leave_code:        record.leave_code || "",
    is_day_off:        !!record.is_day_off,
    notes:             record.notes || "",
    reason:            "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (isNew) return;
    hrApi.getAttendanceDayHistory(employeeId, attDate).then(setHistory).catch(() => {});
  }, []); // eslint-disable-line

  const handleSave = async () => {
    if (!employeeId || !attDate) { setError("Employee ID and Date are required"); return; }
    setSaving(true); setError("");
    try {
      const body = {};
      if (form.attendance_status !== (record.attendance_status || "")) body.attendance_status = form.attendance_status || null;
      if (form.actual_checkin    !== (record.actual_checkin || ""))    body.actual_checkin    = form.actual_checkin || null;
      if (form.actual_checkout   !== (record.actual_checkout || ""))   body.actual_checkout   = form.actual_checkout || null;
      if (form.leave_code        !== (record.leave_code || ""))        body.leave_code        = form.leave_code || null;
      if (form.is_day_off        !== !!record.is_day_off)              body.is_day_off        = form.is_day_off;
      if (form.notes             !== (record.notes || ""))             body.notes             = form.notes || null;
      if (form.reason) body.reason = form.reason;

      if (Object.keys(body).filter(k => k !== "reason").length === 0) {
        setError("No changes to save");
        setSaving(false);
        return;
      }
      await hrApi.editAttendanceDay(employeeId, attDate, body);
      onSaved();
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
        style={{ background: "#111827", borderRadius: 16, padding: 20, width: 420, maxHeight: "85vh", overflowY: "auto", boxShadow: "0 10px 40px rgba(0,0,0,0.4)" }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-200">
            {knownEmployee ? `Add Leave — ${record.employee_name || employeeId}` : isNew ? "Manual Entry" : "Edit Attendance Day"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="space-y-3">
          {knownEmployee ? (
            <div>
              <label className="text-xs text-gray-500 block mb-1">Date</label>
              <input type="date" value={attDate} onChange={e => setAttDate(e.target.value)}
                className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
            </div>
          ) : isNew ? (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Employee ID</label>
                <input value={employeeId} onChange={e => setEmployeeId(e.target.value)}
                  className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Date</label>
                <input type="date" value={attDate} onChange={e => setAttDate(e.target.value)}
                  className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-400">{record.employee_name} ({employeeId}) — {attDate}</div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Attendance Status</label>
              <select value={form.attendance_status} onChange={e => setForm(f => ({ ...f, attendance_status: e.target.value }))}
                className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
                <option value="">—</option>
                <option value="W">W — Worked</option>
                <option value="L">L — Late</option>
                <option value="E">E — Early leave</option>
                <option value="LE">LE — Late+Early</option>
                <option value="A">A — Absent</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Leave Code</label>
              <select value={form.leave_code} onChange={e => setForm(f => ({ ...f, leave_code: e.target.value }))}
                className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
                <option value="">—</option>
                {LEAVE_CODES.map(c => <option key={c.code} value={c.code}>{c.code} — {c.label}</option>)}
                <option value="H">H — Holiday</option>
                <option value="EL">EL — Event Leave</option>
                <option value="HD">HD — Half Day Leave</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Check In</label>
              <input value={form.actual_checkin} onChange={e => setForm(f => ({ ...f, actual_checkin: e.target.value }))}
                placeholder="HH:MM" className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Check Out</label>
              <input value={form.actual_checkout} onChange={e => setForm(f => ({ ...f, actual_checkout: e.target.value }))}
                placeholder="HH:MM" className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input type="checkbox" checked={form.is_day_off} onChange={e => setForm(f => ({ ...f, is_day_off: e.target.checked }))} />
            Scheduled rest day (excluded from attendance rate)
          </label>

          <div>
            <label className="text-xs text-gray-500 block mb-1">Notes</label>
            <input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-1">Reason for this edit (optional, logged in history)</label>
            <input value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
              placeholder='e.g. "Surat izin sakit menyusul"'
              className="w-full text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5" />
          </div>

          {error && <div className="text-xs text-red-400">{error}</div>}

          <div className="flex items-center justify-between pt-1">
            <button onClick={handleSave} disabled={saving}
              className="text-xs font-semibold px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
              {saving ? "Saving..." : "Save"}
            </button>
            {!isNew && (
              <button onClick={() => setShowHistory(v => !v)}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300">
                <History size={13} /> History ({history.length})
              </button>
            )}
          </div>

          {showHistory && (
            <div className="mt-1 border-t border-gray-800 pt-2 space-y-1.5 max-h-40 overflow-y-auto">
              {history.length === 0 ? (
                <p className="text-xs text-gray-600">No manual edits yet</p>
              ) : history.map(h => (
                <div key={h.id} className="text-[11px] text-gray-500">
                  <span className="text-gray-300 font-semibold">{h.field}</span>: {h.old_value ?? "—"} → {h.new_value ?? "—"}
                  <div className="text-gray-600">{h.changed_by} · {h.changed_at?.replace("T", " ").slice(0, 16)}{h.reason ? ` · "${h.reason}"` : ""}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Data Coverage — moved to Setup > HRGA (src/pages/setup/HRSetupPage.jsx),
// 2026-08-19 user request. Was AttendanceCoverageSection here, rendered as
// the "Data Coverage" tab of Attendance Rate; that tab is gone from this
// page now, the component lives standalone in the new file instead.

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
          style={{ fontSize: 11, fontWeight: 700, padding: "5px 12px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#2563eb", boxShadow: NEU_IN.boxShadow, outline: "none", cursor: "pointer" }}>
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
                <tr key={m.period} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}>
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

// ── HikCentral integration — live poller status + manual "Sync Now" for the
// office's Hikvision DS-K1T342MFWX terminals (via HikCentral OpenAPI). The
// actual 15-minute poll runs server-side (hikcentral_scheduler.py); this
// panel just surfaces its status and lets HR force an immediate sync,
// alongside the file-upload sources it feeds the same reports as. ─────────
function HikCentralIntegration() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };
  const API = "/api/v1/dashboard/hr/attendance";

  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [error, setError] = useState("");

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/hikcentral/status`, { headers });
      if (res.ok) setStatus(await res.json());
    } catch (_) {}
    setLoading(false);
  };

  useEffect(() => { loadStatus(); }, []); // eslint-disable-line

  const handleSyncNow = async () => {
    setSyncing(true); setError(""); setSyncResult(null);
    try {
      const res = await fetch(`${API}/hikcentral/sync-now`, { method: "POST", headers });
      if (res.ok) {
        setSyncResult(await res.json());
        loadStatus();
      } else {
        const body = await res.json().catch(() => null);
        setError(body?.detail || `Sync failed (HTTP ${res.status})`);
      }
    } catch (e) {
      setError(e?.message || "Network error");
    }
    setSyncing(false);
  };

  const fmtDateTime = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString("en-US", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
    catch (_) { return iso; }
  };

  return (
    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Network size={15} className="text-cyan-400" />
        <h4 className="text-sm font-semibold text-cyan-300">HikCentral Integration</h4>
      </div>
      <p className="text-xs text-gray-500">
        Auto-syncs check-in/out events every 15 minutes from the office's Hikvision face-recognition terminals via HikCentral OpenAPI — feeds the same Attendance Ratio reports as the uploads below.
      </p>

      {loading ? (
        <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
      ) : (
        <>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${status?.configured ? "bg-green-500/15 text-green-400" : "bg-amber-500/15 text-amber-400"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${status?.configured ? "bg-green-400" : "bg-amber-400"}`} />
            {status?.configured ? "Configured" : "Not configured yet"}
          </span>

          {status?.last_sync ? (
            <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-xs space-y-1">
              <div className="flex justify-between"><span className="text-gray-500">Last sync</span><span className="text-gray-300">{fmtDateTime(status.last_sync.uploaded_at)}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Result</span><span className="text-gray-300">{status.last_sync.inserted} new, {status.last_sync.updated} updated</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Triggered by</span><span className="text-gray-300">{status.last_sync.uploaded_by || "—"}</span></div>
              {status.last_sync.notes && <div className="text-gray-600">{status.last_sync.notes}</div>}
            </div>
          ) : (
            <p className="text-xs text-gray-600">No sync recorded yet.</p>
          )}

          {syncResult && (
            <div className="rounded-lg border border-green-800/40 bg-green-900/10 px-3 py-2 text-xs text-green-400">
              Synced {syncResult.date}: {syncResult.events} events → {syncResult.inserted} new, {syncResult.updated} updated
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-800/40 bg-red-900/10 px-3 py-2 text-xs text-red-400">{error}</div>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleSyncNow}
              disabled={syncing || !status?.configured}
              title={!status?.configured ? "Waiting on HikCentral AppKey/AppSecret/base URL" : undefined}
              className="flex items-center gap-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1.5 text-xs font-semibold text-white transition-colors"
            >
              {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Sync Now
            </button>
            <button onClick={loadStatus} className="flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
              <RefreshCw size={12} /> Refresh Status
            </button>
          </div>
        </>
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

      const [d, w, m] = await Promise.all([
        fetch(`${ATT_API}/dept-summary${qs}`,    { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${ATT_API}/whos-off`,             { headers }).then((r) => r.ok ? r.json() : { date: null, data: [] }),
        fetch(`${ATT_API}/monthly-rate?${new URLSearchParams({ ...(fDept ? {department: fDept} : {}), ...(fYear ? {year: fYear} : {}) })}`, { headers }).then((r) => r.ok ? r.json() : []),
      ]);
      setDeptData(d); setWhosOff(w); setMonthly(m);
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
        boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: "0.12em", textTransform: "uppercase" }}>Attendance Ratio</h2>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {[["summary", "Summary"], ["today", "Attendance Today"], ["detail", "Detail"], ["leaveData", "Attendance Leave"], ["annualReport", "Annual Leave Report"], ["correction", "Data Correction"], ["upload", "Upload"]].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{
              padding: "8px 20px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
              background: "#f1f5f9", cursor: "pointer",
              color: activeTab === id ? "#2563eb" : "#64748b",
              boxShadow: activeTab === id
                ? "inset 0 1px 3px rgba(15,23,42,0.07)"
                : "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
              transition: "all 0.2s ease",
            }}>
            {label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={loadSummary} style={{
          padding: 8, borderRadius: 8, border: "none", cursor: "pointer",
          background: "#f1f5f9", color: "#64748b",
          boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
        }}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Filters */}
      {activeTab === "summary" && (
        <div style={{
          display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap",
          padding: "12px 16px", borderRadius: 14,
          background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
        }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Department</label>
            <select value={fDept} onChange={e => setFDept(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
              <option value="">All Departments</option>
              {departments.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Month</label>
            <select value={fMonth} onChange={e => setFMonth(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
              <option value="">All Months</option>
              {MONTHS_ID.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Year</label>
            <select value={fYear} onChange={e => setFYear(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
              {[curYear, curYear - 1, curYear - 2].map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          {(fDept || fMonth) && (
            <button onClick={() => { setFDept(""); setFMonth(""); setFYear(curYear); }}
              style={{ fontSize: 11, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#dc2626", cursor: "pointer", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
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
            <WhosOffWidget data={whosOff} />
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

      {/* ── Leave (moved from the former standalone Leave tab) ── */}
      {activeTab === "leaveData" && (
        <LeaveDataSection />
      )}

      {/* ── Annual leave report (Jan-Dec matrix per employee) ── */}
      {activeTab === "annualReport" && (
        <AnnualLeaveReportSection />
      )}

      {/* ── Manual data correction ── */}
      {activeTab === "correction" && (
        <AttendanceCorrectionSection departments={departments} />
      )}

      {/* All uploads (attendance + leave) consolidated in one place */}
      {activeTab === "upload" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <HikCentralIntegration />
          <AttendanceUpload kind="intercom" />
          <AttendanceUpload kind="talenta" />
          <AttendanceUpload kind="plant" />
          <AttendanceUpload kind="office" />
          <LeaveUpload />
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
          <p style={{ margin: 0, borderTop: `1px solid ${PRINT_BORDER}`, paddingTop: 2, fontWeight: 700 }}>HRGA</p>
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
            style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
            {[curYear - 1, curYear, curYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <button onClick={() => setShowForm(!showForm)}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
            + Add Holiday
          </button>
          <button onClick={() => window.print()} disabled={!summary}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 14px", borderRadius: 8, border: "none", background: "#059669", color: "#fff", cursor: summary ? "pointer" : "not-allowed", opacity: summary ? 1 : 0.5, boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)" }}>
            🖨 Print Calendar
          </button>
        </div>
      </div>

      {summary && <PrintableWorkingCalendar year={year} holidays={holidays} summary={summary} />}

      {/* Add form */}
      {showForm && (
        <div style={{
          display: "flex", gap: 8, alignItems: "flex-end", padding: "12px 16px", borderRadius: 14,
          background: "#f1f5f9", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
        }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>DATE</label>
            <input type="date" value={form.holiday_date} onChange={e => setForm(p => ({ ...p, holiday_date: e.target.value }))}
              style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", outline: "none" }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>HOLIDAY NAME</label>
            <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Eid al-Fitr"
              style={{ width: "100%", fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", outline: "none", boxSizing: "border-box" }} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>TYPE</label>
            <select value={form.holiday_type} onChange={e => setForm(p => ({ ...p, holiday_type: e.target.value }))}
              style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", cursor: "pointer", outline: "none" }}>
              {Object.entries(HTYPE_CFG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <button onClick={handleAdd} disabled={adding || !form.holiday_date || !form.name}
            style={{ fontSize: 12, fontWeight: 700, padding: "6px 16px", borderRadius: 8, border: "none", background: "#059669", color: "#fff", cursor: "pointer", boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", opacity: adding ? 0.5 : 1 }}>
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
          <div style={{ borderRadius: 12, overflow: "hidden", boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)" }}>
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
                  <tr key={m.month} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}>
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
  const [departments, setDepartments] = useState([]);
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
    department: "",
    search: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = { page, page_size: 25 };
      if (filters.year)       p.year = filters.year;
      if (filters.month)      p.month = filters.month;
      if (filters.leave_code) p.leave_code = filters.leave_code;
      if (filters.department) p.department = filters.department;
      if (filters.search)     p.search = filters.search;
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
    hrApi.getLeaveDepartments().then(setDepartments).catch(() => {});
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
          <label className="text-xs text-gray-500 block mb-1">Department</label>
          <select value={filters.department} onChange={e => handleFilter("department", e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {departments.map(d => <option key={d} value={d}>{d}</option>)}
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
              {[["Employee ID","employee_id"],["Name","employee_name"],["Department","department"],["Date","leave_date"],["Leave Code","leave_code"],["Leave Type","leave_type"]].map(([h, field]) => (
                <SortableTH key={h} label={h} field={field} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr><td colSpan={6} className="py-10 text-center"><Loader2 size={14} className="animate-spin inline mr-2 text-gray-500" />Loading...</td></tr>
            ) : data.data.length === 0 ? (
              <tr><td colSpan={6} className="py-10 text-center text-xs text-gray-600">
                No leave data. Upload Talenta Excel in the Leave Upload tab.
              </td></tr>
            ) : sortRows(data.data, sortBy, sortDir, []).map((r, i) => (
              <tr key={i} onClick={() => handleRowClick(r)}
                className="hover:bg-gray-800/40 transition-colors" style={{ cursor: "pointer" }}>
                <td className="px-3 py-2 text-xs font-mono text-gray-500">{r.employee_id}</td>
                <td className="px-3 py-2 text-sm font-medium text-gray-200 whitespace-nowrap">{r.employee_name}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{r.department || "—"}</td>
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
                background: "#f1f5f9", color: page === 1 ? "#cbd5e1" : "#475569",
                boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
              }}>
              <ChevronLeft size={13} />
            </button>
            <button onClick={() => setPage(p => Math.min(data.pages, p + 1))} disabled={page === data.pages}
              style={{
                padding: 6, borderRadius: 8, border: "none", cursor: page === data.pages ? "not-allowed" : "pointer",
                background: "#f1f5f9", color: page === data.pages ? "#cbd5e1" : "#475569",
                boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
              }}>
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Annual leave report (Jan-Dec matrix per employee) ──────────────────────────
const ANNUAL_REPORT_PAGE_SIZE = 8;
// Preferred column order for whatever codes actually show up in the data —
// any code outside this list still gets a column, just sorted after these.
const LEAVE_CODE_ORDER = ["AL", "ALAB", "SL", "UL", "ULBB", "EM", "ML", "EL", "HD", "H", "BT"];
const LEAVE_CODE_LABELS = {
  SL: "Sick Leave", AL: "Annual Leave", ALAB: "Annual Leave", ML: "Maternity Leave",
  EM: "Employee Marriage", UL: "Unpaid Leave", ULBB: "Unpaid Leave", BT: "Business Trip",
  H: "Holiday", EL: "Event Leave", HD: "Half Day Leave",
};

function AnnualLeaveReportSection() {
  const curYear = new Date().getFullYear();
  const [year, setYear] = useState(curYear);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState([]);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("employee_name");
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(1);
  const [addingFor, setAddingFor] = useState(null);
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  useEffect(() => {
    hrApi.getLeaveDepartments().then(setDepartments).catch(() => {});
  }, []);

  const fetchReport = useCallback(() => {
    setLoading(true);
    hrApi.getAnnualLeaveReport(year)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [year]);

  useEffect(() => { fetchReport(); }, [fetchReport]);
  useEffect(() => { setPage(1); }, [department, search, year]);

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  const filtered = (data?.employees || []).filter(e => {
    if (department && e.department !== department) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!e.employee_name?.toLowerCase().includes(q) && !e.employee_id?.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const rows = sortBy === "employee_name" || sortBy === "total"
    ? [...filtered].sort((a, b) => {
        const dir = sortDir === "asc" ? 1 : -1;
        if (sortBy === "total") return (a.total - b.total) * dir;
        return (a.employee_name || "").localeCompare(b.employee_name || "") * dir;
      })
    : filtered;

  const pageCount = Math.max(1, Math.ceil(rows.length / ANNUAL_REPORT_PAGE_SIZE));
  const pageRows = rows.slice((page - 1) * ANNUAL_REPORT_PAGE_SIZE, page * ANNUAL_REPORT_PAGE_SIZE);

  // Column set = every leave code that actually occurs anywhere in this
  // year's data, sorted by LEAVE_CODE_ORDER — same set repeated under every
  // month header so Total always equals the sum of the visible columns.
  const codesPresent = new Set();
  (data?.employees || []).forEach(e => e.months.forEach(m => Object.keys(m.by_code).forEach(c => codesPresent.add(c))));
  const codes = [...codesPresent].sort((a, b) => {
    const ia = LEAVE_CODE_ORDER.indexOf(a), ib = LEAVE_CODE_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
  const totalCols = 2 + MONTHS.length * Math.max(codes.length, 1) + 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Year</label>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            {[curYear + 1, curYear, curYear - 1, curYear - 2, curYear - 3].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Department</label>
          <select value={department} onChange={e => setDepartment(e.target.value)}
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5">
            <option value="">All</option>
            {departments.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Search</label>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Name / ID..."
            className="text-xs rounded-lg border border-gray-700 bg-gray-800 text-gray-200 px-2 py-1.5 w-36" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">&nbsp;</label>
          <button onClick={fetchReport} disabled={loading}
            title="Hitung ulang laporan dari data attendance/leave terbaru"
            className="flex items-center gap-1.5 text-xs rounded-lg border border-gray-700 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-200 px-2 py-1.5">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Reprocess
          </button>
        </div>
        {loading && <Loader2 size={14} className="animate-spin text-gray-500" />}
        <div className="flex-1" />
        <span className="text-xs text-gray-600">{rows.length} employees</span>
      </div>

      <div className="overflow-x-auto overflow-y-auto max-h-[560px] rounded-lg border border-gray-800">
        <table className="text-xs border-collapse w-full">
          <thead>
            <tr>
              <th rowSpan={2} className="px-3 py-2 text-left text-gray-500 bg-gray-800/60 sticky left-0 top-0 cursor-pointer z-20" onClick={() => handleSort("employee_name")}>
                Employee {sortBy === "employee_name" && (sortDir === "asc" ? "▲" : "▼")}
              </th>
              <th rowSpan={2} className="px-2 py-2 text-left text-gray-500 bg-gray-800/60 sticky top-0 z-10">Department</th>
              {MONTHS.map(m => (
                <th key={m} colSpan={Math.max(codes.length, 1)}
                  className="px-2 py-1.5 text-center text-gray-300 bg-gray-800/80 font-bold border-l border-gray-700 sticky top-0 z-10">
                  {m.toUpperCase()}
                </th>
              ))}
              <th rowSpan={2} className="px-3 py-2 text-center text-gray-300 bg-gray-800/60 font-bold cursor-pointer sticky top-0 z-10" onClick={() => handleSort("total")}>
                Total {sortBy === "total" && (sortDir === "asc" ? "▲" : "▼")}
              </th>
            </tr>
            <tr>
              {MONTHS.map(m => (
                codes.length === 0
                  ? <th key={m} className="px-2 py-1 text-center text-gray-600 bg-gray-800/40 border-l border-gray-700 sticky top-[29px] z-10">–</th>
                  : codes.map((c, i) => (
                      <th key={`${m}-${c}`} title={LEAVE_CODE_LABELS[c] || c}
                        className={`px-1.5 py-1 text-center text-gray-500 bg-gray-800/40 font-medium sticky top-[29px] z-10 ${i === 0 ? "border-l border-gray-700" : ""}`}>
                        {c}
                      </th>
                    ))
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={totalCols} className="py-10 text-center"><Loader2 size={14} className="animate-spin inline mr-2 text-gray-500" />Loading...</td></tr>
            ) : pageRows.length === 0 ? (
              <tr><td colSpan={totalCols} className="py-10 text-center text-gray-600">No employees match these filters.</td></tr>
            ) : pageRows.map(emp => (
              <tr key={emp.employee_id} className="border-t border-gray-800 hover:bg-gray-800/30">
                <td className="px-3 py-2 whitespace-nowrap bg-gray-900 sticky left-0 z-10">
                  <button onClick={() => setAddingFor(emp)} title="Click to add a leave entry"
                    className="text-gray-200 font-medium hover:text-blue-400 hover:underline text-left">
                    {emp.employee_name || emp.employee_id}
                  </button>
                  <div className="text-[10px] text-gray-600 font-mono">{emp.employee_id}</div>
                </td>
                <td className="px-2 py-2 text-gray-400 align-top">{emp.department || "—"}</td>
                {emp.months.map(m => (
                  codes.length === 0
                    ? <td key={m.month} className="px-2 py-2 text-center text-gray-700 border-l border-gray-800">–</td>
                    : codes.map((c, i) => {
                        const v = m.by_code[c] || 0;
                        return (
                          <td key={`${m.month}-${c}`} className={`px-1 py-2 text-center ${i === 0 ? "border-l border-gray-800" : ""}`}>
                            <span className={v > 0 ? "text-amber-300 font-semibold" : "text-gray-700"}>{v > 0 ? v : "–"}</span>
                          </td>
                        );
                      })
                ))}
                <td className="px-3 py-2 text-center font-bold text-gray-100 bg-gray-800/30">{emp.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{rows.length} employees · page {page} of {pageCount}</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="px-2 py-1 rounded bg-gray-800 disabled:opacity-40">Prev</button>
            <button onClick={() => setPage(p => Math.min(pageCount, p + 1))} disabled={page === pageCount}
              className="px-2 py-1 rounded bg-gray-800 disabled:opacity-40">Next</button>
          </div>
        </div>
      )}

      {addingFor && (
        <AttendanceEditModal
          record={{ employee_id: addingFor.employee_id, employee_name: addingFor.employee_name, attendance_date: "", _isNew: true }}
          onClose={() => setAddingFor(null)}
          onSaved={() => { setAddingFor(null); fetchReport(); }}
        />
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
  const [converting,    setConverting]    = useState(null); // filename currently being converted to text
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
      const data = await hrApi.eMagazineList();
      setList(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err?.detail || "Failed to load e-magazine list.");
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
      setError(err?.detail || "Upload failed.");
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

  const handleConvertToText = async (filename) => {
    setConverting(filename); setError(""); setSuccess("");
    try {
      const data = await hrApi.eMagazineConvertToText(filename);
      setSuccess(`"${filename}" converted to text — ${data.pages} pages, now searchable in the public reader.`);
      load();
    } catch (err) {
      setError(err?.detail || "Failed to convert to text.");
    } finally { setConverting(null); }
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
      setError(err?.detail || "Failed to save QR links.");
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
        ) : list.length === 0 && error ? (
          <div className="py-10 text-center text-xs">
            <p className="text-red-400 font-medium mb-2">Failed to load edition list: {error}</p>
            <button onClick={load} className="text-teal-400 hover:text-teal-300 underline">Try again</button>
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
                    <td className="px-4 py-3 font-medium text-gray-200">
                      {ed.title}
                      {ed.text_pages > 0 && (
                        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-green-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-green-400 align-middle">
                          <CheckCircle2 size={10} /> Text ready ({ed.text_pages}p)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400">{ed.date || "-"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs font-mono">{ed.filename}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(ed.uploaded_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleConvertToText(ed.filename)}
                          disabled={converting === ed.filename}
                          title="Extract text on-premise (PyMuPDF + Tesseract OCR fallback, same pipeline as the AI Chatbot's document ingest) so this edition becomes searchable in the public reader."
                          className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold text-purple-400 hover:bg-purple-500/10 disabled:opacity-40 transition-colors"
                        >
                          {converting === ed.filename ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
                          {converting === ed.filename ? "Converting…" : ed.text_pages > 0 ? "Re-convert" : "Convert to Text"}
                        </button>
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
