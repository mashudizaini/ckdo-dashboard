import { useState, useRef, useEffect } from "react";
import {
  FileText, Mic, Square, Upload, Sparkles, Clock, Users, Copy, Download, Loader2,
  AlertTriangle, CheckCircle2, Plus, Trash2, ExternalLink, Save as SaveIcon,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import * as recoveryDb from "./meetingRecordingRecovery";

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

function ordinal(n) {
  const suffixes = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0]);
}

// Matches the company MOM template's date style ("Friday, July 24th, 2026") —
// used to default the Date field to today instead of a stale hardcoded date.
function todayFormatted() {
  const d = new Date();
  const weekday = d.toLocaleDateString("en-US", { weekday: "long" });
  const month = d.toLocaleDateString("en-US", { month: "long" });
  return `${weekday}, ${month} ${ordinal(d.getDate())}, ${d.getFullYear()}`;
}

// Conservative middle-of-the-road estimate for the progress bar — real
// observed speed on this deployment ranges ~8x (a very long 82min meeting)
// to ~15-22x (shorter recordings) realtime, all GPU float16 + VAD-filtered
// faster-whisper large-v3. 10x under-promises a little on purpose so the
// bar rarely finishes "later than expected".
const ASSUMED_REALTIME_MULTIPLIER = 10;

// Reads an audio file's duration client-side (no upload needed) via a
// throwaway <audio> element — used to seed the estimated progress bar for
// an uploaded file (a live recording already tracks its own elapsed
// seconds directly).
function getAudioDurationSeconds(file) {
  return new Promise((resolve) => {
    try {
      const audio = document.createElement("audio");
      audio.preload = "metadata";
      audio.onloadedmetadata = () => {
        const d = isFinite(audio.duration) ? audio.duration : null;
        URL.revokeObjectURL(audio.src);
        resolve(d);
      };
      audio.onerror = () => resolve(null);
      audio.src = URL.createObjectURL(file);
    } catch (_) {
      resolve(null);
    }
  });
}

const MOM_PROVIDER_LABELS = {
  onprem: "the on-premise model",
  anthropic: "Claude",
  gemini: "Gemini",
  deepseek: "DeepSeek",
};

// Meeting info + participant defaults mirror the company's actual recurring
// weekly MOM template (sumber/4. MOM Admin Jul 24, 2026.pdf) so the form
// isn't blank for a meeting that happens every week with mostly the same
// title/venue/agenda/attendees — the user overwrites what's different.
const DEFAULT_PARTICIPANTS = [
  { name: "Mr. Lee Sunho", position: "Administration GM" },
  { name: "Ms. Tika", position: "Planning & Coordination Sr. Manager" },
  { name: "Ms. Dessy", position: "Accounting & Tax Manager" },
  { name: "Ms. Maria", position: "Purchasing Sr. Manager" },
  { name: "Mr. Mashudi", position: "IT Manager" },
  { name: "Mr. Utomo", position: "IT Asst. Manager" },
  { name: "Ms. Ellvin", position: "HRGA Sr. Manager" },
  { name: "", position: "" },
  { name: "", position: "" },
  { name: "", position: "" },
];

export default function MeetingNotes() {
  const { token } = useAuthStore();
  const headers = { Authorization: `Bearer ${token}` };

  // Wizard step within "New Recording" — side tabs instead of one long
  // scrolling page, so each stage (record, transcript, MOM) fits its own
  // shorter pane. Auto-advances on successful transcribe/generate, but the
  // user can always click back to an earlier step.
  const [step, setStep] = useState("setup"); // "info" | "setup" | "transcript" | "mom"

  // Meeting info
  const [title, setTitle] = useState("Administration Weekly Meeting");
  const [date, setDate] = useState(() => todayFormatted());
  const [time, setTime] = useState("10.00 AM – 11.45 AM");
  const [venue, setVenue] = useState("Tezobel Room - HQ Office");
  const [agenda, setAgenda] = useState("Administration Weekly Activities - Review and Follow-up Issues");

  // Participants — 10 structured (name, position) slots instead of one
  // free-text field, matching how the final MOM actually lists attendees.
  const [participantRows, setParticipantRows] = useState(() => DEFAULT_PARTICIPANTS.map((p) => ({ ...p })));
  const updateParticipant = (i, field, value) => {
    setParticipantRows((prev) => prev.map((p, idx) => (idx === i ? { ...p, [field]: value } : p)));
  };
  // Derived "Name (Position)" comma-separated string — the wire format the
  // backend already expects (unchanged), so only the input UI changes here.
  const participants = participantRows
    .filter((p) => p.name.trim())
    .map((p) => (p.position.trim() ? `${p.name.trim()} (${p.position.trim()})` : p.name.trim()))
    .join(", ");

  const [file, setFile] = useState(null);
  const fileRef = useRef(null);

  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState(null);
  const [transcript, setTranscript] = useState(null); // { id, text, segments, language, audio_duration_seconds, processing_time_seconds }
  // "" = auto-detect (mixed-language meetings), "id"/"en" = pin one language,
  // skipping Whisper's language-detection pass for a small speed gain.
  const [transcribeLanguage, setTranscribeLanguage] = useState("");
  // Estimated (not truly live — faster-whisper returns one final result with
  // no mid-transcription progress signal) percentage + ETA, derived from the
  // audio's own duration and this deployment's observed realtime-multiplier
  // (see ASSUMED_REALTIME_MULTIPLIER below). Caps at 95% until the request
  // actually completes, then jumps to 100 — never claims "done" early.
  const [transcribeProgress, setTranscribeProgress] = useState(null); // { pct, etaSeconds } | null
  const transcribeTimerRef = useRef(null);
  const [loadingRecording, setLoadingRecording] = useState(false);

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
  const recordingSessionIdRef = useRef(null);

  // A recording found in IndexedDB left over from an interrupted previous
  // attempt (crash, closed tab, forced logout mid-meeting) — offered for
  // recovery instead of silently lost. { sessionId, startedAt, meta, chunkCount } | null
  const [recoverableSession, setRecoverableSession] = useState(null);
  const [recovering, setRecovering] = useState(false);

  // Microphone device selection — lets the user pick the right input instead
  // of silently relying on whatever the OS/browser treats as "default",
  // which is the most common cause of a recording coming back silent.
  const [micDevices, setMicDevices] = useState([]);
  const [selectedMicId, setSelectedMicId] = useState("");

  // Live input level meter + silence detection — gives immediate feedback
  // that the mic is actually picking up sound, instead of only finding out
  // after a full record -> transcribe round trip that nothing was captured.
  const [audioLevel, setAudioLevel] = useState(0); // 0-100, live while recording
  const [micWarning, setMicWarning] = useState(null); // live "no sound detected" text
  const [recordingWasSilent, setRecordingWasSilent] = useState(false); // set on stop
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const levelRafRef = useRef(null);
  const peakLevelRef = useRef(0);
  const lastLoudTsRef = useRef(0);

  const loadMicDevices = async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      setMicDevices(devices.filter((d) => d.kind === "audioinput"));
    } catch (_) { /* enumerateDevices needs a secure context; ignore if unavailable */ }
  };

  useEffect(() => { loadMicDevices(); }, []);

  const SILENCE_LEVEL = 4;        // level below this counts as "no signal"
  const SILENCE_WARN_MS = 3000;   // how long it must stay silent before warning live

  const startLevelMeter = (stream) => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    audioContextRef.current = ctx;
    analyserRef.current = analyser;
    peakLevelRef.current = 0;
    lastLoudTsRef.current = Date.now();
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sumSq = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sumSq += v * v;
      }
      const rms = Math.sqrt(sumSq / data.length);
      const level = Math.min(100, Math.round(rms * 400));
      peakLevelRef.current = Math.max(peakLevelRef.current, level);
      setAudioLevel(level);
      const now = Date.now();
      if (level > SILENCE_LEVEL) {
        lastLoudTsRef.current = now;
        setMicWarning(null);
      } else if (now - lastLoudTsRef.current > SILENCE_WARN_MS) {
        setMicWarning("No sound detected — check that the right microphone is selected and it isn't muted.");
      }
      levelRafRef.current = requestAnimationFrame(tick);
    };
    tick();
  };

  const stopLevelMeter = () => {
    if (levelRafRef.current) cancelAnimationFrame(levelRafRef.current);
    levelRafRef.current = null;
    analyserRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setAudioLevel(0);
  };

  // History
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (levelRafRef.current) cancelAnimationFrame(levelRafRef.current);
      audioContextRef.current?.close().catch(() => {});
    };
  }, []);

  // On mount, check for a recording left behind by an interrupted previous
  // session (see meetingRecordingRecovery.js) and offer to recover it.
  useEffect(() => {
    recoveryDb.findRecoverableSession().then((s) => { if (s) setRecoverableSession(s); });
  }, []);

  // Keep the app's idle-timeout from logging the user out mid-meeting: it
  // deliberately only counts mouse/keyboard/scroll/touch as activity (see
  // authStore.js), which a hands-off recording or a long unattended
  // transcription/MOM wait will never produce. Ping it periodically for as
  // long as any of those are actually in progress.
  useEffect(() => {
    if (!(recording || transcribing || generating)) return;
    useAuthStore.getState().keepAlive();
    const id = setInterval(() => useAuthStore.getState().keepAlive(), 60000);
    return () => clearInterval(id);
  }, [recording, transcribing, generating]);

  // Fetched once on mount (not just when the History tab is opened) — the
  // compact "Recent Recordings" list on the Record & Upload step needs it
  // too, so users can jump back into a recent recording without leaving
  // the main view.
  useEffect(() => { fetchHistory(); }, []); // eslint-disable-line

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
      setTranscribeError("File too large — maximum 100MB.");
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
    setMicWarning(null);
    setRecordingWasSilent(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      const isInsecureHttp = window.location.protocol === "http:" && !["localhost", "127.0.0.1"].includes(window.location.hostname);
      setRecordError(
        isInsecureHttp
          ? { message: "This page is loaded without HTTPS — the microphone needs a secure connection.", needsHttps: true }
          : { message: "This browser doesn't support microphone recording." }
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: selectedMicId ? { deviceId: { exact: selectedMicId } } : true,
      });
      streamRef.current = stream;
      loadMicDevices(); // device labels are only populated after permission is granted
      startLevelMeter(stream);
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];
      const sessionId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      recordingSessionIdRef.current = sessionId;
      recoveryDb.startSession(sessionId, { mimeType: recorder.mimeType || mimeType || "audio/webm", title });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
          recoveryDb.saveChunk(sessionId, e.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const ext = (recorder.mimeType || "audio/webm").includes("mp4") ? "m4a" : "webm";
        const filename = `recording-${Date.now()}.${ext}`;
        const recordedFile = new File([blob], filename, { type: blob.type });
        setFile(recordedFile);
        setRecordedBlobInfo({ blob, filename });
        setRecordingWasSilent(peakLevelRef.current <= SILENCE_LEVEL);
        resetResults();
        stopLevelMeter();
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        // Reached a clean stop with the audio safely handed off to
        // component state — the IndexedDB backup has served its purpose.
        recoveryDb.clearSession(sessionId);
        recordingSessionIdRef.current = null;
      };
      mediaRecorderRef.current = recorder;
      // 30s timeslice — without it, MediaRecorder never fires
      // ondataavailable until .stop() is called, so a 1-2h recording would
      // sit unbacked-up in the browser's own internal buffer the whole
      // time no matter what we do here.
      recorder.start(30000);
      setRecording(true);
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    } catch (e) {
      if (e.name === "NotAllowedError") {
        setRecordError({ message: "Microphone access denied. Allow microphone access in your browser settings, then try again." });
      } else {
        setRecordError({ message: `Failed to access microphone: ${e.message || e.name}` });
      }
    }
  };

  const handleStopRecording = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const handleRecoverSession = async () => {
    if (!recoverableSession) return;
    setRecovering(true);
    try {
      const chunks = await recoveryDb.getChunks(recoverableSession.sessionId);
      if (!chunks.length) throw new Error("No audio data found in the backup");
      const mimeType = recoverableSession.meta?.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type: mimeType });
      const ext = mimeType.includes("mp4") ? "m4a" : "webm";
      const filename = `recovered-${recoverableSession.sessionId}.${ext}`;
      const recoveredFile = new File([blob], filename, { type: mimeType });
      setFile(recoveredFile);
      setRecordedBlobInfo({ blob, filename });
      resetResults();
      await recoveryDb.clearSession(recoverableSession.sessionId);
      setRecoverableSession(null);
    } catch (e) {
      setRecordError({ message: `Failed to recover the backed-up recording: ${e.message || e}` });
    } finally {
      setRecovering(false);
    }
  };

  const handleDiscardRecoverableSession = async () => {
    if (!recoverableSession) return;
    await recoveryDb.clearSession(recoverableSession.sessionId);
    setRecoverableSession(null);
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
    setTranscribeProgress({ pct: 0, etaSeconds: null });

    // Seed the estimate from the audio's own duration — a live recording
    // already knows its elapsed seconds; an uploaded file needs its
    // duration read out client-side first (no upload required for that).
    const durationSec = recordedBlobInfo ? recordingSeconds : await getAudioDurationSeconds(file);
    const estimatedTotal = durationSec ? Math.max(10, durationSec / ASSUMED_REALTIME_MULTIPLIER) : null;
    const startedAt = Date.now();
    if (estimatedTotal) {
      transcribeTimerRef.current = setInterval(() => {
        const elapsed = (Date.now() - startedAt) / 1000;
        setTranscribeProgress({
          pct: Math.min(95, Math.round((elapsed / estimatedTotal) * 100)),
          etaSeconds: Math.max(0, Math.round(estimatedTotal - elapsed)),
        });
      }, 1000);
    }

    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source", recordedBlobInfo ? "recorded" : "uploaded");
      fd.append("meeting_title", title);
      fd.append("participants", participants);
      if (transcribeLanguage) fd.append("language", transcribeLanguage);
      const res = await fetch("/api/v1/ai/meeting-notes/transcribe", { method: "POST", headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Transcription failed");
      setTranscribeProgress({ pct: 100, etaSeconds: 0 });
      setTranscript(data);
      setStep("transcript");
      fetchHistory();
    } catch (e) {
      setTranscribeError(e.message || String(e));
    } finally {
      if (transcribeTimerRef.current) { clearInterval(transcribeTimerRef.current); transcribeTimerRef.current = null; }
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
      setStep("mom");
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

  // Pulls a past recording's saved transcript (and MOM, if any) back into
  // the wizard so it can be re-run through generate-mom with a different
  // provider — no re-transcription needed, the audio is never re-uploaded.
  const handleLoadRecording = async (recordingId) => {
    setLoadingRecording(true);
    try {
      const res = await fetch(`/api/v1/ai/meeting-notes/recordings/${recordingId}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Gagal memuat recording");
      setTranscript({
        id: data.id,
        text: data.transcript,
        language: data.transcript_language,
        audio_duration_seconds: data.audio_duration_seconds,
        processing_time_seconds: data.processing_time_seconds,
      });
      setTitle(data.meeting_title || title);
      setParticipants(data.participants || "");
      if (data.mom_meta?.date) setDate(data.mom_meta.date);
      if (data.mom_meta?.time) setTime(data.mom_meta.time);
      if (data.mom_meta?.venue) setVenue(data.mom_meta.venue);
      if (data.mom_meta?.agenda) setAgenda(data.mom_meta.agenda);
      setMom(data.mom_json || null);
      setStep("transcript");
    } catch (e) {
      setTranscribeError(e.message || String(e));
    } finally {
      setLoadingRecording(false);
    }
  };

  const copyTranscript = () => {
    if (!transcript?.text) return;
    navigator.clipboard.writeText(transcript.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadTranscript = () => {
    if (!transcript?.text) return;
    const blob = new Blob([transcript.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${(title || "Transcript").replace(/\s+/g, "_")}.txt`; a.click();
    URL.revokeObjectURL(url);
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

      <div className="flex items-start gap-5">
          {/* Side tab rail — wizard steps instead of one long scrolling page,
              so each stage gets its own shorter pane (like Otter/Fireflies). */}
          <div className="w-60 shrink-0 rounded-xl border border-gray-800 bg-gray-900 p-2 sticky top-6 space-y-1">
            {[
              { id: "info", label: "Meeting Info", hint: "Title, date, venue, participants" },
              { id: "setup", label: "Record & Upload", hint: "Live recording or file upload" },
              { id: "transcript", label: "Transcript", hint: "Review the transcribed text" },
              { id: "mom", label: "Minutes of Meeting", hint: "Review, edit & download" },
              { id: "history", label: "History", hint: "All past recordings & MOM" },
            ].map((s, idx) => {
              const isActive = step === s.id;
              const isDone = (s.id === "setup" && !!transcript) || (s.id === "transcript" && !!mom);
              return (
                <button key={s.id} onClick={() => setStep(s.id)}
                  className={`w-full flex items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors ${
                    isActive ? "bg-blue-600/15 border border-blue-500/40" : "border border-transparent hover:bg-gray-800/60"
                  }`}>
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold mt-0.5 ${
                    isDone ? "bg-green-500/20 text-green-400" : isActive ? "bg-blue-500/20 text-blue-300" : "bg-gray-800 text-gray-500"
                  }`}>
                    {isDone ? <CheckCircle2 size={13} /> : idx + 1}
                  </span>
                  <span className="min-w-0">
                    <span className={`block text-sm font-medium ${isActive ? "text-blue-300" : "text-gray-200"}`}>{s.label}</span>
                    <span className="block text-[11px] text-gray-600 mt-0.5">{s.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Step content */}
          <div className="flex-1 min-w-0 space-y-4">
          {step === "info" && (
            <>
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
                <label className="block text-xs text-gray-500 mb-1.5">Date</label>
                <input type="text" value={date} onChange={(e) => setDate(e.target.value)}
                  placeholder="e.g. Friday, July 24th, 2026"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Time</label>
                <input type="text" value={time} onChange={(e) => setTime(e.target.value)}
                  placeholder="e.g. 10.00 AM – 11.45 AM"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Venue</label>
                <input type="text" value={venue} onChange={(e) => setVenue(e.target.value)}
                  placeholder="e.g. Meeting Room A"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1.5">Agenda</label>
                <input type="text" value={agenda} onChange={(e) => setAgenda(e.target.value)}
                  placeholder="e.g. Weekly Coordination"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
              </div>
            </div>
          </div>

          {/* Participants — 10 structured slots (name + position), pre-filled
              from the recurring meeting's usual attendees; blank rows are
              simply left out of the final MOM. */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h3 className="text-sm font-semibold text-gray-200 mb-1">Participants</h3>
            <p className="text-xs text-gray-600 mb-4">Up to 10 attendees — leave a row blank to skip it.</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
              {participantRows.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="w-4 shrink-0 text-xs text-gray-600 text-right">{i + 1}.</span>
                  <input type="text" value={p.name} onChange={(e) => updateParticipant(i, "name", e.target.value)}
                    placeholder="Name"
                    className="flex-1 min-w-0 rounded-lg border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
                  <input type="text" value={p.position} onChange={(e) => updateParticipant(i, "position", e.target.value)}
                    placeholder="Position"
                    className="flex-1 min-w-0 rounded-lg border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors" />
                </div>
              ))}
            </div>
          </div>
            </>
          )}

          {step === "setup" && (
            <>
          {recoverableSession && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-600/40 bg-amber-500/10 p-4">
              <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-amber-200">Unfinished recording found</p>
                <p className="text-xs text-amber-200/80 mt-1 leading-relaxed">
                  A recording from {new Date(recoverableSession.startedAt).toLocaleString("id-ID")} ({recoverableSession.chunkCount} saved chunk{recoverableSession.chunkCount === 1 ? "" : "s"})
                  was never finished — likely an interrupted session (closed tab, logout, crash). The audio captured
                  so far is still backed up and can be recovered.
                </p>
                <div className="flex items-center gap-2 mt-3">
                  <button onClick={handleRecoverSession} disabled={recovering}
                    className="flex items-center gap-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 transition-colors">
                    {recovering ? <Loader2 size={12} className="animate-spin" /> : null}
                    {recovering ? "Recovering…" : "Recover this recording"}
                  </button>
                  <button onClick={handleDiscardRecoverableSession} disabled={recovering}
                    className="text-xs text-amber-200/70 hover:text-amber-100 px-2 py-1.5 transition-colors">
                    Discard
                  </button>
                </div>
              </div>
            </div>
          )}
          {/* Record & Upload (left) / Transcribe & Recent Recordings (right) */}
          <div className="grid grid-cols-2 gap-4 items-start">
          <div className="space-y-4">
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 text-center">
              <div className={`flex h-16 w-16 items-center justify-center rounded-full mx-auto mb-3 border ${
                recording ? "bg-red-500/20 border-red-500/50 animate-pulse" : "bg-red-500/10 border-red-500/30"
              }`}>
                <Mic size={28} className="text-red-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Live Recording</p>
              <p className="text-xs text-gray-600 mb-3">
                {recording ? (
                  <span className="flex items-center justify-center gap-1.5 text-red-400 font-medium">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" /> Recording… {fmtElapsed(recordingSeconds)}
                  </span>
                ) : recordedBlobInfo ? (
                  `Recording ready (${fmtElapsed(recordingSeconds)})`
                ) : (
                  "Record directly from your microphone"
                )}
              </p>

              {!recording && (
                <div className="mb-3 text-left">
                  <label className="block text-[11px] text-gray-500 mb-1">Microphone</label>
                  {micDevices.length === 0 ? (
                    <p className="text-[11px] text-amber-400 flex items-center gap-1">
                      <AlertTriangle size={11} /> No microphone detected yet — click Start Recording to grant access.
                    </p>
                  ) : (
                    <select value={selectedMicId} onChange={(e) => setSelectedMicId(e.target.value)}
                      className="w-full rounded-md border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-blue-500 cursor-pointer">
                      <option value="">Default microphone</option>
                      {micDevices.map((d, i) => (
                        <option key={d.deviceId || i} value={d.deviceId}>{d.label || `Microphone ${i + 1}`}</option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {recording && (
                <div className="mb-3">
                  <div className="h-2.5 w-full rounded-full bg-gray-800 overflow-hidden border border-gray-700">
                    <div
                      className={`h-full rounded-full transition-all duration-75 ${audioLevel > SILENCE_LEVEL ? "bg-green-500" : "bg-gray-600"}`}
                      style={{ width: `${Math.max(4, audioLevel)}%` }}
                    />
                  </div>
                  <p className={`text-[10px] mt-1 ${micWarning ? "text-amber-400 font-medium" : "text-gray-600"}`}>
                    {micWarning ? (
                      <span className="flex items-center justify-center gap-1"><AlertTriangle size={10} />{micWarning}</span>
                    ) : audioLevel > SILENCE_LEVEL ? (
                      "Mic level ● sound is being picked up"
                    ) : (
                      "Speak now — the bar above should move"
                    )}
                  </p>
                </div>
              )}

              {recording ? (
                <button onClick={handleStopRecording}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium py-2 transition-colors">
                  <Square size={13} /> Stop Recording
                </button>
              ) : (
                <button onClick={handleStartRecording}
                  className="w-full flex items-center justify-center gap-2 rounded-lg border border-red-600 text-red-400 hover:bg-red-600/10 text-sm font-medium py-2 transition-colors">
                  <Mic size={14} /> {recordedBlobInfo ? "Record Again" : "Start Recording"}
                </button>
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
                      Open via HTTPS
                    </button>
                  )}
                </div>
              )}
              {recordedBlobInfo && !recording && (
                <div className={`mt-3 text-left rounded-lg border px-3 py-2.5 ${
                  recordingWasSilent ? "border-amber-600/40 bg-amber-500/10" : "border-green-600/40 bg-green-500/10"
                }`}>
                  <p className={`flex items-center gap-1.5 text-xs font-semibold ${recordingWasSilent ? "text-amber-300" : "text-green-300"}`}>
                    {recordingWasSilent ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
                    {recordingWasSilent ? "Recording captured — but no sound was detected" : "Recording captured"}
                  </p>
                  <p className="text-[11px] text-gray-400 mt-1.5 break-all">
                    <span className="text-gray-500">File:</span> {recordedBlobInfo.filename}
                    <span className="text-gray-500"> · </span>{fmtElapsed(recordingSeconds)}
                    <span className="text-gray-500"> · </span>{fmtBytes(recordedBlobInfo.blob.size)}
                  </p>
                  {recordingWasSilent ? (
                    <p className="text-[11px] text-amber-400/90 mt-1.5 leading-relaxed">
                      The audio level never rose above silence during this recording. Transcribing it will almost
                      certainly come back empty. Check the microphone selected above isn't muted or set to the
                      wrong device, then try Record Again.
                    </p>
                  ) : (
                    <p className="text-[11px] text-gray-500 mt-1.5 leading-relaxed">
                      This will be uploaded and saved permanently on the server (in the recordings history) when you click <strong className="text-gray-300">Transcribe</strong> below.
                    </p>
                  )}
                  <button onClick={handleSaveRecordingLocally}
                    className="mt-2 flex items-center gap-1.5 rounded-md border border-gray-700 bg-gray-800 hover:border-blue-500 hover:text-blue-400 px-2.5 py-1.5 text-[11px] font-medium text-gray-300 transition-colors">
                    <Download size={12} /> Save a copy to this device
                  </button>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900 p-5 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/30 mx-auto mb-3">
                <Upload size={28} className="text-blue-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Upload Audio</p>
              <p className="text-xs text-gray-600 mb-4">MP3, WAV, M4A — max 100MB. Saved on the server alongside other recordings once transcribed.</p>
              <input ref={fileRef} type="file" accept="audio/*,.mp3,.wav,.m4a" className="hidden"
                onChange={(e) => handlePickFile(e.target.files?.[0])} />
              <button onClick={() => fileRef.current?.click()}
                className="w-full rounded-lg border border-blue-600 text-blue-400 hover:bg-blue-600/10 text-sm font-medium py-2 transition-colors">
                {file && !recordedBlobInfo ? file.name : "Choose File"}
              </button>
              {file && !recordedBlobInfo && <p className="text-[11px] text-gray-600 mt-2">{fmtBytes(file.size)}</p>}
            </div>
          </div>

          <div className="space-y-4">
          {/* Transcribe */}
          <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-5">
            <div className="flex items-center gap-3 mb-3">
              <Sparkles size={18} className="text-purple-400" />
              <h3 className="text-sm font-semibold text-gray-200">Transcribe Audio</h3>
            </div>
            <div className="flex items-center gap-3 mb-4">
              <label className="text-xs text-gray-500 shrink-0">Meeting language</label>
              <select value={transcribeLanguage} onChange={(e) => setTranscribeLanguage(e.target.value)} disabled={transcribing}
                className="rounded-md border border-gray-700 bg-gray-800 text-gray-200 text-xs px-2.5 py-1.5 focus:outline-none focus:border-purple-500 disabled:opacity-50">
                <option value="">Auto-detect (mixed / both)</option>
                <option value="id">Bahasa Indonesia</option>
                <option value="en">English</option>
              </select>
            </div>
            <button onClick={handleTranscribe} disabled={!file || transcribing}
              className="flex items-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 transition-colors">
              {transcribing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {transcribing ? "Transcribing…" : "Transcribe"}
            </button>

            {transcribing && (
              <div className="mt-3 rounded-lg border border-purple-500/40 bg-purple-950/50 px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <Loader2 size={18} className="animate-spin text-purple-300 shrink-0" />
                  <span className="text-sm font-semibold text-purple-200">Transcribing audio via GPU Whisper… please wait, this tab will update automatically.</span>
                </div>
                <div className="mt-2.5 h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
                  <div className="h-full rounded-full bg-purple-400 transition-all duration-1000 ease-linear"
                    style={{ width: `${transcribeProgress?.pct ?? 0}%` }} />
                </div>
                <div className="mt-1.5 flex items-center justify-between text-[11px] text-purple-300/80">
                  <span>{transcribeProgress?.pct ?? 0}%</span>
                  <span>
                    {transcribeProgress?.etaSeconds != null
                      ? transcribeProgress.etaSeconds > 0
                        ? `Est. ${fmtElapsed(transcribeProgress.etaSeconds)} remaining`
                        : "Almost done…"
                      : "Estimating…"}
                  </span>
                </div>
              </div>
            )}

            {transcribeError && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />{transcribeError}
              </div>
            )}
          </div>

          {/* Recent Recordings — compact, 5 rows visible then scroll, so
              users can jump back into a recent recording without leaving
              this view. Full detail (filters, delete, MOM/audio download)
              still lives in the History step. */}
          <div className="rounded-xl border border-gray-800 bg-gray-900">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">Recent Recordings</h3>
              <button onClick={() => setStep("history")} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">View all</button>
            </div>
            {historyLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-gray-600" /></div>
            ) : history.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-gray-600">Belum ada recording.</div>
            ) : (
              <div className="divide-y divide-gray-800 overflow-y-auto" style={{ maxHeight: 5 * 52 }}>
                {history.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-gray-800/40 transition-colors">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-gray-200 truncate">{item.meeting_title || "(Tanpa judul)"}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-500">{fmtDate(item.created_at)}</span>
                        <span className={`text-[9px] font-semibold rounded-full px-1.5 py-0.5 ${
                          item.source === "recorded" ? "bg-red-500/10 text-red-400" : "bg-blue-500/10 text-blue-400"
                        }`}>
                          {item.source === "recorded" ? "Recorded" : "Uploaded"}
                        </span>
                        {item.has_mom && <span className="text-[9px] font-semibold rounded-full px-1.5 py-0.5 bg-green-500/10 text-green-400">MOM ready</span>}
                      </div>
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      {item.status !== "error" && (
                        <button onClick={() => handleLoadRecording(item.id)} disabled={loadingRecording}
                          className="text-gray-500 hover:text-purple-400 transition-colors disabled:opacity-50" title="Reprocess (regenerate MOM with a different model)">
                          <Sparkles size={13} />
                        </button>
                      )}
                      <button onClick={() => window.open(`/ai/meeting-notes/view/${item.id}`, "_blank")}
                        className="text-gray-500 hover:text-gray-200 transition-colors" title="Open transcript">
                        <ExternalLink size={13} />
                      </button>
                      <button onClick={() => handleDeleteRecording(item.id)}
                        className="text-gray-500 hover:text-red-400 transition-colors" title="Delete recording">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          </div>
          </div>
            </>
          )}

          {step === "transcript" && (
            <>
          {!transcript ? (
            <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900 p-10 text-center">
              <FileText size={28} className="text-gray-700 mx-auto mb-3" />
              <p className="text-sm text-gray-400 mb-1">No transcript yet</p>
              <p className="text-xs text-gray-600 mb-4">Record or upload audio and transcribe it first.</p>
              <button onClick={() => setStep("setup")}
                className="rounded-lg border border-blue-600 text-blue-400 hover:bg-blue-600/10 text-sm font-medium px-4 py-2 transition-colors">
                Go to Record & Upload
              </button>
            </div>
          ) : (
            <>
          {/* Transcript result — always shown once a transcribe attempt completes,
              even when the text comes back empty (e.g. silent/muted recording),
              so the user always gets a visible outcome instead of nothing happening. */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                  {transcript.text?.trim() ? (
                    <><CheckCircle2 size={15} className="text-green-400" /> Transcript</>
                  ) : (
                    <><AlertTriangle size={15} className="text-amber-400" /> Transcript</>
                  )}
                </h3>
                {transcript.text?.trim() && (
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{Math.round(transcript.audio_duration_seconds)}s audio · processed in {transcript.processing_time_seconds}s</span>
                    <button onClick={() => window.open(`/ai/meeting-notes/view/${transcript.id}`, "_blank")}
                      className="flex items-center gap-1 text-gray-400 hover:text-gray-200">
                      <ExternalLink size={12} />Open in tab
                    </button>
                    <button onClick={copyTranscript} className="flex items-center gap-1 text-gray-400 hover:text-gray-200">
                      <Copy size={12} />{copied ? "Copied!" : "Copy"}
                    </button>
                    <button onClick={downloadTranscript} className="flex items-center gap-1 text-gray-400 hover:text-gray-200">
                      <Download size={12} />Download .txt
                    </button>
                  </div>
                )}
              </div>
              {transcript.text?.trim() ? (
                <div className="max-h-64 overflow-y-auto text-sm text-gray-300 whitespace-pre-wrap leading-relaxed bg-gray-800/50 rounded-lg p-3">
                  {transcript.text}
                </div>
              ) : (
                <div className="flex items-start gap-2.5 rounded-lg border border-amber-600/40 bg-amber-500/10 px-4 py-3">
                  <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-200 leading-relaxed">
                    <p className="font-semibold mb-1">No speech detected</p>
                    <p>
                      The recording ({Math.round(transcript.audio_duration_seconds || 0)}s) was processed successfully,
                      but came back with no words — this usually means the microphone was muted, the wrong input
                      device was selected, or the room was silent while recording. Check your microphone settings
                      and try recording again.
                    </p>
                  </div>
                </div>
              )}
          </div>

          {/* Generate MOM */}
          <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-5">
            <div className="flex items-center gap-3 mb-3">
              <FileText size={18} className="text-blue-400" />
              <h3 className="text-sm font-semibold text-gray-200">Generate Minutes of Meeting with AI</h3>
            </div>
            <p className="text-xs text-gray-500 mb-4">Structures the transcript into departments, topics, discussion points & action plans.</p>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleGenerateMom} disabled={!transcript?.text || generating}
                className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 transition-colors">
                {generating ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                {generating ? "Generating…" : "Generate MOM"}
              </button>
              <select value={momProvider} onChange={(e) => setMomProvider(e.target.value)} title="Provider for Generate MOM"
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 outline-none focus:border-blue-500 cursor-pointer">
                <option value="onprem">Standard (On-Premise)</option>
                <option value="anthropic">Claude</option>
                <option value="gemini">Gemini</option>
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>

            {generating && (
              <div className="mt-3 rounded-lg border border-blue-500/40 bg-blue-950/50 px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <Loader2 size={18} className="animate-spin text-blue-300 shrink-0" />
                  <span className="text-sm font-semibold text-blue-200">Generating Minutes of Meeting with {MOM_PROVIDER_LABELS[momProvider] || "the on-premise model"}…</span>
                </div>
                <div className="mt-2.5 h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
                  <div className="h-full w-1/3 rounded-full bg-blue-400 animate-pulse" />
                </div>
              </div>
            )}
            {generateError && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <AlertTriangle size={13} className="shrink-0 mt-0.5" />{generateError}
              </div>
            )}
          </div>
            </>
          )}
            </>
          )}

          {step === "mom" && (
            <>
          {!mom ? (
            <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900 p-10 text-center">
              <CheckCircle2 size={28} className="text-gray-700 mx-auto mb-3" />
              <p className="text-sm text-gray-400 mb-1">No Minutes of Meeting yet</p>
              <p className="text-xs text-gray-600 mb-4">Generate the MOM from a transcript first.</p>
              <button onClick={() => setStep("transcript")}
                className="rounded-lg border border-blue-600 text-blue-400 hover:bg-blue-600/10 text-sm font-medium px-4 py-2 transition-colors">
                Go to Transcript
              </button>
            </div>
          ) : (
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

              {!mom.departments?.length && (
                <div className="flex items-start gap-2.5 rounded-lg border border-amber-600/40 bg-amber-500/10 px-4 py-3">
                  <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-200 leading-relaxed">
                    <p className="font-semibold mb-1">AI found no meeting content to summarize</p>
                    <p>
                      The generated MOM has zero departments/topics — downloading now would produce a .docx with
                      just the letterhead and no discussion content. This usually means the transcript doesn't
                      contain identifiable meeting discussion (e.g. it's casual conversation, too short, or the
                      wrong recording). Go back to the <button onClick={() => setStep("transcript")} className="underline hover:text-amber-100">Transcript</button> tab
                      to check what was actually transcribed, or add a department manually below.
                    </p>
                  </div>
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
            </>
          )}

          {step === "history" && (
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
                    {item.status !== "error" && (
                      <button onClick={() => handleLoadRecording(item.id)} disabled={loadingRecording}
                        title="Reprocess (regenerate MOM with a different model)"
                        className="flex items-center gap-1 rounded-md border border-purple-700/50 bg-purple-500/10 px-2.5 py-1.5 text-xs text-purple-300 hover:bg-purple-500/20 transition-colors disabled:opacity-50">
                        <Sparkles size={12} />Reprocess
                      </button>
                    )}
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
        </div>
    </div>
  );
}
