"""
RAG Service — Retrieval Augmented Generation
Ported from sumber/chatbotai (db.py + query.py), adapted onto the shared
ckdo_dashboard Postgres database (extension `vector` via pgvector image).

Documents are tagged with a `department` (HR / Accounting / PAC / Purchasing / IT / General).
Retrieval is scoped to the asking user's department(s); IT/Admin see everything.

Flow: embed user question (local Ollama, nomic-embed-text) -> find similar
chunks (pgvector cosine similarity, filtered by allowed departments) -> build
context -> chat model answers grounded in company docs.
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from pgvector.psycopg2 import register_vector

from app.config import get_settings
from app.services import embeddings_service as emb

settings = get_settings()

DEPARTMENTS = ["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]


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
    """Create `vector` extension + company_documents table/columns if missing. Safe to call repeatedly."""
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
                department  TEXT NOT NULL DEFAULT 'General',
                metadata    JSONB DEFAULT '{}',
                embedding   VECTOR(768),
                created_by  TEXT,
                created_at  TIMESTAMPTZ DEFAULT now()
            )
        """)
        # Migrate existing table: add department column if it predates this change
        cur.execute("ALTER TABLE company_documents ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT 'General'")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_documents_embedding
                ON company_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_company_documents_source ON company_documents (source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_company_documents_department ON company_documents (department)")
        conn.commit()
        conn.close()
    except Exception:
        pass  # e.g. pgvector extension not available yet on first boot — chat falls back gracefully


# ── Document management (ingest) ──────────────────────────────────

def insert_document(source: str, title: str, content: str, embedding: list, created_by: str,
                     department: str = "General", metadata: dict = None) -> int:
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_documents (source, title, content, embedding, created_by, department, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (source, title, content, embedding, created_by, department, Json(metadata or {})),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


def ingest_text(source: str, title: str, text: str, created_by: str,
                department: str = "General", from_file: bool = False,
                file_name: str = None) -> list[int]:
    """Chunk + embed + store one document. Returns list of inserted chunk ids."""
    chunks = emb.chunk_text(text.strip())
    if not chunks:
        return []
    vectors = emb.embed_texts_batch(chunks, input_type="document")
    ids = []
    base_meta = {"from_file": from_file, "file_name": file_name or ""}
    for chunk, vec in zip(chunks, vectors):
        meta = {**base_meta, "length": len(chunk)}
        doc_id = insert_document(source, title, chunk, vec, created_by, department, meta)
        ids.append(doc_id)
    return ids


def list_documents() -> list[dict]:
    """List distinct documents (grouped by source+title) with chunk counts and origin info."""
    conn = _get_pg()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT source, title,
                       MAX(department)                                            AS department,
                       COUNT(*)                                                   AS chunks,
                       MIN(id)                                                    AS first_id,
                       MAX(created_at)                                            AS created_at,
                       MAX(created_by)                                            AS created_by,
                       BOOL_OR((metadata->>'from_file')::boolean)                AS from_file,
                       MAX(metadata->>'file_name')                               AS file_name
                FROM company_documents
                GROUP BY source, title
                ORDER BY MAX(created_at) DESC
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def delete_text_only_documents() -> int:
    """Delete all documents that were ingested from text-paste (not from a real file upload).
    Returns number of rows deleted."""
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM company_documents
                WHERE (metadata->>'from_file')::boolean IS NOT TRUE
            """)
            count = cur.rowcount
        conn.commit()
        return count
    finally:
        conn.close()


def delete_all_documents() -> int:
    """Delete ALL documents from the knowledge base. Returns rows deleted."""
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_documents")
            count = cur.rowcount
        conn.commit()
        return count
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

def search_similar(query_embedding: list, top_k: int = 5, department_filter: list[str] = None) -> list[dict]:
    """
    department_filter: list of allowed departments, or None/empty for no restriction (IT/Admin).
    """
    conn = _get_pg()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if department_filter:
                cur.execute(
                    """
                    SELECT id, source, title, content, department, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM company_documents
                    WHERE department = ANY(%s)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_embedding, department_filter, query_embedding, top_k),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source, title, content, department, metadata,
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
        parts.append(f"[Sumber: {r['source']} - {r['title']} ({r['department']}) | similarity={r['similarity']:.2f}]\n{r['content']}")
    return "\n\n---\n\n".join(parts)


def is_configured() -> bool:
    """RAG runs on the local Ollama server, which has a sensible default URL —
    it's 'configured' unconditionally now (there's no API key to check).
    If Ollama itself is unreachable, retrieve_context() fails closed anyway."""
    return bool(settings.ollama_api_url)


def departments_for_roles(roles: list[str], is_unrestricted: bool) -> list[str] | None:
    """
    Map a user's Keycloak roles to the list of document departments they may see.
    Returns None for unrestricted access (IT staff / admin — sees all departments).
    A user with multiple department roles sees the union of those departments,
    plus 'General' documents are always visible to everyone.
    """
    if is_unrestricted:
        return None
    role_to_dept = {
        "hr_staff": "HR",
        "accounting_staff": "Accounting",
        "pac_staff": "PAC",
        "purchasing_staff": "Purchasing",
    }
    depts = {role_to_dept[r] for r in roles if r in role_to_dept}
    depts.add("General")
    return list(depts)


def retrieve_context(question: str, department_filter: list[str] = None, top_k: int = 10, min_similarity: float = 0.25) -> dict:
    """
    Embed question + search similar chunks (scoped to department_filter). Returns
    {context, sources} or {context: None, sources: []} if RAG isn't configured,
    no relevant docs found, or nothing matches the user's allowed departments.
    Safe to call even if Ollama/pgvector aren't reachable — fails closed (no context).
    """
    if not is_configured():
        return {"context": None, "sources": []}
    try:
        query_embedding = emb.embed_text(question, input_type="query")
        results = search_similar(query_embedding, top_k=top_k, department_filter=department_filter)
        results = [r for r in results if r["similarity"] >= min_similarity]
        if not results:
            return {"context": None, "sources": []}
        return {
            "context": build_context(results),
            "sources": [
                {"id": r["id"], "source": r["source"], "title": r["title"], "department": r["department"], "similarity": round(r["similarity"], 3)}
                for r in results
            ],
        }
    except Exception:
        return {"context": None, "sources": []}
