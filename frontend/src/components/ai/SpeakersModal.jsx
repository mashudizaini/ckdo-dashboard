import { useState, useEffect, useRef } from "react";
import { X, Users, Mic, Loader2, Trash2, UploadCloud, AlertTriangle, CheckCircle2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// Enrolled voices used to identify who's speaking in a meeting recording
// (see backend/app/services/speaker_id_service.py). Each entry here holds
// one embedding vector, computed server-side from an uploaded clip by the
// ai-engine diarization service — this modal never sees the vector itself,
// only name/position/team metadata.
export default function SpeakersModal({ onClose }) {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };
  const url = "/api/v1/ai/meeting-notes/speakers";

  const [speakers, setSpeakers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  const [file, setFile] = useState(null);
  const fileRef = useRef(null);
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [position, setPosition] = useState("");
  const [team, setTeam] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const [msg, setMsg] = useState(null); // { type, text }

  const fetchSpeakers = async () => {
    setLoading(true);
    try {
      const res = await fetch(url, { headers });
      const data = await res.json();
      setSpeakers(Array.isArray(data) ? data : []);
    } catch (_) {} finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSpeakers(); }, []); // eslint-disable-line

  const handleEnroll = async () => {
    if (!file) { setMsg({ type: "error", text: "Pilih file audio dulu" }); return; }
    if (!name.trim()) { setMsg({ type: "error", text: "Nama tidak boleh kosong" }); return; }
    setEnrolling(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", name.trim());
      fd.append("gender", gender);
      fd.append("position", position);
      fd.append("team", team);
      const res = await fetch(url, { method: "POST", headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Gagal mendaftarkan suara");
      setMsg({ type: "success", text: `Suara "${data.name}" berhasil didaftarkan` });
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      setName(""); setGender(""); setPosition(""); setTeam("");
      fetchSpeakers();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setEnrolling(false);
    }
  };

  const handleDelete = async (id, spName) => {
    if (!confirm(`Hapus suara terdaftar "${spName}"?`)) return;
    setDeletingId(id);
    try {
      await fetch(`${url}/${id}`, { method: "DELETE", headers });
      fetchSpeakers();
    } catch (_) {} finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="rounded-xl border border-gray-800 bg-gray-900 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 sticky top-0 bg-gray-900 z-10">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <Users size={16} className="text-blue-400" /> Enrolled Speakers
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          <p className="text-xs text-gray-400 leading-relaxed">
            Daftarkan suara seseorang sekali (klip solo, idealnya 20 detik atau lebih, tanpa suara orang lain) —
            selanjutnya "Identify Speakers" pada rekaman rapat akan otomatis mengenali suara ini. Mendaftar ulang
            nama yang sama akan menimpa sample sebelumnya.
          </p>

          <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 space-y-3">
            <p className="text-xs font-semibold text-gray-300">Daftarkan suara baru</p>
            <div className="grid grid-cols-2 gap-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nama *"
                className="rounded-md border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
              <select value={gender} onChange={(e) => setGender(e.target.value)}
                className="rounded-md border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500 cursor-pointer">
                <option value="">Gender (opsional)</option>
                <option value="man">Pria</option>
                <option value="women">Wanita</option>
              </select>
              <input value={position} onChange={(e) => setPosition(e.target.value)} placeholder="Jabatan (opsional)"
                className="rounded-md border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
              <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Team (opsional)"
                className="rounded-md border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
            </div>
            <input ref={fileRef} type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="w-full text-xs text-gray-400 file:mr-3 file:rounded-md file:border-0 file:bg-gray-700 file:px-3 file:py-1.5 file:text-xs file:text-gray-200 file:cursor-pointer cursor-pointer" />
            <button onClick={handleEnroll} disabled={enrolling}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium py-2 transition-colors">
              {enrolling ? <Loader2 size={14} className="animate-spin" /> : <UploadCloud size={14} />}
              {enrolling ? "Memproses suara…" : "Enroll"}
            </button>
            {msg && (
              <div className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium ${msg.type === "error" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-green-500/10 border border-green-500/30 text-green-400"}`}>
                {msg.type === "error" ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}{msg.text}
              </div>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-300 mb-2">Terdaftar ({speakers.length})</p>
            {loading ? (
              <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
            ) : speakers.length === 0 ? (
              <div className="text-xs text-gray-600 text-center py-6 border border-dashed border-gray-800 rounded-lg">Belum ada suara terdaftar.</div>
            ) : (
              <div className="divide-y divide-gray-800 border border-gray-800 rounded-lg overflow-hidden">
                {speakers.map((s) => (
                  <div key={s.id} className="flex items-center justify-between px-3 py-2.5">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/20">
                        <Mic size={13} className="text-blue-400" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm text-gray-200 truncate">{s.name}</p>
                        <p className="text-[11px] text-gray-500 truncate">{[s.position, s.team].filter(Boolean).join(" · ") || "—"}</p>
                      </div>
                    </div>
                    <button onClick={() => handleDelete(s.id, s.name)} disabled={deletingId === s.id}
                      className="text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50 shrink-0">
                      {deletingId === s.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
