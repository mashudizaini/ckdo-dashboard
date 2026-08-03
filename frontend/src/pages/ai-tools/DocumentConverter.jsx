import { useState, useRef, useEffect, useCallback } from "react";
import {
  FileStack, Upload, Loader2, Download, Send, AlertTriangle, CheckCircle2, FileText,
  FolderOpen, X, Save, Clock, Square, Trash2, History,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const ACCEPTED = ".pdf,.docx,.doc,.png,.jpg,.jpeg";
const POLL_MS = 2500;

const STATUS_STYLE = {
  pending:    { label: "Queued",     color: "text-gray-400",   bar: "bg-gray-600" },
  processing: { label: "Processing", color: "text-teal-400",   bar: "bg-teal-500" },
  done:       { label: "Done",       color: "text-green-400",  bar: "bg-green-500" },
  error:      { label: "Failed",     color: "text-red-400",    bar: "bg-red-500" },
  stopped:    { label: "Stopped",    color: "text-amber-400",  bar: "bg-amber-500" },
};

export default function DocumentConverter() {
  const { token } = useAuthStore();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileRef = useRef(null);

  // Conversion jobs — dispatched to a Celery background task and polled
  // from here, so a job keeps running (and its progress keeps being
  // recorded) even if this tab is closed or the session logs out; reopening
  // the page just re-fetches the same history instead of losing it.
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [markdownDirty, setMarkdownDirty] = useState(false);

  const [departments, setDepartments] = useState(["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]);
  const [form, setForm] = useState({ source: "", title: "", department: "General" });
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState(null);

  // Reopen-existing-KB-document flow
  const [existingDocs, setExistingDocs] = useState([]);
  const [selectedDocKey, setSelectedDocKey] = useState("");
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [editingExisting, setEditingExisting] = useState(null); // { source, title } of the doc currently loaded for editing, or null

  const headers = { Authorization: `Bearer ${token}` };
  const anyActive = jobs.some((j) => j.status === "pending" || j.status === "processing");

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/ai/document-converter/jobs", { headers });
      if (res.ok) setJobs(await res.json());
    } catch (_) {} finally { setJobsLoading(false); }
  }, [token]); // eslint-disable-line

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/v1/ai/chatbot/status", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.departments?.length) setDepartments(data.departments);
        }
      } catch (_) {}
      try {
        const res = await fetch("/api/v1/ai/chatbot/documents", { headers });
        if (res.ok) setExistingDocs(await res.json());
      } catch (_) {}
    })();
    fetchJobs();
  }, [token]); // eslint-disable-line

  // Poll while any job is queued/processing — this is what makes the
  // history list feel "live" without needing a persistent connection of
  // its own (unlike the old SSE design, a dropped poll just resumes next
  // tick, it never loses the job).
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(fetchJobs, POLL_MS);
    return () => clearInterval(t);
  }, [anyActive, fetchJobs]);

  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null;

  // When the selected job finishes, pull its full markdown (the list
  // endpoint omits it to keep the history payload light).
  useEffect(() => {
    if (!selectedJobId) return;
    const job = jobs.find((j) => j.id === selectedJobId);
    if (!job || job.status !== "done" || markdownDirty) return;
    (async () => {
      try {
        const res = await fetch(`/api/v1/ai/document-converter/jobs/${selectedJobId}`, { headers });
        if (res.ok) {
          const data = await res.json();
          setMarkdown(data.markdown || "");
        }
      } catch (_) {}
    })();
  }, [selectedJobId, jobs]); // eslint-disable-line

  const handleFileChange = (f) => {
    setFile(f);
    setUploadError(null);
    if (f) setForm((p) => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, "") }));
  };

  const handleConvert = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/v1/ai/document-converter/convert", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
      setSelectedJobId(data.job_id);
      setMarkdown("");
      setMarkdownDirty(false);
      setEditingExisting(null);
      setSelectedDocKey("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      fetchJobs();
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleStopJob = async (jobId) => {
    try {
      await fetch(`/api/v1/ai/document-converter/jobs/${jobId}/stop`, { method: "POST", headers });
      fetchJobs();
    } catch (_) {}
  };

  const handleDeleteJob = async (jobId) => {
    if (!confirm("Remove this job from history?")) return;
    try {
      const res = await fetch(`/api/v1/ai/document-converter/jobs/${jobId}`, { method: "DELETE", headers });
      if (res.ok) {
        if (selectedJobId === jobId) { setSelectedJobId(null); setMarkdown(""); }
        fetchJobs();
      }
    } catch (_) {}
  };

  const handleSelectJob = (job) => {
    setSelectedJobId(job.id);
    setMarkdownDirty(false);
    setEditingExisting(null);
    setSelectedDocKey("");
    setForm((p) => ({ ...p, title: p.title || job.filename.replace(/\.[^.]+$/, "") }));
    if (job.status !== "done") setMarkdown("");
  };

  const handleLoadExisting = async () => {
    if (!selectedDocKey) return;
    const [source, title] = JSON.parse(selectedDocKey);
    setLoadingDoc(true);
    try {
      const params = new URLSearchParams({ source, title });
      const res = await fetch(`/api/v1/ai/chatbot/documents/content?${params}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal memuat dokumen");
      const doc = existingDocs.find((d) => d.source === source && d.title === title);
      setMarkdown(data.content);
      setMarkdownDirty(false);
      setForm({ source, title, department: doc?.department || "General" });
      setEditingExisting({ source, title });
      setSelectedJobId(null);
      setSendMsg(null);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setLoadingDoc(false);
    }
  };

  const handleCancelEdit = () => {
    setEditingExisting(null);
    setSelectedDocKey("");
    setMarkdown("");
    setMarkdownDirty(false);
    setForm({ source: "", title: "", department: "General" });
  };

  const handleDownload = () => {
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${form.title || "document"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSendToKB = async () => {
    if (!form.source.trim() || !form.title.trim() || !markdown.trim()) {
      setSendMsg({ type: "error", text: "Isi Source, Title, dan pastikan hasil konversi tidak kosong" });
      return;
    }
    setSending(true);
    setSendMsg(null);
    try {
      if (editingExisting) {
        const params = new URLSearchParams({ source: editingExisting.source, title: editingExisting.title });
        const delRes = await fetch(`/api/v1/ai/chatbot/documents?${params}`, { method: "DELETE", headers });
        if (!delRes.ok) {
          const d = await delRes.json().catch(() => ({}));
          throw new Error(d.detail || "Gagal menghapus versi lama sebelum menyimpan perubahan");
        }
      }

      const fd = new FormData();
      fd.append("source", form.source.trim());
      fd.append("title", form.title.trim());
      fd.append("text", markdown);
      fd.append("department", form.department);
      const res = await fetch("/api/v1/ai/chatbot/documents", { method: "POST", headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal mengirim ke Knowledge Base");
      setSendMsg({ type: "success", text: `✓ ${editingExisting ? "Perubahan disimpan — " : ""}${data.message}` });
      setEditingExisting(editingExisting ? { source: form.source.trim(), title: form.title.trim() } : null);
      try {
        const listRes = await fetch("/api/v1/ai/chatbot/documents", { headers });
        if (listRes.ok) setExistingDocs(await listRes.json());
      } catch (_) {}
    } catch (e) {
      setSendMsg({ type: "error", text: e.message });
    } finally {
      setSending(false);
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return "-";
    try { return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  };

  return (
    <div className="flex flex-col h-full p-6">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FileStack className="text-teal-400" size={26} />
          Document Converter
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Konversi PDF, DOCX, atau gambar (termasuk hasil scan) ke Markdown terstruktur — tabel tetap rapi, cocok untuk Knowledge Base AI Chatbot.
          Konversi berjalan di background — aman ditinggal atau tutup tab, progress tersimpan.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 flex-1 min-h-0">
        {/* Left: upload + jobs history + KB transfer */}
        <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 p-5 gap-4 overflow-y-auto">
          <div>
            <label className="text-xs text-gray-500 mb-2 block">File (PDF / DOCX / PNG / JPG)</label>
            <div
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-dashed border-gray-700 hover:border-teal-500 transition-colors p-5 text-center cursor-pointer"
            >
              <input ref={fileRef} type="file" accept={ACCEPTED} className="hidden"
                onChange={(e) => handleFileChange(e.target.files?.[0] || null)} />
              <Upload size={20} className="mx-auto text-gray-600 mb-2" />
              <p className="text-sm text-gray-300">{file ? file.name : "Klik untuk pilih file"}</p>
              {file && <p className="text-xs text-gray-600 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>}
            </div>
          </div>

          <button
            onClick={handleConvert}
            disabled={!file || uploading}
            className="flex items-center justify-center gap-2 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
          >
            {uploading ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
            {uploading ? "Mengirim..." : "Konversi ke Markdown"}
          </button>

          {uploadError && (
            <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
              <AlertTriangle size={12} /> {uploadError}
            </div>
          )}

          {/* Jobs history — done/in-progress list with per-job progress % */}
          <div className="border-t border-gray-800 pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <History size={12} /> Conversion Jobs ({jobs.length})
              </p>
              {anyActive && <span className="text-[10px] text-teal-400 flex items-center gap-1"><Loader2 size={10} className="animate-spin" />live</span>}
            </div>
            {jobsLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
            ) : jobs.length === 0 ? (
              <p className="text-xs text-gray-600 py-4 text-center">No conversion jobs yet.</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {jobs.map((job) => {
                  const st = STATUS_STYLE[job.status] || STATUS_STYLE.pending;
                  const isSelected = job.id === selectedJobId;
                  return (
                    <button key={job.id} onClick={() => handleSelectJob(job)}
                      className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                        isSelected ? "border-teal-500 bg-teal-500/5" : "border-gray-800 hover:border-gray-700 bg-gray-800/30"
                      }`}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium text-gray-200 truncate flex-1">{job.filename}</p>
                        <span className={`text-[10px] font-semibold shrink-0 ${st.color}`}>{st.label}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1.5">
                        <div className="h-1 flex-1 rounded-full bg-gray-800 overflow-hidden">
                          <div className={`h-full ${st.bar} transition-all`} style={{ width: `${job.progress_percent || 0}%` }} />
                        </div>
                        <span className="text-[10px] text-gray-500 shrink-0 w-8 text-right">{job.progress_percent || 0}%</span>
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <p className="text-[10px] text-gray-600 truncate flex-1">
                          {job.status === "error" ? job.error_message : job.status_message}
                          {job.total_pages > 1 && ` · page ${job.current_page || 0}/${job.total_pages}`}
                        </p>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] text-gray-600 flex items-center gap-1"><Clock size={9} />{fmtDate(job.created_at)}</span>
                          {(job.status === "pending" || job.status === "processing") ? (
                            <span onClick={(e) => { e.stopPropagation(); handleStopJob(job.id); }}
                              className="text-gray-600 hover:text-amber-400 cursor-pointer" title="Stop">
                              <Square size={10} />
                            </span>
                          ) : (
                            <span onClick={(e) => { e.stopPropagation(); handleDeleteJob(job.id); }}
                              className="text-gray-600 hover:text-red-400 cursor-pointer" title="Delete">
                              <Trash2 size={10} />
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="border-t border-gray-800 pt-4">
            {editingExisting ? (
              <div className="rounded-lg border border-amber-700/40 bg-amber-500/10 px-3 py-2.5 flex items-center justify-between gap-2 mb-3">
                <p className="text-xs text-amber-400 flex items-center gap-1.5">
                  <FolderOpen size={13} /> Mengedit: <span className="font-semibold">{editingExisting.title}</span>
                </p>
                <button onClick={handleCancelEdit} title="Batal edit"
                  className="text-amber-400 hover:text-amber-300 shrink-0">
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div className="mb-3">
                <label className="text-xs text-gray-500 mb-2 block">Or open & edit an existing KB document</label>
                <div className="flex gap-2">
                  <select value={selectedDocKey} onChange={(e) => setSelectedDocKey(e.target.value)}
                    className="flex-1 rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 outline-none focus:border-teal-500 cursor-pointer">
                    <option value="">Pilih dokumen...</option>
                    {existingDocs.map((d) => (
                      <option key={`${d.source}::${d.title}`} value={JSON.stringify([d.source, d.title])}>
                        {d.title} ({d.chunks} chunk)
                      </option>
                    ))}
                  </select>
                  <button onClick={handleLoadExisting} disabled={!selectedDocKey || loadingDoc}
                    className="flex items-center gap-1.5 rounded-md border border-gray-700 bg-gray-800 hover:border-teal-500 disabled:opacity-40 px-3 py-2 text-xs font-medium text-gray-300 transition-colors shrink-0">
                    {loadingDoc ? <Loader2 size={13} className="animate-spin" /> : <FolderOpen size={13} />} Buka
                  </button>
                </div>
              </div>
            )}

            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              {editingExisting ? "Edit Dokumen KB" : "Transfer to Knowledge Base"}
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Source / Category</label>
                <input value={form.source} onChange={(e) => setForm((p) => ({ ...p, source: e.target.value }))}
                  placeholder="e.g. Employee Benefit" className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-teal-500" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Title</label>
                <input value={form.title} onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                  placeholder="e.g. Employee Benefit 2025" className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-teal-500" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Department</label>
                <select value={form.department} onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}
                  className="w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 outline-none focus:border-teal-500 cursor-pointer">
                  {departments.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>

              <div className="flex gap-2">
                <button onClick={handleDownload} disabled={!markdown}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-md border border-gray-700 bg-gray-800 hover:border-teal-500 disabled:opacity-40 px-3 py-2 text-xs font-medium text-gray-300 transition-colors">
                  <Download size={13} /> Download .md
                </button>
                <button onClick={handleSendToKB} disabled={!markdown || sending}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-md bg-teal-600 hover:bg-teal-700 disabled:opacity-40 px-3 py-2 text-xs font-semibold text-white transition-colors">
                  {sending ? <Loader2 size={13} className="animate-spin" /> : editingExisting ? <Save size={13} /> : <Send size={13} />}
                  {editingExisting ? "Simpan Perubahan" : "Kirim ke KB Chatbot"}
                </button>
              </div>

              {sendMsg && (
                <div className={`rounded-md px-3 py-2 text-xs font-medium flex items-center gap-2 ${sendMsg.type === "error" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-green-500/10 border border-green-500/30 text-green-400"}`}>
                  {sendMsg.type === "success" && <CheckCircle2 size={12} />} {sendMsg.text}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: markdown preview/edit */}
        <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Result (Markdown){selectedJob && <span className="text-gray-600 normal-case font-normal"> — {selectedJob.filename}</span>}
            </p>
            {markdown && <p className="text-xs text-gray-600">{markdown.length.toLocaleString()} karakter — bisa diedit sebelum dikirim</p>}
          </div>
          {selectedJob && selectedJob.status !== "done" ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6">
              {selectedJob.status === "error" ? (
                <>
                  <AlertTriangle size={26} className="text-red-500" />
                  <p className="text-sm text-red-400">{selectedJob.error_message || "Conversion failed"}</p>
                </>
              ) : selectedJob.status === "stopped" ? (
                <p className="text-sm text-amber-400">Job was stopped.</p>
              ) : (
                <>
                  <Loader2 size={26} className="animate-spin text-teal-400" />
                  <p className="text-sm text-gray-300">{selectedJob.status_message || "Processing…"}</p>
                  {selectedJob.total_pages > 1 && (
                    <p className="text-xs text-gray-600">Page {selectedJob.current_page || 0} of {selectedJob.total_pages} — {selectedJob.progress_percent || 0}%</p>
                  )}
                  <p className="text-xs text-gray-700 max-w-xs">Bisa beberapa menit untuk dokumen hasil scan — aman ditinggal, tab ini boleh ditutup.</p>
                </>
              )}
            </div>
          ) : (
            <textarea
              value={markdown}
              onChange={(e) => { setMarkdown(e.target.value); setMarkdownDirty(true); }}
              placeholder="Konversi sebuah file, atau pilih job/dokumen yang sudah ada — hasilnya akan muncul di sini..."
              className="flex-1 w-full resize-none bg-gray-950 text-gray-200 text-xs font-mono p-4 outline-none placeholder-gray-700"
            />
          )}
        </div>
      </div>
    </div>
  );
}
