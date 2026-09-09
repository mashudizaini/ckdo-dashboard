/**
 * Site map B.3/B.4 and C.6/C.7/C.8 — the approval desk.
 *
 * One inbox for every level the signed-in user holds: Team Head review,
 * Department Head review, and HRGA's final check. Which level a given
 * request is at is decided server-side and returned as `awaiting_level`,
 * so this screen never has to guess.
 */
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CheckSquare, Eye, History, RefreshCw, RotateCcw, XCircle } from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, CATEGORY_BADGE, Empty, Field, Input, Modal, PLAN_STATUS, Pill,
  RZ_STATUS, SectionTitle, Spinner, Table, Textarea, TEXT, TYPE_BADGE,
  errMsg, fmtDate, fmtGap, fmtHours, gapColor,
} from "./ui";

const LEVEL_LABEL = { team_head: "Team Head review", dept_head: "Dept Head review", hrga: "HRGA final check" };
const STAGE_LABEL = { plan: "Order", realization: "Realization" };

const STAGE_BADGE = {
  plan:        { label: "Order",       bg: "#dbeafe", color: "#1d4ed8" },
  realization: { label: "Realization", bg: "#f3e8ff", color: "#7e22ce" },
};

/** Approve / reject / send back, with the extra payable-hours control the
 *  HRGA final check needs (and nobody else gets). */
function DecisionModal({ open, request, decision, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [payableHours, setPayableHours] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const isHrgaFinal = request?.awaiting_level === "hrga";
  const isApprove = decision === "approve";

  useEffect(() => {
    if (!open) return;
    setNote("");
    setError("");
    setPayableHours(request ? Number(request.actual_hours || 0).toFixed(2) : "");
  }, [open, request]);

  if (!request) return null;

  const submit = async () => {
    if (!isApprove && !note.trim()) {
      setError("A note is required when rejecting or asking for a revision.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const body = { decision, note: note.trim() || null };
      if (isHrgaFinal && isApprove) {
        const hours = Number(payableHours);
        if (!Number.isFinite(hours) || hours < 0) {
          setError("Payable hours must be a number of zero or more.");
          setSaving(false);
          return;
        }
        body.payable_minutes = Math.round(hours * 60);
      }
      await overtimeApi.decide(request.id, body);
      onDone(
        isApprove
          ? `${STAGE_LABEL[request.awaiting_stage]} ${request.request_no} approved.`
          : decision === "revision"
            ? `${STAGE_LABEL[request.awaiting_stage]} ${request.request_no} sent back for revision.`
            : `${STAGE_LABEL[request.awaiting_stage]} ${request.request_no} rejected.`
      );
      onClose();
    } catch (e) {
      setError(errMsg(e, "Could not record that decision."));
    } finally {
      setSaving(false);
    }
  };

  const title = {
    approve: "Approve", reject: "Reject", revision: "Request revision",
  }[decision];

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={520}
      title={`${title} — ${request.request_no}`}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn
            variant={isApprove ? "success" : decision === "revision" ? "warning" : "danger"}
            icon={isApprove ? CheckCircle2 : decision === "revision" ? RotateCcw : XCircle}
            onClick={submit}
            loading={saving}
          >
            {title}
          </Btn>
        </>
      }
    >
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <div style={{ padding: "10px 13px", borderRadius: 11, background: "#f8fafc", marginBottom: 14, fontSize: 12 }}>
        <p style={{ margin: 0, fontWeight: 700, color: TEXT.strong }}>
          {request.employee_name} <span style={{ color: TEXT.muted, fontWeight: 500 }}>({request.employee_id})</span>
        </p>
        <p style={{ margin: "4px 0 0", color: TEXT.body }}>
          {fmtDate(request.ot_date)} · {request.plan_start}–{request.plan_finish} · planned {fmtHours(request.planned_hours)}
          {request.awaiting_stage === "realization" && request.actual_start && (
            <> · actual {request.actual_start}–{request.actual_finish} ({fmtHours(request.actual_hours)}),
              gap <span style={{ color: gapColor(request.gap_hours), fontWeight: 700 }}>{fmtGap(request.gap_hours)}</span></>
          )}
        </p>
        <p style={{ margin: "6px 0 0", color: TEXT.body, whiteSpace: "pre-wrap" }}>{request.task_description}</p>
        {request.gap_reason && (
          <p style={{ margin: "6px 0 0", color: TEXT.muted, fontStyle: "italic" }}>Reason: {request.gap_reason}</p>
        )}
      </div>

      {isHrgaFinal && isApprove && (
        <Field
          label="Payable hours"
          required
          hint="Defaults to the hours actually worked. Reduce it if part of the overtime is not payable — it cannot exceed the actual hours, and this figure is what the Calculation tab reports to payroll."
          style={{ marginBottom: 14 }}
        >
          <Input
            type="number" step="0.25" min="0" max={request.actual_hours}
            value={payableHours} onChange={(e) => setPayableHours(e.target.value)}
          />
        </Field>
      )}

      <Field
        label="Note"
        required={!isApprove}
        hint={isApprove ? "Optional." : "The employee sees this, so say what needs to change."}
      >
        <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder={isApprove ? "Anything the employee should know" : "Why is this being sent back?"} />
      </Field>
    </Modal>
  );
}

export default function OvertimeApprovals({ refreshBadges }) {
  const [inbox, setInbox] = useState({ approvals: [], counts: {} });
  const [history, setHistory] = useState([]);
  const [view, setView] = useState("inbox");
  const [stageFilter, setStageFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [detailId, setDetailId] = useState(null);
  const [decision, setDecision] = useState({ open: false, request: null, decision: "approve" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [box, hist] = await Promise.all([
        overtimeApi.getApprovals(),
        overtimeApi.getApprovalHistory(),
      ]);
      setInbox(box);
      setHistory(hist.history || []);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not load your approval inbox."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const afterDecision = (msg) => {
    setNotice(msg);
    load();
    refreshBadges?.();
  };

  const rows = stageFilter === "all"
    ? inbox.approvals
    : inbox.approvals.filter((r) => r.awaiting_stage === stageFilter);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      {notice && <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>}

      <Card>
        <SectionTitle
          icon={CheckSquare}
          title="Approvals"
          subtitle="Overtime orders and realizations waiting for your decision"
          right={
            <div style={{ display: "flex", gap: 7 }}>
              <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
              <Btn
                icon={view === "inbox" ? History : CheckSquare}
                onClick={() => setView(view === "inbox" ? "history" : "inbox")}
              >
                {view === "inbox" ? "My decision history" : "Back to inbox"}
              </Btn>
            </div>
          }
        />

        {view === "inbox" && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {[
              { id: "all", label: "All", n: inbox.counts?.total || 0 },
              { id: "plan", label: "Overtime Order", n: inbox.counts?.plan || 0 },
              { id: "realization", label: "Realization", n: inbox.counts?.realization || 0 },
            ].map((f) => {
              const on = stageFilter === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setStageFilter(f.id)}
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
                    {f.n}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {loading && !inbox.approvals.length ? <Spinner /> : view === "inbox" ? (
          rows.length === 0 ? (
            <Empty icon={CheckCircle2} title="Nothing waiting for you" hint="New submissions land here as soon as they are filed." />
          ) : (
            <Table
              columns={[
                { key: "awaiting_stage", label: "Stage", render: (r) => <Pill map={STAGE_BADGE} value={r.awaiting_stage} /> },
                { key: "awaiting_level", label: "Your level", render: (r) => (
                  <span style={{ fontSize: 11, fontWeight: 700, color: TEXT.muted }}>{LEVEL_LABEL[r.awaiting_level] || r.awaiting_level}</span>
                ) },
                { key: "request_no", label: "Request No", mono: true },
                { key: "employee_name", label: "Employee",
                  render: (r) => (
                    <span>
                      <strong style={{ color: TEXT.strong }}>{r.employee_name}</strong>
                      <span style={{ color: TEXT.muted, fontSize: 11 }}> · {r.team || r.department || "—"}</span>
                    </span>
                  ) },
                { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
                { key: "overtime_type", label: "Type", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
                { key: "work_category", label: "Work", render: (r) => <Pill map={CATEGORY_BADGE} value={r.work_category} /> },
                { key: "task_description", label: "Task / Target Result", wrap: true, maxWidth: 240,
                  render: (r) => <span title={r.task_description}>{r.task_description}</span> },
                { key: "planned_hours", label: "Planned", align: "right", render: (r) => fmtHours(r.planned_hours) },
                { key: "actual_hours", label: "Actual", align: "right",
                  render: (r) => (r.awaiting_stage === "realization" && r.actual_start ? fmtHours(r.actual_hours) : "—") },
                { key: "gap_hours", label: "Gap", align: "right",
                  render: (r) => (r.awaiting_stage === "realization" && r.actual_start
                    ? <span style={{ color: gapColor(r.gap_hours), fontFamily: "ui-monospace, monospace" }}>{fmtGap(r.gap_hours)}</span>
                    : "—") },
                { key: "evidence", label: "Evidence", align: "center",
                  render: (r) => (r.attachments?.length ? `${r.attachments.length} file(s)` : "—") },
                { key: "actions", label: "", align: "right", render: (r) => (
                  <div style={{ display: "inline-flex", gap: 5 }}>
                    <button title="View detail" onClick={() => setDetailId(r.id)} style={iconBtn}>
                      <Eye size={13} />
                    </button>
                    <button
                      title="Approve" style={{ ...iconBtn, background: "#dcfce7", color: "#15803d" }}
                      onClick={() => setDecision({ open: true, request: r, decision: "approve" })}
                    >
                      <CheckCircle2 size={13} />
                    </button>
                    <button
                      title="Request revision" style={{ ...iconBtn, background: "#ffedd5", color: "#c2410c" }}
                      onClick={() => setDecision({ open: true, request: r, decision: "revision" })}
                    >
                      <RotateCcw size={13} />
                    </button>
                    <button
                      title="Reject" style={{ ...iconBtn, background: "#fee2e2", color: "#b91c1c" }}
                      onClick={() => setDecision({ open: true, request: r, decision: "reject" })}
                    >
                      <XCircle size={13} />
                    </button>
                  </div>
                ) },
              ]}
              rows={rows}
              rowKey={(r) => `${r.id}-${r.awaiting_stage}`}
            />
          )
        ) : (
          history.length === 0 ? (
            <Empty icon={History} title="No decisions yet" hint="Requests you approve or reject show up here." />
          ) : (
            <Table
              columns={[
                { key: "request_no", label: "Request No", mono: true },
                { key: "employee_name", label: "Employee" },
                { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
                { key: "overtime_type", label: "Type", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
                { key: "planned_hours", label: "Planned", align: "right", render: (r) => fmtHours(r.planned_hours) },
                { key: "actual_hours", label: "Actual", align: "right",
                  render: (r) => (r.actual_start ? fmtHours(r.actual_hours) : "—") },
                { key: "plan_status", label: "Order", render: (r) => <Pill map={PLAN_STATUS} value={r.plan_status} /> },
                { key: "rz_status", label: "Realization", render: (r) => <Pill map={RZ_STATUS} value={r.rz_status} /> },
                { key: "actions", label: "", align: "right", render: (r) => (
                  <button title="View detail" onClick={() => setDetailId(r.id)} style={iconBtn}>
                    <Eye size={13} />
                  </button>
                ) },
              ]}
              rows={history}
              rowKey={(r) => r.id}
            />
          )
        )}
      </Card>

      <DecisionModal
        open={decision.open}
        request={decision.request}
        decision={decision.decision}
        onClose={() => setDecision({ open: false, request: null, decision: "approve" })}
        onDone={afterDecision}
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
