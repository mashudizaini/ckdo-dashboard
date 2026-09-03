import { useState, useEffect } from "react";
import { Cpu, Sparkles, Gem, Loader2, MessageSquare, Database, MessagesSquare } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// Matches ai_chat_provider_service.PROVIDERS exactly — id must be the
// provider string the backend/frontend already use everywhere else
// ("onprem"/"anthropic"/"gemini"), not a display-only slug.
const MODELS = [
  { id: "onprem",    label: "On-Premise",  icon: Cpu,      desc: "Model lokal di server ai-engine — gratis, tanpa biaya per token." },
  { id: "anthropic", label: "Claude",      icon: Sparkles, desc: "Anthropic Claude — berbayar per token, plus biaya pencarian web di General Chat." },
  { id: "gemini",    label: "Gemini",      icon: Gem,      desc: "Google Gemini — berbayar per token (jauh lebih murah dari Claude), pencarian web punya kuota gratis bulanan." },
];

// Matches ai_chat_provider_service.MODES exactly.
const MODES = [
  { id: "policy",  label: "Company Policy",   icon: MessageSquare },
  { id: "oracle",  label: "Oracle ERP Data",  icon: Database },
  { id: "general", label: "General Chat",     icon: MessagesSquare },
];

export default function ModelAccessPanel() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const [status, setStatus] = useState(null); // {onprem, anthropic, gemini} | null while loading
  const [defaults, setDefaults] = useState(null); // {policy, oracle, general} | null while loading
  const [saving, setSaving] = useState(null); // provider id, or `default-${mode}`, currently being saved
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [statusRes, defaultsRes] = await Promise.all([
        fetch("/api/v1/ai/chatbot/provider-status", { headers }),
        fetch("/api/v1/ai/chatbot/default-providers", { headers }),
      ]);
      if (statusRes.ok) setStatus(await statusRes.json());
      if (defaultsRes.ok) setDefaults(await defaultsRes.json());
    } catch (_) {}
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  const toggle = async (id, next) => {
    setSaving(id);
    setError(null);
    try {
      const res = await fetch(`/api/v1/ai/chatbot/provider-status/${id}`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Gagal menyimpan (${res.status})`);
      }
      setStatus(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(null);
    }
  };

  const setDefault = async (mode, provider) => {
    const key = `default-${mode}`;
    setSaving(key);
    setError(null);
    try {
      const res = await fetch(`/api/v1/ai/chatbot/default-providers/${mode}`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ provider }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Gagal menyimpan (${res.status})`);
      }
      setDefaults(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(null);
    }
  };

  if (status === null || defaults === null) {
    return <div className="p-6 flex justify-center"><Loader2 size={20} className="animate-spin text-gray-600" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-800 bg-gray-900">
        <div className="px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">Model Access</h3>
          <p className="text-xs text-gray-500 mt-1">
            Kontrol model AI mana yang boleh dipilih user di AI Chatbot (Company Policy, Oracle ERP Data, dan General Chat). Tidak mempengaruhi fitur AI lain (CV Screening, Meeting Notes, dll).
          </p>
        </div>

        <div className="p-5 space-y-3">
          {error && (
            <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>
          )}
          {MODELS.map((m) => {
            const enabled = status[m.id] !== false;
            return (
              <label key={m.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3 cursor-pointer hover:border-gray-700 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <m.icon size={18} className={enabled ? "text-blue-400 shrink-0" : "text-gray-600 shrink-0"} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-200">{m.label}</p>
                    <p className="text-xs text-gray-500 truncate">{m.desc}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {saving === m.id && <Loader2 size={14} className="animate-spin text-gray-500" />}
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={saving === m.id}
                    onChange={(e) => toggle(m.id, e.target.checked)}
                    className="w-4 h-4 accent-blue-600 cursor-pointer disabled:opacity-50"
                  />
                </div>
              </label>
            );
          })}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900">
        <div className="px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">Default Model per Mode</h3>
          <p className="text-xs text-gray-500 mt-1">
            Model yang otomatis terpilih saat user pertama kali membuka tiap mode chat (di halaman AI Chatbot maupun widget chat). User tetap bisa mengganti sendiri di dropdown provider — ini cuma titik awalnya.
          </p>
        </div>

        <div className="p-5 space-y-3">
          {MODES.map((mode) => {
            const key = `default-${mode.id}`;
            return (
              <div key={mode.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <mode.icon size={18} className="text-gray-400 shrink-0" />
                  <p className="text-sm font-medium text-gray-200">{mode.label}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {saving === key && <Loader2 size={14} className="animate-spin text-gray-500" />}
                  <select
                    value={defaults[mode.id]}
                    disabled={saving === key}
                    onChange={(e) => setDefault(mode.id, e.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-300 outline-none focus:border-blue-500 cursor-pointer disabled:opacity-50"
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
