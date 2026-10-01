import { useState, useRef, useEffect, useCallback } from "react";
import {
  Languages, Upload, Loader2, Download, AlertTriangle, CheckCircle2, Square, Trash2, History, X,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// A simple front end over the Document Converter pipeline
// (/api/v1/ai/document-converter): upload -> background conversion ->
// translation chained by the backend (translate_target on /convert) ->
// download. Jobs live in the same table, so a job started here also shows up
// in Setup > AI > Document Converter, where its glossary can be edited.

const ACCEPTED = ".pdf,.docx,.doc,.png,.jpg,.jpeg";
const POLL_MS = 2500;

// ocr: "korean" switches PDF text extraction to Tesseract's Korean pack
// (see OCR_LANGUAGES in DocumentConverter.jsx); everything else uses the
// default pipeline.
const DIRECTIONS = [
  { value: "en-id", label: "English → Indonesian", target: "id", ocr: "auto" },
  { value: "id-en", label: "Indonesian → English", target: "en", ocr: "auto" },
  { value: "ko-en", label: "Korean → English",     target: "en", ocr: "korean" },
  { value: "ko-id", label: "Korean → Indonesian",  target: "id", ocr: "korean" },
];

const MODELS = [
  { value: "onprem",    label: "On-premise (Qwen)", hint: "Free; the document never leaves the company network." },
  { value: "anthropic", label: "Claude",            hint: "Higher quality on difficult or technical text; billed per use." },
];

const LANG_LABEL = { en: "English", id: "Indonesian" };

const OUTPUT_FORMATS = [
  { value: "docx", label: "Word (.docx)" },
  { value: "pdf",  label: "PDF" },
];

// Prefer the RFC 5987 filename* (keeps Korean names intact) over the ASCII
// fallback filename=.
function filenameFrom(res, fallback) {
  const cd = res.headers.get("Content-Disposition") || "";
  const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try { return decodeURIComponent(star[1].trim()); } catch (_) {}
  }
  const plain = cd.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1].trim() : fallback;
}

function jobState(j) {
  if (j.status === "pending" || j.status === "processing") {
    return { key: "converting", label: `Reading document… ${j.progress_percent || 0}%`, color: "text-teal-400", busy: true };
  }
  if (j.status === "error") return { key: "error", label: "Failed", color: "text-red-400", detail: j.error_message };
  if (j.status === "stopped") return { key: "stopped", label: "Stopped", color: "text-amber-400" };
  if (j.translate_status === "pending" || j.translate_status === "processing") {
    return { key: "translating", label: "Translating…", color: "text-blue-400", busy: true };
  }
  if (j.translate_status === "error") return { key: "error", label: "Translation failed", color: "text-red-400", detail: j.translate_error };
  if (j.has_translation_en || j.has_translation_id) return { key: "done", label: "Done", color: "text-green-400" };
  return { key: "other", label: "Not translated", color: "text-gray-500" };
}

export default function DocumentTranslation() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const [direction, setDirection] = useState("ko-en");
  const [model, setModel] = useState("onprem");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [downloading, setDownloading] = useState(null); // `${jobId}-${lang}`
  const [outputFormat, setOutputFormat] = useState("docx");
  const [withOriginal, setWithOriginal] = useState(false);

  // Only jobs that are, or were, translation jobs — plain conversions from
  // the Document Converter would just be noise here.
  const translationJobs = jobs.filter((j) => j.translate_status || j.has_translation_en || j.has_translation_id);
  const anyActive = translationJobs.some((j) => jobState(j).busy);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/ai/document-converter/jobs?limit=100", { headers });
      if (res.ok) setJobs(await res.json());
    } catch (_) {} finally { setJobsLoading(false); }
  }, [token]); // eslint-disable-line

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(fetchJobs, POLL_MS);
    return () => clearInterval(t);
  }, [anyActive, fetchJobs]);

  const handleTranslate = async () => {
    if (!file || uploading) return;
    const dir = DIRECTIONS.find((d) => d.value === direction);
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("language", dir.ocr);
      fd.append("translate_target", dir.target);
      fd.append("translate_provider", model);
      const res = await fetch("/api/v1/ai/document-converter/convert", { method: "POST", headers, body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      fetchJobs();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  // lang is the translation to download; "both" asks the server for the
  // original followed by the translation (it picks the job's translation).
  const handleDownload = async (job, lang) => {
    if (downloading) return;
    setDownloading(`${job.id}-${lang}`);
    try {
      const params = new URLSearchParams({ format: outputFormat, lang: withOriginal ? "both" : lang });
      const res = await fetch(`/api/v1/ai/document-converter/jobs/${job.id}/render?${params}`, { headers });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Download failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filenameFrom(res, `${job.filename}.${outputFormat}`);
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setDownloading(null);
    }
  };

  const handleStop = async (job) => {
    try {
      await fetch(`/api/v1/ai/document-converter/jobs/${job.id}/stop`, { method: "POST", headers });
      fetchJobs();
    } catch (_) {}
  };

  const handleDelete = async (job) => {
    if (!confirm(`Remove "${job.filename}" from history?`)) return;
    try {
      const res = await fetch(`/api/v1/ai/document-converter/jobs/${job.id}`, { method: "DELETE", headers });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Delete failed (${res.status})`);
      }
      fetchJobs();
    } catch (e) {
      setError(e.message);
    }
  };

  const selectedDir = DIRECTIONS.find((d) => d.value === direction);
  const selectedModel = MODELS.find((m) => m.value === model);

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Languages className="text-purple-400" size={26} />
          Document Translation
        </h1>
        <p className="text-gray-500 text-sm mt-1">Upload a PDF, Word file or image → translated document you can download as Word</p>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Translation</label>
            <select value={direction} onChange={(e) => setDirection(e.target.value)} disabled={uploading}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500 disabled:opacity-50">
              {DIRECTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
            {selectedDir.ocr === "korean" && (
              <p className="text-[11px] text-gray-600 mt-1.5">Scanned Korean PDFs are read with Korean OCR, which takes longer per page.</p>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)} disabled={uploading}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500 disabled:opacity-50">
              {MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <p className="text-[11px] text-gray-600 mt-1.5">{selectedModel.hint}</p>
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1.5">Document (PDF, Word, PNG or JPG)</label>
          <div className="flex items-center gap-3">
            <label className={`flex items-center gap-2 rounded-lg border border-dashed border-gray-700 bg-gray-800/50 px-4 py-2.5 text-sm text-gray-300 ${uploading ? "opacity-50" : "cursor-pointer hover:border-blue-500"}`}>
              <Upload size={15} className="text-gray-500" />
              <span className="truncate max-w-xs">{file ? file.name : "Choose file…"}</span>
              <input ref={fileRef} type="file" accept={ACCEPTED} className="hidden" disabled={uploading}
                onChange={(e) => { setFile(e.target.files?.[0] || null); setError(null); }} />
            </label>
            {file && !uploading && (
              <button onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; }}
                className="text-gray-500 hover:text-gray-300" title="Clear">
                <X size={16} />
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" /> {error}
          </div>
        )}

        <button onClick={handleTranslate} disabled={!file || uploading}
          className="flex items-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 transition-colors">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Languages size={14} />}
          {uploading ? "Uploading…" : "Translate"}
        </button>
        <p className="text-[11px] text-gray-600">
          Translation runs in the background — you can close this page and come back; the result stays in the history below.
        </p>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2 mr-auto">
            <History size={15} className="text-gray-500" /> History
          </h3>
          <label className="text-xs text-gray-500">Download as</label>
          <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}
            className="rounded-md border border-gray-700 bg-gray-800 text-gray-200 text-xs px-2.5 py-1.5 outline-none focus:border-blue-500">
            {OUTPUT_FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
          <select value={withOriginal ? "both" : "translation"} onChange={(e) => setWithOriginal(e.target.value === "both")}
            className="rounded-md border border-gray-700 bg-gray-800 text-gray-200 text-xs px-2.5 py-1.5 outline-none focus:border-blue-500">
            <option value="translation">Translation only</option>
            <option value="both">Original + translation</option>
          </select>
        </div>
        {jobsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>
        ) : translationJobs.length === 0 ? (
          <p className="text-sm text-gray-600">No translated documents yet.</p>
        ) : (
          <div className="divide-y divide-gray-800">
            {translationJobs.map((j) => {
              const st = jobState(j);
              const langs = ["en", "id"].filter((l) => j[`has_translation_${l}`]);
              const converting = j.status === "pending" || j.status === "processing";
              return (
                <div key={j.id} className="py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-gray-200 truncate">{j.filename}</div>
                    <div className="text-[11px] text-gray-600 mt-0.5">
                      {j.created_by} · {j.created_at ? new Date(j.created_at).toLocaleString() : ""}
                      {j.translate_provider ? ` · ${j.translate_provider === "onprem" ? "On-premise" : j.translate_provider === "anthropic" ? "Claude" : j.translate_provider}` : ""}
                    </div>
                    {st.detail && <div className="text-[11px] text-red-400/80 mt-0.5 truncate" title={st.detail}>{st.detail}</div>}
                    {st.key === "done" && j.translate_qa_warnings?.length > 0 && (
                      <div className="text-[11px] text-amber-400/80 mt-0.5">
                        {j.translate_qa_warnings.length} item(s) flagged for review — check numbers and terms in the output
                      </div>
                    )}
                  </div>
                  <div className={`flex items-center gap-1.5 text-xs ${st.color}`}>
                    {st.busy ? <Loader2 size={13} className="animate-spin" /> : st.key === "done" ? <CheckCircle2 size={13} /> : st.key === "error" ? <AlertTriangle size={13} /> : null}
                    {st.label}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {langs.map((l) => (
                      <button key={l} onClick={() => handleDownload(j, l)} disabled={!!downloading}
                        className="flex items-center gap-1 rounded-md border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:border-blue-500 disabled:opacity-50"
                        title={`${LANG_LABEL[l]} translation as ${outputFormat === "pdf" ? "PDF" : "Word"}${withOriginal ? ", with the original first" : ""}`}>
                        {downloading === `${j.id}-${l}` ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                        {outputFormat === "pdf" ? "PDF" : "Word"} ({l.toUpperCase()})
                      </button>
                    ))}
                    {converting ? (
                      <button onClick={() => handleStop(j)} className="p-1.5 text-gray-500 hover:text-amber-400" title="Stop">
                        <Square size={14} />
                      </button>
                    ) : (
                      <button onClick={() => handleDelete(j)} className="p-1.5 text-gray-500 hover:text-red-400" title="Remove from history">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
