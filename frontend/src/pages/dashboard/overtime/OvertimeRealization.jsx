/**
 * Site map C.1–C.5 — Overtime Realization.
 * My Realization (with the "To Be Realized" queue), Daily Realization form,
 * weekend/public-holiday hour-by-hour detail, work evidence upload, and
 * submission to the Team Head. C.6–C.8 (the reviews) are in Approvals;
 * C.9/C.10 (calculation and monitoring) are HRGA-only tabs.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CalendarClock, Eye, Paperclip, Pencil, Plus, RefreshCw, Send, Trash2, Upload,
} from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, Empty, Field, Input, Modal, RZ_STATUS, Pill, SectionTitle,
  Spinner, Table, Textarea, TEXT, TYPE_BADGE, errMsg, fmtDate, fmtGap, fmtHours, gapColor,
} from "./ui";

const FILTERS = [
  { id: "to_be_realized", label: "To Be Realized" },
  { id: "all",            label: "All" },
  { id: "draft",          label: "Draft" },
  { id: "submitted",      label: "Submitted" },
  { id: "revision",       label: "Revision Required" },
  { id: "approved",       label: "Approved" },
  { id: "rejected",       label: "Rejected" },
];

function durationHours(start, finish) {
  const toMin = (t) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(t || "");
    if (!m) return null;
    const h = +m[1], mi = +m[2];
    return h > 23 || mi > 59 ? null : h * 60 + mi;
  };
  const s = toMin(start), f = toMin(finish);
  if (s === null || f === null || s === f) return 0;
  return ((f < s ? f + 1440 : f) - s) / 60;
}

/* ── C.2/C.3/C.4/C.5 — the realization form ─────────────────────────────── */
function RealizationForm({ open, request, onClose, onSaved }) {
  const [form, setForm] = useState({ actual_start: "", actual_finish: "", gap_reason: "" });
  const [hours, setHours] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const isWeekend = request?.overtime_type === "weekend";

  useEffect(() => {
    if (!open || !request) return;
    setError("");
    setForm({
      actual_start: request.actual_start || request.plan_start || "",
      actual_finish: request.actual_finish || request.plan_finish || "",
      gap_reason: request.gap_reason || "",
    });
    setAttachments(request.attachments || []);
    setHours(request.hour_details?.length
      ? request.hour_details.map((h) => ({ ...h }))
      : (isWeekend ? [{ hour_no: 1, detail: "", start_time: "", finish_time: "" }] : []));
  }, [open, request, isWeekend]);

  if (!request) return null;

  const actual = durationHours(form.actual_start, form.actual_finish);
  const gap = actual - Number(request.planned_hours || 0);
  const gapNeedsReason = Math.abs(gap) >= 0.25;

  const setHour = (i, key) => (e) =>
    setHours((p) => p.map((h, idx) => (idx === i ? { ...h, [key]: e.target.value } : h)));

  const addHour = () =>
    setHours((p) => [...p, { hour_no: p.length + 1, detail: "", start_time: "", finish_time: "" }]);

  const removeHour = (i) =>
    setHours((p) => p.filter((_, idx) => idx !== i).map((h, idx) => ({ ...h, hour_no: idx + 1 })));

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const saved = await overtimeApi.uploadAttachment(request.id, file);
      setAttachments((p) => [...p, saved]);
    } catch (err) {
      setError(errMsg(err, "Could not upload that file."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeAttachment = async (id) => {
    try {
      await overtimeApi.deleteAttachment(id);
      setAttachments((p) => p.filter((a) => a.id !== id));
    } catch (err) {
      setError(errMsg(err, "Could not remove that attachment."));
    }
  };

  const save = async (submit) => {
    setSaving(true);
    setError("");
    try {
      await overtimeApi.saveRealization(request.id, {
        actual_start: form.actual_start,
        actual_finish: form.actual_finish,
        gap_reason: form.gap_reason,
        hour_details: isWeekend ? hours : [],
        submit,
      });
      onSaved(submit ? "Realization submitted to your Team Head." : "Realization saved as draft.");
      onClose();
    } catch (err) {
      setError(errMsg(err, "Could not save this realization."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={700}
      title={`Daily Realization — ${request.request_no} · ${fmtDate(request.ot_date)}`}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => save(false)} loading={saving}>Save as Draft</Btn>
          <Btn variant="primary" icon={Send} onClick={() => save(true)} loading={saving}>Submit to Team Head</Btn>
        </>
      }
    >
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <div style={{
        display: "flex", gap: 14, flexWrap: "wrap", padding: "10px 13px", borderRadius: 11,
        background: "#eff6ff", marginBottom: 15, fontSize: 11.5,
      }}>
        <span><strong style={{ color: "#1d4ed8" }}>Plan:</strong> {request.plan_start} – {request.plan_finish} ({fmtHours(request.planned_hours)})</span>
        <span><strong style={{ color: "#1d4ed8" }}>Type:</strong> <Pill map={TYPE_BADGE} value={request.overtime_type} /></span>
        <span style={{ flexBasis: "100%", color: TEXT.body }}><strong style={{ color: "#1d4ed8" }}>Task:</strong> {request.task_description}</span>
      </div>

      {/* C.2 Daily Realization */}
      <p style={sectionLabel}>Realization Time (Actual)</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 11, marginBottom: 14 }}>
        <Field label="Start" required>
          <Input type="time" value={form.actual_start} onChange={(e) => setForm((p) => ({ ...p, actual_start: e.target.value }))} />
        </Field>
        <Field label="Finish" required>
          <Input type="time" value={form.actual_finish} onChange={(e) => setForm((p) => ({ ...p, actual_finish: e.target.value }))} />
        </Field>
        <Field label="Actual Duration">
          <div style={readonlyBox}>{actual.toFixed(2)} h</div>
        </Field>
        <Field label="Gap vs Plan">
          <div style={{ ...readonlyBox, color: gapColor(gap), background: "#f8fafc" }}>{fmtGap(gap)}</div>
        </Field>
      </div>

      <Field
        label="Reason / Explanation"
        required={gapNeedsReason}
        hint={gapNeedsReason
          ? "Required — the actual time differs from the plan by 15 minutes or more."
          : "Optional when the realization matches the plan."}
        style={{ marginBottom: 16 }}
      >
        <Textarea
          rows={2} value={form.gap_reason}
          onChange={(e) => setForm((p) => ({ ...p, gap_reason: e.target.value }))}
          placeholder="Why did the actual overtime differ from what was planned?"
        />
      </Field>

      {/* C.3 Weekend / Public Holiday detail */}
      {isWeekend && (
        <>
          <p style={sectionLabel}>Weekend / Public Holiday — Hour by Hour</p>
          <p style={{ fontSize: 11, color: TEXT.muted, margin: "0 0 9px" }}>
            Weekend and public-holiday overtime is paid at a higher statutory rate, so each hour needs its own
            task and result before HRGA will approve it.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 10 }}>
            {hours.map((h, i) => (
              <div key={i} style={{
                display: "grid", gridTemplateColumns: "52px 1fr 96px 96px 28px", gap: 7, alignItems: "center",
              }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: TEXT.muted }}>Hour {h.hour_no}</span>
                <Input placeholder="Detail task / result" value={h.detail || ""} onChange={setHour(i, "detail")} />
                <Input type="time" value={h.start_time || ""} onChange={setHour(i, "start_time")} />
                <Input type="time" value={h.finish_time || ""} onChange={setHour(i, "finish_time")} />
                <button
                  onClick={() => removeHour(i)}
                  title="Remove this hour"
                  style={{
                    width: 26, height: 26, borderRadius: 8, border: "none", background: "#fee2e2",
                    color: "#b91c1c", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <Btn icon={Plus} onClick={addHour}>Add hour</Btn>
            <span style={{ fontSize: 11.5, color: TEXT.muted }}>
              Final hour count: <strong style={{ color: TEXT.strong }}>{hours.length}</strong> ·
              {" "}auto-calculated duration <strong style={{ color: TEXT.strong }}>{actual.toFixed(2)} h</strong>
            </span>
          </div>
        </>
      )}

      {/* C.4 Work Evidence */}
      <p style={sectionLabel}>Work Evidence / Supporting Document</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginBottom: 9 }}>
        {attachments.length === 0 && (
          <span style={{ fontSize: 11.5, color: TEXT.muted }}>No file attached yet — at least one is required to submit.</span>
        )}
        {attachments.map((a) => (
          <span key={a.id} style={{
            display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8,
            background: "#eff6ff", color: "#1d4ed8", fontSize: 11.5, fontWeight: 700, maxWidth: 260,
          }}>
            <Paperclip size={11} style={{ flexShrink: 0 }} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.original_name}</span>
            <button onClick={() => removeAttachment(a.id)} title="Remove"
              style={{ background: "none", border: "none", cursor: "pointer", color: "#b91c1c", display: "flex", padding: 0 }}>
              <Trash2 size={11} />
            </button>
          </span>
        ))}
      </div>
      <input
        ref={fileRef} type="file" onChange={upload} style={{ display: "none" }}
        accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt"
      />
      <Btn icon={Upload} onClick={() => fileRef.current?.click()} loading={uploading}>Attach file</Btn>
      <p style={{ fontSize: 10.5, color: TEXT.muted, margin: "7px 0 0" }}>
        PDF, image, Office or text file, up to 15 MB each. Uploads are saved immediately, even before you save the form.
      </p>
    </Modal>
  );
}

const sectionLabel = {
  fontSize: 10, fontWeight: 800, color: TEXT.muted, letterSpacing: "0.06em",
  textTransform: "uppercase", margin: "0 0 8px", paddingBottom: 4, borderBottom: "1px solid #e2e8f0",
};

const readonlyBox = {
  padding: "8px 11px", borderRadius: 10, background: "#eff6ff", color: "#1d4ed8",
  fontSize: 13, fontWeight: 800, fontFamily: "ui-monospace, monospace",
};

export default function OvertimeRealization({ refreshBadges }) {
  const [data, setData] = useState({ realizations: [], status_counts: {} });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("to_be_realized");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // "To Be Realized" and "All" are both the unfiltered fetch — the
      // former is a client-side view of the flag the server sets per row,
      // which also covers drafts and returned revisions.
      const params = ["all", "to_be_realized"].includes(filter) ? {} : { status: filter };
      setData(await overtimeApi.listRealizations(params));
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not load your realizations."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const rows = filter === "to_be_realized"
    ? data.realizations.filter((r) => r.to_be_realized)
    : data.realizations;

  const afterChange = (msg) => {
    setNotice(msg);
    load();
    refreshBadges?.();
  };

  const counts = data.status_counts || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      {notice && <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>}

      <Card>
        <SectionTitle
          icon={CalendarClock}
          title="My Realization"
          subtitle="Report what actually happened against each approved overtime order"
          right={<Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>}
        />

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          {FILTERS.map((f) => {
            const on = filter === f.id;
            const n = f.id === "all"
              ? data.realizations.length
              : f.id === "to_be_realized"
                ? (counts.to_be_realized || 0)
                : (counts[f.id] || 0);
            return (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 12px",
                  borderRadius: 20, border: "none", cursor: "pointer", fontSize: 11.5, fontWeight: 700,
                  background: on ? "#2563eb" : "#ffffff", color: on ? "#fff" : TEXT.body,
                  boxShadow: on ? "0 3px 8px rgba(37,99,235,0.30)" : "0 1px 2px rgba(15,23,42,0.08)",
                }}
              >
                {f.label}
                <span style={{
                  fontSize: 10, fontWeight: 800, padding: "1px 6px", borderRadius: 9,
                  background: on ? "rgba(255,255,255,0.25)" : "#f1f5f9", color: on ? "#fff" : TEXT.muted,
                }}>
                  {n}
                </span>
              </button>
            );
          })}
        </div>

        {loading && !data.realizations.length ? <Spinner /> : rows.length === 0 ? (
          <Empty
            icon={CalendarClock}
            title={filter === "to_be_realized" ? "Nothing waiting to be realized" : "No realization here"}
            hint={filter === "to_be_realized"
              ? "Approved overtime orders appear here on the day they were planned for."
              : `No realization with status "${filter}".`}
          />
        ) : (
          <Table
            columns={[
              { key: "request_no", label: "Request No", mono: true },
              { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
              { key: "overtime_type", label: "Type", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
              { key: "task_description", label: "Task / Target Result", wrap: true, maxWidth: 260,
                render: (r) => <span title={r.task_description}>{r.task_description}</span> },
              { key: "plan", label: "Plan", mono: true, render: (r) => `${r.plan_start} – ${r.plan_finish}` },
              { key: "planned_hours", label: "Planned", align: "right", render: (r) => fmtHours(r.planned_hours) },
              { key: "actual", label: "Actual", mono: true,
                render: (r) => (r.actual_start ? `${r.actual_start} – ${r.actual_finish}` : "—") },
              { key: "actual_hours", label: "Realized", align: "right",
                render: (r) => (r.actual_start ? fmtHours(r.actual_hours) : "—") },
              { key: "gap_hours", label: "Gap", align: "right",
                render: (r) => (r.actual_start
                  ? <span style={{ color: gapColor(r.gap_hours), fontFamily: "ui-monospace, monospace" }}>{fmtGap(r.gap_hours)}</span>
                  : "—") },
              { key: "rz_status", label: "Status", render: (r) => <Pill map={RZ_STATUS} value={r.rz_status} /> },
              { key: "actions", label: "", align: "right", render: (r) => (
                <div style={{ display: "inline-flex", gap: 5 }}>
                  <button title="View detail" onClick={() => setDetailId(r.id)} style={iconBtn}>
                    <Eye size={13} />
                  </button>
                  {["pending", "draft", "revision"].includes(r.rz_status) && (
                    <button
                      title="Fill in realization"
                      onClick={() => setEditing(r)}
                      style={{ ...iconBtn, background: "#dbeafe", color: "#1d4ed8" }}
                    >
                      <Pencil size={13} />
                    </button>
                  )}
                </div>
              ) },
            ]}
            rows={rows}
            rowKey={(r) => r.id}
          />
        )}
      </Card>

      <RealizationForm
        open={!!editing}
        request={editing}
        onClose={() => setEditing(null)}
        onSaved={afterChange}
      />

      <RequestDetail
        requestId={detailId}
        open={!!detailId}
        onClose={() => setDetailId(null)}
        footer={<Btn onClick={() => setDetailId(null)}>Close</Btn>}
      />
    </div>
  );
}

const iconBtn = {
  width: 26, height: 26, borderRadius: 8, border: "none", background: "#f1f5f9",
  color: "#64748b", cursor: "pointer", display: "inline-flex", alignItems: "center",
  justifyContent: "center", boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
};
