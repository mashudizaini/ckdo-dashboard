"""
ingest.py
Contoh script untuk memasukkan dokumen perusahaan ke pgvector.
Jalankan: python ingest.py

Ganti bagian `documents = [...]` dengan loop pembacaan file asli
(misal hasil extract dari Oracle EBS, SOP PDF, atau knowledge base helpdesk).
"""

from embeddings import embed_texts_batch, chunk_text
from db import insert_document

# Contoh data -- nanti diganti sumber data perusahaan beneran
documents = [
    {
        "source": "SOP_FINANCE",
        "title": "Prosedur Pengajuan PR di Oracle EBS",
        "content": """
        Pengajuan Purchase Requisition (PR) di Oracle EBS dilakukan melalui modul
        Purchasing. User membuat PR baru, mengisi item, quantity, dan kode anggaran.
        Setelah submit, PR akan masuk ke approval workflow sesuai hierarki jabatan.
        Approver dapat melihat status approval melalui Notification Worklist.
        """,
    },
    {
        "source": "helpdesk_kb",
        "title": "Troubleshooting akses helpdesk.ckd-otto.com",
        "content": """
        Jika helpdesk.ckd-otto.com tidak bisa diakses meskipun DNS sudah benar,
        periksa konfigurasi Nginx, pastikan server_name sudah diisi sesuai domain.
        Tanpa server_name yang benar, Nginx tidak akan merutekan request meskipun
        FortiGate dan DNS sudah dikonfigurasi dengan benar.
        """,
    },
]


def main():
    for doc in documents:
        chunks = chunk_text(doc["content"].strip())
        embeddings = embed_texts_batch(chunks, input_type="document")

        for chunk, emb in zip(chunks, embeddings):
            doc_id = insert_document(
                source=doc["source"],
                title=doc["title"],
                content=chunk,
                embedding=emb,
                metadata={"length": len(chunk)},
            )
            print(f"Tersimpan id={doc_id} | source={doc['source']} | title={doc['title']}")


if __name__ == "__main__":
    main()
