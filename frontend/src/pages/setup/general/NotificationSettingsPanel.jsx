import { useState, useEffect } from "react";
import { Loader2, CheckCircle2, AlertTriangle, Megaphone, Plus, Pencil, Trash2, X } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const API = "/api/v1/dashboard/general/notification-settings";

const EMPTY_FORM = { title: "", message: "", is_enabled: true, start_date: "", end_date: "" };

// Setup > General > Announcement & Notification — two independent things
// managed here: (1) on/off switches for the 3 system-derived notification
// types AppLauncher.jsx already fetches (birthday/late attendance/task
// alert), and (2) full CRUD for custom Announcement messages, which is
// the "add a new notification" half — adding a new *system-derived* type
// would need a new backend query, but a custom message doesn't.
export default function NotificationSettingsPanel() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };

  const [types, setTypes] = useState(null);
  const [savingType, setSavingType] = useState(null);

  const [announcements, setAnnouncements] = useState(null);
  const [form, setForm] = useState(null); // null = form closed; object = open (create or edit)
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);

  const loadTypes = async () => {
    try {
      const res = await fetch(`${API}/types`, { headers: hdrs });
      if (res.ok) setTypes(await res.json());
    } catch (_) {}
  };

  const loadAnnouncements = async () => {
    try {
      const res = await fetch(`${API}/announcements`, { headers: hdrs });
      if (res.ok) setAnnouncements(await res.json());
    } catch (_) {}
  };

  useEffect(() => { loadTypes(); loadAnnouncements(); }, []); // eslint-disable-line

  const toggleType = async (key, next) => {
    setSavingType(key);
    try {
      const res = await fetch(`${API}/types/${encodeURIComponent(key)}`, {
        method: "PUT",
        headers: { ...hdrs, "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: next }),
      });
      if (!res.ok) throw new Error("Failed to save");
      setTypes(prev => prev.map(t => t.key === key ? { ...t, is_enabled: next } : t));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSavingType(null);
    }
  };

  const openCreate = () => { setForm({ ...EMPTY_FORM }); setEditingId(null); setError(null); };
  const openEdit = (a) => {
    setForm({
      title: a.title, message: a.message, is_enabled: a.is_enabled,
      start_date: a.start_date || "", end_date: a.end_date || "",
    });
    setEditingId(a.id);
    setError(null);
  };
  const closeForm = () => { setForm(null); setEditingId(null); };

  const submitForm = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.message.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const body = JSON.stringify({
        title: form.title.trim(),
        message: form.message.trim(),
        is_enabled: form.is_enabled,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      });
      const url = editingId ? `${API}/announcements/${editingId}` : `${API}/announcements`;
      const res = await fetch(url, {
        method: editingId ? "PUT" : "POST",
        headers: { ...hdrs, "Content-Type": "application/json" },
        body,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to save");
      closeForm();
      await loadAnnouncements();
    } catch (e2) {
      setError(e2.message || String(e2));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!confirm("Hapus pengumuman ini?")) return;
    setDeletingId(id);
    try {
      const res = await fetch(`${API}/announcements/${id}`, { method: "DELETE", headers: hdrs });
      if (!res.ok) throw new Error("Failed to delete");
      await loadAnnouncements();
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setDeletingId(null);
    }
  };

  const toggleAnnouncementEnabled = async (a) => {
    try {
      const res = await fetch(`${API}/announcements/${a.id}`, {
        method: "PUT",
        headers: { ...hdrs, "Content-Type": "application/json" },
        body: JSON.stringify({
          title: a.title, message: a.message, is_enabled: !a.is_enabled,
          start_date: a.start_date, end_date: a.end_date,
        }),
      });
      if (!res.ok) throw new Error("Failed to save");
      setAnnouncements(prev => prev.map(x => x.id === a.id ? { ...x, is_enabled: !a.is_enabled } : x));
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {error && (
        <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2 bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {/* ── Section 1: system-derived notification types ── */}
      <div>
        <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-1.5">Jenis Notifikasi Otomatis</p>
        <p className="text-xs text-gray-500 mb-3 leading-relaxed">
          Aktif/nonaktifkan jenis notifikasi yang tampil di panel Announcement & Notification (Application Center).
        </p>
        {types === null ? (
          <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
        ) : (
          <div className="rounded-xl border border-gray-800 bg-gray-900 divide-y divide-gray-800">
            {types.map(t => {
              const isOn = t.is_enabled;
              const isSaving = savingType === t.key;
              return (
                <label key={t.key} className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-800/40 transition-colors">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-base shrink-0">{t.icon}</span>
                    <div className="min-w-0">
                      <p className="text-sm text-gray-200">{t.label}</p>
                      <p className="text-[11px] text-gray-600 truncate">{t.description}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => toggleType(t.key, !isOn)}
                    disabled={isSaving}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 shrink-0 ${
                      isOn ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-gray-800 text-gray-500 border border-gray-700"
                    }`}
                  >
                    {isSaving ? <Loader2 size={12} className="animate-spin" /> : isOn ? <CheckCircle2 size={12} /> : null}
                    {isOn ? "Tampil" : "Disembunyikan"}
                  </button>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Section 2: custom Announcements ── */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider">Pengumuman (Announcement)</p>
          {!form && (
            <button onClick={openCreate}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-1.5 transition-colors">
              <Plus size={13} /> Tambah Pengumuman
            </button>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3 leading-relaxed">
          Pesan bebas yang ikut tampil di panel Announcement & Notification — dengan jendela tanggal opsional (kosong = tampil terus).
        </p>

        {form && (
          <form onSubmit={submitForm} className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-3 mb-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-gray-200">{editingId ? "Edit Pengumuman" : "Pengumuman Baru"}</p>
              <button type="button" onClick={closeForm} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
            </div>
            <input
              required placeholder="Judul" value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
            />
            <textarea
              required placeholder="Pesan" rows={3} value={form.message}
              onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 resize-none"
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Mulai (opsional)</p>
                <input type="date" value={form.start_date}
                  onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </div>
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Sampai (opsional)</p>
                <input type="date" value={form.end_date}
                  onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer w-fit">
              <input type="checkbox" checked={form.is_enabled}
                onChange={e => setForm(f => ({ ...f, is_enabled: e.target.checked }))}
                className="w-4 h-4 accent-blue-600 cursor-pointer" />
              Tampilkan sekarang
            </label>
            <button type="submit" disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 transition-colors">
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {editingId ? "Simpan Perubahan" : "Tambah"}
            </button>
          </form>
        )}

        {announcements === null ? (
          <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-gray-600" /></div>
        ) : announcements.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-6 py-10 text-center">
            <Megaphone size={22} className="text-gray-700 mx-auto mb-2" />
            <p className="text-xs text-gray-600">Belum ada pengumuman.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-800 bg-gray-900 divide-y divide-gray-800">
            {announcements.map(a => (
              <div key={a.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-gray-200 truncate">{a.title}</p>
                    {(a.start_date || a.end_date) && (
                      <span className="text-[10px] text-gray-600 shrink-0">
                        {a.start_date || "…"} – {a.end_date || "…"}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-gray-500 line-clamp-2">{a.message}</p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => toggleAnnouncementEnabled(a)}
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold border transition-colors ${
                      a.is_enabled ? "bg-green-500/15 text-green-400 border-green-500/30" : "bg-gray-800 text-gray-500 border-gray-700"
                    }`}>
                    {a.is_enabled ? "Tampil" : "Disembunyikan"}
                  </button>
                  <button onClick={() => openEdit(a)} className="p-1.5 rounded-lg text-gray-500 hover:text-blue-400 hover:bg-gray-800 transition-colors">
                    <Pencil size={13} />
                  </button>
                  <button onClick={() => remove(a.id)} disabled={deletingId === a.id}
                    className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors disabled:opacity-50">
                    {deletingId === a.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
