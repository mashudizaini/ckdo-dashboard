import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Loader2, Save, X, Trash2, Pencil } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Field, Level, Note, Panel, Stat, Table, fmtDate, errText, inputStyle, probeLevel } from "./ui";

const GROUPS = [["NET", "Network"], ["CLI", "Client"], ["EBS", "EBS"], ["DB", "Database"]];

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);

const EMPTY = {
  started_at: "", ended_at: "", status: "open", user_name: "", laptop: "", location: "HO",
  ebs_module: "", transaction: "", symptom: "", root_cause_code: "", root_cause: "", corrective_action: "",
  client_report_id: "", capture_now: true,
};

function IncidentForm({ initial, codes, reports, onSaved, onCancel }) {
  const [f, setF] = useState(initial);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const save = async () => {
    if (!f.started_at) return alert("Waktu mulai wajib diisi — waktu yang tepat adalah kunci korelasi log");
    setSaving(true);
    const body = {
      ...f, started_at: fromLocalInput(f.started_at), ended_at: fromLocalInput(f.ended_at),
      root_cause_code: f.root_cause_code || null, client_report_id: f.client_report_id ? Number(f.client_report_id) : null,
    };
    try {
      if (f.id) await ebsNetApi.updateIncident(f.id, body); else await ebsNetApi.createIncident(body);
      onSaved();
    } catch (e) { alert(errText(e, "Gagal menyimpan")); } finally { setSaving(false); }
  };

  return (
    <Panel title={f.id ? `Edit insiden #${f.id}` : "Catat insiden baru"} action={<Btn size="sm" icon={X} onClick={onCancel}>Batal</Btn>}>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Field label="Waktu mulai *"><input type="datetime-local" style={inputStyle} value={f.started_at} onChange={set("started_at")} /></Field>
        <Field label="Waktu selesai"><input type="datetime-local" style={inputStyle} value={f.ended_at} onChange={set("ended_at")} /></Field>
        <Field label="Status">
          <select style={inputStyle} value={f.status} onChange={set("status")}>
            <option value="open">Open</option><option value="investigating">Investigasi</option><option value="resolved">Resolved</option>
          </select>
        </Field>
        <Field label="Lokasi"><input style={inputStyle} value={f.location} onChange={set("location")} /></Field>
        <Field label="User"><input style={inputStyle} value={f.user_name} onChange={set("user_name")} /></Field>
        <Field label="Laptop"><input style={inputStyle} value={f.laptop} onChange={set("laptop")} /></Field>
        <Field label="Modul EBS"><input style={inputStyle} value={f.ebs_module} onChange={set("ebs_module")} placeholder="mis. Payables" /></Field>
        <Field label="Transaksi / form"><input style={inputStyle} value={f.transaction} onChange={set("transaction")} placeholder="mis. Invoice Workbench" /></Field>
        <div className="md:col-span-2"><Field label="Gejala"><textarea rows={2} style={inputStyle} value={f.symptom} onChange={set("symptom")} placeholder="Lambat / hang / FRM-92xxx / harus restart browser…" /></Field></div>
        <div className="md:col-span-2">
          <Field label="Laporan laptop terkait (opsional)">
            <select style={inputStyle} value={f.client_report_id || ""} onChange={set("client_report_id")}>
              <option value="">—</option>
              {reports.map((r) => <option key={r.id} value={r.id}>#{r.id} · {fmtDate(r.created_at)} · {r.hostname || r.reported_by} · {r.verdict}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Kode root cause">
          <select style={inputStyle} value={f.root_cause_code || ""} onChange={set("root_cause_code")}>
            <option value="">Belum diketahui</option>
            {GROUPS.map(([g, label]) => (
              <optgroup key={g} label={label}>
                {Object.entries(codes).filter(([c]) => c.startsWith(`${g}-`)).map(([c, l]) => <option key={c} value={c}>{c} {l}</option>)}
              </optgroup>
            ))}
          </select>
        </Field>
        <div className="md:col-span-3"><Field label="Root cause"><input style={inputStyle} value={f.root_cause} onChange={set("root_cause")} /></Field></div>
        <div className="md:col-span-4"><Field label="Corrective action"><textarea rows={2} style={inputStyle} value={f.corrective_action} onChange={set("corrective_action")} /></Field></div>
      </div>
      <div className="flex items-center gap-4 mt-4 flex-wrap">
        <label className="flex items-center gap-2" style={{ fontSize: 12, color: "#334155" }}>
          <input type="checkbox" checked={!!f.capture_now} onChange={set("capture_now")} />
          Ambil snapshot sekarang (probe + FortiGate + EBS) dan lampirkan — centang bila insiden sedang terjadi
        </label>
        <Btn variant="primary" icon={saving ? Loader2 : Save} spin={saving} disabled={saving} onClick={save}>{saving ? "Menyimpan & snapshot…" : "Simpan"}</Btn>
      </div>
    </Panel>
  );
}

function SnapshotView({ snap, thresholds }) {
  if (!snap) return <Empty>Tidak ada snapshot terlampir.</Empty>;
  const ebs = snap.ebs?.summary || {};
  return (
    <div className="space-y-3">
      <p style={{ fontSize: 11.5, color: "#64748b" }}>Diambil {fmtDate(snap.captured_at)}</p>
      <Table rows={snap.probes || []}
        columns={[{ key: "name", label: "Target" }, { key: "st", label: "Status", render: (r) => <Level size="sm" level={probeLevel(r.last, thresholds)} /> },
          { key: "avg", label: "Avg", align: "right", render: (r) => r.last?.rtt_avg != null ? `${r.last.rtt_avg} ms` : "—" },
          { key: "loss", label: "Loss", align: "right", render: (r) => r.last?.loss_pct != null ? `${r.last.loss_pct}%` : "—" },
          { key: "err", label: "Error", wrap: true, render: (r) => r.last?.error || "" }]} />
      {(snap.fortigates || []).map((fg) => (
        <p key={fg.id} style={{ fontSize: 11.5, color: "#334155" }}>
          <b>{fg.name}</b>: {fg.ok ? `CPU ${fg.summary?.cpu_pct}% · mem ${fg.summary?.mem_pct}% · sesi ${fg.summary?.sessions} · tunnel ${(fg.summary?.tunnels || []).map((t) => `${t.name} ${t.up ? "UP" : "DOWN"}`).join(", ")} · SLA ${(fg.summary?.sdwan || []).map((m) => `${m.member} ${m.state} ${m.latency_ms ?? "-"}ms/${m.loss_pct ?? "-"}%`).join(", ")}` : fg.error}
        </p>
      ))}
      {snap.ebs && (
        <div className="flex gap-2 flex-wrap">
          <Stat label="Sesi aktif" value={ebs.sessions_active} /><Stat label="Forms" value={ebs.forms_sessions} />
          <Stat label="Terblokir" value={ebs.sessions_blocked} /><Stat label="CPU DB" value={ebs.host_cpu_pct} unit="%" />
          <Stat label="Pending req" value={ebs.requests_pending} />
          <Stat label="Wait teratas" value={ebs.waits?.[0]?.event || "—"} />
        </div>
      )}
    </div>
  );
}

function IncidentDetail({ id, thresholds, onEdit, onClose, onDeleted }) {
  const [d, setD] = useState(null);
  useEffect(() => { ebsNetApi.getIncident(id).then(setD).catch((e) => alert(errText(e))); }, [id]);
  if (!d) return null;
  const del = async () => {
    if (!confirm("Hapus insiden ini?")) return;
    try { await ebsNetApi.deleteIncident(id); onDeleted(); } catch (e) { alert(errText(e)); }
  };
  const corr = d.correlation || { snapshots: [], probes: [] };
  return (
    <Panel title={`Insiden #${d.id} — ${fmtDate(d.started_at)}`} subtitle={`${d.user_name || "?"} · ${d.laptop || "?"} · ${d.ebs_module || ""} ${d.transaction || ""}`}
      action={<><Btn size="sm" icon={Pencil} onClick={() => onEdit(d)}>Edit</Btn><Btn size="sm" variant="ghost" icon={Trash2} onClick={del}>Hapus</Btn><Btn size="sm" icon={X} onClick={onClose}>Tutup</Btn></>}>
      <div className="space-y-4">
        <div style={{ fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
          <p><b>Gejala:</b> {d.symptom || "—"}</p>
          <p><b>Root cause:</b> {d.root_cause_code ? `${d.root_cause_code} ${d.root_cause_label}` : "belum"} {d.root_cause ? `— ${d.root_cause}` : ""}</p>
          <p><b>Corrective action:</b> {d.corrective_action || "—"}</p>
          {d.client_report && <p><b>Laporan laptop:</b> #{d.client_report.id} · RTT {d.client_report.ebs_rtt_avg} ms · verdict {d.client_report.verdict} · {d.client_report.codes.join(", ")}</p>}
        </div>
        <div>
          <p style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Snapshot saat dicatat</p>
          <SnapshotView snap={d.snapshot} thresholds={thresholds} />
        </div>
        <div>
          <p style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Korelasi ±{corr.window_minutes} menit dari waktu mulai (data poller otomatis)</p>
          <Table rows={corr.probes} empty="Tidak ada data probe di sekitar waktu tersebut."
            columns={[{ key: "checked_at", label: "Waktu", render: (r) => fmtDate(r.checked_at) }, { key: "name", label: "Target" },
              { key: "st", label: "Status", render: (r) => <Level size="sm" level={probeLevel(r, thresholds)} /> },
              { key: "rtt_avg", label: "Avg", align: "right" }, { key: "rtt_max", label: "Max", align: "right" },
              { key: "loss_pct", label: "Loss %", align: "right" }, { key: "error", label: "Error", wrap: true }]} />
          <div className="mt-2 space-y-1">
            {corr.snapshots.map((s) => (
              <p key={s.id} style={{ fontSize: 11.5, color: "#475569" }}>
                {fmtDate(s.checked_at)} · <b>{s.name}</b> · {s.ok ? (s.kind === "ebs"
                  ? `sesi aktif ${s.summary?.sessions_active}, blok ${s.summary?.sessions_blocked}, CPU DB ${s.summary?.host_cpu_pct}%, wait: ${s.summary?.waits?.[0]?.event || "-"}`
                  : `CPU ${s.summary?.cpu_pct}%, sesi ${s.summary?.sessions}, SLA ${(s.summary?.sdwan || []).map((m) => `${m.member} ${m.latency_ms ?? "-"}ms/${m.loss_pct ?? "-"}%`).join(", ")}`) : s.error}
              </p>
            ))}
          </div>
        </div>
        <Note>Untuk melengkapi korelasi, minta log di timestamp yang sama dari: FortiAnalyzer/log FortiGate (VPN renegotiation, SLA fail), ISP, EBS 12.2 WebLogic (<code>$EBS_DOMAIN_HOME/servers/forms_server1</code> &amp; <code>oacore_server1/logs</code>, OHS <code>access_log</code>), AWR/ASH database.</Note>
      </div>
    </Panel>
  );
}

export default function IncidentTab({ meta, thresholds }) {
  const [rows, setRows] = useState([]);
  const [reports, setReports] = useState([]);
  const [form, setForm] = useState(null);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [i, r] = await Promise.all([ebsNetApi.listIncidents(180), ebsNetApi.listReports(72)]);
      setRows(i); setReports(r);
    } catch (e) { alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const byGroup = useMemo(() => {
    const out = { NET: 0, CLI: 0, EBS: 0, DB: 0, "?": 0 };
    rows.forEach((r) => { const g = (r.root_cause_code || "").split("-")[0]; out[g in out ? g : "?"]++; });
    return out;
  }, [rows]);

  const codes = meta?.root_cause_codes || {};

  return (
    <>
      <Panel title="Rekam insiden Oracle EBS" subtitle="Tujuan akhirnya membuktikan secara objektif: client? LAN? WAN/VPN? provider? application tier? database? — bukan sekadar “lambat karena network”"
        action={!form && <Btn variant="primary" size="sm" icon={Plus} onClick={() => { setOpenId(null); setForm({ ...EMPTY, started_at: toLocalInput(new Date().toISOString()) }); }}>Catat insiden</Btn>}>
        <div className="flex gap-2.5 flex-wrap">
          <Stat label="Insiden 180 hari" value={rows.length} />
          <Stat label="Network" value={byGroup.NET} /><Stat label="Client" value={byGroup.CLI} />
          <Stat label="EBS" value={byGroup.EBS} /><Stat label="Database" value={byGroup.DB} />
          <Stat label="Belum diklasifikasi" value={byGroup["?"]} />
        </div>
      </Panel>

      {form && <IncidentForm initial={form} codes={codes} reports={reports} onCancel={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}

      {openId && !form && (
        <IncidentDetail id={openId} thresholds={thresholds} onClose={() => setOpenId(null)}
          onDeleted={() => { setOpenId(null); load(); }}
          onEdit={(d) => setForm({ ...EMPTY, ...Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v ?? ""])),
            started_at: toLocalInput(d.started_at), ended_at: toLocalInput(d.ended_at), capture_now: false })} />
      )}

      <Panel title="Daftar insiden">
        <Table rows={rows} onRowClick={(r) => { setForm(null); setOpenId(r.id); }} empty="Belum ada insiden tercatat."
          columns={[
            { key: "started_at", label: "Mulai", render: (r) => fmtDate(r.started_at) },
            { key: "status", label: "Status", render: (r) => <Level size="sm" level={r.status === "resolved" ? "ok" : "warn"} label={r.status} /> },
            { key: "user_name", label: "User" }, { key: "laptop", label: "Laptop" },
            { key: "ebs_module", label: "Modul" }, { key: "symptom", label: "Gejala", wrap: true },
            { key: "root_cause_code", label: "Root cause", render: (r) => r.root_cause_code ? `${r.root_cause_code} ${r.root_cause_label}` : "—" },
            { key: "snap", label: "Snapshot", render: (r) => r.has_snapshot ? "✓" : "" },
          ]} />
      </Panel>
    </>
  );
}
