import { useState, useEffect } from "react";
import { ShieldCheck, Loader2, Trash2, Plus, Info } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// Matches department_taxonomy.CANONICAL_DEPARTMENTS exactly.
const DEPARTMENTS = ["Administration", "Sales & Marketing", "Strategy & Development", "Plant"];

const EMPTY_FORM = { email: "", full_access: false, departments: [], allowed_modules: [], notes: "" };

export default function EbsChatAccessPanel() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  const [rows, setRows] = useState(null); // null while loading
  const [modules, setModules] = useState([]); // MODULE_TOOL_MAP keys
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingEmail, setDeletingEmail] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const res = await fetch("/api/v1/ai/ebs-chat/scope", { headers });
      if (res.ok) setRows(await res.json());
    } catch (_) {}
  };

  const loadModules = async () => {
    try {
      const res = await fetch("/api/v1/ai/ebs-chat/modules", { headers });
      if (res.ok) setModules(await res.json());
    } catch (_) {}
  };

  useEffect(() => { load(); loadModules(); }, []); // eslint-disable-line

  const toggleDept = (d) => {
    setForm((f) => ({
      ...f,
      departments: f.departments.includes(d) ? f.departments.filter((x) => x !== d) : [...f.departments, d],
    }));
  };

  const toggleModule = (m) => {
    setForm((f) => ({
      ...f,
      allowed_modules: f.allowed_modules.includes(m) ? f.allowed_modules.filter((x) => x !== m) : [...f.allowed_modules, m],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/ai/ebs-chat/scope", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Gagal menyimpan (${res.status})`);
      }
      setForm(EMPTY_FORM);
      await load();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (email) => {
    setDeletingEmail(email);
    try {
      await fetch(`/api/v1/ai/ebs-chat/scope/${encodeURIComponent(email)}`, { method: "DELETE", headers });
      await load();
    } finally {
      setDeletingEmail(null);
    }
  };

  const editRow = (r) => setForm({
    email: r.email, full_access: r.full_access, departments: r.departments,
    allowed_modules: r.allowed_modules || [], notes: r.notes || "",
  });

  if (rows === null) {
    return <div className="p-6 flex justify-center"><Loader2 size={20} className="animate-spin text-gray-600" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-800 bg-gray-900">
        <div className="px-5 py-4 border-b border-gray-800 flex items-start gap-3">
          <ShieldCheck size={18} className="text-blue-400 shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-gray-200">EBS Chat Access</h3>
            <p className="text-xs text-gray-500 mt-1">
              Kontrol siapa yang boleh bertanya data Oracle EBS lewat CoChat, dan departemen apa saja yang
              terlihat untuk mereka. Email di sini harus sama persis dengan email login user tersebut di CoChat.
              Email yang tidak terdaftar akan ditolak (403).
            </p>
          </div>
        </div>

        <div className="px-5 py-3 border-b border-gray-800 bg-blue-500/5 flex items-start gap-2">
          <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />
          <p className="text-xs text-gray-400">
            Dua lapis pembatasan, independen: <b>Departemen</b> membatasi baris data yang terlihat, tapi hanya
            berlaku untuk Employee Directory/Headcount dan Budget vs Actual (data lain tidak punya kolom departemen).
            <b> Modul</b> di bawah membatasi jenis data apa saja yang boleh ditanyakan sama sekali — kosongkan
            keduanya untuk akses tanpa batasan (mis. Direksi/Admin).
          </p>
        </div>

        <form onSubmit={submit} className="p-5 space-y-3 border-b border-gray-800">
          {error && (
            <div className="rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="email" required placeholder="email@ckd-otto.com" value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 outline-none focus:border-blue-500"
            />
            <input
              type="text" placeholder="Catatan (opsional)" value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-200 outline-none focus:border-blue-500"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer w-fit">
            <input
              type="checkbox" checked={form.full_access}
              onChange={(e) => setForm((f) => ({ ...f, full_access: e.target.checked }))}
              className="w-4 h-4 accent-blue-600 cursor-pointer"
            />
            Full access (lihat semua departemen — untuk Direksi/Admin)
          </label>

          {!form.full_access && (
            <div>
              <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-1.5">Departemen (baris data)</p>
              <div className="flex flex-wrap gap-2">
                {DEPARTMENTS.map((d) => (
                  <button key={d} type="button" onClick={() => toggleDept(d)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                      form.departments.includes(d)
                        ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                        : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                    }`}>
                    {d}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-1.5">
              Modul (jenis data yang boleh ditanyakan) — kosong = semua modul
            </p>
            <div className="flex flex-wrap gap-2">
              {modules.map((m) => (
                <button key={m} type="button" onClick={() => toggleModule(m)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    form.allowed_modules.includes(m)
                      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                      : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                  }`}>
                  {m}
                </button>
              ))}
            </div>
          </div>

          <button type="submit" disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 text-xs font-semibold text-white transition-colors">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Simpan
          </button>
        </form>

        <div className="divide-y divide-gray-800">
          {rows.length === 0 && (
            <p className="px-5 py-6 text-xs text-gray-500 text-center">Belum ada email yang dikonfigurasi.</p>
          )}
          {rows.map((r) => (
            <div key={r.email} className="px-5 py-3 flex items-center justify-between gap-4">
              <button onClick={() => editRow(r)} className="min-w-0 text-left">
                <p className="text-sm text-gray-200 truncate">{r.email}</p>
                <p className="text-xs text-gray-500 truncate">
                  {r.full_access ? "Full access" : (r.departments.join(", ") || "Semua departemen")}
                  {" · "}
                  {r.allowed_modules?.length ? `Modul: ${r.allowed_modules.join(", ")}` : "Semua modul"}
                  {r.notes ? ` — ${r.notes}` : ""}
                </p>
              </button>
              <button onClick={() => remove(r.email)} disabled={deletingEmail === r.email}
                className="shrink-0 text-gray-500 hover:text-red-400 disabled:opacity-50 transition-colors">
                {deletingEmail === r.email ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
