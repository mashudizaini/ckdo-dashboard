import { useState, useEffect } from "react";
import { Search, Loader2, CheckCircle2, AlertTriangle, Users } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/general/access-control";

// Manages per-user grants for the modules relocated from Setup > IT (see
// GeneralSetupPage.jsx) — an explicit allow-list keyed by login email, NOT
// tied to Keycloak role. No autocomplete against the HR employee list on
// purpose (keeps this page decoupled from the HR module) — just type the
// email directly, or pick one of the previously-configured emails below.
export default function AccessControlPanel() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };

  const [menus, setMenus] = useState([]);
  const [configuredEmails, setConfiguredEmails] = useState([]);
  const [emailInput, setEmailInput] = useState("");
  const [activeEmail, setActiveEmail] = useState(null);
  const [access, setAccess] = useState(null); // {menu_key: bool}
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(null); // menu_key currently being toggled
  const [error, setError] = useState(null);

  const loadMenus = async () => {
    try {
      const res = await fetch(`${API}/menus`, { headers: hdrs });
      if (res.ok) setMenus(await res.json());
    } catch (_) {}
  };

  const loadConfiguredEmails = async () => {
    try {
      const res = await fetch(`${API}/users`, { headers: hdrs });
      if (res.ok) setConfiguredEmails(await res.json());
    } catch (_) {}
  };

  useEffect(() => { loadMenus(); loadConfiguredEmails(); }, []); // eslint-disable-line

  const openEmail = async (email) => {
    const clean = email.trim().toLowerCase();
    if (!clean) return;
    setActiveEmail(clean);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/users/${encodeURIComponent(clean)}`, { headers: hdrs });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to load access");
      setAccess(data.access);
    } catch (e) {
      setError(e.message || String(e));
      setAccess(null);
    } finally {
      setLoading(false);
    }
  };

  const toggle = async (menuKey, next) => {
    if (!activeEmail) return;
    setSaving(menuKey);
    try {
      const res = await fetch(`${API}/users/${encodeURIComponent(activeEmail)}/${encodeURIComponent(menuKey)}`, {
        method: "PUT",
        headers: { ...hdrs, "Content-Type": "application/json" },
        body: JSON.stringify({ granted: next }),
      });
      if (!res.ok) throw new Error("Failed to save");
      setAccess(prev => ({ ...prev, [menuKey]: next }));
      if (!configuredEmails.includes(activeEmail)) loadConfiguredEmails();
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4 max-w-2xl">
      <p className="text-xs text-gray-500 leading-relaxed">
        Grants access to the modules above by login email — independent of Keycloak role. A user with no grants here
        sees none of these tabs at all, and hitting their API directly returns 403.
      </p>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            value={emailInput}
            onChange={e => setEmailInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && openEmail(emailInput)}
            placeholder="user@company.com"
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
          />
        </div>
        <button onClick={() => openEmail(emailInput)} disabled={!emailInput.trim()}
          className="rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 transition-colors">
          Open
        </button>
      </div>

      {configuredEmails.length > 0 && (
        <div>
          <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <Users size={11} /> Already configured
          </p>
          <div className="flex flex-wrap gap-1.5">
            {configuredEmails.map(email => (
              <button key={email} onClick={() => { setEmailInput(email); openEmail(email); }}
                className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                  activeEmail === email
                    ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                    : "border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700"
                }`}>
                {email}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
      ) : activeEmail && access ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900">
          <div className="px-4 py-3 border-b border-gray-800">
            <p className="text-sm font-semibold text-gray-200">{activeEmail}</p>
          </div>
          <div className="divide-y divide-gray-800">
            {menus.map(m => {
              const isOn = !!access[m.menu_key];
              const isSaving = saving === m.menu_key;
              return (
                <label key={m.menu_key} className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-800/40 transition-colors">
                  <div>
                    <p className="text-sm text-gray-200">{m.label}</p>
                    <p className="text-[11px] text-gray-600">{m.section}</p>
                  </div>
                  <button
                    onClick={() => toggle(m.menu_key, !isOn)}
                    disabled={isSaving}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                      isOn ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-gray-800 text-gray-500 border border-gray-700"
                    }`}
                  >
                    {isSaving ? <Loader2 size={12} className="animate-spin" /> : isOn ? <CheckCircle2 size={12} /> : null}
                    {isOn ? "Granted" : "Not granted"}
                  </button>
                </label>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="py-10 text-center text-xs text-gray-600">Enter an email above to view/edit their access.</div>
      )}
    </div>
  );
}
