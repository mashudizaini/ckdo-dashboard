import { useState, useEffect, useCallback } from "react";
import {
  Users, UserCheck, Umbrella, BarChart2, RefreshCw,
  Upload, Search, ChevronLeft, ChevronRight, X, Loader2, CalendarCheck
} from "lucide-react";
import EmployeeUpload from "./EmployeeUpload";
import AttendanceUpload from "./AttendanceUpload";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/hr/employees";

export default function HRDashboard() {
  const [activeSection, setActiveSection] = useState("employees");

  const kpiCards = [
    { id: "employees",  icon: Users,         color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Data Karyawan" },
    { id: "present",    icon: UserCheck,     color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Hadir Hari Ini" },
    { id: "leave",      icon: Umbrella,      color: "text-yellow-400", bg: "bg-yellow-500/10", activeBorder: "border-yellow-500/40", label: "Cuti / Leave" },
    { id: "attendance", icon: BarChart2,     color: "text-indigo-400", bg: "bg-indigo-500/10", activeBorder: "border-indigo-500/40", label: "Attendance Rate" },
    { id: "upload",     icon: Upload,        color: "text-purple-400", bg: "bg-purple-500/10", activeBorder: "border-purple-500/40", label: "Upload Karyawan" },
    { id: "upload-att", icon: CalendarCheck, color: "text-teal-400",   bg: "bg-teal-500/10",   activeBorder: "border-teal-500/40",   label: "Upload Absensi" },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 xl:grid-cols-6 gap-2">
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
        <SectionCard title="Upload File Excel Karyawan">
          <EmployeeUpload />
        </SectionCard>
      )}

      {/* ── Upload Absensi ───────────────────────────────────────────────────── */}
      {activeSection === "upload-att" && (
        <SectionCard title="Upload File Excel Absensi">
          <AttendanceUpload />
        </SectionCard>
      )}

      {activeSection === "present" && (
        <SectionCard title="Kehadiran Hari Ini">
          <AttendanceTodaySection />
        </SectionCard>
      )}

      {activeSection === "leave" && (
        <SectionCard title="Karyawan Cuti / Leave"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <DataTable
            headers={["Nama", "NIK", "Department", "Jenis Cuti", "Mulai", "Selesai"]}
            placeholder="Klik Refresh untuk memuat data cuti"
          />
        </SectionCard>
      )}

      {activeSection === "attendance" && (
        <SectionCard title="Attendance Rate — Bulanan">
          <AttendanceRateSection />
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
            { label: "Total Karyawan", val: summary.total,     color: "text-blue-400" },
            { label: "Permanent",      val: summary.permanent, color: "text-green-400" },
            { label: "Contract",       val: summary.contract,  color: "text-amber-400" },
            { label: "Laki-laki / Perempuan", val: `${summary.male} / ${summary.female}`, color: "text-purple-400" },
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
            placeholder="Cari nama / NIK / jabatan…"
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
          <option value="">Semua Department</option>
          {departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => handleStatus(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="">Semua Status</option>
          <option value="Permanent">Permanent</option>
          <option value="Contract">Contract</option>
        </select>

        <select
          value={teamFilter}
          onChange={(e) => handleTeam(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="">Semua Team</option>
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
              {["NIK", "Nama", "Department", "Divisi / Tim", "Jabatan", "Penempatan", "Status", "Tgl Masuk"].map((h) => (
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
                    ? "Tidak ada karyawan yang sesuai filter"
                    : "Belum ada data karyawan. Upload file Excel di tab Upload Karyawan."}
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
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>
            {data.total} karyawan · halaman {page} dari {data.pages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-gray-700 p-1.5 hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={13} />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              className="rounded-md border border-gray-700 p-1.5 hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Kehadiran Hari Ini ────────────────────────────────────────────────────────
function AttendanceTodaySection() {
  const { token } = useAuthStore();
  const headers   = { Authorization: `Bearer ${token}` };
  const ATT_API   = "/api/v1/dashboard/hr/attendance";

  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${ATT_API}/today`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, []); // eslint-disable-line

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
    catch (_) { return iso; }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <Loader2 size={20} className="animate-spin text-gray-600" />
    </div>
  );

  if (!data || !data.has_data) return (
    <p className="py-10 text-center text-xs text-gray-600">Belum ada data absensi. Upload file Excel di tab Upload Absensi.</p>
  );

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
              Data terakhir tersedia
            </span>
          )}
        </div>
        <button onClick={fetchData} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Total Karyawan", val: summary.total,           color: "text-blue-400",  bg: "bg-blue-500/10"  },
          { label: "Hadir",          val: summary.hadir,           color: "text-green-400", bg: "bg-green-500/10" },
          { label: "Absen",          val: summary.absen,           color: "text-red-400",   bg: "bg-red-500/10"   },
        ].map(({ label, val, color, bg }) => (
          <div key={label} className={`rounded-lg border border-white/5 ${bg} px-4 py-3 text-center`}>
            <div className={`text-2xl font-bold ${color}`}>{val}</div>
            <div className="text-xs text-gray-500 mt-0.5">{label}</div>
          </div>
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
              <tr><td colSpan={5} className="py-10 text-center text-xs text-gray-600">Tidak ada data hari kerja</td></tr>
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
}

// ── Attendance Rate Bulanan ────────────────────────────────────────────────────
function AttendanceRateSection() {
  const { token } = useAuthStore();
  const headers   = { Authorization: `Bearer ${token}` };
  const ATT_API   = "/api/v1/dashboard/hr/attendance";

  const [data,    setData]    = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${ATT_API}/monthly-rate`, { headers });
      if (res.ok) setData(await res.json());
    } catch (_) {}
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, []); // eslint-disable-line

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <Loader2 size={20} className="animate-spin text-gray-600" />
    </div>
  );

  if (data.length === 0) return (
    <p className="py-10 text-center text-xs text-gray-600">Belum ada data absensi. Upload file Excel di tab Upload Absensi.</p>
  );

  const maxRate  = Math.max(...data.map((d) => d.rate), 1);
  const avgRate  = (data.reduce((s, d) => s + d.rate, 0) / data.length).toFixed(1);
  const reversed = [...data].reverse(); // oldest first for chart

  return (
    <div className="space-y-5">
      {/* Avg summary */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/30 px-4 py-2 text-center">
            <div className="text-xl font-bold text-indigo-400">{avgRate}%</div>
            <div className="text-xs text-gray-500">Rata-rata {data.length} bulan</div>
          </div>
        </div>
        <button onClick={fetchData} className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Bar chart */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-2.5">
        {reversed.map((item) => (
          <div key={item.period} className="flex items-center gap-3">
            <span className="text-xs text-gray-500 w-14 shrink-0 text-right">{item.period}</span>
            <div className="flex-1 h-6 rounded bg-gray-800 overflow-hidden relative">
              <div
                className={`h-full rounded transition-all ${item.rate >= 80 ? "bg-green-500" : item.rate >= 60 ? "bg-amber-500" : "bg-red-500"}`}
                style={{ width: `${(item.rate / maxRate) * 100}%` }}
              />
              <span className="absolute inset-0 flex items-center pl-2 text-xs font-semibold text-white">
                {item.rate}%
              </span>
            </div>
            <span className="text-xs text-gray-600 w-16 shrink-0">{item.hadir}/{item.working} hadir</span>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {["Periode", "Hari Kerja", "Hadir", "Absen", "Attendance Rate"].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {data.map((row) => (
              <tr key={row.period} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-3 py-2.5 font-semibold text-gray-200">{row.period}</td>
                <td className="px-3 py-2.5 text-gray-400 text-center">{row.working}</td>
                <td className="px-3 py-2.5 text-green-400 font-semibold text-center">{row.hadir}</td>
                <td className="px-3 py-2.5 text-red-400 font-semibold text-center">{row.absen}</td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                      <div className={`h-full rounded-full ${row.rate >= 80 ? "bg-green-500" : row.rate >= 60 ? "bg-amber-500" : "bg-red-500"}`}
                        style={{ width: `${row.rate}%` }} />
                    </div>
                    <span className={`text-xs font-semibold w-12 text-right ${row.rate >= 80 ? "text-green-400" : row.rate >= 60 ? "text-amber-400" : "text-red-400"}`}>
                      {row.rate}%
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Shared helpers ─────────────────────────────────────────────────────────────
function Loader({ size = 16, className = "" }) {
  return <Loader2 size={size} className={className} />;
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
                {placeholder || "Tidak ada data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
