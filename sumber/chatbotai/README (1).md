# RAG Prototype — Claude API + pgvector

Prototype chatbot internal CKD OTTO berbasis RAG (Retrieval Augmented Generation).

## Cara menjalankan

### 1. Jalankan database
```bash
docker compose up -d
```
Cek log untuk pastikan `init.sql` berhasil dieksekusi (membuat extension vector + tabel).

### 2. Setup Python environment
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Siapkan API key
Copy `.env.example` jadi `.env`, lalu isi:
- `ANTHROPIC_API_KEY` — dari console.anthropic.com
- `VOYAGE_API_KEY` — dari dash.voyageai.com (Voyage punya free tier, cukup untuk prototype)
- Sesuaikan `DB_PASSWORD` dengan yang ada di `docker-compose.yml`

### 4. Masukkan data contoh
```bash
python ingest.py
```
Ini akan meng-embed dan menyimpan 2 dokumen contoh ke pgvector.
Ganti isi `documents = [...]` di `ingest.py` dengan data perusahaan asli
(SOP, hasil extract Oracle EBS, knowledge base helpdesk, dll).

### 5. Tes tanya jawab
```bash
python query.py
```
Atau panggil `ask_chatbot("pertanyaan...")` dari kode lain (dashboard).

## Struktur file
- `docker-compose.yml` — definisi container Postgres + pgvector
- `init.sql` — schema tabel `company_documents` + index vector
- `db.py` — koneksi & query database (insert, search similarity)
- `embeddings.py` — generate embedding pakai Voyage AI + chunking teks
- `ingest.py` — contoh script memasukkan dokumen
- `query.py` — fungsi inti `ask_chatbot()` untuk RAG + Claude API

## Cara tempel ke dashboard utama
Karena dashboard pakai Python, paling gampang:
1. Copy file `db.py`, `embeddings.py`, `query.py` ke project dashboard.
2. Tambahkan `requirements.txt` ke dependency dashboard.
3. Import `from query import ask_chatbot` di endpoint API dashboard
   (misal Flask: `@app.route("/api/chatbot", methods=["POST"])` lalu panggil `ask_chatbot(question)`).
4. Pastikan env variable (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `DB_*`) sudah
   di-set di environment dashboard, bukan cuma di `.env` lokal.

## Catatan migrasi ke on-premise nanti
- `docker-compose.yml` ini bisa langsung dipindah ke server on-premise tanpa ubah apa pun,
  cukup `pg_dump` dari VPS lalu `pg_restore` di server baru.
- Kalau nanti mau ganti LLM dari Claude API ke model lokal (on-premise, misal lewat Ollama/vLLM),
  cukup ubah bagian pemanggilan API di `query.py`, struktur RAG-nya tidak perlu berubah.
- Dimensi embedding (1024, model voyage-3) harus konsisten antara `init.sql` dan `embeddings.py`.
  Kalau ganti model embedding dengan dimensi berbeda, tabel `company_documents` perlu dibuat ulang.

## Catatan keamanan
- Jangan commit file `.env` ke git (sudah seharusnya ada di `.gitignore`).
- Ganti `POSTGRES_PASSWORD` di `docker-compose.yml` sebelum dipakai di luar laptop lokal.
- Untuk data sensitif perusahaan (data EBS, finance, dll), pastikan koneksi ke VPS/DB
  pakai SSL dan firewall yang membatasi akses hanya dari IP dashboard.
