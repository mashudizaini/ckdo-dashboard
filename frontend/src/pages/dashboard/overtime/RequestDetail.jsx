/**
 * Read-only detail view of one overtime request — plan, realization,
 * evidence and the full approval timeline.
 *
 * Shared by My Order, My Realization and the Approvals inbox so all three
 * show a request the same way; only the action buttons in the footer differ,
 * and those are passed in by the caller.
 */
import { useCallback, useEffect, useState } from "react";
import { Download, FileText, Paperclip } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

import { overtimeApi } from "@/api/overtime";
import {
  Alert, CATEGORY_BADGE, Modal, PLAN_STATUS, Pill, RZ_STATUS, Spinner, TEXT, TYPE_BADGE,
  errMsg, fmtDate, fmtDateTime, fmtGap, fmtHours, gapColor,
} from "./ui";

const ACTION_LABEL = {
  create: "Created", update: "Updated", submit: "Submitted",
  approve: "Approved", reject: "Rejected", revision: "Sent back for revision",
  cancel: "Cancelled", adjust: "Adjusted",
};

const ACTION_COLOR = {
  approve: "#16a34a", reject: "#dc2626", revision: "#ea580c",
  submit: "#2563eb", cancel: "#64748b",
};

function Row({ label, children, mono }) {
  return (
    <div style={{ display: "flex", gap: 10, padding: "5px 0", fontSize: 12 }}>
      <span style={{ minWidth: 128, color: TEXT.muted, fontWeight: 600, flexShrink: 0 }}>{label}</span>
      <span style={{ color: TEXT.strong, fontWeight: 600, fontFamily: mono ? "ui-monospace, monospace" : undefined }}>
        {children ?? "—"}
      </span>
    </div>
  );
}

function Block({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <p style={{
        fontSize: 10, fontWeight: 800, color: TEXT.muted, letterSpacing: "0.06em",
        textTransform: "uppercase", margin: "0 0 6px", paddingBottom: 4, borderBottom: "1px solid #e2e8f0",
      }}>
        {title}
      </p>
      {children}
    </div>
  );
}

/** Evidence downloads are bearer-authenticated, so a plain <a href> would
 *  400 — fetch as a blob and hand the browser an object URL instead. */
function AttachmentLink({ attachment }) {
  const { token } = useAuthStore();
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    let url;
    try {
      const res = await fetch(overtimeApi.attachmentUrl(attachment.id), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("download failed");
      url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = attachment.original_name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (_) {
      // Nothing actionable for the user beyond retrying — the file either
      // downloads or it doesn't.
    } finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      setBusy(false);
    }
  };

  return (
    <button
      onClick={download}
      disabled={busy}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8,
        border: "none", background: "#eff6ff", color: "#1d4ed8", fontSize: 11.5, fontWeight: 700,
        cursor: busy ? "wait" : "pointer", maxWidth: "100%",
      }}
    >
      <Paperclip size={11} style={{ flexShrink: 0 }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {attachment.original_name}
      </span>
      <Download size={11} style={{ flexShrink: 0 }} />
    </button>
  );
}

export default function RequestDetail({ requestId, open, onClose, footer, title }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!requestId) return;
    setLoading(true);
    setError("");
    try {
      setData(await overtimeApi.getRequest(requestId));
    } catch (e) {
      setError(errMsg(e, "Could not load this overtime request."));
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={720}
      title={title || (data ? `${data.request_no} — ${data.employee_name}` : "Overtime request")}
      footer={footer}
    >
      {loading && <Spinner />}
      {error && <Alert kind="error">{error}</Alert>}

      {data && !loading && (
        <>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 14 }}>
            <Pill map={TYPE_BADGE} value={data.overtime_type} />
            <Pill map={CATEGORY_BADGE} value={data.work_category} />
            <Pill map={PLAN_STATUS} value={data.plan_status} />
            {data.plan_status === "approved" && <Pill map={RZ_STATUS} value={data.rz_status} />}
          </div>

          <Block title="Overtime order">
            <Row label="Employee">{data.employee_name} ({data.employee_id})</Row>
            <Row label="Department / Team">{[data.department, data.team].filter(Boolean).join(" · ") || "—"}</Row>
            <Row label="Date">{fmtDate(data.ot_date)}</Row>
            <Row label="Working time" mono>{data.work_start || "—"} – {data.work_finish || "—"}</Row>
            <Row label="Planned overtime" mono>
              {data.plan_start || "—"} – {data.plan_finish || "—"} ({fmtHours(data.planned_hours)})
            </Row>
            <Row label="Task / target result">
              <span style={{ fontWeight: 500, whiteSpace: "pre-wrap" }}>{data.task_description}</span>
            </Row>
          </Block>

          <Block title="Plan approval">
            <Row label="Team Head">
              {data.th_approver_name || "—"}
              {data.th_decision && (
                <span style={{ marginLeft: 8, color: ACTION_COLOR[data.th_decision] || TEXT.muted, fontSize: 11 }}>
                  {ACTION_LABEL[data.th_decision] || data.th_decision} · {fmtDateTime(data.th_decision_at)}
                </span>
              )}
            </Row>
            {data.th_note && <Row label="Team Head note"><span style={{ fontWeight: 500 }}>{data.th_note}</span></Row>}
            <Row label="Department Head">
              {data.dh_approver_name || "—"}
              {data.dh_decision && (
                <span style={{ marginLeft: 8, color: ACTION_COLOR[data.dh_decision] || TEXT.muted, fontSize: 11 }}>
                  {ACTION_LABEL[data.dh_decision] || data.dh_decision} · {fmtDateTime(data.dh_decision_at)}
                </span>
              )}
            </Row>
            {data.dh_note && <Row label="Dept Head note"><span style={{ fontWeight: 500 }}>{data.dh_note}</span></Row>}
          </Block>

          {data.rz_status !== "pending" && (
            <Block title="Realization">
              <Row label="Actual time" mono>
                {data.actual_start || "—"} – {data.actual_finish || "—"} ({fmtHours(data.actual_hours)})
              </Row>
              <Row label="Gap vs plan">
                <span style={{ color: gapColor(data.gap_hours), fontFamily: "ui-monospace, monospace" }}>
                  {fmtGap(data.gap_hours)}
                </span>
              </Row>
              {data.gap_reason && <Row label="Reason"><span style={{ fontWeight: 500, whiteSpace: "pre-wrap" }}>{data.gap_reason}</span></Row>}
              {data.rz_status === "approved" && (
                <>
                  <Row label="Payable">{fmtHours(data.payable_hours)}</Row>
                  <Row label="Overtime index">{Number(data.overtime_index || 0).toFixed(2)} × hourly wage</Row>
                </>
              )}
            </Block>
          )}

          {data.hour_details?.length > 0 && (
            <Block title="Weekend / public holiday — hour by hour">
              {data.hour_details.map((h) => (
                <div key={h.hour_no} style={{ display: "flex", gap: 10, padding: "5px 0", fontSize: 12, borderBottom: "1px dashed #e2e8f0" }}>
                  <span style={{ minWidth: 58, color: TEXT.muted, fontWeight: 700 }}>Hour {h.hour_no}</span>
                  <span style={{ minWidth: 96, fontFamily: "ui-monospace, monospace", color: TEXT.body }}>
                    {h.start_time || "—"} – {h.finish_time || "—"}
                  </span>
                  <span style={{ color: TEXT.strong, fontWeight: 500, flex: 1 }}>{h.detail || "—"}</span>
                </div>
              ))}
            </Block>
          )}

          {data.attachments?.length > 0 && (
            <Block title="Work evidence / supporting document">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                {data.attachments.map((a) => <AttachmentLink key={a.id} attachment={a} />)}
              </div>
            </Block>
          )}

          {data.rz_status !== "pending" && (
            <Block title="Realization approval">
              <Row label="Team Head">
                {data.rz_th_approver_name || "—"}
                {data.rz_th_decision && (
                  <span style={{ marginLeft: 8, color: ACTION_COLOR[data.rz_th_decision] || TEXT.muted, fontSize: 11 }}>
                    {ACTION_LABEL[data.rz_th_decision] || data.rz_th_decision} · {fmtDateTime(data.rz_th_decision_at)}
                  </span>
                )}
              </Row>
              {data.rz_th_note && <Row label="Note"><span style={{ fontWeight: 500 }}>{data.rz_th_note}</span></Row>}
              <Row label="Department Head">
                {data.rz_dh_approver_name || "—"}
                {data.rz_dh_decision && (
                  <span style={{ marginLeft: 8, color: ACTION_COLOR[data.rz_dh_decision] || TEXT.muted, fontSize: 11 }}>
                    {ACTION_LABEL[data.rz_dh_decision] || data.rz_dh_decision} · {fmtDateTime(data.rz_dh_decision_at)}
                  </span>
                )}
              </Row>
              {data.rz_dh_note && <Row label="Note"><span style={{ fontWeight: 500 }}>{data.rz_dh_note}</span></Row>}
              <Row label="HRGA final check">
                {data.hr_approver_name || "—"}
                {data.hr_decision && (
                  <span style={{ marginLeft: 8, color: ACTION_COLOR[data.hr_decision] || TEXT.muted, fontSize: 11 }}>
                    {ACTION_LABEL[data.hr_decision] || data.hr_decision} · {fmtDateTime(data.hr_decision_at)}
                  </span>
                )}
              </Row>
              {data.hr_note && <Row label="HRGA note"><span style={{ fontWeight: 500 }}>{data.hr_note}</span></Row>}
            </Block>
          )}

          {data.timeline?.length > 0 && (
            <Block title="Audit trail">
              {data.timeline.map((t, i) => (
                <div key={i} style={{ display: "flex", gap: 9, padding: "5px 0", fontSize: 11.5, alignItems: "flex-start" }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: "50%", marginTop: 5, flexShrink: 0,
                    background: ACTION_COLOR[t.action] || "#94a3b8",
                  }} />
                  <span style={{ minWidth: 132, color: TEXT.muted }}>{fmtDateTime(t.created_at)}</span>
                  <span style={{ color: TEXT.strong, fontWeight: 700, minWidth: 148 }}>
                    {ACTION_LABEL[t.action] || t.action}
                    <span style={{ color: TEXT.muted, fontWeight: 500 }}> ({t.stage})</span>
                  </span>
                  <span style={{ color: TEXT.body, flex: 1 }}>
                    {t.actor_name}
                    {t.note && <span style={{ color: TEXT.muted }}> — {t.note}</span>}
                  </span>
                </div>
              ))}
            </Block>
          )}

          {!data.timeline?.length && !data.attachments?.length && data.rz_status === "pending" && (
            <p style={{ fontSize: 11.5, color: TEXT.muted, display: "flex", alignItems: "center", gap: 6 }}>
              <FileText size={12} /> No realization filed yet.
            </p>
          )}
        </>
      )}
    </Modal>
  );
}
