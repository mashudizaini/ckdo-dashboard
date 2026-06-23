import { useState, useEffect } from "react";
import {
  validateInvoice, updateInvoice, previewInterface,
  insertInterface, runImport, getInvoice,
} from "../services/api.js";
import StatusBadge from "../components/StatusBadge.jsx";

const fmt = (n) => n != null ? Number(n).toLocaleString("id-ID", { minimumFractionDigits: 2 }) : "-";

/* ── Step Bar ───────────────────────────────────────────────────── */
function StepBar({ current }) {
  const steps = [
    { n: 1, label: "Review Hasil Extract" },
    { n: 2, label: "Preview Interface" },
    { n: 3, label: "Insert ke Interface" },
    { n: 4, label: "Run Import" },
  ];
  return (
    <div style={{ display: "flex", marginBottom: 24 }}>
      {steps.map((s, i) => {
        const done = current > s.n;
        const active = current === s.n;
        const col = done || active ? "#1d4ed8" : "#cbd5e1";
        return (
          <div key={s.n} style={{ flex: 1, textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              {i > 0 && <div style={{ flex: 1, height: 2, background: done ? "#1d4ed8" : "#e2e8f0" }} />}
              <div style={{
                width: 30, height: 30, borderRadius: "50%", lineHeight: "30px",
                fontWeight: 700, fontSize: 13, textAlign: "center",
                background: col, color: done || active ? "#fff" : "#94a3b8",
              }}>{done ? "✓" : s.n}</div>
              {i < steps.length - 1 && <div style={{ flex: 1, height: 2, background: done ? "#1d4ed8" : "#e2e8f0" }} />}
            </div>
            <div style={{ fontSize: 11, marginTop: 4, fontWeight: active ? 700 : 400, color: active ? "#1d4ed8" : "#64748b" }}>{s.label}</div>
          </div>
        );
      })}
    </div>
  );
}

const Card = ({ title, children }) => (
  <div style={{ background: "#fff", borderRadius: 10, padding: 20, marginBottom: 16, boxShadow: "0 1px 3px #0001" }}>
    {title && <h4 style={{ color: "#475569", margin: "0 0 12px" }}>{title}</h4>}
    {children}
  </div>
);

/* ── Editable Interface Form ─────────────────────────────────────── */
function InterfaceForm({ header, lines, onHeaderChange, onLineChange }) {
  const cell = { padding: "5px 8px", fontSize: 12, borderBottom: "1px solid #f1f5f9" };
  const th = { ...cell, fontWeight: 600, color: "#64748b", background: "#f8fafc", textAlign: "left" };
  const inp = { border: "1px solid #cbd5e1", borderRadius: 4, padding: "3px 6px", fontSize: 12, width: "100%" };

  const readOnly = new Set(["INVOICE_TYPE_LOOKUP_CODE", "SOURCE", "ORG_ID", "CREATED_BY"]);

  const headerEntries = Object.entries(header);

  const lineColumns = lines.length > 0 ? Object.keys(lines[0]) : [];
  const lineReadOnly = new Set(["LINE_TYPE_LOOKUP_CODE", "ORG_ID"]);

  return (
    <>
      {/* Header */}
      <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
        <div style={{ background: "#1e3a5f", color: "#fff", padding: "8px 14px", fontSize: 12, fontWeight: 700 }}>
          AP_INVOICES_INTERFACE (Header)
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {headerEntries.map(([col, val]) => (
              <tr key={col}>
                <td style={{ ...cell, width: 240, fontFamily: "monospace", fontSize: 11, fontWeight: 600, color: "#475569" }}>{col}</td>
                <td style={cell}>
                  {readOnly.has(col)
                    ? <span style={{ fontSize: 12, color: "#94a3b8" }}>{val != null ? String(val) : "(null)"}</span>
                    : <input
                        value={val != null ? String(val) : ""}
                        onChange={e => onHeaderChange(col, e.target.value)}
                        style={inp}
                      />
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Lines */}
      <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ background: "#1e3a5f", color: "#fff", padding: "8px 14px", fontSize: 12, fontWeight: 700 }}>
          AP_INVOICE_LINES_INTERFACE ({lines.length} lines)
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 900 }}>
            <thead>
              <tr>{lineColumns.map(c => <th key={c} style={{ ...th, fontFamily: "monospace", fontSize: 10 }}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {lines.map((ln, i) => (
                <tr key={i}>
                  {lineColumns.map(c => (
                    <td key={c} style={cell}>
                      {lineReadOnly.has(c)
                        ? <span style={{ fontSize: 12, color: "#94a3b8" }}>{ln[c] != null ? String(ln[c]) : ""}</span>
                        : <input
                            value={ln[c] != null ? String(ln[c]) : ""}
                            onChange={e => onLineChange(i, c, e.target.value)}
                            style={{ ...inp, textAlign: typeof ln[c] === "number" ? "right" : "left" }}
                          />
                      }
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ── Validation Warnings ─────────────────────────────────────────── */
function Warnings({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      {items.map((w, i) => {
        const isWarning = w.type === "warning";
        return (
          <div key={i} style={{
            padding: "8px 14px", borderRadius: 8, fontSize: 13, marginBottom: 6,
            background: isWarning ? "#fef3c7" : "#e0f2fe",
            color: isWarning ? "#92400e" : "#0c4a6e",
            border: `1px solid ${isWarning ? "#fde68a" : "#bae6fd"}`,
          }}>
            {isWarning ? "⚠️" : "ℹ️"} {w.message}
          </div>
        );
      })}
    </div>
  );
}

/* ── Main ─────────────────────────────────────────────────────────── */
export default function Review({ invoice, onDone }) {
  const [data, setData] = useState(invoice.preview || invoice);
  const [stgId] = useState(invoice.stg_id);
  const [step, setStep] = useState(1);
  const [status, setStatus] = useState("NEW");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(invoice.message || "");
  const [error, setError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [intfHeader, setIntfHeader] = useState(null);
  const [intfLines, setIntfLines] = useState([]);
  const [result, setResult] = useState(null);
  const [matchType, setMatchType] = useState("none");
  const [poNumber, setPoNumber] = useState(null);

  useEffect(() => {
    if (invoice._fetchById) {
      (async () => {
        try {
          const full = await getInvoice(stgId);
          setData(full);
          setStatus(full.status || "NEW");
          if (full.status === "VALIDATED") setStep(2);
          else if (full.status === "INTERFACED") setStep(3);
          else if (full.status === "SUBMITTED" || full.status === "IMPORTED") setStep(4);
        } catch (e) { setError(e.message); }
      })();
    }
  }, [invoice._fetchById, stgId]);

  const field = (label, key, editable = false) => (
    <div style={{ display: "flex", gap: 8, padding: "5px 0", borderBottom: "1px solid #f1f5f9" }}>
      <span style={{ width: 150, color: "#64748b", fontSize: 13 }}>{label}</span>
      {editable
        ? <input value={data[key] || ""} onChange={e => setData({ ...data, [key]: e.target.value })}
            style={{ flex: 1, border: "1px solid #cbd5e1", borderRadius: 6, padding: "2px 8px", fontSize: 13 }} />
        : <span style={{ fontWeight: 500, fontSize: 13 }}>{data[key] || "-"}</span>}
    </div>
  );

  const act = async (fn) => {
    setLoading(true); setError(null); setMsg("");
    try { return await fn(); }
    catch (e) { setError(e.message); return null; }
    finally { setLoading(false); }
  };

  // Step 1: Validate (non-blocking)
  const handleValidate = () => act(async () => {
    await updateInvoice(stgId, {
      invoice_num: data.invoice_num, invoice_date: data.invoice_date,
      vendor_name: data.vendor_name, po_number: data.po_number,
      terms_date: data.terms_date, so_number: data.so_number,
    });
    const res = await validateInvoice(stgId);
    setStatus("VALIDATED");
    setMsg(res.message);
    setWarnings(res.warnings || []);

    // Auto-load preview
    const pv = await previewInterface(stgId);
    setIntfHeader(pv.header);
    setIntfLines(pv.lines);
    setPoNumber(pv.po_number || null);
    setMatchType("none");
    setStep(2);
  });

  // Step 2 → 3: Insert edited data to Oracle
  const handleInsert = () => act(async () => {
    // Convert numeric strings back to numbers
    const h = { ...intfHeader };
    for (const k of ["VENDOR_ID", "VENDOR_SITE_ID", "INVOICE_AMOUNT", "ORG_ID", "CREATED_BY"]) {
      if (h[k] != null) h[k] = Number(h[k]);
    }
    const ls = intfLines.map(ln => {
      const row = { ...ln };
      for (const k of ["LINE_NUMBER", "AMOUNT", "QUANTITY_INVOICED", "UNIT_PRICE", "ORG_ID"]) {
        if (row[k] != null) row[k] = Number(row[k]);
      }
      return row;
    });

    const res = await insertInterface(stgId, { header: h, lines: ls });
    setStatus("INTERFACED"); setMsg(res.message); setResult(res); setStep(3);
  });

  // Step 3 → 4: Run APXIIMPT
  const handleRunImport = () => act(async () => {
    const res = await runImport(stgId);
    setStatus("SUBMITTED"); setMsg(res.message); setResult(res); setStep(4);
    setTimeout(() => onDone(), 2000);
  });

  const onHeaderChange = (col, val) => setIntfHeader(prev => ({ ...prev, [col]: val }));
  const onLineChange = (idx, col, val) => setIntfLines(prev => prev.map((ln, i) => i === idx ? { ...ln, [col]: val } : ln));

  const handleMatchTypeChange = (type) => {
    setMatchType(type);
    setIntfLines(prev => prev.map((ln, i) => {
      if (type === "none") {
        return { ...ln, PO_NUMBER: null, PO_LINE_NUMBER: null, MATCH_OPTION: null };
      } else if (type === "2way") {
        return { ...ln, PO_NUMBER: poNumber, PO_LINE_NUMBER: i + 1, MATCH_OPTION: "P" };
      } else if (type === "3way") {
        return { ...ln, PO_NUMBER: poNumber, PO_LINE_NUMBER: i + 1, MATCH_OPTION: "R" };
      }
      return ln;
    }));
  };

  const btn = (bg, label, onClick) => (
    <button onClick={onClick} disabled={loading} style={{
      padding: "10px 24px", background: bg, color: "#fff", border: "none",
      borderRadius: 8, fontWeight: 600, cursor: "pointer", fontSize: 14,
      opacity: loading ? 0.6 : 1,
    }}>{loading ? "Loading..." : label}</button>
  );

  return (
    <div style={{ maxWidth: 960, margin: "24px auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ color: "#1e3a5f", margin: 0 }}>Review Invoice</h2>
        <StatusBadge status={status} />
      </div>

      <StepBar current={step} />

      {/* ── Step 1: Review Extracted Data ── */}
      {step === 1 && (
        <>
          <Card title="Header">
            {field("Invoice No.", "invoice_num", true)}
            {field("Invoice Date", "invoice_date", true)}
            {field("Vendor Name", "vendor_name", true)}
            {field("PO Number", "po_number", true)}
            {field("SO Number", "so_number", true)}
            {field("No. Faktur Pajak", "tax_serial_number", true)}
            {field("Payment Terms", "payment_terms", true)}
            {field("Jatuh Tempo", "terms_date", true)}
            {field("Currency", "currency_code")}
          </Card>
          <Card title="Nilai">
            {field("Subtotal", "subtotal")}
            {field("PPN (Tax)", "tax_amount")}
            {field("Total", "invoice_amount")}
          </Card>
          <Card title="Line Items">
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8fafc", color: "#64748b" }}>
                  {["#", "Kode", "Deskripsi", "Batch", "Qty", "Harga", "Amount"].map(h =>
                    <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontWeight: 600 }}>{h}</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {(data.lines || []).map(ln => (
                  <tr key={ln.line_num} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{ln.line_num}</td>
                    <td style={{ padding: "8px 10px" }}>{ln.item_code || "-"}</td>
                    <td style={{ padding: "8px 10px" }}>{ln.description}</td>
                    <td style={{ padding: "8px 10px" }}>{ln.batch_no || "-"}</td>
                    <td style={{ padding: "8px 10px", textAlign: "center" }}>{ln.qty}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>{fmt(ln.unit_price)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600 }}>{fmt(ln.line_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {/* ── Step 2: Editable Interface Preview ── */}
      {step === 2 && intfHeader && (
        <>
          <Warnings items={warnings} />

          {/* Match Type Selector */}
          {poNumber && (
            <Card title={`PO Matching — PO: ${poNumber}`}>
              <div style={{ display: "flex", gap: 10 }}>
                {[
                  { key: "none", label: "Tanpa PO Match", desc: "Invoice tanpa matching PO (match manual nanti)", color: "#64748b" },
                  { key: "2way", label: "2-Way Match", desc: "Match ke PO saja (tanpa receipt)", color: "#1d4ed8" },
                  { key: "3way", label: "3-Way Match", desc: "Match ke PO + Receipt (harus sudah di-receive)", color: "#7c3aed" },
                ].map(opt => (
                  <div key={opt.key} onClick={() => handleMatchTypeChange(opt.key)} style={{
                    flex: 1, padding: "12px 14px", borderRadius: 8, cursor: "pointer",
                    border: matchType === opt.key ? `2px solid ${opt.color}` : "2px solid #e2e8f0",
                    background: matchType === opt.key ? `${opt.color}11` : "#fff",
                  }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: opt.color, marginBottom: 4 }}>
                      {matchType === opt.key ? "● " : "○ "}{opt.label}
                    </div>
                    <div style={{ fontSize: 11, color: "#64748b" }}>{opt.desc}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div style={{
            background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8,
            padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#1e40af",
          }}>
            Periksa dan edit data di bawah sebelum insert ke Oracle. Field yang abu-abu tidak bisa diubah.
          </div>
          <InterfaceForm
            header={intfHeader}
            lines={intfLines}
            onHeaderChange={onHeaderChange}
            onLineChange={onLineChange}
          />
        </>
      )}

      {/* ── Step 3: Insert done ── */}
      {step === 3 && (
        <Card>
          <div style={{ textAlign: "center", padding: 24 }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>{"✅"}</div>
            <h3 style={{ color: "#15803d", margin: "0 0 8px" }}>Data berhasil masuk ke AP Interface</h3>
            {result && <p style={{ color: "#64748b", fontSize: 13 }}>Interface Invoice ID: <b>{result.interface_invoice_id}</b></p>}
            <p style={{ color: "#64748b", fontSize: 13 }}>Klik tombol di bawah untuk menjalankan import (APXIIMPT).</p>
          </div>
        </Card>
      )}

      {/* ── Step 4: Submitted ── */}
      {step === 4 && (
        <Card>
          <div style={{ textAlign: "center", padding: 24 }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>{"✅"}</div>
            <h3 style={{ color: "#15803d", margin: "0 0 8px" }}>APXIIMPT Submitted</h3>
            {result && <p style={{ color: "#64748b", fontSize: 13 }}>Request ID: <b>{result.conc_request_id}</b></p>}
            <p style={{ color: "#64748b", fontSize: 13 }}>Pantau progress di Tracker. Redirecting...</p>
          </div>
        </Card>
      )}

      {/* ── Messages ── */}
      {msg && <div style={{ padding: "10px 16px", background: "#f0fdf4", borderRadius: 8, color: "#15803d", fontSize: 13, marginTop: 12 }}>{msg}</div>}
      {error && (
        <div style={{ padding: "12px 16px", background: "#fee2e2", borderRadius: 8, color: "#b91c1c", fontSize: 13, marginTop: 12 }}>
          {error}
        </div>
      )}

      {/* ── Action Buttons ── */}
      <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", marginTop: 20 }}>
        {step === 1 && btn("#1d4ed8", "Validate & Preview", handleValidate)}
        {step === 2 && intfHeader && (
          <>
            {btn("#64748b", "Kembali", () => { setIntfHeader(null); setIntfLines([]); setWarnings([]); setStep(1); })}
            {btn("#15803d", "Insert ke Oracle Interface", handleInsert)}
          </>
        )}
        {step === 3 && btn("#0369a1", "Run Import (APXIIMPT)", handleRunImport)}
      </div>
    </div>
  );
}
