"""
Embeddings Service — local Ollama (bge-m3)

Generates embeddings for RAG (Retrieval Augmented Generation) chatbot.
Runs on the local "ai-engine" Ollama server (172.21.2.27) instead of the
paid Voyage AI API — see sumber/AI_Chat_Implementation_Guide.md.
Kalau provider embedding diganti lagi nanti, cukup ubah file ini saja —
rag_service.py dan ai_service.py tidak perlu berubah.

Migrated 2026-07 from nomic-embed-text (768-dim) to bge-m3 (1024-dim) —
validated empirically on a real retrieval failure case (a scanned-PDF table
buried at rank #228 under nomic-embed-text came back at rank #1 under
bge-m3 for the same query). EMBED_DIM must match the DB's
`VECTOR(...)` column — changing EMBED_MODEL to a model with a different
output dimension requires re-embedding every existing row (see
rag_service.reembed_all_documents / the one-off migration this shipped with).
"""
import re
import httpx
from app.config import get_settings

settings = get_settings()

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024
EMBED_TIMEOUT_SECONDS = 30.0

# bge-m3 (unlike nomic-embed-text) doesn't need asymmetric task prefixes for
# query vs. document text — validated empirically (plain, unprefixed text
# correctly ranked the right chunk #1 in a real retrieval test). input_type
# is kept as a parameter for interface compatibility with callers/any future
# model swap that does need it, it's just a no-op for bge-m3.


def embed_text(text: str, input_type: str = "document") -> list[float]:
    """input_type: 'document' saat menyimpan data, 'query' saat user bertanya."""
    return embed_texts_batch([text], input_type=input_type)[0]


def embed_texts_batch(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed banyak teks sekaligus, lebih efisien untuk ingest dokumen."""
    with httpx.Client(base_url=settings.ollama_api_url.rstrip("/"), timeout=EMBED_TIMEOUT_SECONDS) as client:
        resp = client.post("/api/embed", json={"model": EMBED_MODEL, "input": texts})
        resp.raise_for_status()
        return resp.json()["embeddings"]


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120, line_aware: bool = False) -> list[str]:
    """
    Paragraph-aware chunking — respects semantic boundaries so tables and
    structured lists don't get split mid-row.

    Strategy:
    1. Split on blank lines to get paragraphs / table blocks.
    2. Merge adjacent short paragraphs up to chunk_size.
    3. Overlap: carry the last paragraph(s) into the next chunk for continuity.
    4. Single paragraphs longer than chunk_size are split on sentence boundaries.

    line_aware: for OCR'd scanned pages, Tesseract emits one table cell/word
    per line with NO blank line between them (it isn't real prose), so the
    default blank-line split sees an entire page as a single unsplittable
    "paragraph" and falls through to sentence-splitting — which does nothing
    useful on table fragments that have no sentence punctuation, and ends up
    cutting a table apart at an arbitrary point instead of keeping row
    labels next to their values. When True, every non-empty line is treated
    as its own mergeable unit so short table lines actually get grouped
    together up to chunk_size via the normal merge logic below.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if line_aware:
        paragraphs = [p.strip() for p in text.split("\n")]
    else:
        # Split into semantic blocks (double newline or more)
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text)]
    paragraphs = [p for p in paragraphs if p]

    chunks: list[str] = []
    current: list[str] = []
    current_len: int   = 0

    def flush(carry_overlap: bool = True):
        nonlocal current, current_len
        if not current:
            return
        chunks.append("\n\n".join(current))
        if carry_overlap:
            # Carry last paragraph(s) into next chunk (up to overlap chars)
            tail: list[str] = []
            tail_len = 0
            for p in reversed(current):
                if tail_len + len(p) + 2 <= overlap:
                    tail.insert(0, p)
                    tail_len += len(p) + 2
                else:
                    break
            current    = tail
            current_len = tail_len
        else:
            current    = []
            current_len = 0

    for para in paragraphs:
        para_len = len(para)

        if para_len > chunk_size:
            # Flush what we have, then split oversized paragraph by sentences
            flush(carry_overlap=False)
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sub: list[str] = []
            sub_len = 0
            for sent in sentences:
                if sub_len + len(sent) + 1 > chunk_size and sub:
                    chunks.append(" ".join(sub))
                    sub     = [sent]
                    sub_len = len(sent)
                else:
                    sub.append(sent)
                    sub_len += len(sent) + 1
            if sub:
                current    = [" ".join(sub)]
                current_len = sub_len
            continue

        if current_len + para_len + 2 > chunk_size and current:
            flush(carry_overlap=True)

        current.append(para)
        current_len += para_len + 2

    flush(carry_overlap=False)
    return [c for c in chunks if c.strip()]
