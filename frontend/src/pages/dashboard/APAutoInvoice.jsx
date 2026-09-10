import { useState, useEffect, useRef } from "react";
import {
  Upload, FileText, CheckCircle, Send, Loader2, AlertTriangle,
  RefreshCw, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, X, Pencil, Trash2, Save, Search, Paperclip, Link2,
} from "lucide-react";
import { apInvoiceApi, supplierWhtApi } from "@/api/dashboard";

const NEU = {
  bg: "#f1f5f9",
  shadowOut: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  shadowOutSm: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
  shadowIn: "inset 0 2px 5px rgba(15,23,42,0.09)",
  shadowBtn: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
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
        boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
        outline: "none", textAlign: align, boxSizing: "border-box",
        ...extraStyle,
      }}
    />
  );
}

// Shared by the single-invoice "Insert to Interface" action and bulk
// processing — Oracle only accepts WHT as a GROUP NAME on the header (see
// insert_to_interface's comment for why a manual AWT-type line is
// rejected outright).
function buildInterfaceHeader(preview) {
  return {
    INVOICE_NUM: preview.invoice_num, INVOICE_DATE: preview.invoice_date,
    RECEIVED_DATE: preview.received_date,
    VENDOR_ID: preview.vendor_id, VENDOR_SITE_ID: preview.vendor_site_id,
    INVOICE_AMOUNT: preview.invoice_amount,
    INVOICE_CURRENCY_CODE: preview.currency_code || "IDR",
    TERMS_NAME: preview.payment_terms || "30 Days",
    TERMS_DATE: preview.terms_date, PO_NUMBER: preview.po_number,
    SO_NUMBER: preview.so_number, TAX_SERIAL_NUMBER: preview.tax_serial_number,
    FAKTUR_PAJAK_DATE: preview.faktur_pajak_date,
    AWT_GROUP_ID: preview.wht_enabled ? preview.awt_group_id : null,
    AWT_GROUP_NAME: preview.wht_enabled ? preview.awt_group_name : null,
  };
}

// Bulk processing advances each selected invoice by exactly one step in
// its own pipeline — never guesses which step an ERROR invoice failed at,
// so those are skipped and left for one-at-a-time handling.
function nextActionFor(status) {
  if (status === "NEW") return "validate";
  if (status === "VALIDATED" || status === "PROCESSING") return "interface";
  if (status === "INTERFACED" || status === "SUBMITTED") return "import";
  return null;
}

export default function APAutoInvoice() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [ocrProvider, setOcrProvider] = useState("onprem"); // "onprem" (standard, default) | "anthropic" (premium)
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [actionLoading, setActionLoading] = useState("");
  const [message, setMessage] = useState(null);
  const [batchProgress, setBatchProgress] = useState(null); // { done, total, current } while a multi-file upload is running
  const [listPage, setListPage] = useState(1);
  const LIST_PAGE_SIZE = 5;
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkProgress, setBulkProgress] = useState(null); // { done, total, current } while bulk-processing runs
  const fileRef = useRef(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await apInvoiceApi.list();
      setInvoices(data);
    } catch (e) {
      setMessage({ type: "error", text: "Failed to load data: " + (e?.detail || e?.message || String(e)) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  // Multiple PDFs (one invoice each) are processed one at a time, not in
  // parallel — the on-premise AI engine runs one Ollama vision instance, so
  // firing several extractions at once would just queue up behind it while
  // giving no progress feedback in the meantime. Each file succeeds or
  // fails independently (a bad PDF partway through the batch doesn't stop
  // the rest), and the list only refreshes once at the end.
  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    setMessage(null);
    setBatchProgress({ done: 0, total: files.length, current: files[0].name });

    const results = [];
    let lastStgId = null;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setBatchProgress({ done: i, total: files.length, current: file.name });
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await apInvoiceApi.upload(form, ocrProvider);
        results.push({ file: file.name, success: true, invoice_num: res.preview?.invoice_num });
        lastStgId = res.stg_id;
      } catch (err) {
        results.push({ file: file.name, success: false, error: err?.detail || err?.message || String(err) });
      }
      setBatchProgress({ done: i + 1, total: files.length, current: file.name });
    }

    const okCount = results.filter(r => r.success).length;
    const failed = results.filter(r => !r.success);
    if (files.length === 1) {
      setMessage(okCount === 1
        ? { type: "success", text: `PDF extracted successfully! Invoice: ${results[0].invoice_num}` }
        : { type: "error", text: "Upload failed: " + failed[0].error });
    } else {
      setMessage({
        type: failed.length === 0 ? "success" : okCount === 0 ? "error" : "warning",
        text: `Processed ${files.length} file(s): ${okCount} succeeded` +
          (failed.length ? `, ${failed.length} failed — ${failed.map(f => `${f.file} (${f.error})`).join("; ")}` : "."),
      });
    }

    await refresh();
    if (lastStgId) { setSelectedId(lastStgId); loadDetail(lastStgId); }
    setUploading(false);
    setBatchProgress(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const loadDetail = async (id) => {
    try {
      const data = await apInvoiceApi.get(id);
      setDetail(data);
      setSelectedId(id);
    } catch (e) {
      setMessage({ type: "error", text: "Failed to load detail" });
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this invoice from staging?")) return;
    setActionLoading("delete");
    try {
      await apInvoiceApi.delete(id);
      setMessage({ type: "success", text: "Invoice deleted successfully" });
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
      setMessage({ type: "success", text: "Data saved successfully" });
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
          setMessage({ type: "success", text: "Validation successful" });
        }
      } else if (action === "interface") {
        const preview = await apInvoiceApi.get(id);
        const header = buildInterfaceHeader(preview);
        res = await apInvoiceApi.insertInterface(id, { header, lines: preview.lines || [] });
        setMessage({ type: "success", text: `Successfully inserted to AP Interface (ID: ${res.interface_invoice_id})` });
      } else if (action === "import") {
        res = await apInvoiceApi.runImport(id);
        setMessage({ type: "success", text: `APXIIMPT submitted (Request ID: ${res.conc_request_id}). Click "Check Status" to check the result.` });
      } else if (action === "attach") {
        res = await apInvoiceApi.attachPdf(id);
        setMessage({ type: "success", text: res.message });
      } else if (action === "check") {
        res = await apInvoiceApi.checkStatus(id);
        if (res.stg_status === "IMPORTED") {
          setMessage({ type: "success", text: `Invoice imported to EBS successfully! (AP Invoice ID: ${res.import?.invoice_id})` });
        } else if (res.stg_status === "ERROR") {
          setMessage({ type: "error", text: res.import?.error_msg || "Import failed" });
        } else {
          const phase = res.concurrent?.phase || "—";
          const status = res.concurrent?.status || "—";
          setMessage({ type: "warning", text: `Concurrent: ${phase} / ${status}. Invoice not yet found in ap_invoices_all. Try again later.` });
        }
      }
      await refresh();
      loadDetail(id);
    } catch (e) {
      setMessage({ type: "error", text: (e?.detail || e?.message || String(e)) });
    } finally {
      setActionLoading("");
    }
  };

  const toggleSelected = (stgId) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(stgId)) next.delete(stgId); else next.add(stgId);
      return next;
    });
  };

  // Advances each selected invoice one step (Validate / Insert to
  // Interface / Run APXIIMPT) sequentially — one at a time, same reasoning
  // as the multi-file upload above. ERROR invoices are skipped rather than
  // guessed at, since which step actually failed isn't determinable here.
  const handleBulkProcess = async () => {
    const targets = invoices.filter(inv => selectedIds.has(inv.stg_id));
    const runnable = targets.filter(inv => nextActionFor(inv.status));
    const skipped = targets.length - runnable.length;
    if (runnable.length === 0) {
      setMessage({ type: "warning", text: "Tidak ada invoice terpilih yang bisa diproses otomatis (status ERROR ditangani satu per satu, IMPORTED sudah selesai)." });
      return;
    }
    setBulkProgress({ done: 0, total: runnable.length, current: runnable[0].invoice_num });
    setMessage(null);
    const results = [];
    for (let i = 0; i < runnable.length; i++) {
      const inv = runnable[i];
      const action = nextActionFor(inv.status);
      setBulkProgress({ done: i, total: runnable.length, current: inv.invoice_num });
      try {
        if (action === "validate") {
          await apInvoiceApi.validate(inv.stg_id);
        } else if (action === "interface") {
          const preview = await apInvoiceApi.get(inv.stg_id);
          const header = buildInterfaceHeader(preview);
          await apInvoiceApi.insertInterface(inv.stg_id, { header, lines: preview.lines || [] });
        } else if (action === "import") {
          await apInvoiceApi.runImport(inv.stg_id);
        }
        results.push({ invoice_num: inv.invoice_num, success: true });
      } catch (err) {
        results.push({ invoice_num: inv.invoice_num, success: false, error: err?.detail || err?.message || String(err) });
      }
      setBulkProgress({ done: i + 1, total: runnable.length, current: inv.invoice_num });
    }
    const okCount = results.filter(r => r.success).length;
    const failed = results.filter(r => !r.success);
    setMessage({
      type: failed.length === 0 ? "success" : okCount === 0 ? "error" : "warning",
      text: `Bulk process: ${okCount}/${runnable.length} berhasil` +
        (skipped ? `, ${skipped} dilewati (status ERROR/Imported)` : "") +
        (failed.length ? ` — gagal: ${failed.map(f => `${f.invoice_num} (${f.error})`).join("; ")}` : "."),
    });
    setSelectedIds(new Set());
    setBulkProgress(null);
    await refresh();
  };

  const totalListPages = Math.max(1, Math.ceil(invoices.length / LIST_PAGE_SIZE));
  const safeListPage = Math.min(listPage, totalListPages);
  const pagedInvoices = invoices.slice((safeListPage - 1) * LIST_PAGE_SIZE, safeListPage * LIST_PAGE_SIZE);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header + Upload */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: "#1e293b", margin: 0 }}>AP Autoinvoice</h2>
          <p style={{ fontSize: 12, color: "#64748b", fontWeight: 500, marginTop: 2 }}>
            Upload supplier PDF → Extract → Review/Edit → Validate → Import to Oracle EBS
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <select value={ocrProvider} onChange={e => setOcrProvider(e.target.value)} disabled={uploading}
            title="AI provider used to extract data from the PDF"
            style={{ fontSize: 11.5, fontWeight: 600, padding: "8px 12px", borderRadius: 10, border: "none", background: "#f1f5f9", color: "#1e293b", boxShadow: NEU.shadowOutSm, cursor: "pointer", outline: "none", colorScheme: "light" }}>
            <option value="onprem">Standard (On-Premise AI)</option>
            <option value="anthropic">Premium (Anthropic Claude)</option>
          </select>
          <NeuBtn icon={RefreshCw} label="Refresh" color="#f1f5f9" textColor="#475569" onClick={refresh} loading={loading} />
          <label style={{ cursor: "pointer" }} title="Select one or more PDFs — each becomes its own invoice, processed one at a time">
            <input ref={fileRef} type="file" accept=".pdf" multiple onChange={handleUpload} style={{ display: "none" }} />
            <NeuBtn icon={Upload} label={uploading ? "Uploading..." : "Upload PDF(s)"} color="#2563eb" onClick={() => fileRef.current?.click()} loading={uploading} />
          </label>
        </div>
      </div>

      {/* Batch upload progress */}
      {batchProgress && (
        <div style={{
          padding: "10px 16px", borderRadius: 12, fontSize: 12, fontWeight: 600,
          display: "flex", alignItems: "center", gap: 10,
          background: "#dbeafe", color: "#1d4ed8", boxShadow: NEU.shadowOutSm,
        }}>
          <Loader2 size={14} className="animate-spin" />
          Processing {batchProgress.done + 1} of {batchProgress.total}: {batchProgress.current}
          <div style={{ flex: 1, height: 6, borderRadius: 3, background: "rgba(29,78,216,0.15)", overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 3, background: "#2563eb",
              width: `${Math.round((batchProgress.done / batchProgress.total) * 100)}%`,
              transition: "width 0.2s ease",
            }} />
          </div>
        </div>
      )}

      {/* Bulk-process progress */}
      {bulkProgress && (
        <div style={{
          padding: "10px 16px", borderRadius: 12, fontSize: 12, fontWeight: 600,
          display: "flex", alignItems: "center", gap: 10,
          background: "#e0e7ff", color: "#4338ca", boxShadow: NEU.shadowOutSm,
        }}>
          <Loader2 size={14} className="animate-spin" />
          Bulk processing {bulkProgress.done + 1} of {bulkProgress.total}: {bulkProgress.current}
          <div style={{ flex: 1, height: 6, borderRadius: 3, background: "rgba(67,56,202,0.15)", overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 3, background: "#4338ca",
              width: `${Math.round((bulkProgress.done / bulkProgress.total) * 100)}%`,
              transition: "width 0.2s ease",
            }} />
          </div>
        </div>
      )}

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

      {/* Invoice Staging — header data as a list, one row per invoice, since
          a single upload batch can now produce several at once. A checkbox
          column lets several be bulk-processed at once (advances each one
          step); WHT is now shown as a line-level detail (see Line Items in
          the panel below) rather than toggled per invoice here; Delete is
          the last column. */}
      <div style={{ borderRadius: 18, overflow: "hidden", boxShadow: NEU.shadowOut, background: NEU.bg }}>
        <div style={{
          padding: "14px 18px", background: "linear-gradient(135deg, #dfe5ed, #d8dee8)",
          borderBottom: "2px solid rgba(0,0,0,0.06)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "#374151" }}>
            Invoice Staging ({invoices.length})
          </span>
          {selectedIds.size > 0 && (
            <NeuBtn small icon={Send} label={`Process Selected (${selectedIds.size})`} color="#4338ca"
              onClick={handleBulkProcess} loading={!!bulkProgress} />
          )}
        </div>
        <div style={{ overflow: "auto" }}>
          {invoices.length === 0 ? (
            <div style={{ padding: "40px 20px", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
              {loading ? "Loading..." : "No invoices yet. Upload PDF to get started."}
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 960 }}>
              <thead>
                <tr style={{ background: "linear-gradient(135deg, #eef1f5, #e7ebf1)" }}>
                  <th style={{ padding: "9px 10px", textAlign: "center", borderBottom: "2px solid rgba(0,0,0,0.06)", width: 34 }}>
                    <input type="checkbox"
                      checked={pagedInvoices.length > 0 && pagedInvoices.every(inv => selectedIds.has(inv.stg_id))}
                      onChange={e => {
                        setSelectedIds(prev => {
                          const next = new Set(prev);
                          pagedInvoices.forEach(inv => e.target.checked ? next.add(inv.stg_id) : next.delete(inv.stg_id));
                          return next;
                        });
                      }}
                      style={{ width: 14, height: 14, cursor: "pointer" }} />
                  </th>
                  {["Invoice / Vendor", "Date Invoice", "PO Number", "Amount", "Status", "WHT", ""].map((h, i) => (
                    <th key={h || i} style={{
                      padding: "9px 14px", fontSize: 10.5, fontWeight: 700, color: "#64748b",
                      textAlign: h === "Amount" ? "right" : h === "WHT" || h === "" ? "center" : "left",
                      textTransform: "uppercase", letterSpacing: "0.05em",
                      borderBottom: "2px solid rgba(0,0,0,0.06)", whiteSpace: "nowrap",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pagedInvoices.map((inv, i) => {
                  return (
                    <tr key={inv.stg_id}
                      onClick={() => loadDetail(inv.stg_id)}
                      style={{
                        cursor: "pointer",
                        background: selectedId === inv.stg_id ? "rgba(37,99,235,0.08)" : i % 2 === 0 ? "#f8fafc" : "#f1f5f9",
                        borderLeft: selectedId === inv.stg_id ? "3px solid #2563eb" : "3px solid transparent",
                        borderBottom: "1px solid rgba(0,0,0,0.04)",
                      }}>
                      <td style={{ padding: "10px 10px", textAlign: "center" }} onClick={e => e.stopPropagation()}>
                        <input type="checkbox" checked={selectedIds.has(inv.stg_id)}
                          onChange={() => toggleSelected(inv.stg_id)}
                          style={{ width: 14, height: 14, cursor: "pointer" }} />
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>{inv.invoice_num}</div>
                        <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500 }}>{inv.vendor_name}</div>
                      </td>
                      <td style={{ padding: "10px 14px", fontSize: 12, color: "#475569", whiteSpace: "nowrap" }}>
                        {inv.invoice_date || "—"}
                      </td>
                      <td style={{ padding: "10px 14px", fontSize: 12, color: "#475569", whiteSpace: "nowrap" }}>
                        {inv.po_number || "—"}
                      </td>
                      <td style={{ padding: "10px 14px", fontSize: 12.5, fontWeight: 700, color: "#334155", textAlign: "right", whiteSpace: "nowrap" }}>
                        {inv.invoice_amount ? `Rp ${Number(inv.invoice_amount).toLocaleString("id-ID")}` : "—"}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <StatusPill status={inv.status} />
                      </td>
                      <td style={{ padding: "10px 10px", textAlign: "center" }}>
                        {/* WHT is now set per line item (see Line Items in the
                            detail panel below) — this just reflects the
                            resulting header value once any line is flagged. */}
                        {inv.wht_enabled ? (
                          <span title={`Estimasi: Rp ${Number(inv.wht_amount || 0).toLocaleString("id-ID")} (dihitung Oracle saat validasi)`} style={{
                            fontSize: 11, fontWeight: 700, color: "#d97706",
                            background: "#fef3c7", borderRadius: 6, padding: "2px 8px", whiteSpace: "nowrap",
                          }}>
                            {inv.awt_group_name || "?"}
                          </span>
                        ) : (
                          <span style={{ color: "#cbd5e1", fontSize: 12 }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: "10px 10px", textAlign: "center" }} onClick={e => e.stopPropagation()}>
                        {["NEW", "VALIDATED", "ERROR"].includes(inv.status) && (
                          <button onClick={() => handleDelete(inv.stg_id)} title="Delete"
                            style={{ background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4 }}>
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {totalListPages > 1 && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 16px", borderTop: "1px solid rgba(0,0,0,0.06)", background: "#f1f5f9",
          }}>
            <span style={{ fontSize: 11.5, color: "#64748b", fontWeight: 600 }}>
              {(safeListPage - 1) * LIST_PAGE_SIZE + 1}–{Math.min(safeListPage * LIST_PAGE_SIZE, invoices.length)} of {invoices.length}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <button onClick={() => setListPage(p => Math.max(1, p - 1))} disabled={safeListPage === 1}
                style={{
                  padding: 4, borderRadius: 6, border: "none", cursor: safeListPage === 1 ? "not-allowed" : "pointer",
                  background: "#f1f5f9", color: safeListPage === 1 ? "#cbd5e1" : "#475569",
                  boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
                }}>
                <ChevronLeft size={14} />
              </button>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: "#334155" }}>
                {safeListPage} / {totalListPages}
              </span>
              <button onClick={() => setListPage(p => Math.min(totalListPages, p + 1))} disabled={safeListPage === totalListPages}
                style={{
                  padding: 4, borderRadius: 6, border: "none", cursor: safeListPage === totalListPages ? "not-allowed" : "pointer",
                  background: "#f1f5f9", color: safeListPage === totalListPages ? "#cbd5e1" : "#475569",
                  boxShadow: "0 1px 2px rgba(15,23,42,0.08)",
                }}>
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail Panel — line items, PO matching, and the action/status workflow for the selected invoice */}
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
          Select an invoice from the list above to view details
        </div>
      )}
    </div>
  );
}

function DetailPanel({ detail, onAction, onDelete, onSave, actionLoading }) {
  const [showLines, setShowLines] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [editLines, setEditLines] = useState([]);
  const [matchingLineIdx, setMatchingLineIdx] = useState(null);
  const [poLines, setPoLines] = useState(null);
  const [poLinesLoading, setPoLinesLoading] = useState(false);
  const [poLinesError, setPoLinesError] = useState("");
  const [glDatePreview, setGlDatePreview] = useState(null);
  const [glDatePreviewLoading, setGlDatePreviewLoading] = useState(false);
  const [whtMaster, setWhtMaster] = useState(null); // { awt_group_id, awt_group_name, tax_rate } | null once checked
  const [whtChecking, setWhtChecking] = useState(false);

  const d = detail;
  const s = d.status;
  const canEdit      = ["NEW", "VALIDATED", "ERROR"].includes(s);
  const canDelete    = ["NEW", "VALIDATED", "ERROR"].includes(s);
  const canValidate  = s === "NEW" || s === "ERROR";
  const canInterface = s === "VALIDATED" || s === "PROCESSING" || s === "ERROR";
  const canImport    = s === "INTERFACED" || s === "SUBMITTED" || s === "ERROR";

  // WHT is now a per-LINE decision (not every line in an invoice is
  // necessarily subject to withholding, e.g. services vs. goods) — but
  // Oracle only accepts one WHT GROUP for the whole header (see
  // buildInterfaceHeader), so the line-level flags only decide the
  // TAXBASE the rate applies to (see the recompute effect below), not a
  // per-line Oracle submission. Checks the Supplier WHT Master first
  // (tolerant of "PT" placement — see get_wht_for_vendor's fuzzy fallback);
  // if a match exists, every line defaults to flagged UNLESS it already
  // carries an explicit saved value from a prior edit (ln.wht_flag ?? true
  // preserves an earlier manual uncheck instead of re-checking everything).
  const startEdit = async () => {
    setForm({
      invoice_num: d.invoice_num,
      invoice_date: d.invoice_date || "",
      received_date: d.received_date || "",
      vendor_name: d.vendor_name || "",
      payment_terms: d.payment_terms || "",
      po_number: d.po_number || "",
      so_number: d.so_number || "",
      currency_code: d.currency_code || "IDR",
      subtotal: d.subtotal || 0,
      tax_amount: d.tax_amount || 0,
      invoice_amount: d.invoice_amount || 0,
      tax_serial_number: d.tax_serial_number || "",
      faktur_pajak_date: d.faktur_pajak_date || "",
      wht_enabled: d.wht_enabled || false,
      wht_amount: d.wht_amount || 0,
      awt_group_id: d.awt_group_id ?? null,
      awt_group_name: d.awt_group_name ?? null,
    });

    setWhtChecking(true);
    let master = null;
    try {
      master = await supplierWhtApi.getForVendor(d.vendor_id, d.vendor_name);
    } catch (_) {
      master = null; // no WHT master entry for this supplier — leave every line unflagged
    }
    setWhtMaster(master);
    setWhtChecking(false);

    setEditLines((d.lines || []).map(ln => ({ ...ln, wht_flag: ln.wht_flag ?? !!master })));
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

  // Taxbase/VAT/Total auto-recalculate from the line items — previously
  // stayed stale after adding/editing a line (e.g. a 2nd line), so VAT
  // never reflected the real 11% PPN on the updated Taxbase.
  useEffect(() => {
    if (!editing) return;
    const newSubtotal = editLines.reduce((sum, ln) => sum + (Number(ln.line_amount) || 0), 0);
    const newTax = Math.round(newSubtotal * 0.11);
    setForm(prev => ({ ...prev, subtotal: newSubtotal, tax_amount: newTax, invoice_amount: newSubtotal + newTax }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editLines, editing]);

  // WHT estimate/group recompute from whichever lines are flagged — the
  // taxbase is the sum of ONLY the WHT-flagged lines (e.g. service lines),
  // not the whole invoice, since not every line is necessarily subject to
  // withholding.
  useEffect(() => {
    if (!editing) return;
    const whtBase = editLines.filter(ln => ln.wht_flag).reduce((sum, ln) => sum + (Number(ln.line_amount) || 0), 0);
    if (whtMaster && whtBase > 0) {
      const estimate = whtMaster.tax_rate != null ? Math.round((whtBase * whtMaster.tax_rate) / 100) : 0;
      setForm(prev => ({
        ...prev, wht_enabled: true, wht_amount: estimate,
        awt_group_id: whtMaster.awt_group_id ?? null, awt_group_name: whtMaster.awt_group_name ?? null,
      }));
    } else {
      setForm(prev => ({ ...prev, wht_enabled: false, wht_amount: 0, awt_group_id: null, awt_group_name: null }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editLines, whtMaster, editing]);

  const toggleAllWht = () => {
    const allChecked = editLines.length > 0 && editLines.every(ln => ln.wht_flag);
    setEditLines(prev => prev.map(ln => ({ ...ln, wht_flag: !allChecked })));
  };

  const openMatchPicker = async (idx) => {
    setMatchingLineIdx(idx);
    if (poLines) return; // already fetched for this po_number this session
    setPoLinesLoading(true);
    setPoLinesError("");
    try {
      const res = await apInvoiceApi.getPoLines(form.po_number || d.po_number);
      setPoLines(res.lines || []);
    } catch (e) {
      setPoLinesError(e?.detail || e?.message || "Failed to load PO lines");
    } finally {
      setPoLinesLoading(false);
    }
  };

  const applyMatch = (poLine, receipt) => {
    updateLine(matchingLineIdx, "po_number", d.po_number);
    updateLine(matchingLineIdx, "po_line_number", poLine.line_num);
    updateLine(matchingLineIdx, "receipt_number", receipt ? receipt.receipt_number : null);
    setMatchingLineIdx(null);
  };

  const clearMatch = (idx) => {
    updateLine(idx, "po_line_number", null);
    updateLine(idx, "receipt_number", null);
  };

  // Live preview, re-fetched whenever the relevant Received Date changes —
  // while editing that's the in-progress form value (so correcting the
  // stamp date updates the preview immediately), otherwise the saved one.
  const receivedDateForPreview = editing ? form.received_date : d.received_date;
  useEffect(() => {
    if (!receivedDateForPreview) { setGlDatePreview(null); return; }
    let cancelled = false;
    setGlDatePreviewLoading(true);
    apInvoiceApi.glDatePreview(receivedDateForPreview)
      .then(res => { if (!cancelled) setGlDatePreview(res.gl_date); })
      .catch(() => { if (!cancelled) setGlDatePreview(null); })
      .finally(() => { if (!cancelled) setGlDatePreviewLoading(false); });
    return () => { cancelled = true; };
  }, [receivedDateForPreview]);

  const FIELDS = [
    { key: "invoice_num",    label: "Invoice Number" },
    { key: "invoice_date",   label: "Date Invoice" },
    { key: "received_date",  label: "Received Date (Stamp)" },
    { key: "vendor_name",    label: "Vendor Name" },
    { key: "po_number",      label: "PO Number" },
    { key: "tax_serial_number", label: "No Faktur" },
    { key: "faktur_pajak_date", label: "Tgl Faktur Pajak" },
    { key: "currency_code",  label: "Currency" },
    { key: "subtotal",       label: "Taxbase", type: "number", fmt: true },
    { key: "tax_amount",     label: "VAT", type: "number", fmt: true },
    { key: "invoice_amount", label: "Total", type: "number", fmt: true },
    // TOP is the payment TERM itself (e.g. "30 Days", "COD"), OCR'd off
    // the PDF's Purchase Order page — not a date.
    { key: "payment_terms",  label: "TOP (Term of Payment)" },
    // Terms Date is the actual computed due-date = Received Date + TOP's
    // day count (see compute_terms_date) — server-computed, shown
    // read-only so it's never confused with TOP itself.
    { key: "terms_date",     label: "Terms Date", readOnly: true },
  ];

  return (
    <>
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
            <NeuBtn icon={Pencil} label="Edit" color="#f1f5f9" textColor="#2563eb" onClick={startEdit} small />
          )}
          {canDelete && !editing && (
            <NeuBtn icon={Trash2} label="Delete" color="#f1f5f9" textColor="#dc2626" onClick={() => onDelete(d.stg_id)} loading={actionLoading === "delete"} small />
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

        {/* Info Grid — view or edit mode. 4 columns (not 3) and tighter
            padding/gap so the mostly-narrow fields (dates especially)
            don't waste width, and more of the header is visible without
            scrolling. */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>
          {FIELDS.map((f) => (
            <div key={f.key} style={{
              padding: "7px 10px", borderRadius: 12,
              background: NEU.bg, boxShadow: NEU.shadowOutSm,
            }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
                {f.label}
              </div>
              {editing && !f.readOnly ? (
                <EditInput
                  value={form[f.key]}
                  onChange={v => setForm(p => ({ ...p, [f.key]: v }))}
                  type={f.type || "text"}
                />
              ) : f.key === "received_date" && !d[f.key] ? (
                <div style={{ fontSize: 11.5, fontWeight: 700, color: "#d97706" }}>
                  Not read from stamp — click Edit to fill in
                </div>
              ) : (
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b", wordBreak: "break-all" }}>
                  {f.fmt && d[f.key] ? `Rp ${Number(d[f.key]).toLocaleString("id-ID")}` : (d[f.key] || "—")}
                </div>
              )}
            </div>
          ))}

          {/* GL Date — computed live from Received Date (rolled to the next
              open Payables period if that one's closed), not stored on the
              record — always freshly recomputed at Insert-to-Interface time
              too, so this is a preview, not the authoritative value. */}
          <div style={{ padding: "7px 10px", borderRadius: 12, background: NEU.bg, boxShadow: NEU.shadowOutSm }}>
            <div style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
              GL Date (Preview)
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b" }}>
              {glDatePreviewLoading ? <Loader2 size={13} className="animate-spin" /> : (glDatePreview || "—")}
            </div>
          </div>

          {/* WHT — toggled from the checkbox in the invoice list above (not
              editable here). Oracle only accepts a WHT GROUP NAME on the
              header (never an amount — a manually-inserted AWT-type line
              is rejected outright); its own withholding engine calculates
              and posts the actual deduction at Validation, so what's sent
              is this name, and what's shown is this name too — the
              Rupiah figure below is a rough estimate for reference only. */}
          {d.wht_enabled && (
            <div style={{ padding: "7px 10px", borderRadius: 12, background: NEU.bg, boxShadow: NEU.shadowOutSm }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
                WHT Group (sent to Oracle)
              </div>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>
                {d.awt_group_name || "—"}
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                Estimasi: Rp {Number(d.wht_amount || 0).toLocaleString("id-ID")} (dihitung ulang oleh Oracle)
              </div>
            </div>
          )}
        </div>

        {/* Edit save/cancel bar */}
        {editing && (
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <NeuBtn icon={Save} label="Save" color="#059669" onClick={saveEdit} loading={actionLoading === "save"} />
            <NeuBtn icon={X} label="Cancel" color="#f1f5f9" textColor="#64748b" onClick={cancelEdit} />
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
                    {["#", "Description", "Qty", "Unit Price", "Amount",
                      ...((editing ? form.po_number : d.po_number) ? ["PO Match"] : []),
                      "WHT",
                      ...(editing ? [""] : [])].map(h => (
                      <th key={h} style={{
                        padding: "10px 12px", fontSize: 11, fontWeight: 700,
                        color: "#374151", textAlign: h === "Description" ? "left" : h === "WHT" ? "center" : "right",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        borderBottom: "2px solid rgba(0,0,0,0.06)",
                      }}>
                        {h === "WHT" ? (
                          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: editing && whtMaster ? "pointer" : "default" }}
                            title={whtMaster ? "Centang/hapus semua baris" : "Tidak ada data WHT untuk supplier ini"}>
                            <input type="checkbox"
                              checked={editing ? editLines.length > 0 && editLines.every(ln => ln.wht_flag) : (d.lines || []).length > 0 && (d.lines || []).every(ln => ln.wht_flag)}
                              disabled={!editing || !whtMaster}
                              onChange={toggleAllWht}
                              style={{ width: 12, height: 12, cursor: editing && whtMaster ? "pointer" : "not-allowed" }} />
                            WHT {whtChecking && <Loader2 size={10} className="animate-spin" />}
                          </label>
                        ) : h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(editing ? editLines : d.lines).map((ln, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? "#f8fafc" : "#f1f5f9" }}>
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
                      {(editing ? form.po_number : d.po_number) && (
                        <td style={{ padding: "8px 12px", fontSize: 11, textAlign: "left", width: 150 }}>
                          {ln.po_line_number ? (
                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                              <div style={{ fontWeight: 700, color: "#059669" }}>
                                Line {ln.po_line_number}{ln.receipt_number ? ` · ${ln.receipt_number}` : ""}
                              </div>
                              {editing && (
                                <button onClick={() => clearMatch(i)} style={{
                                  display: "flex", alignItems: "center", gap: 3, background: "#fee2e2",
                                  color: "#dc2626", border: "none", borderRadius: 6, padding: "3px 7px",
                                  fontSize: 10, fontWeight: 700, cursor: "pointer",
                                }}>
                                  <X size={10} /> Unmatch
                                </button>
                              )}
                            </div>
                          ) : editing ? (
                            <button onClick={() => openMatchPicker(i)} style={{
                              display: "flex", alignItems: "center", gap: 4, background: "#fef3c7",
                              color: "#d97706", border: "none", borderRadius: 8, padding: "4px 8px",
                              fontSize: 11, fontWeight: 700, cursor: "pointer",
                            }}>
                              <Link2 size={11} /> Match to PO
                            </button>
                          ) : (
                            <span style={{ color: "#d97706", fontWeight: 700 }}>Not matched</span>
                          )}
                        </td>
                      )}
                      <td style={{ padding: "8px 6px", textAlign: "center", width: 44 }}>
                        {editing ? (
                          <input type="checkbox" checked={!!ln.wht_flag} disabled={!whtMaster}
                            title={whtMaster ? "Kenakan WHT pada baris ini" : "Tidak ada data WHT untuk supplier ini"}
                            onChange={() => updateLine(i, "wht_flag", !ln.wht_flag)}
                            style={{ width: 14, height: 14, cursor: whtMaster ? "pointer" : "not-allowed" }} />
                        ) : ln.wht_flag ? (
                          <CheckCircle size={14} style={{ color: "#059669" }} />
                        ) : (
                          <span style={{ color: "#cbd5e1" }}>—</span>
                        )}
                      </td>
                      {editing && (
                        <td style={{ padding: "8px 6px", textAlign: "center", width: 36 }}>
                          <button onClick={() => removeLine(i)} style={{
                            background: "none", border: "none", cursor: "pointer", color: "#dc2626", padding: 4,
                          }} title="Delete row">
                            <Trash2 size={13} />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: "linear-gradient(135deg, #eef1f5, #e7ebf1)", borderTop: "2px solid rgba(0,0,0,0.08)" }}>
                    <td colSpan={2} style={{ padding: "9px 12px", fontSize: 11.5, fontWeight: 800, color: "#374151" }}>
                      TOTAL
                    </td>
                    <td style={{ padding: "9px 12px", fontSize: 12, fontWeight: 800, color: "#374151", textAlign: "right" }}>
                      {(editing ? editLines : d.lines).reduce((sum, ln) => sum + (Number(ln.qty) || 0), 0).toLocaleString("id-ID")}
                    </td>
                    <td />
                    <td style={{ padding: "9px 12px", fontSize: 12.5, fontWeight: 800, color: "#1e293b", textAlign: "right" }}>
                      {Number((editing ? editLines : d.lines).reduce((sum, ln) => sum + (Number(ln.line_amount) || 0), 0)).toLocaleString("id-ID")}
                    </td>
                    {(editing ? form.po_number : d.po_number) && <td />}
                    <td />
                    {editing && <td />}
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>

        {/* Actions — tombol muncul berdasarkan status */}
        {!editing && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Step indicator */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
              {["NEW", "VALIDATED", "INTERFACED", "SUBMITTED", "IMPORTED"].map((step, i) => {
                const steps = ["NEW", "VALIDATED", "INTERFACED", "SUBMITTED", "IMPORTED"];
                const current = steps.indexOf(s);
                const idx = i;
                const done = idx < current || s === "IMPORTED";
                const active = idx === current;
                return (
                  <div key={step} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{
                      width: 22, height: 22, borderRadius: "50%", fontSize: 10, fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: done ? "#059669" : active ? "#2563eb" : s === "ERROR" ? "#fee2e2" : "#e2e8f0",
                      color: done || active ? "#fff" : s === "ERROR" && idx === current ? "#dc2626" : "#94a3b8",
                      boxShadow: active ? "0 0 0 3px rgba(37,99,235,0.2)" : "none",
                    }}>
                      {done ? <CheckCircle size={12} /> : i + 1}
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 600, color: done ? "#059669" : active ? "#1e293b" : "#94a3b8" }}>
                      {step === "NEW" ? "Upload" : step === "VALIDATED" ? "Validate" : step === "INTERFACED" ? "Interface" : step === "SUBMITTED" ? "Import" : "Done"}
                    </span>
                    {i < 4 && <div style={{ width: 20, height: 2, background: done ? "#059669" : "#e2e8f0", borderRadius: 1 }} />}
                  </div>
                );
              })}
            </div>

            {/* Action buttons */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {canValidate && (
                <NeuBtn icon={CheckCircle}
                  label={s === "ERROR" ? "Re-validate" : "Validate"}
                  color="#059669"
                  onClick={() => onAction("validate", d.stg_id)} loading={actionLoading === "validate"} />
              )}
              {canInterface && (
                <NeuBtn icon={Send}
                  label={s === "PROCESSING" || s === "ERROR" ? "Retry Interface" : "Insert to Interface"}
                  color="#4f46e5"
                  onClick={() => onAction("interface", d.stg_id)} loading={actionLoading === "interface"} />
              )}
              {canImport && (
                <NeuBtn icon={Send}
                  label={s === "ERROR" ? "Retry Import" : s === "SUBMITTED" ? "Re-run APXIIMPT" : "Run APXIIMPT"}
                  color="#be185d"
                  onClick={() => onAction("import", d.stg_id)} loading={actionLoading === "import"} />
              )}
              {(s === "SUBMITTED" || s === "INTERFACED") && (
                <NeuBtn icon={Search}
                  label="Check Status"
                  color="#0891b2"
                  onClick={() => onAction("check", d.stg_id)} loading={actionLoading === "check"} />
              )}
              {(s === "SUBMITTED" || s === "IMPORTED") && (
                <NeuBtn icon={Paperclip}
                  label="Attach PDF"
                  color="#d97706"
                  onClick={() => onAction("attach", d.stg_id)} loading={actionLoading === "attach"} />
              )}
              {s === "IMPORTED" && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", borderRadius: 12, fontSize: 12, fontWeight: 700,
                  background: "#d1fae5", color: "#047857", boxShadow: NEU.shadowOutSm,
                }}>
                  <CheckCircle size={14} /> Invoice imported to EBS successfully
                  {d.ap_invoice_id && <span style={{ marginLeft: 4 }}>(ID: {d.ap_invoice_id})</span>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>

    {matchingLineIdx !== null && (
      <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
        onClick={() => setMatchingLineIdx(null)}>
        <div onClick={e => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, width: 640, maxWidth: "90vw", maxHeight: "80vh", overflow: "auto", boxShadow: NEU.shadowOut }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, background: "#fff" }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: "#1e293b" }}>Match to PO {d.po_number}</div>
            <button onClick={() => setMatchingLineIdx(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b" }}>
              <X size={16} />
            </button>
          </div>

          {/* Status of every invoice line — which are already matched vs
              still pending, so it's clear at a glance without closing the
              popup and checking the table underneath. */}
          <div style={{ padding: "12px 18px", borderBottom: "1px solid #f1f5f9", display: "flex", flexWrap: "wrap", gap: 6 }}>
            {editLines.map((ln, i) => (
              <span key={i} style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: "4px 9px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                background: i === matchingLineIdx ? "#dbeafe" : ln.po_line_number ? "#d1fae5" : "#fef3c7",
                color: i === matchingLineIdx ? "#1d4ed8" : ln.po_line_number ? "#059669" : "#d97706",
                border: i === matchingLineIdx ? "1px solid #93c5fd" : "none",
              }}>
                Line {ln.line_num}: {ln.po_line_number ? `✓ PO Line ${ln.po_line_number}` : "Not matched"}
                {i === matchingLineIdx && " (editing)"}
              </span>
            ))}
          </div>

          <div style={{ padding: 16 }}>
            {poLinesLoading && (
              <div style={{ textAlign: "center", padding: 30 }}><Loader2 size={20} className="animate-spin" /></div>
            )}
            {poLinesError && (
              <div style={{ fontSize: 12, fontWeight: 600, color: "#dc2626", marginBottom: 8 }}>{poLinesError}</div>
            )}
            {!poLinesLoading && !poLinesError && (poLines || []).length === 0 && (
              <div style={{ fontSize: 12, color: "#64748b" }}>No lines found for this PO.</div>
            )}
            {!poLinesLoading && (poLines || []).map(pl => {
              const usedByLine = editLines.find((ln, i) => i !== matchingLineIdx && ln.po_line_number === pl.line_num);
              // receipts are already ordered by transaction_date ascending
              // (see get_po_lines_for_matching) — last item is the most
              // recent, same "Receive Date" Oracle EBS's own Receiving
              // Transactions Summary shows for a line.
              const receipts = pl.receipts || [];
              const lastReceipt = receipts.length ? receipts[receipts.length - 1] : null;
              return (
              <div key={pl.line_num} style={{ borderRadius: 12, border: usedByLine ? "1px solid #fca5a5" : "1px solid #e2e8f0", padding: 12, marginBottom: 10, background: usedByLine ? "#fef2f2" : "transparent" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>
                      Line {pl.line_num} — {pl.item_code || "(no item code)"}
                    </div>
                    <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>{pl.description}</div>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                      Qty {pl.quantity} · Rp {Number(pl.unit_price || 0).toLocaleString("id-ID")}/unit · Received {pl.quantity_received ?? 0}
                      {" · "}{pl.match_option === "R" ? "Match to Receipt" : "Match to PO"}
                      {pl.closed_code ? ` · ${pl.closed_code}` : ""}
                    </div>
                    {/* Receive Date — same field Oracle EBS's own Receiving
                        Transactions Summary shows, surfaced here for every
                        line (not only receipt-matched ones) so it's clear
                        at a glance whether/when goods actually arrived. */}
                    {lastReceipt ? (
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#059669", marginTop: 4 }}>
                        Receive Date: {lastReceipt.transaction_date} (Qty {lastReceipt.quantity})
                        {receipts.length > 1 ? ` · ${receipts.length} penerimaan` : ""}
                      </div>
                    ) : (
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#dc2626", marginTop: 4 }}>
                        Belum ada penerimaan barang (Belum di-Receiving)
                      </div>
                    )}
                    {usedByLine && (
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#dc2626", marginTop: 4 }}>
                        Already matched to invoice Line {usedByLine.line_num}
                      </div>
                    )}
                  </div>
                  {pl.match_option !== "R" && (
                    <NeuBtn small label="Select" color="#2563eb" onClick={() => applyMatch(pl, null)} />
                  )}
                </div>
                {pl.match_option === "R" && receipts.length > 0 && (
                  <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {receipts.map(r => (
                      <button key={r.receipt_number} onClick={() => applyMatch(pl, r)} style={{
                        fontSize: 11, fontWeight: 700, padding: "5px 10px", borderRadius: 8, border: "none",
                        background: "#dbeafe", color: "#1d4ed8", cursor: "pointer",
                      }}>
                        Receipt {r.receipt_number} · {r.transaction_date} · Qty {r.quantity}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </div>
      </div>
    )}
    </>
  );
}
