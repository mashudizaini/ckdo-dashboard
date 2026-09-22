import { useState, useEffect, useCallback } from "react";
import { Loader2, Plus, Pencil, Trash2, X } from "lucide-react";
import { hrApi } from "@/api/dashboard";

// Data Coverage — moved here from Dashboard > HRGA > Attendance Rate
// (2026-08-19 user request). Was the "Data Coverage" tab there; now lives
// standalone under Setup > HRGA instead.
const COVERAGE_SOURCES = [
  { key: "intercom",      label: "Intercom" },
  { key: "talenta",       label: "Talenta (Attendance)" },
  { key: "talenta-leave", label: "Talenta (Leave)" },
  { key: "plant",         label: "Plant" },
  { key: "office",        label: "Office" },
  { key: "manual",        label: "Manual" },
];

function AttendanceCoverageSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState(null); // null = all sources combined

  useEffect(() => {
    setLoading(true);
    hrApi.getAttendanceCoverage(10)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: "#94a3b8" }} /></div>;
  if (!data) return <p className="text-center text-xs text-gray-500 py-10">Failed to load coverage data.</p>;

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const gridByYm = {};
  data.grid.forEach(c => { gridByYm[`${c.year}-${c.month}`] = c; });
  const yearsDesc = [...data.years].sort((a, b) => b - a);

  const cellStyle = (status) => {
    if (status === "data") return "bg-green-500/15 text-green-300 border border-green-500/25";
    if (status === "gap")  return "bg-red-500/15 text-red-400 border border-red-500/30";
    return "bg-gray-800/40 text-gray-700 border border-gray-800";
  };

  const selectedLabel = selectedSource
    ? (COVERAGE_SOURCES.find(s => s.key === selectedSource)?.label || selectedSource)
    : "All Sources";

  return (
    <div className="space-y-4">
      {/* Last upload per source — click a card to filter the grid below by that source */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setSelectedSource(null)}
          className={`rounded-lg border px-3 py-2 text-xs text-left min-w-[100px] transition-colors ${
            selectedSource === null
              ? "border-blue-500/50 bg-blue-500/10"
              : "border-gray-800 bg-gray-900 hover:border-gray-700"
          }`}>
          <div className={`font-semibold ${selectedSource === null ? "text-blue-300" : "text-gray-300"}`}>All Sources</div>
          <div className="text-gray-600 mt-0.5">Combined view</div>
        </button>
        {COVERAGE_SOURCES.map(s => {
          const info = data.last_upload_by_source[s.key];
          const isActive = selectedSource === s.key;
          return (
            <button key={s.key} onClick={() => setSelectedSource(cur => cur === s.key ? null : s.key)}
              className={`rounded-lg border px-3 py-2 text-xs text-left min-w-[140px] transition-colors ${
                isActive ? "border-blue-500/50 bg-blue-500/10" : "border-gray-800 bg-gray-900 hover:border-gray-700"
              }`}>
              <div className={`font-semibold ${isActive ? "text-blue-300" : "text-gray-300"}`}>{s.label}</div>
              {info ? (
                <div className="text-gray-500 mt-0.5">
                  {info.uploaded_at?.replace("T", " ").slice(0, 16)}
                  <div className="text-gray-600 truncate max-w-[160px]" title={info.filename}>{info.filename}</div>
                </div>
              ) : (
                <div className="text-gray-600 mt-0.5">Never uploaded</div>
              )}
            </button>
          );
        })}
      </div>

      <p className="text-xs text-gray-500">Showing: <span className="text-gray-300 font-semibold">{selectedLabel}</span></p>

      {/* Heatmap grid */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-gray-500 bg-gray-800/60 sticky left-0">Year</th>
              {MONTHS.map(m => <th key={m} className="px-2 py-2 text-center text-gray-500 bg-gray-800/60 font-medium">{m}</th>)}
            </tr>
          </thead>
          <tbody>
            {yearsDesc.map(yr => (
              <tr key={yr} className="border-t border-gray-800">
                <td className="px-3 py-2 font-semibold text-gray-300 bg-gray-900 sticky left-0">{yr}</td>
                {MONTHS.map((_, i) => {
                  const mo = i + 1;
                  const cell = gridByYm[`${yr}-${mo}`];
                  const value = selectedSource ? (cell?.by_source?.[selectedSource] || 0) : (cell?.total || 0);
                  const status = !cell || cell.status === "outside" ? "outside" : (value > 0 ? "data" : "gap");
                  const sourceLines = cell && cell.total > 0
                    ? Object.entries(cell.by_source).map(([k, v]) => `${k}: ${v}`).join("\n")
                    : "";
                  const tooltip = selectedSource
                    ? (value > 0 ? `${selectedLabel}: ${value} rows` : status === "gap" ? `${selectedLabel}: no data` : "")
                    : cell?.total > 0 ? `${cell.total} rows, ${cell.employees} employees\n${sourceLines}` : status === "gap" ? "No data uploaded" : "";
                  return (
                    <td key={mo} className="p-1">
                      <div title={tooltip}
                        className={`w-16 h-9 rounded flex items-center justify-center font-semibold ${cellStyle(status)}`}>
                        {value > 0 ? value : (status === "gap" ? "—" : "")}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-green-500/30 border border-green-500/40 inline-block" /> Ada data</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-red-500/30 border border-red-500/40 inline-block" /> Belum diupload (gap)</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-gray-800/40 border border-gray-800 inline-block" /> Di luar rentang data</span>
        {data.observed_range.from && (
          <span className="text-gray-600">Data tersedia: {data.observed_range.from} s/d {data.observed_range.to}</span>
        )}
      </div>
    </div>
  );
}

// Department Master — the curated department/division/team hierarchy +
// display order (see backend/app/models/department_master.py). Previously
// SQL-only; this is that table's CRUD UI, so HR can add/reorder/rename
// without a developer running SQL by hand.
const TYPE_BADGE = {
  director:   "bg-purple-500/15 text-purple-300 border-purple-500/30",
  department: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  division:   "bg-teal-500/15 text-teal-300 border-teal-500/30",
  team:       "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

function DeptMasterFormModal({ node, onClose, onSaved }) {
  const isNew = !node?.id;
  const [form, setForm] = useState({
    name: node?.name || "",
    type: node?.type || "team",
    parent_id: node?.parent_id ?? null,
    sequence: node?.sequence ?? 0,
  });
  const [lov, setLov] = useState([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    hrApi.getDeptMasterLov().then(setLov).catch(() => setLov([]));
  }, []);

  const parentOptions = lov.filter((n) => n.id !== node?.id);

  const handleSave = async () => {
    if (!form.name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, parent_id: form.parent_id || null, sequence: Number(form.sequence) || 0 };
      if (isNew) await hrApi.createDeptMaster(payload);
      else await hrApi.updateDeptMaster(node.id, payload);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete "${node.name}"? This can't be undone.`)) return;
    setDeleting(true);
    setError("");
    try {
      await hrApi.deleteDeptMaster(node.id);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.detail || "Failed to delete — it may still have children.");
      setDeleting(false);
    }
  };

  const inputCls = "w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500";
  const labelCls = "mb-1 block text-[10px] font-semibold uppercase tracking-wide text-gray-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(15,23,42,0.6)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-100">{isNew ? "Add Entry" : "Edit Entry"}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-3">
          {error && <p className="text-xs text-red-400 font-semibold">{error}</p>}
          <div>
            <label className={labelCls}>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Sales & Marketing, Quality Management, QA" className={inputCls} />
            <p className="text-[10px] text-gray-600 mt-1">Must match the raw Employee department/division/team value already in use elsewhere — this table only curates order, not the display label.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className={inputCls}>
                <option value="director">Director</option>
                <option value="department">Department</option>
                <option value="division">Division</option>
                <option value="team">Team</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Sequence</label>
              <input type="number" value={form.sequence} onChange={(e) => setForm({ ...form, sequence: e.target.value })} className={inputCls} />
            </div>
          </div>
          <div>
            <label className={labelCls}>Parent (blank = top level)</label>
            <select value={form.parent_id || ""} onChange={(e) => setForm({ ...form, parent_id: e.target.value ? Number(e.target.value) : null })} className={inputCls}>
              <option value="">— None (top level) —</option>
              {parentOptions.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.type})</option>)}
            </select>
          </div>
        </div>
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-800">
          <div>
            {!isNew && (
              <button onClick={handleDelete} disabled={deleting || saving}
                className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold text-red-400 hover:bg-red-500/10 disabled:opacity-40 transition-colors">
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete
              </button>
            )}
          </div>
          <button onClick={handleSave} disabled={saving || deleting}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-4 py-2 text-xs font-semibold text-white transition-colors">
            {saving ? <Loader2 size={13} className="animate-spin" /> : null}
            {saving ? "Saving..." : isNew ? "Add" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DepartmentMasterPanel() {
  const [nodes, setNodes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modalNode, setModalNode] = useState(null); // null=closed, {}=new, {...}=edit

  const load = useCallback(async () => {
    setLoading(true);
    try { setNodes((await hrApi.getDeptMasterList()) || []); } catch (_) { setNodes([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin text-gray-600" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-gray-500 max-w-xl">
          Sets the display order Employee Summary, Turnover Report and other Department/Team filters use — sorted by Sequence within each Type/Parent, not alphabetically.
        </p>
        <button onClick={() => setModalNode({})}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-2 text-xs font-semibold text-white transition-colors shrink-0">
          <Plus size={14} /> Add Entry
        </button>
      </div>

      {nodes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-8 py-16 text-center">
          <p className="text-sm text-gray-400">No entries yet. Click "Add Entry" to create one.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-xs">
            <thead className="bg-gray-800/70">
              <tr>
                <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Name</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Type</th>
                <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Parent</th>
                <th className="px-3 py-2 text-right font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">Sequence</th>
                <th className="px-3 py-2 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {nodes.map((n) => (
                <tr key={n.id} onClick={() => setModalNode(n)} className="hover:bg-gray-800/30 cursor-pointer transition-colors">
                  <td className="px-3 py-2 font-medium text-gray-200 whitespace-nowrap">{n.name}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${TYPE_BADGE[n.type] || "bg-gray-700 text-gray-400 border-gray-600"}`}>{n.type}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{n.parent_name || "—"}</td>
                  <td className="px-3 py-2 text-right text-gray-400 whitespace-nowrap">{n.sequence}</td>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => setModalNode(n)} title="Edit" className="p-1 text-gray-600 hover:text-indigo-400">
                      <Pencil size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalNode && (
        <DeptMasterFormModal
          node={modalNode.id ? modalNode : null}
          onClose={() => setModalNode(null)}
          onSaved={() => { setModalNode(null); load(); }}
        />
      )}
    </div>
  );
}

const HR_SETUP_TABS = [
  { id: "coverage", label: "Data Coverage" },
  { id: "dept-master", label: "Department Master" },
];

export default function HRSetupPage() {
  const [tab, setTab] = useState("coverage");
  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1e293b" }}>HRGA Setup</h2>
        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
          Attendance upload coverage, and the curated department/division/team order used across HRGA reports.
        </p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {HR_SETUP_TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
              tab === t.id
                ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                : "border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700"
            }`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "coverage"    && <AttendanceCoverageSection />}
      {tab === "dept-master" && <DepartmentMasterPanel />}
    </div>
  );
}
