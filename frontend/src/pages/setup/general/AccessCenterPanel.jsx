import { useState, useEffect } from "react";
import { Search, Loader2, AlertTriangle, CheckCircle2, KeyRound, Database, Building2, Info } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/general/access-center";

// One-stop "what can this person do" lookup across the 3 systems this app
// touches: Dashboard roles (Keycloak, read-write here), EBS Chat / CoChat
// scope (its own existing CRUD at Setup > AI Tools > EBS Chat Access — this
// page shows a summary + a link there rather than re-implementing it), and
// Oracle EBS responsibilities (read-only — Oracle's own System
// Administrator responsibility remains the source of truth for actually
// granting/revoking those).
export default function AccessCenterPanel() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const [emailInput, setEmailInput] = useState("");
  const [activeEmail, setActiveEmail] = useState(null);
  const [data, setData] = useState(null);
  const [keycloakRoles, setKeycloakRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(null); // role name currently being toggled
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/keycloak/roles`, { headers });
        if (res.ok) setKeycloakRoles(await res.json());
      } catch (_) {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEmail = async (email) => {
    const clean = email.trim().toLowerCase();
    if (!clean) return;
    setActiveEmail(clean);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/user/${encodeURIComponent(clean)}`, { headers });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || "Failed to load the access data");
      setData(body);
    } catch (e) {
      setError(e.message || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const toggleRole = async (roleName, has) => {
    setSaving(roleName);
    try {
      const res = await fetch(`${API}/keycloak/${encodeURIComponent(activeEmail)}/roles/${encodeURIComponent(roleName)}`, {
        method: has ? "DELETE" : "PUT",
        headers,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Save failed");
      }
      setData((prev) => ({
        ...prev,
        keycloak: {
          ...prev.keycloak,
          roles: has ? prev.keycloak.roles.filter((r) => r !== roleName) : [...prev.keycloak.roles, roleName],
        },
      }));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <p className="text-xs text-gray-500 leading-relaxed">
        One screen to view/manage a person's access across 3 systems: Dashboard roles (Keycloak), EBS Chat/
        CoChat scope, and their Oracle EBS responsibilities for reference (view only — the actual setting stays in Oracle EBS).
      </p>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && openEmail(emailInput)}
            placeholder="user@ckd-otto.com"
            className="w-full rounded-lg border border-gray-700 bg-gray-900 pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
          />
        </div>
        <button onClick={() => openEmail(emailInput)} disabled={!emailInput.trim()}
          className="rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 transition-colors">
          Search
        </button>
      </div>

      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
      ) : activeEmail && data ? (
        <div className="space-y-4">
          <p className="text-sm font-semibold text-gray-200">{activeEmail}</p>

          {/* Panel 1: Dashboard roles */}
          <div className="rounded-xl border border-gray-800 bg-gray-900">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
              <KeyRound size={15} className="text-blue-400" />
              <p className="text-sm font-semibold text-gray-200">Dashboard Roles (Keycloak)</p>
            </div>
            {!data.keycloak.configured ? (
              <p className="px-4 py-4 text-xs text-gray-500">
                The Keycloak Admin API is not configured — manage roles in the Keycloak Admin Console.
              </p>
            ) : !data.keycloak.found ? (
              <p className="px-4 py-4 text-xs text-gray-500">No Keycloak account for this email.</p>
            ) : (
              <div className="p-4 flex flex-wrap gap-2">
                {keycloakRoles.map((r) => {
                  const has = data.keycloak.roles.includes(r.name);
                  const isSaving = saving === r.name;
                  return (
                    <button key={r.name} onClick={() => toggleRole(r.name, has)} disabled={isSaving}
                      title={r.description}
                      className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                        has ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-gray-800 text-gray-500 border border-gray-700"
                      }`}>
                      {isSaving ? <Loader2 size={12} className="animate-spin" /> : has ? <CheckCircle2 size={12} /> : null}
                      {r.name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Panel 2: EBS Chat / CoChat scope — link out to the existing CRUD */}
          <div className="rounded-xl border border-gray-800 bg-gray-900">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
              <Database size={15} className="text-emerald-400" />
              <p className="text-sm font-semibold text-gray-200">EBS Chat / CoChat Scope</p>
            </div>
            <div className="px-4 py-3 flex items-start gap-2">
              <Info size={13} className="text-gray-600 shrink-0 mt-0.5" />
              <p className="text-xs text-gray-500">
                Managed in <b>Setup &gt; AI Tools &gt; EBS Chat Access</b> (data departments, the modules they may
                use, and the company documents they may read) — not duplicated here.
              </p>
            </div>
          </div>

          {/* Panel 3: Oracle EBS Responsibility — read-only */}
          <div className="rounded-xl border border-gray-800 bg-gray-900">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
              <Building2 size={15} className="text-amber-400" />
              <p className="text-sm font-semibold text-gray-200">Oracle EBS Responsibility</p>
              <span className="ml-auto text-[10px] uppercase tracking-wider text-gray-600 font-bold">Read-only</span>
            </div>
            {data.oracle?.error ? (
              <p className="px-4 py-4 text-xs text-red-400">Failed to fetch Oracle data: {data.oracle.error}</p>
            ) : !data.oracle?.found ? (
              <p className="px-4 py-4 text-xs text-gray-500">No Oracle EBS account is registered for this email.</p>
            ) : (
              <div className="p-4 space-y-2">
                <p className="text-xs text-gray-400">
                  Oracle username: <span className="font-mono text-gray-300">{data.oracle.oracle_username}</span>
                </p>
                {data.oracle.is_shared_account && (
                  <div className="rounded-md px-3 py-2 text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-start gap-2">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                    This is a shared/admin account (not a personal one) — the responsibilities below do not reflect
                    this person's own access, but a shared account that happens to be registered with the same email.
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {data.oracle.responsibilities.length === 0 ? (
                    <p className="text-xs text-gray-600">No active responsibilities.</p>
                  ) : (
                    data.oracle.responsibilities.map((r) => (
                      <span key={r.name} className="rounded-full border border-gray-700 bg-gray-800 px-2.5 py-1 text-[11px] text-gray-300">
                        {r.name}
                      </span>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="py-10 text-center text-xs text-gray-600">Search for an email above to see its access.</div>
      )}
    </div>
  );
}
