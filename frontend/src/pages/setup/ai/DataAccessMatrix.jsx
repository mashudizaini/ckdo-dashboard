import { useEffect, useMemo, useState } from "react";
import { Grid3x3, Loader2, Plus, Minus, Trash2, Info, EyeOff, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import api from "@/api/client";

// Data access matrix for EBS chat — backend: app/services/ebs_mart/policy.py,
// endpoints /ai/ebs-mart/access-policy*. Each cell is one role × one data set:
//   —      no access
//   Qty    quantities, dates and names only; price / value / amount columns
//          are removed from every answer and run_sql may not read them
//   Full   every column
// System Administration data (sa_*) is not here: it follows the IT email
// allowlist only.
// Data sets are grouped per domain; a group starts collapsed and shows a
// per-role summary until it is expanded with its + button.

const DOMAIN_LABEL = {
  AP: "Payables (AP)", AR: "Receivables (AR)", PO: "Purchasing (PO/PR)", INV: "Inventory", OM: "Sales (OM)",
  OPM: "Production (OPM)", GL: "General Ledger (GL)", CE: "Cash & Bank (CE)", FA: "Fixed Assets (FA)", MASTER: "Master data",
};
const DOMAIN_ORDER = ["INV", "PO", "AP", "OM", "AR", "OPM", "GL", "CE", "FA", "MASTER"];

const LEVEL_STYLE = {
  "": "border-gray-800 bg-gray-900 text-gray-600",
  qty: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  full: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
};

const errText = (e) => {
  const d = e?.detail ?? e?.response?.data?.detail;
  return d ? (typeof d === "string" ? d : JSON.stringify(d)) : e?.message || "Something went wrong";
};

export default function DataAccessMatrix({ onRolesChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(null); // "role|mart" of the cell being saved
  const [newRole, setNewRole] = useState({ code: "", label: "" });
  const [addingRole, setAddingRole] = useState(false);
  const [open, setOpen] = useState({}); // domain -> expanded

  const load = async () => {
    try {
      setData(await api.get("/ai/ebs-mart/access-policy"));
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  };
  useEffect(() => { load(); }, []);

  const grantOf = useMemo(() => {
    const m = {};
    (data?.grants || []).forEach((g) => { m[`${g.role_code}|${g.mart}`] = g.level; });
    return m;
  }, [data]);

  const byDomain = useMemo(() => {
    const groups = {};
    (data?.marts || []).forEach((m) => { (groups[m.domain] ||= []).push(m); });
    return DOMAIN_ORDER.filter((d) => groups[d]).map((d) => [d, groups[d]])
      .concat(Object.keys(groups).filter((d) => !DOMAIN_ORDER.includes(d)).map((d) => [d, groups[d]]));
  }, [data]);

  const toggle = (domain) => setOpen((o) => ({ ...o, [domain]: !o[domain] }));
  const allOpen = byDomain.length > 0 && byDomain.every(([d]) => open[d]);
  const setAll = (value) => setOpen(Object.fromEntries(byDomain.map(([d]) => [d, value])));

  const setLevel = async (role, mart, level) => {
    const key = `${role}|${mart}`;
    setSaving(key);
    setError(null);
    try {
      await api.put("/ai/ebs-mart/access-policy/grant", { role_code: role, mart, level: level || null });
      setData((d) => ({
        ...d,
        grants: [...d.grants.filter((g) => !(g.role_code === role && g.mart === mart)),
                 ...(level ? [{ role_code: role, mart, level }] : [])],
      }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setSaving(null);
    }
  };

  const addRole = async (e) => {
    e.preventDefault();
    const code = newRole.code.trim().toLowerCase();
    if (!code || !newRole.label.trim()) return;
    setAddingRole(true);
    setError(null);
    try {
      await api.put(`/ai/ebs-mart/access-policy/roles/${encodeURIComponent(code)}`,
        { label: newRole.label.trim(), all_access: false });
      setNewRole({ code: "", label: "" });
      await load();
      onRolesChange?.();
    } catch (err) {
      setError(errText(err));
    } finally {
      setAddingRole(false);
    }
  };

  const deleteRole = async (code) => {
    setError(null);
    try {
      await api.delete(`/ai/ebs-mart/access-policy/roles/${encodeURIComponent(code)}`);
      await load();
      onRolesChange?.();
    } catch (err) {
      setError(errText(err));
    }
  };

  if (!data && !error) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 flex justify-center">
        <Loader2 size={18} className="animate-spin text-gray-500" />
      </div>
    );
  }

  const roles = data?.roles || [];

  // What a role has in one domain, shown on the group row: "All", "—", or "2 Full · 1 Qty".
  const summary = (role, marts) => {
    if (role.all_access && !marts.some((m) => m.explicit_grant)) {
      return <span className={`rounded border px-1.5 py-0.5 ${LEVEL_STYLE.full}`}>All</span>;
    }
    let full = 0, qty = 0;
    marts.forEach((m) => {
      const lv = grantOf[`${role.role_code}|${m.mart}`];
      if (lv === "full") full += 1;
      else if (lv === "qty") qty += 1;
    });
    if (!full && !qty) return <span className="text-gray-700">—</span>;
    return (
      <span className="inline-flex gap-1">
        {full > 0 && <span className={`rounded border px-1.5 py-0.5 ${LEVEL_STYLE.full}`}>{full} Full</span>}
        {qty > 0 && <span className={`rounded border px-1.5 py-0.5 ${LEVEL_STYLE.qty}`}>{qty} Qty</span>}
      </span>
    );
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="px-5 py-3 border-b border-gray-800 flex items-start gap-2.5">
        <Grid3x3 size={16} className="text-blue-400 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-gray-200">Data access per role</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Applies to EBS Analyst, EBS Finance Controller and EBS Support in CoChat. The dashboard checks it on
            every tool call, so it does not depend on the prompt. Changes take effect within 30 seconds.
          </p>
        </div>
        <button type="button" onClick={() => setAll(!allOpen)}
          className="shrink-0 flex items-center gap-1 rounded-md border border-gray-700 px-2 py-1 text-[11px] text-gray-400 hover:text-gray-200 hover:border-gray-600">
          {allOpen ? <ChevronsDownUp size={12} /> : <ChevronsUpDown size={12} />} {allOpen ? "Collapse all" : "Expand all"}
        </button>
      </div>

      <div className="px-5 py-3 border-b border-gray-800 flex flex-wrap gap-x-5 gap-y-1.5 text-[11px] text-gray-400">
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE[""]}`}>—</span> no access</span>
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE.qty}`}>Qty</span> quantities, dates and names only — price/value columns are hidden</span>
        <span className="flex items-center gap-1.5"><span className={`rounded border px-1.5 ${LEVEL_STYLE.full}`}>Full</span> all columns</span>
        <span className="flex items-center gap-1.5 text-gray-500"><Info size={12} /> System Administration data is limited to the IT email allowlist and is not managed here.</span>
      </div>

      {error && <div className="mx-5 mt-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="overflow-auto max-h-[70vh]">
        <table className="min-w-full text-xs border-separate border-spacing-0">
          <thead>
            <tr>
              <th className="sticky top-0 left-0 z-30 bg-gray-900 border-b border-gray-700 text-left font-medium text-gray-500 px-4 py-2 min-w-[240px]">
                Data set
              </th>
              {roles.map((r) => (
                <th key={r.role_code} title={r.label}
                  className="sticky top-0 z-20 bg-gray-900 border-b border-gray-700 px-2 py-2 text-center align-bottom min-w-[92px]">
                  <div className="font-mono text-[11px] text-gray-300">{r.role_code.replace(/^ebs-/, "")}</div>
                  <div className="text-[10px] font-normal text-gray-600">{r.users} {r.users === 1 ? "user" : "users"}</div>
                  {!r.all_access && r.users === 0 && (
                    <button onClick={() => deleteRole(r.role_code)} title={`Delete role ${r.role_code}`}
                      className="mt-1 text-gray-600 hover:text-red-400"><Trash2 size={12} /></button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {byDomain.map(([domain, marts]) => {
              const expanded = !!open[domain];
              return [
                <tr key={`h-${domain}`} className="bg-gray-950">
                  <td className="sticky left-0 z-10 bg-gray-950 border-b border-gray-800 px-2 py-1.5">
                    <button type="button" onClick={() => toggle(domain)} aria-expanded={expanded}
                      className="flex items-center gap-2 w-full text-left rounded px-2 py-0.5 hover:bg-gray-800/60">
                      <span className="flex items-center justify-center w-4 h-4 rounded border border-gray-700 text-gray-400">
                        {expanded ? <Minus size={10} /> : <Plus size={10} />}
                      </span>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-gray-300">{DOMAIN_LABEL[domain] || domain}</span>
                      <span className="text-[10px] text-gray-600">{marts.length} data {marts.length === 1 ? "set" : "sets"}</span>
                    </button>
                  </td>
                  {roles.map((r) => (
                    <td key={`${domain}|${r.role_code}`} className="border-b border-gray-800 px-2 py-1.5 text-center text-[10px]">
                      {summary(r, marts)}
                    </td>
                  ))}
                </tr>,
                ...(expanded ? marts.map((m) => (
                  <tr key={m.mart} className="group">
                    <td className="sticky left-0 z-10 bg-gray-900 group-hover:bg-gray-800 border-b border-gray-800/60 pl-10 pr-4 py-1.5">
                      <div className="font-mono text-[11px] text-gray-300">{m.mart}</div>
                      <div className="text-[10px] text-gray-600 line-clamp-1 max-w-[320px]" title={m.description}>{m.description}</div>
                      {m.money_columns.length > 0 && (
                        <div className="text-[10px] text-gray-600 flex items-center gap-1" title={m.money_columns.join(", ")}>
                          <EyeOff size={10} /> hidden at Qty: {m.money_columns.slice(0, 4).join(", ")}
                          {m.money_columns.length > 4 ? ` +${m.money_columns.length - 4}` : ""}
                        </div>
                      )}
                    </td>
                    {roles.map((r) => {
                      const key = `${r.role_code}|${m.mart}`;
                      // all_access covers every data set except explicit_grant ones
                      // (PAC Business Plan), which are granted per role like any other.
                      if (r.all_access && !m.explicit_grant) {
                        return (
                          <td key={key} className="border-b border-gray-800/60 group-hover:bg-gray-800/40 px-2 py-1.5 text-center">
                            <span className={`rounded border px-2 py-0.5 ${LEVEL_STYLE.full}`}>All</span>
                          </td>
                        );
                      }
                      const level = grantOf[key] || "";
                      return (
                        <td key={key} className="border-b border-gray-800/60 group-hover:bg-gray-800/40 px-2 py-1.5 text-center">
                          <select id={`acl-${key}`} aria-label={`${r.role_code} ${m.mart}`} value={level}
                            disabled={saving === key}
                            onChange={(e) => setLevel(r.role_code, m.mart, e.target.value)}
                            className={`rounded border px-1.5 py-0.5 text-[11px] focus:outline-none focus:ring-1 focus:ring-blue-500 ${LEVEL_STYLE[level]}`}>
                            <option value="">—</option>
                            <option value="qty" disabled={m.money_columns.length === 0}>Qty</option>
                            <option value="full">Full</option>
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                )) : []),
              ];
            })}
          </tbody>
        </table>
      </div>

      <form onSubmit={addRole} className="px-5 py-3 border-t border-gray-800 flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="new-role-code" className="block text-[10px] font-bold uppercase tracking-wider text-gray-600 mb-1">New role code</label>
          <input id="new-role-code" value={newRole.code} placeholder="ebs-purchasing-stock"
            onChange={(e) => setNewRole((r) => ({ ...r, code: e.target.value }))}
            className="rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 w-48" />
        </div>
        <div className="flex-1 min-w-[180px]">
          <label htmlFor="new-role-label" className="block text-[10px] font-bold uppercase tracking-wider text-gray-600 mb-1">Name</label>
          <input id="new-role-label" value={newRole.label} placeholder="Purchasing — stock view"
            onChange={(e) => setNewRole((r) => ({ ...r, label: e.target.value }))}
            className="rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-200 w-full" />
        </div>
        <button type="submit" disabled={addingRole || !newRole.code.trim() || !newRole.label.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-white">
          {addingRole ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add role
        </button>
        <p className="w-full text-[10px] text-gray-600">
          A role still assigned to a user cannot be deleted. Roles with "All" access (management) get new data sets automatically.
        </p>
      </form>
    </div>
  );
}
