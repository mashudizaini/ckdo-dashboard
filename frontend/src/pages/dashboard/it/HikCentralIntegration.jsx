/**
 * HikCentral Integration
 * ─────────────────────────────────────────
 * One place to configure and control the office's HikCentral OpenAPI
 * connection (the Hikvision DS-K1T342MFWX face-recognition terminals report
 * to HikCentral, not directly to this app) — connection status, a manual
 * connectivity test, the 15-minute background sync's status/history, and a
 * manual "Sync Now". Config is DB-backed (editable here, takes effect
 * immediately) instead of requiring an SSH session + .env edit + backend
 * restart, which was the slow loop the initial integration setup went
 * through. Local `Panel`/`Btn`/`Field` helpers duplicated rather than
 * shared, matching the convention already used by VpnAccessMonitoring.jsx.
 */
import { useState, useEffect, useCallback } from "react";
import {
  Wifi, WifiOff, RefreshCw, Loader2, Settings2, ChevronDown, ChevronUp,
  Clock, CheckCircle, XCircle, History, PlayCircle, HelpCircle,
} from "lucide-react";
import { hikcentralApi } from "@/api/dashboard";

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

const SOURCE_LABEL = { database: "Saved in dashboard (Setup below)", env: "Server .env (not yet saved here)", none: "Not configured" };

/* ─── Main ────────────────────────────────────────── */

export default function HikCentralIntegration() {
  const [config, setConfig] = useState(null);
  const [loadingConfig, setLoadingConfig] = useState(true);

  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncError, setSyncError] = useState(null);

  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const refreshConfig = useCallback(async () => {
    setLoadingConfig(true);
    try { setConfig(await hikcentralApi.getConfig()); }
    catch (_) {}
    finally { setLoadingConfig(false); }
  }, []);

  const refreshSyncStatus = useCallback(async () => {
    try { setSyncStatus(await hikcentralApi.getSyncStatus()); } catch (_) {}
  }, []);

  const refreshHistory = useCallback(async () => {
    setLoadingHistory(true);
    try { setHistory(await hikcentralApi.getSyncHistory(20)); }
    catch (_) {}
    finally { setLoadingHistory(false); }
  }, []);

  useEffect(() => { refreshConfig(); refreshSyncStatus(); refreshHistory(); }, [refreshConfig, refreshSyncStatus, refreshHistory]);

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try { setTestResult(await hikcentralApi.testConnection()); }
    catch (e) { setTestResult({ ok: false, error: e?.detail || "Test request failed" }); }
    finally { setTesting(false); }
  };

  const syncNow = async () => {
    setSyncing(true);
    setSyncResult(null);
    setSyncError(null);
    try {
      const r = await hikcentralApi.syncNow();
      setSyncResult(r);
      await refreshSyncStatus();
      await refreshHistory();
    } catch (e) {
      setSyncError(e?.detail || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  if (loadingConfig && !config) {
    return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  }

  return (
    <>
      <Panel title="Connection Status" subtitle="HikCentral OpenAPI (Artemis) — aggregates the Hikvision DS-K1T342MFWX terminals."
        action={<Btn icon={testing ? Loader2 : Wifi} disabled={testing} onClick={testConnection}>{testing ? "Testing…" : "Test Connection"}</Btn>}>
        <div className="flex items-center gap-4 flex-wrap mb-4">
          <div className="flex items-center gap-2.5 rounded-xl px-4 py-3" style={{
            background: config?.configured ? "rgba(22,163,74,0.08)" : "rgba(217,119,6,0.08)",
          }}>
            {config?.configured
              ? <CheckCircle size={20} style={{ color: "#16a34a" }} />
              : <XCircle size={20} style={{ color: "#d97706" }} />}
            <div>
              <p style={{ fontSize: 13, fontWeight: 800, color: config?.configured ? "#16a34a" : "#d97706" }}>
                {config?.configured ? "Configured" : "Not Configured"}
              </p>
              <p style={{ fontSize: 11, color: "#64748b" }}>{SOURCE_LABEL[config?.source] || "—"}</p>
            </div>
          </div>
          <div>
            <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>Base URL</p>
            <p style={{ fontSize: 13, color: "#334155", fontFamily: "monospace" }}>{config?.base_url || "—"}</p>
          </div>
          <div>
            <p style={{ fontSize: 10.5, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>AppKey</p>
            <p style={{ fontSize: 13, color: "#334155", fontFamily: "monospace" }}>{config?.app_key_masked || "—"}</p>
          </div>
        </div>

        {testResult && (
          <div className={`flex items-start gap-2 px-3 py-2.5 rounded-lg text-sm`} style={{
            background: testResult.ok ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)",
            color: testResult.ok ? "#16a34a" : "#dc2626",
          }}>
            {testResult.ok ? <CheckCircle size={15} className="shrink-0 mt-0.5" /> : <XCircle size={15} className="shrink-0 mt-0.5" />}
            <span>{testResult.ok ? testResult.message : testResult.error}</span>
          </div>
        )}
      </Panel>

      <Panel title="Attendance Sync" subtitle={`Background poll every ${syncStatus?.interval_minutes ?? 15} minutes — pulls today's door events into Attendance.`}
        action={<Btn icon={syncing ? Loader2 : PlayCircle} disabled={syncing || !config?.configured} onClick={syncNow}>{syncing ? "Syncing…" : "Sync Now"}</Btn>}>
        {!config?.configured ? (
          <Empty>Configure the connection below first.</Empty>
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
          <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: "rgba(22,163,74,0.08)", color: "#16a34a" }}>
            <CheckCircle size={14} /> Synced: {syncResult.events} events → {syncResult.employees} employees ({syncResult.inserted} new, {syncResult.updated} updated)
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

      <SetupSection config={config} onChanged={refreshConfig} />
      <SetupGuide />
    </>
  );
}

/* ─── Setup ───────────────────────────────────────── */

function SetupSection({ config, onChanged }) {
  const [open, setOpen] = useState(!config?.configured);
  const [form, setForm] = useState({ base_url: config?.base_url || "", app_key: "", app_secret: "" });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    setForm((p) => ({ ...p, base_url: config?.base_url || p.base_url }));
    if (config && !config.configured) setOpen(true);
  }, [config?.base_url, config?.configured]);

  const save = async () => {
    if (!form.base_url || !form.app_key || !form.app_secret) {
      setSaveError("Base URL, AppKey, and AppSecret are all required.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await hikcentralApi.saveConfig(form);
      setForm({ base_url: form.base_url, app_key: "", app_secret: "" });
      await onChanged();
    } catch (e) {
      setSaveError(e?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel
      title={<span className="flex items-center gap-2"><Settings2 size={14} /> Setup</span>}
      action={<Btn size="sm" icon={open ? ChevronUp : ChevronDown} onClick={() => setOpen((v) => !v)}>{open ? "Hide" : "Show"}</Btn>}
    >
      {open && (
        <div className="space-y-3">
          <p style={{ fontSize: 11.5, color: "#64748b" }}>
            From HikCentral: System &gt; Open Platform (or "Third-party Integration") &gt; add an Integration
            Partner to get an AppKey + AppSecret. Base URL is HikCentral's own host (e.g. <code>https://172.21.x.x</code>),
            not the individual terminal IPs.
          </p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Base URL">
              <input style={inputStyle} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://172.21.x.x" />
            </Field>
            <Field label="AppKey">
              <input style={inputStyle} value={form.app_key} onChange={(e) => setForm({ ...form, app_key: e.target.value })} placeholder={config?.app_key_masked || "AppKey"} />
            </Field>
            <Field label="AppSecret">
              <input type="password" style={inputStyle} value={form.app_secret} onChange={(e) => setForm({ ...form, app_secret: e.target.value })} placeholder="Leave blank to keep existing" />
            </Field>
          </div>
          {saveError && <p style={{ fontSize: 11.5, color: "#dc2626" }}>{saveError}</p>}
          <Btn variant="primary" icon={saving ? Loader2 : CheckCircle} disabled={saving} onClick={save}>{saving ? "Saving…" : "Save Config"}</Btn>
        </div>
      )}
    </Panel>
  );
}

/* ─── Setup Guide — distilled from the initial live debugging session ── */

function SetupGuide() {
  const [open, setOpen] = useState(false);
  return (
    <Panel
      title={<span className="flex items-center gap-2"><HelpCircle size={14} /> Setup Guide &amp; Troubleshooting</span>}
      action={<Btn size="sm" icon={open ? ChevronUp : ChevronDown} onClick={() => setOpen((v) => !v)}>{open ? "Hide" : "Show"}</Btn>}
    >
      {open && (
        <div className="space-y-4" style={{ fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>1. Network reachability</p>
            <p>This backend server must reach HikCentral's Base URL over the network — a plain ping is not enough, the exact
              port used by Base URL (usually 443) must also be open. If Test Connection times out, check firewall rules
              between the two sites/subnets first.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>2. Create an Integration Partner</p>
            <p>In HikCentral: <strong>System &gt; Open Platform</strong> (some editions call it "Third-party Integration") &gt;
              add a new Integration Partner. This generates the AppKey/AppSecret pair used above — make sure to save the
              Secret shown at creation time, HikCentral won't show it again.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>3. Authorize the APIs this integration needs</p>
            <p>Still under Open Platform, the Integration Partner has an <strong>"Authorized APIs"</strong> list — if this is
              empty, every call fails regardless of how correct the AppKey/AppSecret/Base URL are. This is the most common
              blocker: the OpenAPI Gateway module sometimes needs a separate license activation before any APIs can be
              authorized at all. If Test Connection keeps failing and steps 1-2 check out, check License Management in
              HikCentral (or contact your HikCentral integrator/vendor) for an OpenAPI Gateway license.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>4. Signing quirks across HikCentral editions</p>
            <p>The signing scheme (HMAC-SHA256, Alibaba Cloud API Gateway-style headers) is Hikvision's documented Artemis/
              OpenAPI convention, but exact header casing/order can vary slightly by version — most HikCentral installs
              ship (or let you download) an "OpenAPI Development Guide" PDF with one worked signed-request example for
              your exact version, useful for comparing against a failing request here.</p>
          </div>
          <div>
            <p style={{ fontWeight: 700, marginBottom: 4 }}>What syncs, and how</p>
            <p>Every 15 minutes (and on manual "Sync Now"), this pulls the day's raw door (face-recognition check-in)
              events and derives each employee's earliest event as check-in / latest as check-out — the same
              upsert-by-(employee, date) pattern as the other attendance sources (Plant/Intercom/Talenta uploads), so it
              shows up in Attendance Today/Rate with <code>source = "hikcentral"</code>.</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
