/**
 * Site map B — Overtime Order / Plan.
 * B.1 My Overtime Order (filtered by status) + B.2 Create Overtime Order.
 * B.3/B.4 (the two head reviews) live in the Approvals tab.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList, Eye, Pencil, Plus, RefreshCw, Send, Trash2, XCircle } from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, CATEGORY_BADGE, Empty, Field, Input, Modal, PLAN_STATUS, Pill,
  RZ_STATUS, SectionTitle, Select, Spinner, Table, Textarea, TEXT, TYPE_BADGE,
  errMsg, fmtDate, fmtHours,
} from "./ui";

const FILTERS = [
  { id: "all",         label: "All" },
  { id: "draft",       label: "Draft" },
  { id: "submitted",   label: "Submitted" },
  { id: "revision",    label: "Revision Required" },
  { id: "approved",    label: "Approved" },
  { id: "rejected",    label: "Rejected" },
  { id: "cancelled",   label: "Cancelled" },
];

const EMPTY_FORM = {
  ot_date: "",
  work_category: "adhoc",
  task_description: "",
  work_start: "08:30",
  work_finish: "17:30",
  plan_start: "17:30",
  plan_finish: "20:00",
};

/** Same rule as overtime_service.duration_minutes — a finish at or before
 *  the start crosses midnight. Mirrored client-side purely so the form can
 *  show the duration live; the server always recomputes it. */
function durationHours(start, finish) {
  const toMin = (t) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(t || "");
    if (!m) return null;
    const h = +m[1], mi = +m[2];
    if (h > 23 || mi > 59) return null;
    return h * 60 + mi;
  };
  const s = toMin(start), f = toMin(finish);
  if (s === null || f === null || s === f) return 0;
  return ((f < s ? f + 1440 : f) - s) / 60;
}

function OrderForm({ open, initial, onClose, onSaved, matrixConfigured }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setForm(initial ? {
      ot_date: initial.ot_date || "",
      work_category: initial.work_category || "adhoc",
      task_description: initial.task_description || "",
      work_start: initial.work_start || "08:30",
      work_finish: initial.work_finish || "17:30",
      plan_start: initial.plan_start || "17:30",
      plan_finish: initial.plan_finish || "20:00",
    } : { ...EMPTY_FORM, ot_date: new Date().toISOString().slice(0, 10) });
  }, [open, initial]);

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }));
  const planned = durationHours(form.plan_start, form.plan_finish);

  // Derived locally for the badge only — the server re-derives it from the
  // working calendar (which also knows about public holidays this can't see).
  const looksWeekend = useMemo(() => {
    if (!form.ot_date) return false;
    const d = new Date(`${form.ot_date}T00:00:00`).getDay();
    return d === 0 || d === 6;
  }, [form.ot_date]);

  const save = async (submit) => {
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, submit };
      if (initial?.id) await overtimeApi.updateOrder(initial.id, payload);
      else await overtimeApi.createOrder(payload);
      onSaved(submit ? "Overtime order submitted to your Team Head." : "Draft saved.");
      onClose();
    } catch (e) {
      setError(errMsg(e, "Could not save this overtime order."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={640}
      title={initial?.id ? `Edit Overtime Order — ${initial.request_no}` : "Create Overtime Order"}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => save(false)} loading={saving}>Save as Draft</Btn>
          <Btn
            variant="primary" icon={Send} onClick={() => save(true)} loading={saving}
            disabled={!matrixConfigured}
            title={matrixConfigured ? "" : "No approval matrix configured — ask HRGA to set your Team Head and Department Head."}
          >
            Submit to Team Head
          </Btn>
        </>
      }
    >
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      {!matrixConfigured && (
        <Alert kind="warning">
          You can save a draft, but submitting needs an approval matrix. Ask HRGA to set your Team Head and
          Department Head first.
        </Alert>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Overtime Date" required>
          <Input type="date" value={form.ot_date} onChange={set("ot_date")} />
        </Field>
        <Field label="Overtime Type" hint="Set automatically from the working calendar, including public holidays.">
          <div style={{ paddingTop: 6 }}>
            <Pill map={TYPE_BADGE} value={looksWeekend ? "weekend" : "weekday"} />
          </div>
        </Field>

        <Field label="Work Category" required>
          <Select value={form.work_category} onChange={set("work_category")}>
            <option value="adhoc">Ad Hoc Task</option>
            <option value="routine">Routine Task</option>
          </Select>
        </Field>
        <Field label="Planned Duration">
          <div style={{
            padding: "8px 11px", borderRadius: 10, background: "#eff6ff", color: "#1d4ed8",
            fontSize: 13, fontWeight: 800, fontFamily: "ui-monospace, monospace",
          }}>
            {planned.toFixed(2)} h
          </div>
        </Field>

        <Field label="Working Time — Start">
          <Input type="time" value={form.work_start} onChange={set("work_start")} />
        </Field>
        <Field label="Working Time — Finish">
          <Input type="time" value={form.work_finish} onChange={set("work_finish")} />
        </Field>

        <Field label="Overtime — Start" required>
          <Input type="time" value={form.plan_start} onChange={set("plan_start")} />
        </Field>
        <Field label="Overtime — Finish" required hint="A finish earlier than the start is read as passing midnight.">
          <Input type="time" value={form.plan_finish} onChange={set("plan_finish")} />
        </Field>

        <Field label="Task / Target Result" required style={{ gridColumn: "1 / -1" }}>
          <Textarea
            rows={3} value={form.task_description} onChange={set("task_description")}
            placeholder="What will be done, and what result is expected from this overtime?"
          />
        </Field>
      </div>
    </Modal>
  );
}

export default function OvertimeOrders({ me, refreshBadges }) {
  const [data, setData] = useState({ orders: [], status_counts: {} });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await overtimeApi.listOrders(filter === "all" ? {} : { status: filter }));
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not load your overtime orders."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const afterChange = (msg) => {
    setNotice(msg);
    load();
    refreshBadges?.();
  };

  const act = async (fn, msg) => {
    try {
      await fn();
      afterChange(msg);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusyId(null);
    }
  };

  const counts = data.status_counts || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      {notice && <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>}

      <Card>
        <SectionTitle
          icon={ClipboardList}
          title="My Overtime Order"
          subtitle="Every overtime order you have filed, and where it currently sits"
          right={
            <div style={{ display: "flex", gap: 7 }}>
              <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
              <Btn icon={Plus} variant="primary" onClick={() => { setEditing(null); setFormOpen(true); }}>
                Create Overtime Order
              </Btn>
            </div>
          }
        />

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          {FILTERS.map((f) => {
            const on = filter === f.id;
            const n = f.id === "all"
              ? Object.values(counts).reduce((a, b) => a + b, 0)
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

        {loading && !data.orders.length ? <Spinner /> : data.orders.length === 0 ? (
          <Empty
            icon={ClipboardList}
            title="No overtime orders here"
            hint={filter === "all" ? "Create your first overtime order to get started." : `No order with status "${filter}".`}
            action={<Btn icon={Plus} variant="primary" onClick={() => { setEditing(null); setFormOpen(true); }}>Create Overtime Order</Btn>}
          />
        ) : (
          <Table
            columns={[
              { key: "request_no", label: "Request No", mono: true },
              { key: "ot_date", label: "Date", render: (r) => fmtDate(r.ot_date) },
              { key: "overtime_type", label: "Type", render: (r) => <Pill map={TYPE_BADGE} value={r.overtime_type} /> },
              { key: "work_category", label: "Category", render: (r) => <Pill map={CATEGORY_BADGE} value={r.work_category} /> },
              { key: "task_description", label: "Task / Target Result", wrap: true, maxWidth: 280,
                render: (r) => <span title={r.task_description}>{r.task_description}</span> },
              { key: "time", label: "Plan", mono: true, render: (r) => `${r.plan_start} – ${r.plan_finish}` },
              { key: "planned_hours", label: "Duration", align: "right", render: (r) => fmtHours(r.planned_hours) },
              { key: "plan_status", label: "Status", render: (r) => <Pill map={PLAN_STATUS} value={r.plan_status} /> },
              { key: "rz_status", label: "Realization",
                render: (r) => (r.plan_status === "approved" ? <Pill map={RZ_STATUS} value={r.rz_status} /> : "—") },
              { key: "actions", label: "", align: "right", render: (r) => (
                <div style={{ display: "inline-flex", gap: 5 }}>
                  <IconBtn title="View detail" icon={Eye} onClick={() => setDetailId(r.id)} />
                  {["draft", "revision"].includes(r.plan_status) && (
                    <>
                      <IconBtn title="Edit" icon={Pencil} onClick={() => { setEditing(r); setFormOpen(true); }} />
                      <IconBtn
                        title="Submit to Team Head" icon={Send} color="#2563eb" busy={busyId === r.id}
                        onClick={() => { setBusyId(r.id); act(() => overtimeApi.submitOrder(r.id), "Submitted to your Team Head."); }}
                      />
                    </>
                  )}
                  {r.plan_status === "draft" && (
                    <IconBtn
                      title="Delete draft" icon={Trash2} color="#dc2626"
                      onClick={() => {
                        if (window.confirm(`Delete draft ${r.request_no}? This cannot be undone.`)) {
                          act(() => overtimeApi.deleteOrder(r.id), "Draft deleted.");
                        }
                      }}
                    />
                  )}
                  {["submitted", "th_approved", "approved"].includes(r.plan_status) && r.rz_status === "pending" && (
                    <IconBtn title="Cancel order" icon={XCircle} color="#ea580c"
                      onClick={() => { setCancelling(r); setCancelReason(""); }} />
                  )}
                </div>
              ) },
            ]}
            rows={data.orders}
            rowKey={(r) => r.id}
          />
        )}
      </Card>

      <OrderForm
        open={formOpen}
        initial={editing}
        matrixConfigured={!!me?.matrix_configured}
        onClose={() => { setFormOpen(false); setEditing(null); }}
        onSaved={afterChange}
      />

      <RequestDetail
        requestId={detailId}
        open={!!detailId}
        onClose={() => setDetailId(null)}
        footer={<Btn onClick={() => setDetailId(null)}>Close</Btn>}
      />

      <Modal
        open={!!cancelling}
        title={`Cancel ${cancelling?.request_no || ""}`}
        onClose={() => setCancelling(null)}
        width={460}
        footer={
          <>
            <Btn onClick={() => setCancelling(null)}>Keep it</Btn>
            <Btn
              variant="danger" icon={XCircle}
              onClick={() => {
                const target = cancelling;
                setCancelling(null);
                act(() => overtimeApi.cancelOrder(target.id, { reason: cancelReason }), "Overtime order cancelled.");
              }}
            >
              Cancel order
            </Btn>
          </>
        }
      >
        <p style={{ fontSize: 12.5, color: TEXT.body, marginTop: 0 }}>
          The order stays on record as cancelled — it is not deleted, and your approvers keep seeing it in their history.
        </p>
        <Field label="Reason" hint="Optional, but it saves your approver a phone call.">
          <Textarea rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
            placeholder="e.g. Task completed within normal working hours" />
        </Field>
      </Modal>
    </div>
  );
}

function IconBtn({ icon: Icon, title, onClick, color = "#64748b", busy }) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={busy}
      style={{
        width: 26, height: 26, borderRadius: 8, border: "none", background: "#f1f5f9",
        color, cursor: busy ? "wait" : "pointer", display: "inline-flex",
        alignItems: "center", justifyContent: "center", boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
      }}
    >
      <Icon size={13} />
    </button>
  );
}
