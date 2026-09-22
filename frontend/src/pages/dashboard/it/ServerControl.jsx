/**
 * Server Control
 * ─────────────────────────────────────────
 * Centralized inventory of the company's own infrastructure (hypervisors,
 * DB/App servers, network gear, SaaS admin consoles, etc.) and their login
 * credentials — replaces the informal Excel sheet IT was keeping for this.
 * Credentials are encrypted at rest (see crypto.py) and never shown by
 * default: an explicit "reveal" click decrypts on demand, is logged (see
 * the Access Log panel), and the plaintext auto-re-masks after 20s so
 * nothing stays visible on screen indefinitely.
 *
 * Same self-contained-tab convention as VpnAccessMonitoring.jsx/
 * EbsBackupRecovery.jsx — local Panel/Btn/Field helpers, not shared.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Server, Plus, Trash2, Pencil, Eye, EyeOff, Copy, Check, Search,
  Loader2, X, KeyRound, History, ExternalLink, ShieldAlert, ChevronDown, ChevronRight,
} from "lucide-react";
import { serverRegistryApi } from "@/api/dashboard";

/* ─── Shared UI (local copy, see file header) ──────────────────────── */

function Panel({ title, subtitle, action, children }) {
  return (
    <div style={{ background: "#ffffff", borderRadius: 16, boxShadow: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)", marginBottom: 16 }}>
      <div className="flex items-center justify-between px-5 py-3.5 flex-wrap gap-2" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{subtitle}</p>}
        </div>
        <div className="flex gap-2">{action}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Btn({ onClick, children, variant = "default", disabled, icon: Icon, size = "md", type = "button" }) {
  const variants = {
    default: { bg: "#f1f5f9", color: "#334155" },
    primary: { bg: "#2563eb", color: "#ffffff" },
    danger:  { bg: "#dc2626", color: "#ffffff" },
    ghost:   { bg: "transparent", color: "#2563eb" },
  };
  const v = variants[variant] || variants.default;
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className="flex items-center gap-1.5 rounded-lg transition-all"
      style={{
        background: v.bg, color: v.color, fontWeight: 700,
        padding: size === "sm" ? "5px 10px" : "7px 14px",
        fontSize: size === "sm" ? 11 : 12,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
        border: "none",
      }}>
      {Icon && <Icon size={size === "sm" ? 12 : 13} />}{children}
    </button>
  );
}

const inputStyle = {
  width: "100%", padding: "7px 10px", borderRadius: 8, fontSize: 12.5,
  border: "1px solid rgba(15,23,42,0.14)", background: "#ffffff", color: "#0f172a",
};

function Field({ label, children }) {
  return (
    <div>
      <label style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.04em", display: "block", marginBottom: 4 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function Modal({ title, onClose, children, footer }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}
      onClick={onClose}>
      <div style={{ background: "#fff", borderRadius: 16, width: "100%", maxWidth: 440, maxHeight: "90vh", overflow: "auto", boxShadow: "0 20px 40px rgba(0,0,0,0.25)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3.5" style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{title}</h3>
          <button onClick={onClose} style={{ color: "#94a3b8", background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">{children}</div>
        {footer && <div className="px-5 py-3.5 flex justify-end gap-2" style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>{footer}</div>}
      </div>
    </div>
  );
}

/* ─── Main ──────────────────────────────────────────────────────────── */

const EMPTY_SERVER = { name: "", category: "", address: "", notes: "", sequence: 0 };
const EMPTY_CRED = { label: "", username: "", password: "", notes: "" };
const REVEAL_TIMEOUT_MS = 20_000;

export default function ServerControl() {
  const [servers, setServers] = useState(null);
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState({}); // category -> bool

  const [serverModal, setServerModal] = useState(null); // null | {mode:"add"} | {mode:"edit", server}
  const [credModal, setCredModal] = useState(null);      // null | {serverId, mode:"add"} | {mode:"edit", credential}
  const [saving, setSaving] = useState(false);

  const [revealed, setRevealed] = useState({}); // credentialId -> {username, password}
  const [revealing, setRevealing] = useState(null);
  const [copied, setCopied] = useState(null); // credentialId, briefly
  const timers = useRef({});

  const [showLog, setShowLog] = useState(false);
  const [log, setLog] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [srv, cats] = await Promise.all([serverRegistryApi.getServers(), serverRegistryApi.getCategories()]);
      setServers(srv);
      setCategories(cats);
    } catch (e) {
      setError(e?.detail || e?.message || String(e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { Object.values(timers.current).forEach(clearTimeout); }, []);

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = (servers || []).filter((s) => {
      if (!q) return true;
      return s.name.toLowerCase().includes(q) || (s.address || "").toLowerCase().includes(q) ||
        s.credentials.some((c) => (c.username || "").toLowerCase().includes(q) || (c.label || "").toLowerCase().includes(q));
    });
    const g = {};
    for (const s of filtered) (g[s.category] ||= []).push(s);
    return g;
  }, [servers, search]);

  const reveal = async (credentialId) => {
    setRevealing(credentialId);
    try {
      const res = await serverRegistryApi.revealCredential(credentialId);
      setRevealed((prev) => ({ ...prev, [credentialId]: res }));
      clearTimeout(timers.current[credentialId]);
      timers.current[credentialId] = setTimeout(() => {
        setRevealed((prev) => { const next = { ...prev }; delete next[credentialId]; return next; });
      }, REVEAL_TIMEOUT_MS);
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal membuka password");
    } finally {
      setRevealing(null);
    }
  };

  const hide = (credentialId) => {
    clearTimeout(timers.current[credentialId]);
    setRevealed((prev) => { const next = { ...prev }; delete next[credentialId]; return next; });
  };

  const copyPassword = (credentialId, password) => {
    navigator.clipboard?.writeText(password).then(() => {
      setCopied(credentialId);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  const saveServer = async (form) => {
    setSaving(true);
    setError(null);
    try {
      if (serverModal.mode === "edit") await serverRegistryApi.updateServer(serverModal.server.id, form);
      else await serverRegistryApi.createServer(form);
      setServerModal(null);
      await load();
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal menyimpan server");
    } finally {
      setSaving(false);
    }
  };

  const removeServer = async (server) => {
    if (!confirm(`Hapus "${server.name}" beserta semua credential-nya?`)) return;
    try {
      await serverRegistryApi.deleteServer(server.id);
      await load();
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal menghapus server");
    }
  };

  const saveCredential = async (form) => {
    setSaving(true);
    setError(null);
    try {
      if (credModal.mode === "edit") await serverRegistryApi.updateCredential(credModal.credential.id, form);
      else await serverRegistryApi.addCredential(credModal.serverId, form);
      setCredModal(null);
      await load();
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal menyimpan credential");
    } finally {
      setSaving(false);
    }
  };

  const removeCredential = async (credential) => {
    if (!confirm("Hapus credential ini?")) return;
    try {
      await serverRegistryApi.deleteCredential(credential.id);
      hide(credential.id);
      await load();
    } catch (e) {
      setError(e?.detail || e?.message || "Gagal menghapus credential");
    }
  };

  const openLog = async () => {
    setShowLog(true);
    try { setLog(await serverRegistryApi.getAccessLog()); } catch (_) { setLog([]); }
  };

  if (servers === null) {
    return <div className="flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-400" /></div>;
  }

  return (
    <div>
      <Panel
        title="Server Control"
        subtitle="Inventaris server & network device perusahaan — password terenkripsi, setiap akses dicatat"
        action={
          <>
            <Btn icon={History} onClick={openLog}>Access Log</Btn>
            <Btn icon={Plus} variant="primary" onClick={() => setServerModal({ mode: "add" })}>Tambah Server</Btn>
          </>
        }
      >
        <div className="relative mb-4" style={{ maxWidth: 360 }}>
          <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cari nama server, IP, username..."
            style={{ ...inputStyle, paddingLeft: 32 }} />
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 mb-4" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}>
            <ShieldAlert size={14} className="text-red-500" />
            <span style={{ fontSize: 12, color: "#dc2626" }}>{error}</span>
          </div>
        )}

        {Object.keys(grouped).length === 0 ? (
          <div className="text-center py-10" style={{ color: "#94a3b8", fontSize: 12.5 }}>
            {search ? "Tidak ada hasil." : "Belum ada server terdaftar."}
          </div>
        ) : (
          Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b)).map(([category, list]) => (
            <div key={category} className="mb-3">
              <button onClick={() => setCollapsed((p) => ({ ...p, [category]: !p[category] }))}
                className="flex items-center gap-1.5 w-full text-left py-2" style={{ border: "none", background: "none", cursor: "pointer" }}>
                {collapsed[category] ? <ChevronRight size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                <Server size={13} className="text-blue-500" />
                <span style={{ fontSize: 12.5, fontWeight: 800, color: "#334155", textTransform: "uppercase", letterSpacing: "0.03em" }}>{category}</span>
                <span style={{ fontSize: 11, color: "#94a3b8" }}>({list.length})</span>
              </button>

              {!collapsed[category] && (
                <div className="space-y-2 pl-1">
                  {list.map((s) => (
                    <ServerRow
                      key={s.id} server={s}
                      revealed={revealed} revealing={revealing} copied={copied}
                      onReveal={reveal} onHide={hide} onCopy={copyPassword}
                      onEditServer={() => setServerModal({ mode: "edit", server: s })}
                      onDeleteServer={() => removeServer(s)}
                      onAddCredential={() => setCredModal({ mode: "add", serverId: s.id })}
                      onEditCredential={(c) => setCredModal({ mode: "edit", credential: c })}
                      onDeleteCredential={removeCredential}
                    />
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </Panel>

      {serverModal && (
        <ServerModal mode={serverModal.mode} initial={serverModal.server || EMPTY_SERVER} categories={categories}
          saving={saving} onSave={saveServer} onClose={() => setServerModal(null)} />
      )}

      {credModal && (
        <CredentialModal mode={credModal.mode} initial={credModal.credential || EMPTY_CRED}
          saving={saving} onSave={saveCredential} onClose={() => setCredModal(null)} />
      )}

      {showLog && <AccessLogModal log={log} onClose={() => setShowLog(false)} />}
    </div>
  );
}

/* ─── Server row + credential list ─────────────────────────────────── */

function looksLikeUrl(v) {
  return /^https?:\/\//i.test(v || "");
}

function ServerRow({
  server, revealed, revealing, copied, onReveal, onHide, onCopy,
  onEditServer, onDeleteServer, onAddCredential, onEditCredential, onDeleteCredential,
}) {
  return (
    <div style={{ borderRadius: 12, border: "1px solid rgba(15,23,42,0.08)", overflow: "hidden" }}>
      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 flex-wrap" style={{ background: "#f8fafc" }}>
        <div className="min-w-0">
          <p style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>{server.name}</p>
          {server.address && (
            looksLikeUrl(server.address) ? (
              <a href={server.address} target="_blank" rel="noreferrer" className="flex items-center gap-1"
                style={{ fontSize: 11.5, color: "#2563eb", textDecoration: "none" }}>
                {server.address} <ExternalLink size={10} />
              </a>
            ) : (
              <span style={{ fontSize: 11.5, color: "#64748b", fontFamily: "monospace" }}>{server.address}</span>
            )
          )}
          {server.notes && <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{server.notes}</p>}
        </div>
        <div className="flex gap-1.5 shrink-0">
          <Btn size="sm" icon={KeyRound} onClick={onAddCredential}>Credential</Btn>
          <Btn size="sm" icon={Pencil} onClick={onEditServer} />
          <Btn size="sm" icon={Trash2} variant="danger" onClick={onDeleteServer} />
        </div>
      </div>

      {server.credentials.length > 0 && (
        <div className="divide-y" style={{ borderTop: "1px solid rgba(15,23,42,0.06)" }}>
          {server.credentials.map((c) => {
            const isRevealed = revealed[c.id];
            const isRevealing = revealing === c.id;
            return (
              <div key={c.id} className="flex items-center gap-3 px-3.5 py-2 flex-wrap" style={{ borderColor: "rgba(15,23,42,0.06)" }}>
                <div style={{ minWidth: 130, fontSize: 11.5, color: "#475569" }}>
                  {c.label && <span style={{ fontWeight: 700 }}>{c.label}: </span>}
                  <span style={{ fontFamily: "monospace" }}>{c.username || "—"}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                  <span style={{
                    fontFamily: "monospace", fontSize: 11.5, background: "#f1f5f9", borderRadius: 6,
                    padding: "3px 8px", color: isRevealed ? "#0f172a" : "#94a3b8", flex: 1, minWidth: 0,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {isRevealed ? isRevealed.password : "••••••••••••"}
                  </span>
                  {isRevealed ? (
                    <>
                      <Btn size="sm" icon={copied === c.id ? Check : Copy} onClick={() => onCopy(c.id, isRevealed.password)} />
                      <Btn size="sm" icon={EyeOff} onClick={() => onHide(c.id)} />
                    </>
                  ) : (
                    <Btn size="sm" icon={isRevealing ? Loader2 : Eye} disabled={isRevealing} onClick={() => onReveal(c.id)} />
                  )}
                  <Btn size="sm" icon={Pencil} onClick={() => onEditCredential(c)} />
                  <Btn size="sm" icon={Trash2} variant="danger" onClick={() => onDeleteCredential(c)} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ─── Modals ────────────────────────────────────────────────────────── */

function ServerModal({ mode, initial, categories, saving, onSave, onClose }) {
  const [form, setForm] = useState({
    name: initial.name || "", category: initial.category || "", address: initial.address || "",
    notes: initial.notes || "", sequence: initial.sequence || 0,
  });
  return (
    <Modal title={mode === "edit" ? "Edit Server" : "Tambah Server"} onClose={onClose}
      footer={<>
        <Btn onClick={onClose}>Batal</Btn>
        <Btn variant="primary" disabled={saving || !form.name.trim()} icon={saving ? Loader2 : undefined}
          onClick={() => onSave(form)}>Simpan</Btn>
      </>}>
      <Field label="Nama Server *">
        <input style={inputStyle} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} autoFocus />
      </Field>
      <Field label="Kategori">
        <input style={inputStyle} list="server-categories" value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} placeholder="Hypervisor, Database, Network, ..." />
        <datalist id="server-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
      </Field>
      <Field label="Address / IP / URL">
        <input style={inputStyle} value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
      </Field>
      <Field label="Catatan">
        <textarea style={{ ...inputStyle, minHeight: 60, resize: "vertical" }} value={form.notes}
          onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
      </Field>
    </Modal>
  );
}

function CredentialModal({ mode, initial, saving, onSave, onClose }) {
  const [form, setForm] = useState({
    label: initial.label || "", username: initial.username || "", password: "", notes: initial.notes || "",
  });
  const [showPw, setShowPw] = useState(false);
  return (
    <Modal title={mode === "edit" ? "Edit Credential" : "Tambah Credential"} onClose={onClose}
      footer={<>
        <Btn onClick={onClose}>Batal</Btn>
        <Btn variant="primary" disabled={saving || (mode === "add" && !form.password)} icon={saving ? Loader2 : undefined}
          onClick={() => onSave(form)}>Simpan</Btn>
      </>}>
      <Field label="Label (opsional)">
        <input style={inputStyle} value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
          placeholder="Local Admin, Domain Admin, ..." autoFocus />
      </Field>
      <Field label="Username">
        <input style={inputStyle} value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} />
      </Field>
      <Field label={mode === "edit" ? "Password (kosongkan jika tidak diubah)" : "Password *"}>
        <div className="relative">
          <input type={showPw ? "text" : "password"} style={{ ...inputStyle, paddingRight: 32 }} value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
          <button type="button" onClick={() => setShowPw((v) => !v)}
            style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}>
            {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </Field>
      <Field label="Catatan">
        <textarea style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} value={form.notes}
          onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
      </Field>
    </Modal>
  );
}

function AccessLogModal({ log, onClose }) {
  return (
    <Modal title="Access Log — riwayat reveal password" onClose={onClose}>
      {log === null ? (
        <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-gray-400" /></div>
      ) : log.length === 0 ? (
        <p style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "20px 0" }}>Belum ada aktivitas.</p>
      ) : (
        <div className="space-y-1.5" style={{ maxHeight: 400, overflow: "auto" }}>
          {log.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 py-1.5" style={{ borderBottom: "1px solid rgba(15,23,42,0.05)", fontSize: 11.5 }}>
              <div className="min-w-0">
                <span style={{ fontWeight: 700, color: "#0f172a" }}>{r.accessed_by}</span>
                <span style={{ color: "#64748b" }}> membuka </span>
                <span style={{ fontWeight: 600, color: "#334155" }}>{r.server_name || "?"}{r.credential_label ? ` (${r.credential_label})` : ""}</span>
              </div>
              <span style={{ color: "#94a3b8", whiteSpace: "nowrap" }}>{new Date(r.accessed_at).toLocaleString("id-ID")}</span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
