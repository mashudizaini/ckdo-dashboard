/**
 * AttendanceUpload.jsx
 * Upload file Excel absensi → insert/update ke database.
 * Format: "Attendance HO.xlsx" (header baris 1, data mulai baris 2)
 * Kolom: Name | ID | Department | Date | Week | Time Period |
 *        Check-In | Check-Out | Actual Check-In | Actual Check-Out | Notes
 */

import { useState, useRef, useEffect } from "react";
import {
  Upload, FileSpreadsheet, CheckCircle2, XCircle,
  Loader2, RefreshCw, Clock, ChevronDown, ChevronUp,
  CalendarCheck, FilePlus, RotateCcw, AlertCircle
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/hr/attendance";

export default function AttendanceUpload() {
  const [file,        setFile]        = useState(null);
  const [dragging,    setDragging]    = useState(false);
  const [notes,       setNotes]       = useState("");
  const [uploading,   setUploading]   = useState(false);
  const [result,      setResult]      = useState(null);
  const [error,       setError]       = useState(null);
  const [logs,        setLogs]        = useState([]);
  const [showLogs,    setShowLogs]    = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const inputRef = useRef(null);
  const { token } = useAuthStore();

  const headers = { Authorization: `Bearer ${token}` };

  const loadLogs = async () => {
    setLoadingLogs(true);
    try {
      const res = await fetch(`${API}/upload-logs`, { headers });
      if (res.ok) setLogs(await res.json());
    } catch (_) {}
    finally { setLoadingLogs(false); }
  };

  useEffect(() => { loadLogs(); }, []); // eslint-disable-line

  const onFileSelect = (f) => {
    if (!f) return;
    if (!f.name.endsWith(".xlsx") && !f.name.endsWith(".xlsm")) {
      setError("File must be .xlsx or .xlsm format"); return;
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
      const res = await fetch(`${API}/upload`, {
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
    try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); }
    catch (_) { return iso; }
  };

  const fileSizeKB = file ? (file.size / 1024).toFixed(1) : 0;

  return (
    <div className="space-y-5">

      {/* ── Panduan ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-3 rounded-xl border border-teal-500/20 bg-teal-500/5 px-4 py-3 text-sm text-teal-300">
        <AlertCircle size={15} className="mt-0.5 shrink-0" />
        <span>
          Upload attendance Excel file (format <strong>Attendance HO.xlsx</strong>).
          Header in row 1, data starts at row 2. Required columns: <strong>ID</strong> and <strong>Date</strong>.
          Existing records will be updated based on <strong>ID + date</strong>.
        </span>
      </div>

      {/* ── Drop zone ───────────────────────────────────────────────────────── */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed py-10 cursor-pointer transition-all select-none
          ${dragging
            ? "border-teal-500 bg-teal-500/10"
            : file
            ? "border-green-500/50 bg-green-500/5"
            : "border-gray-700 bg-gray-900 hover:border-gray-600 hover:bg-gray-800/50"}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xlsm"
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

      {/* ── Catatan ─────────────────────────────────────────────────────────── */}
      <div>
        <label className="mb-1.5 block text-xs font-medium text-gray-500">
          Upload notes <span className="text-gray-700">(optional — e.g. "Attendance March 2026")</span>
        </label>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Upload description..."
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-teal-500 transition-colors"
        />
      </div>

      {/* ── Tombol Upload ───────────────────────────────────────────────────── */}
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition-all
          ${!file || uploading
            ? "cursor-not-allowed bg-gray-700 opacity-50"
            : "bg-teal-600 hover:bg-teal-500 active:scale-95"}`}
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

      {/* ── Hasil Upload ─────────────────────────────────────────────────────── */}
      {result && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 size={18} className="text-green-400" />
            <span className="text-sm font-semibold text-green-300">{result.message}</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { icon: CalendarCheck, color: "text-blue-400",  bg: "bg-blue-500/10",  label: "Total Read",    val: result.total_rows },
              { icon: FilePlus,      color: "text-green-400", bg: "bg-green-500/10", label: "New Records",   val: result.inserted },
              { icon: RotateCcw,     color: "text-amber-400", bg: "bg-amber-500/10", label: "Updated",       val: result.updated },
            ].map(({ icon: Icon, color, bg, label, val }) => (
              <div key={label} className="rounded-lg border border-white/5 bg-white/3 p-3 text-center">
                <div className={`mx-auto mb-1.5 flex h-7 w-7 items-center justify-center rounded-lg ${bg}`}>
                  <Icon size={14} className={color} />
                </div>
                <div className={`text-xl font-bold ${color}`}>{val}</div>
                <div className="text-xs text-gray-500 mt-0.5">{label}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-3">Batch ID: {result.batch_id}</p>
        </div>
      )}

      {/* ── Riwayat Upload ──────────────────────────────────────────────────── */}
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
                    {["Upload Time", "File", "Total", "New", "Update", "By", "Notes"].map((h) => (
                      <th key={h} className="px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {logs.map((l) => (
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
