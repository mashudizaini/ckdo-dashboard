import { useState } from "react";
import { Users, UserCheck, Umbrella, BarChart2, RefreshCw } from "lucide-react";

export default function HRDashboard() {
  const [activeSection, setActiveSection] = useState("employees");

  const kpiCards = [
    { id: "employees",  icon: Users,     color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Total Karyawan",  value: "—" },
    { id: "present",    icon: UserCheck, color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Hadir Hari Ini",  value: "—" },
    { id: "leave",      icon: Umbrella,  color: "text-yellow-400", bg: "bg-yellow-500/10", activeBorder: "border-yellow-500/40", label: "Cuti / Leave",    value: "—" },
    { id: "attendance", icon: BarChart2, color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Attendance Rate", value: "—" },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
        {kpiCards.map((c) => (
          <button
            key={c.id}
            onClick={() => setActiveSection(activeSection === c.id ? null : c.id)}
            className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-all ${
              activeSection === c.id
                ? `${c.bg} ${c.activeBorder} ring-1 ring-inset ${c.activeBorder}`
                : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
            }`}
          >
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${c.bg} border ${c.activeBorder}`}>
              <c.icon size={15} className={c.color} />
            </div>
            <span className={`text-sm font-medium truncate ${activeSection === c.id ? "text-white" : "text-gray-400"}`}>
              {c.label}
            </span>
          </button>
        ))}
      </div>

      {activeSection === "employees" && (
        <SectionCard title="Karyawan per Department">
          <DataTable
            headers={["Department", "Permanent", "Contract", "Total"]}
            rows={[
              ["Production",           "480", "40", "520"],
              ["Quality Assurance",    "170", "15", "185"],
              ["Warehouse",            "95",  "20", "115"],
              ["Finance & Accounting", "45",  "5",  "50"],
              ["HR & GA",              "30",  "5",  "35"],
              ["IT",                   "15",  "2",  "17"],
              ["Marketing & Sales",    "25",  "5",  "30"],
            ]}
          />
        </SectionCard>
      )}

      {activeSection === "present" && (
        <SectionCard title="Kehadiran Hari Ini"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <DataTable
            headers={["Department", "Hadir", "Absen", "Terlambat", "WFH"]}
            placeholder="Klik Refresh untuk memuat data kehadiran"
          />
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
        <SectionCard title="Attendance Rate — Bulanan"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <div className="h-40 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center mb-4">
            <span className="text-xs text-gray-600">Chart attendance rate bulanan</span>
          </div>
          <DataTable
            headers={["Bulan", "Total Hari Kerja", "Rata-rata Hadir", "Attendance Rate"]}
            placeholder="Klik Refresh untuk memuat data"
          />
        </SectionCard>
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
                {placeholder || "Tidak ada data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
