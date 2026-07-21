"""
Embeddings Service — local Ollama (nomic-embed-text)

Generates embeddings for RAG (Retrieval Augmented Generation) chatbot.
Runs on the local "ai-engine" Ollama server (172.21.2.27) instead of the
paid Voyage AI API — see sumber/AI_Chat_Implementation_Guide.md.
Kalau provider embedding diganti lagi nanti, cukup ubah file ini saja —
rag_service.py dan ai_service.py tidak perlu berubah.
"""
import re
import httpx
from app.config import get_settings

settings = get_settings()

EMBED_MODEL = "nomic-embed-text"  # dimensi 768, harus sama dengan kolom VECTOR(768) di DB
EMBED_TIMEOUT_SECONDS = 30.0

# nomic-embed-text is an asymmetric embedding model — the doc it stores and the
# query that searches for it need different task prefixes for retrieval to
# actually work well (per Nomic's model card), mirroring Voyage's old
# input_type param.
_TASK_PREFIX = {"document": "search_document: ", "query": "search_query: "}


def embed_text(text: str, input_type: str = "document") -> list[float]:
    """input_type: 'document' saat menyimpan data, 'query' saat user bertanya."""
    return embed_texts_batch([text], input_type=input_type)[0]


def embed_texts_batch(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed banyak teks sekaligus, lebih efisien untuk ingest dokumen."""
    prefix = _TASK_PREFIX.get(input_type, "")
    with httpx.Client(base_url=settings.ollama_api_url.rstrip("/"), timeout=EMBED_TIMEOUT_SECONDS) as client:
        resp = client.post("/api/embed", json={"model": EMBED_MODEL, "input": [f"{prefix}{t}" for t in texts]})
        resp.raise_for_status()
        return resp.json()["embeddings"]


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    """
    Paragraph-aware chunking — respects semantic boundaries so tables and
    structured lists don't get split mid-row.

    Strategy:
    1. Split on blank lines to get paragraphs / table blocks.
    2. Merge adjacent short paragraphs up to chunk_size.
    3. Overlap: carry the last paragraph(s) into the next chunk for continuity.
    4. Single paragraphs longer than chunk_size are split on sentence boundaries.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

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
