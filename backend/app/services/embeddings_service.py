"""
Embeddings Service — Voyage AI
Ported from sumber/chatbotai/embeddings.py.

Generates embeddings for RAG (Retrieval Augmented Generation) chatbot.
Kalau provider embedding diganti nanti, cukup ubah file ini saja —
rag_service.py dan ai_service.py tidak perlu berubah.
"""
import re
import voyageai
from app.config import get_settings

settings = get_settings()

EMBED_MODEL = "voyage-3"  # dimensi 1024, harus sama dengan kolom VECTOR(1024) di DB

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            _client = voyageai.Client(api_key=settings.voyage_api_key, timeout=5)
        except TypeError:
            _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


def embed_text(text: str, input_type: str = "document") -> list[float]:
    """input_type: 'document' saat menyimpan data, 'query' saat user bertanya."""
    result = _get_client().embed([text], model=EMBED_MODEL, input_type=input_type)
    return result.embeddings[0]


def embed_texts_batch(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed banyak teks sekaligus, lebih efisien untuk ingest dokumen."""
    result = _get_client().embed(texts, model=EMBED_MODEL, input_type=input_type)
    return result.embeddings


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
