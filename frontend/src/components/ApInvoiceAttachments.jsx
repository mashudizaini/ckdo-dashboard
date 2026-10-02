/**
 * Files attached to an AP invoice in Oracle EBS, listed and downloadable.
 *
 * The files are BLOBs inside the EBS database (FND_LOBS), not files on the EBS
 * server — the backend streams them straight through, so nothing is mirrored
 * into the dashboard and nothing goes stale. See
 * backend/app/services/ebs_attachment_service.py.
 *
 * Fetched only when the paperclip is clicked. There are ~23,000 attachments
 * across AP invoices and a list page shows hundreds of rows at a time; asking
 * EBS for every row's attachments up front would be thousands of pointless
 * queries for the handful anyone actually opens.
 */
import { useState } from "react";
import { Paperclip, Download, Loader2 } from "lucide-react";
import { accountingApi } from "@/api/dashboard";

const fmtSize = (b) => {
  if (b == null) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
};

export default function ApInvoiceAttachments({ invoiceId, invoiceNum }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);     // null = belum pernah dimuat
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || rows !== null) return;
    setBusy(true);
    setError(null);
    try {
      const res = await accountingApi.getApInvoiceAttachments(invoiceId);
      setRows(res.attachments || []);
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal memuat lampiran");
    } finally {
      setBusy(false);
    }
  };

  const download = async (a) => {
    setDownloading(a.attached_document_id);
    setError(null);
    try {
      // The api client's response interceptor already unwraps to the Blob.
      const blob = await accountingApi.downloadApInvoiceAttachment(a.attached_document_id);
      const url = URL.createObjectURL(new Blob([blob], { type: a.file_content_type }));
      const el = document.createElement("a");
      el.href = url;
      el.download = a.file_name || `lampiran-${a.attached_document_id}`;
      el.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal mengunduh");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="relative">
      <button onClick={toggle} title={`Lampiran invoice ${invoiceNum || ""}`.trim()}
        className="p-1 rounded hover:bg-gray-700/50"
        style={{ background: "none", border: "none", cursor: "pointer", color: open ? "#60a5fa" : "#94a3b8" }}>
        <Paperclip size={13} />
      </button>

      {open && (
        <div className="absolute z-20 mt-1 rounded-lg shadow-xl"
          style={{
            right: 0, minWidth: 320, maxWidth: 460, background: "#0f172a",
            border: "1px solid rgba(148,163,184,0.25)", padding: 8,
          }}>
          {busy && (
            <p className="flex items-center gap-2" style={{ fontSize: 11.5, color: "#94a3b8", padding: 4 }}>
              <Loader2 size={12} className="animate-spin" /> memuat…
            </p>
          )}
          {error && <p style={{ fontSize: 11.5, color: "#f87171", padding: 4 }}>{error}</p>}
          {!busy && rows !== null && rows.length === 0 && (
            <p style={{ fontSize: 11.5, color: "#64748b", padding: 4 }}>Invoice ini tidak punya lampiran berkas.</p>
          )}
          {(rows || []).map((a) => (
            <div key={a.attached_document_id} className="flex items-center justify-between gap-3"
              style={{ padding: "5px 4px", fontSize: 11.5 }}>
              <span className="min-w-0">
                <span style={{ color: "#e2e8f0", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {a.file_name}
                </span>
                <span style={{ color: "#64748b" }}>
                  {a.title ? `${a.title} · ` : ""}{fmtSize(a.file_size)} · {a.created_at}
                </span>
              </span>
              <button onClick={() => download(a)} disabled={downloading === a.attached_document_id}
                title="Unduh"
                className="shrink-0 p-1 rounded hover:bg-gray-700/50"
                style={{ background: "none", border: "none", cursor: "pointer", color: "#60a5fa" }}>
                {downloading === a.attached_document_id
                  ? <Loader2 size={13} className="animate-spin" />
                  : <Download size={13} />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
