"""
Whisper Transcription Service — runs on the ai-engine GPU box (172.21.2.27),
alongside Ollama, so the main CKDO Dashboard backend can transcribe long
meeting recordings (1-2 hours) fast instead of running faster-whisper
in-process on CPU.

The model is loaded lazily on the first request and unloaded again after
WHISPER_IDLE_UNLOAD_SECONDS without a request (default 600s). Meetings are
uploaded a few times a day, so keeping the model resident around the clock
only took ~4GB of the GPU's 16GB away from Ollama for nothing. The cost is a
one-off model load (a few seconds, from local disk) on the first request
after an idle period — negligible next to a 1-2 hour transcription. Set
WHISPER_IDLE_UNLOAD_SECONDS=0 to keep the model resident as before.

Run under systemd (see whisper-server.service) — restarts automatically,
starts on boot, matching how ollama.service is already run on this box.

Deployed on ai-engine as /home/aiuser/whisper-service/whisper_server.py
(venv in the same folder, packages in requirements.txt) and
/etc/systemd/system/whisper-server.service. Edit this copy, then copy it
there and `sudo systemctl restart whisper-server`.
"""
import asyncio
import gc
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from faster_whisper import WhisperModel
import structlog

logger = structlog.get_logger()

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "large-v3")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
IDLE_UNLOAD_SECONDS = int(os.environ.get("WHISPER_IDLE_UNLOAD_SECONDS", "600"))

_model: WhisperModel | None = None
_lock = threading.Lock()  # guards _model, _in_flight, _last_used
_in_flight = 0
_last_used = 0.0


def _acquire_model() -> WhisperModel:
    """Return the loaded model (loading it if needed) and mark a request in flight."""
    global _model, _in_flight
    with _lock:
        if _model is None:
            logger.info("loading_whisper_model", model=MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            t0 = time.time()
            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            logger.info("whisper_model_loaded", elapsed_seconds=round(time.time() - t0, 1))
        _in_flight += 1
        return _model


def _release_model() -> None:
    global _in_flight, _last_used
    with _lock:
        _in_flight -= 1
        _last_used = time.time()


def _unload_if_idle() -> None:
    global _model
    with _lock:
        if _model is None or _in_flight > 0 or time.time() - _last_used < IDLE_UNLOAD_SECONDS:
            return
        _model = None
    gc.collect()  # CTranslate2 frees the GPU memory once the model object is gone
    logger.info("whisper_model_unloaded", idle_seconds=IDLE_UNLOAD_SECONDS)


async def _idle_watcher():
    while True:
        await asyncio.sleep(30)
        await asyncio.to_thread(_unload_if_idle)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    watcher = None
    if IDLE_UNLOAD_SECONDS > 0:
        watcher = asyncio.create_task(_idle_watcher())
    else:
        # Resident mode: load at startup like before; with no watcher it never unloads.
        await asyncio.to_thread(_acquire_model)
        _release_model()
    yield
    if watcher:
        watcher.cancel()
    _model = None


app = FastAPI(title="CKDO Whisper Transcription Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "loaded": _model is not None,
        "idle_unload_seconds": IDLE_UNLOAD_SECONDS,
    }


def _transcribe(path: str, language: str | None, task: str, filename: str | None) -> dict:
    model = _acquire_model()
    try:
        t0 = time.time()
        segments_gen, info = model.transcribe(
            path,
            language=language or None,
            task=task,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segments = []
        text_parts = []
        for seg in segments_gen:
            text = seg.text.strip()
            segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
            text_parts.append(text)

        elapsed = time.time() - t0
        logger.info(
            "transcription_complete",
            filename=filename,
            audio_duration_seconds=round(info.duration, 1),
            processing_time_seconds=round(elapsed, 1),
            speed_multiple=round(info.duration / elapsed, 1) if elapsed > 0 else None,
            language=info.language,
            task=task,
        )

        return {
            "text": " ".join(text_parts),
            "segments": segments,
            # "translate" always outputs English text; report that as the
            # transcript's language and keep the spoken one separately.
            "language": "en" if task == "translate" else info.language,
            "source_language": info.language,
            "task": task,
            "language_probability": round(info.language_probability, 3),
            "audio_duration_seconds": round(info.duration, 1),
            "processing_time_seconds": round(elapsed, 1),
        }
    finally:
        _release_model()


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(None),  # e.g. "id", "en" — omit to auto-detect (mixed-language meetings)
    # "translate" = transcribe speech in `language` straight into English text
    # (e.g. Korean meetings). large-v3 supports this; large-v3-turbo does not.
    task: str = Form("transcribe"),
):
    if task not in ("transcribe", "translate"):
        raise HTTPException(400, 'task must be "transcribe" or "translate"')
    suffix = os.path.splitext(file.filename or "")[1] or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # Run in a worker thread so /health (and the idle watcher) stay
        # responsive during a long transcription.
        return await asyncio.to_thread(_transcribe, tmp_path, language, task, file.filename)
    except Exception as e:
        logger.error("transcription_failed", filename=file.filename, error=str(e))
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        os.remove(tmp_path)
