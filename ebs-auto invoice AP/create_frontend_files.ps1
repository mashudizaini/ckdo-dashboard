# Script: Buat semua file frontend yang diperlukan
# Jalankan dari root project: D:\ebs-auto invoice AP\
# Usage: .\create_frontend_files.ps1

$base = "frontend\src"

# Buat folder struktur
New-Item -ItemType Directory -Force -Path "$base\pages"
New-Item -ItemType Directory -Force -Path "$base\components"
New-Item -ItemType Directory -Force -Path "$base\services"

Write-Host "Membuat file..." -ForegroundColor Cyan

# ── api.js ────────────────────────────────────────────────────────────────────
@'
const BASE = "/api";

export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload/`, { method: "POST", body: form });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Upload gagal"); }
  return res.json();
}
export async function listInvoices() {
  const res = await fetch(`${BASE}/invoices/`);
  if (!res.ok) throw new Error("Gagal ambil data");
  return res.json();
}
export async function getInvoice(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}`);
  if (!res.ok) throw new Error("Invoice tidak ditemukan");
  return res.json();
}
export async function updateInvoice(stgId, payload) {
  const res = await fetch(`${BASE}/invoices/${stgId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Update gagal"); }
  return res.json();
}
export async function validateInvoice(stgId) {
  const res = await fetch(`${BASE}/process/validate/${stgId}`, { method: "POST" });
  if (!res.ok) { const err = await res.json(); throw new Error(JSON.stringify(err.detail) || "Validasi gagal"); }
  return res.json();
}
export async function submitInvoice(stgId) {
  const res = await fetch(`${BASE}/process/submit/${stgId}`, { method: "POST" });
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Submit gagal"); }
  return res.json();
}
export async function getRequestStatus(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}/request-status`);
  if (!res.ok) throw new Error("Gagal cek status");
  return res.json();
}
'@ | Set-Content "$base\services\api.js" -Encoding UTF8

# ── StatusBadge.jsx ───────────────────────────────────────────────────────────
@'
const STATUS_CONFIG = {
  NEW:        { label: "Baru",        color: "#6b7280", bg: "#f3f4f6" },
  VALIDATED:  { label: "Tervalidasi", color: "#1d4ed8", bg: "#dbeafe" },
  PROCESSING: { label: "Diproses",    color: "#d97706", bg: "#fef3c7" },
  INTERFACED: { label: "Dikirim",     color: "#7c3aed", bg: "#ede9fe" },
  IMPORTED:   { label: "Selesai",     color: "#15803d", bg: "#dcfce7" },
  ERROR:      { label: "Error",       color: "#b91c1c", bg: "#fee2e2" },
};
export default function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: "#374151", bg: "#e5e7eb" };
  return (
    <span style={{ display:"inline-block", padding:"2px 10px", borderRadius:"12px",
      fontSize:"12px", fontWeight:"600", color:cfg.color, backgroundColor:cfg.bg }}>
      {cfg.label}
    </span>
  );
}
'@ | Set-Content "$base\components\StatusBadge.jsx" -Encoding UTF8

# ── Upload.jsx ────────────────────────────────────────────────────────────────
@'
import { useState, useRef } from "react";
import { uploadPDF } from "../services/api.js";

export default function Upload({ onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const inputRef = useRef();

  const handleFile = async (file) => {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) { setError("Hanya file PDF."); return; }
    setLoading(true); setError(null);
    try { const result = await uploadPDF(file); onUploaded(result); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ maxWidth:600, margin:"40px auto" }}>
      <h2 style={{ color:"#1e3a5f", marginBottom:24 }}>Upload Invoice PDF</h2>
      <div onClick={() => !loading && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
        style={{ border:`2px dashed ${dragging?"#1d4ed8":"#94a3b8"}`, borderRadius:12,
          padding:"48px 24px", textAlign:"center", cursor:loading?"not-allowed":"pointer",
          backgroundColor:dragging?"#eff6ff":"#f8fafc", transition:"all 0.2s" }}>
        <div style={{ fontSize:48, marginBottom:12 }}>📄</div>
        {loading ? <p style={{ color:"#6b7280" }}>Mengekstrak data...</p> : (
          <>
            <p style={{ color:"#374151", fontWeight:600 }}>Drag & drop file PDF invoice di sini</p>
            <p style={{ color:"#9ca3af", fontSize:14 }}>atau klik untuk pilih file</p>
          </>
        )}
        <input ref={inputRef} type="file" accept=".pdf" style={{ display:"none" }}
          onChange={(e) => handleFile(e.target.files[0])} />
      </div>
      {error && <div style={{ marginTop:16, padding:"12px 16px", backgroundColor:"#fee2e2",
        borderRadius:8, color:"#b91c1c", fontSize:14 }}>⚠️ {error}</div>}
    </div>
  );
}
'@ | Set-Content "$base\pages\Upload.jsx" -Encoding UTF8

# ── Review.jsx ────────────────────────────────────────────────────────────────
@'
import { useState } from "react";
import { validateInvoice, submitInvoice, updateInvoice } from "../services/api.js";
import StatusBadge from "../components/StatusBadge.jsx";

const fmt = (n) => n != null ? Number(n).toLocaleString("id-ID", { minimumFractionDigits:2 }) : "-";

export default function Review({ invoice, onDone }) {
  const [data,    setData]    = useState(invoice.preview || invoice);
  const [stgId]              = useState(invoice.stg_id);
  const [status,  setStatus]  = useState("NEW");
  const [loading, setLoading] = useState(false);
  const [msg,     setMsg]     = useState(invoice.message || "");
  const [error,   setError]   = useState(null);

  const field = (label, key, editable=false) => (
    <div style={{ display:"flex", gap:8, padding:"6px 0", borderBottom:"1px solid #f1f5f9" }}>
      <span style={{ width:160, color:"#64748b", fontSize:13, flexShrink:0 }}>{label}</span>
      {editable
        ? <input value={data[key]||""} onChange={(e)=>setData({...data,[key]:e.target.value})}
            style={{ flex:1, border:"1px solid #cbd5e1", borderRadius:6, padding:"2px 8px", fontSize:13 }}/>
        : <span style={{ fontWeight:500, fontSize:13, color:"#1e293b" }}>{data[key]||"-"}</span>}
    </div>
  );

  const handleValidate = async () => {
    setLoading(true); setError(null);
    try {
      await updateInvoice(stgId, { invoice_num:data.invoice_num, invoice_date:data.invoice_date,
        vendor_name:data.vendor_name, po_number:data.po_number, terms_date:data.terms_date });
      const res = await validateInvoice(stgId);
      setStatus("VALIDATED"); setMsg(res.message);
    } catch(e) { setError(e.message); setStatus("ERROR"); }
    finally { setLoading(false); }
  };

  const handleSubmit = async () => {
    setLoading(true); setError(null);
    try {
      const res = await submitInvoice(stgId);
      setStatus("INTERFACED"); setMsg(res.message);
      setTimeout(()=>onDone(), 1500);
    } catch(e) { setError(e.message); setStatus("ERROR"); }
    finally { setLoading(false); }
  };

  const btnStyle = (bg) => ({ padding:"10px 24px", background:bg, color:"#fff",
    border:"none", borderRadius:8, fontWeight:600, cursor:"pointer", fontSize:14 });

  return (
    <div style={{ maxWidth:800, margin:"24px auto" }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
        <h2 style={{ color:"#1e3a5f", margin:0 }}>Review Invoice</h2>
        <StatusBadge status={status}/>
      </div>
      <div style={{ background:"#fff", borderRadius:12, padding:20, marginBottom:16, boxShadow:"0 1px 4px #0001" }}>
        <h4 style={{ color:"#475569", marginBottom:12, marginTop:0 }}>📋 Header</h4>
        {field("Invoice No.",  "invoice_num",  true)}
        {field("Invoice Date", "invoice_date", true)}
        {field("Vendor Name",  "vendor_name",  true)}
        {field("PO Number",    "po_number",    true)}
        {field("SO Number",    "so_number")}
        {field("Jatuh Tempo",  "terms_date")}
        {field("Currency",     "currency_code")}
      </div>
      <div style={{ background:"#fff", borderRadius:12, padding:20, marginBottom:16, boxShadow:"0 1px 4px #0001" }}>
        <h4 style={{ color:"#475569", marginBottom:12, marginTop:0 }}>💰 Nilai</h4>
        {field("Subtotal",    "subtotal")}
        {field("PPN (Tax)",   "tax_amount")}
        {field("Total (IDR)", "invoice_amount")}
      </div>
      <div style={{ background:"#fff", borderRadius:12, padding:20, marginBottom:16, boxShadow:"0 1px 4px #0001" }}>
        <h4 style={{ color:"#475569", marginBottom:12, marginTop:0 }}>📦 Line Items</h4>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
          <thead>
            <tr style={{ background:"#f8fafc", color:"#64748b" }}>
              {["#","Kode","Deskripsi","Batch","Qty","Harga","Amount"].map(h=>(
                <th key={h} style={{ padding:"8px 10px", textAlign:"left", fontWeight:600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.lines||[]).map((ln)=>(
              <tr key={ln.line_num} style={{ borderBottom:"1px solid #f1f5f9" }}>
                <td style={{ padding:"8px 10px", color:"#94a3b8" }}>{ln.line_num}</td>
                <td style={{ padding:"8px 10px" }}>{ln.item_code||"-"}</td>
                <td style={{ padding:"8px 10px" }}>{ln.description}</td>
                <td style={{ padding:"8px 10px" }}>{ln.batch_no||"-"}</td>
                <td style={{ padding:"8px 10px", textAlign:"center" }}>{ln.qty}</td>
                <td style={{ padding:"8px 10px", textAlign:"right" }}>{fmt(ln.unit_price)}</td>
                <td style={{ padding:"8px 10px", textAlign:"right", fontWeight:600 }}>{fmt(ln.line_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {msg   && <div style={{ padding:"10px 16px", background:"#f0fdf4", borderRadius:8, color:"#15803d", fontSize:13, marginBottom:12 }}>✅ {msg}</div>}
      {error && <div style={{ padding:"10px 16px", background:"#fee2e2", borderRadius:8, color:"#b91c1c", fontSize:13, marginBottom:12 }}>⚠️ {error}</div>}
      <div style={{ display:"flex", gap:12, justifyContent:"flex-end" }}>
        {!["INTERFACED","IMPORTED"].includes(status) && (
          <button onClick={handleValidate} disabled={loading} style={btnStyle("#1d4ed8")}>
            {loading?"Validating...":"🔍 Validate"}
          </button>
        )}
        {status==="VALIDATED" && (
          <button onClick={handleSubmit} disabled={loading} style={btnStyle("#15803d")}>
            {loading?"Submitting...":"🚀 Submit ke EBS"}
          </button>
        )}
      </div>
    </div>
  );
}
'@ | Set-Content "$base\pages\Review.jsx" -Encoding UTF8

# ── Tracker.jsx ───────────────────────────────────────────────────────────────
@'
import { useState, useEffect, useCallback } from "react";
import { listInvoices, getRequestStatus } from "../services/api.js";
import StatusBadge from "../components/StatusBadge.jsx";

const fmt = (n) => n != null ? Number(n).toLocaleString("id-ID") : "-";

export default function Tracker({ onReview }) {
  const [invoices,  setInvoices]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [checking,  setChecking]  = useState(null);
  const [reqStatus, setReqStatus] = useState({});

  const load = useCallback(async () => {
    try { const data = await listInvoices(); setInvoices(data); }
    catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const iv = setInterval(load,15000); return ()=>clearInterval(iv); }, [load]);

  const checkStatus = async (stgId) => {
    setChecking(stgId);
    try { const res = await getRequestStatus(stgId); setReqStatus(p=>({...p,[stgId]:res})); await load(); }
    catch(e) { console.error(e); }
    finally { setChecking(null); }
  };

  const summary = ["NEW","VALIDATED","PROCESSING","INTERFACED","IMPORTED","ERROR"]
    .reduce((a,s)=>({...a,[s]:invoices.filter(i=>i.status===s).length}), {});

  const btnStyle = (bg) => ({ padding:"7px 16px", background:bg, color:"#fff",
    border:"none", borderRadius:6, fontWeight:600, cursor:"pointer" });
  const actBtn = (bg) => ({ padding:"4px 10px", background:bg, color:"#fff",
    border:"none", borderRadius:5, fontSize:12, cursor:"pointer", fontWeight:600 });

  return (
    <div style={{ maxWidth:1100, margin:"24px auto" }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
        <h2 style={{ color:"#1e3a5f", margin:0 }}>📊 Status Tracker</h2>
        <button onClick={load} style={{ ...btnStyle("#475569"), padding:"6px 16px", fontSize:13 }}>↻ Refresh</button>
      </div>
      <div style={{ display:"flex", gap:12, marginBottom:24, flexWrap:"wrap" }}>
        {[{key:"IMPORTED",color:"#15803d",bg:"#dcfce7",label:"Selesai"},
          {key:"INTERFACED",color:"#7c3aed",bg:"#ede9fe",label:"Dikirim"},
          {key:"VALIDATED",color:"#1d4ed8",bg:"#dbeafe",label:"Tervalidasi"},
          {key:"NEW",color:"#6b7280",bg:"#f3f4f6",label:"Baru"},
          {key:"ERROR",color:"#b91c1c",bg:"#fee2e2",label:"Error"}
        ].map(({key,label,color,bg})=>(
          <div key={key} style={{ background:bg, borderRadius:10, padding:"12px 20px", minWidth:110, textAlign:"center" }}>
            <div style={{ fontSize:24, fontWeight:700, color }}>{summary[key]||0}</div>
            <div style={{ fontSize:12, color, fontWeight:500 }}>{label}</div>
          </div>
        ))}
      </div>
      {loading ? <p style={{ color:"#94a3b8", textAlign:"center" }}>Memuat data...</p>
      : invoices.length===0 ? <p style={{ color:"#94a3b8", textAlign:"center" }}>Belum ada invoice.</p>
      : (
        <div style={{ background:"#fff", borderRadius:12, boxShadow:"0 1px 4px #0001", overflow:"hidden" }}>
          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
            <thead>
              <tr style={{ background:"#f8fafc", color:"#64748b" }}>
                {["STG ID","Invoice No","Vendor","Tgl Invoice","Amount (IDR)","Status","Upload","Aksi"].map(h=>(
                  <th key={h} style={{ padding:"10px 14px", textAlign:"left", fontWeight:600, whiteSpace:"nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv)=>(
                <>
                  <tr key={inv.stg_id}>
                    <td style={{ padding:"10px 14px", color:"#94a3b8" }}>{inv.stg_id}</td>
                    <td style={{ padding:"10px 14px", fontWeight:600 }}>{inv.invoice_num}</td>
                    <td style={{ padding:"10px 14px" }}>{inv.vendor_name}</td>
                    <td style={{ padding:"10px 14px" }}>{inv.invoice_date||"-"}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:600 }}>{fmt(inv.invoice_amount)}</td>
                    <td style={{ padding:"10px 14px" }}><StatusBadge status={inv.status}/></td>
                    <td style={{ padding:"10px 14px", color:"#94a3b8", fontSize:12 }}>{inv.created_date}</td>
                    <td style={{ padding:"10px 14px" }}>
                      <div style={{ display:"flex", gap:6 }}>
                        {["NEW","VALIDATED","ERROR"].includes(inv.status) && (
                          <button onClick={()=>onReview(inv.stg_id)} style={actBtn("#1d4ed8")}>Review</button>
                        )}
                        {["INTERFACED","IMPORTED"].includes(inv.status) && (
                          <button onClick={()=>checkStatus(inv.stg_id)} disabled={checking===inv.stg_id} style={actBtn("#7c3aed")}>
                            {checking===inv.stg_id?"...":"Cek"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {reqStatus[inv.stg_id] && (
                    <tr key={`rs-${inv.stg_id}`}>
                      <td colSpan={8} style={{ padding:"0 14px 10px" }}>
                        <div style={{ background:"#f8fafc", borderRadius:8, padding:"8px 14px", fontSize:12, color:"#475569" }}>
                          {(()=>{ const rs=reqStatus[inv.stg_id]; const p=[];
                            if(rs.concurrent) p.push(`Concurrent: ${rs.concurrent.phase}/${rs.concurrent.status}`);
                            if(rs.import){ p.push(`EBS: ${rs.import.status}`);
                              if(rs.import.invoice_id) p.push(`Invoice ID: ${rs.import.invoice_id}`);
                              if(rs.import.error_msg)  p.push(`⚠️ ${rs.import.error_msg}`); }
                            return p.join(" | "); })()}
                        </div>
                      </td>
                    </tr>
                  )}
                  {inv.status==="ERROR"&&inv.error_msg && (
                    <tr key={`err-${inv.stg_id}`}>
                      <td colSpan={8} style={{ padding:"0 14px 10px" }}>
                        <div style={{ background:"#fef2f2", borderRadius:8, padding:"6px 14px", fontSize:12, color:"#b91c1c" }}>
                          ⚠️ {inv.error_msg}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
'@ | Set-Content "$base\pages\Tracker.jsx" -Encoding UTF8

# ── main.jsx ──────────────────────────────────────────────────────────────────
@'
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);
'@ | Set-Content "$base\main.jsx" -Encoding UTF8

Write-Host ""
Write-Host "Selesai! Struktur file:" -ForegroundColor Green
Get-ChildItem $base -Recurse -File | ForEach-Object { Write-Host "  $($_.FullName)" }
