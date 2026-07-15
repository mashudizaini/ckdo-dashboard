import { useState, useEffect, useCallback, useRef } from "react";
import {
  Plus, Upload, Loader2, Trash2, Download, X, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle, Search, FileText, Sparkles, ChevronLeft, ChevronRight,
} from "lucide-react";
import { hrApi } from "@/api/dashboard";
import { useAuthStore } from "@/store/authStore";
import { toggleSort, sortRows } from "@/components/SortableTH";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn: "inset 4px 4px 10px #c5cad8, inset -4px -4px 10px #ffffff",
  shadowBtn: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff",
};

const REC_CFG = {
  "Highly Recommended": { bg: "#dcfce7", color: "#16a34a" },
  "Recommended":         { bg: "#dbeafe", color: "#1d4ed8" },
  "Consider":            { bg: "#fef3c7", color: "#d97706" },
  "Not Recommended":     { bg: "#fee2e2", color: "#dc2626" },
  "Error Processing":    { bg: "#f1f5f9", color: "#64748b" },
};

const CV_SUBTABS = [
  { id: "screening",   label: "CV Screening" },
  { id: "detail",      label: "Detail" },
  { id: "candidates",  label: "Candidate Database" },
  { id: "requirement", label: "Database Qualification" },
];

const TH = { padding: "10px 12px", textAlign: "left", fontSize: 10.5, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "2px solid rgba(0,0,0,0.06)", whiteSpace: "nowrap" };
const TD = { padding: "8px 12px", fontSize: 12, color: "#334155", whiteSpace: "nowrap" };

function SortableTHi({ label, field, sortBy, sortDir, onSort, style }) {
  const active = sortBy === field;
  return (
    <th onClick={() => onSort(field)} style={{ ...TH, ...style, cursor: "pointer", userSelect: "none", color: active ? "#2563eb" : TH.color }}>
      {label} {active && (sortDir === "asc" ? "▲" : "▼")}
    </th>
  );
}

function RecBadge({ rec }) {
  const cfg = REC_CFG[rec] || REC_CFG["Consider"];
  return (
    <span style={{ display: "inline-flex", padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: cfg.bg, color: cfg.color }}>
      {rec}
    </span>
  );
}

function Pagination({ total, page, onPage, pageSize = 10 }) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 4px" }}>
      <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700 }}>
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button onClick={() => onPage(Math.max(1, page - 1))} disabled={page === 1}
          style={{ padding: 5, borderRadius: 7, border: "none", cursor: page === 1 ? "not-allowed" : "pointer", background: NEU.bg, color: page === 1 ? "#cbd5e1" : "#475569", boxShadow: NEU.shadowOutSm }}>
          <ChevronLeft size={13} />
        </button>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#1e293b", padding: "0 6px" }}>{page} / {pages}</span>
        <button onClick={() => onPage(Math.min(pages, page + 1))} disabled={page === pages}
          style={{ padding: 5, borderRadius: 7, border: "none", cursor: page === pages ? "not-allowed" : "pointer", background: NEU.bg, color: page === pages ? "#cbd5e1" : "#475569", boxShadow: NEU.shadowOutSm }}>
          <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}

function JobForm({ onSave, onCancel, saving, initial }) {
  const [form, setForm] = useState({
    position_title: initial?.position_title || "",
    required_skills: (initial?.required_skills || []).join(", "),
    min_experience: initial?.min_experience || 0,
    education_keywords: (initial?.education_keywords || []).join(", "),
    certification_keywords: (initial?.certification_keywords || []).join(", "),
    date_posted: initial?.date_posted || new Date().toISOString().slice(0, 10),
  });
  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }));

  const submit = () => {
    onSave({
      position_title: form.position_title,
      required_skills: form.required_skills.split(",").map(s => s.trim()).filter(Boolean),
      min_experience: Number(form.min_experience) || 0,
      education_keywords: form.education_keywords.split(",").map(s => s.trim()).filter(Boolean),
      certification_keywords: form.certification_keywords.split(",").map(s => s.trim()).filter(Boolean),
      date_posted: form.date_posted || null,
    });
  };

  const inputStyle = { width: "100%", fontSize: 13, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box" };
  const labelStyle = { fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 };

  return (
    <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: 18, marginBottom: 16 }}>
      <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 12 }}>New Position / Job Requirement</h4>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>POSITION TITLE *</label>
          <input value={form.position_title} onChange={set("position_title")} placeholder="e.g. Oracle EBS Technical Consultant" style={inputStyle} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>REQUIRED SKILLS (comma separated) *</label>
          <input value={form.required_skills} onChange={set("required_skills")} placeholder="Oracle EBS, PL/SQL, SQL, Database Administration" style={inputStyle} />
        </div>
        <div>
          <label style={labelStyle}>MIN. EXPERIENCE (years)</label>
          <input type="number" min={0} value={form.min_experience} onChange={set("min_experience")} style={inputStyle} />
        </div>
        <div>
          <label style={labelStyle}>DATE POSTED</label>
          <input type="date" value={form.date_posted} onChange={set("date_posted")} style={inputStyle} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>EDUCATION KEYWORDS (comma separated)</label>
          <input value={form.education_keywords} onChange={set("education_keywords")} placeholder="S1 Teknik Informatika, Bachelor Computer Science" style={inputStyle} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>CERTIFICATION KEYWORDS (comma separated)</label>
          <input value={form.certification_keywords} onChange={set("certification_keywords")} placeholder="OCP, Oracle Certified Professional" style={inputStyle} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={submit} disabled={saving || !form.position_title.trim() || !form.required_skills.trim()}
          style={{ fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", boxShadow: NEU.shadowBtn, opacity: (saving || !form.position_title.trim() || !form.required_skills.trim()) ? 0.5 : 1 }}>
          {saving ? "Saving..." : "Create Position"}
        </button>
        <button onClick={onCancel} style={{ fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: NEU.bg, color: "#64748b", cursor: "pointer", boxShadow: NEU.shadowBtn }}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function JdGeneratorPanel({ onUseCriteria, onCancel }) {
  const [jdText, setJdText] = useState("");
  const [method, setMethod] = useState("template");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  const handleUploadFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await hrApi.uploadCvJd(fd);
      setJdText(res.text || "");
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleGenerate = async () => {
    if (!jdText.trim()) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const res = await hrApi.generateCvJd({ jd_text: jdText, method });
      setResult(res.result);
    } catch (err) {
      setError(err.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const improved = result?.improved_jd;
  const inputStyle = { width: "100%", fontSize: 12.5, padding: "10px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box", fontFamily: "inherit" };

  return (
    <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: 18, marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={14} /> Generate Position from Job Description
        </h4>
        <button onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8" }}>
          <X size={16} />
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
        <label>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={handleUploadFile} style={{ display: "none" }} />
          <span onClick={() => fileRef.current?.click()}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, background: NEU.bg, color: "#64748b", fontSize: 11.5, fontWeight: 700, cursor: "pointer", boxShadow: NEU.shadowOutSm }}>
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />} Upload JD File
          </span>
        </label>
        <select value={method} onChange={e => setMethod(e.target.value)}
          style={{ fontSize: 11.5, fontWeight: 600, padding: "6px 10px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
          <option value="template">Template (free)</option>
          <option value="ai">AI-Powered (Claude)</option>
        </select>
      </div>

      <textarea value={jdText} onChange={e => setJdText(e.target.value)} rows={6}
        placeholder="Paste job description text here, or upload a file..."
        style={{ ...inputStyle, resize: "vertical" }} />

      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button onClick={handleGenerate} disabled={generating || !jdText.trim()}
          style={{ fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", boxShadow: NEU.shadowBtn, opacity: (generating || !jdText.trim()) ? 0.5 : 1, display: "flex", alignItems: "center", gap: 6 }}>
          {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          {generating ? "Generating..." : "Generate"}
        </button>
      </div>

      {error && <p style={{ color: "#dc2626", fontSize: 12, marginTop: 10 }}>{error}</p>}

      {improved && (
        <div style={{ marginTop: 14, padding: 14, borderRadius: 12, background: "#f0f3f9", boxShadow: NEU.shadowIn }}>
          <p style={{ fontSize: 13, fontWeight: 800, color: "#1e293b" }}>{improved.position_title}</p>
          <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 4 }}>{improved.overview}</p>

          {improved.key_responsibilities?.length > 0 && (
            <>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#374151", marginTop: 10 }}>Key Responsibilities</p>
              <ul style={{ fontSize: 11.5, color: "#475569", paddingLeft: 16, marginTop: 4 }}>
                {improved.key_responsibilities.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </>
          )}

          <p style={{ fontSize: 11, fontWeight: 700, color: "#374151", marginTop: 10 }}>Required Qualifications</p>
          <p style={{ fontSize: 11.5, color: "#475569", marginTop: 2 }}>
            Education: {improved.required_qualifications?.education} · Experience: {improved.required_qualifications?.experience}
          </p>
          <p style={{ fontSize: 11.5, color: "#475569", marginTop: 2 }}>
            Skills: {(improved.required_qualifications?.technical_skills || []).join(", ")}
          </p>

          {result.hr_notes && (
            <p style={{ fontSize: 11, color: "#7c3aed", marginTop: 10, fontStyle: "italic" }}>{result.hr_notes}</p>
          )}

          <button onClick={() => onUseCriteria(improved.screening_criteria)}
            style={{ marginTop: 12, fontSize: 12, fontWeight: 700, padding: "8px 18px", borderRadius: 10, border: "none", background: "#16a34a", color: "#fff", cursor: "pointer", boxShadow: NEU.shadowBtn }}>
            Use as New Position
          </button>
        </div>
      )}
    </div>
  );
}

function CandidateRow({ c, i, onDelete, onHire }) {
  const [expanded, setExpanded] = useState(false);
  const [hireForm, setHireForm] = useState(false);
  const [appDate, setAppDate] = useState(c.application_date || (c.screened_at ? c.screened_at.slice(0, 10) : ""));
  const [offerDate, setOfferDate] = useState(c.offer_accept_date || new Date().toISOString().slice(0, 10));

  const submitHire = () => {
    onHire(c.id, { application_date: appDate, offer_accept_date: offerDate, is_hired: true });
    setHireForm(false);
  };

  return (
    <>
      <tr style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5", cursor: "pointer" }} onClick={() => setExpanded(!expanded)}>
        <td style={{ padding: "8px 12px", fontSize: 12, color: "#64748b" }}>{expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</td>
        <td style={{ padding: "8px 12px", fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>{c.name}</td>
        <td style={{ padding: "8px 12px", fontSize: 11.5, color: "#64748b" }}>{c.email || "—"}</td>
        <td style={{ padding: "8px 12px", fontSize: 11.5, color: "#64748b" }}>{c.experience_years}y</td>
        <td style={{ padding: "8px 12px", fontSize: 11.5, color: "#475569" }}>{c.education || "—"}</td>
        <td style={{ padding: "8px 12px", fontSize: 11.5, color: "#475569" }}>{(c.skills_found || []).length} skills</td>
        <td style={{ padding: "8px 12px", fontSize: 14, fontWeight: 800, color: "#1e293b" }}>{c.total_score}</td>
        <td style={{ padding: "8px 12px" }}>
          <RecBadge rec={c.recommendation} />
          {c.is_hired && (
            <span style={{ marginLeft: 6, display: "inline-flex", padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: "#dcfce7", color: "#16a34a" }}>
              ✓ Hired
            </span>
          )}
        </td>
        <td style={{ padding: "8px 12px" }} onClick={e => e.stopPropagation()}>
          <button onClick={() => onDelete(c.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4 }}>
            <Trash2 size={13} />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
          <td colSpan={9} style={{ padding: "0 12px 14px 36px" }}>
            {c.error ? (
              <div style={{ fontSize: 12, color: "#dc2626", fontWeight: 600 }}>Error: {c.error}</div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 11.5 }}>
                <div>
                  <p style={{ fontWeight: 700, color: "#374151", marginBottom: 4 }}>Skills Found</p>
                  <p style={{ color: "#475569" }}>{(c.skills_found || []).join(", ") || "None"}</p>
                  {c.additional_relevant_skills?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#374151", marginTop: 6, marginBottom: 4 }}>Additional Relevant Skills</p>
                      <p style={{ color: "#475569" }}>{c.additional_relevant_skills.join(", ")}</p>
                    </>
                  )}
                  {c.missing_skills?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#dc2626", marginTop: 6, marginBottom: 4 }}>Missing Critical Skills</p>
                      <p style={{ color: "#dc2626" }}>{c.missing_skills.join(", ")}</p>
                    </>
                  )}
                  {c.positions?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#374151", marginTop: 6, marginBottom: 4 }}>Work History</p>
                      <ul style={{ color: "#475569", paddingLeft: 16 }}>
                        {c.positions.map((p, j) => (
                          <li key={j}>{p.title} — {p.company} ({p.duration}){p.relevant === false ? " · not relevant" : ""}</li>
                        ))}
                      </ul>
                    </>
                  )}
                  {c.certifications?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#374151", marginTop: 6, marginBottom: 4 }}>Certifications</p>
                      <p style={{ color: "#475569" }}>
                        {c.certifications.map((cert, j) => `${cert.name}${cert.year ? ` (${cert.year})` : ""}`).join(", ")}
                      </p>
                    </>
                  )}
                  <p style={{ fontWeight: 700, color: "#374151", marginTop: 6, marginBottom: 4 }}>Score Breakdown</p>
                  <p style={{ color: "#475569" }}>
                    Skills: {c.skills_score} · Experience: {c.experience_score} · Education: {c.education_score} · Certification: {c.certification_score}
                  </p>
                </div>
                <div>
                  {c.reasoning && (
                    <>
                      <p style={{ fontWeight: 700, color: "#374151", marginBottom: 4 }}>AI Reasoning</p>
                      <p style={{ color: "#475569" }}>{c.reasoning}</p>
                    </>
                  )}
                  {c.strengths?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#16a34a", marginTop: 6, marginBottom: 4 }}>Strengths</p>
                      <ul style={{ color: "#475569", paddingLeft: 16 }}>
                        {c.strengths.map((s, j) => <li key={j}>{s}</li>)}
                      </ul>
                    </>
                  )}
                  {c.red_flags?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#dc2626", marginTop: 6, marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
                        <AlertTriangle size={11} /> Red Flags
                      </p>
                      <ul style={{ color: "#dc2626", paddingLeft: 16 }}>
                        {c.red_flags.map((s, j) => <li key={j}>{s}</li>)}
                      </ul>
                    </>
                  )}
                  {c.interview_focus?.length > 0 && (
                    <>
                      <p style={{ fontWeight: 700, color: "#7c3aed", marginTop: 6, marginBottom: 4 }}>Interview Focus</p>
                      <ul style={{ color: "#475569", paddingLeft: 16 }}>
                        {c.interview_focus.map((s, j) => <li key={j}>{s}</li>)}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Recruitment pipeline — hire tracking for Time to Hire / Time to Fill */}
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid rgba(0,0,0,0.08)" }}>
              {c.is_hired ? (
                <p style={{ fontSize: 11.5, color: "#16a34a", fontWeight: 700 }}>
                  ✓ Hired — Applied {c.application_date || "—"} · Offer accepted {c.offer_accept_date || "—"}
                </p>
              ) : hireForm ? (
                <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>APPLICATION DATE</label>
                    <input type="date" value={appDate} onChange={e => setAppDate(e.target.value)}
                      style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: NEU.bg, boxShadow: NEU.shadowIn, outline: "none" }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 }}>OFFER ACCEPT DATE</label>
                    <input type="date" value={offerDate} onChange={e => setOfferDate(e.target.value)}
                      style={{ fontSize: 12, padding: "6px 10px", borderRadius: 8, border: "none", background: NEU.bg, boxShadow: NEU.shadowIn, outline: "none" }} />
                  </div>
                  <button onClick={submitHire} style={{ fontSize: 11.5, fontWeight: 700, padding: "7px 14px", borderRadius: 8, border: "none", background: "#16a34a", color: "#fff", cursor: "pointer", boxShadow: NEU.shadowBtn }}>Save</button>
                  <button onClick={() => setHireForm(false)} style={{ fontSize: 11.5, fontWeight: 700, padding: "7px 14px", borderRadius: 8, border: "none", background: NEU.bg, color: "#64748b", cursor: "pointer", boxShadow: NEU.shadowBtn }}>Cancel</button>
                </div>
              ) : (
                <button onClick={() => setHireForm(true)}
                  style={{ fontSize: 11.5, fontWeight: 700, padding: "7px 14px", borderRadius: 8, border: "none", background: NEU.bg, color: "#16a34a", cursor: "pointer", boxShadow: NEU.shadowOutSm }}>
                  Mark as Hired
                </button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ─── Sub-tab: CV Screening (upload + score against an existing position) ── */

function ScreeningTab({ jobs, activeJobId, setActiveJobId }) {
  const { token } = useAuthStore();
  const activeJob = jobs.find(j => j.id === activeJobId);
  const [candidates, setCandidates] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState(null);
  const [recFilter, setRecFilter] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };
  const fileRef = useRef(null);

  const fetchCandidates = useCallback(async () => {
    if (!activeJobId) { setCandidates([]); setStats(null); return; }
    setLoading(true);
    try {
      const p = {};
      if (recFilter) p.recommendation = recFilter;
      if (search) p.search = search;
      const [cands, st] = await Promise.all([
        hrApi.getCvCandidates(activeJobId, p),
        hrApi.getCvStats(activeJobId),
      ]);
      setCandidates(cands);
      setStats(st);
    } catch (_) {}
    finally { setLoading(false); }
  }, [activeJobId, recFilter, search]);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length || !activeJobId) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));
      const res = await fetch(`/api/v1/dashboard/hr/cv-screening/jobs/${activeJobId}/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      setUploadMsg({ type: "success", text: `Screened ${data.count} CV(s) successfully` });
      fetchCandidates();
    } catch (err) {
      setUploadMsg({ type: "error", text: err.message || "Upload failed" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDeleteCandidate = async (id) => {
    if (!confirm("Delete this candidate?")) return;
    try { await hrApi.deleteCvCandidate(id); fetchCandidates(); } catch (_) {}
  };

  const handleHire = async (id, data) => {
    try { await hrApi.hireCvCandidate(id, data); fetchCandidates(); } catch (_) {}
  };

  const handleExport = async () => {
    if (!activeJobId) return;
    try {
      const res = await fetch(hrApi.exportCvExcel(activeJobId), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cv_screening_${(activeJob?.position_title || "export").replace(/\s+/g, "_")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (_) {}
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Qualification parameter — pulled from Database Qualification */}
      <div>
        {jobs.length === 0 ? (
          <p style={{ fontSize: 12, color: "#94a3b8" }}>
            No positions configured yet. Go to the "Database Qualification" tab to create one.
          </p>
        ) : (
          <>
            <label style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 4 }}>QUALIFICATION</label>
            <select value={activeJobId || ""} onChange={e => setActiveJobId(Number(e.target.value))}
              style={{ fontSize: 13, fontWeight: 700, padding: "8px 14px", borderRadius: 10, border: "none", background: NEU.bg, color: "#2563eb", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none", minWidth: 260 }}>
              {jobs.map(j => <option key={j.id} value={j.id}>{j.position_title}</option>)}
            </select>
          </>
        )}
      </div>

      {activeJob && (
        <>
          {/* Job requirements summary */}
          <div style={{ background: NEU.bg, boxShadow: NEU.shadowOutSm, borderRadius: 14, padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <div>
              <p style={{ fontSize: 13, fontWeight: 800, color: "#1e293b" }}>{activeJob.position_title}</p>
              <p style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                Skills: {activeJob.required_skills.join(", ")} · Min exp: {activeJob.min_experience}y
                {activeJob.education_keywords.length > 0 && <> · Education: {activeJob.education_keywords.join(", ")}</>}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <label>
                <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" multiple onChange={handleUpload} style={{ display: "none" }} />
                <span onClick={() => fileRef.current?.click()}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, background: "#2563eb", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: NEU.shadowBtn }}>
                  {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                  {uploading ? "Screening..." : "Upload CVs"}
                </span>
              </label>
              <button onClick={handleExport} disabled={!candidates.length}
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: NEU.bg, color: "#64748b", fontSize: 12, fontWeight: 700, cursor: candidates.length ? "pointer" : "not-allowed", boxShadow: NEU.shadowOutSm, opacity: candidates.length ? 1 : 0.5 }}>
                <Download size={13} /> Export
              </button>
            </div>
          </div>

          {uploadMsg && (
            <div style={{
              padding: "10px 16px", borderRadius: 12, fontSize: 12, fontWeight: 600,
              display: "flex", alignItems: "center", gap: 8,
              background: uploadMsg.type === "error" ? "#fee2e2" : "#dcfce7",
              color: uploadMsg.type === "error" ? "#dc2626" : "#16a34a",
              boxShadow: NEU.shadowOutSm,
            }}>
              {uploadMsg.type === "error" ? <X size={13} /> : <CheckCircle size={13} />}
              {uploadMsg.text}
            </div>
          )}

          {/* Summary cards */}
          {stats && stats.total > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
              {[
                { label: "Total CVs",       val: stats.total,              color: "#2563eb" },
                { label: "Highly Rec.",     val: stats.highly_recommended, color: "#16a34a" },
                { label: "Recommended",     val: stats.recommended,        color: "#1d4ed8" },
                { label: "Consider",        val: stats.consider,           color: "#d97706" },
                { label: "Not Recommended", val: stats.not_recommended,    color: "#dc2626" },
                { label: "Avg. Score",      val: stats.average_score,      color: "#7c3aed" },
              ].map(c => (
                <div key={c.label} style={{ padding: 12, borderRadius: 14, background: NEU.bg, boxShadow: NEU.shadowOut, textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: c.color }}>{c.val}</div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#64748b", marginTop: 2 }}>{c.label}</div>
                </div>
              ))}
            </div>
          )}

          {/* Filters */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={recFilter} onChange={e => setRecFilter(e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none" }}>
              <option value="">All Recommendations</option>
              {Object.keys(REC_CFG).map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name / email..."
                style={{ fontSize: 12, padding: "6px 12px 6px 30px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", width: 200 }} />
            </div>
          </div>

          {/* Candidate table */}
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}><Loader2 size={20} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
          ) : candidates.length === 0 ? (
            <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
              No candidates yet. Click "Upload CVs" to screen resumes against this position.
            </p>
          ) : (
            <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                    <th style={{ padding: "10px 12px", borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <SortableTHi label="Name"           field="name"             sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <SortableTHi label="Email"          field="email"            sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <SortableTHi label="Exp"            field="experience_years" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <SortableTHi label="Education"      field="education"        sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <th style={{ padding: "10px 12px", textAlign: "left", fontSize: 10.5, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "2px solid rgba(0,0,0,0.06)" }}>Skills</th>
                    <SortableTHi label="Score"          field="total_score"      sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <SortableTHi label="Recommendation" field="recommendation"   sortBy={sortBy} sortDir={sortDir} onSort={handleSort} style={{ borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                    <th style={{ padding: "10px 12px", borderBottom: "2px solid rgba(0,0,0,0.06)" }} />
                  </tr>
                </thead>
                <tbody>
                  {sortRows(candidates, sortBy, sortDir, ["experience_years", "total_score"]).map((c, i) => (
                    <CandidateRow key={c.id} c={c} i={i} onDelete={handleDeleteCandidate} onHire={handleHire} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Sub-tab: Database Qualification (master data — position CRUD) ──────── */

function RequirementTab({ jobs, fetchJobs, activeJobId, setActiveJobId }) {
  const [showJobForm, setShowJobForm] = useState(false);
  const [showJdPanel, setShowJdPanel] = useState(false);
  const [jdPrefill, setJdPrefill] = useState(null);
  const [savingJob, setSavingJob] = useState(false);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); };

  const handleCreateJob = async (data) => {
    setSavingJob(true);
    try {
      const j = await hrApi.createCvJob(data);
      setShowJobForm(false);
      setJdPrefill(null);
      await fetchJobs();
      setActiveJobId(j.id);
    } catch (_) {}
    finally { setSavingJob(false); }
  };

  const handleUseJdCriteria = (criteria) => {
    setJdPrefill(criteria);
    setShowJdPanel(false);
    setShowJobForm(true);
  };

  const handleDeleteJob = async (id) => {
    if (!confirm("Delete this position and all its screened candidates?")) return;
    try {
      await hrApi.deleteCvJob(id);
      if (activeJobId === id) setActiveJobId(null);
      fetchJobs();
    } catch (_) {}
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={() => { setShowJdPanel(!showJdPanel); setShowJobForm(false); }}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: NEU.bg, color: "#7c3aed", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: showJdPanel ? NEU.shadowIn : NEU.shadowOutSm }}>
          <Sparkles size={14} /> Generate from JD
        </button>
        <button onClick={() => { setShowJobForm(!showJobForm); setJdPrefill(null); setShowJdPanel(false); }}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: NEU.shadowBtn }}>
          <Plus size={14} /> New Position
        </button>
      </div>

      {showJdPanel && <JdGeneratorPanel onUseCriteria={handleUseJdCriteria} onCancel={() => setShowJdPanel(false)} />}
      {showJobForm && <JobForm onSave={handleCreateJob} onCancel={() => { setShowJobForm(false); setJdPrefill(null); }} saving={savingJob} initial={jdPrefill} />}

      {jobs.length === 0 ? (
        <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: "40px 20px", textAlign: "center" }}>
          <p style={{ fontSize: 13, color: "#94a3b8", fontWeight: 500 }}>
            No position requirements defined yet. Click "+ New Position" to add one.
          </p>
        </div>
      ) : (
        <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                  <SortableTHi label="Position"       field="position_title"         sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Required Skills" field="required_skills"        sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Min Exp"        field="min_experience"         sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Education"      field="education_keywords"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Certification"  field="certification_keywords" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Date Posted"    field="date_posted"            sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Created By"     field="created_by"             sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <th style={TH} />
                </tr>
              </thead>
              <tbody>
                {sortRows(jobs, sortBy, sortDir, ["min_experience"]).map((j, i) => (
                  <tr key={j.id} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                    <td style={{ ...TD, fontWeight: 700, color: "#1e293b" }}>{j.position_title}</td>
                    <td style={{ ...TD, whiteSpace: "normal", maxWidth: 260 }}>{j.required_skills.join(", ") || "—"}</td>
                    <td style={TD}>{j.min_experience}y</td>
                    <td style={{ ...TD, whiteSpace: "normal", maxWidth: 200 }}>{j.education_keywords.join(", ") || "—"}</td>
                    <td style={{ ...TD, whiteSpace: "normal", maxWidth: 200 }}>{j.certification_keywords.join(", ") || "—"}</td>
                    <td style={TD}>{j.date_posted || "—"}</td>
                    <td style={TD}>{j.created_by || "—"}</td>
                    <td style={TD}>
                      <button onClick={() => handleDeleteJob(j.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4 }}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Sub-tab: Detail — Time to Hire / Time to Fill per candidate ─────────
   Time to Hire = Offer Accept Date − Application Date (per candidate)
   Time to Fill = avg(Offer Accept Date − Job Date Posted) across hired
                  candidates of that position                             */

function DetailTab({ jobs }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [jobFilter, setJobFilter] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const PAGE_SIZE = 10;

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    try {
      const p = {};
      if (jobFilter) p.job_id = jobFilter;
      const res = await hrApi.getCvDetail(p);
      setRows(res);
      setPage(1);
    } catch (_) {}
    finally { setLoading(false); }
  }, [jobFilter]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); setPage(1); };
  const fmtDays = (d) => d == null ? "—" : `${d} day${d === 1 ? "" : "s"}`;
  const fmtDate = (d) => d ? d.slice(0, 10) : "—";
  const sortedRows = sortRows(rows, sortBy, sortDir, ["time_to_hire", "time_to_fill", "skills_score", "experience_score", "education_score", "certification_score"]);
  const paged = sortedRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <select value={jobFilter} onChange={e => setJobFilter(e.target.value)}
        style={{ fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none", width: 260 }}>
        <option value="">All Positions</option>
        {jobs.map(j => <option key={j.id} value={j.id}>{j.position_title}</option>)}
      </select>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}><Loader2 size={20} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
      ) : rows.length === 0 ? (
        <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No screened candidates yet.</p>
      ) : (
        <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                  <SortableTHi label="Position"             field="position_title"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Candidate"            field="candidate_name"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Time to Hire"         field="time_to_hire"       sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Time to Fill"         field="time_to_fill"       sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Education"            field="education"          sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Skills Score"         field="skills_score"       sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Experience Score"     field="experience_score"   sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Education Score"      field="education_score"    sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Certification Score"  field="certification_score" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="File Name"            field="filename"           sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableTHi label="Processed Date"       field="processed_date"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody>
                {paged.map((r, i) => (
                  <tr key={r.candidate_id} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                    <td style={{ ...TD, fontWeight: 700, color: "#1e293b" }}>{r.position_title}</td>
                    <td style={TD}>{r.candidate_name}</td>
                    <td style={TD}>{fmtDays(r.time_to_hire)}</td>
                    <td style={TD}>{fmtDays(r.time_to_fill)}</td>
                    <td style={TD}>{r.education || "—"}</td>
                    <td style={TD}>{r.skills_score}</td>
                    <td style={TD}>{r.experience_score}</td>
                    <td style={TD}>{r.education_score}</td>
                    <td style={TD}>{r.certification_score}</td>
                    <td style={{ ...TD, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }} title={r.filename}>{r.filename}</td>
                    <td style={TD}>{fmtDate(r.processed_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination total={rows.length} page={page} onPage={setPage} pageSize={PAGE_SIZE} />
        </div>
      )}
    </div>
  );
}

/* ─── Sub-tab: Candidate Database — every CV ever processed, all positions ── */

function CandidateDatabaseTab() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy,  setSortBy]  = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const PAGE_SIZE = 10;

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrApi.getAllCvCandidates(search ? { search } : {});
      setCandidates(res || []);
      setPage(1);
    } catch (_) {}
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

  const handleSort = (f) => { const r = toggleSort(sortBy, sortDir, f); setSortBy(r.sortBy); setSortDir(r.sortDir); setPage(1); };
  const fmtDate = (d) => d ? d.slice(0, 10) : "—";
  const sortedCandidates = sortRows(candidates, sortBy, sortDir, ["experience_years", "total_score"]);
  const paged = sortedCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const HEADERS = [
    ["Position", "position_title"], ["Name", "name"], ["Email", "email"], ["Phone", "phone"],
    ["Experience (yrs)", "experience_years"], ["Education", "education"], ["Total Score", "total_score"],
    ["Recommendation", "recommendation"], ["Status", "is_hired"], ["File Name", "filename"], ["Processed Date", "screened_at"],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ position: "relative", width: 260 }}>
        <Search size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name / email..."
          style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "6px 12px 6px 30px", borderRadius: 8, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none" }} />
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}><Loader2 size={20} className="animate-spin" style={{ color: "#94a3b8" }} /></div>
      ) : candidates.length === 0 ? (
        <p style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No CVs processed yet.</p>
      ) : (
        <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                  <th style={TH}>No</th>
                  {HEADERS.map(([h, field]) => (
                    <SortableTHi key={field} label={h} field={field} sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.map((c, i) => (
                  <tr key={c.id} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                    <td style={TD}>{(page - 1) * PAGE_SIZE + i + 1}</td>
                    <td style={{ ...TD, fontWeight: 700, color: "#1e293b" }}>{c.position_title}</td>
                    <td style={TD}>{c.name || "—"}</td>
                    <td style={TD}>{c.email || "—"}</td>
                    <td style={TD}>{c.phone || "—"}</td>
                    <td style={{ ...TD, textAlign: "right" }}>{c.experience_years}</td>
                    <td style={TD}>{c.education || "—"}</td>
                    <td style={{ ...TD, textAlign: "right", fontWeight: 700 }}>{c.total_score}</td>
                    <td style={TD}><RecBadge rec={c.recommendation} /></td>
                    <td style={TD}>{c.is_hired ? "✓ Hired" : "—"}</td>
                    <td style={{ ...TD, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }} title={c.filename}>{c.filename}</td>
                    <td style={TD}>{fmtDate(c.screened_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination total={candidates.length} page={page} onPage={setPage} pageSize={PAGE_SIZE} />
        </div>
      )}
    </div>
  );
}

/* ─── Main export: E-Recruitment shell with 4 sub-tabs ────────────────────── */

export default function HRCvScreening() {
  const [subTab, setSubTab] = useState("screening");
  const [jobs, setJobs] = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await hrApi.getCvJobs();
      setJobs(res);
      if (!activeJobId && res.length > 0) setActiveJobId(res[0].id);
    } catch (_) {}
  }, [activeJobId]);

  useEffect(() => { fetchJobs(); }, []); // eslint-disable-line

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", gap: 4, borderBottom: "2px solid rgba(0,0,0,0.06)", flexWrap: "wrap" }}>
        {CV_SUBTABS.map(t => (
          <button key={t.id} onClick={() => setSubTab(t.id)}
            style={{
              padding: "9px 16px", border: "none", cursor: "pointer", background: "transparent",
              borderBottom: subTab === t.id ? "2px solid #0891b2" : "2px solid transparent",
              marginBottom: -2, color: subTab === t.id ? "#0891b2" : "#64748b",
              fontSize: 12.5, fontWeight: subTab === t.id ? 700 : 500, transition: "all 0.15s",
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {subTab === "screening"   && <ScreeningTab jobs={jobs} activeJobId={activeJobId} setActiveJobId={setActiveJobId} />}
      {subTab === "requirement" && <RequirementTab jobs={jobs} fetchJobs={fetchJobs} activeJobId={activeJobId} setActiveJobId={setActiveJobId} />}
      {subTab === "detail"      && <DetailTab jobs={jobs} />}
      {subTab === "candidates"  && <CandidateDatabaseTab />}
    </div>
  );
}
