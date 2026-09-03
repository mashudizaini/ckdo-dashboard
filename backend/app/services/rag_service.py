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
from urllib.parse import urlsplit, unquote
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from pgvector.psycopg2 import register_vector

from app.config import get_settings
from app.services import embeddings_service as emb
import structlog

logger = structlog.get_logger()
settings = get_settings()

DEPARTMENTS = ["General", "HR", "Accounting", "PAC", "Purchasing", "IT"]


def _pg_connect_kwargs() -> dict:
    """Parse DATABASE_URL into psycopg2 connect() kwargs. Handles any
    'postgresql[+driver]://' scheme (e.g. plain, +asyncpg, +psycopg2) since
    different environments' .env files have used different variants —
    a scheme-literal regex silently broke on '+asyncpg' and made RAG's
    schema/table never get created there."""
    parts = urlsplit(settings.database_url)
    if not parts.hostname or not parts.path.lstrip("/"):
        raise RuntimeError(f"Cannot parse DATABASE_URL (scheme={parts.scheme!r})")
    return {
        "host": parts.hostname,
        "port": parts.port or 5432,
        "dbname": parts.path.lstrip("/"),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
    }


def _get_pg():
    conn = psycopg2.connect(**_pg_connect_kwargs())
    try:
        register_vector(conn)
    except Exception:
        pass  # extension not ready yet — ensure_schema() will create it
    return conn


def ensure_schema():
    """Create `vector` extension + company_documents table/columns if missing. Safe to call repeatedly."""
    try:
        conn = psycopg2.connect(**_pg_connect_kwargs())
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS company_documents (
                id          BIGSERIAL PRIMARY KEY,
                source      TEXT NOT NULL,
                title       TEXT,
                content     TEXT NOT NULL,
                department  TEXT NOT NULL DEFAULT 'General',
                metadata    JSONB DEFAULT '{{}}',
                embedding   VECTOR({emb.EMBED_DIM}),
                created_by  TEXT,
                created_at  TIMESTAMPTZ DEFAULT now()
            )
        """)
        # Migrate existing table: add department column if it predates this change
        cur.execute("ALTER TABLE company_documents ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT 'General'")

        # Migrate existing table if its embedding column's dimension doesn't
        # match the currently configured model (e.g. after switching
        # EMBED_MODEL to one with a different output size, like the
        # nomic-embed-text[768] -> bge-m3[1024] migration this shipped with).
        # pgvector requires one fixed dimension per column, so old vectors
        # must be cleared before the column can be widened/narrowed — the
        # actual re-embedding is a separate, explicit one-off step (see
        # reembed_all_documents), not run automatically here.
        cur.execute("""
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'company_documents'::regclass AND attname = 'embedding'
        """)
        row = cur.fetchone()
        current_dim = row[0] if row else None
        if current_dim is not None and current_dim != emb.EMBED_DIM:
            logger.warning(
                "rag_embedding_dimension_mismatch_migrating",
                current_dim=current_dim, target_dim=emb.EMBED_DIM,
            )
            cur.execute("DROP INDEX IF EXISTS idx_company_documents_embedding")
            cur.execute("UPDATE company_documents SET embedding = NULL")
            cur.execute(f"ALTER TABLE company_documents ALTER COLUMN embedding TYPE VECTOR({emb.EMBED_DIM})")

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


def reembed_all_documents(batch_size: int = 20) -> dict:
    """
    One-off migration helper — re-computes embeddings for every existing
    row using the currently configured EMBED_MODEL (e.g. after
    ensure_schema() cleared them due to a dimension change). Safe to call
    multiple times: only touches rows where embedding IS NULL, so an
    interrupted run can just be re-invoked to pick up where it left off.
    Returns {"total": int, "updated": int}.
    """
    conn = _get_pg()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, content FROM company_documents WHERE embedding IS NULL ORDER BY id")
            rows = cur.fetchall()

        updated = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            vectors = emb.embed_texts_batch([r["content"] for r in batch], input_type="document")
            with conn.cursor() as cur:
                for row, vec in zip(batch, vectors):
                    cur.execute("UPDATE company_documents SET embedding = %s WHERE id = %s", (vec, row["id"]))
            conn.commit()
            updated += len(batch)
            logger.info("rag_reembed_progress", updated=updated, total=len(rows))

        return {"total": len(rows), "updated": updated}
    finally:
        conn.close()


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
                file_name: str = None, chunk_size: int = 700, overlap: int = 120,
                line_aware: bool = False) -> list[int]:
    """Chunk + embed + store one document. Returns list of inserted chunk ids.
    chunk_size/overlap/line_aware: callers ingesting OCR'd scanned PDFs should
    pass a larger chunk_size and line_aware=True — see chunk_text()'s
    line_aware docstring for why OCR output needs different boundary handling
    than real prose."""
    chunks = emb.chunk_text(text.strip(), chunk_size=chunk_size, overlap=overlap, line_aware=line_aware)
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


def get_document_content(source: str, title: str) -> str | None:
    """Concatenate all chunks of a document (in original chunk order) back into
    one text blob — used by the Document Converter's 'reopen for editing' flow
    so an already-ingested document can be loaded back into the editor."""
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM company_documents WHERE source = %s AND title = %s ORDER BY id", (source, title))
            rows = cur.fetchall()
            if not rows:
                return None
            return "\n\n".join(r[0] for r in rows)
    finally:
        conn.close()


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


def delete_document(source: str, title: str) -> int:
    """Delete a document by (source, title). Returns rows deleted — the
    caller should treat 0 as a failure (mismatched source/title) rather
    than silently reporting success, since a document that "fails" to
    delete this way still answers queries afterward with no visible sign
    anything went wrong."""
    conn = _get_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_documents WHERE source = %s AND title = %s", (source, title))
            count = cur.rowcount
        conn.commit()
        return count
    finally:
        conn.close()


# ── Retrieval + RAG answer ────────────────────────────────────────

# Sentinel tsquery for a question with no extractable (non-stopword) words
# — matches nothing real, so the keyword pool is simply empty and results
# fall back to pure vector similarity, without needing a whole separate
# query path just for that edge case.
_NO_KEYWORD_SENTINEL = "zzz_no_keyword_match_zzz"

# Common Indonesian/English connector words — excluded from the keyword
# query. Root-caused empirically: "hadiah apa yang di dapat bagi karyawan
# terbaik" (asking about the Best Employee reward) failed to rescue the
# one chunk that actually had the reward amount, because the OR-joined
# query included "yang"/"di"/"dapat"/"bagi"/"apa" — words common enough to
# appear throughout most of the knowledge base — so the keyword-rank
# ordering (used to pick the top candidates for rescue, see search_similar)
# got dominated by chunks that happened to repeat those filler words most,
# crowding out the chunk that actually matched the distinctive terms
# ("karyawan", "terbaik"). Not exhaustive by design — just common enough
# words that they carry ~no topical signal on their own.
_STOPWORDS = {
    "yang", "di", "ke", "dari", "dan", "atau", "untuk", "dengan", "pada",
    "adalah", "akan", "ini", "itu", "apa", "apakah", "bagaimana", "dapat",
    "bisa", "bagi", "oleh", "dalam", "atas", "karena", "jika", "tidak",
    "juga", "saja", "saya", "anda", "kami", "kita", "mereka", "ada",
    "sudah", "belum", "harus", "wajib", "sebagai", "secara", "para",
    "seperti", "maka", "namun", "tetapi", "jadi", "yaitu", "serta",
    "the", "is", "a", "an", "of", "to", "for", "and", "or", "in", "on",
    "at", "by", "with", "this", "that", "what", "how", "does", "do",
    "can", "will", "are", "was", "were", "be", "been", "as", "it", "its",
}


def _keyword_tsquery(question: str) -> str:
    """OR-joined (not AND) tsquery built from the question's meaningful
    (non-stopword) words, so a chunk containing even ONE matching word
    gets a shot at rescue — plainto_tsquery's default AND-all-words
    behavior would score a chunk 0 unless it happened to contain every
    single word in the question, which defeats the purpose for exactly the
    case this exists to catch. 'simple' text-search config (no stemming)
    is used rather than 'english', since this KB's content is a bilingual
    English/Indonesian mix and Postgres has no built-in Indonesian config
    — plain tokenization/lowercasing still catches exact-term overlaps
    like "masuk" without risking wrong stemming assumptions in either
    language. Only \\w+ tokens are used, so no tsquery syntax characters
    can leak in from user input."""
    words = [w for w in re.findall(r"\w+", question.lower()) if w not in _STOPWORDS and len(w) > 1]
    return " | ".join(words) if words else _NO_KEYWORD_SENTINEL


def search_similar(query_embedding: list, question: str = "", top_k: int = 5, department_filter: list[str] = None, per_doc_cap: int = 4) -> list[dict]:
    """
    department_filter: list of allowed departments, or None/empty for no restriction (IT/Admin).

    question: original question text — used for a keyword/full-text
    *rescue*, not a blended score. Root-caused why it has to work this way,
    not as a weighted average: a chunk can be the single most relevant one
    for a question (e.g. the exact reward-amount table for "hadiah apa yang
    didapat karyawan terbaik") while barely containing any of the
    question's literal words itself — it inherits its topic from earlier
    chunks in the same document (headings, intro) rather than repeating
    "karyawan"/"terbaik" in its own text. A blended score (tried first,
    replaced after finding this case) let a low keyword component drag a
    chunk ranked #9 by pure vector similarity in a 418-chunk KB down past
    the top-30 cutoff entirely. So: keyword match can only ADD a chunk to
    the candidate pool (rescuing one that scored well on exact terms even
    if vector similarity alone ranked it lower — the original "uang masuk"
    vs "biaya masuk" motivation), never used to demote one already ranked
    well by vector similarity. Final ordering is by vector similarity only.

    per_doc_cap: max candidate chunks any single (source, title) document may
    contribute to the pool BEFORE the final top_k cut. Without this, a large
    document (e.g. a 200+ chunk company-wide regulation) can flood every
    slot in a plain top-k similarity search purely by chunk-count — its many
    chunks all scoring "pretty relevant" can out-rank a small, specific
    document's one genuinely-best chunk, even when that chunk is the actual
    answer. Root-caused on a real case: a 12-chunk scholarship-allowance memo
    never reached the local model's 16-chunk context window because a
    211-chunk general regulation document dominated the ranking, even though
    the allowance memo's table chunk was a near-exact match for the question.
    Capping candidates per document first guarantees every document gets a
    fair shot at its best chunk being seen. A keyword-rescued chunk (below)
    is exempt from this cap, on the same reasoning as the top_k cap itself
    doesn't apply to it: it wouldn't have made the per-document vector cut
    either, and rescue can't do its job if it's still filtered right back out.
    """
    tsquery = _keyword_tsquery(question)
    keyword_pool_limit = max(top_k, 20)
    conn = _get_pg()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if department_filter:
                cur.execute(
                    """
                    WITH vector_pool AS (
                        SELECT id, source, title, content, department, metadata,
                               1 - (embedding <=> %s::vector) AS similarity,
                               ROW_NUMBER() OVER (PARTITION BY source, title ORDER BY embedding <=> %s::vector) AS doc_rank
                        FROM company_documents
                        WHERE department = ANY(%s)
                    ),
                    keyword_pool AS (
                        SELECT id
                        FROM company_documents
                        WHERE department = ANY(%s)
                          AND to_tsvector('simple', content) @@ to_tsquery('simple', %s)
                        ORDER BY ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', %s), 32) DESC
                        LIMIT %s
                    )
                    SELECT id, source, title, content, department, metadata, similarity
                    FROM vector_pool
                    WHERE doc_rank <= %s OR id IN (SELECT id FROM keyword_pool)
                    ORDER BY similarity DESC
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, department_filter,
                     department_filter, tsquery, tsquery, keyword_pool_limit,
                     per_doc_cap, top_k),
                )
            else:
                cur.execute(
                    """
                    WITH vector_pool AS (
                        SELECT id, source, title, content, department, metadata,
                               1 - (embedding <=> %s::vector) AS similarity,
                               ROW_NUMBER() OVER (PARTITION BY source, title ORDER BY embedding <=> %s::vector) AS doc_rank
                        FROM company_documents
                    ),
                    keyword_pool AS (
                        SELECT id
                        FROM company_documents
                        WHERE to_tsvector('simple', content) @@ to_tsquery('simple', %s)
                        ORDER BY ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', %s), 32) DESC
                        LIMIT %s
                    )
                    SELECT id, source, title, content, department, metadata, similarity
                    FROM vector_pool
                    WHERE doc_rank <= %s OR id IN (SELECT id FROM keyword_pool)
                    ORDER BY similarity DESC
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, tsquery, tsquery,
                     keyword_pool_limit, per_doc_cap, top_k),
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


def retrieve_context(question: str, department_filter: list[str] = None, top_k: int = 30,
                      min_similarity: float = 0.15, context_k: int = None) -> dict:
    """
    Embed question + search similar chunks (scoped to department_filter). Returns
    {context, sources} or {context: None, sources: []} if RAG isn't configured,
    no relevant docs found, or nothing matches the user's allowed departments.
    Safe to call even if Ollama/pgvector aren't reachable — fails closed (no context).

    top_k vs. context_k: top_k controls how many candidates are FETCHED from the
    DB (broad, for recall — a correct chunk can legitimately rank in the teens
    or twenties against a large multi-document KB). context_k controls how many
    of those actually get formatted into the prompt (defaults to top_k, i.e. no
    truncation). These need to differ per chat model: validated empirically that
    the on-premise qwen2.5:14b model answers correctly with 16 sources in context
    but starts failing (or outright hallucinating a wrong number from an unrelated
    chunk) at 18+ — classic "lost in the middle" context overload for a smaller
    model — while Gemini handles the full top_k=30 correctly. Callers should pass
    a smaller context_k for local-model providers.

    The top_k FETCH itself is per-document-capped (see search_similar's
    per_doc_cap) before this global top_k cut, so a single large document
    can't monopolize the candidate pool purely by chunk count — a small,
    specific document's best-matching chunk still gets a fair shot even
    against a much bigger document in the same knowledge base. Ranking
    within that pool blends vector similarity with a keyword/full-text
    signal (see search_similar's KEYWORD_MATCH_WEIGHT), so a chunk sharing
    exact words with the question ranks higher even when the question is
    phrased differently enough to weaken pure embedding similarity — the
    min_similarity floor below still filters on pure vector similarity
    only, so a keyword-only coincidental match can't sneak in as "relevant"
    on its own.
    """
    if not is_configured():
        return {"context": None, "sources": []}
    if context_k is None:
        context_k = top_k
    try:
        query_embedding = emb.embed_text(question, input_type="query")
        results = search_similar(query_embedding, question=question, top_k=top_k, department_filter=department_filter)
        results = [r for r in results if r["similarity"] >= min_similarity][:context_k]
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
