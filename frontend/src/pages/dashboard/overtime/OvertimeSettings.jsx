/**
 * Site map D — System Setting (HRGA only).
 * D.1 Approval Matrix · D.2 Working Calendar (lives in its own HRGA module,
 * linked from here) · D.3 Overtime Rules · D.4 Cut-Off Configuration ·
 * D.5 Notification Setting, plus the grade hourly rates that drive the
 * estimated-cost figures on the Monitoring tab.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BellRing, BookOpen, CalendarDays, Coins, ExternalLink, Network, Pencil, Plus,
  RefreshCw, Save, Scissors, Search, Trash2, Users,
} from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import {
  Alert, Btn, Card, Empty, Field, Input, Modal, ROLE_LABEL, SectionTitle, Select,
  Spinner, Table, Textarea, TEXT, errMsg, fmtDateTime, fmtIDR,
} from "./ui";

const SUB_TABS = [
  { id: "matrix",        label: "Approval Matrix",      icon: Network },
  { id: "calendar",      label: "Working Calendar",     icon: CalendarDays },
  { id: "rules",         label: "Overtime Rules",       icon: BookOpen },
  { id: "cutoff",        label: "Cut-Off Configuration", icon: Scissors },
  { id: "notifications", label: "Notification Setting", icon: BellRing },
  { id: "rates",         label: "Overtime Rates",       icon: Coins },
];

/* ── D.1 Approval Matrix ────────────────────────────────────────────────── */
function ApprovalMatrix({ notify }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, o] = await Promise.all([
        overtimeApi.getMatrix({ search: search || undefined, department: dept || undefined, unassigned_only: unassignedOnly }),
        overtimeApi.getApproverOptions(),
      ]);
      setRows(m.rows || []);
      setSummary(m.summary || {});
      setOptions(o || []);
      setSelected(new Set());
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not load the approval matrix."));
    } finally {
      setLoading(false);
    }
  }, [search, dept, unassignedOnly]);

  useEffect(() => { load(); }, [load]);

  const departments = useMemo(
    () => [...new Set(options.map((o) => o.department).filter(Boolean))].sort(),
    [options],
  );

  const toggle = (id) => setSelected((p) => {
    const n = new Set(p);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const save = async (payload, msg) => {
    try {
      await overtimeApi.saveMatrix(payload);
      notify(msg);
      setEditing(null);
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  return (
    <>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <SectionTitle
        icon={Network}
        title="Approval Matrix"
        subtitle="Who approves each employee's overtime. Without both a Team Head and a Department Head, that employee cannot submit."
        right={
          <div style={{ display: "flex", gap: 7 }}>
            <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
            <Btn icon={Users} variant="primary" disabled={selected.size === 0} onClick={() => setBulkOpen(true)}>
              Assign {selected.size > 0 ? `${selected.size} selected` : "in bulk"}
            </Btn>
          </div>
        }
      />

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 13 }}>
        <Field label="Search" style={{ minWidth: 210 }}>
          <div style={{ position: "relative" }}>
            <Search size={12} style={{ position: "absolute", left: 10, top: 11, color: TEXT.muted }} />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or NIK" style={{ paddingLeft: 27 }} />
          </div>
        </Field>
        <Field label="Department" style={{ minWidth: 190 }}>
          <Select value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">All Departments</option>
            {departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </Select>
        </Field>
        <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 600, color: TEXT.body, paddingBottom: 9 }}>
          <input type="checkbox" checked={unassignedOnly} onChange={(e) => setUnassignedOnly(e.target.checked)} />
          Show only employees without a complete matrix
        </label>
        <span style={{ marginLeft: "auto", fontSize: 11.5, color: TEXT.muted, paddingBottom: 9 }}>
          {summary.configured ?? 0} configured · <strong style={{ color: "#b45309" }}>{summary.unconfigured ?? 0}</strong> not configured
        </span>
      </div>

      {loading && !rows.length ? <Spinner /> : (
        <Table
          maxHeight={520}
          columns={[
            { key: "sel", label: "", align: "center", render: (r) => (
              <input type="checkbox" checked={selected.has(r.employee_id)} onChange={() => toggle(r.employee_id)} />
            ) },
            { key: "employee_id", label: "NIK", mono: true },
            { key: "employee_name", label: "Name", render: (r) => <strong style={{ color: TEXT.strong }}>{r.employee_name}</strong> },
            { key: "department", label: "Department" },
            { key: "team", label: "Team" },
            { key: "role_level", label: "Role", render: (r) => (
              <span style={{
                padding: "2px 9px", borderRadius: 20, fontSize: 10.5, fontWeight: 700,
                background: r.role_level === "member" ? "#e2e8f0" : "#dbeafe",
                color: r.role_level === "member" ? "#475569" : "#1d4ed8",
              }}>
                {ROLE_LABEL[r.role_level] || r.role_level}
              </span>
            ) },
            { key: "team_head_name", label: "Team Head",
              render: (r) => r.team_head_name || <span style={{ color: "#b45309", fontWeight: 700 }}>not set</span> },
            { key: "dept_head_name", label: "Department Head",
              render: (r) => r.dept_head_name || <span style={{ color: "#b45309", fontWeight: 700 }}>not set</span> },
            { key: "updated_at", label: "Last updated", render: (r) => (r.updated_at ? fmtDateTime(r.updated_at) : "—") },
            { key: "actions", label: "", align: "right", render: (r) => (
              <div style={{ display: "inline-flex", gap: 5 }}>
                <button title="Edit" onClick={() => setEditing(r)} style={iconBtn}><Pencil size={13} /></button>
                {r.id && (
                  <button
                    title="Remove matrix row" style={{ ...iconBtn, background: "#fee2e2", color: "#b91c1c" }}
                    onClick={async () => {
                      if (!window.confirm(`Remove the approval matrix for ${r.employee_name}? They will not be able to submit overtime until it is set again.`)) return;
                      try { await overtimeApi.deleteMatrix(r.id); notify("Approval matrix row removed."); load(); }
                      catch (e) { setError(errMsg(e)); }
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            ) },
          ]}
          rows={rows}
          rowKey={(r) => r.employee_id}
          empty="No employees match this filter."
        />
      )}

      <MatrixEditor
        row={editing}
        options={options}
        onClose={() => setEditing(null)}
        onSave={(payload) => save(payload, `Approval matrix saved for ${editing.employee_name}.`)}
      />

      <BulkAssign
        open={bulkOpen}
        count={selected.size}
        options={options}
        onClose={() => setBulkOpen(false)}
        onSave={async (payload) => {
          try {
            const res = await overtimeApi.bulkMatrix({ ...payload, employee_ids: [...selected] });
            notify(res.message + (res.skipped?.length ? ` (${res.skipped.length} skipped)` : ""));
            setBulkOpen(false);
            load();
          } catch (e) {
            setError(errMsg(e));
          }
        }}
      />
    </>
  );
}

function ApproverSelect({ value, onChange, options, exclude, placeholder }) {
  return (
    <Select value={value || ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {options.filter((o) => o.employee_id !== exclude).map((o) => (
        <option key={o.employee_id} value={o.employee_id}>
          {o.full_name} — {o.team || o.department || "—"}
          {o.role_level !== "member" ? ` (${ROLE_LABEL[o.role_level]})` : ""}
        </option>
      ))}
    </Select>
  );
}

function MatrixEditor({ row, options, onClose, onSave }) {
  const [form, setForm] = useState({ role_level: "member", team_head_id: "", dept_head_id: "", is_active: true });

  useEffect(() => {
    if (!row) return;
    setForm({
      role_level: row.role_level || "member",
      team_head_id: row.team_head_id || "",
      dept_head_id: row.dept_head_id || "",
      is_active: row.is_active !== false,
    });
  }, [row]);

  if (!row) return null;

  return (
    <Modal
      open={!!row}
      onClose={onClose}
      width={520}
      title={`Approval Matrix — ${row.employee_name}`}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" icon={Save} onClick={() => onSave({ employee_id: row.employee_id, ...form })}>Save</Btn>
        </>
      }
    >
      <p style={{ fontSize: 12, color: TEXT.muted, marginTop: 0 }}>
        {row.employee_id} · {row.job_title || "—"} · {[row.department, row.team].filter(Boolean).join(" / ") || "—"}
      </p>

      <div style={{ display: "grid", gap: 12 }}>
        <Field label="Role in the overtime process" hint="Team Head and Department Head see an Approvals tab. HRGA Admin also gets Calculation, Monitoring and System Setting.">
          <Select value={form.role_level} onChange={(e) => setForm((p) => ({ ...p, role_level: e.target.value }))}>
            {["member", "team_head", "dept_head", "hrga_admin"].map((r) => (
              <option key={r} value={r}>{ROLE_LABEL[r]}</option>
            ))}
          </Select>
        </Field>
        <Field label="Team Head (first approver)" required>
          <ApproverSelect
            value={form.team_head_id} exclude={row.employee_id} options={options}
            placeholder="— select the Team Head —"
            onChange={(v) => setForm((p) => ({ ...p, team_head_id: v }))}
          />
        </Field>
        <Field label="Department Head (second approver)" required
          hint="Must be a different person from the Team Head — otherwise one signature would clear both levels.">
          <ApproverSelect
            value={form.dept_head_id} exclude={row.employee_id} options={options}
            placeholder="— select the Department Head —"
            onChange={(v) => setForm((p) => ({ ...p, dept_head_id: v }))}
          />
        </Field>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 600, color: TEXT.body }}>
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((p) => ({ ...p, is_active: e.target.checked }))} />
          Active — uncheck to stop this employee filing new overtime
        </label>
      </div>
    </Modal>
  );
}

function BulkAssign({ open, count, options, onClose, onSave }) {
  const [form, setForm] = useState({ role_level: "", team_head_id: "", dept_head_id: "" });

  useEffect(() => { if (open) setForm({ role_level: "", team_head_id: "", dept_head_id: "" }); }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={520}
      title={`Assign approvers to ${count} employee(s)`}
      footer={
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" icon={Save} onClick={() => onSave({
            role_level: form.role_level || undefined,
            team_head_id: form.team_head_id || undefined,
            dept_head_id: form.dept_head_id || undefined,
          })}>
            Apply
          </Btn>
        </>
      }
    >
      <p style={{ fontSize: 12, color: TEXT.body, marginTop: 0 }}>
        Fields left blank keep whatever each selected employee already has. Anyone in the selection who would end up
        as their own approver is skipped and reported back.
      </p>
      <div style={{ display: "grid", gap: 12 }}>
        <Field label="Role" hint="Leave as “keep existing” unless you are promoting the whole selection.">
          <Select value={form.role_level} onChange={(e) => setForm((p) => ({ ...p, role_level: e.target.value }))}>
            <option value="">— keep existing —</option>
            {["member", "team_head", "dept_head", "hrga_admin"].map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </Select>
        </Field>
        <Field label="Team Head">
          <ApproverSelect value={form.team_head_id} options={options} placeholder="— keep existing —"
            onChange={(v) => setForm((p) => ({ ...p, team_head_id: v }))} />
        </Field>
        <Field label="Department Head">
          <ApproverSelect value={form.dept_head_id} options={options} placeholder="— keep existing —"
            onChange={(v) => setForm((p) => ({ ...p, dept_head_id: v }))} />
        </Field>
      </div>
    </Modal>
  );
}

/* ── D.3 Overtime Rules ─────────────────────────────────────────────────── */
function Rules({ notify }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setRules(await overtimeApi.adminGetRules()); setError(""); }
    catch (e) { setError(errMsg(e, "Could not load overtime rules.")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (form) => {
    try {
      if (form.id) await overtimeApi.updateRule(form.id, form);
      else await overtimeApi.createRule(form);
      notify("Overtime rule saved.");
      setEditing(null);
      load();
    } catch (e) { setError(errMsg(e)); }
  };

  return (
    <>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      <SectionTitle
        icon={BookOpen}
        title="Overtime Rules"
        subtitle="Published read-only on every employee's overtime dashboard"
        right={
          <Btn icon={Plus} variant="primary"
            onClick={() => setEditing({ title: "", content: "", seq: rules.length + 1, is_active: true })}>
            Add New
          </Btn>
        }
      />
      {loading && !rules.length ? <Spinner /> : rules.length === 0 ? (
        <Empty icon={BookOpen} title="No rules yet" hint="Add the company overtime policy so employees can read it before filing." />
      ) : (
        <Table
          columns={[
            { key: "seq", label: "No", align: "center" },
            { key: "title", label: "Rule", render: (r) => <strong style={{ color: TEXT.strong }}>{r.title}</strong> },
            { key: "content", label: "Detail", wrap: true, maxWidth: 460,
              render: (r) => <span style={{ color: TEXT.body }}>{r.content || "—"}</span> },
            { key: "is_active", label: "Active", align: "center", render: (r) => (r.is_active ? "Yes" : "No") },
            { key: "updated_at", label: "Updated", render: (r) => fmtDateTime(r.updated_at) },
            { key: "actions", label: "", align: "right", render: (r) => (
              <div style={{ display: "inline-flex", gap: 5 }}>
                <button title="Edit" onClick={() => setEditing(r)} style={iconBtn}><Pencil size={13} /></button>
                <button
                  title="Delete" style={{ ...iconBtn, background: "#fee2e2", color: "#b91c1c" }}
                  onClick={async () => {
                    if (!window.confirm(`Delete rule "${r.title}"?`)) return;
                    try { await overtimeApi.deleteRule(r.id); notify("Rule deleted."); load(); }
                    catch (e) { setError(errMsg(e)); }
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ) },
          ]}
          rows={rules}
          rowKey={(r) => r.id}
        />
      )}

      {editing && (
        <Modal
          open onClose={() => setEditing(null)} width={560}
          title={editing.id ? "Edit Overtime Rule" : "Add Overtime Rule"}
          footer={
            <>
              <Btn onClick={() => setEditing(null)}>Cancel</Btn>
              <Btn variant="primary" icon={Save} onClick={() => save(editing)}>Save</Btn>
            </>
          }
        >
          <div style={{ display: "grid", gap: 12 }}>
            <Field label="Order" required>
              <Input type="number" min="1" value={editing.seq}
                onChange={(e) => setEditing((p) => ({ ...p, seq: Number(e.target.value) }))} />
            </Field>
            <Field label="Rule title" required>
              <Input value={editing.title} onChange={(e) => setEditing((p) => ({ ...p, title: e.target.value }))}
                placeholder="e.g. Overtime must be requested before it is worked" />
            </Field>
            <Field label="Detail">
              <Textarea rows={4} value={editing.content || ""}
                onChange={(e) => setEditing((p) => ({ ...p, content: e.target.value }))} />
            </Field>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 600, color: TEXT.body }}>
              <input type="checkbox" checked={editing.is_active}
                onChange={(e) => setEditing((p) => ({ ...p, is_active: e.target.checked }))} />
              Show this rule to employees
            </label>
          </div>
        </Modal>
      )}
    </>
  );
}

/* ── D.4 Cut-Off Configuration ──────────────────────────────────────────── */
function Cutoff({ notify }) {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ name: "Default", start_day: 11, end_day: 10 });
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await overtimeApi.getCutoff();
      setCfg(data);
      setForm({ name: data.name, start_day: data.start_day, end_day: data.end_day });
      setError("");
    } catch (e) { setError(errMsg(e, "Could not load the cut-off configuration.")); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await overtimeApi.updateCutoff({ ...form, start_day: Number(form.start_day), end_day: Number(form.end_day) });
      notify("Cut-off configuration updated.");
      setEditing(false);
      load();
    } catch (e) { setError(errMsg(e)); }
    finally { setSaving(false); }
  };

  if (!cfg) return <Spinner />;

  return (
    <>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      <SectionTitle
        icon={Scissors}
        title="Cut-Off Configuration"
        subtitle="The payroll window overtime is totalled into on the Calculation tab"
        right={editing
          ? <div style={{ display: "flex", gap: 7 }}>
              <Btn onClick={() => { setEditing(false); setForm({ name: cfg.name, start_day: cfg.start_day, end_day: cfg.end_day }); }}>Cancel</Btn>
              <Btn variant="primary" icon={Save} onClick={save} loading={saving}>Submit</Btn>
            </div>
          : <Btn icon={Pencil} onClick={() => setEditing(true)}>Edit</Btn>}
      />

      <div style={{ padding: "14px 16px", borderRadius: 12, background: "#ffffff", boxShadow: "0 2px 4px rgba(15,23,42,0.08)", marginBottom: 14 }}>
        <p style={{ fontSize: 10.5, fontWeight: 800, color: TEXT.muted, letterSpacing: "0.06em", textTransform: "uppercase", margin: 0 }}>
          Current Cut-Off Configuration
        </p>
        <p style={{ fontSize: 18, fontWeight: 800, color: TEXT.strong, margin: "6px 0 2px" }}>
          Day {cfg.start_day} → Day {cfg.end_day}
        </p>
        <p style={{ fontSize: 12, color: TEXT.body, margin: 0 }}>
          Current period: <strong>{cfg.current_period?.label}</strong>
        </p>
      </div>

      {editing && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 16 }}>
          <Field label="Configuration name">
            <Input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
          </Field>
          <Field label="Start (day of month)" required hint="The period opens on this day of the previous month.">
            <Input type="number" min="1" max="28" value={form.start_day}
              onChange={(e) => setForm((p) => ({ ...p, start_day: e.target.value }))} />
          </Field>
          <Field label="Finish (day of month)" required hint="1–28 only, so the window exists in February too.">
            <Input type="number" min="1" max="28" value={form.end_day}
              onChange={(e) => setForm((p) => ({ ...p, end_day: e.target.value }))} />
          </Field>
        </div>
      )}

      <p style={{ fontSize: 10.5, fontWeight: 800, color: TEXT.muted, letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 8px" }}>
        History
      </p>
      <Table
        columns={[
          { key: "name", label: "Name" },
          { key: "window", label: "Window", render: (r) => `Day ${r.start_day} → Day ${r.end_day}` },
          { key: "is_active", label: "Status", render: (r) => (r.is_active ? "Active" : "Superseded") },
          { key: "updated_by", label: "Changed by" },
          { key: "updated_at", label: "Changed at", render: (r) => fmtDateTime(r.updated_at) },
        ]}
        rows={cfg.history || []}
        rowKey={(r) => r.id}
      />
      <p style={{ fontSize: 11, color: TEXT.muted, marginTop: 9 }}>
        Changing the window creates a new record rather than editing the old one, so a calculation re-run for a closed
        period can still be traced back to the window that was in force at the time.
      </p>
    </>
  );
}

/* ── D.5 Notification Setting ───────────────────────────────────────────── */
function NotificationSettings({ notify }) {
  const [rows, setRows] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setRows(await overtimeApi.getNotificationSettings()); setError(""); }
    catch (e) { setError(errMsg(e, "Could not load notification settings.")); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const set = (key, field) => (e) =>
    setRows((p) => p.map((r) => (r.event_key === key ? { ...r, [field]: e.target.checked } : r)));

  const save = async () => {
    setSaving(true);
    try {
      await overtimeApi.updateNotificationSettings(
        rows.map(({ event_key, in_app, email, is_active }) => ({ event_key, in_app, email, is_active })),
      );
      notify("Notification settings saved.");
      load();
    } catch (e) { setError(errMsg(e)); }
    finally { setSaving(false); }
  };

  return (
    <>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      <SectionTitle
        icon={BellRing}
        title="Notification Setting"
        subtitle="Which overtime events raise a notification, and through which channel"
        right={<Btn variant="primary" icon={Save} onClick={save} loading={saving}>Save</Btn>}
      />
      <Alert kind="info">
        In-app notifications are live and appear on the Notification tab. Email delivery is stored here but no mail
        sender is wired up yet — the switch takes effect the moment one is.
      </Alert>
      <Table
        columns={[
          { key: "label", label: "Event", render: (r) => <strong style={{ color: TEXT.strong }}>{r.label || r.event_key}</strong> },
          { key: "is_active", label: "Enabled", align: "center",
            render: (r) => <input type="checkbox" checked={r.is_active} onChange={set(r.event_key, "is_active")} /> },
          { key: "in_app", label: "In-app", align: "center",
            render: (r) => <input type="checkbox" checked={r.in_app} onChange={set(r.event_key, "in_app")} /> },
          { key: "email", label: "Email", align: "center",
            render: (r) => <input type="checkbox" checked={r.email} onChange={set(r.event_key, "email")} /> },
          { key: "updated_at", label: "Updated", render: (r) => fmtDateTime(r.updated_at) },
        ]}
        rows={rows}
        rowKey={(r) => r.event_key}
      />
    </>
  );
}

/* ── Overtime rates (cost estimation) ───────────────────────────────────── */
function Rates({ notify }) {
  const [data, setData] = useState({ rates: [], employee_grades: [] });
  const [form, setForm] = useState({ grade: "", hourly_rate: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setData(await overtimeApi.getRates()); setError(""); }
    catch (e) { setError(errMsg(e, "Could not load overtime rates.")); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await overtimeApi.saveRate({ grade: form.grade.trim(), hourly_rate: Number(form.hourly_rate) || 0 });
      notify(`Rate for grade "${form.grade}" saved.`);
      setForm({ grade: "", hourly_rate: "" });
      load();
    } catch (e) { setError(errMsg(e)); }
    finally { setSaving(false); }
  };

  const missing = data.employee_grades.filter(
    (g) => !data.rates.some((r) => r.grade.toLowerCase() === g.toLowerCase()),
  );

  return (
    <>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}
      <SectionTitle
        icon={Coins}
        title="Overtime Rates"
        subtitle="Base hourly wage per employee grade — used only to estimate cost on the Monitoring tab"
      />
      <Alert kind="info">
        This system holds no salary data. Enter a representative hourly figure per grade; overtime cost is then
        <strong> statutory index × this rate</strong> (Kepmenaker 102/2004: weekday 1.5× the first hour then 2×;
        weekend/public holiday 2× up to 8 hours, 3× the 9th, 4× the 10th–11th). A grade with no rate simply shows a
        cost of zero. Add a grade named <strong>DEFAULT</strong> as the fallback for everyone else.
      </Alert>

      <div style={{ display: "flex", gap: 11, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 14 }}>
        <Field label="Grade" style={{ minWidth: 180 }}>
          <Input list="ot-grades" value={form.grade} onChange={(e) => setForm((p) => ({ ...p, grade: e.target.value }))}
            placeholder="e.g. G3 or DEFAULT" />
          <datalist id="ot-grades">
            {[...data.employee_grades, "DEFAULT"].map((g) => <option key={g} value={g} />)}
          </datalist>
        </Field>
        <Field label="Hourly rate (IDR)" style={{ minWidth: 180 }}>
          <Input type="number" min="0" step="1000" value={form.hourly_rate}
            onChange={(e) => setForm((p) => ({ ...p, hourly_rate: e.target.value }))} placeholder="e.g. 35000" />
        </Field>
        <Btn variant="primary" icon={Save} onClick={save} loading={saving} disabled={!form.grade.trim()} style={{ marginBottom: 1 }}>
          Save rate
        </Btn>
      </div>

      {missing.length > 0 && (
        <Alert kind="warning">
          No rate configured for grade(s): <strong>{missing.join(", ")}</strong>. Overtime for those employees will
          report a cost of zero until a rate (or a DEFAULT) is set.
        </Alert>
      )}

      <Table
        columns={[
          { key: "grade", label: "Grade", render: (r) => <strong style={{ color: TEXT.strong }}>{r.grade}</strong> },
          { key: "hourly_rate", label: "Hourly rate", align: "right", render: (r) => fmtIDR(r.hourly_rate) },
          { key: "updated_by", label: "Updated by" },
          { key: "updated_at", label: "Updated at", render: (r) => fmtDateTime(r.updated_at) },
          { key: "actions", label: "", align: "right", render: (r) => (
            <button
              title="Delete" style={{ ...iconBtn, background: "#fee2e2", color: "#b91c1c" }}
              onClick={async () => {
                if (!window.confirm(`Delete the rate for grade "${r.grade}"?`)) return;
                try { await overtimeApi.deleteRate(r.id); notify("Rate deleted."); load(); }
                catch (e) { setError(errMsg(e)); }
              }}
            >
              <Trash2 size={13} />
            </button>
          ) },
        ]}
        rows={data.rates}
        rowKey={(r) => r.id}
        empty="No rates configured — overtime cost will show as zero everywhere."
      />
    </>
  );
}

/* ── D.2 Working Calendar — pointer to the existing HRGA module ─────────── */
function WorkingCalendarLink() {
  const navigate = useNavigate();
  return (
    <>
      <SectionTitle
        icon={CalendarDays}
        title="Working Calendar"
        subtitle="Shared with the rest of HRGA — this module reads it, it is not maintained separately here"
      />
      <p style={{ fontSize: 12.5, color: TEXT.body, lineHeight: 1.6, marginTop: 0 }}>
        The overtime module decides whether a given date is <strong>weekday</strong> or <strong>weekend / public
        holiday</strong> from the HRGA Working Calendar, which also drives attendance. That means a national holiday
        added there is immediately paid at the higher statutory multiplier here — there is no second calendar to keep
        in sync.
      </p>
      <Btn icon={ExternalLink} variant="primary" onClick={() => navigate("/dashboard/hr/workingcalendar")}>
        Open Working Calendar
      </Btn>
    </>
  );
}

export default function OvertimeSettings() {
  const [sub, setSub] = useState("matrix");
  const [notice, setNotice] = useState("");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {notice && <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>}

      <Card>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
          {SUB_TABS.map((t) => {
            const on = sub === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setSub(t.id)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 13px",
                  borderRadius: 20, border: "none", cursor: "pointer", fontSize: 11.5, fontWeight: 700,
                  background: on ? "#2563eb" : "#ffffff", color: on ? "#fff" : TEXT.body,
                  boxShadow: on ? "0 3px 8px rgba(37,99,235,0.30)" : "0 1px 2px rgba(15,23,42,0.08)",
                }}
              >
                <t.icon size={12} />
                {t.label}
              </button>
            );
          })}
        </div>

        {sub === "matrix"        && <ApprovalMatrix notify={setNotice} />}
        {sub === "calendar"      && <WorkingCalendarLink />}
        {sub === "rules"         && <Rules notify={setNotice} />}
        {sub === "cutoff"        && <Cutoff notify={setNotice} />}
        {sub === "notifications" && <NotificationSettings notify={setNotice} />}
        {sub === "rates"         && <Rates notify={setNotice} />}
      </Card>
    </div>
  );
}

const iconBtn = {
  width: 26, height: 26, borderRadius: 8, border: "none", background: "#f1f5f9",
  color: "#64748b", cursor: "pointer", display: "inline-flex", alignItems: "center",
  justifyContent: "center", boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
};
