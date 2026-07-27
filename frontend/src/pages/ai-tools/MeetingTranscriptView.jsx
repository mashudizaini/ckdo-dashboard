import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { FileText, Copy, Loader2, AlertTriangle, Clock } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

export default function MeetingTranscriptView() {
  const { id } = useParams();
  const { token } = useAuthStore();
  const [rec, setRec] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/v1/ai/meeting-notes/recordings/${id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || "Gagal memuat transcript");
        setRec(data);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [id, token]);

  const copyTranscript = () => {
    if (!rec?.transcript) return;
    navigator.clipboard.writeText(rec.transcript);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-5">
          <h1 className="text-xl font-bold text-white flex items-center gap-3">
            <FileText className="text-purple-400" size={22} />
            {rec?.meeting_title || "Transcript"}
          </h1>
          {rec && (
            <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
              {rec.audio_duration_seconds && (
                <span className="flex items-center gap-1"><Clock size={11} />{Math.round(rec.audio_duration_seconds)}s audio</span>
              )}
              {rec.participants && <span>Peserta: {rec.participants}</span>}
            </div>
          )}
        </div>

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {!rec && !error && (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={22} className="animate-spin text-gray-600" />
          </div>
        )}

        {rec && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-200">Transcript</h3>
              <button onClick={copyTranscript} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200">
                <Copy size={12} />{copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
              {rec.transcript || "(transcript kosong)"}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
