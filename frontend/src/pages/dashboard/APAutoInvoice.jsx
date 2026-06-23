import { useState, useEffect, useRef } from "react";
import {
  Upload, FileText, CheckCircle, Send, Loader2, AlertTriangle,
  RefreshCw, ChevronDown, ChevronUp, X, Pencil, Trash2, Save,
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

function NeuBtn({ icon: Icon, label, color = "#2563eb", textColor = "#fff", onClick, disabled, loading, small }) {
  return (
    <button onClick={onClick} disabled={disabled || loading}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: small ? "6px 12px" : "9px 18px", borderRadius: small ? 8 : 12, border: "none",
        background: color, color: textColor,
        fontSize: small ? 11 : 13, fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
        boxShadow: NEU.shadowBtn, opacity: disabled ? 0.5 : 1,
        transition: "all 0.18s ease",
      }}
      onMouseDown={e => { if (!disabled) e.currentTarget.style.boxShadow = NEU.shadowBtnIn; }}
      onMouseUp={e => e.currentTarget.style.boxShadow = NEU.shadowBtn}
      onMouseLeave={e => e.currentTarget.style.boxShadow = NEU.shadowBtn}
    >
      {loading ? <Loader2 size={small ? 12 : 14} className="animate-spin" /> : Icon && <Icon size={small ? 12 : 14} />}
      {label}
    </button>
  );
}

function EditInput({ value, onChange, type = "text", align = "left", style: extraStyle }) {
  return (
    <input
      type={type}
      value={value ?? ""}
      onChange={e => onChange(type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)}
      style={{
        width: "100%", padding: "6px 10px", borderRadius: 8, border: "none",
        background: NEU.bg, fontSize: 13, fontWeight: 600, color: "#1e293b",
        boxShadow: "inset 2px 2px 5px #c5cad8, inset -2px -2px 5px #ffffff",
        outline: "none", textAlign: align, boxSizing: "border-box",
        ...extraStyle,
      }}
    />
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
      await refresh();
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

  const handleDelete = async (id) => {
    if (!confirm("Hapus invoice ini dari staging?")) return;
    setActionLoading("delete");
    try {
      await apInvoiceApi.delete(id);
      setMessage({ type: "success", text: "Invoice berhasil dihapus" });
      setDetail(null);
      setSelectedId(null);
      await refresh();
    } catch (e) {
      setMessage({ type: "error", text: (e?.detail || e?.message || String(e)) });
    } finally {
      setActionLoading("");
    }
  };

  const handleSave = async (id, payload) => {
    setActionLoading("save");
    setMessage(null);
    try {
      await apInvoiceApi.update(id, payload);
      setMessage({ type: "success", text: "Data berhasil disimpan" });
      await refresh();
      loadDetail(id);
    } catch (e) {
      setMessage({ type: "error", text: (e?.detail || e?.message || String(e)) });
    } finally {
      setActionLoading("");
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
      await refresh();
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
            Upload PDF supplier → Extract → Review/Edit → Validate → Import ke Oracle EBS
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
          <div style={{ borderRadius: 18, overflow: "hidden", boxShadow: NEU.shadowOut, background: NEU.bg }}>
            <div style={{
              padding: "14px 18px", background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
              borderBottom: "2px solid rgba(0,0,0,0.06)",
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
                  <div style={{ fontSize: 11.5, color: "#64748b", fontWeight: 500 }}>{inv.vendor_name}</div>
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
            <DetailPanel
              detail={detail}
              onAction={doAction}
              onDelete={handleDelete}
              onSave={handleSave}
              actionLoading={actionLoading}
            />
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

function DetailPanel({ detail, onAction, onDelete, onSave, actionLoading }) {
  const [showLines, setShowLines] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [editLines, setEditLines] = useState([]);

  const d = detail;
  const canEdit = ["NEW", "VALIDATED", "ERROR"].includes(d.status);
  const canValidate = d.status === "NEW" || d.status === "ERROR";
  const canInterface = d.status === "VALIDATED";
  const canImport = d.status === "INTERFACED";

  const startEdit = () => {
    setForm({
      invoice_num: d.invoice_num,
      invoice_date: d.invoice_date || "",
      vendor_name: d.vendor_name || "",
      po_number: d.po_number || "",
      so_number: d.so_number || "",
      currency_code: d.currency_code || "IDR",
      subtotal: d.subtotal || 0,
      tax_amount: d.tax_amount || 0,
      invoice_amount: d.invoice_amount || 0,
      terms_date: d.terms_date || "",
    });
    setEditLines((d.lines || []).map(ln => ({ ...ln })));
    setEditing(true);
  };

  const cancelEdit = () => { setEditing(false); };

  const saveEdit = () => {
    const payload = { ...form };
    if (editLines.length > 0) {
      payload.lines_json = JSON.stringify(editLines);
    }
    onSave(d.stg_id, payload);
    setEditing(false);
  };

  const updateLine = (idx, field, value) => {
    setEditLines(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const removeLine = (idx) => {
    setEditLines(prev => prev.filter((_, i) => i !== idx));
  };

  const FIELDS = [
    { key: "invoice_num",    label: "Invoice Number" },
    { key: "invoice_date",   label: "Invoice Date" },
    { key: "vendor_name",    label: "Vendor Name" },
    { key: "po_number",      label: "PO Number" },
    { key: "currency_code",  label: "Currency" },
    { key: "subtotal",       label: "Subtotal", type: "number", fmt: true },
    { key: "tax_amount",     label: "Tax", type: "number", fmt: true },
    { key: "invoice_amount", label: "Total", type: "number", fmt: true },
    { key: "terms_date",     label: "Terms Date" },
  ];

  return (
    <div style={{ borderRadius: 18, boxShadow: NEU.shadowOut, background: NEU.bg, overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px", background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
        borderBottom: "2px solid rgba(0,0,0,0.06)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, color: "#1e293b" }}>{d.invoice_num}</div>
          <div style={{ fontSize: 12, color: "#64748b", fontWeight: 500, marginTop: 2 }}>{d.vendor_name}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusPill status={d.status} />
          {canEdit && !editing && (
            <>
              <NeuBtn icon={Pencil} label="Edit" color="#e8edf5" textColor="#2563eb" onClick={startEdit} small />
              <NeuBtn icon={Trash2} label="Hapus" color="#e8edf5" textColor="#dc2626" onClick={() => onDelete(d.stg_id)} loading={actionLoading === "delete"} small />
            </>
          )}
        </div>
      </div>

      <div style={{ padding: 20 }}>
        {/* Error message */}
        {d.error_msg && (
          <div style={{
            padding: "10px 14px", borderRadius: 12, marginBottom: 16, fontSize: 12,
            background: "#fee2e2", color: "#dc2626", fontWeight: 600, boxShadow: NEU.shadowOutSm,
          }}>
            {d.error_msg}
          </div>
        )}

        {/* Info Grid — view or edit mode */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
          {FIELDS.map((f) => (
            <div key={f.key} style={{
              padding: "10px 14px", borderRadius: 14,
              background: NEU.bg, boxShadow: NEU.shadowOutSm,
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                {f.label}
              </div>
              {editing ? (
                <EditInput
                  value={form[f.key]}
                  onChange={v => setForm(p => ({ ...p, [f.key]: v }))}
                  type={f.type || "text"}
                />
              ) : (
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", wordBreak: "break-all" }}>
                  {f.fmt && d[f.key] ? `Rp ${Number(d[f.key]).toLocaleString("id-ID")}` : (d[f.key] || "—")}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Edit save/cancel bar */}
        {editing && (
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <NeuBtn icon={Save} label="Simpan" color="#059669" onClick={saveEdit} loading={actionLoading === "save"} />
            <NeuBtn icon={X} label="Batal" color="#e8edf5" textColor="#64748b" onClick={cancelEdit} />
          </div>
        )}

        {/* Lines */}
        <div style={{ marginBottom: 16 }}>
          <button onClick={() => setShowLines(!showLines)} style={{
            display: "flex", alignItems: "center", gap: 6, background: "none",
            border: "none", cursor: "pointer", fontSize: 13, fontWeight: 700,
            color: "#374151", marginBottom: 8,
          }}>
            {showLines ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            Line Items ({editing ? editLines.length : (d.lines?.length || 0)})
          </button>

          {showLines && (editing ? editLines : d.lines)?.length > 0 && (
            <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                    {["#", "Description", "Qty", "Unit Price", "Amount", ...(editing ? [""] : [])].map(h => (
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
                  {(editing ? editLines : d.lines).map((ln, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 600, color: "#64748b", textAlign: "right", width: 40 }}>
                        {ln.line_num}
                      </td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
                        {editing ? (
                          <EditInput value={ln.description} onChange={v => updateLine(i, "description", v)} />
                        ) : ln.description}
                      </td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "right", width: 80 }}>
                        {editing ? (
                          <EditInput value={ln.qty} onChange={v => updateLine(i, "qty", v)} type="number" align="right" />
                        ) : ln.qty}
                      </td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 500, color: "#475569", textAlign: "right", width: 120 }}>
                        {editing ? (
                          <EditInput value={ln.unit_price} onChange={v => updateLine(i, "unit_price", v)} type="number" align="right" />
                        ) : Number(ln.unit_price).toLocaleString("id-ID")}
                      </td>
                      <td style={{ padding: "8px 12px", fontSize: 12, fontWeight: 700, color: "#1e293b", textAlign: "right", width: 120 }}>
                        {editing ? (
                          <EditInput value={ln.line_amount} onChange={v => updateLine(i, "line_amount", v)} type="number" align="right" />
                        ) : Number(ln.line_amount).toLocaleString("id-ID")}
                      </td>
                      {editing && (
                        <td style={{ padding: "8px 6px", textAlign: "center", width: 36 }}>
                          <button onClick={() => removeLine(i)} style={{
                            background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4,
                          }} title="Hapus baris">
                            <Trash2 size={13} />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Actions */}
        {!editing && (
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
                background: "#d1fae5", color: "#047857", boxShadow: NEU.shadowOutSm,
              }}>
                <CheckCircle size={14} /> Invoice berhasil di-import ke EBS
                {d.ap_invoice_id && <span>(ID: {d.ap_invoice_id})</span>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
