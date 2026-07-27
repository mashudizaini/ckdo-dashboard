import { useState, useRef, useEffect } from "react";
import {
  FileText, Mic, Square, Upload, Sparkles, Clock, Users, Copy, Download, Loader2,
  AlertTriangle, CheckCircle2, Plus, Trash2, ExternalLink, Save as SaveIcon,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";

function fmtElapsed(sec) {
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function fmtBytes(n) {
  if (!n) return "";
  const mb = n / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`;
}

function fmtDate(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function MeetingNotes() {
  const [tab, setTab] = useState("new");
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  // Meeting info
  const [title, setTitle] = useState("");
  const [participants, setParticipants] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [venue, setVenue] = useState("");
  const [agenda, setAgenda] = useState("");

  const [file, setFile] = useState(null);
  const fileRef = useRef(null);

  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState(null);
  const [transcript, setTranscript] = useState(null); // { id, text, segments, language, audio_duration_seconds, processing_time_seconds }

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [mom, setMom] = useState(null); // { departments: [...] }
  const [momProvider, setMomProvider] = useState("onprem");
  const [savingMom, setSavingMom] = useState(false);
  const [saveMomMsg, setSaveMomMsg] = useState(null);
  const [downloadingDocx, setDownloadingDocx] = useState(false);

  const [copied, setCopied] = useState(false);

  // Live recording
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [recordError, setRecordError] = useState(null);
  const [recordedBlobInfo, setRecordedBlobInfo] = useState(null); // { blob, filename }
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);

  // History
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (tab === "history") fetchHistory();
  }, [tab]); // eslint-disable-line

  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await fetch("/api/v1/ai/meeting-notes/recordings", { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Gagal memuat riwayat");
      setHistory(data);
    } catch (e) {
      setHistoryError(e.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const resetResults = () => {
    setTranscript(null); setTranscribeError(null);
    setMom(null); setGenerateError(null); setSaveMomMsg(null);
  };

  const handlePickFile = (f) => {
    if (!f) return;
    if (f.size > 100 * 1024 * 1024) {
      setTranscribeError("File terlalu besar — maksimal 100MB.");
      return;
    }
    setFile(f);
    setRecordedBlobInfo(null);
    resetResults();
  };

  const pickMimeType = () => {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    return candidates.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
  };

  const handleStartRecording = async () => {
    setRecordError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      const isInsecureHttp = window.location.protocol === "http:" && !["localhost", "127.0.0.1"].includes(window.location.hostname);
      setRecordError(
        isInsecureHttp
          ? { message: "Halaman ini diakses tanpa HTTPS — microphone butuh koneksi aman.", needsHttps: true }
          : { message: "Browser ini tidak mendukung perekaman microphone." }
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const ext = (recorder.mimeType || "audio/webm").includes("mp4") ? "m4a" : "webm";
        const filename = `recording-${Date.now()}.${ext}`;
        const recordedFile = new File([blob], filename, { type: blob.type });
        setFile(recordedFile);
        setRecordedBlobInfo({ blob, filename });
        resetResults();
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    } catch (e) {
      if (e.name === "NotAllowedError") {
        setRecordError({ message: "Akses microphone ditolak. Izinkan akses microphone di pengaturan browser lalu coba lagi." });
      } else {
        setRecordError({ message: `Gagal mengakses microphone: ${e.message || e.name}` });
      }
    }
  };

  const handleStopRecording = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const handleSaveRecordingLocally = () => {
    if (!recordedBlobInfo) return;
    const url = URL.createObjectURL(recordedBlobInfo.blob);
    const a = document.createElement("a");
    a.href = url; a.download = recordedBlobInfo.filename; a.click();
    URL.revokeObjectURL(url);
  };

  const handleTranscribe = async () => {
    if (!file) return;
    setTranscribing(true); setTranscribeError(null); setTranscript(null); setMom(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source", recordedBlobInfo ? "recorded" : "uploaded");
      fd.append("meeting_title", title);
      fd.append("participants", participants);
      const res = await fetch("/api/v1/ai/meeting-notes/transcribe", { method: "POST", headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Transcription failed");
      setTranscript(data);
      fetchHistory();
    } catch (e) {
      setTranscribeError(e.message || String(e));
    } finally {
      setTranscribing(false);
    }
  };

  const handleGenerateMom = async () => {
    if (!transcript?.id) return;
    setGenerating(true); setGenerateError(null); setMom(null); setSaveMomMsg(null);
    try {
      const res = await fetch(`/api/v1/ai/meeting-notes/recordings/${transcript.id}/generate-mom`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ provider: momProvider, date, time, venue, agenda }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "MOM generation failed");
      setMom(data.mom_json);
    } catch (e) {
      setGenerateError(e.message || String(e));
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveMom = async () => {
    if (!transcript?.id || !mom) return;
    setSavingMom(true); setSaveMomMsg(null);
    try {
      const res = await fetch(`/api/v1/ai/meeting-notes/recordings/${transcript.id}/mom`, {
        method: "PUT",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ mom_json: mom, mom_meta: { date, time, venue, agenda }, meeting_title: title, participants }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Gagal menyimpan perubahan");
      setSaveMomMsg({ type: "success", text: "Perubahan disimpan" });
    } catch (e) {
      setSaveMomMsg({ type: "error", text: e.message });
    } finally {
      setSavingMom(false);
    }
  };

  const handleDownloadDocx = async (recordingId) => {
    setDownloadingDocx(true);
    try {
      const res = await fetch(`/api/v1/ai/meeting-notes/recordings/${recordingId}/mom/docx`, { headers });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Gagal mengunduh MOM");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${(title || "MOM").replace(/\s+/g, "_")}.docx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setSaveMomMsg({ type: "error", text: e.message });
    } finally {
      setDownloadingDocx(false);
    }
  };

  const handleDownloadAudio = (recordingId) => {
    window.open(`/api/v1/ai/meeting-notes/recordings/${recordingId}/audio`, "_blank");
  };

  const handleDeleteRecording = async (recordingId) => {
    if (!confirm("Hapus recording ini beserta transcript & MOM-nya?")) return;
    try {
      await fetch(`/api/v1/ai/meeting-notes/recordings/${recordingId}`, { method: "DELETE", headers });
      fetchHistory();
    } catch (_) {}
  };

  const copyTranscript = () => {
    if (!transcript?.text) return;
    navigator.clipboard.writeText(transcript.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ── MOM editing helpers (immutable updates) ──
  const updateMom = (updater) => setMom((prev) => updater(structuredClone(prev)));

  const updateDeptName = (di, value) => updateMom((m) => { m.departments[di].name = value; return m; });
  const removeDept = (di) => updateMom((m) => { m.departments.splice(di, 1); return m; });
  const addDept = () => updateMom((m) => { m.departments.push({ name: "Departemen Baru", topics: [] }); return m; });

  const updateTopicTitle = (di, ti, value) => updateMom((m) => { m.departments[di].topics[ti].title = value; return m; });
  const removeTopic = (di, ti) => updateMom((m) => { m.departments[di].topics.splice(ti, 1); return m; });
  const addTopic = (di) => updateMom((m) => {
    m.departments[di].topics.push({ title: "Topik Baru", discussion_points: [], action_plans: [] });
    return m;
  });

  const updatePoint = (di, ti, field, pi, value) => updateMom((m) => { m.departments[di].topics[ti][field][pi] = value; return m; });
  const removePoint = (di, ti, field, pi) => updateMom((m) => { m.departments[di].topics[ti][field].splice(pi, 1); return m; });
  const addPoint = (di, ti, field) => updateMom((m) => { m.departments[di].topics[ti][field].push(""); return m; });

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FileText className="text-purple-400" size={26} />
          Meeting Notes
        </h1>
        <p className="text-gray-500 text-sm mt-1">Record or upload → GPU transcription → AI-generated, editable Minutes of Meeting</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-900 border border-gray-800 p-1 w-fit">
        {[
          { id: "new",     label: "New Recording" },
          { id: "history", label: "History" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
              tab === t.id ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: New Recording */}
      {tab === "new" && (
        <div className="space-y-4">
          {/* Info form */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h3 className="text-sm font-semibold text-gray-200 mb-4">Meeting Information</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Meeting Title</label>
                <input type="text" value={title} onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. IT Coordination Meeting"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Participants</label>
                <input type="text" value={participants} onChange={(e) => setParticipants(e.target.value)}
                  placeholder="Participant names, separated by comma"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Date</label>
                <input type="text" value={date} onChange={(e) => setDate(e.target.value)}
                  placeholder="e.g. 27 Juli 2026"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Time</label>
                <input type="text" value={time} onChange={(e) => setTime(e.target.value)}
                  placeholder="e.g. 10:00 - 11:00"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Venue</label>
                <input type="text" value={venue} onChange={(e) => setVenue(e.target.value)}
                  placeholder="e.g. Meeting Room A"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Agenda</label>
                <input type="text" value={agenda} onChange={(e) => setAgenda(e.target.value)}
                  placeholder="e.g. Weekly Coordination"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
            </div>
          </div>

          {/* Record / Upload */}
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 text-center">
              <div className={`flex h-16 w-16 items-center justify-center rounded-full mx-auto mb-3 border ${
                recording ? "bg-red-500/20 border-red-500/50 animate-pulse" : "bg-red-500/10 border-red-500/30"
              }`}>
                <Mic size={28} className="text-red-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Live Recording</p>
              <p className="text-xs text-gray-600 mb-4">
                {recording ? (
                  <span className="flex items-center justify-center gap-1.5 text-red-400 font-medium">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" /> Recording… {fmtElapsed(recordingSeconds)}
                  </span>
                ) : recordedBlobInfo ? (
                  `Rekaman siap ditranskrip (${fmtElapsed(recordingSeconds)})`
                ) : (
                  "Rekam langsung dari microphone"
                )}
              </p>
              {recording ? (
                <button onClick={handleStopRecording}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium py-2 transition-colors">
                  <Square size={13} /> Stop Recording
                </button>
              ) : (
                <div className="flex gap-2">
                  <button onClick={handleStartRecording}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg border border-red-600 text-red-400 hover:bg-red-600/10 text-sm font-medium py-2 transition-colors">
                    <Mic size={14} /> {recordedBlobInfo ? "Record Again" : "Start Recording"}
                  </button>
                  {recordedBlobInfo && (
                    <button onClick={handleSaveRecordingLocally} title="Save recording to local disk"
                      className="flex items-center justify-center gap-1.5 rounded-lg border border-gray-700 text-gray-300 hover:border-blue-500 hover:text-blue-400 text-sm font-medium px-3 py-2 transition-colors">
                      <Download size={14} />
                    </button>
                  )}
                </div>
              )}
              {recordError && (
                <div className="mt-2 text-left">
                  <p className="text-[11px] text-red-400 flex items-start gap-1">
                    <AlertTriangle size={11} className="shrink-0 mt-0.5" /> {recordError.message}
                  </p>
                  {recordError.needsHttps && (
                    <button
                      onClick={() => { window.location.href = "https:" + window.location.href.slice(window.location.protocol.length); }}
                      className="mt-1.5 w-full rounded-md bg-red-600/20 hover:bg-red-600/30 border border-red-600/40 text-red-300 text-[11px] font-medium py-1.5 transition-colors"
                    >
                      Buka via HTTPS
                    </button>
                  )}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900 p-5 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/30 mx-auto mb-3">
                <Upload size={28} className="text-blue-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Upload Audio</p>
              <p className="text-xs text-gray-600 mb-4">MP3, WAV, M4A — maks 100MB. Otomatis tersimpan di server bersama rekaman lain.</p>
              <input ref={fileRef} type="file" accept="audio/*,.mp3,.wav,.m4a" className="hidden"
                onChange={(e) => handlePickFile(e.target.files?.[0])} />
              <button onClick={() => fileRef.current?.click()}
                className="w-full rounded-lg border border-blue-600 text-blue-400 hover:bg-blue-600/10 text-sm font-medium py-2 transition-colors">
                {file && !recordedBlobInfo ? file.name : "Choose File"}
              </button>
              {file && !recordedBlobInfo && <p className="text-[11px] text-gray-600 mt-2">{fmtBytes(file.size)}</p>}
            </div>
          </div>

          {/* Transcribe */}
          <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-5">
            <div className="flex items-center gap-3 mb-3">
              <Sparkles size={18} className="text-purple-400" />
              <h3 className="text-sm font-semibold text-gray-200">Transcribe & Generate MOM with AI</h3>
            </div>
            <p className="text-xs text-gray-500 mb-4">
              Transcribe always runs on the on-premise GPU (Claude has no audio support). MOM generation can use either provider.
              Transcript opens in a new tab once ready.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleTranscribe} disabled={!file || transcribing}
                className="flex items-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 transition-colors">
                {transcribing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {transcribing ? "Transcribing…" : "1. Transcribe"}
              </button>
              <button onClick={handleGenerateMom} disabled={!transcript?.text || generating}
                className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 transition-colors">
                {generating ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                {generating ? "Generating…" : "2. Generate MOM"}
              </button>
              <select value={momProvider} onChange={(e) => setMomProvider(e.target.value)} title="Provider untuk Generate MOM"
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 outline-none focus:border-blue-500 cursor-pointer">
                <option value="onprem">Standard (On-Premise)</option>
                <option value="anthropic">Claude</option>
              </select>
            </div>

            {transcribeError && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />{transcribeError}
              </div>
            )}
            {generateError && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />{generateError}
              </div>
            )}
          </div>

          {/* Transcript result */}
          {transcript?.text && (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                  <CheckCircle2 size={15} className="text-green-400" /> Transcript
                </h3>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span>{Math.round(transcript.audio_duration_seconds)}s audio · processed in {transcript.processing_time_seconds}s</span>
                  <button onClick={() => window.open(`/ai/meeting-notes/view/${transcript.id}`, "_blank")}
                    className="flex items-center gap-1 text-gray-400 hover:text-gray-200">
                    <ExternalLink size={12} />Open in tab
                  </button>
                  <button onClick={copyTranscript} className="flex items-center gap-1 text-gray-400 hover:text-gray-200">
                    <Copy size={12} />{copied ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>
              <div className="max-h-64 overflow-y-auto text-sm text-gray-300 whitespace-pre-wrap leading-relaxed bg-gray-800/50 rounded-lg p-3">
                {transcript.text}
              </div>
            </div>
          )}

          {/* MOM result — editable */}
          {mom && (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                  <CheckCircle2 size={15} className="text-green-400" /> Minutes of Meeting
                  <span className="text-xs font-normal text-gray-500">— review & edit before downloading</span>
                </h3>
                <div className="flex items-center gap-2">
                  <button onClick={handleSaveMom} disabled={savingMom}
                    className="flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 hover:border-blue-500 px-2.5 py-1.5 text-xs text-gray-300 transition-colors">
                    {savingMom ? <Loader2 size={12} className="animate-spin" /> : <SaveIcon size={12} />}Save
                  </button>
                  <button onClick={() => handleDownloadDocx(transcript.id)} disabled={downloadingDocx}
                    className="flex items-center gap-1 rounded-md bg-blue-600 hover:bg-blue-700 px-2.5 py-1.5 text-xs text-white transition-colors">
                    {downloadingDocx ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}Download .docx
                  </button>
                </div>
              </div>

              {saveMomMsg && (
                <div className={`text-xs rounded-md px-3 py-2 ${saveMomMsg.type === "error" ? "bg-red-500/10 border border-red-500/30 text-red-400" : "bg-green-500/10 border border-green-500/30 text-green-400"}`}>
                  {saveMomMsg.text}
                </div>
              )}

              {mom.departments?.map((dept, di) => (
                <div key={di} className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <input value={dept.name} onChange={(e) => updateDeptName(di, e.target.value)}
                      className="flex-1 rounded-md border border-gray-700 bg-gray-900 px-2.5 py-1.5 text-sm font-semibold text-gray-200 uppercase outline-none focus:border-blue-500" />
                    <button onClick={() => removeDept(di)} className="text-gray-600 hover:text-red-400 p-1"><Trash2 size={14} /></button>
                  </div>

                  {dept.topics?.map((topic, ti) => (
                    <div key={ti} className="rounded-md border border-gray-800 bg-gray-900/60 p-3 space-y-2 ml-2">
                      <div className="flex items-center gap-2">
                        <input value={topic.title} onChange={(e) => updateTopicTitle(di, ti, e.target.value)}
                          className="flex-1 rounded-md border border-gray-700 bg-gray-950 px-2.5 py-1.5 text-sm font-medium text-gray-200 outline-none focus:border-blue-500" />
                        <button onClick={() => removeTopic(di, ti)} className="text-gray-600 hover:text-red-400 p-1"><Trash2 size={13} /></button>
                      </div>

                      {["discussion_points", "action_plans"].map((field) => (
                        <div key={field}>
                          <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            {field === "discussion_points" ? "Discussion Points" : "Action Plans"}
                          </p>
                          <div className="space-y-1.5">
                            {(topic[field] || []).map((pt, pi) => (
                              <div key={pi} className="flex items-center gap-2">
                                <input value={pt} onChange={(e) => updatePoint(di, ti, field, pi, e.target.value)}
                                  className="flex-1 rounded-md border border-gray-700 bg-gray-950 px-2.5 py-1.5 text-xs text-gray-300 outline-none focus:border-blue-500" />
                                <button onClick={() => removePoint(di, ti, field, pi)} className="text-gray-600 hover:text-red-400 p-0.5"><Trash2 size={12} /></button>
                              </div>
                            ))}
                            <button onClick={() => addPoint(di, ti, field)}
                              className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-blue-400">
                              <Plus size={11} /> Tambah {field === "discussion_points" ? "poin" : "action"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                  <button onClick={() => addTopic(di)}
                    className="flex items-center gap-1 text-xs text-gray-400 hover:text-blue-400 ml-2">
                    <Plus size={12} /> Tambah topik
                  </button>
                </div>
              ))}

              <button onClick={addDept}
                className="flex items-center gap-1.5 rounded-md border border-dashed border-gray-700 hover:border-blue-500 text-gray-400 hover:text-blue-400 text-xs font-medium px-3 py-2 w-full justify-center transition-colors">
                <Plus size={13} /> Tambah Departemen / Topik
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab: History */}
      {tab === "history" && (
        <div className="rounded-xl border border-gray-800 bg-gray-900">
          <div className="px-5 py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-200">Meeting Notes History</h3>
          </div>

          {historyLoading ? (
            <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-gray-600" /></div>
          ) : historyError ? (
            <div className="px-5 py-4 text-sm text-red-400 flex items-center gap-2"><AlertTriangle size={13} />{historyError}</div>
          ) : history.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-gray-600">Belum ada recording.</div>
          ) : (
            <div className="divide-y divide-gray-800">
              {history.map((item) => (
                <div key={item.id} className="flex items-center justify-between px-5 py-4 hover:bg-gray-800/40 transition-colors">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple-500/10 border border-purple-500/20">
                      <FileText size={16} className="text-purple-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-200 truncate">{item.meeting_title || "(Tanpa judul)"}</p>
                      <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                        <span className="flex items-center gap-1 text-xs text-gray-500">
                          <Clock size={11} />{fmtDate(item.created_at)}
                        </span>
                        {item.audio_duration_seconds && (
                          <span className="flex items-center gap-1 text-xs text-gray-500">
                            <Mic size={11} />{Math.round(item.audio_duration_seconds)}s
                          </span>
                        )}
                        {item.participants && (
                          <span className="flex items-center gap-1 text-xs text-gray-500">
                            <Users size={11} />{item.participants}
                          </span>
                        )}
                        <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 ${
                          item.source === "recorded" ? "bg-red-500/10 text-red-400" : "bg-blue-500/10 text-blue-400"
                        }`}>
                          {item.source === "recorded" ? "Recorded" : "Uploaded"}
                        </span>
                        {item.status === "error" && <span className="text-[10px] font-semibold rounded-full px-2 py-0.5 bg-red-500/10 text-red-400">Error</span>}
                        {item.has_mom && <span className="text-[10px] font-semibold rounded-full px-2 py-0.5 bg-green-500/10 text-green-400">MOM ready</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button onClick={() => window.open(`/ai/meeting-notes/view/${item.id}`, "_blank")}
                      className="flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                      <ExternalLink size={12} />Transcript
                    </button>
                    <button onClick={() => handleDownloadAudio(item.id)}
                      className="flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                      <Download size={12} />Audio
                    </button>
                    {item.has_mom && (
                      <button onClick={() => handleDownloadDocx(item.id)}
                        className="flex items-center gap-1 rounded-md bg-blue-600 hover:bg-blue-700 px-2.5 py-1.5 text-xs text-white transition-colors">
                        <Download size={12} />MOM
                      </button>
                    )}
                    <button onClick={() => handleDeleteRecording(item.id)}
                      className="flex items-center gap-1 rounded-md border border-red-800/40 bg-red-500/5 px-2.5 py-1.5 text-xs text-red-400 hover:bg-red-500/10 transition-colors">
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
