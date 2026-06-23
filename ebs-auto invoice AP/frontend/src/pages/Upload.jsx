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
