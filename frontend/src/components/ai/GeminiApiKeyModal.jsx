import { useState, useEffect } from "react";
import { X, KeyRound, ExternalLink, Eye, EyeOff, Loader2, CheckCircle2, Trash2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const AI_STUDIO_URL = "https://aistudio.google.com/apikey";

export default function GeminiApiKeyModal({ onClose }) {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const [loading, setLoading] = useState(true);
  const [hasKey, setHasKey] = useState(false);
  const [keyHint, setKeyHint] = useState(null);
  const [input, setInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [msg, setMsg] = useState(null); // { type: "error"|"success", text }

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/ai/settings/api-key/gemini", { headers });
      const data = await res.json();
      setHasKey(!!data.has_key);
      setKeyHint(data.key_hint);
    } catch (_) {} finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStatus(); }, []); // eslint-disable-line

  const handleSave = async () => {
    const key = input.trim();
    if (!key) { setMsg({ type: "error", text: "Paste an API key first" }); return; }
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch("/api/v1/ai/settings/api-key/gemini", {
        method: "PUT", headers, body: JSON.stringify({ api_key: key }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to save the API key");
      setMsg({ type: "success", text: data.message });
      setInput("");
      setHasKey(true);
      setKeyHint(data.key_hint);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!confirm("Delete your personal API key? The chatbot will go back to the company (shared) key.")) return;
    setRemoving(true);
    setMsg(null);
    try {
      const res = await fetch("/api/v1/ai/settings/api-key/gemini", { method: "DELETE", headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to delete the API key");
      setMsg({ type: "success", text: data.message });
      setHasKey(false);
      setKeyHint(null);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="rounded-xl border border-gray-800 bg-gray-900 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 sticky top-0 bg-gray-900 z-10">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <KeyRound size={16} className="text-violet-400" /> My Gemini API Key
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-xs text-gray-400 leading-relaxed">
            By default, the AI Chatbot uses the company's shared Gemini API key. If you want to use
            your own Gemini account (your own quota &amp; billing), paste your API key below.
            Clear / delete it at any time to go back to the company key.
          </p>

          {/* Guide */}
          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 space-y-2">
            <p className="text-xs font-semibold text-gray-300">How to get a Gemini API key:</p>
            <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
              <li>
                Open{" "}
                <a href={AI_STUDIO_URL} target="_blank" rel="noopener noreferrer"
                  className="text-violet-400 hover:text-violet-300 underline inline-flex items-center gap-1">
                  Google AI Studio <ExternalLink size={10} />
                </a>
              </li>
              <li>Log in with your Google/Gmail account (one that already has Gemini access)</li>
              <li>Click <span className="text-gray-300 font-medium">"Create API key"</span></li>
              <li>Choose the company Google Cloud project if asked</li>
              <li>Copy the key shown (it starts with <code className="text-gray-300">AIza...</code>)</li>
              <li>Paste it in the field below, then click <span className="text-gray-300 font-medium">Save</span></li>
            </ol>
          </div>

          {/* Current status */}
          {loading ? (
            <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
          ) : hasKey ? (
            <div className="flex items-center justify-between rounded-lg border border-green-700/40 bg-green-500/10 px-3 py-2.5">
              <span className="flex items-center gap-2 text-xs text-green-400">
                <CheckCircle2 size={14} /> Personal API key active: <code>{keyHint}</code>
              </span>
              <button onClick={handleRemove} disabled={removing}
                className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded px-2 py-1 hover:bg-red-500/10 transition-colors disabled:opacity-50">
                {removing ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />} Delete
              </button>
            </div>
          ) : (
            <div className="rounded-lg border border-gray-700 bg-gray-800/30 px-3 py-2.5 text-xs text-gray-500">
              No personal API key yet — currently using the company (shared) key.
            </div>
          )}

          {/* Input field */}
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Paste your Gemini API key</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? "text" : "password"}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="AIza..."
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 pr-9 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-violet-500"
                />
                <button type="button" onClick={() => setShowKey((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                  {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <button onClick={handleSave} disabled={saving || !input.trim()}
                className="flex items-center gap-1.5 rounded-md bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-2 text-xs font-semibold text-white shrink-0">
                {saving ? <Loader2 size={13} className="animate-spin" /> : null}
                {saving ? "Validating..." : "Save"}
              </button>
            </div>
          </div>

          {msg && (
            <div className={`rounded-md px-3 py-2 text-xs font-medium ${msg.type === "error" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-green-500/10 border border-green-500/30 text-green-400"}`}>
              {msg.text}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
