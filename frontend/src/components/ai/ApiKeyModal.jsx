import { useState, useEffect } from "react";
import { X, KeyRound, ExternalLink, Eye, EyeOff, Loader2, CheckCircle2, Trash2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// Provider-agnostic version of GeminiApiKeyModal — same security model
// (once saved, the plaintext key is never fetched or shown again, only a
// masked hint like "••••abcd"; the input field itself is a password-type
// box with a show/hide toggle for what you're ABOUT to save, not for
// revealing anything already stored), generalized to whichever provider is
// passed in instead of being hardcoded to Gemini. Backend already supports
// this generically (user_settings.py dispatches by :provider), only the
// frontend needed generalizing.
const PROVIDER_META = {
  anthropic: {
    label: "Claude (Anthropic)",
    accent: "text-orange-400",
    docsUrl: "https://console.anthropic.com/settings/keys",
    docsLabel: "Anthropic Console",
    placeholder: "sk-ant-...",
    steps: [
      "Log in to your company/personal Anthropic account",
      'Click "Create Key"',
      "Copy the key shown (it starts with sk-ant-...)",
      "Paste it in the field below, then click Save",
    ],
    models: [
      { id: "claude-sonnet-5", label: "Claude Sonnet 5", note: "Recommended — fast & economical, enough for everyday chat" },
      { id: "claude-opus-5", label: "Claude Opus 5", note: "Most capable — for more complex questions/analysis, but more expensive & slower" },
      { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5", note: "Fastest & cheapest — for simple questions" },
    ],
  },
  gemini: {
    label: "Gemini (Google)",
    accent: "text-violet-400",
    docsUrl: "https://aistudio.google.com/apikey",
    docsLabel: "Google AI Studio",
    placeholder: "AIza...",
    steps: [
      "Log in with your Google/Gmail account (one that already has Gemini access)",
      'Click "Create API key"',
      "Choose the company Google Cloud project if asked",
      "Copy the key shown (it starts with AIza...)",
      "Paste it in the field below, then click Save",
    ],
  },
  openai: {
    label: "ChatGPT (OpenAI)",
    accent: "text-emerald-400",
    docsUrl: "https://platform.openai.com/api-keys",
    docsLabel: "OpenAI Platform",
    placeholder: "sk-...",
    steps: [
      "Log in to your company/personal OpenAI account",
      'Click "Create new secret key"',
      "Copy the key shown (it starts with sk-...)",
      "Paste it in the field below, then click Save",
    ],
  },
  kimi: {
    label: "Kimi (Moonshot AI)",
    accent: "text-sky-400",
    docsUrl: "https://platform.moonshot.ai/console/api-keys",
    docsLabel: "Moonshot AI Platform",
    placeholder: "sk-...",
    steps: [
      "Log in to your company/personal Moonshot AI account",
      'Click "Create API Key"',
      "Copy the key shown",
      "Paste it in the field below, then click Save",
    ],
  },
};

export default function ApiKeyModal({ provider, onClose }) {
  const meta = PROVIDER_META[provider];
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const url = `/api/v1/ai/settings/api-key/${provider}`;

  const [loading, setLoading] = useState(true);
  const [hasKey, setHasKey] = useState(false);
  const [keyHint, setKeyHint] = useState(null);
  const [input, setInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [msg, setMsg] = useState(null); // { type: "error"|"success", text }
  const [model, setModel] = useState(meta?.models?.[0]?.id || null);
  const [activeModel, setActiveModel] = useState(null);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch(url, { headers });
      const data = await res.json();
      setHasKey(!!data.has_key);
      setKeyHint(data.key_hint);
      setActiveModel(data.model || null);
      if (data.model) setModel(data.model);
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
      const res = await fetch(url, { method: "PUT", headers, body: JSON.stringify({ api_key: key, model }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to save the API key");
      setMsg({ type: "success", text: data.message });
      setInput("");
      setHasKey(true);
      setKeyHint(data.key_hint);
      setActiveModel(data.model || null);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!confirm(`Delete your personal ${meta.label} API key? This feature will go back to the company (shared) key.`)) return;
    setRemoving(true);
    setMsg(null);
    try {
      const res = await fetch(url, { method: "DELETE", headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to delete the API key");
      setMsg({ type: "success", text: data.message });
      setHasKey(false);
      setKeyHint(null);
      setActiveModel(null);
      setModel(meta?.models?.[0]?.id || null);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setRemoving(false);
    }
  };

  if (!meta) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="rounded-xl border border-gray-800 bg-gray-900 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 sticky top-0 bg-gray-900 z-10">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <KeyRound size={16} className={meta.accent} /> My {meta.label} API Key
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-xs text-gray-400 leading-relaxed">
            By default, Generate MOM uses the company's shared {meta.label} API key. If you want to use
            your own {meta.label} account (your own quota &amp; billing), paste your API key below.
            Clear / delete it at any time to go back to the company key.
          </p>

          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 space-y-2">
            <p className="text-xs font-semibold text-gray-300">How to get a {meta.label} API key:</p>
            <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
              <li>
                Open{" "}
                <a href={meta.docsUrl} target="_blank" rel="noopener noreferrer"
                  className={`${meta.accent} hover:opacity-80 underline inline-flex items-center gap-1`}>
                  {meta.docsLabel} <ExternalLink size={10} />
                </a>
              </li>
              {meta.steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>

          {loading ? (
            <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
          ) : hasKey ? (
            <div className="flex items-center justify-between rounded-lg border border-green-700/40 bg-green-500/10 px-3 py-2.5">
              <span className="flex items-center gap-2 text-xs text-green-400">
                <CheckCircle2 size={14} /> Personal API key active: <code>{keyHint}</code>
                {activeModel && <span className="text-gray-500">· model: <code>{activeModel}</code></span>}
              </span>
              <button onClick={handleRemove} disabled={removing}
                className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded px-2 py-1 hover:bg-red-500/10 transition-colors disabled:opacity-50">
                {removing ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />} Delete
              </button>
            </div>
          ) : (
            <div className="rounded-lg border border-gray-700 bg-gray-800/30 px-3 py-2.5 text-xs text-gray-500">
              No personal API key yet — currently using the company (shared) key{meta.models ? `, model ${meta.models[0].id}` : ""}.
            </div>
          )}

          {meta.models && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">{meta.label} model to use</label>
              <div className="space-y-1.5">
                {meta.models.map((m) => (
                  <label key={m.id}
                    className={`flex items-start gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
                      model === m.id ? "border-orange-500/60 bg-orange-500/10" : "border-gray-700 bg-gray-800/30 hover:border-gray-600"
                    }`}>
                    <input type="radio" name="model" className="mt-0.5" checked={model === m.id} onChange={() => setModel(m.id)} />
                    <span>
                      <span className="text-xs font-semibold text-gray-200">{m.label}</span>
                      <span className="block text-[11px] text-gray-500">{m.note}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="text-xs text-gray-500 mb-1 block">Paste your {meta.label} API key</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? "text" : "password"}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={meta.placeholder}
                  autoComplete="off"
                  className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 pr-9 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
                />
                <button type="button" onClick={() => setShowKey((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                  {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <button onClick={handleSave} disabled={saving || !input.trim()}
                className="flex items-center gap-1.5 rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 text-xs font-semibold text-white shrink-0">
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
