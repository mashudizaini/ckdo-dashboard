import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, BookOpen, Upload, Trash2, X, Loader2, FileText, AlignLeft, AlertTriangle, KeyRound, RotateCcw } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { useChatStream } from "@/hooks/useChatStream";
import { CHAT_MODES, CHAT_MODE_ORDER } from "@/config/chatModes";
import { DeptBadge, renderSource } from "@/components/ai/ChatSourceBadges";
import GeminiApiKeyModal from "@/components/ai/GeminiApiKeyModal";

function KnowledgeBasePanel({ onClose }) {
  const { token, hasAnyRole } = useAuthStore();
  const canWipeAll = hasAnyRole("it_staff", "admin"); // matches the backend's cleanup/all role gate
  const [docs, setDocs] = useState([]);
  const [departments, setDepartments] = useState(["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]);
  const [loading, setLoading] = useState(false);
  const [ragConfigured, setRagConfigured] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [form, setForm] = useState({ source: "", title: "", text: "", department: "General" });
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const fileRef = useRef(null);
  const msgTimerRef = useRef(null);

  const headers = { Authorization: `Bearer ${token}` };

  const showMsg = (type, text) => {
    setMsg({ type, text });
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    if (type === "success") msgTimerRef.current = setTimeout(() => setMsg(null), 6000);
  };

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
    setFetchError(null);
    try {
      const res = await fetch("/api/v1/ai/chatbot/documents", { headers });
      if (res.status === 400) { setRagConfigured(false); setDocs([]); return; }
      if (res.ok) {
        setRagConfigured(true);
        setDocs(await res.json());
      } else {
        const err = await res.json().catch(() => ({}));
        setFetchError(err.detail || `Error ${res.status} loading document list`);
      }
    } catch (e) {
      setFetchError(`Failed to load list: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStatus(); fetchDocs(); }, []); // eslint-disable-line

  const handleSubmit = async () => {
    if (!form.source.trim() || !form.title.trim() || (!form.text.trim() && !file)) {
      showMsg("error", "Fill in Source, Title, and Content/File first");
      return;
    }
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
      showMsg("success", `✓ ${data.message}`);
      setForm({ source: "", title: "", text: "", department: form.department });
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      fetchDocs();
    } catch (e) {
      showMsg("error", e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (source, title) => {
    if (!confirm(`Delete document "${title}"?`)) return;
    try {
      const params = new URLSearchParams({ source, title });
      const res = await fetch(`/api/v1/ai/chatbot/documents?${params}`, { method: "DELETE", headers });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { showMsg("success", `Document "${title}" deleted`); fetchDocs(); }
      else { showMsg("error", d.detail || `Delete failed (${res.status})`); }
    } catch (e) { showMsg("error", `Failed to delete: ${e.message}`); }
  };

  const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }) : "-";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="rounded-xl border border-gray-800 bg-gray-900 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 sticky top-0 bg-gray-900 z-10">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <BookOpen size={16} className="text-blue-400" /> Knowledge Base
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          {!ragConfigured ? (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-sm text-amber-400">
              RAG is not active yet: <code>OLLAMA_API_URL</code> is not set in the backend environment.
            </div>
          ) : (
            <>
              {/* Upload Form */}
              <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Add New Document</p>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Source / Category</label>
                    <input value={form.source} onChange={e => setForm(p => ({ ...p, source: e.target.value }))}
                      placeholder="e.g. SOP_FINANCE" className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">Title</label>
                    <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
                      placeholder="e.g. PR Submission Procedure" className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
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
                  <label className="text-xs text-gray-500 mb-1 block">Content (paste text or upload file)</label>
                  <textarea value={form.text} onChange={e => setForm(p => ({ ...p, text: e.target.value }))} rows={3}
                    placeholder="Paste document text here..." className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 resize-vertical" />
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={e => setFile(e.target.files?.[0] || null)}
                    className="text-xs text-gray-400 flex-1" />
                  <button onClick={handleSubmit} disabled={saving}
                    className="flex items-center gap-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 text-xs font-semibold text-white shrink-0">
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                    {saving ? "Processing... (bisa beberapa menit untuk PDF hasil scan)" : "Upload & Save"}
                  </button>
                </div>
                {msg && (
                  <div className={`rounded-md px-3 py-2 text-xs font-medium ${msg.type === "error" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-green-500/10 border border-green-500/30 text-green-400"}`}>
                    {msg.text}
                  </div>
                )}
              </div>

              {/* Document History */}
              <div>
                {/* Header row */}
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    Uploaded Documents ({docs.length})
                  </h4>
                  <div className="flex items-center gap-2">
                    <button onClick={fetchDocs} disabled={loading}
                      className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 disabled:opacity-50">
                      <Loader2 size={11} className={loading ? "animate-spin" : ""} /> Refresh
                    </button>
                    {canWipeAll && docs.length > 0 && (
                      <button
                        onClick={async () => {
                          const typed = prompt(
                            `This deletes ALL ${docs.length} documents from the Knowledge Base — every department, files and text-paste alike. This cannot be undone.\n\nType DELETE ALL to confirm:`
                          );
                          if (typed !== "DELETE ALL") return;
                          try {
                            const res = await fetch("/api/v1/ai/chatbot/documents/cleanup/all", { method: "DELETE", headers });
                            const d = await res.json();
                            showMsg("success", d.message);
                            fetchDocs();
                          } catch (e) { showMsg("error", `Wipe failed: ${e.message}`); }
                        }}
                        title="IT/Admin only — permanently deletes the entire Knowledge Base"
                        className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 border border-red-600/40 rounded px-2 py-0.5 hover:bg-red-600/10 transition-colors">
                        <Trash2 size={11} /> Wipe Entire Knowledge Base
                      </button>
                    )}
                  </div>
                </div>

                {/* Summary counts */}
                {docs.length > 0 && (() => {
                  const fileCount = docs.filter(d => d.from_file).length;
                  const textCount = docs.filter(d => !d.from_file).length;
                  return (
                    <div className="flex items-center gap-3 mb-3 text-xs">
                      <span className="flex items-center gap-1 text-blue-400">
                        <FileText size={11} /> {fileCount} file upload{fileCount !== 1 ? "s" : ""}
                      </span>
                      {textCount > 0 && (
                        <>
                          <span className="flex items-center gap-1 text-amber-400">
                            <AlignLeft size={11} /> {textCount} text-paste
                          </span>
                          <button
                            onClick={async () => {
                              if (!confirm(`Delete all ${textCount} text-paste entries from the knowledge base?`)) return;
                              try {
                                const res = await fetch("/api/v1/ai/chatbot/documents/cleanup/text-only", { method: "DELETE", headers });
                                const d = await res.json();
                                showMsg("success", d.message);
                                fetchDocs();
                              } catch (e) { showMsg("error", `Cleanup failed: ${e.message}`); }
                            }}
                            className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded px-2 py-0.5 hover:bg-red-500/10 transition-colors">
                            <Trash2 size={10} /> Delete text-paste entries
                          </button>
                        </>
                      )}
                    </div>
                  );
                })()}

                {fetchError && (
                  <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400 mb-3 flex items-center gap-2">
                    <AlertTriangle size={12} /> {fetchError}
                  </div>
                )}

                {loading ? (
                  <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
                ) : docs.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-700 py-10 text-center">
                    <BookOpen size={28} className="mx-auto text-gray-700 mb-2" />
                    <p className="text-xs text-gray-600">No documents yet.</p>
                    <p className="text-xs text-gray-700 mt-1">Upload a file or paste text using the form above.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {docs.map((d, i) => (
                      <div key={i} className={`flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors ${d.from_file ? 'bg-blue-500/5 border-blue-800/40 hover:border-blue-700/60' : 'bg-amber-500/5 border-amber-800/30 hover:border-amber-700/40'}`}>
                        <div className="min-w-0 flex items-start gap-2 flex-1">
                          {/* File vs Text badge */}
                          <span title={d.from_file ? (d.file_name || "File upload") : "Text paste"}
                            className={`shrink-0 mt-0.5 flex items-center gap-1 text-[10px] font-semibold rounded px-1.5 py-0.5 ${d.from_file ? 'bg-blue-500/15 text-blue-400' : 'bg-amber-500/15 text-amber-400'}`}>
                            {d.from_file ? <FileText size={9} /> : <AlignLeft size={9} />}
                            {d.from_file ? "FILE" : "TEXT"}
                          </span>
                          <DeptBadge department={d.department} />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-semibold text-gray-200 truncate">{d.title}</p>
                            <p className="text-xs text-gray-500 mt-0.5 truncate">
                              <span className="text-gray-400">{d.source}</span>
                              {d.from_file && d.file_name && <span className="text-blue-500/80"> · {d.file_name}</span>}
                              {" · "}{d.chunks} chunk{d.chunks !== 1 ? "s" : ""}
                              {" · "}{fmtDate(d.created_at)}
                              {d.created_by && <span className="text-gray-600"> · {d.created_by}</span>}
                            </p>
                          </div>
                        </div>
                        <button onClick={() => handleDelete(d.source, d.title)}
                          className="text-gray-600 hover:text-red-400 ml-3 shrink-0 p-1 rounded hover:bg-red-400/10 transition-colors"
                          title="Delete document">
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

  const [activeTab, setActiveTab] = useState("policy");
  const [provider, setProvider] = useState("onprem");
  const [showKB, setShowKB] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const bottomRef = useRef(null);

  // Claude isn't wired into Oracle EBS Data Chat's tool-calling pipeline
  // yet (see chatbot.py) — the dropdown below disables selecting it while
  // that tab is active, but if it was already selected on a different tab
  // before switching here, fall back automatically instead of letting the
  // next message hit the backend's 400.
  useEffect(() => {
    if (activeTab === "oracle" && provider === "anthropic") setProvider("gemini");
  }, [activeTab, provider]);

  // All 3 modes stay mounted (via their own hook instance) at all times, so
  // switching tabs preserves each conversation's history instead of
  // resetting it — each has its own localStorage key too.
  const policyChat  = useChatStream(CHAT_MODES.policy.greeting,  CHAT_MODES.policy.storageKey,  CHAT_MODES.policy.endpoint,  provider);
  const oracleChat  = useChatStream(CHAT_MODES.oracle.greeting,  CHAT_MODES.oracle.storageKey,  CHAT_MODES.oracle.endpoint,  provider);
  const generalChat = useChatStream(CHAT_MODES.general.greeting, CHAT_MODES.general.storageKey, CHAT_MODES.general.endpoint, provider);

  const chats = { policy: policyChat, oracle: oracleChat, general: generalChat };
  const chat = chats[activeTab];
  const mode = CHAT_MODES[activeTab];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, activeTab]);

  return (
    <div className="flex flex-col h-full p-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Bot className="text-blue-400" size={26} />
            AI Chatbot
          </h1>
          <p className="text-gray-500 text-sm mt-1">Company policy, Oracle ERP data, and general questions — all in one place</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            title="AI provider"
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="onprem">Standard (On-Premise)</option>
            <option value="gemini">Gemini</option>
            <option value="anthropic" disabled={activeTab === "oracle"}>
              Claude{activeTab === "oracle" ? " (not available for Oracle ERP Data chat)" : ""}
            </option>
          </select>
          <button onClick={() => setShowApiKey(true)} title="Pakai API key Gemini pribadi Anda sendiri"
            className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-violet-500 hover:text-violet-400 transition-colors">
            <KeyRound size={14} /> My API Key
          </button>
          <button
            onClick={() => { if (confirm("Clear this conversation's history? This cannot be undone.")) chat.clearHistory(); }}
            title="Riwayat percakapan tersimpan di browser ini dan ikut dikirim sebagai konteks di setiap pertanyaan baru — kosongkan kalau jawaban lama masih 'nyangkut' meski Knowledge Base sudah diubah."
            className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-amber-500 hover:text-amber-400 transition-colors">
            <RotateCcw size={14} /> Clear Conversation
          </button>
          {activeTab === "policy" && canManageKB && (
            <button onClick={() => setShowKB(true)}
              className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-blue-500 hover:text-blue-400 transition-colors">
              <BookOpen size={14} /> Knowledge Base
            </button>
          )}
        </div>
      </div>

      {showKB && <KnowledgeBasePanel onClose={() => setShowKB(false)} />}
      {showApiKey && <GeminiApiKeyModal onClose={() => setShowApiKey(false)} />}

      {/* Mode tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-800">
        {CHAT_MODE_ORDER.map((key) => {
          const m = CHAT_MODES[key];
          const Icon = m.icon;
          const isActive = activeTab === key;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive ? m.tabActive : "border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              <Icon size={15} />
              {m.label}
            </button>
          );
        })}
      </div>

      {/* Chat container */}
      <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 flex-1 overflow-hidden">
        {/* Chat Header */}
        <div className={`flex items-center gap-3 px-5 py-4 border-b border-gray-800 bg-gradient-to-r ${mode.gradient}`}>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
            <mode.icon size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">{mode.subtitle}</p>
            <p className="text-xs text-white/70">{mode.subtitle2}</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-white/70">
            <span className={`h-2 w-2 rounded-full ${chat.streaming ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
            {chat.streaming ? mode.thinkingLabel : "Online"}
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {chat.messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                msg.role === "user" ? mode.userAvatar : "bg-gray-700"
              }`}>
                {msg.role === "user" ? <User size={14} className="text-white" /> : <Bot size={14} className="text-gray-300" />}
              </div>
              <div className={`max-w-md rounded-xl px-4 py-3 text-sm ${
                msg.error
                  ? "bg-red-500/10 border border-red-500/30 text-red-400"
                  : msg.role === "user"
                    ? `${mode.userBubble} text-white rounded-tr-sm`
                    : "bg-gray-800 text-gray-200 rounded-tl-sm"
              }`}>
                {msg.text || (chat.streaming && i === chat.messages.length - 1 ? <Loader2 size={14} className="animate-spin" /> : "")}
                {msg.sources?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-700 flex flex-wrap gap-1.5">
                    {msg.sources.map((s, j) => renderSource(activeTab, s, j))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Suggestions */}
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {mode.suggestions.map((s) => (
            <button
              key={s}
              onClick={() => chat.setInput(s)}
              className={`rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 transition-colors ${mode.suggestHover}`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-3 border-t border-gray-800 p-4">
          <input
            type="text"
            value={chat.input}
            onChange={(e) => chat.setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && chat.sendMessage()}
            disabled={chat.streaming}
            placeholder="Type your question..."
            className={`flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none transition-colors disabled:opacity-50 ${mode.focusRing}`}
          />
          <button
            onClick={() => chat.sendMessage()}
            disabled={chat.streaming || !chat.input.trim()}
            className={`flex h-10 w-10 items-center justify-center rounded-full disabled:opacity-50 transition-colors ${mode.sendBtn}`}
          >
            {chat.streaming ? <Loader2 size={16} className="text-white animate-spin" /> : <Send size={16} className="text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
}
