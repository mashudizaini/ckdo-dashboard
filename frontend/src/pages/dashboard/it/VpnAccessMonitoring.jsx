/**
 * VPN Access Monitoring
 * ─────────────────────────────────────────
 * Office FortiClient SSL-VPN gateway: reachability status (so IT can check
 * before users need it on a weekend), who's currently connected, and a
 * short uptime history. New module — see the local `Panel`/`Btn`/`Field`
 * helpers below, duplicated rather than shared, matching the convention
 * already used by EbsBackupRecovery.jsx for self-contained IT sub-tabs.
 */
import { useState, useEffect, useCallback } from "react";
import {
  Wifi, WifiOff, RefreshCw, Loader2, Settings2, Plus, Trash2,
  ChevronDown, ChevronUp, Clock, Key,
} from "lucide-react";
import { vpnApi } from "@/api/dashboard";

/* ─── Shared UI (local copy, see file header) ──────────────────────── */

function Panel({ title, subtitle, action, children }) {
  return (
    <div style={{ background: "#ffffff", borderRadius: 16, boxShadow: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", marginBottom: 16 }}>
      <div className="flex items-center justify-between px-5 py-3.5" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Btn({ onClick, children, variant = "default", disabled, icon: Icon, size = "md", type = "button" }) {
  const variants = {
    default: { bg: "#f1f5f9", color: "#334155" },
    primary: { bg: "#2563eb", color: "#ffffff" },
    danger: { bg: "#dc2626", color: "#ffffff" },
    ghost: { bg: "transparent", color: "#2563eb" },
  };
  const v = variants[variant] || variants.default;
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className="flex items-center gap-1.5 rounded-lg transition-all"
      style={{
        background: v.bg, color: v.color, fontWeight: 700,
        padding: size === "sm" ? "5px 10px" : "7px 14px",
        fontSize: size === "sm" ? 11 : 12,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
        border: "none",
      }}>
      {Icon && <Icon size={size === "sm" ? 12 : 13} />}{children}
    </button>
  );
}

const inputStyle = {
  width: "100%", padding: "7px 10px", borderRadius: 8, fontSize: 12.5,
  border: "1px solid rgba(15,23,42,0.14)", background: "#ffffff", color: "#0f172a",
};

function Field({ label, children }) {
  return (
    <div>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#64748b", display: "block", marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}

function Empty({ children }) {
  return <p style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "24px 0" }}>{children}</p>;
}

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch (_) { return iso; }
}

/* ─── Main ────────────────────────────────────────── */

export default function VpnAccessMonitoring() {
  const [gateways, setGateways] = useState([]);
  const [gatewayId, setGatewayId] = useState(null);
  const [loadingGateways, setLoadingGateways] = useState(true);
  const [showSetup, setShowSetup] = useState(false);

  const [checkResult, setCheckResult] = useState(null);
  const [checking, setChecking] = useState(false);

  const [sessions, setSessions] = useState(null);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const [history, setHistory] = useState([]);

  const refreshGateways = useCallback(async () => {
    setLoadingGateways(true);
    try {
      const rows = await vpnApi.listGateways();
      setGateways(rows);
      setGatewayId((cur) => cur && rows.some((g) => g.id === cur) ? cur : (rows[0]?.id ?? null));
    } catch (_) {
    } finally {
      setLoadingGateways(false);
    }
  }, []);

  useEffect(() => { refreshGateways(); }, [refreshGateways]);

  const gateway = gateways.find((g) => g.id === gatewayId) || null;

  const refreshHistory = useCallback(async () => {
    if (!gatewayId) return;
    try { setHistory(await vpnApi.getHistory(gatewayId, 24)); } catch (_) {}
  }, [gatewayId]);

  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  const refreshSessions = useCallback(async () => {
    if (!gatewayId || !gateway?.has_credential) { setSessions(null); return; }
    setLoadingSessions(true);
    try { setSessions(await vpnApi.getSessions(gatewayId)); }
    catch (e) { setSessions({ ok: false, error: e?.detail || "Failed to load sessions", sessions: [], raw_output: null }); }
    finally { setLoadingSessions(false); }
  }, [gatewayId, gateway?.has_credential]);

  useEffect(() => { refreshSessions(); }, [refreshSessions]);

  const checkNow = async () => {
    if (!gatewayId) return;
    setChecking(true);
    try {
      const r = await vpnApi.checkNow(gatewayId);
      setCheckResult(r);
      if (r.sessions) setSessions(r.sessions);
      await refreshHistory();
      await refreshGateways();
    } catch (e) {
      alert(e?.detail || "Check failed");
    } finally {
      setChecking(false);
    }
  };

  if (loadingGateways && !gateways.length) {
    return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  }

  return (
    <>
      {gateways.length > 1 && (
        <div className="mb-3">
          <select style={{ ...inputStyle, width: "auto", fontWeight: 700 }} value={gatewayId || ""} onChange={(e) => setGatewayId(Number(e.target.value))}>
            {gateways.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </div>
      )}

      {!gateway ? (
        <Panel title="VPN Access Monitoring" subtitle="No gateway configured yet — add one in Setup below.">
          <Empty>Belum ada VPN gateway terdaftar. Buka Setup di bawah untuk menambahkan.</Empty>
        </Panel>
      ) : (
        <>
          <Panel title={`Status — ${gateway.name}`} subtitle={`${gateway.public_host}:${gateway.public_port}`}
            action={<Btn icon={checking ? Loader2 : RefreshCw} disabled={checking} onClick={checkNow}>{checking ? "Checking…" : "Check Now"}</Btn>}>
            {!checkResult ? (
              <Empty>Klik "Check Now" untuk cek status VPN sekarang.</Empty>
            ) : (
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-2.5 rounded-xl px-4 py-3" style={{
                  background: checkResult.reachable ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)",
                }}>
                  {checkResult.reachable
                    ? <Wifi size={20} style={{ color: "#16a34a" }} />
                    : <WifiOff size={20} style={{ color: "#dc2626" }} />}
                  <div>
                    <p style={{ fontSize: 13, fontWeight: 800, color: checkResult.reachable ? "#16a34a" : "#dc2626" }}>
                      {checkResult.reachable ? "VPN Reachable" : "VPN Unreachable"}
                    </p>
                    {checkResult.error && <p style={{ fontSize: 11, color: "#dc2626" }}>{checkResult.error}</p>}
                  </div>
                </div>
                {checkResult.reachable && (
                  <div>
                    <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Latency</p>
                    <p style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{checkResult.latency_ms} ms</p>
                  </div>
                )}
                <div>
                  <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Checked At</p>
                  <p style={{ fontSize: 13, color: "#334155" }}>{fmtDate(checkResult.checked_at)}</p>
                </div>
              </div>
            )}

            {/* Uptime history strip */}
            {history.length > 0 && (
              <div className="mt-4 pt-4" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
                <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6 }}>
                  <Clock size={11} className="inline mr-1" style={{ marginTop: -2 }} />
                  Last 24 hours
                </p>
                <div className="flex gap-0.5">
                  {history.map((h, i) => (
                    <div key={i} title={`${fmtDate(h.checked_at)} — ${h.reachable ? `OK${h.latency_ms ? ` (${h.latency_ms}ms)` : ""}` : (h.error || "unreachable")}`}
                      style={{ flex: 1, height: 20, borderRadius: 2, background: h.reachable ? "#16a34a" : "#dc2626", opacity: h.reachable ? 0.7 : 1 }} />
                  ))}
                </div>
              </div>
            )}
          </Panel>

          <Panel title="Active VPN Users" subtitle={gateway.has_credential ? "Live from the FortiGate CLI (get vpn ssl monitor)." : "Add an SSH credential in Setup to enable this."}
            action={gateway.has_credential ? <Btn size="sm" icon={loadingSessions ? Loader2 : RefreshCw} disabled={loadingSessions} onClick={refreshSessions}>Refresh</Btn> : null}>
            {!gateway.has_credential ? (
              <Empty>Belum ada kredensial SSH FortiGate untuk gateway ini.</Empty>
            ) : loadingSessions && !sessions ? (
              <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
            ) : !sessions?.ok ? (
              <p style={{ fontSize: 11.5, color: "#dc2626" }}>{sessions?.error || "Failed to reach FortiGate CLI."}</p>
            ) : sessions.sessions.length === 0 ? (
              <Empty>Tidak ada user yang sedang konek VPN saat ini.</Empty>
            ) : (
              <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                      {Object.keys(sessions.sessions[0]).map((col) => <td key={col} className="px-3 py-2">{col}</td>)}
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.sessions.map((row, i) => (
                      <tr key={i} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                        {Object.keys(sessions.sessions[0]).map((col) => (
                          <td key={col} className="px-3 py-2" style={{ color: "#334155" }}>{row[col] ?? "—"}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {sessions?.raw_output && (
              <details className="mt-3">
                <summary style={{ fontSize: 11, color: "#64748b", cursor: "pointer" }}>Raw CLI output</summary>
                <pre style={{ background: "#0f172a", color: "#e2e8f0", fontSize: 10.5, padding: 10, borderRadius: 8, marginTop: 6, maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap" }}>
                  {sessions.raw_output}
                </pre>
              </details>
            )}
          </Panel>
        </>
      )}

      <SetupSection gateways={gateways} onChanged={refreshGateways} />
    </>
  );
}

/* ─── Setup ───────────────────────────────────────── */

function SetupSection({ gateways, onChanged }) {
  const [open, setOpen] = useState(gateways.length === 0);
  const [form, setForm] = useState({ name: "", public_host: "", public_port: 443, ssh_host: "", ssh_port: 22, notes: "", enabled: true });
  const [saving, setSaving] = useState(false);
  const [credForm, setCredForm] = useState({}); // { [gatewayId]: { username, password } }
  const [savingCred, setSavingCred] = useState(null);

  const saveGateway = async () => {
    if (!form.name || !form.public_host) return alert("Name and public host are required");
    setSaving(true);
    try {
      await vpnApi.upsertGateway({
        ...form,
        public_port: Number(form.public_port) || 443,
        ssh_host: form.ssh_host || null,
        ssh_port: Number(form.ssh_port) || 22,
      });
      setForm({ name: "", public_host: "", public_port: 443, ssh_host: "", ssh_port: 22, notes: "", enabled: true });
      await onChanged();
    } catch (e) {
      alert(e?.detail || "Failed to save gateway");
    } finally {
      setSaving(false);
    }
  };

  const deleteGateway = async (id) => {
    if (!confirm("Delete this gateway and its history?")) return;
    try { await vpnApi.deleteGateway(id); await onChanged(); }
    catch (e) { alert(e?.detail || "Delete failed"); }
  };

  const saveCred = async (gatewayId) => {
    const c = credForm[gatewayId];
    if (!c?.username || !c?.password) return alert("Username and password are required");
    setSavingCred(gatewayId);
    try {
      await vpnApi.upsertCredential(gatewayId, c);
      setCredForm((p) => ({ ...p, [gatewayId]: { username: "", password: "" } }));
      await onChanged();
    } catch (e) {
      alert(e?.detail || "Failed to save credential");
    } finally {
      setSavingCred(null);
    }
  };

  return (
    <Panel
      title={<span className="flex items-center gap-2"><Settings2 size={14} /> Setup</span>}
      action={<Btn size="sm" icon={open ? ChevronUp : ChevronDown} onClick={() => setOpen((v) => !v)}>{open ? "Hide" : "Show"}</Btn>}
    >
      {open && (
        <div className="space-y-5">
          {gateways.length > 0 && (
            <div className="space-y-3">
              {gateways.map((g) => (
                <div key={g.id} className="rounded-xl p-4" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>{g.name}</p>
                      <p style={{ fontSize: 11, color: "#94a3b8" }}>
                        Reachability: {g.public_host}:{g.public_port} · SSH: {g.ssh_host || g.public_host}:{g.ssh_port}
                        {g.has_credential ? " · credential set" : " · no credential"}
                      </p>
                    </div>
                    <Btn size="sm" variant="ghost" icon={Trash2} onClick={() => deleteGateway(g.id)}>Delete</Btn>
                  </div>
                  <div className="flex items-end gap-2 mt-2">
                    <div className="flex-1">
                      <Field label="SSH Username (FortiGate admin)">
                        <input style={inputStyle} value={credForm[g.id]?.username || ""}
                          onChange={(e) => setCredForm((p) => ({ ...p, [g.id]: { ...p[g.id], username: e.target.value } }))} />
                      </Field>
                    </div>
                    <div className="flex-1">
                      <Field label="Password">
                        <input type="password" style={inputStyle} value={credForm[g.id]?.password || ""}
                          onChange={(e) => setCredForm((p) => ({ ...p, [g.id]: { ...p[g.id], password: e.target.value } }))} />
                      </Field>
                    </div>
                    <Btn size="sm" icon={savingCred === g.id ? Loader2 : Key} disabled={savingCred === g.id} onClick={() => saveCred(g.id)}>
                      {savingCred === g.id ? "Saving…" : "Save Credential"}
                    </Btn>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="pt-4" style={{ borderTop: gateways.length > 0 ? "1px solid rgba(0,0,0,0.06)" : "none" }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 10 }}>Add Gateway</p>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <Field label="Name"><input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="CKD VPN Plant" /></Field>
              <Field label="Public Host (VPN endpoint)"><input style={inputStyle} value={form.public_host} onChange={(e) => setForm({ ...form, public_host: e.target.value })} placeholder="139.255.213.138" /></Field>
              <Field label="Public Port"><input type="number" style={inputStyle} value={form.public_port} onChange={(e) => setForm({ ...form, public_port: e.target.value })} /></Field>
              <Field label="FortiGate SSH Host (optional, defaults to Public Host)"><input style={inputStyle} value={form.ssh_host} onChange={(e) => setForm({ ...form, ssh_host: e.target.value })} /></Field>
              <Field label="FortiGate SSH Port"><input type="number" style={inputStyle} value={form.ssh_port} onChange={(e) => setForm({ ...form, ssh_port: e.target.value })} /></Field>
              <Field label="Notes"><input style={inputStyle} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            </div>
            <Btn variant="primary" icon={saving ? Loader2 : Plus} disabled={saving} onClick={saveGateway}>{saving ? "Saving…" : "Add / Update Gateway"}</Btn>
          </div>
        </div>
      )}
    </Panel>
  );
}
