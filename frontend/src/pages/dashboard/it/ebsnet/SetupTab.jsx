import { useCallback, useEffect, useState } from "react";
import { Save, Loader2, Plus, Trash2, Pencil, X } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Field, Note, Panel, Table, errText, inputStyle } from "./ui";

const SEGMENTS = [
  ["wan", "HO ↔ Plant path (device at HO, seen from Plant)"],
  ["plant_lan", "LAN Plant"],
  ["ebs_web", "EBS Web / App Tier"],
  ["ebs_db", "EBS Database"],
  ["internet", "Internet / ISP"],
  ["ho_lan", "LAN HO"],
];
const EMPTY_T = { name: "", segment: "wan", check_type: "tcp", host: "", port: "", url: "", enabled: true, sequence: 50, notes: "" };

const THRESHOLDS = [
  ["latency_warn", "Latency warning (ms)"], ["latency_crit", "Latency critical (ms)"],
  ["jitter_warn", "Jitter warning (ms)"], ["jitter_crit", "Jitter critical (ms)"],
  ["loss_warn", "Loss warning (%)"], ["loss_crit", "Loss critical (%)"],
  ["lan_rtt_warn", "Laptop→gateway RTT warning (ms)"], ["ttfb_warn", "EBS web TTFB warning (ms)"],
  ["cpu_warn", "Laptop CPU warning (%)"], ["ram_avail_warn", "Minimum free RAM (%)"],
  ["fgt_cpu_warn", "FortiGate CPU warning (%)"], ["fgt_mem_warn", "FortiGate memory warning (%)"],
];

function TargetForm({ initial, onSaved, onCancel }) {
  const [t, setT] = useState(initial);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setT({ ...t, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const save = async () => {
    if (!t.name) return alert("Name is required");
    setSaving(true);
    try {
      await ebsNetApi.upsertTarget({ ...t, port: t.port ? Number(t.port) : null, sequence: Number(t.sequence) || 0,
        host: t.host || null, url: t.url || null });
      onSaved();
    } catch (e) { alert(errText(e)); } finally { setSaving(false); }
  };
  return (
    <div className="rounded-xl p-4 mb-3" style={{ border: "1px solid rgba(37,99,235,0.25)", background: "rgba(37,99,235,0.03)" }}>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Field label="Name"><input style={inputStyle} value={t.name} onChange={set("name")} /></Field>
        <Field label="Segment">
          <select style={inputStyle} value={t.segment} onChange={set("segment")}>{SEGMENTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </Field>
        <Field label="Check type">
          <select style={inputStyle} value={t.check_type} onChange={set("check_type")}>
            <option value="tcp">TCP connect (host:port)</option><option value="http">HTTP TTFB (URL)</option>
          </select>
        </Field>
        <Field label="Order"><input type="number" style={inputStyle} value={t.sequence} onChange={set("sequence")} /></Field>
        {t.check_type === "tcp" ? (
          <>
            <Field label="Host / IP"><input style={inputStyle} value={t.host || ""} onChange={set("host")} /></Field>
            <Field label="Port" hint="e.g. 443 FortiGate, 1521 DB, 8000 EBS web"><input type="number" style={inputStyle} value={t.port || ""} onChange={set("port")} /></Field>
          </>
        ) : (
          <div className="md:col-span-2"><Field label="URL" hint="e.g. http://ebs-host:8000/OA_HTML/AppsLocalLogin.jsp"><input style={inputStyle} value={t.url || ""} onChange={set("url")} /></Field></div>
        )}
        <div className="md:col-span-2"><Field label="Notes"><input style={inputStyle} value={t.notes || ""} onChange={set("notes")} /></Field></div>
      </div>
      <div className="flex items-center gap-3 mt-3">
        <label className="flex items-center gap-2" style={{ fontSize: 12 }}><input type="checkbox" checked={!!t.enabled} onChange={set("enabled")} /> Active</label>
        <Btn variant="primary" size="sm" icon={saving ? Loader2 : Save} spin={saving} disabled={saving} onClick={save}>Save target</Btn>
        <Btn size="sm" icon={X} onClick={onCancel}>Cancel</Btn>
      </div>
    </div>
  );
}

export default function SetupTab({ settings, onSettingsSaved }) {
  const [s, setS] = useState(null);
  const [servers, setServers] = useState([]);
  const [targets, setTargets] = useState([]);
  const [editT, setEditT] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadTargets = useCallback(async () => {
    try { setTargets(await ebsNetApi.listTargets()); } catch (e) { alert(errText(e)); }
  }, []);

  useEffect(() => {
    if (settings) setS({ ...settings, ebs_ports_text: (settings.ebs_ports || []).join(", "), tunnel_names_text: (settings.tunnel_names || []).join(", ") });
  }, [settings]);
  useEffect(() => { ebsNetApi.listServers().then(setServers).catch(() => {}); loadTargets(); }, [loadTargets]);

  if (!s) return null;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const setTh = (k) => (e) => setS({ ...s, thresholds: { ...s.thresholds, [k]: Number(e.target.value) } });

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        ebs_host: s.ebs_host?.trim(), ebs_web_url: s.ebs_web_url?.trim(), browser_probe_url: s.browser_probe_url?.trim(),
        ebs_ports: s.ebs_ports_text.split(/[,\s]+/).map(Number).filter((n) => n > 0 && n < 65536),
        tunnel_names: s.tunnel_names_text.split(/[,\s]+/).filter(Boolean),
        fortigate_ho_server_id: s.fortigate_ho_server_id ? Number(s.fortigate_ho_server_id) : null,
        fortigate_plant_server_id: s.fortigate_plant_server_id ? Number(s.fortigate_plant_server_id) : null,
        poll_fortigate: !!s.poll_fortigate, poll_ebs: !!s.poll_ebs,
        probe_samples: Math.min(Math.max(Number(s.probe_samples) || 5, 1), 20), thresholds: s.thresholds,
      };
      await ebsNetApi.putSettings(body);
      await onSettingsSaved();
    } catch (e) { alert(errText(e, "Save failed")); } finally { setSaving(false); }
  };

  const delTarget = async (id) => {
    if (!confirm("Delete this target and its history?")) return;
    try { await ebsNetApi.deleteTarget(id); loadTargets(); } catch (e) { alert(errText(e)); }
  };

  const serverOpt = (sv) => `${sv.name} (${sv.ip || "?"}:${sv.port})${sv.problem ? ` — ${sv.problem}` : ""}`;

  return (
    <>
      <Panel title="Settings" action={<Btn variant="primary" icon={saving ? Loader2 : Save} spin={saving} disabled={saving} onClick={save}>Save</Btn>}>
        <div className="space-y-5">
          <div>
            <p style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>Oracle EBS (used by the laptop agent)</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="EBS host / IP the agent pings" hint="Ideally the web/app tier server users access"><input style={inputStyle} value={s.ebs_host || ""} onChange={set("ebs_host")} /></Field>
              <Field label="EBS ports for the TCP test" hint="Comma-separated, e.g. 8000, 1521"><input style={inputStyle} value={s.ebs_ports_text} onChange={set("ebs_ports_text")} /></Field>
              <Field label="EBS login URL" hint=".../OA_HTML/AppsLocalLogin.jsp — for HTTP TTFB"><input style={inputStyle} value={s.ebs_web_url || ""} onChange={set("ebs_web_url")} /></Field>
              <div className="md:col-span-3">
                <Field label="Static image URL on the EBS web for the browser test (optional)"
                  hint="Only works if EBS uses https (browsers block http from an https page). Example: https://ebs-host:4443/OA_MEDIA/FNDSSCORP.gif">
                  <input style={inputStyle} value={s.browser_probe_url || ""} onChange={set("browser_probe_url")} />
                </Field>
              </div>
            </div>
          </div>

          <div>
            <p style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>FortiGate (from Server Control)</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="FortiGate HO">
                <select style={inputStyle} value={s.fortigate_ho_server_id || ""} onChange={set("fortigate_ho_server_id")}>
                  <option value="">— not used —</option>
                  {servers.map((sv) => <option key={sv.id} value={sv.id}>{serverOpt(sv)}</option>)}
                </select>
              </Field>
              <Field label="FortiGate Plant">
                <select style={inputStyle} value={s.fortigate_plant_server_id || ""} onChange={set("fortigate_plant_server_id")}>
                  <option value="">— not used —</option>
                  {servers.map((sv) => <option key={sv.id} value={sv.id}>{serverOpt(sv)}</option>)}
                </select>
              </Field>
              <Field label="HO↔Plant tunnel names" hint="For reference, comma-separated"><input style={inputStyle} value={s.tunnel_names_text} onChange={set("tunnel_names_text")} /></Field>
            </div>
            <Note>Not in the list? Add the FortiGate in IT &gt; Server Control (internal LAN IP, SSH port, read-only admin account). Credentials are not copied into this module.</Note>
          </div>

          <div>
            <p style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>Automatic poller (every 5 minutes)</p>
            <div className="flex gap-6 flex-wrap items-end">
              <label className="flex items-center gap-2" style={{ fontSize: 12 }}><input type="checkbox" checked={!!s.poll_fortigate} onChange={set("poll_fortigate")} /> Snapshot FortiGate</label>
              <label className="flex items-center gap-2" style={{ fontSize: 12 }}><input type="checkbox" checked={!!s.poll_ebs} onChange={set("poll_ebs")} /> EBS health snapshot</label>
              <div style={{ width: 160 }}><Field label="Samples per probe"><input type="number" style={inputStyle} value={s.probe_samples} onChange={set("probe_samples")} /></Field></div>
            </div>
          </div>

          <div>
            <p style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>Thresholds</p>
            <p style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>Defaults from script §11: loss 0 %, latency &lt; 50 ms, jitter &lt; 10 ms, CPU &lt; 80 %, free RAM &gt; 20 % — an operational baseline, not an official Oracle requirement.</p>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {THRESHOLDS.map(([k, l]) => (
                <Field key={k} label={l}><input type="number" step="0.1" style={inputStyle} value={s.thresholds?.[k] ?? ""} onChange={setTh(k)} /></Field>
              ))}
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Server probe targets" subtitle="Probed from the dashboard server at Plant"
        action={!editT && <Btn size="sm" icon={Plus} onClick={() => setEditT({ ...EMPTY_T })}>Add target</Btn>}>
        {editT && <TargetForm initial={editT} onCancel={() => setEditT(null)} onSaved={() => { setEditT(null); loadTargets(); }} />}
        <Table rows={targets} empty="No targets yet."
          columns={[
            { key: "sequence", label: "#", align: "right" },
            { key: "name", label: "Name" },
            { key: "segment", label: "Segment", render: (r) => SEGMENTS.find(([k]) => k === r.segment)?.[1] || r.segment },
            { key: "addr", label: "Address", render: (r) => r.check_type === "http" ? (r.url || "—") : `${r.host || "?"}:${r.port || "?"}` },
            { key: "enabled", label: "Active", render: (r) => r.enabled ? "yes" : "no" },
            { key: "notes", label: "Notes", wrap: true },
            { key: "act", label: "", render: (r) => (
              <div className="flex gap-1">
                <Btn size="sm" variant="ghost" icon={Pencil} onClick={() => setEditT({ ...EMPTY_T, ...r, port: r.port ?? "", host: r.host ?? "", url: r.url ?? "", notes: r.notes ?? "" })}>Edit</Btn>
                <Btn size="sm" variant="ghost" icon={Trash2} onClick={() => delTarget(r.id)}>Delete</Btn>
              </div>
            ) },
          ]} />
        <div className="mt-3">
          <Note>
            Suggested targets: <b>HO FortiGate LAN IP :443</b> and one server/printer at HO (Path segment — measures the tunnel),
            <b> EBS web :8000/4443</b> + <b>login URL (HTTP)</b> (EBS Web), <b>DB listener :1521</b> (Database), <b>Plant LAN gateway</b> (Plant LAN),
            and <b>1.1.1.1:443</b> (Internet, Plant ISP comparison).
          </Note>
        </div>
      </Panel>
    </>
  );
}
