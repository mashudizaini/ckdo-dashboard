import { useState, useRef, useEffect } from "react";
import { MessageSquare, Send, Bot, User, BookOpen, Upload, Trash2, X, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { useChatStream } from "@/hooks/useChatStream";

const SUGGESTIONS = [
  "What's the total revenue this month?",
  "Current production batch status?",
  "Employee attendance summary?",
  "How many POs are pending approval?",
];

const DEPT_COLORS = {
  General:    { bg: "#e2e8f0", color: "#475569" },
  HR:         { bg: "#fef3c7", color: "#d97706" },
  Accounting: { bg: "#dbeafe", color: "#1d4ed8" },
  PAC:        { bg: "#dcfce7", color: "#16a34a" },
  Purchasing: { bg: "#ede9fe", color: "#7c3aed" },
  IT:         { bg: "#fee2e2", color: "#dc2626" },
};

function DeptBadge({ department }) {
  const cfg = DEPT_COLORS[department] || DEPT_COLORS.General;
  return (
    <span className="text-[10px] font-semibold rounded-full px-2 py-0.5" style={{ background: cfg.bg, color: cfg.color }}>
      {department}
    </span>
  );
}

function KnowledgeBasePanel({ onClose }) {
  const { token } = useAuthStore();
  const [docs, setDocs] = useState([]);
  const [departments, setDepartments] = useState(["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]);
  const [loading, setLoading] = useState(false);
  const [ragConfigured, setRagConfigured] = useState(true);
  const [form, setForm] = useState({ source: "", title: "", text: "", department: "General" });
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const fileRef = useRef(null);

  const headers = { Authorization: `Bearer ${token}` };

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/v1/ai/chatbot/status", { headers });
      if (res.ok) {
        const data = await res.json();
        if (data.departments?.length) setDepartments(data.departments);
      }
    } catch (_) {}
  };

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/ai/chatbot/documents", { headers });
      if (res.status === 400) { setRagConfigured(false); setDocs([]); return; }
      if (res.ok) { setRagConfigured(true); setDocs(await res.json()); }
    } catch (_) {}
    finally { setLoading(false); }
  };

  useEffect(() => { fetchStatus(); fetchDocs(); }, []); // eslint-disable-line

  const handleSubmit = async () => {
    if (!form.source.trim() || !form.title.trim() || (!form.text.trim() && !file)) return;
    setSaving(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("source", form.source.trim());
      fd.append("title", form.title.trim());
      fd.append("text", form.text);
      fd.append("department", form.department);
      if (file) fd.append("file", file);
      const res = await fetch("/api/v1/ai/chatbot/documents", { method: "POST", headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      setMsg({ type: "success", text: data.message });
      setForm({ source: "", title: "", text: "", department: form.department });
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      fetchDocs();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (source, title) => {
    if (!confirm(`Delete document "${title}"?`)) return;
    try {
      const params = new URLSearchParams({ source, title });
      await fetch(`/api/v1/ai/chatbot/documents?${params}`, { method: "DELETE", headers });
      fetchDocs();
    } catch (_) {}
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.4)" }}>
      <div className="rounded-xl border border-gray-800 bg-gray-900 w-full max-w-2xl max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 sticky top-0 bg-gray-900">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <BookOpen size={16} className="text-blue-400" /> Knowledge Base
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          {!ragConfigured ? (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-sm text-amber-400">
              RAG belum aktif: <code>VOYAGE_API_KEY</code> belum diset di environment backend.
              Chatbot tetap berfungsi sebagai chat umum tanpa konteks dokumen perusahaan.
            </div>
          ) : (
            <>
              <p className="text-xs text-gray-500">
                Dokumen yang ditambahkan di sini akan dipakai chatbot untuk menjawab pertanyaan terkait perusahaan (SOP, prosedur, knowledge base helpdesk, dll).
                Pilih <strong>Department</strong> dengan benar — chatbot hanya akan menampilkan dokumen sesuai departemen user yang bertanya (IT/Admin bisa lihat semua).
              </p>

              <div className="rounded-lg border border-gray-800 bg-gray-800/40 p-4 space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Source / Category</label>
                    <input value={form.source} onChange={e => setForm(p => ({ ...p, source: e.target.value }))}
                      placeholder="e.g. SOP_FINANCE" className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Title</label>
                    <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
                      placeholder="e.g. Prosedur Pengajuan PR" className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Department</label>
                    <select value={form.department} onChange={e => setForm(p => ({ ...p, department: e.target.value }))}
                      className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500 cursor-pointer">
                      {departments.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Content (paste text, or upload a file below)</label>
                  <textarea value={form.text} onChange={e => setForm(p => ({ ...p, text: e.target.value }))} rows={4}
                    placeholder="Paste dokumen di sini..." className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 resize-vertical" />
                </div>
                <div className="flex items-center gap-3">
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={e => setFile(e.target.files?.[0] || null)}
                    className="text-xs text-gray-400" />
                  <button onClick={handleSubmit} disabled={saving}
                    className="ml-auto flex items-center gap-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-white">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                    {saving ? "Ingesting..." : "Add Document"}
                  </button>
                </div>
                {msg && (
                  <p className={`text-xs ${msg.type === "error" ? "text-red-400" : "text-green-400"}`}>{msg.text}</p>
                )}
              </div>

              <div>
                <h4 className="text-xs font-semibold text-gray-400 mb-2">Documents ({docs.length})</h4>
                {loading ? (
                  <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
                ) : docs.length === 0 ? (
                  <p className="text-xs text-gray-600 py-4 text-center">No documents yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {docs.map((d, i) => (
                      <div key={i} className="flex items-center justify-between rounded-lg bg-gray-800/50 border border-gray-700 px-3 py-2">
                        <div className="min-w-0 flex items-center gap-2">
                          <DeptBadge department={d.department} />
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-gray-200 truncate">{d.title}</p>
                            <p className="text-xs text-gray-500">{d.source} · {d.chunks} chunk(s)</p>
                          </div>
                        </div>
                        <button onClick={() => handleDelete(d.source, d.title)} className="text-gray-500 hover:text-red-400 ml-2 shrink-0">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Chatbot() {
  const { hasAnyRole } = useAuthStore();
  const canManageKB = hasAnyRole("it_staff", "hr_staff", "accounting_staff", "pac_staff", "purchasing_staff", "admin");

  const { messages, input, setInput, streaming, sendMessage } = useChatStream(
    "Hello! I'm the CKDO Dashboard AI Assistant. Ask me anything about company data."
  );
  const [showKB, setShowKB] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-full p-6">
      {/* Header */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <MessageSquare className="text-blue-400" size={26} />
            AI Chatbot
          </h1>
          <p className="text-gray-500 text-sm mt-1">AI Assistant powered by Claude — Ask anything about company data</p>
        </div>
        {canManageKB && (
          <button onClick={() => setShowKB(true)}
            className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-blue-500 hover:text-blue-400 transition-colors">
            <BookOpen size={14} /> Knowledge Base
          </button>
        )}
      </div>

      {showKB && <KnowledgeBasePanel onClose={() => setShowKB(false)} />}

      {/* Chat container */}
      <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 flex-1 overflow-hidden">
        {/* Chat Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800 bg-gradient-to-r from-blue-600 to-blue-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
            <Bot size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Ask me anything</p>
            <p className="text-xs text-blue-200">AI-powered insights</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-200">
            <span className={`h-2 w-2 rounded-full ${streaming ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
            {streaming ? "Thinking..." : "Online"}
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                msg.role === "user" ? "bg-blue-600" : "bg-gray-700"
              }`}>
                {msg.role === "user" ? <User size={14} className="text-white" /> : <Bot size={14} className="text-gray-300" />}
              </div>
              <div className={`max-w-md rounded-xl px-4 py-3 text-sm ${
                msg.error
                  ? "bg-red-500/10 border border-red-500/30 text-red-400"
                  : msg.role === "user"
                    ? "bg-blue-600 text-white rounded-tr-sm"
                    : "bg-gray-800 text-gray-200 rounded-tl-sm"
              }`}>
                {msg.text || (streaming && i === messages.length - 1 ? <Loader2 size={14} className="animate-spin" /> : "")}
                {msg.sources?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-700 flex flex-wrap gap-1.5">
                    {msg.sources.map((s, j) => (
                      <span key={j} title={`${s.department} · similarity: ${s.similarity}`}
                        className="text-[10px] rounded-full border border-gray-600 bg-gray-900 px-2 py-0.5 text-gray-400">
                        📄 {s.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Suggestions */}
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-3 border-t border-gray-800 p-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            disabled={streaming}
            placeholder="Type your question..."
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={streaming || !input.trim()}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {streaming ? <Loader2 size={16} className="text-white animate-spin" /> : <Send size={16} className="text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
}
