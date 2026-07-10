import { useState, useEffect, useCallback } from "react";
import {
  Plus, X, Trash2, Pencil, Check, AlertTriangle, Calendar as CalendarIcon,
  List, RefreshCw, Loader2,
} from "lucide-react";
import { hrApi } from "@/api/dashboard";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn: "inset 4px 4px 10px #c5cad8, inset -4px -4px 10px #ffffff",
  shadowBtn: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff",
};

const STATUS_CFG = {
  "Not Started": { bg: "#e2e8f0", color: "#475569" },
  "In Progress": { bg: "#dbeafe", color: "#1d4ed8" },
  "Completed":   { bg: "#dcfce7", color: "#16a34a" },
};

const ROLE_OPTIONS = ["Manager", "Supervisor", "Officer"];
const CATEGORY_OPTIONS = ["Event", "Project", "Vendor Invoice", "Admin", "Other"];
const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG["Not Started"];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "3px 10px", borderRadius: 20,
      fontSize: 11, fontWeight: 700, background: cfg.bg, color: cfg.color,
    }}>
      {status}
    </span>
  );
}

// ── Multi-select "Assigned To", sourced from the Employee master list ──────
function AssignedToSelect({ value, onChange, employees }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const selected = (value || "").split(",").map(s => s.trim()).filter(Boolean);

  const addName = (name) => {
    if (!selected.includes(name)) onChange([...selected, name].join(", "));
    setQuery(""); setOpen(false);
  };
  const removeName = (name) => onChange(selected.filter(n => n !== name).join(", "));

  const q = query.trim().toLowerCase();
  const matches = employees
    .filter(e => !selected.includes(e.full_name))
    .filter(e => !q || e.full_name.toLowerCase().includes(q))
    .slice(0, 30);

  return (
    <div style={{ position: "relative" }}>
      <div
        onClick={() => setOpen(true)}
        style={{
          width: "100%", minHeight: 34, padding: "5px 8px", borderRadius: 10, boxSizing: "border-box",
          background: NEU.bg, boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff",
          display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center", cursor: "text",
        }}>
        {selected.map(name => (
          <span key={name} style={{
            display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20,
            background: "#dbeafe", color: "#1d4ed8", fontSize: 11, fontWeight: 700,
          }}>
            {name}
            <button type="button" onClick={(e) => { e.stopPropagation(); removeName(name); }}
              style={{ background: "none", border: "none", cursor: "pointer", color: "#1d4ed8", padding: 0, display: "flex" }}>
              <X size={10} />
            </button>
          </span>
        ))}
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={selected.length ? "" : "Search employee name..."}
          style={{ flex: 1, minWidth: 100, border: "none", background: "transparent", outline: "none", fontSize: 12, color: "#1e293b" }}
        />
      </div>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 21,
            maxHeight: 220, overflowY: "auto", borderRadius: 10, background: "#fff",
            boxShadow: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
          }}>
            {matches.length === 0 ? (
              <p style={{ fontSize: 11.5, color: "#94a3b8", padding: "10px 12px" }}>No matching employees.</p>
            ) : matches.map(e => (
              <button key={e.user_id} type="button" onClick={() => addName(e.full_name)}
                style={{
                  display: "block", width: "100%", textAlign: "left", padding: "7px 12px", border: "none",
                  background: "none", cursor: "pointer", fontSize: 12,
                }}
                onMouseEnter={ev => ev.currentTarget.style.background = "#f0f3f9"}
                onMouseLeave={ev => ev.currentTarget.style.background = "none"}
              >
                <span style={{ fontWeight: 600, color: "#1e293b" }}>{e.full_name}</span>
                {e.department && <span style={{ color: "#94a3b8", marginLeft: 6, fontSize: 10.5 }}>{e.department}</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function TaskForm({ initial, onSave, onCancel, saving, employees }) {
  const [form, setForm] = useState(() => initial
    ? { ...initial, alert_days_before: initial.alert_days_before ?? "" }
    : { title: "", description: "", category: "Event", is_vendor: false,
        assigned_to: "", role: "Officer", status: "Not Started", due_date: "", alert_days_before: "" });

  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target?.type === "checkbox" ? e.target.checked : e.target.value }));

  const handleVendorToggle = (e) => {
    const checked = e.target.checked;
    setForm(p => ({ ...p, is_vendor: checked, alert_days_before: checked && !p.alert_days_before ? "7" : p.alert_days_before }));
  };

  return (
    <div style={{ ...{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16 }, padding: 18, marginBottom: 16 }}>
      <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 12 }}>
        {initial?.id ? "Edit Activity" : "Add New Activity"}
      </h4>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>ACTIVITY TITLE *</label>
          <input value={form.title} onChange={set("title")} placeholder="e.g. Review vendor invoice PT XYZ"
            style={{ width: "100%", fontSize: 13, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box" }} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>DESCRIPTION</label>
          <textarea value={form.description} onChange={set("description")} rows={2} placeholder="Details (optional)"
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box", resize: "vertical" }} />
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>CATEGORY</label>
          <select value={form.category} onChange={set("category")}
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
            {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>DUE DATE</label>
          <input type="date" value={form.due_date || ""} onChange={set("due_date")}
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, outline: "none", boxSizing: "border-box" }} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>ASSIGNED TO</label>
          <AssignedToSelect
            value={form.assigned_to}
            onChange={(v) => setForm(p => ({ ...p, assigned_to: v }))}
            employees={employees}
          />
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>ROLE</label>
          <select value={form.role} onChange={set("role")}
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
            {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>STATUS</label>
          <select value={form.status} onChange={set("status")}
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
            {Object.keys(STATUS_CFG).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>ALERT (DAYS BEFORE DUE DATE)</label>
          <input type="number" min="0" value={form.alert_days_before} onChange={set("alert_days_before")} placeholder="e.g. 7 — leave blank for no alert"
            style={{ width: "100%", fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box" }} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 18 }}>
          <input type="checkbox" checked={!!form.is_vendor} onChange={handleVendorToggle} id="is_vendor"
            style={{ width: 16, height: 16, accentColor: "#2563eb" }} />
          <label htmlFor="is_vendor" style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
            Vendor / TOP related <span style={{ color: "#94a3b8", fontWeight: 500 }}>(pre-fills a 7-day alert, still editable)</span>
          </label>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={() => onSave({ ...form, alert_days_before: form.alert_days_before === "" ? null : Number(form.alert_days_before) })} disabled={saving || !form.title.trim()}
          style={{ fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", boxShadow: NEU.shadowBtn, opacity: (saving || !form.title.trim()) ? 0.5 : 1 }}>
          {saving ? "Saving..." : "Submit"}
        </button>
        <button onClick={onCancel}
          style={{ fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: NEU.bg, color: "#64748b", cursor: "pointer", boxShadow: NEU.shadowBtn }}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ListView({ tasks, loading, onEdit, onDelete, onToggleComplete }) {
  if (loading) {
    return <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}><Loader2 size={20} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  }
  if (!tasks.length) {
    return <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No activities yet. Click "+ Add New Activity" to get started.</p>;
  }

  const fmtDate = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" }); }
    catch (_) { return iso; }
  };

  return (
    <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
            {["Activity", "Category", "Assigned To", "Role", "Due Date", "Status", ""].map(h => (
              <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontSize: 10.5, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "2px solid rgba(0,0,0,0.06)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((t, i) => (
            <tr key={t.id} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
              <td style={{ padding: "8px 12px", fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>
                {t.title}
                {t.alert_active && (
                  <span style={{ marginLeft: 6, display: "inline-flex", alignItems: "center", gap: 3, padding: "1px 6px", borderRadius: 8, fontSize: 9.5, fontWeight: 700, background: "#fee2e2", color: "#dc2626" }}>
                    <AlertTriangle size={9} /> {t.alert_days_left}d left
                  </span>
                )}
                {t.is_overdue && (
                  <span style={{ marginLeft: 6, display: "inline-flex", alignItems: "center", padding: "1px 6px", borderRadius: 8, fontSize: 9.5, fontWeight: 700, background: "#fef3c7", color: "#d97706" }}>
                    Overdue
                  </span>
                )}
              </td>
              <td style={{ padding: "8px 12px", fontSize: 12, color: "#64748b", fontWeight: 500 }}>{t.category || "—"}</td>
              <td style={{ padding: "8px 12px", fontSize: 12, color: "#475569", fontWeight: 500 }}>{t.assigned_to || "—"}</td>
              <td style={{ padding: "8px 12px", fontSize: 12, color: "#64748b", fontWeight: 500 }}>{t.role || "—"}</td>
              <td style={{ padding: "8px 12px", fontSize: 12, color: t.is_overdue ? "#dc2626" : "#475569", fontWeight: t.is_overdue ? 700 : 500 }}>{fmtDate(t.due_date)}</td>
              <td style={{ padding: "8px 12px" }}><StatusBadge status={t.status} /></td>
              <td style={{ padding: "8px 12px", whiteSpace: "nowrap" }}>
                <div style={{ display: "flex", gap: 6 }}>
                  {t.status !== "Completed" && (
                    <button onClick={() => onToggleComplete(t)} title="Mark complete"
                      style={{ background: "none", border: "none", cursor: "pointer", color: "#16a34a", padding: 4 }}>
                      <Check size={14} />
                    </button>
                  )}
                  <button onClick={() => onEdit(t)} title="Edit"
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#2563eb", padding: 4 }}>
                    <Pencil size={13} />
                  </button>
                  <button onClick={() => onDelete(t.id)} title="Delete"
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4 }}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CalendarView({ tasks, year, month, setYear, setMonth }) {
  const daysInMonth = new Date(year, month, 0).getDate();
  const startDay = new Date(year, month - 1, 1).getDay();
  const cells = [];
  for (let i = 0; i < startDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const tasksByDay = {};
  tasks.forEach(t => {
    if (!t.due_date) return;
    const d = new Date(t.due_date + "T00:00:00");
    if (d.getFullYear() === year && d.getMonth() + 1 === month) {
      const day = d.getDate();
      (tasksByDay[day] = tasksByDay[day] || []).push(t);
    }
  });

  const [selectedDay, setSelectedDay] = useState(null);
  const dayTasks = selectedDay ? (tasksByDay[selectedDay] || []) : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
      <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <button onClick={() => { if (month === 1) { setMonth(12); setYear(year - 1); } else setMonth(month - 1); }}
            style={{ padding: "4px 10px", borderRadius: 8, border: "none", background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: "pointer", fontSize: 13, fontWeight: 700 }}>‹</button>
          <h4 style={{ fontSize: 13, fontWeight: 800, color: "#1e293b" }}>{MONTH_NAMES[month - 1]} {year}</h4>
          <button onClick={() => { if (month === 12) { setMonth(1); setYear(year + 1); } else setMonth(month + 1); }}
            style={{ padding: "4px 10px", borderRadius: 8, border: "none", background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: "pointer", fontSize: 13, fontWeight: 700 }}>›</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, marginBottom: 4 }}>
          {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d => (
            <div key={d} style={{ textAlign: "center", fontSize: 10, fontWeight: 700, color: "#94a3b8" }}>{d}</div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
          {cells.map((day, i) => {
            if (day === null) return <div key={i} />;
            const dayT = tasksByDay[day] || [];
            const hasVendorAlert = dayT.some(t => t.vendor_alert);
            const isSelected = selectedDay === day;
            return (
              <div key={i} onClick={() => setSelectedDay(isSelected ? null : day)}
                style={{
                  minHeight: 44, borderRadius: 10, padding: "4px 6px", cursor: "pointer",
                  background: isSelected ? "#2563eb" : NEU.bg,
                  boxShadow: isSelected ? "inset 2px 2px 5px rgba(0,0,0,0.25)" : NEU.shadowOutSm,
                  transition: "all 0.15s ease",
                }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: isSelected ? "#fff" : "#1e293b" }}>{day}</div>
                {dayT.length > 0 && (
                  <div style={{
                    marginTop: 2, fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 8,
                    display: "inline-block",
                    background: isSelected ? "rgba(255,255,255,0.25)" : (hasVendorAlert ? "#fee2e2" : "#dbeafe"),
                    color: isSelected ? "#fff" : (hasVendorAlert ? "#dc2626" : "#1d4ed8"),
                  }}>
                    {dayT.length} task{dayT.length > 1 ? "s" : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: 16 }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>
          {selectedDay ? `${MONTH_NAMES[month - 1]} ${selectedDay}, ${year}` : "Select a day"}
        </h4>
        {!selectedDay ? (
          <p style={{ fontSize: 12, color: "#94a3b8" }}>Click a date with tasks to view details.</p>
        ) : dayTasks.length === 0 ? (
          <p style={{ fontSize: 12, color: "#94a3b8" }}>No activities due this day.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {dayTasks.map(t => (
              <div key={t.id} style={{ padding: "8px 10px", borderRadius: 10, background: NEU.bg, boxShadow: NEU.shadowOutSm }}>
                <p style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>{t.title}</p>
                <p style={{ fontSize: 10.5, color: "#64748b", marginTop: 2 }}>{t.assigned_to} · {t.role}</p>
                <div style={{ marginTop: 4 }}><StatusBadge status={t.status} /></div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function HRTodoList() {
  const [view, setView] = useState("list");
  const [tasks, setTasks] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [saving, setSaving] = useState(false);
  const [filters, setFilters] = useState({ status: "", role: "", category: "", vendor_only: false, search: "" });
  const [calYear, setCalYear] = useState(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(new Date().getMonth() + 1);
  const [employees, setEmployees] = useState([]);

  useEffect(() => {
    hrApi.getEmployeeNames().then(setEmployees).catch(() => {});
  }, []);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const p = {};
      if (filters.status) p.status = filters.status;
      if (filters.role) p.role = filters.role;
      if (filters.category) p.category = filters.category;
      if (filters.vendor_only) p.vendor_only = true;
      if (filters.search) p.search = filters.search;
      if (view === "calendar") { p.year = calYear; p.month = calMonth; }
      const res = await hrApi.getTodoTasks(p);
      setTasks(res);
    } catch (_) {}
    finally { setLoading(false); }
  }, [filters, view, calYear, calMonth]);

  const fetchSummary = useCallback(async () => {
    try { setSummary(await hrApi.getTodoSummary()); } catch (_) {}
  }, []);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);
  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const handleFilter = (k, v) => setFilters(p => ({ ...p, [k]: v }));

  const handleSave = async (form) => {
    setSaving(true);
    try {
      if (editingTask?.id) {
        await hrApi.updateTodoTask(editingTask.id, form);
      } else {
        await hrApi.createTodoTask(form);
      }
      setShowForm(false);
      setEditingTask(null);
      fetchTasks();
      fetchSummary();
    } catch (_) {}
    finally { setSaving(false); }
  };

  const handleEdit = (t) => { setEditingTask(t); setShowForm(true); };

  const handleDelete = async (id) => {
    if (!confirm("Delete this activity?")) return;
    try { await hrApi.deleteTodoTask(id); fetchTasks(); fetchSummary(); } catch (_) {}
  };

  const handleToggleComplete = async (t) => {
    try { await hrApi.updateTodoTask(t.id, { status: "Completed" }); fetchTasks(); fetchSummary(); } catch (_) {}
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Summary cards */}
      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
          {[
            { label: "Total",       val: summary.total,       color: "#2563eb" },
            { label: "Not Started", val: summary.not_started, color: "#64748b" },
            { label: "In Progress", val: summary.in_progress, color: "#1d4ed8" },
            { label: "Completed",   val: summary.completed,   color: "#16a34a" },
            { label: "Overdue",     val: summary.overdue,     color: "#d97706" },
            { label: "Vendor Alert",val: summary.vendor_alerts,color: "#dc2626" },
          ].map(c => (
            <div key={c.label} style={{ padding: "12px", borderRadius: 14, background: NEU.bg, boxShadow: NEU.shadowOut, textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: c.color }}>{c.val}</div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", marginTop: 2 }}>{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {[["list", "List View", List], ["calendar", "e-Calendar View", CalendarIcon]].map(([id, label, Icon]) => (
            <button key={id} onClick={() => setView(id)}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 10,
                border: "none", fontSize: 12, fontWeight: 700, background: NEU.bg, cursor: "pointer",
                color: view === id ? "#2563eb" : "#64748b",
                boxShadow: view === id ? NEU.shadowIn : NEU.shadowOutSm,
              }}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => { fetchTasks(); fetchSummary(); }}
            style={{ padding: 8, borderRadius: 10, border: "none", background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: "pointer", color: "#64748b" }}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={() => { setEditingTask(null); setShowForm(!showForm); }}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: NEU.shadowBtn }}>
            <Plus size={14} /> Add New Activity
          </button>
        </div>
      </div>

      {/* Add/Edit Form */}
      {showForm && (
        <TaskForm
          initial={editingTask}
          saving={saving}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditingTask(null); }}
          employees={employees}
        />
      )}

      {view === "list" ? (
        <>
          {/* Filters */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <select value={filters.status} onChange={e => handleFilter("status", e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
              <option value="">All Status</option>
              {Object.keys(STATUS_CFG).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.role} onChange={e => handleFilter("role", e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
              <option value="">All Roles</option>
              {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <select value={filters.category} onChange={e => handleFilter("category", e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
              <option value="">All Categories</option>
              {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: "#1e293b", padding: "6px 12px", borderRadius: 8, background: NEU.bg, boxShadow: NEU.shadowOutSm, cursor: "pointer" }}>
              <input type="checkbox" checked={filters.vendor_only} onChange={e => handleFilter("vendor_only", e.target.checked)} style={{ accentColor: "#dc2626" }} />
              Vendor Alert Only
            </label>
            <input value={filters.search} onChange={e => handleFilter("search", e.target.value)} placeholder="Search title / assignee..."
              style={{ fontSize: 12, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", width: 200 }} />
          </div>

          <ListView tasks={tasks} loading={loading} onEdit={handleEdit} onDelete={handleDelete} onToggleComplete={handleToggleComplete} />
        </>
      ) : (
        <CalendarView tasks={tasks} year={calYear} month={calMonth} setYear={setCalYear} setMonth={setCalMonth} />
      )}
    </div>
  );
}
