"""
RAG Service — Retrieval Augmented Generation
Ported from sumber/chatbotai (db.py + query.py), adapted onto the shared
ckdo_dashboard Postgres database (extension `vector` via pgvector image).

Flow: embed user question (Voyage) -> find similar chunks (pgvector cosine
similarity) -> build context -> Claude answers grounded in company docs.
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from pgvector.psycopg2 import register_vector

from app.config import get_settings
from app.services import embeddings_service as emb

settings = get_settings()


def _get_pg():
    url = settings.database_url
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise RuntimeError(f"Cannot parse DATABASE_URL: {url}")
    conn = psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                             user=m.group(1), password=m.group(2))
    try:
        register_vector(conn)
    except Exception:
        pass  # extension not ready yet — ensure_schema() will create it
    return conn


def ensure_schema():
    """Create `vector` extension + company_documents table if missing. Safe to call repeatedly."""
    try:
        m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
        conn = psycopg2.connect(host=m.group(3), port=int(m.group(4)), dbname=m.group(5),
                                 user=m.group(1), password=m.group(2))
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS company_documents (
                id          BIGSERIAL PRIMARY KEY,
                source      TEXT NOT NULL,
                title       TEXT,
                content     TEXT NOT NULL,
                metadata    JSONB DEFAULT '{}',
                embedding   VECTOR(1024),
                created_by  TEXT,
                created_at  TIMESTAMPTZ DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_documents_embedding
                ON company_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_company_documents_source ON company_documents (source)")
        conn.commit()
        conn.close()
    except Exception:
        pass  # e.g. pgvector extension not available yet on first boot — chat falls back gracefully


# ── Document management (ingest) ──────────────────────────────────

def insert_document(source: str, title: str, content: str, embedding: list, created_by: str, metadata: dict = None) -> int:
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_documents (source, title, content, embedding, created_by, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (source, title, content, embedding, created_by, Json(metadata or {})),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


def ingest_text(source: str, title: str, text: str, created_by: str) -> list[int]:
    """Chunk + embed + store one document. Returns list of inserted chunk ids."""
    chunks = emb.chunk_text(text.strip())
    if not chunks:
        return []
    vectors = emb.embed_texts_batch(chunks, input_type="document")
    ids = []
    for chunk, vec in zip(chunks, vectors):
        doc_id = insert_document(source, title, chunk, vec, created_by, {"length": len(chunk)})
        ids.append(doc_id)
    return ids


def list_documents() -> list[dict]:
    """List distinct documents (grouped by source+title) with chunk counts."""
    conn = _get_pg()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT source, title, COUNT(*) AS chunks,
                       MIN(id) AS first_id, MAX(created_at) AS created_at, MAX(created_by) AS created_by
                FROM company_documents
                GROUP BY source, title
                ORDER BY MAX(created_at) DESC
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def delete_document(source: str, title: str):
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_documents WHERE source = %s AND title = %s", (source, title))
        conn.commit()
    finally:
        conn.close()


# ── Retrieval + RAG answer ────────────────────────────────────────

def search_similar(query_embedding: list, top_k: int = 5, source_filter: str = None) -> list[dict]:
    conn = _get_pg()
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
                    LIMIT %s
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
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, top_k),
                )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def build_context(search_results: list[dict]) -> str:
    parts = []
    for r in search_results:
        parts.append(f"[Sumber: {r['source']} - {r['title']} | similarity={r['similarity']:.2f}]\n{r['content']}")
    return "\n\n---\n\n".join(parts)


def is_configured() -> bool:
    return bool(settings.voyage_api_key)


def retrieve_context(question: str, top_k: int = 5, min_similarity: float = 0.3) -> dict:
    """
    Embed question + search similar chunks. Returns {context, sources} or
    {context: None, sources: []} if RAG isn't configured / no relevant docs found.
    Safe to call even if Voyage/pgvector aren't set up — fails closed (no context).
    """
    if not is_configured():
        return {"context": None, "sources": []}
    try:
        query_embedding = emb.embed_text(question, input_type="query")
        results = search_similar(query_embedding, top_k=top_k)
        results = [r for r in results if r["similarity"] >= min_similarity]
        if not results:
            return {"context": None, "sources": []}
        return {
            "context": build_context(results),
            "sources": [
                {"id": r["id"], "source": r["source"], "title": r["title"], "similarity": round(r["similarity"], 3)}
                for r in results
            ],
        }
    except Exception:
        return {"context": None, "sources": []}
