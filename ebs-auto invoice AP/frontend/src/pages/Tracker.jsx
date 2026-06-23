import { useState, useEffect, useCallback } from "react";
import { listInvoices, getRequestStatus, attachPdf } from "../services/api.js";
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

  const [attaching, setAttaching] = useState(null);
  const handleAttach = async (stgId) => {
    setAttaching(stgId);
    try {
      const res = await attachPdf(stgId);
      alert(res.message);
      await load();
    } catch(e) { alert("Attach gagal: " + e.message); }
    finally { setAttaching(null); }
  };

  const summary = ["NEW","VALIDATED","PROCESSING","INTERFACED","SUBMITTED","IMPORTED","ERROR"]
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
          {key:"SUBMITTED",color:"#0369a1",bg:"#e0f2fe",label:"Submitted"},
          {key:"INTERFACED",color:"#7c3aed",bg:"#ede9fe",label:"Interfaced"},
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
                        {["INTERFACED","SUBMITTED","IMPORTED"].includes(inv.status) && (
                          <button onClick={()=>checkStatus(inv.stg_id)} disabled={checking===inv.stg_id} style={actBtn("#7c3aed")}>
                            {checking===inv.stg_id?"...":"Cek"}
                          </button>
                        )}
                        {["IMPORTED","SUBMITTED"].includes(inv.status) && (
                          <button onClick={()=>handleAttach(inv.stg_id)} disabled={attaching===inv.stg_id} style={actBtn("#0369a1")}>
                            {attaching===inv.stg_id?"...":"Attach PDF"}
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
