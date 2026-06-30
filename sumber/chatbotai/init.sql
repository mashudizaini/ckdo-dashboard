-- Aktifkan extension pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabel utama untuk menyimpan chunk dokumen perusahaan + embedding-nya
CREATE TABLE IF NOT EXISTS company_documents (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,          -- contoh: 'EBS_PO_MODULE', 'SOP_FINANCE', 'helpdesk_kb'
    title           TEXT,
    content         TEXT NOT NULL,          -- isi chunk teks (potongan dokumen, bukan satu file utuh)
    metadata        JSONB DEFAULT '{}',     -- info tambahan: nomor dokumen, tanggal, departemen, dll
    embedding       VECTOR(1024),           -- sesuaikan dimensi dengan model embedding yang dipakai (voyage-3 = 1024)
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Index untuk pencarian similarity yang cepat (ivfflat, cocok untuk skala menengah)
-- Jalankan ANALYZE setelah data agak banyak (>1000 baris) baru index ini efektif
CREATE INDEX IF NOT EXISTS idx_company_documents_embedding
    ON company_documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index biasa untuk filter berdasarkan source/metadata
CREATE INDEX IF NOT EXISTS idx_company_documents_source ON company_documents (source);
CREATE INDEX IF NOT EXISTS idx_company_documents_metadata ON company_documents USING GIN (metadata);
