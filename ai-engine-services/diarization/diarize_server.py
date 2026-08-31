"""
CKDO Speaker Diarization Service
─────────────────────────────────────────
Runs on the "ai-engine" VM (172.21.2.27), the same box as whisper-server.service
and Ollama — deliberately colocated so this GPU-hungry service shares that
hardware, and the ckdo-dashboard backend only ever talks to it over HTTP,
exactly like it already does for Whisper (see backend/app/config.py's
diarization_api_url and backend/app/services/speaker_id_service.py).

This service is pure ML inference and knows nothing about people — it never
stores anything and has no concept of "names". Enrollment storage, the
name-matching decision, and every other business rule live in the dashboard
backend; this service only ever turns audio bytes into numbers:

  POST /embed    — a single-speaker clip (an enrollment sample) -> one
                   embedding vector (list[float])
  POST /diarize  — a full meeting recording -> speaker-labeled time segments
                   + one embedding vector per detected speaker cluster
  GET  /health   — {"status": "ok", "gpu": true/false}

Both endpoints use pyannote.audio's speaker-diarization-3.1 pipeline with
return_embeddings=True (pyannote.audio >= 3.1), so a single model handles
diarization AND embedding extraction — no separate embedding model/license
needed.

──────────────────────────────────────────────────────────────────────────
Setup on ai-engine
──────────────────────────────────────────────────────────────────────────
1. Get a free Hugging Face account, then accept the user agreement on BOTH
   of these pages (pyannote's pipeline is gated and pulls in the second
   model as a dependency):
     https://huggingface.co/pyannote/speaker-diarization-3.1
     https://huggingface.co/pyannote/segmentation-3.0
   Create a read-only access token: https://huggingface.co/settings/tokens

2. python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   (torch: install the CUDA build matching this box's driver — reuse
   whatever torch/CUDA setup whisper-server.service already has if it's in
   a shared environment; otherwise follow the selector at
   https://pytorch.org/get-started/locally/ for this box's CUDA version)

3. export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
   uvicorn diarize_server:app --host 0.0.0.0 --port 9600

   First request will download the pipeline's weights (a few hundred MB,
   one-time, cached under ~/.cache/huggingface afterwards).

4. To run as a systemd service alongside whisper-server.service, see
   diarize-server.service in this same folder — copy it to
   /etc/systemd/system/, edit the paths/user, then:
     sudo systemctl daemon-reload
     sudo systemctl enable --now diarize-server

5. Sanity check from the dashboard-dev/prod server (or anywhere that can
   reach ai-engine):
     curl http://172.21.2.27:9600/health
"""
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
import torch
from pyannote.audio import Pipeline

HF_TOKEN = os.environ.get("HF_TOKEN", "")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN environment variable is required (Hugging Face access token — see setup notes above)")

app = FastAPI(title="CKDO Speaker Diarization Service")

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN)
        if torch.cuda.is_available():
            _pipeline.to(torch.device("cuda"))
    return _pipeline


def _save_temp(content: bytes, filename: str) -> str:
    ext = os.path.splitext(filename or "")[1] or ".wav"
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


@app.post("/embed")
async def embed(file: UploadFile = File(...)):
    """Single-speaker enrollment clip -> one embedding vector."""
    content = await file.read()
    path = _save_temp(content, file.filename or "clip.wav")
    try:
        pipeline = get_pipeline()
        diarization, embeddings = pipeline(path, return_embeddings=True)
        labels = list(diarization.labels())
        if not labels:
            raise HTTPException(422, "No speech detected in this clip")
        # Dominant cluster (most total speaking time) = the enrollment
        # subject — robust to a few seconds of leading/trailing silence or
        # a stray noise blip getting its own tiny cluster.
        durations = {label: diarization.label_duration(label) for label in labels}
        dominant = max(durations, key=durations.get)
        idx = labels.index(dominant)
        return {"embedding": embeddings[idx].tolist()}
    finally:
        os.remove(path)


@app.post("/diarize")
async def diarize(file: UploadFile = File(...)):
    """Full meeting audio -> speaker-labeled segments + one embedding per
    detected speaker cluster. The dashboard backend matches each cluster's
    embedding against its enrolled voiceprints to assign real names."""
    content = await file.read()
    path = _save_temp(content, file.filename or "meeting.wav")
    try:
        pipeline = get_pipeline()
        diarization, embeddings = pipeline(path, return_embeddings=True)
        labels = list(diarization.labels())
        segments = [
            {"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": label}
            for turn, _, label in diarization.itertracks(yield_label=True)
        ]
        speaker_embeddings = {label: embeddings[i].tolist() for i, label in enumerate(labels)}
        return {"segments": segments, "speaker_embeddings": speaker_embeddings}
    finally:
        os.remove(path)


@app.get("/health")
async def health():
    return {"status": "ok", "gpu": torch.cuda.is_available()}
