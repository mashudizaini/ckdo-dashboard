import { useState, useEffect, useCallback } from "react";
import {
  Users, UserCheck, Umbrella, BarChart2, RefreshCw,
  Upload, Search, ChevronLeft, ChevronRight, X, Loader2, CalendarCheck,
  Wallet, Download, ChevronDown,
} from "lucide-react";
import EmployeeUpload from "./EmployeeUpload";
import AttendanceUpload from "./AttendanceUpload";
import LeaveUpload from "./LeaveUpload";
import { useAuthStore } from "@/store/authStore";
import { hrApi } from "@/api/dashboard";

const API        = "/api/v1/dashboard/hr/employees";
const BUDGET_API = "/api/v1/dashboard/hr/budget";

const MONTHS_ID = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"];

export default function HRDashboard() {
  const [activeSection, setActiveSection] = useState("employees");

  const kpiCards = [
    { id: "employees",  icon: Users,         color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Employee Data" },
    { id: "present",    icon: UserCheck,     color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Present Today" },
    { id: "leave",      icon: Umbrella,      color: "text-yellow-400", bg: "bg-yellow-500/10", activeBorder: "border-yellow-500/40", label: "Leave" },
    { id: "attendance", icon: BarChart2,     color: "text-indigo-400", bg: "bg-indigo-500/10", activeBorder: "border-indigo-500/40", label: "Attendance Rate" },
    { id: "upload",     icon: Upload,        color: "text-purple-400", bg: "bg-purple-500/10", activeBorder: "border-purple-500/40", label: "Employee Upload" },
    { id: "upload-att", icon: CalendarCheck, color: "text-teal-400",   bg: "bg-teal-500/10",   activeBorder: "border-teal-500/40",   label: "Attendance Upload" },
    { id: "upload-lv",  icon: Umbrella,      color: "text-pink-400",   bg: "bg-pink-500/10",   activeBorder: "border-pink-500/40",   label: "Leave Upload" },
    { id: "budget",     icon: Wallet,        color: "text-orange-400", bg: "bg-orange-500/10", activeBorder: "border-orange-500/40", label: "Budget Monitoring" },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 xl:grid-cols-8 gap-2">
        {kpiCards.map((c) => (
          <button
            key={c.id}
            onClick={() => setActiveSection(activeSection === c.id ? null : c.id)}
            className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-all ${
              activeSection === c.id
                ? `${c.bg} ${c.activeBorder} ring-1 ring-inset ${c.activeBorder}`
                : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
            }`}
          >
            <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${c.bg} border ${c.activeBorder}`}>
              <c.icon size={12} className={c.color} />
            </div>
            <span className={`text-xs font-medium leading-tight ${activeSection === c.id ? "text-white" : "text-gray-400"}`}>
              {c.label}
            </span>
          </button>
        ))}
      </div>

      {/* ── Data Karyawan (tabel + search) ─────────────────────────────────── */}
      {activeSection === "employees" && (
        <SectionCard title="List Of Employee">
          <EmployeeTable />
        </SectionCard>
      )}

      {/* ── Upload Karyawan ──────────────────────────────────────────────────── */}
      {activeSection === "upload" && (
        <SectionCard title="Upload Employee Excel File">
          <EmployeeUpload />
        </SectionCard>
      )}

      {/* ── Upload Absensi ───────────────────────────────────────────────────── */}
      {activeSection === "upload-att" && (
        <SectionCard title="Upload Attendance Excel File">
          <AttendanceUpload />
        </SectionCard>
      )}

      {activeSection === "present" && (
        <SectionCard title="Attendance Today">
          <AttendanceTodaySection />
        </SectionCard>
      )}

      {activeSection === "leave" && (
        <SectionCard title="Employee Leave">
          <LeaveDataSection />
        </SectionCard>
      )}

      {activeSection === "upload-lv" && (
        <SectionCard title="Upload Leave Data (Talenta Excel)">
          <LeaveUpload />
        </SectionCard>
      )}

      {activeSection === "attendance" && (
        <SectionCard title="Attendance Rate — Monthly">
          <AttendanceRateSection />
        </SectionCard>
      )}

      {activeSection === "budget" && (
        <SectionCard title="Budget Monitoring HRGA">
          <BudgetMonitoringSection />
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
  const [teamFilter, setTeamFilter] = useState("");
  const [departments, setDepartments]   = useState([]);
  const [teams,       setTeams]         = useState([]);
  const [summary,    setSummary]    = useState(null);

  const PAGE_SIZE = 25;

  const fetchDepts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/departments`, { headers });
      if (res.ok) setDepartments(await res.json());
    } catch (_) {}
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
        ...(search       ? { search }               : {}),
        ...(deptFilter   ? { department: deptFilter } : {}),
        ...(statusFilter ? { status: statusFilter }  : {}),
        ...(teamFilter   ? { team: teamFilter }      : {}),
      });
      const res = await fetch(`${API}?${params}`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  }, [page, search, deptFilter, statusFilter, teamFilter]); // eslint-disable-line

  useEffect(() => { fetchDepts(); fetchSummary(); fetchTeams(""); }, []); // eslint-disable-line
  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  // Reset page kalau filter/search berubah
  const handleSearch   = (v) => { setSearch(v);       setPage(1); };
  const handleDept     = (v) => { setDeptFilter(v);   setTeamFilter(""); fetchTeams(v); setPage(1); };
  const handleStatus   = (v) => { setStatusFilter(v); setPage(1); };
  const handleTeam     = (v) => { setTeamFilter(v);   setPage(1); };

  const STATUS_BADGE = {
    "Permanent": "bg-green-500/15 text-green-400 border-green-500/30",
    "Contract":  "bg-amber-500/15 text-amber-400 border-amber-500/30",
  };

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Total Employees", val: summary.total,     color: "text-blue-400" },
            { label: "Permanent",      val: summary.permanent, color: "text-green-400" },
            { label: "Contract",       val: summary.contract,  color: "text-amber-400" },
            { label: "Male / Female", val: `${summary.male} / ${summary.female}`, color: "text-purple-400" },
          ].map(({ label, val, color }) => (
            <div key={label} className="rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3 text-center">
              <div className={`text-2xl font-bold ${color}`}>{val}</div>
              <div className="text-xs text-gray-500 mt-0.5">{label}</div>
            </div>
          ))}
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
      </div>

      {/* Tabel */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {["NIK", "Name", "Department", "Division / Team", "Position", "Placement", "Status", "Join Date"].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr>
                <td colSpan={8} className="py-12 text-center">
                  <Loader size={16} className="mx-auto animate-spin text-gray-600" />
                </td>
              </tr>
            ) : data.employees.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-xs text-gray-600">
                  {search || deptFilter || statusFilter
                    ? "No employees matching filter"
                    : "No employee data yet. Upload Excel in Employee Upload tab."}
                </td>
              </tr>
            ) : (
              data.employees.map((e) => (
                <tr key={e.user_id} className="hover:bg-gray-800/40 transition-colors">
                  <td className="px-3 py-2.5 font-mono text-xs text-gray-500">{e.user_id}</td>
                  <td className="px-3 py-2.5 font-medium text-gray-200 whitespace-nowrap">{e.full_name}</td>
                  <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{e.department || "—"}</td>
                  <td className="px-3 py-2.5 text-gray-500 text-xs">
                    {[e.division, e.team].filter(Boolean).join(" / ") || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap max-w-[180px] truncate" title={e.job_title}>{e.job_title || "—"}</td>
                  <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{e.work_placement || "—"}</td>
                  <td className="px-3 py-2.5">
                    {e.status ? (
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[e.status] || "bg-gray-700 text-gray-400 border-gray-600"}`}>
                        {e.status}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-xs">
                    {e.date_of_joining
                      ? new Date(e.date_of_joining).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" })
                      : "—"}
                  </td>
                </tr>
              ))
            )}
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
    </div>
  );
}

// ── Tabel detail Dept + Team ──────────────────────────────────────────────────
function DeptTeamTable({ data }) {
  if (!data) return null;
  const { departments, grand_total } = data;

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-800/70">
            <th className="px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Dept.</th>
            <th className="px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Div. / Team</th>
            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Employees</th>
            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Plan</th>
            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">Act</th>
            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wider border border-gray-700">%</th>
          </tr>
        </thead>
        <tbody>
          {departments.map((dept) => [
            ...dept.teams.map((team, ti) => (
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

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${ATT_API}/today`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
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
    try { return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
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
          {loading && <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-gray-600" /></div>}
          {noData && <p className="py-10 text-center text-xs text-gray-600">No attendance data yet. Upload Excel in Attendance Upload tab.</p>}
          {data && data.has_data && (() => {
            const { summary, actual_date, is_today } = data;
            return (
              <div className="space-y-4">
                {/* Date badge */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CalendarCheck size={14} className="text-green-400" />
                    <span className="text-sm font-semibold text-gray-200">{fmtDate(actual_date)}</span>
                    {!is_today && (
                      <span className="rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-xs text-amber-400">
                        Latest available data
                      </span>
                    )}
                  </div>
                  <button onClick={fetchData} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                    <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
                  </button>
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
                              {["No", "Name", "Department", "Check-In", "Check-Out", "Notes"].map((h) => (
                                <th key={h} className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-800/50">
                            {employees.length === 0 ? (
                              <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-600">No data</td></tr>
                            ) : employees.map((emp, i) => (
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
                        {["Department", "Total", "Hadir", "Absen", "Rate"].map((h) => (
                          <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {data.data.length === 0 ? (
                        <tr><td colSpan={5} className="py-10 text-center text-xs text-gray-600">No working day data</td></tr>
                      ) : data.data.map((row) => (
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

function DeptBarChart({ data }) {
  if (!data.length) return <p className="text-xs text-gray-600 py-6 text-center">No data</p>;
  const maxVal = Math.max(...data.map((d) => d.plan), 1);
  const BAR_H  = 120;
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold text-gray-400">Attendance Ratio per Department</h4>
        <div className="flex gap-3 text-xs text-gray-600">
          <span className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded bg-blue-500" /> Plan</span>
          <span className="flex items-center gap-1"><div className="w-2.5 h-2.5 rounded bg-orange-500" /> Actual</span>
        </div>
      </div>
      <div className="flex items-end justify-around gap-1" style={{ height: BAR_H + 44 }}>
        {data.map((dept) => {
          const planH   = Math.max(Math.round((dept.plan   / maxVal) * BAR_H), 2);
          const actualH = Math.max(Math.round((dept.actual / maxVal) * BAR_H), dept.actual > 0 ? 2 : 0);
          const short   = dept.department.split(/[\s/&]/)[0];
          return (
            <div key={dept.department} className="flex-1 flex flex-col items-center" title={dept.department}>
              <div className="w-full flex items-end justify-center gap-0.5" style={{ height: BAR_H }}>
                <div className="flex flex-col items-center" style={{ width: "42%" }}>
                  <span className="text-xs text-gray-400 font-semibold">{dept.plan}</span>
                  <div className="w-full bg-blue-500 rounded-t" style={{ height: planH }} />
                </div>
                <div className="flex flex-col items-center" style={{ width: "42%" }}>
                  <span className="text-xs text-orange-400 font-semibold">{dept.actual}</span>
                  <div className="w-full bg-orange-500 rounded-t" style={{ height: actualH }} />
                </div>
              </div>
              <p className="text-xs text-gray-500 mt-1 truncate max-w-full text-center">{short}</p>
              <p className="text-xs font-bold text-orange-400">{dept.rate}%</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WhosOffWidget({ data }) {
  const fmtShort = (iso) => {
    if (!iso) return "";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", { day: "numeric", month: "short" }); }
    catch (_) { return iso; }
  };
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-400">Who's Off</h4>
        {data.date && <span className="text-xs text-gray-600">{fmtShort(data.date)}</span>}
      </div>
      {!data.data?.length ? (
        <p className="text-xs text-gray-600 py-2 text-center">All present</p>
      ) : (
        <div className="space-y-1.5">
          {data.data.slice(0, 5).map((emp, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <div className="h-5 w-5 rounded-full bg-gray-700 flex items-center justify-center text-xs font-bold text-gray-400 shrink-0">
                {emp.name?.charAt(0) || "?"}
              </div>
              <div className="min-w-0">
                <p className="text-xs text-gray-300 truncate leading-tight">{emp.name}</p>
                <p className="text-xs text-gray-600 leading-tight">{emp.reason}</p>
              </div>
            </div>
          ))}
          {data.data.length > 5 && (
            <p className="text-xs text-gray-600 text-center">+{data.data.length - 5} more</p>
          )}
        </div>
      )}
    </div>
  );
}

function StatBreakdown({ title, data }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
      <h4 className="text-xs font-semibold text-gray-400 mb-2">{title}</h4>
      {!data?.length ? (
        <p className="text-xs text-gray-600 py-2 text-center">—</p>
      ) : (
        <div className="space-y-2.5">
          {data.map((item) => (
            <div key={item.label}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-400 truncate max-w-[65%]">{item.label}</span>
                <span className="text-blue-400 font-bold">{item.rate}%</span>
              </div>
              <div className="h-4 rounded-full bg-gray-800 overflow-hidden">
                <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max(item.rate, 1)}%` }} />
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
  const H = 130;
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
      <div className="flex items-center gap-3 mb-3">
        <h4 className="text-xs font-semibold text-gray-400">Monthly Attendance</h4>
        <div className="flex gap-2 text-xs text-gray-600">
          <span className="flex items-center gap-1"><div className="w-2 h-2 bg-blue-500 rounded" />Plan</span>
          <span className="flex items-center gap-1"><div className="w-2 h-2 bg-orange-500 rounded" />Actual</span>
        </div>
      </div>
      <div className="flex items-end gap-2" style={{ height: H }}>
        {data.map((m) => {
          const planH   = Math.max(Math.round((m.plan   / maxVal) * (H - 35)), 2);
          const actualH = Math.max(Math.round((m.actual / maxVal) * (H - 35)), m.actual > 0 ? 2 : 0);
          return (
            <div key={m.period} className="flex-1 flex flex-col items-center">
              <div className="w-full flex items-end justify-center gap-0.5" style={{ height: H - 35 }}>
                <div className="flex flex-col items-center" style={{ width: "42%" }}>
                  <span className="text-xs text-gray-500">{m.plan}</span>
                  <div className="w-full bg-blue-500 rounded-t" style={{ height: planH }} />
                </div>
                <div className="flex flex-col items-center" style={{ width: "42%" }}>
                  <span className="text-xs text-orange-400">{m.actual}</span>
                  <div className="w-full bg-orange-500 rounded-t" style={{ height: actualH }} />
                </div>
              </div>
              <p className="text-xs text-gray-600 mt-0.5">{m.period}</p>
              <p className="text-xs font-bold text-orange-400">{m.rate}%</p>
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
    try { return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }); }
    catch (_) { return iso; }
  };

  return (
    <div className="grid grid-cols-2 gap-5">
      {/* Left: search + info + absence */}
      <div className="space-y-3">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); doSearch(e.target.value); }}
            placeholder="Type employee name..."
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-8 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
          />
          {results.length > 0 && (
            <div className="absolute top-full left-0 right-0 z-20 mt-1 rounded-lg border border-gray-700 bg-gray-800 shadow-xl max-h-52 overflow-y-auto">
              {results.map((r) => (
                <button key={r.id} onClick={() => loadDetail(r)}
                  className="w-full text-left px-3 py-2 hover:bg-gray-700 transition-colors border-b border-gray-700/40 last:border-0">
                  <p className="text-sm text-gray-200">{r.name}</p>
                  <p className="text-xs text-gray-500">{r.id} · {r.department}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {loading && <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-gray-600" /></div>}

        {detail && !loading && (
          <>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "ID",         val: detail.employee.id },
                { label: "Department", val: detail.employee.department },
                { label: "Team",       val: detail.employee.team },
                { label: "Location",   val: detail.employee.work_placement },
              ].map(({ label, val }) => (
                <div key={label} className="rounded-lg bg-gray-800/60 border border-gray-700 px-3 py-2">
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className="text-xs font-semibold text-gray-200 truncate">{val || "—"}</p>
                </div>
              ))}
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-400 mb-1.5">Absence Records</h4>
              <div className="overflow-auto max-h-52 rounded-lg border border-gray-800">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-800">
                    <tr>
                      {["Date", "Note"].map((h) => (
                        <th key={h} className="px-2 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {!detail.absences.length ? (
                      <tr><td colSpan={2} className="px-2 py-4 text-center text-gray-600">No absence records</td></tr>
                    ) : detail.absences.map((a, i) => (
                      <tr key={i} className="hover:bg-gray-800/40">
                        <td className="px-2 py-2 text-gray-400 whitespace-nowrap">{fmtDate(a.date)}</td>
                        <td className="px-2 py-2 text-gray-500">{a.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {!detail && !loading && (
          <p className="py-10 text-center text-xs text-gray-600">Type employee name to view attendance details</p>
        )}
      </div>

      {/* Right: monthly chart */}
      <div>
        {detail?.monthly?.length > 0
          ? <MiniBarChart data={detail.monthly} />
          : (
            <div className="flex items-center justify-center h-48 rounded-lg border border-gray-800 bg-gray-900/50">
              <p className="text-xs text-gray-700">Monthly chart will appear after selecting an employee</p>
            </div>
          )
        }
      </div>
    </div>
  );
}

// ── Attendance Ratio Dashboard ─────────────────────────────────────────────────
function AttendanceRateSection() {
  const { token }  = useAuthStore();
  const headers    = { Authorization: `Bearer ${token}` };
  const ATT_API    = "/api/v1/dashboard/hr/attendance";

  const [activeTab, setActiveTab] = useState("summary");
  const [deptData,  setDeptData]  = useState([]);
  const [whosOff,   setWhosOff]   = useState({ date: null, data: [] });
  const [workforce, setWorkforce] = useState({ by_gender: [], by_location: [] });
  const [monthly,   setMonthly]   = useState([]);
  const [loading,   setLoading]   = useState(false);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const [d, w, ws, m] = await Promise.all([
        fetch(`${ATT_API}/dept-summary`,    { headers }).then((r) => r.ok ? r.json() : []),
        fetch(`${ATT_API}/whos-off`,        { headers }).then((r) => r.ok ? r.json() : { date: null, data: [] }),
        fetch(`${ATT_API}/workforce-stats`, { headers }).then((r) => r.ok ? r.json() : { by_gender: [], by_location: [] }),
        fetch(`${ATT_API}/monthly-rate`,    { headers }).then((r) => r.ok ? r.json() : []),
      ]);
      setDeptData(d); setWhosOff(w); setWorkforce(ws); setMonthly(m);
    } catch (_) {}
    finally { setLoading(false); }
  }, []); // eslint-disable-line

  useEffect(() => { loadSummary(); }, [loadSummary]);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin text-gray-600" /></div>;
  if (!deptData.length) return <p className="py-10 text-center text-xs text-gray-600">No attendance data yet. Upload Excel in Attendance Upload tab.</p>;

  return (
    <div className="space-y-4">
      {/* Header orange */}
      <div className="rounded-lg py-2.5 text-center" style={{ background: "linear-gradient(90deg, #ea580c, #f97316)" }}>
        <h2 className="text-sm font-bold text-white tracking-widest uppercase">Attendance Ratio</h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-gray-700">
        {[["summary", "Summary"], ["detail", "Detail"]].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`px-5 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${
              activeTab === id ? "border-blue-500 text-blue-400 bg-blue-500/5" : "border-transparent text-gray-500 hover:text-gray-300"
            }`}>
            {label}
          </button>
        ))}
        <div className="flex-1" />
        <button onClick={loadSummary} className="px-3 text-gray-600 hover:text-gray-400">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── Summary ── */}
      {activeTab === "summary" && (
        <div className="grid grid-cols-5 gap-4">
          {/* Left 3/5: dept chart + bottom row */}
          <div className="col-span-3 space-y-3">
            <DeptBarChart data={deptData} />
            <div className="grid grid-cols-3 gap-3">
              <WhosOffWidget data={whosOff} />
              <StatBreakdown title="Base on Gender"        data={workforce.by_gender}   />
              <StatBreakdown title="Base on Work Location" data={workforce.by_location} />
            </div>
          </div>

          {/* Right 2/5: monthly overall */}
          <div className="col-span-2 space-y-3">
            <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
              <h4 className="text-xs font-semibold text-gray-400 mb-3">Monthly Overall Rate</h4>
              <div className="space-y-2">
                {[...monthly].reverse().map((m) => (
                  <div key={m.period} className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-14 shrink-0 text-right">{m.period}</span>
                    <div className="flex-1 h-5 rounded bg-gray-800 overflow-hidden relative">
                      <div className={`h-full rounded transition-all ${m.rate >= 80 ? "bg-green-500" : m.rate >= 60 ? "bg-amber-500" : "bg-red-500"}`}
                        style={{ width: `${m.rate}%` }} />
                      <span className="absolute inset-0 flex items-center pl-2 text-xs font-semibold text-white">{m.rate}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/60 px-4 py-3">
              <div className="flex gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-green-500" /> ≥ 80%</span>
                <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-amber-500" /> 60–79%</span>
                <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-red-500" /> &lt; 60%</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Detail ── */}
      {activeTab === "detail" && (
        <EmployeeDetailPanel headers={headers} apiBase={ATT_API} />
      )}
    </div>
  );
}

// ── Budget Monitoring ─────────────────────────────────────────────────────────
// Data dari 2 sumber Oracle yang di-upload terpisah:
//   - "Import Budget"     → Oracle modul Budget   → /upload/budget
//   - "Import Realisasi"  → Oracle modul AP Invoice → /upload/actual
//
// Kalkulasi:  Remain = Available + Reclass − Total Actual

function BudgetMonitoringSection() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const curYear = new Date().getFullYear();

  const [dept,          setDept]          = useState("");
  const [departments,   setDepartments]   = useState([]);
  const [year,          setYear]          = useState(curYear);
  const [month,         setMonth]         = useState(0);
  const [years,         setYears]         = useState([curYear, curYear - 1]);
  const [data,          setData]          = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [expandedCode,  setExpandedCode]  = useState(null);
  const [accountDetail, setAccountDetail] = useState({});
  const [uploadMsg,     setUploadMsg]     = useState(null);

  // Load daftar department dari Oracle saat pertama kali
  const loadDepartments = useCallback(async () => {
    try {
      const res = await fetch(`${BUDGET_API}/departments`, { headers: hdrs });
      if (res.ok) {
        const depts = await res.json();
        setDepartments(depts);
        if (depts.length && !dept) setDept(depts[0].dept_code);
      }
    } catch (_) {}
  }, []); // eslint-disable-line

  const loadYears = useCallback(async () => {
    if (!dept) return;
    try {
      const res = await fetch(`${BUDGET_API}/years?dept=${encodeURIComponent(dept)}`, { headers: hdrs });
      if (res.ok) {
        const ys = await res.json();
        if (ys.length) { setYears(ys); setYear(ys[0]); }
      }
    } catch (_) {}
  }, [dept]); // eslint-disable-line

  const load = useCallback(async () => {
    if (!dept) return;
    setLoading(true);
    setData(null);
    try {
      const params = new URLSearchParams({ dept, year });
      if (month) params.set("month", month);
      const res = await fetch(`${BUDGET_API}?${params}`, { headers: hdrs });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    setLoading(false);
  }, [dept, year, month]); // eslint-disable-line

  useEffect(() => { loadDepartments(); }, [loadDepartments]);
  useEffect(() => { loadYears(); }, [loadYears]);
  useEffect(() => { if (dept) load(); }, [load]); // eslint-disable-line

  const loadDetail = async (code) => {
    const key = `${dept}_${code}_${year}`;
    if (accountDetail[key]) return;
    try {
      const res = await fetch(
        `${BUDGET_API}/account/${encodeURIComponent(code)}?dept=${encodeURIComponent(dept)}&year=${year}`,
        { headers: hdrs }
      );
      if (res.ok) { const d = await res.json(); setAccountDetail(prev => ({ ...prev, [key]: d })); }
    } catch (_) {}
  };

  const handleExpand = async (code) => {
    if (expandedCode === code) { setExpandedCode(null); return; }
    setExpandedCode(code);
    await loadDetail(code);
  };

  const handleDeptChange = (newDept) => {
    setDept(newDept);
    setData(null);
    setExpandedCode(null);
    setAccountDetail({});
  };

  const fmtRp = (v) => {
    if (v === undefined || v === null) return "Rp 0";
    return (v < 0 ? "-Rp " : "Rp ") + Math.abs(v).toLocaleString("id-ID");
  };

  const summary  = data?.summary;
  const accounts = data?.accounts || [];

  return (
    <div className="space-y-4">

      {/* ── Controls ── */}
      <div className="flex flex-wrap items-center gap-2">

        {/* Dropdown Department — dari Oracle CKDO_GL_COA_DEPARTMENT */}
        <select
          value={dept}
          onChange={e => handleDeptChange(e.target.value)}
          className="rounded-lg border border-orange-700/60 bg-gray-900 px-3 py-1.5 text-sm text-orange-200 outline-none focus:border-orange-500 min-w-36"
        >
          {departments.length === 0
            ? <option value="">Loading dept...</option>
            : departments.map(d => (
                <option key={d.dept_code} value={d.dept_code}>
                  {d.dept_code}{d.dept_name ? ` — ${d.dept_name}` : ""}
                </option>
              ))
          }
        </select>

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
          disabled={!dept}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh from Oracle
        </button>

        <div className="flex-1" />

        <button
          onClick={() => {
            if (!dept) return;
            const p = new URLSearchParams({ dept, year });
            if (month) p.set("month", month);
            window.open(`${BUDGET_API}/export?${p}`, "_blank");
          }}
          disabled={!dept || !data}
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
      {!loading && dept && data && accounts.length === 0 && (
        <div className="py-16 text-center space-y-2">
          <Wallet size={32} className="mx-auto text-gray-700" />
          <p className="text-xs text-gray-600">
            No budget data for department <strong className="text-gray-400">{dept}</strong> year {year}.
          </p>
        </div>
      )}
      {!loading && !dept && (
        <div className="py-16 text-center">
          <p className="text-xs text-gray-600">Select department to view budget data.</p>
        </div>
      )}

      {/* ── Summary cards ── */}
      {!loading && summary && accounts.length > 0 && (
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          <BudgetSummaryCard label="Total Budget (GL)"    value={fmtRp(summary.total_budget)} color="text-blue-400"  bg="bg-blue-500/10  border-blue-500/20" />
          <BudgetSummaryCard label="Total Actual (AP)" value={fmtRp(summary.total_actual)} color="text-violet-400" bg="bg-violet-500/10 border-violet-500/20" />
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
            <div className="col-span-2 text-right">Actual (AP)</div>
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
                  <div className="col-span-3 text-right text-blue-300">{fmtRp(acc.budget)}</div>
                  <div className="col-span-2 text-right text-violet-300">{fmtRp(acc.actual)}</div>
                  <div className={`col-span-2 text-right font-semibold ${remainOk ? "text-green-400" : "text-red-400"}`}>
                    {fmtRp(acc.remain)}
                  </div>
                </button>

                {/* ── Detail: tabel per bulan sesuai format laporan ── */}
                {isExp && (
                  <div className="border-t border-gray-800/60 bg-gray-950/50 px-4 py-3">
                    {!detail ? (
                      <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
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

/* Tabel detail per bulan — data dari Oracle GL (budget) + Oracle AP (actual items) */
function BudgetMonthTable({ m, fmtRp, accName }) {
  const remainOk = m.remain >= 0;

  return (
    <div className="rounded-lg border border-gray-800 overflow-hidden text-xs">
      {/* Month header */}
      <div className="bg-gray-800/80 px-3 py-1.5 flex items-center gap-3">
        <span className="font-bold text-gray-200">{m.month_name || MONTHS_ID[m.month - 1]} Budget</span>
        <span className="text-blue-300 font-semibold">{fmtRp(m.budget)}</span>
        <span className="text-gray-600 flex-1">{accName}</span>
      </div>

      {/* Table */}
      <table className="w-full">
        <thead>
          <tr className="bg-gray-800/40 text-gray-500 uppercase tracking-wider text-xs">
            <th className="px-3 py-2 text-left font-semibold" style={{width:"45%"}}>Actual Expense (AP Invoice)</th>
            <th className="px-3 py-2 text-right font-semibold">Amount (Rp)</th>
            <th className="px-3 py-2 text-right font-semibold">Date</th>
            <th className="px-3 py-2 text-right font-semibold">No. Invoice</th>
            <th className="px-3 py-2 text-right font-semibold">Remaining</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {m.items.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-3 py-3 text-gray-700 italic">
                No AP Invoice data for this period.
              </td>
            </tr>
          ) : (
            m.items.map((item, idx) => (
              <tr key={idx} className="hover:bg-gray-800/20 transition-colors">
                <td className="px-3 py-2 text-gray-300">{item.description}</td>
                <td className="px-3 py-2 text-right text-gray-300 tabular-nums">
                  {(item.amount || 0).toLocaleString("id-ID")}
                </td>
                <td className="px-3 py-2 text-right text-gray-500">{item.date || "—"}</td>
                <td className="px-3 py-2 text-right text-gray-600">{item.invoice_num || "—"}</td>
                {/* Sisa hanya tampil di baris pertama (rowspan) */}
                {idx === 0 ? (
                  <td className={`px-3 py-2 text-right tabular-nums align-top font-medium ${remainOk ? "text-green-400" : "text-red-400"}`}
                    rowSpan={m.items.length}>
                    <div className="text-gray-500 text-xs">{fmtRp(m.budget)}</div>
                    <div className="text-gray-600 text-xs">− {fmtRp(m.total_actual)}</div>
                    <div className={`border-t border-gray-700 mt-1 pt-1 font-bold ${remainOk ? "text-green-400" : "text-red-400"}`}>
                      {fmtRp(m.remain)}
                    </div>
                  </td>
                ) : null}
              </tr>
            ))
          )}

          {/* Baris total */}
          <tr className="bg-gray-800/40 font-semibold border-t-2 border-gray-700">
            <td className="px-3 py-2 text-gray-400 uppercase tracking-wider">Total Actual</td>
            <td className="px-3 py-2 text-right text-violet-300 tabular-nums">
              {m.total_actual.toLocaleString("id-ID")}
            </td>
            <td colSpan={2} />
            <td className={`px-3 py-2 text-right tabular-nums font-bold ${remainOk ? "text-green-400" : "text-red-400"}`}>
              {fmtRp(m.remain)}
            </td>
          </tr>
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

function LeaveDataSection() {
  const { token } = useAuthStore();
  const [data, setData] = useState({ data: [], total: 0, pages: 1 });
  const [summary, setSummary] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
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
    <div className="space-y-4">
      {/* Summary badges */}
      {summary && (
        <div className="flex flex-wrap gap-2">
          <div className="px-3 py-1.5 rounded-lg bg-gray-800 text-xs font-semibold text-gray-300">
            Total: {summary.total}
          </div>
          {summary.by_code?.map(c => {
            const cfg = LEAVE_CODES.find(l => l.code === c.code);
            return (
              <div key={c.code} style={{
                padding: "4px 10px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                background: cfg ? `${cfg.color}18` : "#f1f5f9",
                color: cfg?.color || "#64748b",
                border: `1px solid ${cfg ? `${cfg.color}30` : "#e2e8f0"}`,
              }}>
                {c.code}: {c.count}
              </div>
            );
          })}
        </div>
      )}

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
              {["Employee ID","Name","Organization","Position","Date","Leave Code","Leave Type"].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
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
            ) : data.data.map((r, i) => (
              <tr key={i} className="hover:bg-gray-800/40 transition-colors">
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
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        {action}
      </div>
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
