import { useState, useRef, useEffect } from "react";
import { FileStack, Upload, Loader2, Download, Send, AlertTriangle, CheckCircle2, FileText, FolderOpen, X, Save } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const ACCEPTED = ".pdf,.docx,.doc,.png,.jpg,.jpeg";

export default function DocumentConverter() {
  const { token } = useAuthStore();
  const [file, setFile] = useState(null);
  const [converting, setConverting] = useState(false);
  const [progress, setProgress] = useState(null); // { page, total, message }
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState(null);
  const [departments, setDepartments] = useState(["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]);
  const [form, setForm] = useState({ source: "", title: "", department: "General" });
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState(null);
  const fileRef = useRef(null);
  const abortRef = useRef(null);

  // Reopen-existing-document flow
  const [existingDocs, setExistingDocs] = useState([]);
  const [selectedDocKey, setSelectedDocKey] = useState("");
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [editingExisting, setEditingExisting] = useState(null); // { source, title } of the doc currently loaded for editing, or null

  const headers = { Authorization: `Bearer ${token}` };

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
  }, [token]);

  const reset = () => {
    setMarkdown("");
    setError(null);
    setProgress(null);
    setSendMsg(null);
    setEditingExisting(null);
    setSelectedDocKey("");
  };

  const handleFileChange = (f) => {
    setFile(f);
    reset();
    if (f) setForm((p) => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, "") }));
  };

  const handleLoadExisting = async () => {
    if (!selectedDocKey) return;
    const [source, title] = JSON.parse(selectedDocKey);
    setLoadingDoc(true);
    setError(null);
    try {
      const params = new URLSearchParams({ source, title });
      const res = await fetch(`/api/v1/ai/chatbot/documents/content?${params}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal memuat dokumen");
      const doc = existingDocs.find((d) => d.source === source && d.title === title);
      setMarkdown(data.content);
      setForm({ source, title, department: doc?.department || "General" });
      setEditingExisting({ source, title });
      setFile(null);
      setProgress(null);
      setSendMsg(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingDoc(false);
    }
  };

  const handleCancelEdit = () => {
    reset();
    setForm({ source: "", title: "", department: "General" });
  };

  const handleConvert = async () => {
    if (!file || converting) return;
    reset();
    setConverting(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/v1/ai/document-converter/convert", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`Request gagal (${res.status})`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") continue;
          try {
            const evt = JSON.parse(payload);
            if (evt.type === "progress") {
              setProgress({ page: evt.page, total: evt.total, message: evt.message });
            } else if (evt.type === "page_result") {
              accumulated[evt.page - 1] = evt.markdown;
              setMarkdown(accumulated.filter(Boolean).join("\n\n"));
            } else if (evt.type === "done") {
              setMarkdown(evt.markdown);
              setProgress(null);
            } else if (evt.type === "error") {
              setError(evt.message);
            }
          } catch (_) {}
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setConverting(false);
    }
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
      // Editing an existing document: replace its old chunks entirely
      // (delete then re-ingest the edited content) rather than appending
      // duplicate chunks alongside the stale ones.
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
      // Refresh the reopen-existing list so the edited doc's chunk count etc. stays current
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

  const pct = progress?.total ? Math.round((progress.page / progress.total) * 100) : null;

  return (
    <div className="flex flex-col h-full p-6">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FileStack className="text-teal-400" size={26} />
          Document Converter
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Konversi PDF, DOCX, atau gambar (termasuk hasil scan) ke Markdown terstruktur — tabel tetap rapi, cocok untuk Knowledge Base AI Chatbot
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 flex-1 min-h-0">
        {/* Left: upload + controls */}
        <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 p-5 gap-4 overflow-y-auto">
          {editingExisting ? (
            <div className="rounded-lg border border-amber-700/40 bg-amber-500/10 px-3 py-2.5 flex items-center justify-between gap-2">
              <p className="text-xs text-amber-400 flex items-center gap-1.5">
                <FolderOpen size={13} /> Mengedit: <span className="font-semibold">{editingExisting.title}</span>
              </p>
              <button onClick={handleCancelEdit} title="Batal edit, mulai konversi baru"
                className="text-amber-400 hover:text-amber-300 shrink-0">
                <X size={14} />
              </button>
            </div>
          ) : (
            <div>
              <label className="text-xs text-gray-500 mb-2 block">Atau buka & edit dokumen KB yang sudah ada</label>
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

          <div className="border-t border-gray-800 pt-4">
            <label className="text-xs text-gray-500 mb-2 block">File (PDF / DOCX / PNG / JPG)</label>
            <div
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-dashed border-gray-700 hover:border-teal-500 transition-colors p-6 text-center cursor-pointer"
            >
              <input ref={fileRef} type="file" accept={ACCEPTED} className="hidden"
                onChange={(e) => handleFileChange(e.target.files?.[0] || null)} />
              <Upload size={22} className="mx-auto text-gray-600 mb-2" />
              <p className="text-sm text-gray-300">{file ? file.name : "Klik untuk pilih file"}</p>
              {file && <p className="text-xs text-gray-600 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>}
            </div>
          </div>

          <button
            onClick={handleConvert}
            disabled={!file || converting}
            className="flex items-center justify-center gap-2 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
          >
            {converting ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
            {converting ? "Mengonversi..." : "Konversi ke Markdown"}
          </button>

          {converting && (
            <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
              <p className="text-xs text-gray-400 mb-2">
                {progress?.message || "Memulai..."}
                {progress?.total > 1 && <span className="text-gray-600"> (bisa beberapa menit untuk dokumen hasil scan)</span>}
              </p>
              {pct !== null && (
                <div className="h-1.5 rounded-full bg-gray-800 overflow-hidden">
                  <div className="h-full bg-teal-500 transition-all" style={{ width: `${pct}%` }} />
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
              <AlertTriangle size={12} /> {error}
            </div>
          )}

          <div className="border-t border-gray-800 pt-4 space-y-3">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              {editingExisting ? "Edit Dokumen KB" : "Kirim ke Knowledge Base"}
            </p>
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

        {/* Right: markdown preview/edit */}
        <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Hasil Markdown</p>
            {markdown && <p className="text-xs text-gray-600">{markdown.length.toLocaleString()} karakter — bisa diedit sebelum dikirim</p>}
          </div>
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            placeholder="Hasil konversi akan muncul di sini..."
            className="flex-1 w-full resize-none bg-gray-950 text-gray-200 text-xs font-mono p-4 outline-none placeholder-gray-700"
          />
        </div>
      </div>
    </div>
  );
}
