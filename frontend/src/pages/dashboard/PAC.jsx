import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Banknote, ExternalLink, RefreshCw, Filter, X,
  Download, Loader2, TrendingUp, TrendingDown, Minus,
  BookOpen, Plus, Trash2, Save, Printer, ChevronDown, ChevronUp, ChevronRight,
  CheckCircle, Clock, Edit3, FileText, FileSpreadsheet, Globe, Upload, AlertCircle, Calendar, BookOpenCheck, Sparkles, Settings, Users, Factory, Wallet, KeyRound,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ResponsiveContainer, ReferenceLine,
} from "recharts";
import * as XLSX from "xlsx";
import { pacApi } from "@/api/dashboard";
import GeminiApiKeyModal from "@/components/ai/GeminiApiKeyModal";

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
  const navigate = useNavigate();
  const location = useLocation();

  // Derive active tab from URL — navigation now lives in the sidebar tree menu.
  const activeTab = TABS.find((t) => location.pathname.endsWith(t.id))?.id ?? "bizplan";

  useEffect(() => {
    if (location.pathname === "/dashboard/pac" || location.pathname === "/dashboard/pac/") {
      navigate("/dashboard/pac/bizplan", { replace: true });
    }
  }, []); // eslint-disable-line

  return (
    <div className="p-6 space-y-4">
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
  { id: "simulation", label: "Simulation Data",         icon: BarChart },
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
const SELECT = "bg-gray-800/60 border border-gray-700 rounded-md px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-violet-500/60";
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
  const [uploading,  setUploading]  = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

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

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadError(null);
    try {
      const res = await pacApi.uploadBusinessPlanExcel(file, year);
      if (res.success) {
        await load();
        setActiveDoc(res.data); setIsNew(false); setExpanded({ 0: true });
      } else {
        setUploadError(res.error || "Upload failed");
      }
    } catch (err) {
      setUploadError(err?.response?.data?.detail || err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const print = () => window.print();

  // Flatten items → strategies → actions into print-ready rows with
  // rowSpan markers, mirroring the merged-box look of the Excel template
  // (one continuous cell per objective/strategy spanning its action rows).
  const buildPrintRows = (items) => {
    const rows = [];
    (items || []).forEach(item => {
      const strategies = (item.strategies && item.strategies.length) ? item.strategies : [{ letter: "", text: "", actions: [{ num: "", text: "" }] }];
      const objRowCount = strategies.reduce((sum, s) => sum + ((s.actions && s.actions.length) ? s.actions.length : 1), 0);
      let objRowIdx = 0;
      strategies.forEach(strat => {
        const actions = (strat.actions && strat.actions.length) ? strat.actions : [{ num: "", text: "" }];
        actions.forEach((act, ai) => {
          rows.push({
            objText: objRowIdx === 0 ? `(${item.obj_num}) ${item.obj_text}` : null,
            objRowSpan: objRowIdx === 0 ? objRowCount : 0,
            stratText: ai === 0 ? `(${strat.letter}) ${strat.text}` : null,
            stratRowSpan: ai === 0 ? actions.length : 0,
            actText: `(${act.num}) ${act.text}`,
          });
          objRowIdx++;
        });
      });
    });
    return rows;
  };

  return (
    <>
      <style>{`
        @media print {
          @page { size: landscape; margin: 10mm; }
          body * { visibility: hidden !important; }
          #bp-sp-print, #bp-sp-print * { visibility: visible !important; }
          #bp-sp-print { position: fixed; inset: 0; background: white; padding: 12px; font-family: Arial, sans-serif; font-size: 9pt; color: #000; }
          .no-print { display: none !important; }
        }
      `}</style>

      <div className="grid grid-cols-4 gap-4">
        {/* Left: document list */}
        <div className="col-span-1 space-y-2 no-print">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Documents {year}</p>
            <div className="flex gap-1.5">
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")} title="Upload Strategy & Action Plan Excel">
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
              </button>
              <button onClick={openNew} className={BTN_SM("violet")}><Plus size={11} /> New</button>
            </div>
          </div>
          {uploadError && <p className="text-[11px] text-red-400 mb-2">{uploadError}</p>}
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
                {/* Print header — mirrors Strategy_Action Plan - Mashudi.xlsx layout */}
                <div className="hidden print:block mb-3">
                  <p className="text-center font-bold pb-1.5 mb-2 border-b-2 border-black" style={{ fontSize: "18pt" }}>Strategy & Action Plan</p>
                  <table className="text-xs mb-2">
                    <tbody>
                      <tr>
                        <td className="pr-2 py-0.5 text-gray-700">[ Department ]</td>
                        <td className="pl-2 py-0.5 border-b border-gray-400 font-medium">{activeDoc.department}</td>
                      </tr>
                      <tr>
                        <td className="pr-2 py-0.5 text-gray-700">[ Team Code / Name ]</td>
                        <td className="pl-2 py-0.5 border-b border-gray-400 font-medium">
                          {activeDoc.team_code}{activeDoc.team_code && activeDoc.team_name ? " / " : ""}{activeDoc.team_name}
                          {activeDoc.plan_role ? <span className="ml-6">{activeDoc.plan_role}</span> : null}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Print table — flattened Objective / Strategy / Action Plan grid,
                    rowSpan-merged to mirror the Excel template's boxed grouping. */}
                <table className="hidden print:table w-full border-collapse text-xs mb-2" style={{ tableLayout: "fixed" }}>
                  <colgroup><col style={{ width: "38%" }} /><col style={{ width: "30%" }} /><col style={{ width: "32%" }} /></colgroup>
                  <thead>
                    <tr>
                      <th className="border border-black py-1.5 font-normal text-center">Managerial Objective</th>
                      <th className="border border-black py-1.5 font-normal text-center">Strategy</th>
                      <th className="border border-black py-1.5 font-normal text-center">Action Plan*</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buildPrintRows(activeDoc.content?.items).map((row, i) => (
                      <tr key={i}>
                        {row.objRowSpan > 0 && (
                          <td rowSpan={row.objRowSpan} className="border border-black align-top p-1.5">{row.objText}</td>
                        )}
                        {row.stratRowSpan > 0 && (
                          <td rowSpan={row.stratRowSpan} className="border border-black align-top p-1.5">{row.stratText}</td>
                        )}
                        <td className="border border-black align-top p-1.5">{row.actText}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="hidden print:block text-[9px] italic">*) Action plan detail related to {year} KPI plan</p>

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

                {/* Objectives — editing accordion (screen only; print uses the table above) */}
                {(activeDoc.content?.items || []).map((item, oi) => (
                  <div key={oi} className="rounded-xl border border-gray-800 bg-gray-900 mb-3 overflow-hidden no-print">
                    {/* Objective header */}
                    <div className="flex items-center gap-3 px-4 py-3 bg-gray-800/50 cursor-pointer"
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
      {subTab === "simulation" && <SimulationSection year={year} />}
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
   EXCHANGE RATE — Multi-source (BI / ExchangeRate-API / Frankfurter)
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
  const [source,     setSource]     = useState("auto");

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await pacApi.getExchangeRates(refresh, source);
      setData(res);
      if (res?.error) setError(res.error);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data kurs");
    } finally {
      setLoading(false);
    }
  }, [source]);


  useEffect(() => { load(); }, [load]);

  const sourceLabel = data?.source || "Bank Indonesia — Kurs Transaksi BI";
  const isMidMarket = data?.source_id && data.source_id !== "bi_html";

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
              ? "Mengambil data kurs…"
              : data?.date
                ? `Tanggal kurs: ${data.date}`
                : "Tanggal tidak tersedia"
            }
            {!loading && data?.source && (
              <span className="ml-2 text-gray-500">
                · Sumber: {sourceLabel}
                {isMidMarket && <span className="ml-1 text-amber-500/60">(mid-market)</span>}
              </span>
            )}
            {!loading && fmtTs(data?.cached_at) && (
              <span className="ml-2 text-gray-600">
                · Diperbarui: {fmtTs(data.cached_at)}
                {data?.from_cache && <span className="ml-1 text-amber-500/60">(cache)</span>}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={source}
            onChange={e => setSource(e.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:border-amber-500/50 focus:outline-none"
          >
            {(data?.available_sources || []).map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
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
          <span className="text-gray-300 text-sm font-medium">Semua Mata Uang</span>
          <span className="text-gray-500 text-xs">
            {loading ? "memuat…" : `${allRates.length} mata uang`}
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-gray-500">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Mengambil data kurs…</span>
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
            {data?.source || "Sumber: Bank Indonesia — Kurs Transaksi BI"}
          </span>
          {data?.source_id === "bi_html" && (
            <a
              href="https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-amber-400/70 hover:text-amber-400 transition-colors"
            >
              Lihat di BI <ExternalLink size={10} />
            </a>
          )}
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

// Department PIC keys, in display order (matches Business plan schedule.xlsx's PIC column group).
const SCHEDULE_DEPTS = [
  { key: "sales",       label: "Sales & Mkt" },
  { key: "development", label: "Strategic Dev" },
  { key: "plant",        label: "Plant" },
  { key: "admin",        label: "Admin" },
  { key: "director",     label: "P. Director" },
];

// Raw seed rows transcribed from Business plan schedule.xlsx (month-day only —
// years are attached at load time relative to the selected plan year: the
// prior-year reference date falls in {year-2}, this year's submission
// window falls in {year-1}, matching the source file's own labeling).
const SCHEDULE_SEED_ROWS = [
  ["Notification of {year} business plan timeline",                                                     "09-20", "09-19", "09-19", "Friday",             "X X X O X", "Timeline"],
  ["Distribution of all relevant templates",                                                             "09-20", "09-19", "09-19", "Friday",             "X X X X X", "-"],
  ["{year} economic outlook & guideline",                                                                "10-03", "09-30", "09-30", "Tuesday",            "X X X O X", "-"],
  ["{year} managerial objective decision of the Company from President Director",                        "10-08", "10-10", "10-10", "Friday",             "X X X X O", "C1"],
  ["{year} action plan from Department related to managerial objective",                                 "10-18", "10-15", "10-15", "Wednesday",          "O O O O O", "C2, A1"],
  ["Registration schedule (including export)",                                                           "10-11", "10-17", "10-17", "Friday",             "X O X X X", "R1"],
  ["Business development plan : CMO, export, and others / PERT / by new area, customer & product",       "10-29", "10-24", "10-24", "Friday",             "X O X X X", "B1"],
  ["Sales plan {year} : by department, product & area (local, export and CMO)",                          "10-29", "10-24", "10-24", "Friday",             "O O X X X", "S1, S2, S3"],
  ["Sales plan review",                                                                                   "10-31", "10-29", "10-29", "Wednesday",          "X X X O O", "-"],
  ["Sharing sales plan {year} with Shareholders / initial consensus",                                    "10-31", "10-29", "10-29", "Wednesday",          "X X X O O", "-"],
  ["Production / manufacturing plan",                                                                     "11-06", "11-03", "11-03", "Monday",             "X X O X X", "M1"],
  ["Personnel plan",                                                                                      "11-08", "11-05", "11-05", "Wednesday",          "O O O O X", "H1"],
  ["Purchase plan",                                                                                       "11-08", "11-05", "11-05", "Wednesday",          "O O X X X", "P1, P2"],
  ["Investment plan",                                                                                     "11-13", "11-10", "11-10", "Monday",             "X X O O X", "I1"],
  ["Opex budget plan",                                                                                    "11-13", "11-10", "11-10", "Monday",             "O O O O X", "O1, O2"],
  ["Data review : production, personnel, purchase, investment & opex budget plan",                       "11-15", "11-12", "11-12", "Wednesday",          "X X X O X", "-"],
  ["Standard COGS / manufacture costs",                                                                  "11-20", "11-17", "11-17", "Monday",             "X X O X X", "CS1, CS2"],
  ["Forecasting : profit and loss simulation 1",                                                          "11-25", "11-19", "11-19", "Wednesday",          "X X X O X", "-"],
  ["Data evaluation & budget meeting with each Department",                                               "11-26", "11-20", "11-25", "Thursday - Tuesday", "O O O O O", "-"],
  ["Forecasting : profit and loss simulation 2",                                                          "12-02", "11-28", "11-28", "Friday",             "X X X O X", "-"],
  ["Final budget decision",                                                                               "12-06", "12-05", "12-05", "Friday",             "X X O O X", "-"],
  ["Collecting & financing plan",                                                                         "12-06", "12-09", "12-09", "Tuesday",            "X X X O X", "-"],
  ["Other income & expenses",                                                                             "12-06", "12-09", "12-09", "Tuesday",            "X X X O X", "-"],
  ["{year} cashflow forecasting",                                                                         "12-10", "12-09", "12-09", "Tuesday",            "X X X O X", "-"],
  ["{year} business plan report",                                                                         "12-24", "12-12", "12-12", "Friday",             "X X X O X", "-"],
  ["Reporting business plan {year} to President Director",                                                "12-24", "12-15", "12-15", "Monday",             "X X X O O", "-"],
  ["Reporting business plan {year} to BOD",                                                                "12-26", "12-17", "12-17", "Wednesday",          "X X X O O", "-"],
  ["Reporting business plan {year} to Shareholders",                                                       "12-27", "12-19", "12-19", "Friday",             "X X X O O", "-"],
];

function buildDefaultSchedule(year) {
  const y1 = year - 1, y2 = year - 2;
  const mmdd = (md, y) => md ? `${y}-${md}` : "";
  return {
    subtitle: "Timeline of {year} Business Plan".replace("{year}", year),
    activities: SCHEDULE_SEED_ROWS.map(([activity, prior, from, to, day, pic, remarks], i) => {
      const statuses = pic.split(" ");
      const departments = {};
      SCHEDULE_DEPTS.forEach((d, di) => { departments[d.key] = { status: statuses[di] || "X", date: null }; });
      return {
        no: i + 1,
        activity: activity.replace(/\{year\}/g, year),
        prior_date: mmdd(prior, y2),
        submission_from: mmdd(from, y1),
        submission_to: mmdd(to, y1),
        day,
        departments,
        remarks,
      };
    }),
  };
}

const SCHEDULE_COLUMNS = [
  { key: "no",              label: "No",   width: "w-10",  align: "center" },
  { key: "activity",        label: "Activity Description", width: "min-w-[260px]", align: "left" },
  { key: "prior_date",      label: "Prior Year Actual Date", width: "w-28", align: "center" },
  { key: "submission_from", label: "Submission Date From",   width: "w-28", align: "center" },
  { key: "submission_to",   label: "Submission Date To",     width: "w-28", align: "center" },
  { key: "actual_from",     label: "Actual Date From",       width: "w-28", align: "center" },
  { key: "actual_to",       label: "Actual Date To",         width: "w-28", align: "center" },
  { key: "day",             label: "Day",  width: "w-24",  align: "center" },
  ...SCHEDULE_DEPTS.map(d => ({ key: d.key, label: d.label, width: "w-16", align: "center" })),
  { key: "remarks",         label: "Remarks", width: "w-24", align: "center" },
  { key: "notes",           label: "Notes",   width: "w-20", align: "center" },
];

function computeActualRange(departments) {
  const dates = Object.values(departments || {})
    .filter(d => d.status === "O" && d.date)
    .map(d => d.date)
    .sort();
  return { from: dates[0] || null, to: dates[dates.length - 1] || null };
}

// Signed count of working days (Mon-Fri) between two ISO dates, counting
// the range (d1, d2] — negative if d2 precedes d1.
function workingDaysDiff(d1, d2) {
  if (!d1 || !d2) return null;
  const a = new Date(`${d1}T00:00:00`), b = new Date(`${d2}T00:00:00`);
  const sign = b < a ? -1 : 1;
  const start = sign < 0 ? b : a;
  const end = sign < 0 ? a : b;
  let count = 0;
  const cur = new Date(start);
  cur.setDate(cur.getDate() + 1);
  while (cur <= end) {
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) count++;
    cur.setDate(cur.getDate() + 1);
  }
  return count * sign;
}

// Notes[i] = working days from the row above's Actual Date To to this
// row's Actual Date From — aligned 1:1 with the activities array.
function computeScheduleNotes(activities) {
  let prevTo = null;
  return (activities || []).map((act, i) => {
    const { from, to } = computeActualRange(act.departments);
    const note = (i > 0 && prevTo && from) ? workingDaysDiff(prevTo, from) : null;
    prevTo = to;
    return note;
  });
}

function totalWorkingDays(activities) {
  return computeScheduleNotes(activities).reduce((sum, n) => sum + (n || 0), 0);
}

// Activities (typically a prior, closed-out year) where a department
// submitted its actual date after the row's planned Submission Date To.
function computeLateReview(activities) {
  const items = [];
  (activities || []).forEach(act => {
    const lateDepts = SCHEDULE_DEPTS.filter(d => {
      const dep = act.departments?.[d.key];
      return dep?.status === "O" && dep?.date && act.submission_to && dep.date > act.submission_to;
    });
    if (lateDepts.length) items.push({ no: act.no, activity: act.activity, lateDepts: lateDepts.map(d => d.label) });
  });
  return items;
}

function SchedulePanel({ year }) {
  const [data, setData] = useState(null);
  const [prevData, setPrevData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [editingCell, setEditingCell] = useState(null); // `${rowIdx}:${deptKey}`

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSetupModules({ setup_module: "schedule", plan_year: year });
      if (res.success && res.data.length > 0) {
        setData(res.data[0]);
      } else {
        setData({ setup_module: "schedule", plan_year: year, content: buildDefaultSchedule(year), status: "draft" });
      }
    } catch {
      setData({ setup_module: "schedule", plan_year: year, content: buildDefaultSchedule(year), status: "draft" });
    } finally { setLoading(false); }
  }, [year]);

  const loadPrev = useCallback(async () => {
    try {
      const res = await pacApi.listSetupModules({ setup_module: "schedule", plan_year: year - 1 });
      if (res.success && res.data.length > 0) setPrevData(res.data[0]);
      else setPrevData({ content: buildDefaultSchedule(year - 1) });
    } catch {
      setPrevData({ content: buildDefaultSchedule(year - 1) });
    }
  }, [year]);

  useEffect(() => { load(); loadPrev(); }, [load, loadPrev]);

  const updateActivity = (idx, field, val) => {
    setData(prev => ({
      ...prev,
      content: {
        ...prev.content,
        activities: prev.content.activities.map((a, i) => i === idx ? Object.assign({}, a, { [field]: val }) : a),
      },
    }));
  };

  const setDeptDate = (idx, deptKey, val) => {
    setData(prev => ({
      ...prev,
      content: {
        ...prev.content,
        activities: prev.content.activities.map((a, i) => {
          if (i !== idx) return a;
          const departments = { ...a.departments, [deptKey]: { ...a.departments[deptKey], date: val || null } };
          return { ...a, departments };
        }),
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

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await pacApi.exportScheduleExcel(year);
      const url = URL.createObjectURL(new Blob([res])); // api client's response interceptor already unwraps to the Blob itself
      const a = document.createElement("a");
      a.href = url; a.download = `Business plan schedule ${year}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } finally { setExporting(false); }
  };

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!data) return null;

  const currentTotalDays = totalWorkingDays(data.content.activities);
  const prevTotalDays = prevData ? totalWorkingDays(prevData.content.activities) : null;
  const lateReview = prevData ? computeLateReview(prevData.content.activities) : [];

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
          <button onClick={handleExport} disabled={exporting} className={BTN_SM("teal")}>
            {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
            Download Excel
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("sky")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 p-4 border-b border-gray-800">
        <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
          <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">BP {year} (Current)</p>
          <p className="text-xl font-bold text-gray-100 mt-1">{currentTotalDays} <span className="text-xs font-normal text-gray-500">working days</span></p>
        </div>
        <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
          <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">BP {year - 1} (Previous)</p>
          <p className="text-xl font-bold text-gray-100 mt-1">{prevTotalDays ?? "—"} <span className="text-xs font-normal text-gray-500">working days</span></p>
        </div>
        <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-3">
          <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Timeline Review — Late Submissions ({year - 1})</p>
          {lateReview.length === 0 ? (
            <p className="text-xs text-gray-500 mt-1.5">No late submissions</p>
          ) : (
            <div className="mt-1.5 max-h-14 overflow-y-auto space-y-0.5 pr-1">
              {lateReview.slice(0, 4).map(item => (
                <p key={item.no} className="text-[10px] text-red-300 truncate" title={`${item.activity} — ${item.lateDepts.join(", ")}`}>
                  #{item.no} {item.activity} — {item.lateDepts.join(", ")}
                </p>
              ))}
              {lateReview.length > 4 && <p className="text-[10px] text-gray-500">+{lateReview.length - 4} more</p>}
            </div>
          )}
        </div>
      </div>

      <div className="overflow-auto" style={{ maxHeight: "28rem" }}>
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-800/80">
              {SCHEDULE_COLUMNS.map(col => (
                <th key={col.key} className={`sticky top-0 z-10 bg-gray-800 ${col.width} px-3 py-2.5 text-left text-gray-400 border border-gray-700 font-semibold whitespace-nowrap ${col.align === 'center' ? 'text-center' : ''}`}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(() => {
              const notes = computeScheduleNotes(data.content.activities);
              return (data.content.activities || []).map((act, i) => {
                const { from: actualFrom, to: actualTo } = computeActualRange(act.departments);
                const actualToLate = actualTo && act.submission_to && actualTo > act.submission_to;
                return (
                  <tr key={i} className={`border-b border-gray-800 transition-colors ${i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-900/40'} hover:bg-gray-800/50`}>
                    <td className="px-3 py-2 border border-gray-700 text-center font-bold text-gray-400">{act.no}</td>
                    <td className="px-3 py-2 border border-gray-700">
                      <textarea rows={1} className={`${TA} !py-1.5 !text-xs w-full`} value={act.activity} onChange={e => updateActivity(i, "activity", e.target.value)} />
                    </td>
                    <td className="px-3 py-2 border border-gray-700 text-center">
                      <input type="date" className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.prior_date || ""} onChange={e => updateActivity(i, "prior_date", e.target.value)} />
                    </td>
                    <td className="px-3 py-2 border border-gray-700 text-center">
                      <input type="date" className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.submission_from || ""} onChange={e => updateActivity(i, "submission_from", e.target.value)} />
                    </td>
                    <td className="px-3 py-2 border border-gray-700 text-center">
                      <input type="date" className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.submission_to || ""} onChange={e => updateActivity(i, "submission_to", e.target.value)} />
                    </td>
                    <td className="px-3 py-2 border border-gray-700 text-center text-gray-400 font-mono">{actualFrom || "—"}</td>
                    <td className={`px-3 py-2 border border-gray-700 text-center font-mono ${actualToLate ? "text-red-400 font-bold" : "text-gray-400"}`}>{actualTo || "—"}</td>
                    <td className="px-3 py-2 border border-gray-700 text-center">
                      <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.day} onChange={e => updateActivity(i, "day", e.target.value)} />
                    </td>
                    {SCHEDULE_DEPTS.map(dept => {
                      const cell = act.departments[dept.key] || { status: "X", date: null };
                      const cellId = `${i}:${dept.key}`;
                      const isLate = cell.status === "O" && cell.date && act.submission_to && cell.date > act.submission_to;
                      return (
                        <td key={dept.key} className="px-1 py-2 border border-gray-700 text-center">
                          {cell.status !== "O" ? (
                            <span className="text-gray-500 font-mono font-bold">X</span>
                          ) : editingCell === cellId ? (
                            <input type="date" autoFocus className={`${INP} !text-center !py-1 !text-[10px] w-full`}
                              defaultValue={cell.date || ""}
                              onBlur={e => { setDeptDate(i, dept.key, e.target.value); setEditingCell(null); }}
                              onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                          ) : (
                            <button onClick={() => setEditingCell(cellId)}
                              className={`w-full rounded px-1.5 py-1 font-mono font-bold text-[10px] text-black border transition-colors ${
                                isLate ? "bg-red-500/70 border-red-600/60 hover:bg-red-500/80"
                                       : "bg-green-500/70 border-green-600/60 hover:bg-green-500/80"
                              }`}
                              title={isLate ? "Late vs. planned Submission Date To" : "Click to set actual submission date"}>
                              {cell.date || "O"}
                            </button>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-3 py-2 border border-gray-700 text-center">
                      <input className={`${INP} !text-center !py-1.5 !text-xs w-full`} value={act.remarks} onChange={e => updateActivity(i, "remarks", e.target.value)} />
                    </td>
                    <td className="px-3 py-2 border border-gray-700 text-center font-mono text-gray-400">
                      {notes[i] !== null && notes[i] !== undefined ? notes[i] : "—"}
                    </td>
                  </tr>
                );
              });
            })()}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══ Guideline Panel ══════════════════════════════════════════════════════════ */

// Seed data transcribed from Business plan guideline.xlsx (FY2026 "current"
// vs FY2025 "previous" pages) — figures are best-effort reads off a scanned
// template and editable afterward; the field set is what matters (Working
// Days, Exchange Rate, Utilities incl. gasoline/electricity, Meeting/
// Business-Trip minimum salary, and regional UMK for DKI Jakarta / Kab.
// Bekasi-Cikarang).
const DEFAULT_GUIDELINE = {
  sections: [
    {
      title: "1. Working Days",
      icon: "📅",
      items: [
        { label: "Jan", current: 23, previous: 23 },
        { label: "Feb", current: 18, previous: 20 },
        { label: "Mar", current: 22, previous: 19 },
        { label: "Apr", current: 22, previous: 21 },
        { label: "May", current: 16, previous: 20 },
        { label: "Jun", current: 20, previous: 17 },
        { label: "Jul", current: 23, previous: 22 },
        { label: "Aug", current: 22, previous: 21 },
        { label: "Sep", current: 22, previous: 20 },
        { label: "Oct", current: 22, previous: 23 },
        { label: "Nov", current: 21, previous: 20 },
        { label: "Dec", current: 21, previous: 22 },
        { label: "Total", current: 240, previous: 233 },
      ],
    },
    {
      title: "2. Exchange Rate",
      icon: "💱",
      items: [
        { label: "USD / IDR", current: "Rp 15,300", previous: "Rp 15,712" },
        { label: "EUR / IDR", current: "Rp 17,700", previous: "Rp 17,240" },
        { label: "KRW / IDR", current: "Rp 11.70", previous: "Rp 11.68" },
      ],
    },
    {
      title: "3. Utilities & Others",
      icon: "🔌",
      items: [
        { label: "Gasoline (Pertalite / Pertamax)", current: "Rp 10,000", previous: "Rp 13,350" },
        { label: "Electricity, etc (Inflation)", current: "2.7%", previous: "5.1%" },
        { label: "Loan Interest — USD/IDR", current: "8.3%", previous: "6.8%" },
        { label: "Loan Interest — EUR/IDR", current: "6.1%", previous: "5.1%" },
        { label: "Loan Interest — KRW/IDR", current: "7.9%", previous: "7.7%" },
      ],
    },
    {
      title: "4. Minimum Salary — Meeting Allowance",
      icon: "👔",
      items: [
        { label: "Director (Max)", current: "Rp 1,500,000", previous: "Rp 1,500,000" },
        { label: "General Manager (Max)", current: "Rp 1,200,000", previous: "Rp 1,200,000" },
        { label: "Manager (Max)", current: "Rp 800,000", previous: "Rp 800,000" },
        { label: "Assistant Manager (Max)", current: "Rp 600,000", previous: "Rp 600,000" },
        { label: "Supervisor / Product Specialist (Max)", current: "Rp 400,000", previous: "Rp 400,000" },
        { label: "Officer / Senior Staff (Max)", current: "Rp 170,000", previous: "Rp 140,000" },
        { label: "Clerk (Max)", current: "Rp 120,000", previous: "Rp 120,000" },
      ],
    },
    {
      title: "5. Business Trip — Domestic",
      icon: "🚗",
      items: [
        { label: "Hotel Limit / Day", current: "Rp 600,000", previous: "Rp 600,000" },
        { label: "Meal Allowance / Day", current: "Rp 120,000", previous: "Rp 120,000" },
      ],
    },
    {
      title: "6. Business Trip — International",
      icon: "✈️",
      items: [
        { label: "Hotel Limit / Day", current: "$150", previous: "$150" },
        { label: "Meal Allowance / Day", current: "$40", previous: "$40" },
      ],
    },
    {
      title: "7. Minimum Salary — Regional (UMK/UMR)",
      icon: "🏙️",
      items: [
        { label: "DKI Jakarta", current: "Rp 5,657,752", previous: "Rp 5,396,761" },
        { label: "Kab. Bekasi - Cikarang", current: "Rp 5,643,032", previous: "Rp 5,397,838" },
      ],
    },
  ],
};

function GuidelinePanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [exporting, setExporting] = useState(false);

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

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await pacApi.exportGuidelinePpt(year);
      const url = URL.createObjectURL(new Blob([res])); // api client's response interceptor already unwraps to the Blob itself
      const a = document.createElement("a");
      a.href = url; a.download = `Business plan guideline ${year}.pptx`; a.click();
      URL.revokeObjectURL(url);
    } finally { setExporting(false); }
  };

  if (loading) return <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>;
  if (!data) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Business Plan Guideline</h3>
          <p className="text-xs text-gray-500 mt-0.5">Guidelines & Parameters · {year} vs {year - 1}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setData(prev => prev ? Object.assign({}, prev, { status: prev.status === 'final' ? 'draft' : 'final' }) : prev)}
            className={BTN_SM(data.status === 'final' ? 'gray' : 'green')}>
            <CheckCircle size={11} /> {data.status === 'final' ? 'Mark Draft' : 'Mark Final'}
          </button>
          <button onClick={handleExport} disabled={exporting} className={BTN_SM("teal")}>
            {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
            Export PPT
          </button>
          <button onClick={save} disabled={saving} className={BTN_SM("sky")}>
            {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
            {saved ? "Saved!" : "Save"}
          </button>
        </div>
      </div>
      <div className="p-5">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {(data.content.sections || []).map((section, si) => (
            <div key={si} className="rounded-xl border border-gray-700/60 bg-gray-800/40 overflow-hidden">
              <div className="px-4 py-3 bg-gray-800/60 border-b border-gray-700 flex items-center gap-2">
                <span className="text-lg">{section.icon}</span>
                <span className="text-xs font-bold text-teal-400 uppercase tracking-wider">{section.title}</span>
              </div>
              <div className="p-3">
                <table className="w-full">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-wider text-gray-500">
                      <td className="pb-1.5"></td>
                      <td className="pb-1.5 pl-2 text-center font-semibold">Current Year ({year})</td>
                      <td className="pb-1.5 pl-2 text-center font-semibold">Previous Year ({year - 1})</td>
                    </tr>
                  </thead>
                  <tbody>
                    {section.items.map((item, ii) => (
                      <tr key={ii} className="border-b border-gray-800 last:border-0">
                        <td className="py-2 pr-2 text-xs text-gray-400 font-medium whitespace-nowrap">{item.label}</td>
                        <td className="py-2 pl-2">
                          <input className={`${INP} w-full !text-xs !text-center`} value={item.current} onChange={e => updateItem(si, ii, "current", e.target.value)} />
                        </td>
                        <td className="py-2 pl-2">
                          <input className={`${INP} w-full !text-xs !text-center`} value={item.previous} onChange={e => updateItem(si, ii, "previous", e.target.value)} />
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
    text: [
      "- **Global GDP Forecast**: Decrease from 3.0% in 2023 to 2.7% in 2024",
      "- **Key Factor 1**: Sharp slowdown in China — persistent Yuan weakness",
      "- **Key Factor 2**: Declining inflation — reflecting drop in energy prices",
      "- **Key Factor 3**: Russian invasion of Ukraine — ongoing recovery with OECD support",
      "- **Fed Interest Rate**: 5.5% (Sep 2023) -> Expected 5.7% Q4 2023 -> 5.5% in 2024",
      "- **Global Inflation**: Projected to decline from 3.8% to 2.6% in 2024",
    ].join("\n"),
  },
  indonesia_economic: {
    title: "II. Indonesia Economic Outlook",
    text: [
      "- **GDP Forecast**: 5.1% in 2023 -> 5.2% in 2024",
      "- **Annual Budget**: Income Rp 2.8 T + Financing Rp 0.5 T = Expense Rp 3.3 T",
      "- **Target**: Accelerate inclusive and sustainable economic transformation",
      "- **Inflation**: 2.7% - 2.8%",
      "- **Interest Rate**: 6.0% - 6.9%",
      "- **Exchange Rate**: IDR 15,000 - 15,100 / USD",
      "- **Geopolitics**: Presidential election Feb 2024 — potential unstable economic condition",
      "- **IKN Capital**: Move to Kalimantan (IKN) from 2024-2045",
    ].join("\n"),
  },
  pharmaceutical: {
    title: "III. Pharmaceutical Industry",
    text: [
      "- **Global Market Size**: Expected $ 1.1 Trillion in 2023 to $ 1.2 Trillion in 2024",
      "- **Indonesia Growth Rate**: Expected 12% in 2024",
      "- **TKDN Objective**: Reduce importation of raw material by 24% in 2024",
      "- **Oncology**: API for oncology still depend on import API",
      "- **CKD OTTO Strategy**: Increasing TKDN score with local material purchase; Cooperate with foreign oncology medical worker",
    ].join("\n"),
  },
};

// Older saved records may still use the { items: [{label,value}] } shape —
// fold them into the same { title, text } markdown shape on read so the
// editor never has to branch on which format it's looking at.
function normalizeOutlookContent(content) {
  if (!content) return content;
  const out = {};
  for (const key of Object.keys(content)) {
    const sec = content[key] || {};
    if (typeof sec.text === "string") { out[key] = sec; continue; }
    if (Array.isArray(sec.items)) {
      out[key] = {
        title: sec.title || "",
        text: sec.items.map(it => `- **${it.label}**: ${it.value}`).join("\n"),
      };
    } else {
      out[key] = { title: sec.title || "", text: "" };
    }
  }
  return out;
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* Reference files uploaded ahead of writing the Outlook — kept separate
   from the actual generation step. Two categories share this same panel:
   "material" = source data (economic reports, market data, etc.) and
   "format" = example/template files defining the desired report format,
   which can be several and are all used as reference during generation. */
function OutlookBriefStatusBadge({ status }) {
  // Solid (opaque) backgrounds instead of low-opacity tints — a tint over
  // this panel's own translucent container let the light app-shell
  // background bleed through, washing out the badge text's contrast
  // regardless of theme. Opaque colors read correctly no matter what's
  // behind them.
  const map = {
    pending:    { icon: Clock,       cls: "text-gray-100 bg-gray-600 border-gray-500",           label: "Not converted" },
    converting: { icon: Loader2,     cls: "text-white bg-sky-600 border-sky-400",                 label: "Converting…", spin: true },
    done:       { icon: CheckCircle, cls: "text-white bg-green-600 border-green-400",             label: "Converted" },
    failed:     { icon: AlertCircle, cls: "text-white bg-red-600 border-red-400",                 label: "Failed" },
  };
  const s = map[status] || map.pending;
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-semibold whitespace-nowrap ${s.cls}`}>
      <Icon size={9} className={s.spin ? "animate-spin" : ""} /> {s.label}
    </span>
  );
}

function OutlookMaterialsPanel({ year, category = "material", title, description, accent = "teal", provider = "onprem" }) {
  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [converting, setConverting] = useState({});   // { [id]: true } while a single convert is in flight
  const [convertingAll, setConvertingAll] = useState(false);
  const [convertProgress, setConvertProgress] = useState({ done: 0, total: 0 });
  const [expandedId, setExpandedId] = useState(null);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listOutlookMaterials(year, category);
      if (res.success) setMaterials(res.data || []);
    } catch {
      setMaterials([]);
    } finally { setLoading(false); }
  }, [year, category]);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true); setUploadError(null);
    try {
      const res = await pacApi.uploadOutlookMaterials(files, year, category);
      if (res.success) await load();
      else setUploadError(res.error || "Upload failed");
    } catch (err) {
      setUploadError(err?.response?.data?.detail || err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDownload = async (item) => {
    const res = await pacApi.downloadOutlookMaterial(item.id);
    const url = URL.createObjectURL(new Blob([res])); // api client's response interceptor already unwraps to the Blob itself
    const a = document.createElement("a");
    a.href = url; a.download = item.original_name; a.click();
    URL.revokeObjectURL(url);
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this file?")) return;
    await pacApi.deleteOutlookMaterial(id);
    load();
  };

  const convertOne = async (id) => {
    setConverting(prev => Object.assign({}, prev, { [id]: true }));
    try {
      const res = await pacApi.convertOutlookMaterial(id, provider);
      setMaterials(prev => prev.map(m => m.id === id ? res.data : m));
    } catch (err) {
      // reflect failure locally even if the request itself errored (network, etc.)
      setMaterials(prev => prev.map(m => m.id === id ? Object.assign({}, m, { brief_status: "failed", brief_error: err?.response?.data?.detail || err.message }) : m));
    } finally {
      setConverting(prev => { const n = Object.assign({}, prev); delete n[id]; return n; });
    }
  };

  const convertAll = async () => {
    const todo = materials.filter(m => m.brief_status !== "done").map(m => m.id);
    if (todo.length === 0) return;
    setConvertingAll(true);
    setConvertProgress({ done: 0, total: todo.length });
    try {
      for (const id of todo) {
        await convertOne(id);
        setConvertProgress(prev => ({ ...prev, done: prev.done + 1 }));
      }
    } finally {
      setConvertingAll(false);
      setConvertProgress({ done: 0, total: 0 });
    }
  };

  const pendingCount = materials.filter(m => m.brief_status !== "done").length;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          <p className="text-xs text-gray-500 mt-0.5">{description} · {year}</p>
        </div>
        <div className="flex gap-2">
          {materials.length > 0 && pendingCount > 0 && (
            <button onClick={convertAll} disabled={convertingAll} className={BTN_SM("indigo")}>
              {convertingAll ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
              {convertingAll ? "Converting…" : `Convert All (${pendingCount})`}
            </button>
          )}
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleUpload} />
          <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM(accent)}>
            {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
            {uploading ? "Uploading…" : "Upload Files"}
          </button>
        </div>
      </div>
      {convertingAll && convertProgress.total > 0 && (
        <div className="px-5 pt-3 pb-1">
          <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
            <span>Converting file {convertProgress.done + 1} of {convertProgress.total}…</span>
            <span>{Math.round((convertProgress.done / convertProgress.total) * 100)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-indigo-500 transition-all duration-300 ease-out"
              style={{ width: `${Math.round((convertProgress.done / convertProgress.total) * 100)}%` }}
            />
          </div>
        </div>
      )}
      <div className="p-4">
        {uploadError && (
          <p className="text-xs text-red-400 mb-3 flex items-center gap-1.5"><AlertCircle size={12} />{uploadError}</p>
        )}
        {loading ? (
          <div className="flex justify-center py-8 text-gray-500 text-sm gap-2"><Loader2 size={14} className="animate-spin" /> Loading…</div>
        ) : materials.length === 0 ? (
          <p className="text-xs text-gray-600 text-center py-8">
            No files yet. Upload {category === "format" ? "example/format outlook reports (more than 1 file allowed, various formats) as a structural reference for the generated report." : "materials (economic reports, market data, etc. — more than 10 files allowed, various formats) as the basis for drafting the Outlook."}
          </p>
        ) : (
          <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
            {materials.map(item => {
              const isConverting = !!converting[item.id] || item.brief_status === "converting";
              const isExpanded = expandedId === item.id;
              return (
                <div key={item.id} className="rounded-lg border border-gray-800 bg-gray-900 hover:border-gray-700 transition-colors">
                  <div className="flex items-center gap-3 px-3 py-2">
                    <FileText size={14} className={`shrink-0 ${accent === "teal" ? "text-teal-400" : "text-violet-400"}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-200 font-medium truncate">{item.original_name}</p>
                      <p className="text-[10px] text-gray-500">{formatFileSize(item.file_size)} · {item.uploaded_by} · {item.created_at ? new Date(item.created_at).toLocaleDateString("id-ID") : ""}</p>
                    </div>
                    <OutlookBriefStatusBadge status={isConverting ? "converting" : item.brief_status} />
                    {item.brief_status === "done" ? (
                      <button onClick={() => setExpandedId(isExpanded ? null : item.id)} className="shrink-0 p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800" title="View summary">
                        {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      </button>
                    ) : (
                      <button onClick={() => convertOne(item.id)} disabled={isConverting} className="shrink-0 p-1.5 rounded-md text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 disabled:opacity-40" title="Convert into a bullet-point summary">
                        {isConverting ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                      </button>
                    )}
                    <button onClick={() => handleDownload(item)} className="shrink-0 p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800" title="Download">
                      <Download size={13} />
                    </button>
                    <button onClick={() => handleDelete(item.id)} className="shrink-0 p-1.5 rounded-md text-gray-400 hover:text-red-400 hover:bg-red-500/10" title="Delete">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  {isConverting && (
                    <div className="mx-3 mb-2 h-1 rounded-full bg-gray-800 overflow-hidden">
                      <div className="h-full w-2/5 rounded-full bg-sky-500 animate-pulse" />
                    </div>
                  )}
                  {item.brief_status === "failed" && item.brief_error && (
                    <p className="px-3 pb-2 text-[10px] text-red-400 flex items-start gap-1"><AlertCircle size={10} className="mt-0.5 shrink-0" />{item.brief_error}</p>
                  )}
                  {isExpanded && item.brief_status === "done" && (
                    <div className="mx-3 mb-3 p-3 rounded-md bg-gray-950 border border-gray-800">
                      <pre className="text-[10.5px] text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">{item.brief_text}</pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

const PROVIDER_LABELS = { onprem: "Standard (On-Premise)", gemini: "Gemini", anthropic: "Claude AI" };

function OutlookPanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genStatus, setGenStatus] = useState(null); // { type: "info"|"ok"|"err", text }
  const [provider, setProvider] = useState("onprem");
  const [showApiKey, setShowApiKey] = useState(false);

  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSetupModules({ setup_module: "outlook", plan_year: year });
      if (res.success && res.data.length > 0) {
        setData(Object.assign({}, res.data[0], { content: normalizeOutlookContent(res.data[0].content) }));
      } else {
        setData({ setup_module: "outlook", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_OUTLOOK)), status: "draft" });
      }
    } catch {
      setData({ setup_module: "outlook", plan_year: year, content: JSON.parse(JSON.stringify(DEFAULT_OUTLOOK)), status: "draft" });
    } finally { setLoading(false); }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const updateSectionText = (secKey, val) => {
    setData(prev => {
      if (!prev) return prev;
      return Object.assign({}, prev, {
        content: Object.assign({}, prev.content, {
          [secKey]: Object.assign({}, prev.content[secKey], { text: val }),
        }),
      });
    });
  };

  const handleExportPpt = async () => {
    setExporting(true);
    try {
      const res = await pacApi.exportOutlookPpt(year);
      const url = URL.createObjectURL(new Blob([res])); // api client's response interceptor already unwraps to the Blob itself
      const a = document.createElement("a");
      a.href = url; a.download = `Business plan outlook ${year}.pptx`; a.click();
      URL.revokeObjectURL(url);
    } finally { setExporting(false); }
  };

  const generateWithAI = async () => {
    setGenerating(true);
    setGenStatus({
      type: "info",
      text: provider === "anthropic"
        ? "Generating with Claude AI — grounding the outlook in live web search, this can take a few minutes. Please keep this tab open."
        : `Generating with ${PROVIDER_LABELS[provider]}… this can take up to a minute.`,
    });
    try {
      const res = await pacApi.generateOutlook({ year, provider });
      if (res.success && res.data) {
        setData(Object.assign({}, res.data, { content: normalizeOutlookContent(res.data.content) }));
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
        if (!res.materials_used && !res.format_examples_used) {
          setGenStatus({ type: "info", text: "Generated with general knowledge only — no converted reference materials yet for this year. Upload & convert files above for a more accurate result." });
        } else if (res.not_converted > 0) {
          setGenStatus({ type: "ok", text: `Generated using ${res.materials_used} material(s) & ${res.format_examples_used} format example(s). ${res.not_converted} file(s) still not converted — convert them to include in the next generate.` });
        } else {
          setGenStatus({ type: "ok", text: `Generated using ${res.materials_used} material(s) & ${res.format_examples_used} format example(s).` });
        }
      } else {
        setGenStatus({ type: "err", text: res.error || "Failed to generate outlook" });
      }
    } catch (e) {
      setGenStatus({ type: "err", text: "Failed to generate outlook: " + (e?.response?.data?.detail || e.message) });
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
    <div className="space-y-4">
    {showApiKey && <GeminiApiKeyModal onClose={() => setShowApiKey(false)} />}
    <OutlookMaterialsPanel
      year={year} category="material" accent="teal"
      title="Outlook Reference Materials"
      description="Base material for the economic & market share report"
      provider={provider}
    />
    <OutlookMaterialsPanel
      year={year} category="format" accent="violet"
      title="Outlook Report Format"
      description="Example/format report used as a reference for generating the Outlook"
      provider={provider}
    />
    <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Business Plan Outlook</h3>
          <p className="text-xs text-gray-500 mt-0.5">Economic & Industry Outlook · {year}</p>
        </div>
        <div className="flex gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            title="AI provider used for Convert and AI Generate"
            className="rounded-md border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs font-medium text-gray-300 outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="onprem">Standard (On-Premise)</option>
            <option value="gemini">Gemini</option>
            <option value="anthropic">Claude AI</option>
          </select>
          {provider === "gemini" && (
            <button onClick={() => setShowApiKey(true)} title="Use your own personal Gemini API key"
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium border border-gray-700 bg-gray-800 text-gray-300 hover:border-violet-500 hover:text-violet-400 transition-colors">
              <KeyRound size={11} /> My API Key
            </button>
          )}
          <button onClick={generateWithAI} disabled={generating}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border transition-all ${
              generating
                ? "border-indigo-400 bg-indigo-600 text-white"
                : "border-indigo-500/30 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20"
            }`}>
            {generating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={11} />}
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
          <button onClick={handleExportPpt} disabled={exporting} className={BTN_SM("sky")}>
            {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
            {exporting ? "Exporting…" : "Generate PPT"}
          </button>
        </div>
      </div>
      {genStatus && (
        <div className={`px-5 py-4 border-b ${
          genStatus.type === "err" ? "bg-red-950/70 border-red-500/40" :
          genStatus.type === "ok" ? "bg-green-950/70 border-green-500/40" :
          "bg-indigo-950/70 border-indigo-500/40"
        }`}>
          <div className="flex items-center gap-3">
            {generating ? (
              <Loader2 size={22} className="animate-spin shrink-0 text-indigo-300" />
            ) : genStatus.type === "err" ? (
              <AlertCircle size={22} className="shrink-0 text-red-400" />
            ) : (
              <CheckCircle size={22} className="shrink-0 text-green-400" />
            )}
            <span className={`flex-1 text-sm font-semibold ${
              genStatus.type === "err" ? "text-red-200" :
              genStatus.type === "ok" ? "text-green-200" :
              "text-indigo-200"
            }`}>{genStatus.text}</span>
            {!generating && (
              <button onClick={() => setGenStatus(null)} className="shrink-0 text-gray-400 hover:text-gray-200"><X size={16} /></button>
            )}
          </div>
          {generating && (
            <div className="mt-3 h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
              <div className="h-full w-1/3 rounded-full bg-indigo-400 animate-pulse" />
            </div>
          )}
        </div>
      )}
      <div className="p-5 space-y-4">
        <p className="text-[11px] text-gray-500 -mt-1">
          Edit directly as text/Markdown (use "- " for bullets, <span className="font-mono">**bold**</span> for emphasis) — the result is used as-is when generating the PPT.
        </p>
        {["global_economic", "indonesia_economic", "pharmaceutical"].map(secKey => {
          const colors = sectionColors[secKey];
          const section = data.content[secKey] || { title: "", text: "" };
          return (
            <div key={secKey} className={`rounded-xl border ${colors.border} ${colors.bg} overflow-hidden`}>
              <div className={`px-4 py-2.5 border-b border-gray-700 ${colors.header} flex items-center gap-2`}>
                <span className="text-sm">{colors.icon}</span>
                <span className={`text-xs font-bold uppercase tracking-wider ${colors.title}`}>{section.title}</span>
              </div>
              <div className="p-4">
                <textarea
                  rows={10}
                  className={`${TA} !text-xs font-mono`}
                  placeholder={"- **Label**: value\n- **Label**: value"}
                  value={section.text || ""}
                  onChange={e => updateSectionText(secKey, e.target.value)}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
    </div>
  );
}

/* ─── Section: Simulation — Required Columns reference ───────────────────────
   Every Simulation Data upload parses a fixed-cell-position Excel template
   (not a plain header-row table), so users can't tell what a file needs just
   by looking at column headers — this documents the exact cell/column each
   importer reads, mirroring the "Required Columns" reference already used
   for HRGA uploads (see AttendanceUpload.jsx). */
function SimColumnsReference({ cfg }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 mb-4">
      <button onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-gray-300 hover:text-white transition-colors">
        <div className="flex items-center gap-2">
          <FileSpreadsheet size={14} className="text-gray-500" />
          Required Columns / Template Format
        </div>
        {open ? <ChevronUp size={15} className="text-gray-500" /> : <ChevronDown size={15} className="text-gray-500" />}
      </button>
      {open && (
        <div className="border-t border-gray-800 px-5 py-4 space-y-4">
          <div className="flex gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>
              Reference file: <strong>{cfg.example}</strong>.{" "}
              {cfg.signature
                ? <>Sheet is recognized by cell <strong>{cfg.signature.cell}</strong> containing <strong>"{cfg.signature.value}"</strong>{cfg.signature.note ? ` — ${cfg.signature.note}` : ""}.</>
                : <>This upload has <strong>no signature marker</strong> — it always reads the first sheet in the workbook, whatever it's named.</>}
            </span>
          </div>

          {cfg.metaFields?.length > 0 && (
            <div>
              <div className="text-xs text-gray-500 font-medium mb-1.5">Meta Fields (fixed cell position)</div>
              <div className="overflow-x-auto rounded-lg border border-gray-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Cell</th>
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Field</th>
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {cfg.metaFields.map((f, i) => (
                      <tr key={i}>
                        <td className="px-3 py-1.5 font-mono text-cyan-400">{f.cell}</td>
                        <td className="px-3 py-1.5 text-gray-200 font-medium">{f.name}</td>
                        <td className="px-3 py-1.5 text-gray-500">{f.note || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {cfg.sections.map((sec, si) => (
            <div key={si}>
              <div className="text-xs text-gray-500 font-medium mb-1.5">
                {sec.label}{sec.startRow ? ` — data starts row ${sec.startRow}` : ""}
                {sec.note && <span className="font-normal text-gray-600"> ({sec.note})</span>}
              </div>
              <div className="overflow-x-auto rounded-lg border border-gray-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Col</th>
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Field</th>
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Required</th>
                      <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {sec.columns.map((c, i) => (
                      <tr key={i}>
                        <td className="px-3 py-1.5 font-mono text-cyan-400 whitespace-nowrap">{c.col}</td>
                        <td className="px-3 py-1.5 text-gray-200 font-medium">{c.name}</td>
                        <td className="px-3 py-1.5">
                          {c.required === true && <span className="text-red-400 font-semibold">Yes</span>}
                          {c.required === "either" && <span className="text-amber-400 font-semibold">One of</span>}
                          {!c.required && <span className="text-gray-600">No</span>}
                        </td>
                        <td className="px-3 py-1.5 text-gray-500">{c.note || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {cfg.notes?.length > 0 && (
            <ul className="list-disc list-inside space-y-1 text-xs text-gray-500">
              {cfg.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

const SIM_COLUMNS = {
  data_collection: {
    example: "(P1-M) Purchase plan_Material.xlsx",
    signature: { cell: "A1", value: "[ P1 ]", note: "checked per sheet — a workbook can hold multiple data sheets (Summary/Local/CMO/Export), each imported as its own plan" },
    metaFields: [
      { cell: "D6",  name: "Type" },
      { cell: "D9",  name: "Department" },
      { cell: "D11", name: "Team Code" },
      { cell: "E11", name: "Team Name" },
      { cell: "X12", name: "Exchange Rate" },
    ],
    sections: [
      {
        label: "Item grid — Order row",
        startRow: 15,
        columns: [
          { col: "A",     name: "No", required: true },
          { col: "B",     name: "Type", required: false },
          { col: "C",     name: "Item Code No", required: false },
          { col: "D",     name: "Item Code Name", required: true },
          { col: "E",     name: "UOM", required: false },
          { col: "F",     name: "MOQ", required: false },
          { col: "G",     name: "Stock", required: false },
          { col: "H",     name: "QTY Needed", required: false },
          { col: "I",     name: "Final QTY to Order", required: false },
          { col: "J",     name: "(spacer, not read)", required: false },
          { col: "K – V", name: "Jan – Dec Order Quantity", required: false, note: "12 columns" },
          { col: "W",     name: "(not read)", required: false, note: "template may show a 1H subtotal here — ignored by the importer" },
          { col: "X",     name: "Order Total", required: false },
          { col: "Y",     name: "Unit Price (Orig)", required: false },
          { col: "Z",     name: "Unit Price (IDR)", required: false },
          { col: "AA",    name: "Total Price (Rp)", required: false },
        ],
      },
      {
        label: "Received row (the row directly below each Order row)",
        columns: [
          { col: "K – V", name: "Jan – Dec Received Quantity", required: false, note: "12 columns" },
          { col: "X",     name: "Received Total", required: false },
        ],
      },
    ],
    notes: [
      "A row counts as the Received row only if its own No (A) AND Item Code Name (D) are BOTH blank — it's identified purely by position, not a label. If either is filled, it's read as a brand-new item instead of a pair.",
      "Columns J, W, Y, Z, AA are not read at all on the Received row even if the template shows values there.",
    ],
  },

  sales_plan: {
    example: "(S1) Sales plan_Value.xlsx",
    signature: null,
    metaFields: [
      { cell: "C6",  name: "Type" },
      { cell: "C8",  name: "Area" },
      { cell: "C10", name: "Department" },
      { cell: "C12", name: "Team Code" },
      { cell: "D12", name: "Team Name" },
    ],
    sections: [
      {
        label: "Product grid",
        startRow: 16,
        columns: [
          { col: "A",     name: "No", required: true },
          { col: "B",     name: "Product", required: true },
          { col: "C",     name: "(skipped, not read)", required: false },
          { col: "D – O", name: "Jan – Dec Sales Value (Rp)", required: false, note: "12 columns — this is Amount, not quantity" },
          { col: "P",     name: "Total Value", required: false },
          { col: "Q",     name: "Total Unit", required: false },
          { col: "R",     name: "Price (Rp)", required: false },
        ],
      },
    ],
    notes: [
      "No sheet-marker check on this upload — it always reads the FIRST sheet in the workbook, regardless of its name.",
      "A row whose [ Type ] meta (cell C6) is left blank is treated as a pre-aggregated \"Total\" rollup rather than a real market/customer line.",
    ],
  },

  personnel_plan: {
    example: "Personal plan template.xlsx",
    signature: { cell: "A1", value: "[ H1 ]", note: "checked across all worksheets" },
    metaFields: [
      { cell: "C6", name: "Type" },
      { cell: "C9", name: "Department" },
    ],
    sections: [
      {
        label: "Block A — Headcount by Level",
        note: "header row located by searching column A for the text \"Level\"; data starts 3 rows below it",
        columns: [
          { col: "A", name: "Level", required: true },
          { col: "C", name: "Prev. Year — Permanent", required: false },
          { col: "D", name: "Prev. Year — Temporary", required: false },
          { col: "E", name: "Prev. Year — Total", required: false },
          { col: "F", name: "Curr. Year — Permanent", required: false },
          { col: "G", name: "Curr. Year — Temporary", required: false },
          { col: "H", name: "Curr. Year — Total", required: false },
          { col: "I", name: "Increase — Permanent", required: false },
          { col: "J", name: "Increase — Temporary", required: false },
          { col: "K", name: "Increase — Total", required: false },
          { col: "L", name: "Notes", required: false },
        ],
      },
      {
        label: "Block B — Recruitment Schedule (Permanent)",
        note: "located by searching for its section title, then the nearest \"Level\" header below it; data starts 2 rows below that header",
        columns: [
          { col: "A",     name: "Level", required: true },
          { col: "C – N", name: "Jan – Dec Recruitment Headcount", required: false, note: "12 columns" },
          { col: "O",     name: "Total", required: false },
        ],
      },
      {
        label: "Block C — Recruitment Schedule (Temporary)",
        note: "same layout as Block B, located below it",
        columns: [
          { col: "A",     name: "Level", required: true },
          { col: "C – N", name: "Jan – Dec Recruitment Headcount", required: false, note: "12 columns" },
          { col: "O",     name: "Total", required: false },
        ],
      },
    ],
    notes: [
      "Row positions can shift — each block's header is found by searching for its label text, not a fixed row number — but the columns within a block are always fixed as listed above.",
      "A row with column A exactly \"Total\" ends that block and is captured as the block's total rather than a data row.",
      "Import fails only if all three blocks come back completely empty.",
    ],
  },

  manufacture_plan: {
    example: "manufacture plan template.xlsx",
    signature: { cell: "A1", value: "[ M1 ]", note: "checked across all worksheets" },
    metaFields: [
      { cell: "C6",  name: "Type" },
      { cell: "C9",  name: "Department" },
      { cell: "C11", name: "Team Code" },
      { cell: "D11", name: "Team Name" },
      { cell: "G13", name: "Plan Year" },
    ],
    sections: [
      {
        label: "Item grid",
        startRow: 15,
        columns: [
          { col: "A",     name: "No", required: true },
          { col: "B",     name: "Customer", required: false },
          { col: "C",     name: "Item Code", required: false },
          { col: "D",     name: "Item Name", required: true },
          { col: "E",     name: "Batch Size (Vial)", required: false },
          { col: "F",     name: "Yield (%)", required: false },
          { col: "G – R", name: "Jan – Dec Production Plan", required: false, note: "12 columns, batch quantity" },
          { col: "S",     name: "Total Batch", required: false },
          { col: "T",     name: "Total Qty (Before Yield)", required: false },
          { col: "U",     name: "Total Qty (After Yield)", required: false },
          { col: "V",     name: "Sales Quantity", required: false },
          { col: "W",     name: "Coverage", required: false },
        ],
      },
    ],
    notes: [
      "Row scan stops when column A is blank or its text equals \"Total\".",
    ],
  },

  investment_plan: {
    example: "investment plan template.xlsx",
    signature: { cell: "A1", value: "[ I1 ]", note: "checked across all worksheets" },
    metaFields: [
      { cell: "C6",  name: "Type" },
      { cell: "C9",  name: "Department" },
      { cell: "C11", name: "Team Code", note: "single combined field in this template, e.g. \"All\"" },
      { cell: "I13", name: "Plan Year" },
    ],
    sections: [
      {
        label: "Item grid",
        startRow: 15,
        columns: [
          { col: "A",     name: "No", required: false },
          { col: "B",     name: "Clarification", required: true },
          { col: "C",     name: "Priority", required: false },
          { col: "D",     name: "Item", required: false },
          { col: "E",     name: "Purpose", required: false },
          { col: "F",     name: "Picture", required: false },
          { col: "G",     name: "QTY", required: false },
          { col: "H",     name: "Lifetime (Year)", required: false },
          { col: "I – T", name: "Jan – Dec Investment Amount", required: false, note: "12 columns" },
          { col: "U",     name: "Total", required: false },
          { col: "V",     name: "Notes (Replacement/Additional)", required: false },
        ],
      },
    ],
    notes: [
      "Team Name is not read from this template at all — always stored blank.",
      "Row scan stops when column A equals \"Total\". A row is skipped (scan continues) if Clarification (B) is blank.",
    ],
  },

  opex_plan: {
    example: "(O1) OPEX Plan_Summary_Department.xlsx",
    signature: { cell: "A1", value: "[ O1 ]", note: "checked per sheet — a workbook can hold multiple department/team sheets" },
    metaFields: [
      { cell: "C6",  name: "Type" },
      { cell: "C9",  name: "Department" },
      { cell: "C11", name: "Team Code" },
      { cell: "D11", name: "Team Name" },
    ],
    sections: [
      {
        label: "Item grid",
        startRow: 15,
        columns: [
          { col: "A",     name: "No", required: false, note: "merged-cell group header — carried forward onto continuation rows" },
          { col: "B",     name: "Managerial Account No", required: false, note: "carried forward" },
          { col: "C",     name: "Managerial Account Name", required: false, note: "carried forward" },
          { col: "D",     name: "Chart of Account No", required: "either" },
          { col: "E",     name: "Chart of Account Name", required: "either" },
          { col: "F",     name: "Controll/Uncontrolled", required: false },
          { col: "G",     name: "Sales & Mkt Allocation", required: false },
          { col: "H",     name: "Strategy Development Allocation", required: false },
          { col: "I",     name: "Plant Allocation", required: false },
          { col: "J",     name: "Admin Allocation", required: false },
          { col: "K – V", name: "Jan – Dec OPEX Budget", required: false, note: "12 columns" },
          { col: "W",     name: "Total", required: false },
        ],
      },
    ],
    notes: [
      "A row requires at least one of Chart of Account No (D) or Chart of Account Name (E) filled — rows with both blank are skipped.",
      "No / Managerial Account No / Managerial Account Name (A-C) follow the template's merged cells — only need to be filled on a group's first row, the importer carries them onto the rows below.",
      "Row scan stops at a row whose No (A) equals \"Total\".",
    ],
  },
};

/* ─── Section: Simulation ──────────────────────────── */
const SIM_SUBTABS = [
  { id: "data_collection",  label: "Purchase Plan",     icon: FileText },
  { id: "sales_plan",       label: "Sales Plan",        icon: BarChart },
  { id: "personnel_plan",   label: "Personnel Plan",    icon: Users },
  { id: "manufacture_plan", label: "Manufacture Plan",  icon: Factory },
  { id: "investment_plan",  label: "Investment Plan",   icon: Banknote },
  { id: "opex_plan",        label: "OPEX Plan",         icon: Wallet },
];

function SimulationSection({ year }) {
  const [subTab, setSubTab] = useState("data_collection");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-gray-800/60 border border-gray-700">
          {SIM_SUBTABS.map(t => (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                subTab === t.id ? "bg-violet-500/20 border border-violet-500/40 text-violet-300"
                                : "text-gray-500 hover:text-gray-300"
              }`}>
              <t.icon size={11} />{t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Plan Year: <span className="text-violet-400 font-bold">{year}</span></label>
        </div>
      </div>
      {subTab === "data_collection" && <PurchasePlanPanel year={year} />}
      {subTab === "sales_plan"      && <SalesPlanPanel year={year} />}
      {subTab === "personnel_plan"  && <PersonnelPlanPanel year={year} />}
      {subTab === "manufacture_plan" && <ManufacturePlanPanel year={year} />}
      {subTab === "investment_plan"  && <InvestmentPlanPanel year={year} />}
      {subTab === "opex_plan"        && <OpexPlanPanel year={year} />}
    </div>
  );
}

/* ══ Purchase Plan (Material) Panel ═══════════════════════════════════════════ */
/* Field set + Excel format reference: sumber/(P1-M) Purchase plan_Material.xlsx
   Each item has an "Order" row (planned monthly order qty + price) and a
   paired "Received" row (planned monthly received qty), matching the sheet. */

const PP_CATEGORIES = ["Summary", "Local", "CMO", "Export"];
const PP_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const DEFAULT_PP_ITEM = () => ({
  no: 1, type: "", item_code_no: "", item_code_name: "New Item", uom: "",
  moq: null, stock: null, qty_needed: null, final_qty_to_order: null,
  order: Array(12).fill(0), order_total: 0, unit_price_orig: 0, unit_price_idr: 0, total_price: 0,
  received: Array(12).fill(0), received_total: 0,
});

const DEFAULT_PP_CONTENT = () => ({
  meta: { type: "", department: "", team_code: "", team_name: "", exchange_rate: 0 },
  items: [DEFAULT_PP_ITEM()],
});

function PurchasePlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    plan_category: "Local",
    department: "",
    team_code: "",
    team_name: "",
    content: DEFAULT_PP_CONTENT(),
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listPurchasePlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({
      id: null,
      plan_year: year,
      plan_category: "Local",
      department: "",
      team_code: "",
      team_name: "",
      content: DEFAULT_PP_CONTENT(),
      status: "draft",
    });
    setShowForm(false);
  };

  const openCreate = () => {
    resetForm();
    setShowForm(true);
  };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      plan_category: plan.plan_category,
      department: plan.department,
      team_code: plan.team_code,
      team_name: plan.team_name,
      content: plan.content || DEFAULT_PP_CONTENT(),
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertPurchasePlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateItem = (idx, patch) => {
    setForm(prev => {
      const items = [...prev.content.items];
      items[idx] = { ...items[idx], ...patch };
      return { ...prev, content: { ...prev.content, items } };
    });
  };

  const updateItemMonth = (idx, field, monthIdx, val) => {
    setForm(prev => {
      const items = [...prev.content.items];
      const arr = [...items[idx][field]];
      arr[monthIdx] = Number(val) || 0;
      const total = arr.reduce((a, b) => a + (Number(b) || 0), 0);
      items[idx] = { ...items[idx], [field]: arr, [`${field}_total`]: total };
      return { ...prev, content: { ...prev.content, items } };
    });
  };

  const addItem = () => {
    setForm(prev => {
      const items = [...prev.content.items];
      items.push({ ...DEFAULT_PP_ITEM(), no: items.length + 1 });
      return { ...prev, content: { ...prev.content, items } };
    });
  };

  const removeItem = (idx) => {
    setForm(prev => ({
      ...prev,
      content: { ...prev.content, items: prev.content.items.filter((_, i) => i !== idx) },
    }));
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadPurchasePlanExcel(file, year);
      if (res.success) {
        const summary = res.imported.map(x => `${x.category} (${x.items} items)`).join(", ");
        alert(`Import successful: ${summary}`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  const fmtNum = (v) => Number(v || 0).toLocaleString();

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Purchase Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Input Purchase Plan material · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5">
        <SimColumnsReference cfg={SIM_COLUMNS.data_collection} />
        {loading ? (
          <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : !showForm ? (
          <>
            <div className="mb-4">
              <label className="text-xs text-gray-500 mb-1 block">Select Purchase Plan:</label>
              <select value={selectedPlan?.id || ""} onChange={e => {
                const plan = plans.find(p => String(p.id) === e.target.value);
                setSelectedPlan(plan || null);
              }} className={`${SELECT} w-full max-w-md`}>
                <option value="">-- Select Purchase Plan --</option>
                {plans.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.plan_year} - {p.department || "(no dept)"} / {p.team_name || "(no team)"} [{p.plan_category}]
                  </option>
                ))}
              </select>
            </div>
            {selectedPlan && selectedPlan.content && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span className="px-2 py-1 rounded bg-violet-500/10 border border-violet-500/30 text-violet-300 font-medium">{selectedPlan.plan_category}</span>
                  {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                  <span className="text-gray-500">{selectedPlan.department} / {selectedPlan.team_code} - {selectedPlan.team_name}</span>
                  {!!selectedPlan.content.meta?.exchange_rate && <span className="text-gray-500">Kurs: {fmtNum(selectedPlan.content.meta.exchange_rate)}</span>}
                </div>
                <PurchasePlanTable items={selectedPlan.content.items || []} editable={false} />
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Category">
                <select className={`${SELECT}`} value={form.plan_category} onChange={e => setForm({ ...form, plan_category: e.target.value })}>
                  {PP_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. Plant" />
              </Field>
              <Field label="Team Code">
                <input className={`${INP}`} value={form.team_code} onChange={e => setForm({ ...form, team_code: e.target.value })} placeholder="e.g. 35" />
              </Field>
              <Field label="Team Name">
                <input className={`${INP}`} value={form.team_name} onChange={e => setForm({ ...form, team_name: e.target.value })} placeholder="e.g. Production Planning & Warehouse" />
              </Field>
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-gray-500">Type:</label>
              <input className={`${INP} max-w-xs`} value={form.content.meta?.type || ""}
                onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, type: e.target.value } } })}
                placeholder="e.g. API, Excipient & Packaging - Local" />
              <label className="text-xs text-gray-500">Kurs USD/IDR:</label>
              <input type="number" className={`${INP} max-w-[120px]`} value={form.content.meta?.exchange_rate || 0}
                onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, exchange_rate: Number(e.target.value) || 0 } } })} />
              <label className="text-xs text-gray-500">Status:</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                <option value="draft">Draft</option>
                <option value="final">Final</option>
              </select>
            </div>
            <PurchasePlanTable
              items={form.content.items || []}
              editable={true}
              onUpdateItem={updateItem}
              onUpdateMonth={updateItemMonth}
              onRemove={removeItem}
            />
            <button onClick={addItem} className={BTN_SM("violet")}><Plus size={11} /> Add Item</button>
          </div>
        )}
      </div>
    </div>
  );
}

function PurchasePlanTable({ items, editable, onUpdateItem, onUpdateMonth, onRemove }) {
  const TH = "sticky top-0 z-10 bg-gray-800 px-2 py-1.5 text-left text-gray-400 border border-gray-700 font-semibold whitespace-nowrap text-center";
  const TD = "px-2 py-1 border border-gray-700 text-right font-mono text-xs";
  const fmtNum = (v) => Number(v || 0).toLocaleString();

  return (
    <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
      <table className="w-full border-collapse text-xs" style={{ minWidth: 1600 }}>
        <thead>
          <tr className="bg-gray-800/80">
            <th className={`${TH} w-16`}>No</th>
            <th className={TH}>Type</th>
            <th className={TH}>Item Code</th>
            <th className={TH}>Item Name</th>
            <th className={TH}>UOM</th>
            <th className={TH}>MOQ</th>
            <th className={TH}>Stock</th>
            <th className={TH}>Qty Needed</th>
            <th className={TH}>Final Qty</th>
            <th className={`${TH} w-14`}></th>
            {PP_MONTHS.map(m => <th key={m} className={`${TH} w-14`}>{m}</th>)}
            <th className={TH}>Total</th>
            <th className={TH}>Unit Price (Orig)</th>
            <th className={TH}>Unit Price (IDR)</th>
            <th className={TH}>Total Price (Rp)</th>
            {editable && <th className={`${TH} w-10`}></th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => ([
              <tr key={`${idx}-order`} className="border-b border-gray-800 hover:bg-gray-800/30">
                <td className={`${TD} text-center`} rowSpan={2}>{item.no}</td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input className={`${INP} !text-xs`} value={item.type} onChange={e => onUpdateItem(idx, { type: e.target.value })} />
                            : <span className="text-gray-300">{item.type}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input className={`${INP} !text-xs`} value={item.item_code_no} onChange={e => onUpdateItem(idx, { item_code_no: e.target.value })} />
                            : <span className="text-gray-300">{item.item_code_no}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input className={`${INP} !text-xs`} value={item.item_code_name} onChange={e => onUpdateItem(idx, { item_code_name: e.target.value })} />
                            : <span className="text-gray-300">{item.item_code_name}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input className={`${INP} !text-xs`} value={item.uom} onChange={e => onUpdateItem(idx, { uom: e.target.value })} />
                            : <span className="text-gray-300">{item.uom}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.moq ?? ""} onChange={e => onUpdateItem(idx, { moq: e.target.value === "" ? null : Number(e.target.value) })} />
                            : <span className="text-gray-400">{item.moq ?? "—"}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.stock ?? ""} onChange={e => onUpdateItem(idx, { stock: e.target.value === "" ? null : Number(e.target.value) })} />
                            : <span className="text-gray-400">{item.stock ?? "—"}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.qty_needed ?? ""} onChange={e => onUpdateItem(idx, { qty_needed: e.target.value === "" ? null : Number(e.target.value) })} />
                            : <span className="text-gray-400">{item.qty_needed ?? "—"}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.final_qty_to_order ?? ""} onChange={e => onUpdateItem(idx, { final_qty_to_order: e.target.value === "" ? null : Number(e.target.value) })} />
                            : <span className="text-gray-400">{item.final_qty_to_order ?? "—"}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700 text-center text-violet-400 font-semibold">Order</td>
                {PP_MONTHS.map((m, mi) => (
                  <td key={m} className={TD}>
                    {editable
                      ? <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={item.order[mi]} onChange={e => onUpdateMonth(idx, "order", mi, e.target.value)} />
                      : fmtNum(item.order[mi])}
                  </td>
                ))}
                <td className={`${TD} font-bold text-violet-400`} rowSpan={1}>{fmtNum(item.order_total)}</td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.unit_price_orig} onChange={e => onUpdateItem(idx, { unit_price_orig: Number(e.target.value) || 0 })} />
                            : <span className="text-gray-300 font-mono">{fmtNum(item.unit_price_orig)}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.unit_price_idr} onChange={e => onUpdateItem(idx, { unit_price_idr: Number(e.target.value) || 0 })} />
                            : <span className="text-gray-300 font-mono">{fmtNum(item.unit_price_idr)}</span>}
                </td>
                <td className="px-2 py-1 border border-gray-700" rowSpan={2}>
                  {editable ? <input type="number" className={`${INP} !text-xs`} value={item.total_price} onChange={e => onUpdateItem(idx, { total_price: Number(e.target.value) || 0 })} />
                            : <span className="text-sky-400 font-mono font-bold">{fmtNum(item.total_price)}</span>}
                </td>
                {editable && (
                  <td className="px-2 py-1 border border-gray-700 text-center" rowSpan={2}>
                    <button onClick={() => onRemove(idx)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                  </td>
                )}
              </tr>,
              <tr key={`${idx}-received`} className="border-b border-gray-800 hover:bg-gray-800/30">
                <td className="px-2 py-1 border border-gray-700 text-center text-sky-400 font-semibold">Received</td>
                {PP_MONTHS.map((m, mi) => (
                  <td key={m} className={TD}>
                    {editable
                      ? <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={item.received[mi]} onChange={e => onUpdateMonth(idx, "received", mi, e.target.value)} />
                      : fmtNum(item.received[mi])}
                  </td>
                ))}
                <td className={`${TD} font-bold text-sky-400`}>{fmtNum(item.received_total)}</td>
              </tr>
          ]))}
        </tbody>
      </table>
    </div>
  );
}

/* ══ Personnel Plan Panel ("Personal Plan Data") ══════════════════════════════ */
/* Field set + Excel format reference: sumber/Personal plan template.xlsx —
   headcount by level (prev/curr year Permanent/Temporary/Total + Increasing)
   plus two recruitment schedules (Permanent, Temporary) by level x month. */

const DEFAULT_PERSONNEL_HC_ROW = () => ({
  level: "New Level",
  prev_permanent: 0, prev_temporary: 0, prev_total: 0,
  curr_permanent: 0, curr_temporary: 0, curr_total: 0,
  inc_permanent: 0, inc_temporary: 0, inc_total: 0,
  notes: "",
});
const DEFAULT_PERSONNEL_REC_ROW = () => ({ level: "New Level", months: Array(12).fill(0), total: 0 });

const DEFAULT_PERSONNEL_CONTENT = (year) => ({
  meta: { type: "", department: "" },
  headcount: { year_prev: year - 1, year_curr: year, rows: [DEFAULT_PERSONNEL_HC_ROW()], total: null },
  recruitment_permanent: { year, rows: [DEFAULT_PERSONNEL_REC_ROW()], total: null },
  recruitment_temporary: { year, rows: [DEFAULT_PERSONNEL_REC_ROW()], total: null },
});

function PersonnelPlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    department: "",
    content: DEFAULT_PERSONNEL_CONTENT(year),
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listPersonnelPlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({ id: null, plan_year: year, department: "", content: DEFAULT_PERSONNEL_CONTENT(year), status: "draft" });
    setShowForm(false);
  };

  const openCreate = () => { resetForm(); setShowForm(true); };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      department: plan.department,
      content: plan.content || DEFAULT_PERSONNEL_CONTENT(year),
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertPersonnelPlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateHcRow = (idx, patch) => {
    setForm(prev => {
      const rows = [...prev.content.headcount.rows];
      rows[idx] = { ...rows[idx], ...patch };
      return { ...prev, content: { ...prev.content, headcount: { ...prev.content.headcount, rows } } };
    });
  };
  const addHcRow = () => setForm(prev => ({
    ...prev, content: { ...prev.content, headcount: { ...prev.content.headcount, rows: [...prev.content.headcount.rows, DEFAULT_PERSONNEL_HC_ROW()] } },
  }));
  const removeHcRow = (idx) => setForm(prev => ({
    ...prev, content: { ...prev.content, headcount: { ...prev.content.headcount, rows: prev.content.headcount.rows.filter((_, i) => i !== idx) } },
  }));

  const updateRecRow = (block, idx, patch) => {
    setForm(prev => {
      const rows = [...prev.content[block].rows];
      rows[idx] = { ...rows[idx], ...patch };
      return { ...prev, content: { ...prev.content, [block]: { ...prev.content[block], rows } } };
    });
  };
  const updateRecMonth = (block, idx, monthIdx, val) => {
    setForm(prev => {
      const rows = [...prev.content[block].rows];
      const months = [...rows[idx].months];
      months[monthIdx] = Number(val) || 0;
      rows[idx] = { ...rows[idx], months, total: months.reduce((a, b) => a + (Number(b) || 0), 0) };
      return { ...prev, content: { ...prev.content, [block]: { ...prev.content[block], rows } } };
    });
  };
  const addRecRow = (block) => setForm(prev => ({
    ...prev, content: { ...prev.content, [block]: { ...prev.content[block], rows: [...prev.content[block].rows, DEFAULT_PERSONNEL_REC_ROW()] } },
  }));
  const removeRecRow = (block, idx) => setForm(prev => ({
    ...prev, content: { ...prev.content, [block]: { ...prev.content[block], rows: prev.content[block].rows.filter((_, i) => i !== idx) } },
  }));

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadPersonnelPlanExcel(file, year);
      if (res.success) {
        const s = res.rows_imported;
        alert(`Import successful: Headcount ${s.headcount} rows, Recruitment Permanent ${s.recruitment_permanent} rows, Recruitment Temporary ${s.recruitment_temporary} rows (${res.data?.department}).`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  const fmtNum = (v) => Number(v || 0).toLocaleString();

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Personnel Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Personnel planning input (headcount & recruitment) · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5 space-y-5">
        <SimColumnsReference cfg={SIM_COLUMNS.personnel_plan} />
        {loading ? (
          <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : !showForm ? (
          <>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Select Personnel Plan:</label>
              <select value={selectedPlan?.id || ""} onChange={e => {
                const plan = plans.find(p => String(p.id) === e.target.value);
                setSelectedPlan(plan || null);
              }} className={`${SELECT} w-full max-w-md`}>
                <option value="">-- Select Personnel Plan --</option>
                {plans.map(p => (
                  <option key={p.id} value={p.id}>{p.plan_year} - {p.department || "(no dept)"}</option>
                ))}
              </select>
            </div>
            {selectedPlan && selectedPlan.content && (
              <>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                  <span className="text-gray-500">{selectedPlan.department}</span>
                </div>
                <PersonnelHeadcountTable data={selectedPlan.content.headcount} editable={false} fmtNum={fmtNum} />
                <PersonnelRecruitmentTable title="Recruitment Schedule - Permanent" data={selectedPlan.content.recruitment_permanent} editable={false} fmtNum={fmtNum} />
                <PersonnelRecruitmentTable title="Recruitment Schedule - Temporary" data={selectedPlan.content.recruitment_temporary} editable={false} fmtNum={fmtNum} />
              </>
            )}
          </>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. Plant" />
              </Field>
              <Field label="Type">
                <input className={`${INP}`} value={form.content.meta?.type || ""}
                  onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, type: e.target.value } } })}
                  placeholder="e.g. Personnel Plan - Department" />
              </Field>
              <Field label="Status">
                <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                  <option value="draft">Draft</option>
                  <option value="final">Final</option>
                </select>
              </Field>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-300 mb-2">Headcount by Level</h4>
              <PersonnelHeadcountTable data={form.content.headcount} editable={true} fmtNum={fmtNum}
                onUpdateRow={updateHcRow} onRemove={removeHcRow} />
              <button onClick={addHcRow} className={`${BTN_SM("violet")} mt-2`}><Plus size={11} /> Add Level</button>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-300 mb-2">Recruitment Schedule - Permanent</h4>
              <PersonnelRecruitmentTable data={form.content.recruitment_permanent} editable={true} fmtNum={fmtNum}
                onUpdateRow={(idx, patch) => updateRecRow("recruitment_permanent", idx, patch)}
                onUpdateMonth={(idx, mi, val) => updateRecMonth("recruitment_permanent", idx, mi, val)}
                onRemove={(idx) => removeRecRow("recruitment_permanent", idx)} />
              <button onClick={() => addRecRow("recruitment_permanent")} className={`${BTN_SM("violet")} mt-2`}><Plus size={11} /> Add Level</button>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-300 mb-2">Recruitment Schedule - Temporary</h4>
              <PersonnelRecruitmentTable data={form.content.recruitment_temporary} editable={true} fmtNum={fmtNum}
                onUpdateRow={(idx, patch) => updateRecRow("recruitment_temporary", idx, patch)}
                onUpdateMonth={(idx, mi, val) => updateRecMonth("recruitment_temporary", idx, mi, val)}
                onRemove={(idx) => removeRecRow("recruitment_temporary", idx)} />
              <button onClick={() => addRecRow("recruitment_temporary")} className={`${BTN_SM("violet")} mt-2`}><Plus size={11} /> Add Level</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PersonnelHeadcountTable({ data, editable, fmtNum, onUpdateRow, onRemove }) {
  if (!data) return null;
  const TH = "sticky top-0 z-10 bg-gray-800 px-2 py-1.5 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap";
  const TD = "px-2 py-1 border border-gray-700 text-right font-mono text-xs";
  return (
    <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
      <table className="w-full border-collapse text-xs" style={{ minWidth: 1100 }}>
        <thead>
          <tr className="bg-gray-800/80">
            <th className={`${TH} text-left`} rowSpan={2}>Level</th>
            <th className={TH} colSpan={3}>Dec {data.year_prev} (E)</th>
            <th className={TH} colSpan={3}>Dec {data.year_curr} (P)</th>
            <th className={TH} colSpan={3}>Increasing</th>
            <th className={TH} rowSpan={2}>Notes</th>
            {editable && <th className={TH} rowSpan={2}></th>}
          </tr>
          <tr className="bg-gray-800/80">
            {["Permanent","Temporary","Total","Permanent","Temporary","Total","Permanent","Temporary","Total"].map((h, i) => (
              <th key={i} className={`${TH} w-16`} style={{ top: "29px" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, idx) => (
            <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/30">
              <td className="px-2 py-1 border border-gray-700">
                {editable ? <input className={`${INP} !text-xs`} value={row.level} onChange={e => onUpdateRow(idx, { level: e.target.value })} />
                          : <span className="text-gray-300">{row.level}</span>}
              </td>
              {["prev_permanent","prev_temporary","prev_total","curr_permanent","curr_temporary","curr_total","inc_permanent","inc_temporary","inc_total"].map(key => (
                <td key={key} className={TD}>
                  {editable
                    ? <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={row[key]} onChange={e => onUpdateRow(idx, { [key]: Number(e.target.value) || 0 })} />
                    : fmtNum(row[key])}
                </td>
              ))}
              <td className="px-2 py-1 border border-gray-700">
                {editable ? <input className={`${INP} !text-xs`} value={row.notes} onChange={e => onUpdateRow(idx, { notes: e.target.value })} />
                          : <span className="text-gray-500">{row.notes}</span>}
              </td>
              {editable && (
                <td className="px-2 py-1 border border-gray-700 text-center">
                  <button onClick={() => onRemove(idx)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                </td>
              )}
            </tr>
          ))}
          {data.total && (
            <tr className="bg-gray-800/60 font-bold">
              <td className="px-2 py-1 border border-gray-700 text-gray-200">TOTAL</td>
              {["prev_permanent","prev_temporary","prev_total","curr_permanent","curr_temporary","curr_total","inc_permanent","inc_temporary","inc_total"].map(key => (
                <td key={key} className={`${TD} text-indigo-300`}>{fmtNum(data.total[key])}</td>
              ))}
              <td className="px-2 py-1 border border-gray-700"></td>
              {editable && <td className="px-2 py-1 border border-gray-700"></td>}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function PersonnelRecruitmentTable({ title, data, editable, fmtNum, onUpdateRow, onUpdateMonth, onRemove }) {
  if (!data) return null;
  const TH = "sticky top-0 z-10 bg-gray-800 px-2 py-1.5 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap";
  const TD = "px-2 py-1 border border-gray-700 text-right font-mono text-xs";
  return (
    <div className="space-y-1.5">
      {title && <p className="text-xs font-semibold text-gray-400">{title} · {data.year}</p>}
      <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
        <table className="w-full border-collapse text-xs" style={{ minWidth: 1000 }}>
          <thead>
            <tr className="bg-gray-800/80">
              <th className={`${TH} text-left`}>Level</th>
              {PP_MONTHS.map(m => <th key={m} className={`${TH} w-12`}>{m}</th>)}
              <th className={TH}>Total</th>
              {editable && <th className={TH}></th>}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, idx) => (
              <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/30">
                <td className="px-2 py-1 border border-gray-700">
                  {editable ? <input className={`${INP} !text-xs`} value={row.level} onChange={e => onUpdateRow(idx, { level: e.target.value })} />
                            : <span className="text-gray-300">{row.level}</span>}
                </td>
                {row.months.map((v, mi) => (
                  <td key={mi} className={TD}>
                    {editable
                      ? <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={v} onChange={e => onUpdateMonth(idx, mi, e.target.value)} />
                      : fmtNum(v)}
                  </td>
                ))}
                <td className={`${TD} font-bold text-violet-400`}>{fmtNum(row.total)}</td>
                {editable && (
                  <td className="px-2 py-1 border border-gray-700 text-center">
                    <button onClick={() => onRemove(idx)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                  </td>
                )}
              </tr>
            ))}
            {data.total && (
              <tr className="bg-gray-800/60 font-bold">
                <td className="px-2 py-1 border border-gray-700 text-gray-200">TOTAL</td>
                {data.total.months.map((v, mi) => (
                  <td key={mi} className={`${TD} text-indigo-300`}>{fmtNum(v)}</td>
                ))}
                <td className={`${TD} text-indigo-300`}>{fmtNum(data.total.total)}</td>
                {editable && <td className="px-2 py-1 border border-gray-700"></td>}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══ Manufacture Plan Panel ════════════════════════════════════════════════════ */
/* Field set + Excel format reference: sumber/manufacture plan template.xlsx —
   flat product/customer list with monthly batch qty + totals, mirrors
   SalesPlanPanel's shape (headers + rows array). */

const MFG_HEADERS = ["No", "Customer", "Item Code", "Name", "Batch Size (Vial)", "Yield (%)",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  "Total Batch", "Total Qty (Before Yield)", "Total Qty (After Yield)", "Sales Quantity", "Coverage"];

const DEFAULT_MFG_CONTENT = () => ({
  meta: { type: "", department: "", team_code: "", team_name: "", year: null },
  headers: MFG_HEADERS,
  rows: [[1, "", "", "New Product", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
});

function ManufacturePlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    department: "",
    team_code: "",
    team_name: "",
    content: DEFAULT_MFG_CONTENT(),
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listManufacturePlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({ id: null, plan_year: year, department: "", team_code: "", team_name: "", content: DEFAULT_MFG_CONTENT(), status: "draft" });
    setShowForm(false);
  };

  const openCreate = () => { resetForm(); setShowForm(true); };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      department: plan.department,
      team_code: plan.team_code,
      team_name: plan.team_name,
      content: plan.content || DEFAULT_MFG_CONTENT(),
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertManufacturePlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (rowIdx, colIdx, val) => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      newRows[rowIdx] = [...newRows[rowIdx]];
      if (colIdx <= 3) {
        newRows[rowIdx][colIdx] = val;
      } else {
        newRows[rowIdx][colIdx] = Number(val) || 0;
        if (colIdx >= 6 && colIdx <= 17) {
          // Jan-Dec — keep Total Batch (col 18) in sync with the months.
          newRows[rowIdx][18] = newRows[rowIdx].slice(6, 18).reduce((a, b) => a + (Number(b) || 0), 0);
        }
      }
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const addRow = () => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      const no = newRows.length + 1;
      newRows.push([no, "", "", "New Product", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const removeRow = (rowIdx) => {
    setForm(prev => ({ ...prev, content: { ...prev.content, rows: (prev.content.rows || []).filter((_, i) => i !== rowIdx) } }));
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadManufacturePlanExcel(file, year);
      if (res.success) {
        alert(`Import successful: ${res.rows_imported} product rows (${res.data?.department} / ${res.data?.team_name}).`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  const handleExportDetailReport = async () => {
    setExportingReport(true);
    try {
      const blobData = await pacApi.exportManufacturePlanDetailReport(year);
      const blob = new Blob([blobData], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Manufacturing_Plan_Detail_${year}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      let msg = "Export failed";
      if (e instanceof Blob) { try { msg = JSON.parse(await e.text())?.detail || msg; } catch (_) {} }
      else if (e?.detail) msg = e.detail; else if (e?.message) msg = e.message;
      alert("Export Detail Report error: " + msg);
    } finally {
      setExportingReport(false);
    }
  };

  const grandTotal = (colIdx) => (form.content.rows || []).reduce((sum, row) => sum + (Number(row[colIdx]) || 0), 0);
  const fmtNum = (v) => v === "" || v == null ? "—" : Number(v).toLocaleString();

  const NUMERIC_COLS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Manufacture Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Production planning input · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              <button onClick={handleExportDetailReport} disabled={exportingReport} className={BTN_SM("green")} title="Export Detail Manufacturing Plan report (format & calculation matching the reference BOM/Manufacturing Plan file)">
                {exportingReport ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                Export Detail Report
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5">
        <SimColumnsReference cfg={SIM_COLUMNS.manufacture_plan} />
        {loading ? (
          <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : !showForm ? (
          <>
            <div className="mb-4">
              <label className="text-xs text-gray-500 mb-1 block">Select Manufacture Plan:</label>
              <select value={selectedPlan?.id || ""} onChange={e => {
                const plan = plans.find(p => String(p.id) === e.target.value);
                setSelectedPlan(plan || null);
              }} className={`${SELECT} w-full max-w-md`}>
                <option value="">-- Select Manufacture Plan --</option>
                {plans.map(p => (
                  <option key={p.id} value={p.id}>{p.plan_year} - {p.department || "(no dept)"} / {p.team_name || "(no team)"}</option>
                ))}
              </select>
            </div>
            {selectedPlan && selectedPlan.content && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                  <span className="text-gray-500">{selectedPlan.department} / {selectedPlan.team_code} - {selectedPlan.team_name}</span>
                </div>
                <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
                  <table className="w-full border-collapse text-xs" style={{ minWidth: 1900 }}>
                    <thead>
                      <tr className="bg-gray-800/80">
                        {(selectedPlan.content.headers || MFG_HEADERS).map((h, ci) => (
                          <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedPlan.content.rows || []).map((row, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                          {row.map((val, ci) => (
                            <td key={ci} className={`px-2 py-1.5 border border-gray-700 ${NUMERIC_COLS.includes(ci) ? "text-right font-mono" : "text-left"}`}>
                              {NUMERIC_COLS.includes(ci) ? fmtNum(val) : val}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. Plant" />
              </Field>
              <Field label="Team Code">
                <input className={`${INP}`} value={form.team_code} onChange={e => setForm({ ...form, team_code: e.target.value })} placeholder="e.g. 35" />
              </Field>
              <Field label="Team Name">
                <input className={`${INP}`} value={form.team_name} onChange={e => setForm({ ...form, team_name: e.target.value })} placeholder="e.g. Production Planning & Warehouse" />
              </Field>
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-gray-500">Type:</label>
              <input className={`${INP} max-w-xs`} value={form.content.meta?.type || ""}
                onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, type: e.target.value } } })}
                placeholder="e.g. Commercial Production - Export" />
              <label className="text-xs text-gray-500">Status:</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                <option value="draft">Draft</option>
                <option value="final">Final</option>
              </select>
            </div>
            <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
              <table className="w-full border-collapse text-xs" style={{ minWidth: 2000 }}>
                <thead>
                  <tr className="bg-gray-800/80">
                    {(form.content.headers || MFG_HEADERS).map((h, ci) => (
                      <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                    <th className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center border border-gray-700 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.content.rows || []).map((row, ri) => (
                    <tr key={ri} className="border-b border-gray-800 hover:bg-gray-800/30">
                      <td className="px-2 py-1.5 border border-gray-700 text-center font-bold text-gray-400 w-10">{row[0]}</td>
                      {[1, 2, 3].map(ci => (
                        <td key={ci} className="px-2 py-1.5 border border-gray-700">
                          <input className={`${INP} !text-xs`} value={row[ci]} onChange={e => updateCell(ri, ci, e.target.value)} />
                        </td>
                      ))}
                      {row.slice(4).map((val, i) => {
                        const ci = i + 4;
                        return (
                          <td key={ci} className="px-2 py-1.5 border border-gray-700">
                            <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={val} onChange={e => updateCell(ri, ci, e.target.value)} />
                          </td>
                        );
                      })}
                      <td className="px-2 py-1.5 border border-gray-700 text-center">
                        <button onClick={() => removeRow(ri)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800/60">
                    <td colSpan={6} className="px-2 py-1.5 border border-gray-700 text-xs font-bold text-gray-300">GRAND TOTAL</td>
                    {[6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22].map(ci => (
                      <td key={ci} className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-gray-200">{grandTotal(ci).toLocaleString()}</td>
                    ))}
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <button onClick={addRow} className={BTN_SM("violet")}><Plus size={11} /> Add Product</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══ Investment Plan Panel ═════════════════════════════════════════════════════ */
/* Field set + Excel format reference: sumber/investment plan template.xlsx —
   flat capex category/item list with monthly spend + total, mirrors
   ManufacturePlanPanel's shape (headers + rows array). */

const INV_HEADERS = ["No", "Clarification", "Priority", "Item", "Purpose", "Picture", "QTY", "Lifetime (Year)",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  "Total", "Notes (Replacement/Additional)"];

const DEFAULT_INV_CONTENT = () => ({
  meta: { type: "", department: "", team_code: "", team_name: "", year: null },
  headers: INV_HEADERS,
  rows: [[1, "New Category", "", "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ""]],
});

function InvestmentPlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    department: "",
    team_code: "",
    team_name: "",
    content: DEFAULT_INV_CONTENT(),
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listInvestmentPlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({ id: null, plan_year: year, department: "", team_code: "", team_name: "", content: DEFAULT_INV_CONTENT(), status: "draft" });
    setShowForm(false);
  };

  const openCreate = () => { resetForm(); setShowForm(true); };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      department: plan.department,
      team_code: plan.team_code,
      team_name: plan.team_name,
      content: plan.content || DEFAULT_INV_CONTENT(),
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertInvestmentPlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (rowIdx, colIdx, val) => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      newRows[rowIdx] = [...newRows[rowIdx]];
      if ([1, 2, 3, 4, 5, 21].includes(colIdx)) {
        newRows[rowIdx][colIdx] = val;
      } else {
        newRows[rowIdx][colIdx] = Number(val) || 0;
        if (colIdx >= 8 && colIdx <= 19) {
          // Jan-Dec — keep Total (col 20) in sync with the months.
          newRows[rowIdx][20] = newRows[rowIdx].slice(8, 20).reduce((a, b) => a + (Number(b) || 0), 0);
        }
      }
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const addRow = () => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      const no = newRows.length + 1;
      newRows.push([no, "New Category", "", "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ""]);
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const removeRow = (rowIdx) => {
    setForm(prev => ({ ...prev, content: { ...prev.content, rows: (prev.content.rows || []).filter((_, i) => i !== rowIdx) } }));
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadInvestmentPlanExcel(file, year);
      if (res.success) {
        alert(`Import successful: ${res.rows_imported} category rows (${res.data?.department} / ${res.data?.team_name || res.data?.team_code}).`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  const grandTotal = (colIdx) => (form.content.rows || []).reduce((sum, row) => sum + (Number(row[colIdx]) || 0), 0);
  const fmtNum = (v) => v === "" || v == null ? "—" : Number(v).toLocaleString();

  const NUMERIC_COLS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Investment Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Investment (capex) planning input · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5">
        <SimColumnsReference cfg={SIM_COLUMNS.investment_plan} />
        {loading ? (
          <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : !showForm ? (
          <>
            <div className="mb-4">
              <label className="text-xs text-gray-500 mb-1 block">Select Investment Plan:</label>
              <select value={selectedPlan?.id || ""} onChange={e => {
                const plan = plans.find(p => String(p.id) === e.target.value);
                setSelectedPlan(plan || null);
              }} className={`${SELECT} w-full max-w-md`}>
                <option value="">-- Select Investment Plan --</option>
                {plans.map(p => (
                  <option key={p.id} value={p.id}>{p.plan_year} - {p.department || "(no dept)"} / {p.team_code || "(no team)"}</option>
                ))}
              </select>
            </div>
            {selectedPlan && selectedPlan.content && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                  <span className="text-gray-500">{selectedPlan.department} / {selectedPlan.team_code}</span>
                </div>
                <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
                  <table className="w-full border-collapse text-xs" style={{ minWidth: 1900 }}>
                    <thead>
                      <tr className="bg-gray-800/80">
                        {(selectedPlan.content.headers || INV_HEADERS).map((h, ci) => (
                          <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedPlan.content.rows || []).map((row, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                          {row.map((val, ci) => (
                            <td key={ci} className={`px-2 py-1.5 border border-gray-700 ${NUMERIC_COLS.includes(ci) ? "text-right font-mono" : "text-left"}`}>
                              {NUMERIC_COLS.includes(ci) ? fmtNum(val) : val}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. Plant" />
              </Field>
              <Field label="Team Code / Name">
                <input className={`${INP}`} value={form.team_code} onChange={e => setForm({ ...form, team_code: e.target.value })} placeholder="e.g. All" />
              </Field>
              <Field label="Type">
                <input className={`${INP}`} value={form.content.meta?.type || ""}
                  onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, type: e.target.value } } })}
                  placeholder="e.g. Investment - Department" />
              </Field>
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-gray-500">Status:</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                <option value="draft">Draft</option>
                <option value="final">Final</option>
              </select>
            </div>
            <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
              <table className="w-full border-collapse text-xs" style={{ minWidth: 2000 }}>
                <thead>
                  <tr className="bg-gray-800/80">
                    {(form.content.headers || INV_HEADERS).map((h, ci) => (
                      <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                    <th className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center border border-gray-700 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.content.rows || []).map((row, ri) => (
                    <tr key={ri} className="border-b border-gray-800 hover:bg-gray-800/30">
                      <td className="px-2 py-1.5 border border-gray-700 text-center font-bold text-gray-400 w-10">{row[0]}</td>
                      {[1, 2, 3, 4, 5].map(ci => (
                        <td key={ci} className="px-2 py-1.5 border border-gray-700">
                          <input className={`${INP} !text-xs`} value={row[ci]} onChange={e => updateCell(ri, ci, e.target.value)} />
                        </td>
                      ))}
                      {row.slice(6, 21).map((val, i) => {
                        const ci = i + 6;
                        return (
                          <td key={ci} className="px-2 py-1.5 border border-gray-700">
                            <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={val} onChange={e => updateCell(ri, ci, e.target.value)} />
                          </td>
                        );
                      })}
                      <td className="px-2 py-1.5 border border-gray-700">
                        <input className={`${INP} !text-xs`} value={row[21]} onChange={e => updateCell(ri, 21, e.target.value)} />
                      </td>
                      <td className="px-2 py-1.5 border border-gray-700 text-center">
                        <button onClick={() => removeRow(ri)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800/60">
                    <td colSpan={8} className="px-2 py-1.5 border border-gray-700 text-xs font-bold text-gray-300">GRAND TOTAL</td>
                    {[8,9,10,11,12,13,14,15,16,17,18,19,20].map(ci => (
                      <td key={ci} className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-gray-200">{grandTotal(ci).toLocaleString()}</td>
                    ))}
                    <td></td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <button onClick={addRow} className={BTN_SM("violet")}><Plus size={11} /> Add Category</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══ OPEX Plan Panel ═══════════════════════════════════════════════════════════ */

const OPEX_HEADERS = [
  "No", "Managerial Account No", "Managerial Account Name", "Chart of Account No", "Chart of Account Name",
  "Controll/Uncontrolled", "Sales & Mkt", "Strategy Development", "Plant", "Admin",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total",
];

const DEFAULT_OPEX_CONTENT = () => ({
  meta: { type: "", department: "", team_code: "", team_name: "" },
  headers: OPEX_HEADERS,
  rows: [[1, "", "New Account", "", "", "", "", "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
});

function OpexPlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    department: "",
    team_code: "",
    team_name: "",
    content: DEFAULT_OPEX_CONTENT(),
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listOpexPlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({ id: null, plan_year: year, department: "", team_code: "", team_name: "", content: DEFAULT_OPEX_CONTENT(), status: "draft" });
    setShowForm(false);
  };

  const openCreate = () => { resetForm(); setShowForm(true); };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      department: plan.department,
      team_code: plan.team_code,
      team_name: plan.team_name,
      content: plan.content || DEFAULT_OPEX_CONTENT(),
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertOpexPlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (rowIdx, colIdx, val) => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      newRows[rowIdx] = [...newRows[rowIdx]];
      if (colIdx >= 1 && colIdx <= 9) {
        newRows[rowIdx][colIdx] = val;
      } else {
        newRows[rowIdx][colIdx] = Number(val) || 0;
        if (colIdx >= 10 && colIdx <= 21) {
          // Jan-Dec — keep Total (col 22) in sync with the months.
          newRows[rowIdx][22] = newRows[rowIdx].slice(10, 22).reduce((a, b) => a + (Number(b) || 0), 0);
        }
      }
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const addRow = () => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      const no = newRows.length + 1;
      newRows.push([no, "", "New Account", "", "", "", "", "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const removeRow = (rowIdx) => {
    setForm(prev => ({ ...prev, content: { ...prev.content, rows: (prev.content.rows || []).filter((_, i) => i !== rowIdx) } }));
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadOpexPlanExcel(file, year);
      if (res.success) {
        const summary = (res.imported || []).map(x => `${x.sheet} (${x.rows} rows)`).join(", ");
        alert(`Import successful: ${res.imported?.length || 0} sheet(s) — ${summary}.`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  const grandTotal = (colIdx) => (form.content.rows || []).reduce((sum, row) => sum + (Number(row[colIdx]) || 0), 0);
  const fmtNum = (v) => v === "" || v == null ? "—" : Number(v).toLocaleString();

  const NUMERIC_COLS = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">OPEX Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Operational cost (OPEX) planning input · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5">
        <SimColumnsReference cfg={SIM_COLUMNS.opex_plan} />
        {loading ? (
          <div className="flex justify-center py-16 text-gray-500 text-sm gap-2"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : !showForm ? (
          <>
            <div className="mb-4">
              <label className="text-xs text-gray-500 mb-1 block">Select OPEX Plan:</label>
              <select value={selectedPlan?.id || ""} onChange={e => {
                const plan = plans.find(p => String(p.id) === e.target.value);
                setSelectedPlan(plan || null);
              }} className={`${SELECT} w-full max-w-md`}>
                <option value="">-- Select OPEX Plan --</option>
                {plans.map(p => (
                  <option key={p.id} value={p.id}>{p.plan_year} - {p.department || "(no dept)"} / {p.team_name || p.team_code || "(no team)"}</option>
                ))}
              </select>
            </div>
            {selectedPlan && selectedPlan.content && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                  <span className="text-gray-500">{selectedPlan.department} / {selectedPlan.team_name || selectedPlan.team_code}</span>
                </div>
                <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
                  <table className="w-full border-collapse text-xs" style={{ minWidth: 2400 }}>
                    <thead>
                      <tr className="bg-gray-800/80">
                        {(selectedPlan.content.headers || OPEX_HEADERS).map((h, ci) => (
                          <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedPlan.content.rows || []).map((row, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                          {row.map((val, ci) => (
                            <td key={ci} className={`px-2 py-1.5 border border-gray-700 ${NUMERIC_COLS.includes(ci) ? "text-right font-mono" : "text-left"}`}>
                              {NUMERIC_COLS.includes(ci) ? fmtNum(val) : val}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. Plant" />
              </Field>
              <Field label="Team Code / Name">
                <input className={`${INP}`} value={form.team_code} onChange={e => setForm({ ...form, team_code: e.target.value })} placeholder="e.g. All Plant Team" />
              </Field>
              <Field label="Type">
                <input className={`${INP}`} value={form.content.meta?.type || ""}
                  onChange={e => setForm({ ...form, content: { ...form.content, meta: { ...form.content.meta, type: e.target.value } } })}
                  placeholder="e.g. Opex - Department" />
              </Field>
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-gray-500">Status:</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                <option value="draft">Draft</option>
                <option value="final">Final</option>
              </select>
            </div>
            <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
              <table className="w-full border-collapse text-xs" style={{ minWidth: 2500 }}>
                <thead>
                  <tr className="bg-gray-800/80">
                    {(form.content.headers || OPEX_HEADERS).map((h, ci) => (
                      <th key={ci} className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center text-gray-400 border border-gray-700 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                    <th className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center border border-gray-700 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.content.rows || []).map((row, ri) => (
                    <tr key={ri} className="border-b border-gray-800 hover:bg-gray-800/30">
                      <td className="px-2 py-1.5 border border-gray-700 text-center font-bold text-gray-400 w-10">{row[0]}</td>
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(ci => (
                        <td key={ci} className="px-2 py-1.5 border border-gray-700">
                          <input className={`${INP} !text-xs`} value={row[ci]} onChange={e => updateCell(ri, ci, e.target.value)} />
                        </td>
                      ))}
                      {row.slice(10, 23).map((val, i) => {
                        const ci = i + 10;
                        return (
                          <td key={ci} className="px-2 py-1.5 border border-gray-700">
                            <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={val} onChange={e => updateCell(ri, ci, e.target.value)} />
                          </td>
                        );
                      })}
                      <td className="px-2 py-1.5 border border-gray-700 text-center">
                        <button onClick={() => removeRow(ri)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800/60">
                    <td colSpan={10} className="px-2 py-1.5 border border-gray-700 text-xs font-bold text-gray-300">GRAND TOTAL</td>
                    {[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22].map(ci => (
                      <td key={ci} className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-gray-200">{grandTotal(ci).toLocaleString()}</td>
                    ))}
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <button onClick={addRow} className={BTN_SM("violet")}><Plus size={11} /> Add Account</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══ Sales Plan Panel ══════════════════════════════════════════════════════════ */

const DEFAULT_SALES_PLAN_CONTENT = {
  headers: ["No", "Product / Description", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total Value", "Total Unit", "Price (Rp)"],
  rows: [
    ["1", "Product A", 100, 120, 110, 130, 140, 150, 160, 170, 180, 190, 200, 210, 1960, 12, 50000],
    ["2", "Product B", 200, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 310, 3060, 15, 75000],
    ["3", "Product C", 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260, 2460, 10, 60000],
  ],
};

function SalesPlanPanel({ year }) {
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportingGross, setExportingGross] = useState(false);
  const [exportingSummary, setExportingSummary] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    id: null,
    plan_year: year,
    department: "",
    team_code: "",
    team_name: "",
    plan_type: "value",
    content: DEFAULT_SALES_PLAN_CONTENT,
    status: "draft",
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pacApi.listSalesPlans({ plan_year: year });
      if (res.success) setPlans(res.data || []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  // Auto-select the first plan so the panel shows data immediately instead
  // of a blank dropdown-only view when the sub-tab is first opened.
  useEffect(() => {
    if (!showForm && plans.length > 0 && !plans.some(p => p.id === selectedPlan?.id)) {
      setSelectedPlan(plans[0]);
    }
  }, [plans, showForm, selectedPlan]);

  const resetForm = () => {
    setForm({
      id: null,
      plan_year: year,
      department: "",
      team_code: "",
      team_name: "",
      plan_type: "value",
      content: JSON.parse(JSON.stringify(DEFAULT_SALES_PLAN_CONTENT)),
      status: "draft",
    });
    setShowForm(false);
  };

  const openCreate = () => {
    resetForm();
    setShowForm(true);
  };

  const openEdit = (plan) => {
    setForm({
      id: plan.id,
      plan_year: plan.plan_year,
      department: plan.department,
      team_code: plan.team_code,
      team_name: plan.team_name,
      plan_type: plan.plan_type,
      content: plan.content || DEFAULT_SALES_PLAN_CONTENT,
      status: plan.status,
    });
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await pacApi.upsertSalesPlan({ ...form });
      if (res.success) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        await loadPlans();
        setShowForm(false);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (rowIdx, colIdx, val) => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      newRows[rowIdx] = [...newRows[rowIdx]];
      if (colIdx === 0 || colIdx === 1) {
        newRows[rowIdx][colIdx] = val;
      } else {
        newRows[rowIdx][colIdx] = Number(val) || 0;
      }
      const total = newRows[rowIdx].slice(2, 14).reduce((a, b) => a + (Number(b) || 0), 0);
      newRows[rowIdx][14] = total;
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const addRow = () => {
    setForm(prev => {
      const newRows = [...(prev.content.rows || [])];
      const no = newRows.length + 1;
      newRows.push([String(no), "New Product", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const removeRow = (rowIdx) => {
    setForm(prev => {
      const newRows = (prev.content.rows || []).filter((_, i) => i !== rowIdx);
      return { ...prev, content: { ...prev.content, rows: newRows } };
    });
  };

  const exportExcel = async (planType) => {
    const targetId = selectedPlan?.id;
    if (!targetId) {
      alert("Select a sales plan before exporting.");
      return;
    }
    setExporting(true);
    try {
      const res = await pacApi.exportSalesPlanExcel(targetId, planType);
      if (res.success) {
        alert(`Export successful: ${res.filename}`);
      } else {
        alert(res.error || "Export failed");
      }
    } catch (e) {
      alert("Export error: " + e.message);
    } finally {
      setExporting(false);
    }
  };

  const grandTotal = (colIdx) => {
    return (form.content.rows || []).reduce((sum, row) => sum + (Number(row[colIdx]) || 0), 0);
  };

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file next time
    if (!file) return;
    setUploading(true);
    try {
      const res = await pacApi.uploadSalesPlanExcel(file, year);
      if (res.success) {
        alert(`Import successful: ${res.rows_imported} product rows (${res.data?.department} / ${res.data?.team_name}).`);
        await loadPlans();
      } else {
        alert(res.error || "Import failed");
      }
    } catch (e) {
      alert("Import error: " + (e?.detail || e?.message || e));
    } finally {
      setUploading(false);
    }
  };

  // client.js's axios interceptor already unwraps response.data for every
  // call in this app, so `blobData` here IS the Blob itself — not {data: Blob}.
  const handleExportGrossSalesReport = async () => {
    setExportingGross(true);
    try {
      const blobData = await pacApi.exportGrossSalesReport(year);
      const blob = new Blob([blobData], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Gross_Sales_Report_${year}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      // Same interceptor rejects with error.response.data directly — with
      // responseType:"blob" that's a Blob containing the JSON error text.
      let msg = "Export failed";
      if (e instanceof Blob) {
        try { msg = JSON.parse(await e.text())?.detail || msg; } catch (_) {}
      } else if (e?.detail) {
        msg = e.detail;
      } else if (e?.message) {
        msg = e.message;
      }
      alert("Gross Sales Report error: " + msg);
    } finally {
      setExportingGross(false);
    }
  };

  const handleExportSalesSummary = async () => {
    setExportingSummary(true);
    try {
      const blobData = await pacApi.exportSalesSummary(year);
      const blob = new Blob([blobData], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Sales_Summary_${year}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      let msg = "Export failed";
      if (e instanceof Blob) {
        try { msg = JSON.parse(await e.text())?.detail || msg; } catch (_) {}
      } else if (e?.detail) {
        msg = e.detail;
      } else if (e?.message) {
        msg = e.message;
      }
      alert("Sales Summary error: " + msg);
    } finally {
      setExportingSummary(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Sales Plan Data</h3>
          <p className="text-xs text-gray-500 mt-0.5">Sales planning input · {year}</p>
        </div>
        <div className="flex gap-2">
          {!showForm ? (
            <>
              <button onClick={openCreate} className={BTN_SM("violet")}><Plus size={11} /> New Plan</button>
              <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleUploadFile} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className={BTN_SM("teal")}>
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                Upload Excel
              </button>
              {selectedPlan && (
                <button onClick={() => openEdit(selectedPlan)} className={BTN_SM("indigo")}><Edit3 size={11} /> Edit</button>
              )}
              <button onClick={() => exportExcel("value")} disabled={exporting || !selectedPlan} className={BTN_SM("sky")}>
                {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                Export S1 (Value)
              </button>
              <button onClick={() => exportExcel("unit")} disabled={exporting || !selectedPlan} className={BTN_SM("teal")}>
                {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                Export S2 (Unit)
              </button>
            </>
          ) : (
            <>
              <button onClick={save} disabled={saving} className={BTN_SM("green")}>
                {saving ? <Loader2 size={11} className="animate-spin" /> : saved ? <CheckCircle size={11} /> : <Save size={11} />}
                {saved ? "Saved!" : "Save"}
              </button>
              <button onClick={resetForm} className={BTN_SM("gray")}><X size={11} /> Cancel</button>
            </>
          )}
        </div>
      </div>
      <div className="p-5">
        <SimColumnsReference cfg={SIM_COLUMNS.sales_plan} />
        {!showForm ? (
          <>
            <div className="mb-4 flex items-end gap-3">
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">Select Sales Plan:</label>
                <select value={selectedPlan?.id || ""} onChange={e => {
                  const plan = plans.find(p => String(p.id) === e.target.value);
                  setSelectedPlan(plan || null);
                }} className={`${SELECT} w-full max-w-md`}>
                  <option value="">-- Select Sales Plan --</option>
                  {plans.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.plan_year} - {p.department || "(no dept)"} / {p.team_code || "(no team)"} [{p.plan_type}]
                    </option>
                  ))}
                </select>
              </div>
              <button onClick={handleExportGrossSalesReport} disabled={exportingGross} className={BTN_SM("green")}>
                {exportingGross ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                Gross Sales Report
              </button>
              <button onClick={handleExportSalesSummary} disabled={exportingSummary} className={BTN_SM("indigo")}>
                {exportingSummary ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                Sales Summary
              </button>
            </div>
            {selectedPlan && selectedPlan.content && (
              <div className="space-y-3">
                {(selectedPlan.content.meta || selectedPlan.content).area && (
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    <span className="px-2 py-1 rounded bg-violet-500/10 border border-violet-500/30 text-violet-300 font-medium">{selectedPlan.content.meta?.area || 'Total'}</span>
                    {selectedPlan.content.meta?.type && <span className="px-2 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300 font-medium">{selectedPlan.content.meta.type}</span>}
                    <span className="text-gray-500">{selectedPlan.department} / {selectedPlan.team_code} - {selectedPlan.team_name}</span>
                  </div>
                )}
                <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="bg-gray-800/80">
                        {(selectedPlan.content.headers || DEFAULT_SALES_PLAN_CONTENT.headers).map((h, ci) => (
                          <th key={ci} className={`sticky top-0 z-10 bg-gray-800 px-2 py-2 text-left text-gray-400 border border-gray-700 font-semibold whitespace-nowrap ${ci >= 2 && ci <= 13 ? 'text-center w-16' : ci === 14 || ci === 15 ? 'text-right w-20' : ''}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedPlan.content.rows || []).map((row, i) => (
                        <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                          <td className="px-2 py-1.5 border border-gray-700 text-center w-8">{row[0]}</td>
                          <td className="px-2 py-1.5 border border-gray-700">{row[1]}</td>
                          {row.slice(2, 14).map((val, ci) => (
                            <td key={ci} className="px-2 py-1.5 border border-gray-700 text-right font-mono">{Number(val || 0).toLocaleString()}</td>
                          ))}
                          <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-violet-400">{Number(row[14] || 0).toLocaleString()}</td>
                          <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-sky-400">{Number(row[15] || 0).toLocaleString()}</td>
                          <td className="px-2 py-1.5 border border-gray-700 text-right font-mono text-xs text-gray-400">{row[16] ? Number(row[16]).toLocaleString() : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Field label="Plan Year">
                <input type="number" className={`${INP}`} value={form.plan_year} onChange={e => setForm({ ...form, plan_year: Number(e.target.value) })} />
              </Field>
              <Field label="Department">
                <input className={`${INP}`} value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="e.g. SALES" />
              </Field>
              <Field label="Team Code">
                <input className={`${INP}`} value={form.team_code} onChange={e => setForm({ ...form, team_code: e.target.value })} placeholder="e.g. 01" />
              </Field>
              <Field label="Team Name">
                <input className={`${INP}`} value={form.team_name} onChange={e => setForm({ ...form, team_name: e.target.value })} placeholder="e.g. Domestic Sales" />
              </Field>
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-gray-500">Plan Type:</label>
              <select value={form.plan_type} onChange={e => setForm({ ...form, plan_type: e.target.value })} className={`${SELECT}`}>
                <option value="value">Value (S1)</option>
                <option value="unit">Unit (S2)</option>
              </select>
              <label className="text-xs text-gray-500">Status:</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={`${SELECT}`}>
                <option value="draft">Draft</option>
                <option value="final">Final</option>
              </select>
            </div>
            <div className="overflow-auto border border-gray-700 rounded-lg" style={{ maxHeight: "21rem" }}>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-gray-800/80">
                    {(form.content.headers || DEFAULT_SALES_PLAN_CONTENT.headers).map((h, ci) => (
                      <th key={ci} className={`sticky top-0 z-10 bg-gray-800 px-2 py-2 text-left text-gray-400 border border-gray-700 font-semibold whitespace-nowrap ${ci >= 2 && ci <= 13 ? 'text-center w-16' : ci === 14 || ci === 15 ? 'text-right w-20' : ''}`}>{h}</th>
                    ))}
                    <th className="sticky top-0 z-10 bg-gray-800 px-2 py-2 text-center border border-gray-700 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.content.rows || []).map((row, ri) => (
                    <tr key={ri} className="border-b border-gray-800 hover:bg-gray-800/30">
                      <td className="px-2 py-1.5 border border-gray-700 text-center w-8 font-bold text-gray-400">{row[0]}</td>
                      <td className="px-2 py-1.5 border border-gray-700">
                        <input className={`${INP} !text-xs`} value={row[1]} onChange={e => updateCell(ri, 1, e.target.value)} />
                      </td>
                      {row.slice(2, 14).map((val, ci) => (
                        <td key={ci} className="px-2 py-1.5 border border-gray-700">
                          <input type="number" className={`${INP} !text-center !text-xs font-mono`} value={val} onChange={e => updateCell(ri, ci + 2, e.target.value)} />
                        </td>
                      ))}
                      <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-violet-400">{Number(row[14] || 0).toLocaleString()}</td>
                      <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-sky-400">{Number(row[15] || 0).toLocaleString()}</td>
                      <td className="px-2 py-1.5 border border-gray-700 text-right font-mono text-xs text-gray-400">{row[16] ? Number(row[16]).toLocaleString() : '-'}</td>
                      <td className="px-2 py-1.5 border border-gray-700 text-center">
                        <button onClick={() => removeRow(ri)} className={BTN_SM("red")}><Trash2 size={9} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800/60">
                    <td colSpan={2} className="px-2 py-1.5 border border-gray-700 text-xs font-bold text-gray-300">GRAND TOTAL</td>
                    {[2,3,4,5,6,7,8,9,10,11,12,13].map(ci => (
                      <td key={ci} className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-gray-200">{grandTotal(ci).toLocaleString()}</td>
                    ))}
                    <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-violet-400">{grandTotal(14).toLocaleString()}</td>
                    <td className="px-2 py-1.5 border border-gray-700 text-right font-mono font-bold text-sky-400">{grandTotal(15).toLocaleString()}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <button onClick={addRow} className={BTN_SM("violet")}><Plus size={11} /> Add Product</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Section: Budget Usage Report ──────────────── */
