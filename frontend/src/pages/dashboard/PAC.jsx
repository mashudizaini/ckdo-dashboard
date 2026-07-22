import { useState, useEffect, useRef, useCallback } from "react";
import {
  Banknote, ExternalLink, RefreshCw, Filter, X,
  Download, Loader2, TrendingUp, TrendingDown, Minus,
  BookOpen, Plus, Trash2, Save, Printer, ChevronDown, ChevronRight,
  CheckCircle, Clock, Edit3, FileText, Globe, Upload, AlertCircle, Calendar, BookOpenCheck, Sparkles, Settings,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer, ReferenceLine,
} from "recharts";
import * as XLSX from "xlsx";
import { pacApi } from "@/api/dashboard";

/* ─── Tabs ────────────────────────────────────────── */
const TABS = [
  { id: "bizplan",  icon: BookOpen,   color: "text-violet-400", bg: "bg-violet-500/10", activeBorder: "border-violet-500/40", label: "Business Plan"       },
  { id: "budget",   icon: Banknote,   color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Budget Usage Report" },
  { id: "mt940",    icon: Banknote,   color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "BCA MT940 Upload"    },
  { id: "exchange", icon: Globe,      color: "text-amber-400",  bg: "bg-amber-500/10",  activeBorder: "border-amber-500/40",  label: "Exchange Rate"       },
];

const CY = new Date().getFullYear();
const PAGE_SIZE = 15;

/* ─── Formatters ─────────────────────────────────── */
const fmtIDR = (n) => n == null ? "—" : Number(n).toLocaleString("id-ID");
const fmtB   = (n) => {
  if (n == null) return "—";
  const v = Math.abs(Number(n));
  if (v >= 1_000_000_000) return (Number(n) / 1_000_000_000).toFixed(2) + " B";
  if (v >= 1_000_000)     return (Number(n) / 1_000_000).toFixed(1) + " M";
  return fmtIDR(n);
};
const fmtShort = (v) => {
  const abs = Math.abs(Number(v));
  if (abs >= 1_000_000_000) return (Number(v)/1_000_000_000).toFixed(1)+"B";
  if (abs >= 1_000_000)     return (Number(v)/1_000_000).toFixed(0)+"M";
  if (abs >= 1_000)         return (Number(v)/1_000).toFixed(0)+"K";
  return String(Number(v));
};

const MONTH_NAMES = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/* ─── Main ───────────────────────────────────────── */
export default function PACDashboard() {
  const [activeTab, setActiveTab] = useState("bizplan");

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-4 gap-2">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-all ${
                active
                  ? `${tab.bg} ${tab.activeBorder} ring-1 ring-inset ${tab.activeBorder}`
                  : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
              }`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${tab.bg} border ${tab.activeBorder}`}>
                <tab.icon size={15} className={tab.color} />
              </div>
              <span className={`text-sm font-medium truncate ${active ? "text-white" : "text-gray-400"}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {activeTab === "bizplan"  && <BusinessPlanSection />}
      {activeTab === "budget"   && <BudgetUsageSection />}
      {activeTab === "mt940"    && <MT940Section />}
      {activeTab === "exchange" && <ExchangeRateSection />}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   BUSINESS PLAN MODULE
   ══════════════════════════════════════════════════ */

const BP_SUBTABS = [
  { id: "managerial", label: "Managerial Objective", icon: BookOpen },
  { id: "strategy",   label: "Strategy & Action Plan", icon: FileText },
  { id: "history",    label: "Document List",          icon: Clock    },
  { id: "setup",      label: "Setup",                   icon: Settings },
];

const ROMAN = ["i","ii","iii","iv","v","vi","vii","viii","ix","x"];
const ALPHA  = ["a","b","c","d","e","f","g","h","i","j"];
const CY_BP  = new Date().getFullYear();

/* ── default blank doc structures ─────────────────────────────────────────── */
function defaultMO(year) {
  return {
    doc_type:  "managerial_obj",
    plan_year: year,
    department: "ALL",
    team_code: "",
    team_name: "",
    plan_role: "",
    content: {
      mission:    "Better Life through Better Medicine, Contributing to improved quality of life and public welfare by developing quality medicines",
      vision:     "To provide patients with better access to high-quality, cost-effective medicines in key therapeutic areas",
      objectives: [
        { num: 1, text: "Maximize efficiency" },
        { num: 2, text: "Reduce Risk" },
        { num: 3, text: "Prepare new business" },
      ],
      departments: [
        { name: "Sales & Marketing",   strategies: [{ obj_num: 1, text: "" }, { obj_num: 3, text: "" }, { obj_num: 2, text: "" }] },
        { name: "Strategy Development", strategies: [{ obj_num: 1, text: "" }, { obj_num: 3, text: "" }, { obj_num: 2, text: "" }] },
        { name: "Plant",               strategies: [{ obj_num: 1, text: "" }, { obj_num: 2, text: "" }, { obj_num: 3, text: "" }] },
        { name: "Administration",      strategies: [{ obj_num: 1, text: "" }, { obj_num: 2, text: "" }, { obj_num: 3, text: "" }] },
      ],
    },
  };
}

function defaultSP(year) {
  return {
    doc_type:  "strategy_plan",
    plan_year: year,
    department: "",
    team_code: "",
    team_name: "",
    plan_role: "",
    content: {
      items: [
        {
          obj_num: 1, obj_text: "Maximize efficiency",
          strategies: [{ letter: "a", text: "", actions: [{ num: "i", text: "" }] }],
        },
        {
          obj_num: 2, obj_text: "Reduce Risk",
          strategies: [{ letter: "a", text: "", actions: [{ num: "i", text: "" }] }],
        },
        {
          obj_num: 3, obj_text: "New Idea / Prepare New Business",
          strategies: [{ letter: "a", text: "", actions: [{ num: "i", text: "" }] }],
        },
      ],
    },
  };
}

/* ── Shared textarea style ─────────────────────────────────────────────────── */
const TA = "w-full bg-gray-800/60 border border-gray-700 rounded-md px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-500/60 resize-none leading-relaxed";
const INP = "bg-gray-800/60 border border-gray-700 rounded-md px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-500/60";
const BTN_SM = (color = "violet") =>
  `flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all border ` +
  (color === "violet" ? "text-violet-300 border-violet-500/30 bg-violet-500/10 hover:bg-violet-500/20"
   : color === "red"  ? "text-red-400 border-red-500/30 bg-red-500/10 hover:bg-red-500/20"
   : color === "green" ? "text-green-400 border-green-500/30 bg-green-500/10 hover:bg-green-500/20"
   : color === "sky"   ? "text-sky-300 border-sky-500/30 bg-sky-500/10 hover:bg-sky-500/20"
   : color === "teal"  ? "text-teal-300 border-teal-500/30 bg-teal-500/10 hover:bg-teal-500/20"
   : color === "indigo"? "text-indigo-300 border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20"
   : "text-gray-400 border-gray-600 bg-gray-800 hover:bg-gray-700");

/* ══ Managerial Objective Panel ══════════════════════════════════════════════ */
function MOPanel({ year }) {
  const [doc,     setDoc]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const printRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listBusinessPlans({ plan_year: year, doc_type: "managerial_obj" });
      if (res.success && res.data.length > 0) setDoc(res.data[0]);
      else setDoc(defaultMO(year));
    } catch { setDoc(defaultMO(year)); }
    finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const setContent = (fn) => setDoc(prev => ({ ...prev, content: fn(prev.content) }));

  const setObjText  = (idx, val) => setContent(c => {
    const objs = [...c.objectives]; objs[idx] = { ...objs[idx], text: val };
    return { ...c, objectives: objs };
  });

  const setDeptStrat = (di, si, val) => setContent(c => {
    const depts = c.departments.map((d, didx) => {
      if (didx !== di) return d;
      const strats = d.strategies.map((s, sidx) => sidx === si ? { ...s, text: val } : s);
      return { ...d, strategies: strats };
    });
    return { ...c, departments: depts };
  });

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...doc, plan_year: year };
      const res = await pacApi.upsertBusinessPlan(payload);
      if (res.success) { setDoc(res.data); setSaved(true); setTimeout(() => setSaved(false), 2000); }
    } finally { setSaving(false); }
  };

  const print = () => window.print();

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!doc) return null;
  const c = doc.content;

  return (
    <>
      {/* ── Print styles injected ── */}
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          #bp-mo-print, #bp-mo-print * { visibility: visible !important; }
          #bp-mo-print { position: fixed; inset: 0; background: white; padding: 24px; font-family: Arial, sans-serif; font-size: 10pt; color: #000; }
          .no-print { display: none !important; }
        }
      `}</style>

      {/* Screen controls */}
      <div className="flex items-center justify-between mb-4 no-print">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Year: <span className="text-violet-400 font-bold">{year}</span></span>
          <span className="text-xs text-gray-500">·</span>
          <span className="text-xs text-gray-500">Department: <span className="text-gray-300">ALL</span></span>
          {doc.id && <span className={`text-xs px-2 py-0.5 rounded-full border ${doc.status === 'final' ? 'text-green-400 border-green-500/30 bg-green-500/10' : 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10'}`}>{doc.status === 'final' ? '✓ Final' : 'Draft'}</span>}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setDoc(prev => ({ ...prev, status: prev.status === 'final' ? 'draft' : 'final' }))}
            className={BTN_SM(doc.status === 'final' ? 'gray' : 'green')}>
            <CheckCircle size={11} /> {doc.status === 'final' ? 'Mark Draft' : 'Mark Final'}
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("violet")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
          <button onClick={print} className={BTN_SM("gray")}><Printer size={11} /> Print</button>
        </div>
      </div>

      {/* Printable area */}
      <div id="bp-mo-print" ref={printRef}>
        {/* Print header */}
        <div className="hidden print:block mb-4 text-center border-b-2 pb-3" style={{ display: "none" }}>
          <p className="font-bold text-base">PT CKD OTTO Pharmaceuticals</p>
          <p className="text-sm font-semibold">MANAGERIAL OBJECTIVE {year}</p>
        </div>

        {/* Mission & Vision */}
        <SectionCard title="＃ Mission & Vision" subtitle={`${year} Managerial Objective`}>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-violet-400 mb-2">Ｍ Mission</label>
              <textarea rows={4} className={TA} value={c.mission || ""} placeholder="Enter company mission…"
                onChange={e => setContent(cc => ({ ...cc, mission: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs font-semibold text-violet-400 mb-2">Ｖ Vision</label>
              <textarea rows={4} className={TA} value={c.vision || ""} placeholder="Enter company vision…"
                onChange={e => setContent(cc => ({ ...cc, vision: e.target.value }))} />
            </div>
          </div>
        </SectionCard>

        {/* Managerial Objectives */}
        <SectionCard title={`＃ ${year} Managerial Objective`} subtitle="Company-wide strategic objectives">
          <div className="space-y-3">
            {(c.objectives || []).map((obj, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-violet-500/20 border border-violet-500/40 text-violet-400 text-xs flex items-center justify-center font-bold mt-1">{obj.num}</span>
                <input className={`${INP} flex-1`} value={obj.text}
                  placeholder={`Objective ${obj.num}…`}
                  onChange={e => setObjText(i, e.target.value)} />
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Department Strategies grid */}
        <SectionCard title="Department Strategy Mapping" subtitle="Per-department strategies mapped to company objectives">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="bg-gray-800/80">
                  <th className="px-3 py-2.5 text-left text-gray-400 border border-gray-700 font-semibold w-36">Department</th>
                  {(c.objectives || []).map(obj => (
                    <th key={obj.num} className="px-3 py-2.5 text-left border border-gray-700">
                      <span className="text-violet-400 font-bold">({obj.num})</span>
                      <span className="text-gray-400 ml-1.5">{obj.text || `Objective ${obj.num}`}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(c.departments || []).map((dept, di) => (
                  <tr key={di} className="border-b border-gray-800">
                    <td className="px-3 py-2 border border-gray-700 font-semibold text-gray-300 bg-gray-800/40">{dept.name}</td>
                    {(c.objectives || []).map((obj, oi) => {
                      const si = dept.strategies.findIndex(s => s.obj_num === obj.num);
                      return (
                        <td key={oi} className="border border-gray-700 p-1.5">
                          <textarea rows={2} className={TA}
                            value={si >= 0 ? dept.strategies[si].text : ""}
                            placeholder={`Strategy for objective (${obj.num})…`}
                            onChange={e => si >= 0 && setDeptStrat(di, si, e.target.value)} />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    </>
  );
}

/* ══ Strategy & Action Plan Panel ═══════════════════════════════════════════ */
function SPPanel({ year }) {
  const [docs,       setDocs]       = useState([]);
  const [activeDoc,  setActiveDoc]  = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [saved,      setSaved]      = useState(false);
  const [expanded,   setExpanded]   = useState({ 0: true, 1: false, 2: false });
  const [isNew,      setIsNew]      = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listBusinessPlans({ plan_year: year, doc_type: "strategy_plan" });
      if (res.success) setDocs(res.data);
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setActiveDoc(defaultSP(year)); setIsNew(true); setExpanded({ 0: true }); };
  const openDoc = (d) => { setActiveDoc(JSON.parse(JSON.stringify(d))); setIsNew(false); setExpanded({ 0: true }); };

  const setHeader = (k, v) => setActiveDoc(prev => ({ ...prev, [k]: v }));
  const setContent = (fn) => setActiveDoc(prev => ({ ...prev, content: fn(prev.content) }));

  const setObjText = (oi, field, val) => setContent(c => {
    const items = c.items.map((it, i) => i === oi ? { ...it, [field]: val } : it);
    return { ...c, items };
  });

  const addObj = () => setContent(c => ({
    ...c, items: [...c.items, { obj_num: c.items.length + 1, obj_text: "", strategies: [{ letter: "a", text: "", actions: [{ num: "i", text: "" }] }] }]
  }));

  const removeObj = (oi) => setContent(c => ({ ...c, items: c.items.filter((_, i) => i !== oi) }));

  const setStratText = (oi, si, val) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : {
      ...it,
      strategies: it.strategies.map((s, j) => j === si ? { ...s, text: val } : s),
    }),
  }));

  const addStrat = (oi) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : {
      ...it,
      strategies: [...it.strategies, { letter: ALPHA[it.strategies.length] || String.fromCharCode(97 + it.strategies.length), text: "", actions: [{ num: "i", text: "" }] }],
    }),
  }));

  const removeStrat = (oi, si) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : { ...it, strategies: it.strategies.filter((_, j) => j !== si) }),
  }));

  const setActionText = (oi, si, ai, val) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : {
      ...it,
      strategies: it.strategies.map((s, j) => j !== si ? s : {
        ...s, actions: s.actions.map((a, k) => k === ai ? { ...a, text: val } : a),
      }),
    }),
  }));

  const addAction = (oi, si) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : {
      ...it,
      strategies: it.strategies.map((s, j) => j !== si ? s : {
        ...s, actions: [...s.actions, { num: ROMAN[s.actions.length] || `${s.actions.length + 1}`, text: "" }],
      }),
    }),
  }));

  const removeAction = (oi, si, ai) => setContent(c => ({
    ...c, items: c.items.map((it, i) => i !== oi ? it : {
      ...it,
      strategies: it.strategies.map((s, j) => j !== si ? s : { ...s, actions: s.actions.filter((_, k) => k !== ai) }),
    }),
  }));

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertBusinessPlan({ ...activeDoc, plan_year: year });
      if (res.success) {
        setActiveDoc(res.data); setIsNew(false); setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        load();
      }
    } finally { setSaving(false); }
  };

  const deleteDoc = async (id) => {
    if (!window.confirm("Delete this document?")) return;
    await pacApi.deleteBusinessPlan(id);
    load();
    if (activeDoc?.id === id) setActiveDoc(null);
  };

  const print = () => window.print();

  return (
    <>
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          #bp-sp-print, #bp-sp-print * { visibility: visible !important; }
          #bp-sp-print { position: fixed; inset: 0; background: white; padding: 24px; font-family: Arial, sans-serif; font-size: 9.5pt; color: #000; }
          .no-print { display: none !important; }
        }
      `}</style>

      <div className="grid grid-cols-4 gap-4">
        {/* Left: document list */}
        <div className="col-span-1 space-y-2 no-print">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Documents {year}</p>
            <button onClick={openNew} className={BTN_SM("violet")}><Plus size={11} /> New</button>
          </div>
          {loading && <div className="text-xs text-gray-600 py-4 text-center"><Loader2 size={12} className="animate-spin inline mr-1" />Loading…</div>}
          {docs.length === 0 && !loading && (
            <p className="text-xs text-gray-600 text-center py-6">No documents yet.<br /><span className="text-violet-400 cursor-pointer underline" onClick={openNew}>Create one</span></p>
          )}
          {docs.map(d => (
            <button key={d.id} onClick={() => openDoc(d)}
              className={`w-full text-left px-3 py-2.5 rounded-lg border text-xs transition-all ${activeDoc?.id === d.id ? 'bg-violet-500/10 border-violet-500/40 text-violet-300' : 'bg-gray-900 border-gray-800 text-gray-400 hover:border-gray-700'}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-gray-200 truncate">{d.department || "(no dept)"}</span>
                <span className={`shrink-0 ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold ${d.status === 'final' ? 'bg-green-500/15 text-green-400' : 'bg-yellow-500/15 text-yellow-400'}`}>{d.status}</span>
              </div>
              <div className="text-gray-500 mt-0.5 truncate">{d.team_code ? `${d.team_code} / ` : ""}{d.team_name}</div>
            </button>
          ))}
        </div>

        {/* Right: editor */}
        <div className="col-span-3">
          {!activeDoc ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <FileText size={32} className="text-gray-700 mb-3" />
              <p className="text-gray-500 text-sm">Select a document or create a new one</p>
            </div>
          ) : (
            <>
              {/* Header controls */}
              <div className="flex items-center justify-between mb-4 no-print">
                <h3 className="text-sm font-semibold text-gray-200">
                  {isNew ? "New Strategy & Action Plan" : `Editing: ${activeDoc.department}`}
                </h3>
                <div className="flex gap-2">
                  <button onClick={() => setActiveDoc(prev => ({ ...prev, status: prev.status === 'final' ? 'draft' : 'final' }))}
                    className={BTN_SM(activeDoc.status === 'final' ? 'gray' : 'green')}>
                    <CheckCircle size={11} /> {activeDoc.status === 'final' ? 'Mark Draft' : 'Mark Final'}
                  </button>
                  <button onClick={save} disabled={saving} className={BTN_SM("violet")}>
                    {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                    {saved ? "Saved!" : "Save"}
                  </button>
                  {activeDoc.id && <button onClick={() => deleteDoc(activeDoc.id)} className={BTN_SM("red")}><Trash2 size={11} /></button>}
                  <button onClick={print} className={BTN_SM("gray")}><Printer size={11} /> Print</button>
                </div>
              </div>

              {/* Printable area */}
              <div id="bp-sp-print">
                {/* Print header */}
                <div className="hidden print:block mb-4 pb-3 border-b-2 border-gray-800">
                  <p className="font-bold text-sm">PT CKD OTTO Pharmaceuticals</p>
                  <p className="font-semibold">STRATEGY & ACTION PLAN {year}</p>
                  <div className="flex gap-8 mt-1 text-xs text-gray-600">
                    <span>Department: {activeDoc.department}</span>
                    <span>Team: {activeDoc.team_code} / {activeDoc.team_name}</span>
                    <span>Role: {activeDoc.plan_role}</span>
                  </div>
                </div>

                {/* Meta fields */}
                <SectionCard title="Document Header">
                  <div className="grid grid-cols-4 gap-3">
                    <Field label="Department">
                      <input className={`${INP} w-full`} value={activeDoc.department || ""} onChange={e => setHeader("department", e.target.value)} placeholder="e.g. Administration" />
                    </Field>
                    <Field label="Team Code">
                      <input className={`${INP} w-full`} value={activeDoc.team_code || ""} onChange={e => setHeader("team_code", e.target.value)} placeholder="e.g. 15" />
                    </Field>
                    <Field label="Team Name">
                      <input className={`${INP} w-full`} value={activeDoc.team_name || ""} onChange={e => setHeader("team_name", e.target.value)} placeholder="e.g. IT" />
                    </Field>
                    <Field label="Role / Function">
                      <input className={`${INP} w-full`} value={activeDoc.plan_role || ""} onChange={e => setHeader("plan_role", e.target.value)} placeholder="e.g. Planning & Coordination" />
                    </Field>
                  </div>
                </SectionCard>

                {/* Objectives */}
                {(activeDoc.content?.items || []).map((item, oi) => (
                  <div key={oi} className="rounded-xl border border-gray-800 bg-gray-900 mb-3 overflow-hidden">
                    {/* Objective header */}
                    <div className="flex items-center gap-3 px-4 py-3 bg-gray-800/50 cursor-pointer no-print"
                      onClick={() => setExpanded(prev => ({ ...prev, [oi]: !prev[oi] }))}>
                      {expanded[oi] ? <ChevronDown size={13} className="text-violet-400" /> : <ChevronRight size={13} className="text-violet-400" />}
                      <span className="w-6 h-6 rounded-full bg-violet-500/20 border border-violet-500/40 text-violet-400 text-xs flex items-center justify-center font-bold shrink-0">{item.obj_num}</span>
                      <input className={`${INP} flex-1 font-semibold`}
                        value={item.obj_text}
                        placeholder={`Managerial Objective ${item.obj_num}…`}
                        onChange={e => setObjText(oi, "obj_text", e.target.value)}
                        onClick={e => e.stopPropagation()} />
                      <button onClick={e => { e.stopPropagation(); removeObj(oi); }} className={`shrink-0 ${BTN_SM("red")}`}><Trash2 size={10} /></button>
                    </div>

                    {/* Print-only objective header */}
                    <div className="print:block hidden px-4 py-2 bg-gray-100">
                      <span className="font-bold">({item.obj_num}) {item.obj_text}</span>
                    </div>

                    {expanded[oi] && (
                      <div className="p-4 space-y-3">
                        {(item.strategies || []).map((strat, si) => (
                          <div key={si} className="rounded-lg border border-gray-700/50 bg-gray-800/30 p-3">
                            {/* Strategy row */}
                            <div className="flex items-start gap-2 mb-2">
                              <span className="shrink-0 w-5 text-xs font-bold text-amber-400 mt-2.5">({strat.letter})</span>
                              <textarea rows={2} className={`${TA} flex-1`}
                                value={strat.text}
                                placeholder={`Strategy (${strat.letter})…`}
                                onChange={e => setStratText(oi, si, e.target.value)} />
                              <button onClick={() => removeStrat(oi, si)} className={`shrink-0 mt-1.5 ${BTN_SM("red")}`}><Trash2 size={9} /></button>
                            </div>
                            {/* Action plans */}
                            <div className="ml-7 space-y-1.5">
                              {(strat.actions || []).map((act, ai) => (
                                <div key={ai} className="flex items-start gap-2">
                                  <span className="shrink-0 text-xs text-gray-500 w-6 text-right mt-2">({act.num})</span>
                                  <textarea rows={1} className={`${TA} flex-1`}
                                    value={act.text}
                                    placeholder={`Action plan (${act.num})…`}
                                    onChange={e => setActionText(oi, si, ai, e.target.value)} />
                                  <button onClick={() => removeAction(oi, si, ai)} className={`shrink-0 mt-1.5 ${BTN_SM("red")} no-print`}><X size={9} /></button>
                                </div>
                              ))}
                              <button onClick={() => addAction(oi, si)} className={`${BTN_SM("gray")} text-[10px] no-print`}><Plus size={9} /> Add Action</button>
                            </div>
                          </div>
                        ))}
                        <button onClick={() => addStrat(oi)} className={`${BTN_SM("violet")} text-[10px] no-print`}><Plus size={10} /> Add Strategy</button>
                      </div>
                    )}
                  </div>
                ))}

                <button onClick={addObj} className={`${BTN_SM("violet")} w-full justify-center no-print`}><Plus size={12} /> Add Objective</button>

                <p className="text-xs text-gray-600 mt-4 italic no-print">*) Action plan detail related to {year} KPI plan</p>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/* ══ Document History Panel ══════════════════════════════════════════════════ */
function BPHistoryPanel({ year }) {
  const [docs,    setDocs]    = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listBusinessPlans({ plan_year: year });
      if (res.success) setDocs(res.data);
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const deleteDoc = async (id) => {
    if (!window.confirm("Delete this document?")) return;
    await pacApi.deleteBusinessPlan(id);
    load();
  };

  const TH = { padding: "10px 12px", fontSize: 11, fontWeight: 600, color: "#9ca3af", textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" };
  const TD = { padding: "9px 12px", fontSize: 12 };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">{docs.length} document(s) for year {year}</p>
        <button onClick={load} className={BTN_SM("gray")}><RefreshCw size={11} /> Refresh</button>
      </div>
      <div className="rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr style={{ background: "rgba(55,65,81,0.6)" }}>
              {["Type","Year","Department","Team","Role","Status","Updated"].map((h, i) => (
                <th key={h} style={{ ...TH, textAlign: i >= 5 ? "center" : "left" }}>{h}</th>
              ))}
              <th style={TH} />
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} style={{ padding: "32px", textAlign: "center", color: "#6b7280", fontSize: 12 }}><Loader2 size={14} className="animate-spin inline mr-2" />Loading…</td></tr>}
            {!loading && docs.length === 0 && <tr><td colSpan={8} style={{ padding: "32px", textAlign: "center", color: "#6b7280", fontSize: 12 }}>No documents found</td></tr>}
            {docs.map((d, i) => (
              <tr key={d.id} style={{ borderTop: "1px solid rgba(55,65,81,0.5)" }} className="hover:bg-gray-800/30">
                <td style={{ ...TD }}>
                  <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: d.doc_type === 'managerial_obj' ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)', color: d.doc_type === 'managerial_obj' ? '#a78bfa' : '#60a5fa' }}>
                    {d.doc_type === 'managerial_obj' ? 'Managerial Obj' : 'Strategy Plan'}
                  </span>
                </td>
                <td style={{ ...TD, color: "#d1d5db", fontFamily: "monospace" }}>{d.plan_year}</td>
                <td style={{ ...TD, color: "#d1d5db", fontWeight: 600 }}>{d.department}</td>
                <td style={{ ...TD, color: "#9ca3af" }}>{d.team_code ? `${d.team_code} / ${d.team_name}` : d.team_name || "—"}</td>
                <td style={{ ...TD, color: "#9ca3af" }}>{d.plan_role || "—"}</td>
                <td style={{ ...TD, textAlign: "center" }}>
                  <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: d.status === 'final' ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)', color: d.status === 'final' ? '#4ade80' : '#facc15' }}>
                    {d.status}
                  </span>
                </td>
                <td style={{ ...TD, color: "#6b7280", textAlign: "center" }}>{d.updated_at ? new Date(d.updated_at).toLocaleDateString("id-ID") : "—"}</td>
                <td style={{ ...TD }}>
                  <button onClick={() => deleteDoc(d.id)} className={BTN_SM("red")} title="Delete"><Trash2 size={11} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══ Main BusinessPlanSection ════════════════════════════════════════════════ */
function BusinessPlanSection() {
  const [subTab, setSubTab]   = useState("managerial");
  const [year,   setYear]     = useState(CY_BP);

  return (
    <div className="space-y-4">
      {/* Sub-tab + year picker */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-gray-800/60 border border-gray-700">
          {BP_SUBTABS.map(t => (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                subTab === t.id
                  ? "bg-violet-500/20 border border-violet-500/40 text-violet-300"
                  : "text-gray-500 hover:text-gray-300"
              }`}>
              <t.icon size={11} />{t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Plan Year</label>
          <select value={year} onChange={e => setYear(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 rounded-md px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500/60">
            {[CY_BP-2, CY_BP-1, CY_BP, CY_BP+1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {/* Content */}
      {subTab === "managerial" && <SectionCard title="Managerial Objective" subtitle={`PT CKD OTTO Pharmaceuticals · ${year} Business Plan`}><MOPanel year={year} /></SectionCard>}
      {subTab === "strategy"   && <SectionCard title="Strategy & Action Plan" subtitle={`Per department · ${year} Business Plan`}><SPPanel year={year} /></SectionCard>}
      {subTab === "history"    && <SectionCard title="Document List" subtitle={`All Business Plan documents for ${year}`}><BPHistoryPanel year={year} /></SectionCard>}
      {subTab === "setup"      && <SetupSection year={year} />}
    </div>
  );
}

/* ─── Section: Budget Usage Report ──────────────── */
function BudgetUsageSection() {
  const [ledgers,  setLedgers]  = useState([]);
  const [f, setF] = useState({
    year: CY, month: "", cost_center: "", account_type: "", ledger_id: "",
  });
  const [loading,  setLoading]  = useState(false);
  const [searched, setSearched] = useState(false);
  const [rows,     setRows]     = useState([]);
  const [monthly,  setMonthly]  = useState([]);
  const [kpi,      setKpi]      = useState(null);
  const [error,    setError]    = useState("");
  const [page,     setPage]     = useState(1);
  const [chartMode, setChartMode] = useState("bar");  // "bar" | "line"

  useEffect(() => {
    pacApi.getLedgers().then(r => { if (r?.success) setLedgers(r.data ?? []); }).catch(() => {});
  }, []);

  const setFld = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));

  const handleSearch = async () => {
    setLoading(true); setError(""); setPage(1);
    try {
      const p = { year: f.year };
      if (f.month)        p.month        = f.month;
      if (f.cost_center)  p.cost_center  = f.cost_center;
      if (f.account_type) p.account_type = f.account_type;
      if (f.ledger_id)    p.ledger_id    = f.ledger_id;
      const r = await pacApi.getBudgetUsage(p);
      if (r?.success) {
        setRows(r.data || []);
        setMonthly(r.monthly || []);
        setKpi(r.kpi || null);
        setSearched(true);
      } else {
        setError(r?.error || "Request failed");
      }
    } catch (e) {
      setError(e?.detail || e?.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setF({ year: CY, month: "", cost_center: "", account_type: "", ledger_id: "" });
    setRows([]); setMonthly([]); setKpi(null); setSearched(false); setError(""); setPage(1);
  };

  const handleDownload = () => {
    const cols = ["Period","Cost Center Code","Cost Center","Account Code","Account","Type",
                  "Actual (IDR)","Budget (IDR)","Variance (IDR)","Absorption (%)"];
    const data = rows.map(r => {
      const actual   = Number(r.actual_amount) || 0;
      const budget   = Number(r.budget_amount) || 0;
      const variance = budget - actual;
      const abs_pct  = budget ? (actual / budget * 100).toFixed(1) : "—";
      return [r.period_name, r.cost_center_code, r.cost_center_name,
              r.account_code, r.account_name, r.account_type,
              actual, budget, variance, abs_pct];
    });
    const ws = XLSX.utils.aoa_to_sheet([cols, ...data]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Budget Usage");
    XLSX.writeFile(wb, `budget_usage_${f.year}${f.month ? "_M"+f.month : ""}.xlsx`);
  };

  // Pivot for cost-center summary (used in table detail)
  const paged = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const TH = { padding: "10px 12px", fontSize: 11, fontWeight: 600, color: "#9ca3af",
               textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" };
  const TD = { padding: "9px 12px", fontSize: 12, whiteSpace: "nowrap" };

  const absorptionColor = (pct) =>
    pct > 100 ? "#f87171" : pct >= 80 ? "#fbbf24" : "#34d399";

  const INPUT  = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-500/60";
  const SELECT = "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-green-500/60";

  return (
    <div className="space-y-4">
      {/* ── Filter ── */}
      <SectionCard
        title="Budget Usage Report — Actual vs Business Plan"
        subtitle="GL Balances from Oracle EBS · Actual (A) vs Budget (B)"
        action={
          <div className="flex gap-2">
            <ActionBtn icon={RefreshCw} label="Reset"  color="bg-gray-700 hover:bg-gray-600" onClick={handleReset} />
            <ActionBtn icon={loading ? Loader2 : Filter} label="Search" color="bg-green-600 hover:bg-green-700" onClick={handleSearch} />
          </div>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
          <Field label="Year *">
            <input className={INPUT} type="number" value={f.year} onChange={setFld("year")} min={2020} max={2030} />
          </Field>
          <Field label="Month">
            <select className={SELECT} value={f.month} onChange={setFld("month")}>
              <option value="">— All Months —</option>
              {MONTH_NAMES.slice(1).map((m, i) => (
                <option key={i+1} value={i+1}>{m}</option>
              ))}
            </select>
          </Field>
          <Field label="Cost Center">
            <input className={INPUT} value={f.cost_center} onChange={setFld("cost_center")} placeholder="partial search…" />
          </Field>
          <Field label="Account Type">
            <select className={SELECT} value={f.account_type} onChange={setFld("account_type")}>
              <option value="">— All —</option>
              <option value="E">Expense (E)</option>
              <option value="A">Asset (A)</option>
              <option value="L">Liability (L)</option>
              <option value="R">Revenue (R)</option>
              <option value="O">Owner Equity (O)</option>
            </select>
          </Field>
          <Field label="Ledger">
            <select className={SELECT} value={f.ledger_id} onChange={setFld("ledger_id")}>
              <option value="">— All Ledgers —</option>
              {ledgers.map(l => (
                <option key={l.ledger_id} value={l.ledger_id}>{l.ledger_name} ({l.currency_code})</option>
              ))}
            </select>
          </Field>
        </div>
        {error && (
          <div className="mt-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <X size={12} />{error}
          </div>
        )}
      </SectionCard>

      {loading && (
        <div className="flex items-center justify-center py-12 text-gray-500 text-sm gap-2">
          <Loader2 size={16} className="animate-spin" /> Loading from Oracle EBS GL…
        </div>
      )}

      {searched && !loading && (
        <>
          {/* ── KPI Cards ── */}
          {kpi && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Total Actual",    value: fmtB(kpi.total_actual),    color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20" },
                { label: "Total Budget",    value: fmtB(kpi.total_budget),    color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/20" },
                {
                  label: "Absorption",
                  value: kpi.absorption_pct + "%",
                  color: kpi.absorption_pct > 100 ? "text-red-400" : kpi.absorption_pct >= 80 ? "text-yellow-400" : "text-green-400",
                  bg: kpi.absorption_pct > 100 ? "bg-red-500/10" : "bg-yellow-500/10",
                  border: kpi.absorption_pct > 100 ? "border-red-500/20" : "border-yellow-500/20",
                },
                { label: "Remaining Budget", value: fmtB(kpi.variance),      color: kpi.variance < 0 ? "text-red-400" : "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
              ].map(k => (
                <div key={k.label} className={`rounded-lg border ${k.border} ${k.bg} px-4 py-3`}>
                  <p className="text-xs text-gray-500 mb-1">{k.label}</p>
                  <p className={`text-xl font-bold ${k.color}`}>{k.value}</p>
                </div>
              ))}
            </div>
          )}

          {/* ── Chart toggle ── */}
          {monthly.length > 0 && (
            <>
              <div className="flex gap-2">
                {[{ id: "bar", label: "Bar Chart" }, { id: "line", label: "Trend Line" }].map(m => (
                  <button key={m.id} onClick={() => setChartMode(m.id)}
                    className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
                      chartMode === m.id
                        ? "bg-green-500/10 border-green-500/40 text-green-400"
                        : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
                    }`}>{m.label}</button>
                ))}
              </div>

              <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
                <p className="text-xs text-gray-500 mb-3">
                  Monthly Budget vs Actual (IDR) — {f.year}
                </p>
                <ResponsiveContainer width="100%" height={300}>
                  {chartMode === "bar" ? (
                    <BarChart data={monthly} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                      <XAxis dataKey="period_name" tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <YAxis tickFormatter={fmtShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                        formatter={(v, name) => [fmtIDR(v), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                      <Bar dataKey="budget" name="Budget (BP)" fill="#3b82f6" radius={[4,4,0,0]} opacity={0.7} />
                      <Bar dataKey="actual" name="Actual"      fill="#34d399" radius={[4,4,0,0]} />
                    </BarChart>
                  ) : (
                    <LineChart data={monthly} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                      <XAxis dataKey="period_name" tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <YAxis tickFormatter={fmtShort} tick={{ fill: "#6b7280", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 8, fontSize: 12, color: "#1e293b", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                        formatter={(v, name) => [fmtIDR(v), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                      <Line type="monotone" dataKey="budget" name="Budget (BP)" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="actual" name="Actual"      stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    </LineChart>
                  )}
                </ResponsiveContainer>

                {/* Absorption mini-table per month */}
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-xs">
                    <tbody>
                      <tr>
                        <td style={{ padding: "4px 8px", color: "#6b7280", whiteSpace: "nowrap" }}>Absorption %</td>
                        {monthly.map(m => (
                          <td key={m.period_name} style={{ padding: "4px 8px", textAlign: "center", whiteSpace: "nowrap",
                            fontWeight: 600, color: absorptionColor(m.absorption) }}>
                            {m.absorption}%
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* ── Detail Table ── */}
          <div className="rounded-lg border border-gray-800 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800 bg-gray-900/50">
              <span className="text-xs text-gray-500">{rows.length} rows</span>
              {rows.length > 0 && (
                <button onClick={handleDownload}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-green-400 border border-green-500/30 bg-green-500/10 hover:bg-green-500/20 transition-colors">
                  <Download size={12} /> Download Excel
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ background: "rgba(55,65,81,0.6)" }}>
                    {["Period","Cost Center","Account","Type","Actual (IDR)","Budget (IDR)","Variance","Absorption"].map((h, i) => (
                      <th key={h} style={{ ...TH, textAlign: i >= 4 ? "right" : "left" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={8} style={{ padding: "40px 12px", textAlign: "center", color: "#6b7280", fontSize: 12 }}>No data found</td></tr>
                  ) : paged.map((r, i) => {
                    const actual   = Number(r.actual_amount)  || 0;
                    const budget   = Number(r.budget_amount)  || 0;
                    const variance = budget - actual;
                    const absPct   = budget ? (actual / budget * 100) : 0;
                    return (
                      <tr key={i} style={{ borderTop: "1px solid rgba(55,65,81,0.5)" }}
                        className="hover:bg-gray-800/30 transition-colors">
                        <td style={{ ...TD, color: "#9ca3af" }}>{r.period_name}</td>
                        <td style={{ ...TD, color: "#d1d5db" }}>
                          <span style={{ fontFamily: "monospace", color: "#60a5fa", marginRight: 6 }}>{r.cost_center_code}</span>
                          {r.cost_center_name !== r.cost_center_code ? r.cost_center_name : ""}
                        </td>
                        <td style={{ ...TD, color: "#d1d5db" }}>
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#a78bfa", marginRight: 6 }}>{r.account_code}</span>
                          <span style={{ color: "#9ca3af" }}>{r.account_name}</span>
                        </td>
                        <td style={{ ...TD }}>
                          <span style={{ padding: "2px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                            background: r.account_type === "E" ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)",
                            color: r.account_type === "E" ? "#f87171" : "#60a5fa" }}>
                            {r.account_type}
                          </span>
                        </td>
                        <td style={{ ...TD, textAlign: "right", color: "#34d399", fontWeight: 500 }}>{fmtIDR(actual)}</td>
                        <td style={{ ...TD, textAlign: "right", color: "#60a5fa" }}>{fmtIDR(budget)}</td>
                        <td style={{ ...TD, textAlign: "right", color: variance < 0 ? "#f87171" : "#9ca3af", fontWeight: 500 }}>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            {variance < 0
                              ? <TrendingUp size={11} color="#f87171" />
                              : variance > 0
                                ? <TrendingDown size={11} color="#6b7280" />
                                : <Minus size={11} color="#6b7280" />}
                            {fmtIDR(Math.abs(variance))}
                          </span>
                        </td>
                        <td style={{ ...TD, textAlign: "right" }}>
                          <span style={{ fontWeight: 600, color: absorptionColor(absPct) }}>
                            {budget ? absPct.toFixed(1) + "%" : "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {rows.length > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-800 bg-gray-900/50">
                <span className="text-xs text-gray-500">
                  {(page-1)*PAGE_SIZE+1}–{Math.min(page*PAGE_SIZE, rows.length)} of {rows.length}
                </span>
                <div className="flex gap-1">
                  <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}
                    className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 disabled:opacity-30">‹ Prev</button>
                  <button onClick={() => setPage(p => Math.min(Math.ceil(rows.length/PAGE_SIZE), p+1))}
                    disabled={page >= Math.ceil(rows.length/PAGE_SIZE)}
                    className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 disabled:opacity-30">Next ›</button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Section: MT940 ─────────────────────────────── */
function MT940Section() {
  return (
    <SectionCard title="BCA MT940 Upload"
      action={
        <a href="/apps/MT940_upload"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors">
          <ExternalLink size={13} /> Open App
        </a>
      }>
      <div className="grid grid-cols-3 gap-4 mb-5">
        <MetricCard label="Total Files"  value="—" gradient="from-indigo-500 to-purple-600" />
        <MetricCard label="Generated"    value="—" gradient="from-cyan-500 to-teal-500" />
        <MetricCard label="Not Found"    value="—" gradient="from-rose-500 to-pink-600" />
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800/60">
              {["File Name","Size","Generated At","Status"].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr><td colSpan={4} className="px-3 py-10 text-center text-xs text-gray-600">No data</td></tr>
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

/* ─── Shared UI ──────────────────────────────────── */
function SectionCard({ title, subtitle, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color, onClick }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors ${color}`}>
      <Icon size={13} />{label}
    </button>
  );
}

function Field({ label, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-gray-500">{label}</label>
      {children}
    </div>
  );
}

function MetricCard({ label, value, gradient }) {
  return (
    <div className={`rounded-xl bg-gradient-to-br ${gradient} p-5 text-white text-center`}>
      <p className="text-xs opacity-80 mb-2">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   EXCHANGE RATE — Bank Indonesia Kurs Transaksi
   ══════════════════════════════════════════════════ */

const FEATURED_CODES = ["USD", "EUR", "SGD", "JPY", "GBP", "AUD", "CNY", "MYR"];

// Color badges per currency (no emoji — works on all platforms incl. Windows)
const CC_BG = {
  USD:"#1a56db", EUR:"#1c3fa8", SGD:"#c8102e", JPY:"#bc002d",
  GBP:"#c8102e", AUD:"#005aa3", CNY:"#de2910", MYR:"#cc0001",
  HKD:"#ba0c2f", CHF:"#d52b1e", CAD:"#d52b1e", AED:"#00732f",
  BND:"#0d6e3a", KRW:"#003087", KWD:"#007a3d", SAR:"#006c35",
  THB:"#00247d", PHP:"#0038a8", NOK:"#ef2b2d", SEK:"#006aa7",
  DKK:"#c60c30", NZD:"#00247d", CNH:"#c41e3a", PGK:"#ce1126",
  LAK:"#ce1126", VND:"#da251d",
};

function CurrencyBadge({ code, size = 36 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      background: CC_BG[code] || "#374151", flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <span style={{ color: "#fff", fontSize: Math.round(size * 0.3), fontWeight: 700, letterSpacing: 0.3 }}>
        {code.slice(0, 2)}
      </span>
    </div>
  );
}

/* ── Oracle EBS Push Dialog ─────────────────────────────────────────────── */
const EBS_CURRENCIES = ["USD", "EUR", "SGD", "JPY", "GBP", "AUD", "CNY", "MYR",
                        "HKD", "CHF", "CAD", "AED", "SAR", "THB", "MYR", "PHP",
                        "NOK", "SEK", "DKK", "NZD", "KRW"];
const UNIQUE_EBS_CCY = [...new Set(EBS_CURRENCIES)];

function PushToEBSDialog({ rates, onClose }) {
  const today = new Date().toISOString().slice(0, 10);
  const [rateDate,   setRateDate]   = useState(today);
  const [rateType,   setRateType]   = useState("Corporate");
  const [rateSource, setRateSource] = useState("tengah");
  const [selected,   setSelected]   = useState(["USD", "EUR", "SGD", "JPY", "GBP", "AUD", "CNY", "MYR"]);
  const [pushing,    setPushing]     = useState(false);
  const [results,    setResults]     = useState(null);

  const rateMap = Object.fromEntries(rates.map(r => [r.code, r]));

  const toggleCcy = (code) =>
    setSelected(s => s.includes(code) ? s.filter(c => c !== code) : [...s, code]);

  const getDisplayRate = (code) => {
    const r = rateMap[code];
    if (!r) return null;
    const denom = r.denomination || 1;
    let val;
    if (rateSource === "jual")   val = r.sell;
    else if (rateSource === "beli") val = r.buy;
    else val = r.sell && r.buy ? (r.sell + r.buy) / 2 : (r.sell || r.buy);
    if (!val) return null;
    return denom > 1 ? val / denom : val;
  };

  const handlePush = async () => {
    setPushing(true);
    setResults(null);
    try {
      const res = await pacApi.pushExchangeRatesToEBS({
        rate_date:   rateDate,
        rate_type:   rateType,
        rate_source: rateSource,
        currencies:  selected,
      });
      setResults(res.data);
    } catch (e) {
      setResults({ success: false, error: e.response?.data?.detail || "Gagal terhubung ke server", results: [] });
    } finally {
      setPushing(false);
    }
  };

  const fmtR = (n) => n == null ? "—"
    : Number(n).toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-2xl border border-gray-700 bg-gray-900 shadow-2xl overflow-hidden"
           onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-900/80">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-500/15 border border-red-500/30">
              <Upload size={16} className="text-red-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-sm">Push Kurs ke Oracle EBS</h3>
              <p className="text-gray-500 text-xs">GL_DAILY_RATES_API — GL Daily Rates</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
          {!results ? (
            <>
              {/* Config row */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-gray-400 mb-1.5 block">Tanggal Kurs</label>
                  <input type="date" value={rateDate} onChange={e => setRateDate(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-amber-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1.5 block">Rate Type</label>
                  <select value={rateType} onChange={e => setRateType(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-amber-500/50 focus:outline-none">
                    <option value="Corporate">Corporate</option>
                    <option value="Spot">Spot</option>
                    <option value="User">User</option>
                    <option value="EMU Fixed">EMU Fixed</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1.5 block">Sumber Rate BI</label>
                  <select value={rateSource} onChange={e => setRateSource(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-amber-500/50 focus:outline-none">
                    <option value="tengah">Tengah (Rata-rata Jual+Beli)</option>
                    <option value="jual">Kurs Jual</option>
                    <option value="beli">Kurs Beli</option>
                  </select>
                </div>
              </div>

              {/* Currency selection */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-gray-400">Mata Uang yang akan di-push ({selected.length} dipilih)</label>
                  <div className="flex gap-2">
                    <button onClick={() => setSelected(UNIQUE_EBS_CCY.filter(c => rateMap[c]))}
                      className="text-xs text-amber-400 hover:text-amber-300">Pilih Semua</button>
                    <span className="text-gray-700">·</span>
                    <button onClick={() => setSelected([])}
                      className="text-xs text-gray-500 hover:text-gray-400">Hapus Semua</button>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  {UNIQUE_EBS_CCY.filter(c => rateMap[c]).map(code => {
                    const r    = rateMap[code];
                    const val  = getDisplayRate(code);
                    const isOn = selected.includes(code);
                    return (
                      <button key={code} onClick={() => toggleCcy(code)}
                        className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors ${
                          isOn
                            ? "border-amber-500/50 bg-amber-500/10 text-white"
                            : "border-gray-800 bg-gray-800/50 text-gray-500 hover:border-gray-700"
                        }`}>
                        <div className="flex items-center gap-2">
                          <CurrencyBadge code={code} size={20} />
                          <span className="text-xs font-mono font-semibold">{code}</span>
                          {r.denomination > 1 && (
                            <span className="text-[9px] text-amber-500/70">/{r.denomination}</span>
                          )}
                        </div>
                        <span className="text-[10px] font-mono text-gray-400">
                          {val ? Number(val).toLocaleString("id-ID", {maximumFractionDigits: 2}) : "—"}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Note */}
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-amber-400/80 flex gap-2">
                <AlertCircle size={13} className="shrink-0 mt-0.5" />
                <span>
                  Proses ini akan INSERT atau UPDATE GL Daily Rates di Oracle EBS untuk tanggal <strong>{rateDate}</strong>.
                  Rate yang sudah ada akan di-UPDATE secara otomatis.
                </span>
              </div>

              {/* Action */}
              <div className="flex justify-end gap-3">
                <button onClick={onClose}
                  className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 hover:text-white hover:border-gray-600 transition-colors">
                  Batal
                </button>
                <button onClick={handlePush} disabled={pushing || selected.length === 0}
                  className="flex items-center gap-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 px-4 py-2 text-sm text-white font-medium transition-colors">
                  {pushing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  {pushing ? "Mengirim ke EBS…" : `Push ${selected.length} Mata Uang ke Oracle EBS`}
                </button>
              </div>
            </>
          ) : (
            /* Results */
            <div className="space-y-4">
              <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${
                results.success
                  ? "border-green-500/30 bg-green-500/10"
                  : results.error_count > 0
                    ? "border-red-500/30 bg-red-500/10"
                    : "border-gray-700 bg-gray-800"
              }`}>
                {results.success
                  ? <CheckCircle size={18} className="text-green-400 shrink-0" />
                  : results.error_count > 0
                    ? <AlertCircle size={18} className="text-red-400 shrink-0" />
                    : <AlertCircle size={18} className="text-gray-400 shrink-0" />
                }
                <div>
                  {results.error && (
                    <p className="text-sm text-red-300">{results.error}</p>
                  )}
                  {results.success_count !== undefined && (
                    <p className="text-sm text-white">
                      Berhasil: <span className="text-green-400 font-semibold">{results.success_count}</span>
                      {results.error_count > 0 && (
                        <span className="ml-2">Gagal: <span className="text-red-400 font-semibold">{results.error_count}</span></span>
                      )}
                    </p>
                  )}
                  {results.rate_date && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      Tanggal: {results.rate_date} · Rate Type: {results.rate_type}
                    </p>
                  )}
                </div>
              </div>

              {(results.results || []).length > 0 && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      {["Kode", "Action", "Rate (IDR)", "Status", "Keterangan"].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-xs text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(results.results || []).map(r => (
                      <tr key={r.code} className="border-b border-gray-800/50">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <CurrencyBadge code={r.code} size={20} />
                            <span className="font-mono font-semibold text-xs text-white">{r.code}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            r.action === "inserted" ? "bg-green-500/20 text-green-400" :
                            r.action === "updated"  ? "bg-blue-500/20 text-blue-400" :
                            r.action === "failed"   ? "bg-red-500/20 text-red-400" :
                                                      "bg-gray-700 text-gray-400"
                          }`}>{r.action ?? r.status}</span>
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-gray-300">
                          {r.rate != null ? fmtR(r.rate) : "—"}
                        </td>
                        <td className="px-3 py-2">
                          {r.status === "success"
                            ? <CheckCircle size={13} className="text-green-400" />
                            : r.status === "skipped"
                              ? <span className="text-xs text-gray-500">skip</span>
                              : <AlertCircle size={13} className="text-red-400" />
                          }
                        </td>
                        <td className="px-3 py-2 text-[10px] text-gray-500 max-w-[200px] truncate">
                          {r.reason || r.error || ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div className="flex justify-end gap-3">
                <button onClick={() => setResults(null)}
                  className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
                  ← Kembali
                </button>
                <button onClick={onClose}
                  className="rounded-lg bg-gray-700 hover:bg-gray-600 px-4 py-2 text-sm text-white transition-colors">
                  Tutup
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ExchangeRateSection() {
  const [data,       setData]       = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);
  const [showPushDlg, setShowPushDlg] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await pacApi.getExchangeRates(refresh);
      setData(res.data);
      if (res.data?.error) setError(res.data.error);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data kurs dari Bank Indonesia");
    } finally {
      setLoading(false);
    }
  }, []);


  useEffect(() => { load(); }, [load]);

  const ratesMap = Object.fromEntries((data?.rates ?? []).map(r => [r.code, r]));
  const allRates = data?.rates ?? [];

  const fmtRate = (n) =>
    n == null ? "—" : Number(n).toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const fmtTs = (iso) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString("id-ID", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta",
      }) + " WIB";
    } catch { return iso; }
  };

  return (
    <div className="space-y-5">
      {/* ── Push Dialog ───────────────────────────────────── */}
      {showPushDlg && allRates.length > 0 && (
        <PushToEBSDialog rates={allRates} onClose={() => setShowPushDlg(false)} />
      )}

      {/* ── Header ───────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-white font-semibold text-base flex items-center gap-2">
            <Globe size={16} className="text-amber-400" />
            Kurs Transaksi Bank Indonesia
          </h2>
          <p className="text-gray-400 text-xs mt-1">
            {loading
              ? "Mengambil data dari Bank Indonesia…"
              : data?.date
                ? `Tanggal kurs: ${data.date}`
                : "Tanggal tidak tersedia"
            }
            {!loading && fmtTs(data?.cached_at) && (
              <span className="ml-2 text-gray-600">
                · Diperbarui: {fmtTs(data.cached_at)}
                {data?.from_cache && <span className="ml-1 text-amber-500/60">(cache)</span>}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {allRates.length > 0 && (
            <button
              onClick={() => setShowPushDlg(true)}
              className="flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/20 transition-colors whitespace-nowrap"
            >
              <Upload size={13} />
              Push ke Oracle EBS
            </button>
          )}
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-500/20 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Error Banner ── */}
      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300 flex items-start gap-2">
          <span className="text-red-400 mt-0.5 shrink-0">⚠</span>
          <div>
            <span className="font-medium">Gagal mengambil data:</span> {error}
            {allRates.length > 0 && (
              <span className="block text-xs text-red-400/70 mt-1">Menampilkan data cache terakhir.</span>
            )}
          </div>
        </div>
      )}

      {/* ── Featured Cards ────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {FEATURED_CODES.map((code) => {
          const r = ratesMap[code];
          return (
            <div key={code}
              className="rounded-xl border border-gray-800 bg-gray-900 p-4 flex flex-col gap-3">
              {/* Badge + name */}
              <div className="flex items-center gap-3">
                <CurrencyBadge code={code} size={38} />
                <div className="min-w-0">
                  <div className="text-white font-bold text-sm leading-tight">{code}</div>
                  <div className="text-gray-500 text-[10px] leading-tight truncate">
                    {r?.name ?? code}
                    {r?.denomination > 1 && (
                      <span className="ml-1 text-amber-500/80">per {r.denomination}</span>
                    )}
                  </div>
                </div>
              </div>
              {/* Rates / Skeleton */}
              {loading ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-3 bg-gray-700/80 rounded w-full" />
                  <div className="h-3 bg-gray-700/60 rounded w-4/5" />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500 text-xs">Jual</span>
                    <span className="text-red-400 font-mono text-xs font-semibold">
                      {fmtRate(r?.sell)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500 text-xs">Beli</span>
                    <span className="text-green-400 font-mono text-xs font-semibold">
                      {fmtRate(r?.buy)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Full Table ────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <span className="text-gray-300 text-sm font-medium">Semua Kurs Transaksi BI</span>
          <span className="text-gray-500 text-xs">
            {loading ? "memuat…" : `${allRates.length} mata uang`}
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-gray-500">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Mengambil data dari Bank Indonesia…</span>
          </div>
        ) : allRates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-gray-600">
            <Globe size={32} className="opacity-30" />
            <span className="text-sm">Tidak ada data kurs tersedia</span>
            <button onClick={() => load(true)}
              className="mt-1 text-xs text-amber-400 hover:text-amber-300 transition-colors">
              Coba lagi
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {["Mata Uang", "Nama", "Nilai", "Kurs Jual (IDR)", "Kurs Beli (IDR)"].map(h => (
                    <th key={h}
                      className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 bg-gray-900/80 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allRates.map((r, i) => {
                  const isFeatured = FEATURED_CODES.includes(r.code);
                  return (
                    <tr key={r.code}
                      className={`border-b border-gray-800/50 transition-colors hover:bg-gray-800/40 ${
                        isFeatured ? "bg-amber-500/5" : i % 2 === 0 ? "" : "bg-gray-800/20"
                      }`}
                    >
                      <td className="px-4 py-2.5 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <CurrencyBadge code={r.code} size={24} />
                          <span className={`font-mono font-semibold text-sm ${isFeatured ? "text-amber-300" : "text-white"}`}>
                            {r.code}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs">{r.name}</td>
                      <td className="px-4 py-2.5 text-center">
                        {r.denomination > 1
                          ? <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-400 font-mono">{r.denomination}</span>
                          : <span className="text-gray-600 text-xs">1</span>
                        }
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-red-400 font-medium">
                        {fmtRate(r.sell)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-green-400 font-medium">
                        {fmtRate(r.buy)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="px-4 py-2.5 border-t border-gray-800 bg-gray-900/50 flex items-center justify-between">
          <span className="text-gray-600 text-xs">
            Sumber: Bank Indonesia — Kurs Transaksi BI (diperbarui setiap hari kerja)
          </span>
          <a
            href="https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-amber-400/70 hover:text-amber-400 transition-colors"
          >
            Lihat di BI <ExternalLink size={10} />
          </a>
        </div>
      </div>
    </div>
  );
}


/* ══════════════════════════════════════════════════
   SETUP MODULES
   ══════════════════════════════════════════════════ */
const SETUP_SUBTABS = [
  { id: "schedule",  label: "Schedule",   icon: Calendar,      color: "text-sky-400",   bg: "bg-sky-500/10",    activeBorder: "border-sky-500/40" },
  { id: "guideline", label: "Guideline",  icon: BookOpenCheck, color: "text-teal-400",  bg: "bg-teal-500/10",   activeBorder: "border-teal-500/40" },
  { id: "outlook",   label: "Outlook",    icon: Globe,         color: "text-indigo-400", bg: "bg-indigo-500/10", activeBorder: "border-indigo-500/40" },
];

function SetupSection({ year }) {
  const [subTab, setSubTab] = useState("schedule");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-gray-800/60 border border-gray-700">
          {SETUP_SUBTABS.map(t => (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                subTab === t.id ? `${t.bg} ${t.activeBorder} ${t.color}` : "text-gray-500 hover:text-gray-300"
              }`}>
              <t.icon size={11} />{t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Plan Year: <span className="text-sky-400 font-bold">{year}</span></label>
        </div>
      </div>
      {subTab === "schedule"  && <SchedulePanel year={year} />}
      {subTab === "guideline" && <GuidelinePanel year={year} />}
      {subTab === "outlook"   && <OutlookPanel year={year} />}
    </div>
  );
}

/* ══ Schedule Panel ═══════════════════════════════════════════════════════════ */

const DEFAULT_SCHEDULE = {
  subtitle: "Timeline of {year} Business Plan",
  activities: [
    { no: 1, activity: "Notification of {year} business plan timeline", date: "Sep 22", day: "Friday", sales: "x", development: "x", plant: "x", admin: "x", director: "ok", remarks: "Timeline" },
    { no: 2, activity: "Distribution of all relevant templates", date: "Sep 29", day: "Friday", sales: "x", development: "x", plant: "x", admin: "x", director: "ok", remarks: "CS" },
    { no: 3, activity: "{year} economic outlook & guideline", date: "Sep 29", day: "Friday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "Outlook Report" },
    { no: 4, activity: "Review & discuss financial template with Company", date: "Sep 30", day: "Sunday", sales: "F", development: "F", plant: "F", admin: "F", director: "x", remarks: "Finance Team" },
    { no: 5, activity: "Prepare sales plan & strategic direction", date: "Oct 1", day: "Tuesday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "Business Plan" },
    { no: 6, activity: "Business development plan : CMO, export and others", date: "Oct 25-29", day: "Tue-Thu", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "81, 82" },
    { no: 7, activity: "Sales plan {year} : by department, product & area", date: "Oct 25", day: "Wednesday", sales: "x", development: "$1, 52", plant: "x", admin: "x", director: "x", remarks: "Sales Plan" },
    { no: 8, activity: "Starting sales plan with Stakeholders / HO review", date: "Oct 28", day: "Monday", sales: "x", development: "x", plant: "x", admin: "x", director: "Petey", remarks: "Petey" },
    { no: 9, activity: "Purchase plan", date: "Nov 1", day: "Friday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "Purchase" },
    { no: 10, activity: "Reduction / manufacturing plan", date: "Nov 12", day: "Tuesday", sales: "x", development: "x", plant: "x", admin: "Now 14", director: "x", remarks: "Plant" },
    { no: 11, activity: "Data evaluation : production, personnel, purchase, inventory, opex budget plan", date: "Nov 23-24", day: "Thu-Fri", sales: "x", development: "x", plant: "x", admin: "x", director: "Now 23", remarks: "Budget Meeting" },
    { no: 12, activity: "Forecasting : profit and loss simulation", date: "Nov 24", day: "Thursday", sales: "x", development: "x", plant: "x", admin: "Now 24", director: "x", remarks: "Finance" },
    { no: 13, activity: "Final Budget decision", date: "Dec 6", day: "Wednesday", sales: "x", development: "x", plant: "x", admin: "x", director: "Dec 6", remarks: "Final" },
    { no: 14, activity: "{year} Cashflow forecasting", date: "Dec 6", day: "Wednesday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "Cashflow" },
    { no: 15, activity: "{year} Business plan report", date: "Dec 12", day: "Wednesday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "Report" },
    { no: 16, activity: "Reporting business plan {year} to President Director", date: "Dec 12", day: "Wednesday", sales: "x", development: "x", plant: "x", admin: "x", director: "x", remarks: "President Director" },
  ],
};

const SCHEDULE_COLUMNS = [
  { key: "no", label: "No", width: "w-10", align: "center" },
  { key: "activity", label: "Activity Description", width: "flex-1 min-w-[280px]", align: "left" },
  { key: "date", label: "Submission Date", width: "w-28", align: "center" },
  { key: "day", label: "Day", width: "w-20", align: "center" },
  { key: "sales", label: "Sales & Mkt", width: "w-16", align: "center" },
  { key: "development", label: "Strategic Dev", width: "w-20", align: "center" },
  { key: "plant", label: "Plant", width: "w-16", align: "center" },
  { key: "admin", label: "Admin", width: "w-16", align: "center" },
  { key: "director", label: "P. Director", width: "w-20", align: "center" },
  { key: "remarks", label: "Remarks", width: "w-28", align: "center" },
];

function SchedulePanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSetupModules({ setup_module: "schedule", plan_year: year });
      if (res.success && res.data.length > 0) {
        setData(res.data[0]);
      } else {
        const content = JSON.parse(JSON.stringify(DEFAULT_SCHEDULE));
        content.activities = content.activities.map(a => Object.assign({}, a, { activity: a.activity.replace("{year}", year), remarks: String(a.remarks) }));
        setData({ setup_module: "schedule", plan_year: year, content, status: "draft" });
      }
    } catch {
      const content = JSON.parse(JSON.stringify(DEFAULT_SCHEDULE));
      content.activities = content.activities.map(a => Object.assign({}, a, { activity: a.activity.replace("{year}", year), remarks: String(a.remarks) }));
      setData({ setup_module: "schedule", plan_year: year, content, status: "draft" });
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const updateActivity = (idx, field, val) => {
    setData(prev => ({
      ...prev,
      content: {
        ...prev.content,
        activities: prev.content.activities.map((a, i) => i === idx ? Object.assign({}, a, { [field]: val }) : a),
      },
    }));
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = Object.assign({}, data, { setup_module: "schedule", plan_year: year });
      const res = await pacApi.upsertSetupModule(payload);
      if (res.success) { setData(res.data); setSaved(true); setTimeout(() => setSaved(false), 2000); }
    } finally { setSaving(false); }
  };

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!data) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Business Plan Schedule</h3>
          <p className="text-xs text-gray-500 mt-0.5">Timeline & Schedule · {year}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setData(prev => Object.assign({}, prev, { status: prev.status === 'final' ? 'draft' : 'final' }))}
            className={BTN_SM(data.status === 'final' ? 'gray' : 'green')}>
            <CheckCircle size={11} /> {data.status === 'final' ? 'Mark Draft' : 'Mark Final'}
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("sky")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-800/80">
              {SCHEDULE_COLUMNS.map(col => (
                <th key={col.key} className={`${col.width} px-3 py-2.5 text-left text-gray-400 border border-gray-700 font-semibold whitespace-nowrap ${col.align === 'center' ? 'text-center' : ''}`}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.content.activities || []).map((act, i) => (
              <tr key={i} className={`border-b border-gray-800 transition-colors ${i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-900/40'} hover:bg-gray-800/50`}>
                <td className="px-3 py-2 border border-gray-700 text-center font-bold text-gray-400">{act.no}</td>
                <td className="px-3 py-2 border border-gray-700">
                  <textarea rows={1} className={`${TA} !py-1.5 !text-xs w-full`} value={act.activity} onChange={e => updateActivity(i, "activity", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.date} onChange={e => updateActivity(i, "date", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.day} onChange={e => updateActivity(i, "day", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.sales} onChange={e => updateActivity(i, "sales", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.development} onChange={e => updateActivity(i, "development", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.plant} onChange={e => updateActivity(i, "plant", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.admin} onChange={e => updateActivity(i, "admin", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.director} onChange={e => updateActivity(i, "director", e.target.value)} />
                </td>
                <td className="px-3 py-2 border border-gray-700 text-center">
                  <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.remarks} onChange={e => updateActivity(i, "remarks", e.target.value)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══ Guideline Panel ══════════════════════════════════════════════════════════ */

const DEFAULT_GUIDELINE = {
  sections: [
    {
      title: "1. Working Days",
      icon: "📅",
      items: [
        { label: "Jan", value: 22 }, { label: "Feb", value: 20 }, { label: "Mar", value: 23 },
        { label: "Apr", value: 21 }, { label: "May", value: 22 }, { label: "Jun", value: 20 },
        { label: "Jul", value: 23 }, { label: "Aug", value: 21 }, { label: "Sep", value: 21 },
        { label: "Oct", value: 23 }, { label: "Nov", value: 19 }, { label: "Dec", value: 20 },
      ],
    },
    {
      title: "2. Economic Indicator for Budgeting",
      icon: "📊",
      items: [
        { label: "Exchange Rate (IDR/USD)", value: "15,100 - 15,200" },
        { label: "Minimum Salary (UMR)", value: "Rp 5,000,000" },
        { label: "Inflation", value: "2.5% - 3.0%" },
      ],
    },
    {
      title: "3. Meeting & Business Trip",
      icon: "✈️",
      items: [
        { label: "Domestic — Director", value: "Rp 800,000 / day" },
        { label: "Domestic — General Manager", value: "Rp 700,000 / day" },
        { label: "Domestic — Senior Manager", value: "Rp 600,000 / day" },
        { label: "Domestic — Manager", value: "Rp 500,000 / day" },
        { label: "Domestic — Staff", value: "Rp 400,000 / day" },
        { label: "International — Director", value: "$300 / day" },
        { label: "International — Manager", value: "$200 / day" },
        { label: "International — Staff", value: "$150 / day" },
      ],
    },
  ],
};

function GuidelinePanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSetupModules({ setup_module: "guideline", plan_year: year });
      if (res.success && res.data.length > 0) setData(res.data[0]);
      else setData({ setup_module: "guideline", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_GUIDELINE)), status: "draft" });
    } catch {
      setData({ setup_module: "guideline", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_GUIDELINE)), status: "draft" });
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const updateItem = (secIdx, itemIdx, field, val) => {
    setData(prev => {
      if (!prev) return prev;
      return Object.assign({}, prev, {
        content: Object.assign({}, prev.content, {
          sections: prev.content.sections.map((s, si) =>
            si === secIdx ? Object.assign({}, s, { items: s.items.map((it, ii) => ii === itemIdx ? Object.assign({}, it, { [field]: val }) : it) }) : s
          ),
        }),
      });
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = Object.assign({}, data, { setup_module: "guideline", plan_year: year });
      const res = await pacApi.upsertSetupModule(payload);
      if (res.success) { setData(res.data); setSaved(true); setTimeout(() => setSaved(false), 2000); }
    } finally { setSaving(false); }
  };

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!data) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Business Plan Guideline</h3>
          <p className="text-xs text-gray-500 mt-0.5">Guidelines & Parameters · {year}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setData(prev => prev ? Object.assign({}, prev, { status: prev.status === 'final' ? 'draft' : 'final' }) : prev)}
            className={BTN_SM(data.status === 'final' ? 'gray' : 'green')}>
            <CheckCircle size={11} /> {data.status === 'final' ? 'Mark Draft' : 'Mark Final'}
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("teal")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>
      <div className="p-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(data.content.sections || []).map((section, si) => (
            <div key={si} className="rounded-xl border border-gray-700/60 bg-gray-800/40 overflow-hidden">
              <div className="px-4 py-3 bg-gray-800/60 border-b border-gray-700 flex items-center gap-2">
                <span className="text-lg">{section.icon}</span>
                <span className="text-xs font-bold text-teal-400 uppercase tracking-wider">{section.title}</span>
              </div>
              <div className="p-3">
                <table className="w-full">
                  <tbody>
                    {section.items.map((item, ii) => (
                      <tr key={ii} className="border-b border-gray-800 last:border-0">
                        <td className="py-2.5 pr-3 text-xs text-gray-400 font-medium w-32 whitespace-nowrap">{item.label}</td>
                        <td className="py-2.5">
                          <input className={`${INP} w-full !text-xs`} value={item.value} onChange={e => updateItem(si, ii, "value", e.target.value)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ══ Outlook Panel ═══════════════════════════════════════════════════════════ */

const DEFAULT_OUTLOOK = {
  global_economic: {
    title: "I. Global Economic Outlook",
    items: [
      { label: "Global GDP Forecast", value: "Decrease from 3.0% in 2023 to 2.7% in 2024" },
      { label: "Key Factor 1", value: "Sharp slowdown in China — persistent Yuan weakness" },
      { label: "Key Factor 2", value: "Declining inflation — reflecting drop in energy prices" },
      { label: "Key Factor 3", value: "Russian invasion of Ukraine — ongoing recovery with OECD support" },
      { label: "Fed Interest Rate", value: "5.5% (Sep 2023) -> Expected 5.7% Q4 2023 -> 5.5% in 2024" },
      { label: "Global Inflation", value: "Projected to decline from 3.8% to 2.6% in 2024" },
    ],
  },
  indonesia_economic: {
    title: "II. Indonesia Economic Outlook",
    items: [
      { label: "GDP Forecast", value: "5.1% in 2023 -> 5.2% in 2024" },
      { label: "Annual Budget", value: "Income Rp 2.8 T + Financing Rp 0.5 T = Expense Rp 3.3 T" },
      { label: "Target", value: "Accelerate inclusive and sustainable economic transformation" },
      { label: "Inflation", value: "2.7% - 2.8%" },
      { label: "Interest Rate", value: "6.0% - 6.9%" },
      { label: "Exchange Rate", value: "IDR 15,000 - 15,100 / USD" },
      { label: "Geopolitics", value: "Presidential election Feb 2024 — potential unstable economic condition" },
      { label: "IKN Capital", value: "Move to Kalimantan (IKN) from 2024-2045" },
    ],
  },
  pharmaceutical: {
    title: "III. Pharmaceutical Industry",
    items: [
      { label: "Global Market Size", value: "Expected $ 1.1 Trillion in 2023 to $ 1.2 Trillion in 2024" },
      { label: "Indonesia Growth Rate", value: "Expected 12% in 2024" },
      { label: "TKDN Objective", value: "Reduce importation of raw material by 24% in 2024" },
      { label: "Oncology", value: "API for oncology still depend on import API" },
      { label: "CKD OTTO Strategy", value: "Increasing TKDN score with local material purchase; Cooperate with foreign oncology medical worker" },
    ],
  },
};

function OutlookPanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSetupModules({ setup_module: "outlook", plan_year: year });
      if (res.success && res.data.length > 0) setData(res.data[0]);
      else setData({ setup_module: "outlook", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_OUTLOOK)), status: "draft" });
    } catch {
      setData({ setup_module: "outlook", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_OUTLOOK)), status: "draft" });
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const updateItem = (secKey, itemIdx, field, val) => {
    setData(prev => {
      if (!prev) return prev;
      return Object.assign({}, prev, {
        content: Object.assign({}, prev.content, {
          [secKey]: Object.assign({}, prev.content[secKey], {
            items: prev.content[secKey].items.map((it, i) => i === itemIdx ? Object.assign({}, it, { [field]: val }) : it),
          }),
        }),
      });
    });
  };

  const generateWithAI = async () => {
    setGenerating(true);
    try {
      const res = await pacApi.generateOutlook({ year });
      if (res.success && res.data) {
        setData(res.data);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      } else {
        alert(res.error || "Failed to generate outlook");
      }
    } catch (e) {
      alert("Failed to generate outlook: " + e.message);
    } finally {
      setGenerating(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = Object.assign({}, data, { setup_module: "outlook", plan_year: year });
      const res = await pacApi.upsertSetupModule(payload);
      if (res.success) { setData(res.data); setSaved(true); setTimeout(() => setSaved(false), 2000); }
    } finally { setSaving(false); }
  };

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!data) return null;

  const sectionColors = {
    global_economic: { border: "border-blue-500/30", bg: "bg-blue-500/5", header: "bg-blue-500/10", title: "text-blue-400", icon: "🌍" },
    indonesia_economic: { border: "border-amber-500/30", bg: "bg-amber-500/5", header: "bg-amber-500/10", title: "text-amber-400", icon: "🏛️" },
    pharmaceutical: { border: "border-emerald-500/30", bg: "bg-emerald-500/5", header: "bg-emerald-500/10", title: "text-emerald-400", icon: "💊" },
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Business Plan Outlook</h3>
          <p className="text-xs text-gray-500 mt-0.5">Economic & Industry Outlook · {year}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={generateWithAI} disabled={generating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20 transition-all disabled:opacity-50">
            {generating ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {generating ? "Generating…" : "AI Generate"}
          </button>
          <button onClick={() => setData(prev => prev ? Object.assign({}, prev, { status: prev.status === 'final' ? 'draft' : 'final' }) : prev)}
            className={BTN_SM(data.status === 'final' ? 'gray' : 'green')}>
            <CheckCircle size={11} /> {data.status === 'final' ? 'Mark Draft' : 'Mark Final'}
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("indigo")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>
      <div className="p-5 space-y-4">
        {["global_economic", "indonesia_economic", "pharmaceutical"].map(secKey => {
          const colors = sectionColors[secKey];
          return (
            <div key={secKey} className={`rounded-xl border ${colors.border} ${colors.bg} overflow-hidden`}>
              <div className={`px-4 py-2.5 border-b border-gray-700 ${colors.header} flex items-center gap-2`}>
                <span className="text-sm">{colors.icon}</span>
                <span className={`text-xs font-bold uppercase tracking-wider ${colors.title}`}>{data.content[secKey].title}</span>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.content[secKey].items.map((item, ii) => (
                    <div key={ii} className="flex items-start gap-3">
                      <span className="text-xs text-gray-500 w-32 shrink-0 pt-1 font-medium">{item.label}</span>
                      <textarea rows={2} className={`${TA} !text-xs flex-1`} value={item.value} onChange={e => updateItem(secKey, ii, "value", e.target.value)} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Section: Budget Usage Report ──────────────── */
