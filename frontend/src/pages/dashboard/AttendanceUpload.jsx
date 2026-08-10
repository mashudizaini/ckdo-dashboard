/**
 * AttendanceUpload.jsx
 * Four upload sources, all feeding the same Attendance Ratio reports:
 *   - Intercom (kind="intercom") — daily physical check-in/out log
 *     e.g. "Attendance JUN-2026-Intercom.xlsx"
 *   - Talenta  (kind="talenta")  — leave & business-trip days
 *     e.g. "Attendance MAY-JUN-2026 Talenta.xlsx"
 *   - Plant    (kind="plant")    — combined physical + leave log for plant
 *     employees, one workbook with a sheet per month, e.g. "Attendance Plant 2026.xlsx"
 *   - Office   (kind="office")   — combined physical + leave log for
 *     non-Plant/office staff, no department column, e.g. "Attendance 1-22 July 2025.xls"
 */

import { useState, useRef, useEffect } from "react";
import {
  Upload, FileSpreadsheet, CheckCircle2, XCircle,
  Loader2, RefreshCw, Clock, ChevronDown, ChevronUp,
  CalendarCheck, FilePlus, RotateCcw, AlertCircle, Briefcase, Factory, Building2
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { SortableTH, toggleSort, sortRows } from "@/components/SortableTH";

const API = "/api/v1/dashboard/hr/attendance";

const CONFIG = {
  intercom: {
    title: "Attendance Intercom",
    uploadPath: "/upload",
    logSource: "intercom",
    example: "Attendance JUN-2026-Intercom.xlsx",
    guidance: "Daily physical check-in/out log from the Intercom access-control system. Header in row 1, data starts at row 2. Existing records are updated based on Employee ID + date.",
    icon: CalendarCheck,
    columns: [
      { idx: 0,  name: "Name", required: false },
      { idx: 1,  name: "ID", required: true, note: "Employee ID" },
      { idx: 2,  name: "Department", required: false, note: "ignored — real dept comes from Team" },
      { idx: 3,  name: "Team", required: false, note: "used as department" },
      { idx: 4,  name: "Date", required: true },
      { idx: 5,  name: "Week", required: false },
      { idx: 6,  name: "Time Period", required: false },
      { idx: 7,  name: "Required Check-In Time", required: false },
      { idx: 8,  name: "Required Check-Out Time", required: false },
      { idx: 9,  name: "Actual Check-In Time", required: false },
      { idx: 10, name: "Actual Check-Out Time", required: false },
      { idx: 11, name: "Attendance Records", required: false, note: "ignored" },
      { idx: 12, name: "Required Work Hours", required: false, note: "ignored" },
      { idx: 13, name: "Total Work Hours", required: false, note: "ignored" },
      { idx: 14, name: "Attendance Status", required: false, note: "W/L/E/LE/A" },
    ],
    accent: {
      text: "text-teal-300", banner: "border-teal-500/20 bg-teal-500/5",
      dragActive: "border-teal-500 bg-teal-500/10", focus: "focus:border-teal-500",
      button: "bg-teal-600 hover:bg-teal-500",
    },
  },
  talenta: {
    title: "Attendance Talenta",
    uploadPath: "/upload-talenta",
    logSource: "talenta",
    example: "Attendance MAY-JUN-2026 Talenta.xlsx",
    guidance: "Leave and business-trip days from Talenta. Only rows with an Attendance Code or Time Off Code are stored — these explain days an employee wasn't physically checked in (leave is excluded from the attendance rate entirely; Business Trip counts as present).",
    icon: Briefcase,
    columns: [
      { idx: 0,  name: "Employee ID", required: true },
      { idx: 1,  name: "Full Name", required: false },
      { idx: 2,  name: "Branch", required: false, note: "ignored" },
      { idx: 3,  name: "department", required: true },
      { idx: 4,  name: "Job Position", required: false, note: "ignored" },
      { idx: 5,  name: "Date", required: true },
      { idx: 6,  name: "Shift", required: false, note: "ignored" },
      { idx: 7,  name: "Shift Code", required: false, note: "ignored" },
      { idx: 8,  name: "Shift Label", required: false, note: "ignored" },
      { idx: 9,  name: "Schedule Check In", required: false, note: "ignored" },
      { idx: 10, name: "Schedule Check Out", required: false, note: "ignored" },
      { idx: 11, name: "Attendance Code", required: "either", note: "row kept only if this or Time Off Code is filled" },
      { idx: 12, name: "Time Off Code", required: "either", note: "row kept only if this or Attendance Code is filled" },
    ],
    accent: {
      text: "text-indigo-300", banner: "border-indigo-500/20 bg-indigo-500/5",
      dragActive: "border-indigo-500 bg-indigo-500/10", focus: "focus:border-indigo-500",
      button: "bg-indigo-600 hover:bg-indigo-500",
    },
  },
  plant: {
    title: "Attendance Plant",
    uploadPath: "/upload-plant",
    logSource: "plant",
    example: "Attendance Plant 2026.xlsx",
    guidance: "Combined physical check-in/out AND leave/BT log for plant employees. Title in row 1, header in row 2, data from row 3. The workbook has one sheet per month (JAN–DEC) — every sheet is read and merged automatically, so upload the whole file at once. \"OFF\" in On Duty (or Remark = RDO) marks a scheduled shift rest day, excluded from the attendance rate like a weekend. Remark text (Annual/Sick/Unpaid Leave, Business Trip, Event Leave, Half Day Leave, Collective Leave) is mapped to the same leave codes Talenta uses; Late Attend and Back To Home Early set the attendance status instead; Overtime is informational only.",
    icon: Factory,
    columns: [
      { idx: 0,  name: "NO", required: false, note: "ignored" },
      { idx: 1,  name: "TEAM", required: false, note: "used as department" },
      { idx: 2,  name: "EMPLOYEE ID", required: true },
      { idx: 3,  name: "EMPLOYEE NAME", required: false },
      { idx: 4,  name: "DAY", required: false },
      { idx: 5,  name: "DATE", required: true },
      { idx: 6,  name: "ON DUTY", required: false, note: "\"OFF\" = scheduled shift rest day" },
      { idx: 7,  name: "OFF DUTY", required: false },
      { idx: 8,  name: "START OVERTIME", required: false, note: "ignored" },
      { idx: 9,  name: "CLOCK IN", required: false },
      { idx: 10, name: "CLOCK OUT", required: false },
      { idx: 11, name: "LATE (duration)", required: false, note: "ignored" },
      { idx: 12, name: "LATE (status)", required: false, note: "\"LATE ATTEND\" → attendance status L" },
      { idx: 13, name: "REMARK", required: false, note: "Annual/Sick/Unpaid/Collective Leave, Business Trip, Event Leave, Half Day Leave → leave code; RDO → day off; Back To Home Early → status E; Overtime → ignored" },
    ],
    accent: {
      text: "text-amber-300", banner: "border-amber-500/20 bg-amber-500/5",
      dragActive: "border-amber-500 bg-amber-500/10", focus: "focus:border-amber-500",
      button: "bg-amber-600 hover:bg-amber-500",
    },
  },
  office: {
    title: "Attendance Office",
    uploadPath: "/upload-office",
    logSource: "office",
    example: "Attendance 1-22 July 2025.xls",
    accept: ".xlsx,.xls",
    guidance: "Combined physical check-in/out AND leave log for non-Plant/office staff. No Department/Team column at all — department always comes from the Employee master. Columns are matched by header text (case-insensitive), not fixed position, so every worksheet in the file is read even if one sheet has a slightly different layout (e.g. a per-employee addendum sheet). Legacy .xls files are supported. Remark text (Annual/Sick/Unpaid/Maternity Leave, BT, half day / after lunch / before lunch variants, Replacement Day Off) is mapped to leave codes; unrecognized remarks are kept as a note only and don't affect attendance status.",
    icon: Building2,
    columns: [
      { idx: "No.", name: "Employee ID", required: true },
      { idx: "Name", name: "Employee Name", required: false },
      { idx: "Date", name: "Date", required: true, note: "DD/MM/YYYY or Excel date" },
      { idx: "Timetable", name: "Shift group", required: false, note: "optional — not every sheet has this column" },
      { idx: "On duty", name: "Scheduled check-in", required: false },
      { idx: "Off duty", name: "Scheduled check-out", required: false },
      { idx: "Clock In", name: "Actual check-in", required: false, note: "\"OFF\" or blank = not recorded" },
      { idx: "Clock Out", name: "Actual check-out", required: false, note: "\"OFF\" or blank = not recorded" },
      { idx: "Remarks", name: "Remarks", required: false, note: "leave/BT text, or \"Replacement Day Off\" for a scheduled rest day; anything else kept as a note only" },
    ],
    accent: {
      text: "text-rose-300", banner: "border-rose-500/20 bg-rose-500/5",
      dragActive: "border-rose-500 bg-rose-500/10", focus: "focus:border-rose-500",
      button: "bg-rose-600 hover:bg-rose-500",
    },
  },
};

export default function AttendanceUpload({ kind = "intercom" }) {
  const cfg = CONFIG[kind] ?? CONFIG.intercom;

  const [file,        setFile]        = useState(null);
  const [dragging,    setDragging]    = useState(false);
  const [notes,       setNotes]       = useState("");
  const [uploading,   setUploading]   = useState(false);
  const [result,      setResult]      = useState(null);
  const [error,       setError]       = useState(null);
  const [logs,        setLogs]        = useState([]);
  const [showLogs,    setShowLogs]    = useState(false);
  const [showCols,    setShowCols]    = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };
  const inputRef = useRef(null);
  const { token } = useAuthStore();

  const headers = { Authorization: `Bearer ${token}` };

  const loadLogs = async () => {
    setLoadingLogs(true);
    try {
      const res = await fetch(`${API}/upload-logs?source=${cfg.logSource}`, { headers });
      if (res.ok) setLogs(await res.json());
    } catch (_) {}
    finally { setLoadingLogs(false); }
  };

  useEffect(() => { loadLogs(); }, []); // eslint-disable-line

  const acceptExts = (cfg.accept || ".xlsx,.xlsm").split(",");
  const onFileSelect = (f) => {
    if (!f) return;
    if (!acceptExts.some((ext) => f.name.endsWith(ext))) {
      setError(`File must be ${acceptExts.join(" or ")} format`); return;
    }
    setFile(f); setError(null); setResult(null);
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragging(false);
    onFileSelect(e.dataTransfer.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true); setError(null); setResult(null);

    const fd = new FormData();
    fd.append("file", file);
    if (notes.trim()) fd.append("notes", notes.trim());

    try {
      const res = await fetch(`${API}${cfg.uploadPath}`, {
        method: "POST",
        headers,
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      setResult(data);
      setFile(null); setNotes("");
      if (inputRef.current) inputRef.current.value = "";
      await loadLogs();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }); }
    catch (_) { return iso; }
  };

  const fileSizeKB = file ? (file.size / 1024).toFixed(1) : 0;
  const Icon = cfg.icon;

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <h3 className={`flex items-center gap-2 text-sm font-semibold ${cfg.accent.text}`}>
        <Icon size={15} /> {cfg.title}
      </h3>

      {/* ── Guidance ────────────────────────────────────────────────────────── */}
      <div className={`flex gap-3 rounded-xl border px-4 py-3 text-sm ${cfg.accent.banner} ${cfg.accent.text}`}>
        <AlertCircle size={15} className="mt-0.5 shrink-0" />
        <span>
          {cfg.guidance} Example file: <strong>{cfg.example}</strong>.
        </span>
      </div>

      {/* ── Required columns ───────────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900">
        <button
          onClick={() => setShowCols((v) => !v)}
          className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-gray-300 hover:text-white transition-colors"
        >
          <div className="flex items-center gap-2">
            <FileSpreadsheet size={14} className="text-gray-500" />
            Required Columns ({cfg.columns.length})
          </div>
          {showCols ? <ChevronUp size={15} className="text-gray-500" /> : <ChevronDown size={15} className="text-gray-500" />}
        </button>
        {showCols && (
          <div className="border-t border-gray-800 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-800/50">
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Col</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Column Name</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Required</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {cfg.columns.map((c) => (
                  <tr key={c.idx}>
                    <td className="px-3 py-2 text-gray-500">{c.idx}</td>
                    <td className="px-3 py-2 text-gray-200 font-medium">{c.name}</td>
                    <td className="px-3 py-2">
                      {c.required === true && <span className="text-red-400 font-semibold">Yes</span>}
                      {c.required === "either" && <span className="text-amber-400 font-semibold">One of</span>}
                      {c.required === false && <span className="text-gray-600">No</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-500">{c.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Drop zone ───────────────────────────────────────────────────────── */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed py-8 cursor-pointer transition-all select-none
          ${dragging
            ? cfg.accent.dragActive
            : file
            ? "border-green-500/50 bg-green-500/5"
            : "border-gray-700 bg-gray-900 hover:border-gray-600 hover:bg-gray-800/50"}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={cfg.accept || ".xlsx,.xlsm"}
          className="hidden"
          onChange={(e) => onFileSelect(e.target.files[0])}
        />

        {file ? (
          <>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-green-500/15">
              <FileSpreadsheet size={24} className="text-green-400" />
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold text-green-300">{file.name}</p>
              <p className="text-xs text-gray-500 mt-1">{fileSizeKB} KB — click to change file</p>
            </div>
          </>
        ) : (
          <>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-800">
              <Upload size={22} className="text-gray-500" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-gray-300">Drag & drop Excel file here</p>
              <p className="text-xs text-gray-600 mt-1">or click to select file (.xlsx / .xlsm)</p>
            </div>
          </>
        )}
      </div>

      {/* ── Notes ───────────────────────────────────────────────────────────── */}
      <div>
        <label className="mb-1.5 block text-xs font-medium text-gray-500">
          Upload notes <span className="text-gray-700">(optional — e.g. "{cfg.title} June 2026")</span>
        </label>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Upload description..."
          className={`w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none transition-colors ${cfg.accent.focus}`}
        />
      </div>

      {/* ── Upload button ───────────────────────────────────────────────────── */}
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition-all
          ${!file || uploading
            ? "cursor-not-allowed bg-gray-700 opacity-50"
            : `${cfg.accent.button} active:scale-95`}`}
      >
        {uploading
          ? <><Loader2 size={15} className="animate-spin" /> Uploading...</>
          : <><Upload size={15} /> Upload & Save to Database</>}
      </button>

      {/* ── Error ───────────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex gap-3 rounded-xl border border-red-500/30 bg-red-500/8 px-4 py-3 text-sm text-red-300">
          <XCircle size={15} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Result ──────────────────────────────────────────────────────────── */}
      {result && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 size={18} className="text-green-400" />
            <span className="text-sm font-semibold text-green-300">{result.message}</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { icon: CalendarCheck, color: "text-blue-400",  bg: "bg-blue-500/10",  label: "Total Read",  val: result.total_rows },
              { icon: FilePlus,      color: "text-green-400", bg: "bg-green-500/10", label: "New Records", val: result.inserted },
              { icon: RotateCcw,     color: "text-amber-400", bg: "bg-amber-500/10", label: "Updated",     val: result.updated },
            ].map(({ icon: Ic, color, bg, label, val }) => (
              <div key={label} className="rounded-lg border border-white/5 bg-white/3 p-3 text-center">
                <div className={`mx-auto mb-1.5 flex h-7 w-7 items-center justify-center rounded-lg ${bg}`}>
                  <Ic size={14} className={color} />
                </div>
                <div className={`text-xl font-bold ${color}`}>{val}</div>
                <div className="text-xs text-gray-500 mt-0.5">{label}</div>
              </div>
            ))}
          </div>
          {result.skipped_names?.length > 0 && (
            <div className="mt-3 flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>
                Skipped {result.skipped_names.length} employee(s) with no ID in the file — fix the source file
                or add manually via Data Correction: <strong>{result.skipped_names.join(", ")}</strong>
              </span>
            </div>
          )}
          <p className="text-xs text-gray-600 mt-3">Batch ID: {result.batch_id}</p>
        </div>
      )}

      {/* ── Upload history ──────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900">
        <button
          onClick={() => { setShowLogs((v) => !v); if (!showLogs) loadLogs(); }}
          className="flex w-full items-center justify-between px-5 py-3.5 text-sm font-medium text-gray-300 hover:text-white transition-colors"
        >
          <div className="flex items-center gap-2">
            <Clock size={14} className="text-gray-500" />
            Upload History
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); loadLogs(); }}
              className="rounded-md p-1 text-gray-600 hover:text-gray-400 hover:bg-gray-800"
              title="Refresh"
            >
              <RefreshCw size={12} className={loadingLogs ? "animate-spin" : ""} />
            </button>
            {showLogs ? <ChevronUp size={15} className="text-gray-500" /> : <ChevronDown size={15} className="text-gray-500" />}
          </div>
        </button>

        {showLogs && (
          <div className="border-t border-gray-800 overflow-x-auto">
            {logs.length === 0 ? (
              <p className="px-5 py-6 text-center text-xs text-gray-600">No upload history yet</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-800/50">
                    {[["Upload Time", "uploaded_at"], ["File", "filename"], ["Total", "total_rows"], ["New", "inserted"], ["Update", "updated"], ["By", "uploaded_by"], ["Notes", "notes"]].map(([h, field]) => (
                      <SortableTH key={h} label={h} field={field} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {sortRows(logs, sortBy, sortDir, ["total_rows", "inserted", "updated"]).map((l) => (
                    <tr key={l.batch_id} className="hover:bg-gray-800/30 transition-colors">
                      <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{fmtDate(l.uploaded_at)}</td>
                      <td className="px-3 py-2.5 text-gray-300 max-w-[160px] truncate">{l.filename}</td>
                      <td className="px-3 py-2.5 text-gray-400 text-center">{l.total_rows}</td>
                      <td className="px-3 py-2.5 text-green-400 font-semibold text-center">{l.inserted}</td>
                      <td className="px-3 py-2.5 text-amber-400 font-semibold text-center">{l.updated}</td>
                      <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{l.uploaded_by}</td>
                      <td className="px-3 py-2.5 text-gray-600 max-w-[140px] truncate">{l.notes || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
