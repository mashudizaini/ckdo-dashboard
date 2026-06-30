"""
Embeddings Service — Voyage AI
Ported from sumber/chatbotai/embeddings.py.

Generates embeddings for RAG (Retrieval Augmented Generation) chatbot.
Kalau provider embedding diganti nanti, cukup ubah file ini saja —
rag_service.py dan ai_service.py tidak perlu berubah.
"""
import voyageai
from app.config import get_settings

settings = get_settings()

EMBED_MODEL = "voyage-3"  # dimensi 1024, harus sama dengan kolom VECTOR(1024) di DB

_client = None


def _get_client():
    global _client
    if _client is None:
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


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Pecah teks panjang jadi potongan kecil sebelum di-embed."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]
