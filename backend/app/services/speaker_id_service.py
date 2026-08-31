"""
Speaker Identification Service
─────────────────────────────────────────
Talks to the diarization microservice on ai-engine (172.21.2.27:9600, see
ai-engine-services/diarization/) — that service is pure ML inference only
(audio bytes in, embeddings/segments out). Everything that actually knows
about people — enrolled voiceprints, name-matching, merging speaker labels
onto a transcript — lives here, same split as Whisper (ai-engine transcribes,
this backend owns everything else).

Matching is simple nearest-neighbour cosine similarity against every
enrolled SpeakerVoiceprint, with a floor (MATCH_THRESHOLD) below which a
cluster is left as "Unknown speaker" rather than guessing wrong — a rushed
guess is worse than an honest "don't know" for a document meant to record
who said what.
"""
import math
import httpx
from app.config import get_settings

settings = get_settings()


class SpeakerIdError(Exception):
    pass


# Cosine similarity below this is treated as "not a match" — chosen
# conservatively (typical same-speaker pyannote embeddings score 0.85+,
# different speakers usually well under 0.6) so a stranger's voice doesn't
# get silently mislabeled as one of the enrolled 7.
MATCH_THRESHOLD = 0.75


async def embed_clip(content: bytes, filename: str) -> list[float]:
    """Single-speaker enrollment clip -> one embedding vector."""
    url = f"{settings.diarization_api_url.rstrip('/')}/embed"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(url, files={"file": (filename, content)})
            resp.raise_for_status()
            return resp.json()["embedding"]
    except httpx.TimeoutException as e:
        raise SpeakerIdError("Diarization service timed out while embedding the clip") from e
    except httpx.ConnectError as e:
        raise SpeakerIdError(
            f"Cannot reach the diarization service ({settings.diarization_api_url}) — is it running?"
        ) from e
    except httpx.HTTPStatusError as e:
        raise SpeakerIdError(f"Diarization service error: {e.response.text[:300]}") from e


async def diarize_audio(content: bytes, filename: str) -> dict:
    """Full meeting audio -> {"segments": [{start, end, speaker}, ...],
    "speaker_embeddings": {"SPEAKER_00": [...], ...}}."""
    url = f"{settings.diarization_api_url.rstrip('/')}/diarize"
    try:
        # Long timeout — even at GPU speed a 1-2h meeting's diarization pass
        # takes real time, and unlike transcription there's no progress
        # callback to poll here (single request/response).
        async with httpx.AsyncClient(timeout=1800) as client:
            resp = await client.post(url, files={"file": (filename, content)})
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException as e:
        raise SpeakerIdError("Diarization service timed out processing this recording") from e
    except httpx.ConnectError as e:
        raise SpeakerIdError(
            f"Cannot reach the diarization service ({settings.diarization_api_url}) — is it running?"
        ) from e
    except httpx.HTTPStatusError as e:
        raise SpeakerIdError(f"Diarization service error: {e.response.text[:300]}") from e


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def match_speakers(speaker_embeddings: dict, voiceprints: list) -> dict:
    """speaker_embeddings: {"SPEAKER_00": [...], ...} from diarize_audio().
    voiceprints: list of SpeakerVoiceprint rows.
    Returns {"SPEAKER_00": "Mashudi", "SPEAKER_01": "Unknown speaker (SPEAKER_01)", ...}."""
    result = {}
    for cluster_label, emb in speaker_embeddings.items():
        best_name, best_score = None, -1.0
        for vp in voiceprints:
            score = cosine_similarity(emb, vp.embedding)
            if score > best_score:
                best_name, best_score = vp.name, score
        result[cluster_label] = best_name if best_score >= MATCH_THRESHOLD else f"Unknown speaker ({cluster_label})"
    return result


def merge_transcript_with_speakers(transcript_segments: list, diarization_segments: list, speaker_names: dict) -> list:
    """Assigns each Whisper transcript segment ({start, end, text}) the
    speaker whose diarized turn overlaps it the most in time. A segment with
    no overlapping diarization turn at all (silence-gap edge case) is left
    unattributed rather than guessing."""
    merged = []
    for seg in transcript_segments:
        seg_start, seg_end = seg["start"], seg["end"]
        best_label, best_overlap = None, 0.0
        for d in diarization_segments:
            overlap = min(seg_end, d["end"]) - max(seg_start, d["start"])
            if overlap > best_overlap:
                best_overlap, best_label = overlap, d["speaker"]
        speaker = speaker_names.get(best_label, "Unknown speaker") if best_label else "Unknown speaker"
        merged.append({"start": seg_start, "end": seg_end, "text": seg.get("text", ""), "speaker": speaker})
    return merged
