"""
db.py
Koneksi ke Postgres + pgvector. Pisahkan dari logic embedding/query
supaya gampang ditempel ke dashboard utama (tinggal import).
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Buka koneksi baru ke database pgvector."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        dbname=os.getenv("DB_NAME", "rag_db"),
        user=os.getenv("DB_USER", "rag_user"),
        password=os.getenv("DB_PASSWORD"),
    )


def insert_document(source: str, title: str, content: str, embedding: list, metadata: dict = None):
    """Simpan satu chunk dokumen + embedding-nya ke database."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_documents (source, title, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (source, title, content, embedding, Json(metadata or {})),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


def search_similar(query_embedding: list, top_k: int = 5, source_filter: str = None):
    """
    Cari chunk dokumen paling mirip dengan query_embedding (cosine similarity).
    source_filter opsional, misal hanya cari di source='EBS_PO_MODULE'.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if source_filter:
                cur.execute(
                    """
                    SELECT id, source, title, content, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM company_documents
                    WHERE source = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_embedding, source_filter, query_embedding, top_k),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source, title, content, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM company_documents
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_embedding, query_embedding, top_k),
                )
            return cur.fetchall()
    finally:
        conn.close()
