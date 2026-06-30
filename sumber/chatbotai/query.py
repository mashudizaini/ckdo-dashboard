"""
query.py
Fungsi utama RAG: terima pertanyaan user -> cari konteks relevan di pgvector
-> kirim ke Claude API -> kembalikan jawaban.

Fungsi ask_chatbot() ini yang nanti dipanggil dari dashboard utama
(misal di endpoint Flask/FastAPI yang sudah ada).
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

from embeddings import embed_text
from db import search_similar

load_dotenv()

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Kamu adalah asisten internal perusahaan CKD OTTO Pharmaceuticals.
Jawab pertanyaan HANYA berdasarkan konteks dokumen yang diberikan di bawah.
Jika informasi tidak ada di konteks, katakan dengan jujur bahwa kamu tidak
menemukan informasinya di dokumen perusahaan, jangan mengarang jawaban.
Jawab dalam Bahasa Indonesia, singkat dan jelas."""


def build_context(search_results) -> str:
    """Gabungkan hasil retrieval jadi satu blok konteks untuk prompt."""
    parts = []
    for r in search_results:
        parts.append(
            f"[Sumber: {r['source']} - {r['title']} | similarity={r['similarity']:.2f}]\n{r['content']}"
        )
    return "\n\n---\n\n".join(parts)


def ask_chatbot(user_question: str, top_k: int = 5, source_filter: str = None) -> dict:
    """
    Alur RAG lengkap:
    1. Embed pertanyaan user
    2. Cari chunk paling relevan di pgvector
    3. Kirim konteks + pertanyaan ke Claude
    4. Return jawaban beserta sumber yang dipakai (untuk transparansi/audit)
    """
    query_embedding = embed_text(user_question, input_type="query")
    results = search_similar(query_embedding, top_k=top_k, source_filter=source_filter)

    if not results:
        return {
            "answer": "Maaf, saya tidak menemukan dokumen relevan untuk pertanyaan ini.",
            "sources": [],
        }

    context = build_context(results)

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Konteks dokumen:\n\n{context}\n\nPertanyaan: {user_question}",
            }
        ],
    )

    answer_text = "".join(
        block.text for block in response.content if block.type == "text"
    )

    return {
        "answer": answer_text,
        "sources": [
            {"id": r["id"], "source": r["source"], "title": r["title"], "similarity": round(r["similarity"], 3)}
            for r in results
        ],
    }


if __name__ == "__main__":
    # Contoh pemakaian langsung dari terminal
    question = "Bagaimana cara mengajukan PR di Oracle EBS?"
    result = ask_chatbot(question)
    print("\nJawaban:\n", result["answer"])
    print("\nSumber:\n", result["sources"])
