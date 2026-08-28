/**
 * ZKTeco Integration
 * ─────────────────────────────────────────
 * Plant's "Solution" X606-S attendance terminals (ZKTeco protocol, port
 * 4370) — up to 8 physical machines (Lobby, Loker Male, Loker Female,
 * Server IT, Female Lab, Male Lab, Mall, Office; confirmed live 2026-08-28
 * via the "Solution" management software's own device list). Unlike
 * HikCentral (one device, one config), this manages a LIST of devices —
 * add/edit/remove/enable/test each one — since every device's swipes feed
 * the same employees' attendance and get merged per (employee, day).
 * Local `Panel`/`Btn`/`Field` helpers duplicated rather than shared,
 * matching the convention already used by HikCentralIntegration.jsx.
 */
import { useState, useEffect, useCallback } from "react";
import {
  Wifi, RefreshCw, Loader2, ChevronDown, ChevronUp,
  CheckCircle, XCircle, History, PlayCircle, HelpCircle,
  Plus, Pencil, Trash2, X,
} from "lucide-react";
import { zktecoApi } from "@/api/dashboard";

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

export default function ZKTecoIntegration() {
  const [devices, setDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [editing, setEditing] = useState(null); // device object being edited, or {} for new, or null

  const [testResults, setTestResults] = useState({}); // {deviceId: {ok, message/error}}
  const [testingId, setTestingId] = useState(null);

  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncError, setSyncError] = useState(null);

  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const refreshDevices = useCallback(async () => {
    setLoadingDevices(true);
    try { setDevices(await zktecoApi.getDevices()); }
    catch (_) {}
    finally { setLoadingDevices(false); }
  }, []);

  const refreshSyncStatus = useCallback(async () => {
    try { setSyncStatus(await zktecoApi.getSyncStatus()); } catch (_) {}
  }, []);

  const refreshHistory = useCallback(async () => {
    setLoadingHistory(true);
    try { setHistory(await zktecoApi.getSyncHistory(20)); }
    catch (_) {}
    finally { setLoadingHistory(false); }
  }, []);

  useEffect(() => { refreshDevices(); refreshSyncStatus(); refreshHistory(); }, [refreshDevices, refreshSyncStatus, refreshHistory]);

  const testDevice = async (id) => {
    setTestingId(id);
    setTestResults((r) => ({ ...r, [id]: null }));
    try {
      const res = await zktecoApi.testDevice(id);
      setTestResults((r) => ({ ...r, [id]: res }));
    } catch (e) {
      setTestResults((r) => ({ ...r, [id]: { ok: false, error: e?.detail || "Test failed" } }));
    } finally {
      setTestingId(null);
    }
  };

  const deleteDevice = async (id) => {
    if (!confirm("Remove this device? Its future attendance stops syncing, but past AttendanceRecord rows are kept.")) return;
    try { await zktecoApi.deleteDevice(id); await refreshDevices(); } catch (_) {}
  };

  const syncNow = async () => {
    setSyncing(true);
    setSyncResult(null);
    setSyncError(null);
    try {
      const r = await zktecoApi.syncNow();
      setSyncResult(r);
      await refreshSyncStatus();
      await refreshHistory();
    } catch (e) {
      setSyncError(e?.detail || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <>
      <Panel
        title="Devices"
        subtitle="Plant attendance terminals (ZKTeco protocol, port 4370 by default) — Lobby, Loker Male/Female, Server IT, Female/Male Lab, Mall, Office, ..."
        action={<Btn icon={Plus} variant="primary" onClick={() => setEditing({})}>Add Device</Btn>}
      >
        {loadingDevices ? (
          <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
        ) : devices.length === 0 ? (
          <Empty>No devices added yet — click "Add Device" to add the first Plant terminal.</Empty>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                  {["Name", "IP", "Port", "Status", "Test", ""].map((h) => <td key={h} className="px-3 py-2">{h}</td>)}
                </tr>
              </thead>
              <tbody>
                {devices.map((d) => {
                  const t = testResults[d.id];
                  return (
                    <tr key={d.id} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                      <td className="px-3 py-2" style={{ color: "#0f172a", fontWeight: 700 }}>{d.name}</td>
                      <td className="px-3 py-2" style={{ color: "#334155", fontFamily: "monospace" }}>{d.ip}</td>
                      <td className="px-3 py-2" style={{ color: "#334155", fontFamily: "monospace" }}>{d.port}</td>
                      <td className="px-3 py-2">
                        <span style={{
                          fontSize: 10.5, fontWeight: 700, padding: "2px 8px", borderRadius: 10,
                          background: d.enabled ? "rgba(22,163,74,0.1)" : "rgba(100,116,139,0.1)",
                          color: d.enabled ? "#16a34a" : "#64748b",
                        }}>
                          {d.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Btn size="sm" icon={testingId === d.id ? Loader2 : Wifi} disabled={testingId === d.id} onClick={() => testDevice(d.id)}>
                            {testingId === d.id ? "…" : "Test"}
                          </Btn>
                          {t && (
                            t.ok
                              ? <span style={{ fontSize: 10.5, color: "#16a34a", fontWeight: 700 }}>{t.message}</span>
                              : <span style={{ fontSize: 10.5, color: "#dc2626", fontWeight: 700 }}>{t.error}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => setEditing(d)} title="Edit" style={{ padding: 5, borderRadius: 6, border: "none", background: "rgba(37,99,235,0.1)", color: "#2563eb", cursor: "pointer" }}>
                            <Pencil size={12} />
                          </button>
                          <button onClick={() => deleteDevice(d.id)} title="Remove" style={{ padding: 5, borderRadius: 6, border: "none", background: "rgba(220,38,38,0.1)", color: "#dc2626", cursor: "pointer" }}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Attendance Sync" subtitle={`Background poll every ${syncStatus?.interval_minutes ?? 15} minutes — pulls each enabled device's full attendance log into Attendance.`}
        action={<Btn icon={syncing ? Loader2 : PlayCircle} disabled={syncing || !syncStatus?.configured} onClick={syncNow}>{syncing ? "Syncing…" : "Sync Now"}</Btn>}>
        {!syncStatus?.configured ? (
          <Empty>Add at least one device above first.</Empty>
        ) : (
          <div className="flex items-center gap-6 flex-wrap">
            <div>
              <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Last Sync</p>
              <p style={{ fontSize: 13, color: "#334155" }}>{fmtDate(syncStatus?.last_sync?.uploaded_at)}</p>
            </div>
            {syncStatus?.last_sync && (
              <>
                <div>
                  <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Employees</p>
                  <p style={{ fontSize: 13, color: "#334155" }}>{syncStatus.last_sync.total_rows} ({syncStatus.last_sync.inserted} new, {syncStatus.last_sync.updated} updated)</p>
                </div>
                <div>
                  <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Detail</p>
                  <p style={{ fontSize: 13, color: "#334155" }}>{syncStatus.last_sync.notes || "—"}</p>
                </div>
              </>
            )}
          </div>
        )}

        {syncResult && (
          <div className="mt-3 space-y-1.5">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: "rgba(22,163,74,0.08)", color: "#16a34a" }}>
              <CheckCircle size={14} /> Synced: {syncResult.events} events → {syncResult.employees} employees ({syncResult.inserted} new, {syncResult.updated} updated)
            </div>
            {syncResult.unmapped_ids?.length > 0 && (
              <div className="px-3 py-2 rounded-lg text-xs" style={{ background: "rgba(217,119,6,0.08)", color: "#d97706" }}>
                {syncResult.unmapped_ids.length} device user ID(s) had no matching employee: {syncResult.unmapped_ids.join(", ")}
              </div>
            )}
            {syncResult.device_errors?.length > 0 && (
              <div className="px-3 py-2 rounded-lg text-xs" style={{ background: "rgba(220,38,38,0.08)", color: "#dc2626" }}>
                {syncResult.device_errors.join(" · ")}
              </div>
            )}
          </div>
        )}
        {syncError && (
          <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: "rgba(220,38,38,0.08)", color: "#dc2626" }}>
            <XCircle size={14} /> {syncError}
          </div>
        )}
      </Panel>

      <Panel title={<span className="flex items-center gap-2"><History size={14} /> Sync History</span>}
        action={<Btn size="sm" icon={loadingHistory ? Loader2 : RefreshCw} disabled={loadingHistory} onClick={refreshHistory}>Refresh</Btn>}>
        {history.length === 0 ? (
          <Empty>No sync runs yet.</Empty>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(0,0,0,0.06)" }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: "#f8fafc", color: "#64748b", fontWeight: 700 }}>
                  {["Time", "By", "Employees", "New", "Updated", "Detail"].map((h) => <td key={h} className="px-3 py-2">{h}</td>)}
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.batch_id} style={{ borderTop: "1px solid rgba(0,0,0,0.05)" }}>
                    <td className="px-3 py-2" style={{ color: "#334155" }}>{fmtDate(h.uploaded_at)}</td>
                    <td className="px-3 py-2" style={{ color: "#334155" }}>{h.uploaded_by}</td>
                    <td className="px-3 py-2" style={{ color: "#334155" }}>{h.total_rows}</td>
                    <td className="px-3 py-2" style={{ color: "#16a34a" }}>{h.inserted}</td>
                    <td className="px-3 py-2" style={{ color: "#2563eb" }}>{h.updated}</td>
                    <td className="px-3 py-2" style={{ color: "#64748b" }}>{h.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {editing !== null && (
        <DeviceModal device={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refreshDevices(); refreshSyncStatus(); }} />
      )}

      <SetupGuide />
    </>
  );
}

/* ─── Device add/edit modal ─────────────────────────── */

function DeviceModal({ device, onClose, onSaved }) {
  const isNew = !device?.id;
  const [form, setForm] = useState({
    name: device?.name || "", ip: device?.ip || "", port: device?.port || 4370,
    password: 0, enabled: device?.enabled ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (!form.name.trim() || !form.ip.trim()) { setError("Name and IP are required."); return; }
    setSaving(true); setError("");
    try {
      const payload = { ...form, port: Number(form.port), password: Number(form.password) || 0 };
      if (isNew) await zktecoApi.createDevice(payload);
      else await zktecoApi.updateDevice(device.id, payload);
      onSaved();
    } catch (e) {
      setError(e?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(15,23,42,0.6)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-2xl" style={{ background: "#f1f5f9", boxShadow: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)" }}>
        <div className="flex items-center justify-between px-5 py-4" style={{ background: "linear-gradient(135deg, #2563eb, #3b82f6)", borderRadius: "16px 16px 0 0" }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, color: "#fff" }}>{isNew ? "Add Device" : `Edit ${device.name}`}</h3>
          <button onClick={onClose} style={{ padding: 6, borderRadius: 8, border: "none", background: "rgba(255,255,255,0.2)", color: "#fff", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Name">
            <input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Lobby" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="IP Address">
              <input style={inputStyle} value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} placeholder="172.21.10.205" />
            </Field>
            <Field label="Port">
              <input style={inputStyle} type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} placeholder="4370" />
            </Field>
          </div>
          <Field label="Comm Key / Password">
            <input style={inputStyle} type="number" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="0 (no password)" />
          </Field>
          <label className="flex items-center gap-2" style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
            Enabled (included in sync)
          </label>
          {error && <p style={{ fontSize: 11.5, color: "#dc2626" }}>{error}</p>}
          <Btn variant="primary" icon={saving ? Loader2 : CheckCircle} disabled={saving} onClick={save}>{saving ? "Saving…" : "Save"}</Btn>
        </div>
      </div>
    </div>
  );
}

/* ─── Setup Guide ────────────────────────────────────── */

function SetupGuide() {
  const [open, setOpen] = useState(false);
  return (
    <Panel
      title={<span className="flex items-center gap-2"><HelpCircle size={14} /> Setup Guide</span>}
      action={<Btn size="sm" icon={open ? ChevronUp : ChevronDown} onClick={() => setOpen((v) => !v)}>{open ? "Hide" : "Show"}</Btn>}
    >
      {open && (
        <div className="space-y-4" style={{ fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>1. Network reachability</p>
            <p>Plant terminals sit on their own network (confirmed 172.21.10.x) — this backend server must be able to reach that subnet on TCP port 4370 (or whatever port a specific device uses — "Mall" is configured on 4000 instead of 4370 in the "Solution" software, for example). This dev workstation cannot reach that subnet at all; verification for this integration was done via the deployed server instead.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>2. Comm Key / Password</p>
            <p>This is the device's numeric ZKTeco "comm key", not a login password — set via the terminal's own menu or the "Solution" desktop software. <code>0</code> means no key is set (confirmed for the Office terminal: "admin, tanpa password").</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>3. Employee ID matching</p>
            <p>These terminals enroll employees under a plain numeric ID (e.g. <code>24005</code>), not this app's full NIK (e.g. <code>P24005</code>). Sync resolves this automatically by matching the numeric suffix — no per-device mapping needed, but if a swipe's device ID doesn't match any employee (e.g. a stale/deleted enrollment), it's reported under "unmapped" in the sync result rather than silently dropped or guessed at.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>What syncs, and how</p>
            <p>Every 15 minutes (and on manual "Sync Now"), this pulls EVERY enabled device's full attendance log (these terminals don't support a date-range query — each sync re-reads and re-derives the whole thing, which is cheap at this scale) and merges swipes from all devices per employee per day — someone can swipe in at Lobby and out at Male Lab and both count toward the same day. Earliest swipe of the day = check-in, latest = check-out, same convention as the HikCentral integration; shows up in Attendance Today/Rate with <code>source = "zkteco"</code>.</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
