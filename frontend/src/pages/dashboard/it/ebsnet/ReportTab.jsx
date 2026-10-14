/**
 * Laporan — the diagnosis report. "Proses Ulang Semua" re-takes every
 * measurement (probes, both FortiGates, EBS/DB health), grades each data
 * point, names the segment where access gets stuck, and saves the result;
 * the poller does the same on the interval chosen here. Each saved report
 * downloads as a self-contained HTML file (print / email) or JSON.
 */
import { useCallback, useEffect, useState } from "react";
import { Play, Loader2, Download, Trash2, Clock, ChevronRight, FileText } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Btn, Empty, Field, Level, Note, Panel, Spinner, Table, fmtDate, errText, inputStyle } from "./ui";

// Report statuses → the module's level vocabulary (ok/warn/crit/unknown).
const LV = { good: "ok", warn: "warn", bad: "crit", unknown: "unknown" };
const LABEL = { good: "Good", warn: "Warning", bad: "Bad", unknown: "No data" };
const PATH = ["laptop", "ho_lan", "wan", "plant_lan", "ebs_web", "ebs_db"];
const PRIORITY = {
  high:    { bg: "rgba(208,59,59,0.09)", color: "#b42318" },
  medium:  { bg: "rgba(250,178,25,0.14)", color: "#854d0e" },
  data:    { bg: "rgba(100,116,139,0.1)", color: "#475569" },
  routine: { bg: "rgba(12,163,12,0.08)", color: "#0a7d0a" },
};
// Reports saved before the English switch carry the old priority values.
const PRIORITY_ALIAS = { tinggi: "high", sedang: "medium", rutin: "routine" };
const INTERVALS = [[0, "Off"], [1, "Every 1 hour"], [2, "Every 2 hours"], [3, "Every 3 hours"], [6, "Every 6 hours"], [12, "Every 12 hours"], [24, "Every 24 hours"]];

const fmtVal = (v, unit) => (v == null ? "—" : `${v}${unit ? ` ${unit}` : ""}`);

async function saveFile(id, fmt, createdAt) {
  try {
    const blob = await ebsNetApi.downloadSummaryReport(id, fmt);
    const d = new Date(createdAt);
    const p = (n) => String(n).padStart(2, "0");
    const name = `EBS_Diagnosis_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.${fmt}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (e) { alert(errText(e, "Download failed")); }
}

function PathChain({ sections, bottleneck }) {
  const by = Object.fromEntries(sections.map((s) => [s.key, s]));
  return (
    <div className="flex items-stretch gap-1.5 flex-wrap">
      {PATH.map((k, i) => {
        const s = by[k];
        const hit = k === bottleneck;
        return (
          <div key={k} className="flex items-center gap-1.5" style={{ flex: "1 1 140px" }}>
            <div className="rounded-xl p-2.5 w-full" style={{
              border: hit ? "2px solid #d03b3b" : "1px solid rgba(0,0,0,0.07)",
              background: hit ? "rgba(208,59,59,0.06)" : "#f8fafc",
            }}>
              <p style={{ fontSize: 11.5, fontWeight: 800, color: "#0f172a", marginBottom: 4 }}>{s.label}</p>
              <Level size="sm" level={LV[s.status]} label={LABEL[s.status]} />
              {hit && <p style={{ fontSize: 10.5, fontWeight: 800, color: "#d03b3b", marginTop: 4 }}>◀ BOTTLENECK</p>}
              <p style={{ fontSize: 10, color: "#94a3b8", marginTop: 3 }}>
                {s.counts.bad ? `${s.counts.bad} bad · ` : ""}{s.counts.warn ? `${s.counts.warn} warning · ` : ""}{s.counts.good} good
              </p>
            </div>
            {i < PATH.length - 1 && <ChevronRight size={14} className="hidden xl:block" style={{ color: "#cbd5e1", flexShrink: 0 }} />}
          </div>
        );
      })}
    </div>
  );
}

function ReportView({ row }) {
  const c = row.content;
  const internet = c.sections.find((s) => s.key === "internet");
  return (
    <>
      <Panel title={`Report #${row.id} — ${fmtDate(row.created_at)}`}
        subtitle={`${c.trigger === "auto" ? "Automatic (scheduled)" : `Manual by ${c.created_by || "-"}`} · EBS environment ${c.context.ebs_environment || "-"} · ${c.context.client_reports} laptop tests (${c.context.client_window_hours} h) · incidents in 7 days ${c.context.incidents_7d} · processed in ${c.duration_s} s`}
        action={<>
          <Btn size="sm" icon={Download} onClick={() => saveFile(row.id, "html", row.created_at)}>Download HTML</Btn>
          <Btn size="sm" icon={FileText} onClick={() => saveFile(row.id, "json", row.created_at)}>JSON</Btn>
        </>}>
        <div className="rounded-xl px-4 py-3 mb-4" style={{
          background: { good: "rgba(12,163,12,0.07)", warn: "rgba(250,178,25,0.12)", bad: "rgba(208,59,59,0.08)", unknown: "#f1f5f9" }[c.overall],
        }}>
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span style={{ fontSize: 12.5, fontWeight: 700 }}>Overall status</span>
            <Level level={LV[c.overall]} label={LABEL[c.overall]} />
            {c.bottleneck && <><span style={{ fontSize: 12.5, fontWeight: 700, marginLeft: 8 }}>Bottleneck:</span>
              <Level level="crit" label={c.bottleneck_label} /></>}
          </div>
          <p style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", lineHeight: 1.5 }}>{c.headline}</p>
        </div>
        <PathChain sections={c.sections} bottleneck={c.bottleneck} />
        <div className="mt-2 flex items-center gap-2" style={{ fontSize: 11.5, color: "#475569" }}>
          Internet / Plant ISP (comparison): <Level size="sm" level={LV[internet.status]} label={LABEL[internet.status]} />
        </div>
      </Panel>

      <Panel title="Conclusion">
        <ul style={{ paddingLeft: 18, listStyle: "disc", fontSize: 12.5, color: "#1e293b", lineHeight: 1.7 }}>
          {c.conclusion.map((x, i) => <li key={i}>{x}</li>)}
        </ul>
        <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 8 }}>
          Bottleneck = the first segment along the laptop → database path that has a problem; a hold-up early on makes every segment after it look slow too.
          Confirm with repeated reports before changing any configuration.
        </p>
      </Panel>

      <Panel title="Actions" subtitle="By priority: the bottleneck segment first, then in path order">
        {!c.actions.length ? <Empty>No actions.</Empty> : (
          <div className="space-y-2">
            {c.actions.map((a, i) => {
              const pk = PRIORITY_ALIAS[a.priority] || a.priority;
              const p = PRIORITY[pk] || PRIORITY.data;
              return (
                <div key={i} className="flex gap-3 items-start rounded-lg p-2.5" style={{ border: "1px solid rgba(0,0,0,0.05)" }}>
                  <span className="rounded-md" style={{ background: p.bg, color: p.color, fontSize: 10.5, fontWeight: 800, padding: "2px 8px", textTransform: "uppercase", flexShrink: 0, minWidth: 62, textAlign: "center" }}>{pk}</span>
                  <div>
                    <p style={{ fontSize: 12.5, color: "#0f172a" }}>{a.text}</p>
                    <p style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2 }}>{a.section}{a.item ? ` · ${a.item}` : ""}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {c.sections.map((s) => (
        <Panel key={s.key} title={<span className="flex items-center gap-2">{s.label} <Level size="sm" level={LV[s.status]} label={LABEL[s.status]} /></span>}>
          <Table rows={s.items} empty="No data for this segment."
            columns={[
              { key: "name", label: "Item", wrap: true },
              { key: "value", label: "Value", wrap: true, render: (r) => <b style={{ fontWeight: 700 }}>{fmtVal(r.value, r.unit)}</b> },
              { key: "standard", label: "Standard", wrap: true },
              { key: "status", label: "Status", render: (r) => <Level size="sm" level={LV[r.status]} label={LABEL[r.status]} /> },
              { key: "note", label: "Notes", wrap: true },
            ]} />
        </Panel>
      ))}
    </>
  );
}

export default function ReportTab({ settings, onSettingsSaved }) {
  const [list, setList] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [current, setCurrent] = useState(null);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const open = useCallback(async (id) => {
    try { setCurrent(await ebsNetApi.getSummaryReport(id)); } catch (e) { alert(errText(e)); }
  }, []);

  const load = useCallback(async (openLatest = false) => {
    try {
      const r = await ebsNetApi.listSummaryReports(30);
      setList(r.reports); setSchedule(r.schedule);
      if (openLatest && r.reports[0]) open(r.reports[0].id);
    } catch (e) { setList([]); alert(errText(e)); }
  }, [open]);
  useEffect(() => { load(true); }, [load]);

  useEffect(() => {
    if (!running) return undefined;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [running]);

  const run = async () => {
    setRunning(true); setElapsed(0);
    try {
      const r = await ebsNetApi.runSummaryReport();
      setCurrent(r);
      await load(false);
    } catch (e) { alert(errText(e, "Processing failed")); } finally { setRunning(false); }
  };

  const setInterval_ = async (hours) => {
    try { await ebsNetApi.putSettings({ report_interval_hours: Number(hours) }); await onSettingsSaved(); await load(false); }
    catch (e) { alert(errText(e, "Failed to save the schedule")); }
  };

  const del = async (id) => {
    if (!confirm("Delete this report?")) return;
    try {
      await ebsNetApi.deleteSummaryReport(id);
      if (current?.id === id) setCurrent(null);
      load(false);
    } catch (e) { alert(errText(e)); }
  };

  if (!list) return <Spinner />;
  const interval = Number(settings?.report_interval_hours ?? schedule?.interval_hours ?? 0);

  return (
    <>
      <Panel title="Diagnosis report — where does EBS access get stuck?"
        subtitle="Re-runs everything: path probes, HO & Plant FortiGates, EBS/DB health and the latest laptop tests — then grades, concludes and saves a report file">
        <div className="flex items-end gap-4 flex-wrap">
          <Btn variant="primary" icon={running ? Loader2 : Play} spin={running} disabled={running} onClick={run}>
            {running ? `Processing everything… ${elapsed} s` : "Re-run Everything"}
          </Btn>
          <div style={{ width: 200 }}>
            <Field label="Automatic run">
              <select style={inputStyle} value={interval} onChange={(e) => setInterval_(e.target.value)}>
                {INTERVALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
          </div>
          {interval > 0 && (
            <p className="flex items-center gap-1.5" style={{ fontSize: 11.5, color: "#64748b" }}>
              <Clock size={12} />
              Last automatic run: {schedule?.last_auto_at ? fmtDate(schedule.last_auto_at) : "never"} ·
              next: {["soon", "segera"].includes(schedule?.next_auto_at) ? "within ≤ 5 minutes" : fmtDate(schedule?.next_auto_at)}
            </p>
          )}
        </div>
        {running && (
          <div className="mt-3"><Note>Re-measuring every segment (including SSH to the FortiGates and the EBS server) — usually 20–60 seconds.</Note></div>
        )}
      </Panel>

      {current?.content ? <ReportView row={current} /> : (
        <Panel><Empty>No reports yet. Click "Re-run Everything" to create the first one.</Empty></Panel>
      )}

      <Panel title="Report archive (30 days)" subtitle="Kept for 180 days · click a row to open it">
        <Table rows={list} onRowClick={(r) => open(r.id)} empty="No saved reports yet."
          columns={[
            { key: "created_at", label: "Time", render: (r) => <span style={{ fontWeight: r.id === current?.id ? 800 : 500 }}>{fmtDate(r.created_at)}</span> },
            { key: "trigger", label: "Type", render: (r) => (r.trigger === "auto" ? "Automatic" : `Manual · ${r.created_by || ""}`) },
            { key: "overall", label: "Status", render: (r) => <Level size="sm" level={LV[r.overall] || "unknown"} label={LABEL[r.overall] || "—"} /> },
            { key: "bottleneck_label", label: "Bottleneck", render: (r) => r.bottleneck_label || "—" },
            { key: "headline", label: "Summary", wrap: true },
            { key: "act", label: "", render: (r) => (
              <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                <Btn size="sm" variant="ghost" icon={Download} onClick={() => saveFile(r.id, "html", r.created_at)}>HTML</Btn>
                <Btn size="sm" variant="ghost" icon={Trash2} onClick={() => del(r.id)} />
              </div>
            ) },
          ]} />
      </Panel>
    </>
  );
}
