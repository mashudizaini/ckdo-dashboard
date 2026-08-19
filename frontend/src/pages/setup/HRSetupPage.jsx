import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { hrApi } from "@/api/dashboard";

// Data Coverage — moved here from Dashboard > HRGA > Attendance Rate
// (2026-08-19 user request). Was the "Data Coverage" tab there; now lives
// standalone under Setup > HRGA instead.
const COVERAGE_SOURCES = [
  { key: "intercom",      label: "Intercom" },
  { key: "talenta",       label: "Talenta (Attendance)" },
  { key: "talenta-leave", label: "Talenta (Leave)" },
  { key: "plant",         label: "Plant" },
  { key: "office",        label: "Office" },
  { key: "manual",        label: "Manual" },
];

function AttendanceCoverageSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState(null); // null = all sources combined

  useEffect(() => {
    setLoading(true);
    hrApi.getAttendanceCoverage(10)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  if (!data) return <p className="text-center text-xs text-gray-500 py-10">Failed to load coverage data.</p>;

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const gridByYm = {};
  data.grid.forEach(c => { gridByYm[`${c.year}-${c.month}`] = c; });
  const yearsDesc = [...data.years].sort((a, b) => b - a);

  const cellStyle = (status) => {
    if (status === "data") return "bg-green-500/15 text-green-300 border border-green-500/25";
    if (status === "gap")  return "bg-red-500/15 text-red-400 border border-red-500/30";
    return "bg-gray-800/40 text-gray-700 border border-gray-800";
  };

  const selectedLabel = selectedSource
    ? (COVERAGE_SOURCES.find(s => s.key === selectedSource)?.label || selectedSource)
    : "All Sources";

  return (
    <div className="space-y-4">
      {/* Last upload per source — click a card to filter the grid below by that source */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setSelectedSource(null)}
          className={`rounded-lg border px-3 py-2 text-xs text-left min-w-[100px] transition-colors ${
            selectedSource === null
              ? "border-blue-500/50 bg-blue-500/10"
              : "border-gray-800 bg-gray-900 hover:border-gray-700"
          }`}>
          <div className={`font-semibold ${selectedSource === null ? "text-blue-300" : "text-gray-300"}`}>All Sources</div>
          <div className="text-gray-600 mt-0.5">Combined view</div>
        </button>
        {COVERAGE_SOURCES.map(s => {
          const info = data.last_upload_by_source[s.key];
          const isActive = selectedSource === s.key;
          return (
            <button key={s.key} onClick={() => setSelectedSource(cur => cur === s.key ? null : s.key)}
              className={`rounded-lg border px-3 py-2 text-xs text-left min-w-[140px] transition-colors ${
                isActive ? "border-blue-500/50 bg-blue-500/10" : "border-gray-800 bg-gray-900 hover:border-gray-700"
              }`}>
              <div className={`font-semibold ${isActive ? "text-blue-300" : "text-gray-300"}`}>{s.label}</div>
              {info ? (
                <div className="text-gray-500 mt-0.5">
                  {info.uploaded_at?.replace("T", " ").slice(0, 16)}
                  <div className="text-gray-600 truncate max-w-[160px]" title={info.filename}>{info.filename}</div>
                </div>
              ) : (
                <div className="text-gray-600 mt-0.5">Never uploaded</div>
              )}
            </button>
          );
        })}
      </div>

      <p className="text-xs text-gray-500">Showing: <span className="text-gray-300 font-semibold">{selectedLabel}</span></p>

      {/* Heatmap grid */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-gray-500 bg-gray-800/60 sticky left-0">Year</th>
              {MONTHS.map(m => <th key={m} className="px-2 py-2 text-center text-gray-500 bg-gray-800/60 font-medium">{m}</th>)}
            </tr>
          </thead>
          <tbody>
            {yearsDesc.map(yr => (
              <tr key={yr} className="border-t border-gray-800">
                <td className="px-3 py-2 font-semibold text-gray-300 bg-gray-900 sticky left-0">{yr}</td>
                {MONTHS.map((_, i) => {
                  const mo = i + 1;
                  const cell = gridByYm[`${yr}-${mo}`];
                  const value = selectedSource ? (cell?.by_source?.[selectedSource] || 0) : (cell?.total || 0);
                  const status = !cell || cell.status === "outside" ? "outside" : (value > 0 ? "data" : "gap");
                  const sourceLines = cell && cell.total > 0
                    ? Object.entries(cell.by_source).map(([k, v]) => `${k}: ${v}`).join("\n")
                    : "";
                  const tooltip = selectedSource
                    ? (value > 0 ? `${selectedLabel}: ${value} rows` : status === "gap" ? `${selectedLabel}: no data` : "")
                    : cell?.total > 0 ? `${cell.total} rows, ${cell.employees} employees\n${sourceLines}` : status === "gap" ? "No data uploaded" : "";
                  return (
                    <td key={mo} className="p-1">
                      <div title={tooltip}
                        className={`w-16 h-9 rounded flex items-center justify-center font-semibold ${cellStyle(status)}`}>
                        {value > 0 ? value : (status === "gap" ? "—" : "")}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-green-500/30 border border-green-500/40 inline-block" /> Ada data</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-red-500/30 border border-red-500/40 inline-block" /> Belum diupload (gap)</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-gray-800/40 border border-gray-800 inline-block" /> Di luar rentang data</span>
        {data.observed_range.from && (
          <span className="text-gray-600">Data tersedia: {data.observed_range.from} s/d {data.observed_range.to}</span>
        )}
      </div>
    </div>
  );
}

export default function HRSetupPage() {
  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1e293b" }}>HRGA Setup — Data Coverage</h2>
        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
          Attendance upload coverage per source, year x month — moved here from Attendance Rate.
        </p>
      </div>
      <AttendanceCoverageSection />
    </div>
  );
}
