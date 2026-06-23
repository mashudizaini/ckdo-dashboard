import { useState, useEffect, useRef } from "react";
import {
  Upload, FileText, CheckCircle, Send, Loader2, AlertTriangle,
  RefreshCw, Eye, ChevronDown, ChevronUp, X,
} from "lucide-react";
import { apInvoiceApi } from "@/api/dashboard";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn: "inset 4px 4px 10px #c5cad8, inset -4px -4px 10px #ffffff",
  shadowBtn: "3px 3px 6px #c5cad8, -2px -2px 4px #ffffff",
  shadowBtnIn: "inset 2px 2px 4px rgba(0,0,0,0.15)",
};

const STATUS_BADGE = {
  NEW:        { bg: "#dbeafe", color: "#1d4ed8", label: "New" },
  VALIDATED:  { bg: "#d1fae5", color: "#059669", label: "Validated" },
  PROCESSING: { bg: "#fef3c7", color: "#d97706", label: "Processing" },
  INTERFACED: { bg: "#e0e7ff", color: "#4f46e5", label: "Interfaced" },
  SUBMITTED:  { bg: "#fce7f3", color: "#be185d", label: "Submitted" },
  IMPORTED:   { bg: "#d1fae5", color: "#047857", label: "Imported" },
  ERROR:      { bg: "#fee2e2", color: "#dc2626", label: "Error" },
};

function StatusPill({ status }) {
  const cfg = STATUS_BADGE[status] || STATUS_BADGE.NEW;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
      background: cfg.bg, color: cfg.color, letterSpacing: "0.03em",
    }}>
      {cfg.label}
    </span>
  );
}

function NeuBtn({ icon: Icon, label, color = "#2563eb", textColor = "#fff", onClick, disabled, loading }) {
  return (
    <button onClick={onClick} disabled={disabled || loading}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "9px 18px", borderRadius: 12, border: "none",
        background: color, color: textColor,
        fontSize: 13, fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
        boxShadow: NEU.shadowBtn, opacity: disabled ? 0.5 : 1,
        transition: "all 0.18s ease",
      }}
      onMouseDown={e => { if (!disabled) e.currentTarget.style.boxShadow = NEU.shadowBtnIn; }}
      onMouseUp={e => e.currentTarget.style.boxShadow = NEU.shadowBtn}
      onMouseLeave={e => e.currentTarget.style.boxShadow = NEU.shadowBtn}
    >
      {loading ? <Loader2 size={14} className="animate-spin" /> : Icon && <Icon size={14} />}
      {label}
    </button>
  );
}

export default function APAutoInvoice() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [actionLoading, setActionLoading] = useState("");
  const [message, setMessage] = useState(null);
  const fileRef = useRef(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await apInvoiceApi.list();
      setInvoices(data);
    } catch (e) {
      setMessage({ type: "error", text: "Gagal memuat data: " + (e?.detail || e?.message || String(e)) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await apInvoiceApi.upload(form);
      setMessage({ type: "success", text: `PDF berhasil di-extract! Invoice: ${res.preview?.invoice_num}` });
      refresh();
      setSelectedId(res.stg_id);
      loadDetail(res.stg_id);
    } catch (e) {
      setMessage({ type: "error", text: "Upload gagal: " + (e?.detail || e?.message || String(e)) });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const loadDetail = async (id) => {
    try {
      const data = await apInvoiceApi.get(id);
      setDetail(data);
      setSelectedId(id);
    } catch (e) {
      setMessage({ type: "error", text: "Gagal load detail" });
    }
  };

  const doAction = async (action, id) => {
    setActionLoading(action);
    setMessage(null);
    try {
      let res;
      if (action === "validate") {
        res = await apInvoiceApi.validate(id);
        if (res.warnings?.length) {
          setMessage({ type: "warning", text: res.warnings.map(w => w.message).join("; ") });
        } else {
          setMessage({ type: "success", text: "Validasi berhasil" });
        }
      } else if (action === "interface") {
        const preview = await apInvoiceApi.get(id);
        const header = {
          INVOICE_NUM: preview.invoice_num, INVOICE_DATE: preview.invoice_date,
          VENDOR_ID: preview.vendor_id, VENDOR_SITE_ID: preview.vendor_site_id,
          INVOICE_AMOUNT: preview.invoice_amount,
          INVOICE_CURRENCY_CODE: preview.currency_code || "IDR",
          TERMS_NAME: preview.payment_terms || "30 Days",
          TERMS_DATE: preview.terms_date, PO_NUMBER: preview.po_number,
          SO_NUMBER: preview.so_number, TAX_SERIAL_NUMBER: preview.tax_serial_number,
        };
        res = await apInvoiceApi.insertInterface(id, { header, lines: preview.lines || [] });
        setMessage({ type: "success", text: `Berhasil insert ke AP Interface (ID: ${res.interface_invoice_id})` });
      } else if (action === "import") {
        res = await apInvoiceApi.runImport(id);
        setMessage({ type: "success", text: `APXIIMPT submitted (Request ID: ${res.conc_request_id})` });
      }
      refresh();
      loadDetail(id);
    } catch (e) {
      setMessage({ type: "error", text: (e?.detail || e?.message || String(e)) });
    } finally {
      setActionLoading("");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header + Upload */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: "#1e293b", margin: 0 }}>AP Autoinvoice</h2>
          <p style={{ fontSize: 12, color: "#64748b", fontWeight: 500, marginTop: 2 }}>
            Upload PDF supplier → Extract → Validate → Import ke Oracle EBS
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <NeuBtn icon={RefreshCw} label="Refresh" color="#e8edf5" textColor="#475569" onClick={refresh} loading={loading} />
          <label style={{ cursor: "pointer" }}>
            <input ref={fileRef} type="file" accept=".pdf" onChange={handleUpload} style={{ display: "none" }} />
            <NeuBtn icon={Upload} label={uploading ? "Uploading..." : "Upload PDF"} color="#2563eb" onClick={() => fileRef.current?.click()} loading={uploading} />
          </label>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div style={{
          padding: "10px 16px", borderRadius: 12, fontSize: 13, fontWeight: 600,
          display: "flex", alignItems: "center", gap: 8,
          background: message.type === "error" ? "#fee2e2" : message.type === "warning" ? "#fef3c7" : "#d1fae5",
          color: message.type === "error" ? "#dc2626" : message.type === "warning" ? "#d97706" : "#059669",
          boxShadow: NEU.shadowOutSm,
        }}>
          {message.type === "error" ? <X size={14} /> : message.type === "warning" ? <AlertTriangle size={14} /> : <CheckCircle size={14} />}
          {message.text}
          <button onClick={() => setMessage(null)} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "inherit" }}>
            <X size={12} />
          </button>
        </div>
      )}

      <div style={{ display: "flex", gap: 16 }}>
        {/* Invoice List */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            borderRadius: 18, overflow: "hidden",
            boxShadow: NEU.shadowOut, background: NEU.bg,
          }}>
            <div style={{
              padding: "14px 18px",
              background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
              borderBottom: "2px solid rgba(0,0,0,0.06)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#374151" }}>
                Invoice Staging ({invoices.length})
              </span>
            </div>
            <div style={{ maxHeight: 500, overflowY: "auto" }}>
              {invoices.length === 0 ? (
                <div style={{ padding: "40px 20px", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
                  {loading ? "Memuat..." : "Belum ada invoice. Upload PDF untuk memulai."}
                </div>
              ) : invoices.map((inv, i) => (
                <div key={inv.stg_id}
                  onClick={() => loadDetail(inv.stg_id)}
                  style={{
                    padding: "12px 18px", cursor: "pointer",
                    background: selectedId === inv.stg_id ? "rgba(37,99,235,0.08)" : i % 2 === 0 ? "#f0f3f9" : "#e8edf5",
                    borderLeft: selectedId === inv.stg_id ? "3px solid #2563eb" : "3px solid transparent",
                    borderBottom: "1px solid rgba(0,0,0,0.04)",
                    transition: "all 0.15s ease",
                  }}
                  onMouseEnter={e => { if (selectedId !== inv.stg_id) e.currentTarget.style.background = "rgba(37,99,235,0.04)"; }}
                  onMouseLeave={e => { if (selectedId !== inv.stg_id) e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"; }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>{inv.invoice_num}</span>
                    <StatusPill status={inv.status} />
                  </div>
                  <div style={{ fontSize: 11.5, color: "#64748b", fontWeight: 500 }}>
                    {inv.vendor_name}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                    <span style={{ fontSize: 11, color: "#94a3b8" }}>{inv.invoice_date || "—"}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>
                      {inv.invoice_amount ? `Rp ${Number(inv.invoice_amount).toLocaleString("id-ID")}` : "—"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Detail Panel */}
        <div style={{ flex: 1.5, minWidth: 0 }}>
          {detail ? (
            <DetailPanel detail={detail} onAction={doAction} actionLoading={actionLoading} />
          ) : (
            <div style={{
              borderRadius: 18, padding: "60px 20px", textAlign: "center",
              boxShadow: NEU.shadowOut, background: NEU.bg,
              color: "#94a3b8", fontSize: 13, fontWeight: 500,
            }}>
              <FileText size={40} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
              Pilih invoice dari daftar untuk melihat detail
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailPanel({ detail, onAction, actionLoading }) {
  const [showLines, setShowLines] = useState(true);
  const d = detail;

  const canValidate  = d.status === "NEW" || d.status === "ERROR";
  const canInterface = d.status === "VALIDATED";
  const canImport    = d.status === "INTERFACED";

  return (
    <div style={{ borderRadius: 18, boxShadow: NEU.shadowOut, background: NEU.bg, overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px",
        background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
        borderBottom: "2px solid rgba(0,0,0,0.06)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, color: "#1e293b" }}>{d.invoice_num}</div>
          <div style={{ fontSize: 12, color: "#64748b", fontWeight: 500, marginTop: 2 }}>{d.vendor_name}</div>
        </div>
        <StatusPill status={d.status} />
      </div>

      <div style={{ padding: 20 }}>
        {/* Error message */}
        {d.error_msg && (
          <div style={{
            padding: "10px 14px", borderRadius: 12, marginBottom: 16, fontSize: 12,
            background: "#fee2e2", color: "#dc2626", fontWeight: 600,
            boxShadow: NEU.shadowOutSm,
          }}>
            {d.error_msg}
          </div>
        )}

        {/* Info Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
          {[
            { label: "Invoice Date", value: d.invoice_date || "—" },
            { label: "PO Number", value: d.po_number || "—" },
            { label: "Currency", value: d.currency_code || "IDR" },
            { label: "Subtotal", value: d.subtotal ? `Rp ${Number(d.subtotal).toLocaleString("id-ID")}` : "—" },
            { label: "Tax", value: d.tax_amount ? `Rp ${Number(d.tax_amount).toLocaleString("id-ID")}` : "—" },
            { label: "Total", value: d.invoice_amount ? `Rp ${Number(d.invoice_amount).toLocaleString("id-ID")}` : "—" },
            { label: "Payment Terms", value: d.payment_terms || "—" },
            { label: "Terms Date", value: d.terms_date || "—" },
            { label: "Source File", value: d.source_file || "—" },
          ].map((f) => (
            <div key={f.label} style={{
              padding: "10px 14px", borderRadius: 14,
              background: NEU.bg, boxShadow: NEU.shadowOutSm,
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                {f.label}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", wordBreak: "break-all" }}>
                {f.value}
              </div>
            </div>
          ))}
        </div>

        {/* Lines */}
        <div style={{ marginBottom: 16 }}>
          <button onClick={() => setShowLines(!showLines)} style={{
            display: "flex", alignItems: "center", gap: 6, background: "none",
            border: "none", cursor: "pointer", fontSize: 13, fontWeight: 700,
            color: "#374151", marginBottom: 8,
          }}>
            {showLines ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            Line Items ({d.lines?.length || 0})
          </button>
          {showLines && d.lines?.length > 0 && (
            <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                    {["#", "Description", "Qty", "Unit Price", "Amount"].map(h => (
                      <th key={h} style={{
                        padding: "10px 12px", fontSize: 11, fontWeight: 700,
                        color: "#374151", textAlign: h === "Description" ? "left" : "right",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        borderBottom: "2px solid rgba(0,0,0,0.06)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.lines.map((ln, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 600, color: "#64748b", textAlign: "right" }}>{ln.line_num}</td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b" }}>{ln.description}</td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "right" }}>{ln.qty}</td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "right" }}>
                        {Number(ln.unit_price).toLocaleString("id-ID")}
                      </td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 700, color: "#1e293b", textAlign: "right" }}>
                        {Number(ln.line_amount).toLocaleString("id-ID")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {canValidate && (
            <NeuBtn icon={CheckCircle} label="Validate" color="#059669"
              onClick={() => onAction("validate", d.stg_id)} loading={actionLoading === "validate"} />
          )}
          {canInterface && (
            <NeuBtn icon={Send} label="Insert to Interface" color="#4f46e5"
              onClick={() => onAction("interface", d.stg_id)} loading={actionLoading === "interface"} />
          )}
          {canImport && (
            <NeuBtn icon={Send} label="Run APXIIMPT" color="#be185d"
              onClick={() => onAction("import", d.stg_id)} loading={actionLoading === "import"} />
          )}
          {d.status === "IMPORTED" && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 14px", borderRadius: 12, fontSize: 12, fontWeight: 700,
              background: "#d1fae5", color: "#047857",
              boxShadow: NEU.shadowOutSm,
            }}>
              <CheckCircle size={14} /> Invoice berhasil di-import ke EBS
              {d.ap_invoice_id && <span>(ID: {d.ap_invoice_id})</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
