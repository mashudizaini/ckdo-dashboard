"""
embeddings.py
Generate embedding pakai Voyage AI (direkomendasikan Anthropic untuk RAG,
kualitasnya lebih baik dari embedding generik untuk dipasangkan dengan Claude).

Kalau Hudi nanti mau ganti provider embedding (misal OpenAI atau model lokal),
cukup ubah file ini saja -- bagian lain (db.py, query.py) tidak perlu berubah.
"""

import os
import voyageai
from dotenv import load_dotenv

load_dotenv()

client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

EMBED_MODEL = "voyage-3"  # dimensi 1024, samakan dengan init.sql VECTOR(1024)


def embed_text(text: str, input_type: str = "document") -> list:
    """
    input_type: 'document' saat menyimpan data, 'query' saat user bertanya.
    Voyage membedakan dua mode ini untuk hasil retrieval yang lebih akurat.
    """
    result = client.embed([text], model=EMBED_MODEL, input_type=input_type)
    return result.embeddings[0]


def embed_texts_batch(texts: list, input_type: str = "document") -> list:
    """Embed banyak teks sekaligus, lebih efisien untuk proses ingest data."""
    result = client.embed(texts, model=EMBED_MODEL, input_type=input_type)
    return result.embeddings


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """
    Pecah teks panjang jadi potongan kecil sebelum di-embed.
    chunk_size dan overlap dalam karakter -- sesuaikan kalau dokumennya
    berupa tabel/SOP yang butuh konteks lebih utuh.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks
