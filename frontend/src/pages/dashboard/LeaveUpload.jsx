import { useState, useRef, useEffect } from "react";
import { Upload, Loader2, CheckCircle, X, FileText } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/hr/leave";

export default function LeaveUpload() {
  const [file, setFile] = useState(null);
  const [notes, setNotes] = useState("");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const inputRef = useRef(null);

  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API}/history`, { headers });
      if (res.ok) setHistory(await res.json());
    } catch (_) {}
  };

  useEffect(() => { fetchHistory(); }, []);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.match(/\.(xlsx|xlsm)$/i)) {
      setError("File must be .xlsx or .xlsm format");
      return;
    }
    setFile(f);
    setError("");
    setResult(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError("");
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (notes.trim()) fd.append("notes", notes.trim());

      const res = await fetch(`${API}/upload`, {
        method: "POST",
        headers,
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      setResult(data);
      setFile(null);
      setNotes("");
      if (inputRef.current) inputRef.current.value = "";
      fetchHistory();
    } catch (e) {
      setError(e?.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-gray-300 mb-1">
          Upload Talenta Attendance Excel file (leave/time-off data)
        </p>
        <p className="text-xs text-gray-500 mb-3">
          System reads column "Time Off Code" to extract leave records (SL, AL, EM, UL, ML, BT).
        </p>

        <div
          onClick={() => inputRef.current?.click()}
          className="rounded-xl border-2 border-dashed border-gray-700 hover:border-blue-500/40 p-6 text-center cursor-pointer transition-colors"
        >
          <input ref={inputRef} type="file" accept=".xlsx,.xlsm" onChange={handleFile} className="hidden" />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-sm text-gray-300">
              <FileText size={16} className="text-blue-400" />
              <span className="font-medium">{file.name}</span>
              <span className="text-gray-500">({(file.size / 1024).toFixed(0)} KB)</span>
            </div>
          ) : (
            <>
              <Upload size={24} className="mx-auto mb-2 text-gray-600" />
              <p className="text-sm text-gray-400">Drag & drop Excel file here</p>
              <p className="text-xs text-gray-600">or click to select file (.xlsx / .xlsm)</p>
            </>
          )}
        </div>
      </div>

      <div>
        <label className="text-xs text-gray-500 mb-1 block">Upload notes (optional)</label>
        <input value={notes} onChange={e => setNotes(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
          placeholder='e.g. "Leave data May-Jun 2026"' />
      </div>

      <button onClick={handleUpload} disabled={!file || uploading}
        className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2 text-sm font-semibold text-white transition-colors">
        {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
        {uploading ? "Uploading..." : "Upload & Process"}
      </button>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <X size={14} /> {error}
        </div>
      )}

      {result && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2 text-green-400 text-sm font-semibold mb-3">
            <CheckCircle size={14} /> Upload successful
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Total Read", value: result.total_rows },
              { label: "New Records", value: result.inserted },
              { label: "Updated", value: result.updated },
            ].map(c => (
              <div key={c.label} className="bg-gray-800/50 rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-gray-200">{c.value}</p>
                <p className="text-xs text-gray-500">{c.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload History */}
      <div>
        <h4 className="text-sm font-semibold text-gray-300 mb-2">Upload History</h4>
        {history.length === 0 ? (
          <p className="text-xs text-gray-600 py-4 text-center">No upload history yet</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-800/60">
                  {["Upload Time", "File", "Total", "New", "Update", "By", "Notes"].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {history.map(h => (
                  <tr key={h.batch_id} className="hover:bg-gray-800/40">
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{h.uploaded_at?.replace("T", " ").slice(0, 19)}</td>
                    <td className="px-3 py-2 text-gray-300 max-w-[200px] truncate">{h.filename}</td>
                    <td className="px-3 py-2 text-gray-300 font-medium">{h.total_rows}</td>
                    <td className="px-3 py-2 text-green-400">{h.inserted}</td>
                    <td className="px-3 py-2 text-blue-400">{h.updated}</td>
                    <td className="px-3 py-2 text-gray-500">{h.uploaded_by}</td>
                    <td className="px-3 py-2 text-gray-500 max-w-[200px] truncate">{h.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
