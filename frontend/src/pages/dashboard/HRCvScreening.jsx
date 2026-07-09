import { useState, useEffect, useCallback, useRef } from "react";
import {
  Plus, Upload, Loader2, Trash2, Download, X, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle, Search, FileText, Sparkles,
} from "lucide-react";
import { hrApi } from "@/api/dashboard";
import { useAuthStore } from "@/store/authStore";

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

function RecBadge({ rec }) {
  const cfg = REC_CFG[rec] || REC_CFG["Consider"];
  return (
    <span style={{ display: "inline-flex", padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: cfg.bg, color: cfg.color }}>
      {rec}
    </span>
  );
}

function JobForm({ onSave, onCancel, saving, initial }) {
  const [form, setForm] = useState({
    position_title: initial?.position_title || "",
    required_skills: (initial?.required_skills || []).join(", "),
    min_experience: initial?.min_experience || 0,
    education_keywords: (initial?.education_keywords || []).join(", "),
    certification_keywords: (initial?.certification_keywords || []).join(", "),
  });
  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }));

  const submit = () => {
    onSave({
      position_title: form.position_title,
      required_skills: form.required_skills.split(",").map(s => s.trim()).filter(Boolean),
      min_experience: Number(form.min_experience) || 0,
      education_keywords: form.education_keywords.split(",").map(s => s.trim()).filter(Boolean),
      certification_keywords: form.certification_keywords.split(",").map(s => s.trim()).filter(Boolean),
    });
  };

  const inputStyle = { width: "100%", fontSize: 13, padding: "8px 12px", borderRadius: 10, border: "none", background: NEU.bg, color: "#1e293b", boxShadow: "inset 3px 3px 6px #c5cad8, inset -3px -3px 6px #ffffff", outline: "none", boxSizing: "border-box" };
  const labelStyle = { fontSize: 10, fontWeight: 700, color: "#94a3b8", display: "block", marginBottom: 3 };

  return (
    <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: 18, marginBottom: 16 }}>
      <h4 style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 12 }}>New Position / Job Config</h4>
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

function CandidateRow({ c, i, onDelete }) {
  const [expanded, setExpanded] = useState(false);
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
        <td style={{ padding: "8px 12px" }}><RecBadge rec={c.recommendation} /></td>
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
          </td>
        </tr>
      )}
    </>
  );
}

export default function HRCvScreening() {
  const { token } = useAuthStore();
  const [jobs, setJobs] = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);
  const [showJobForm, setShowJobForm] = useState(false);
  const [showJdPanel, setShowJdPanel] = useState(false);
  const [jdPrefill, setJdPrefill] = useState(null);
  const [savingJob, setSavingJob] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState(null);
  const [recFilter, setRecFilter] = useState("");
  const [search, setSearch] = useState("");
  const fileRef = useRef(null);

  const activeJob = jobs.find(j => j.id === activeJobId);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await hrApi.getCvJobs();
      setJobs(res);
      if (!activeJobId && res.length > 0) setActiveJobId(res[0].id);
    } catch (_) {}
  }, [activeJobId]);

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

  useEffect(() => { fetchJobs(); }, []); // eslint-disable-line
  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

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
      setActiveJobId(null);
      fetchJobs();
    } catch (_) {}
  };

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
      {/* Job selector */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {jobs.map(j => (
            <button key={j.id} onClick={() => setActiveJobId(j.id)}
              style={{
                padding: "8px 16px", borderRadius: 10, border: "none", fontSize: 12, fontWeight: 700,
                background: NEU.bg, cursor: "pointer",
                color: activeJobId === j.id ? "#2563eb" : "#64748b",
                boxShadow: activeJobId === j.id ? NEU.shadowIn : NEU.shadowOutSm,
              }}>
              {j.position_title}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => { setShowJdPanel(!showJdPanel); setShowJobForm(false); }}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: NEU.bg, color: "#7c3aed", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: showJdPanel ? NEU.shadowIn : NEU.shadowOutSm }}>
            <Sparkles size={14} /> Generate from JD
          </button>
          <button onClick={() => { setShowJobForm(!showJobForm); setJdPrefill(null); setShowJdPanel(false); }}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", boxShadow: NEU.shadowBtn }}>
            <Plus size={14} /> New Position
          </button>
        </div>
      </div>

      {showJdPanel && <JdGeneratorPanel onUseCriteria={handleUseJdCriteria} onCancel={() => setShowJdPanel(false)} />}

      {showJobForm && <JobForm onSave={handleCreateJob} onCancel={() => { setShowJobForm(false); setJdPrefill(null); }} saving={savingJob} initial={jdPrefill} />}

      {!activeJob && !showJobForm && (
        <div style={{ background: NEU.bg, boxShadow: NEU.shadowOut, borderRadius: 16, padding: "40px 20px", textAlign: "center" }}>
          <p style={{ fontSize: 13, color: "#94a3b8", fontWeight: 500 }}>
            No position configured yet. Click "+ New Position" to define job requirements and start screening CVs.
          </p>
        </div>
      )}

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
              <button onClick={() => handleDeleteJob(activeJob.id)}
                style={{ padding: "8px 10px", borderRadius: 10, border: "none", background: NEU.bg, color: "#dc2626", cursor: "pointer", boxShadow: NEU.shadowOutSm }}>
                <Trash2 size={13} />
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
                    {["", "Name", "Email", "Exp", "Education", "Skills", "Score", "Recommendation", ""].map(h => (
                      <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontSize: 10.5, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "2px solid rgba(0,0,0,0.06)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, i) => (
                    <CandidateRow key={c.id} c={c} i={i} onDelete={handleDeleteCandidate} />
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
