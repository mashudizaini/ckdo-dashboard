# CKDO Dashboard v2

Platform dashboard internal PT CKD OTTO Pharmaceuticals — dibangun dengan FastAPI + React + Keycloak + Docker.

## Quick Start

```bash
# 1. Clone & masuk folder
git clone <repo-url> ckdo-dashboard-v2
cd ckdo-dashboard-v2

# 2. Setup environment
cp .env.example .env
# Edit .env — isi password Oracle, Anthropic API key, dll.

# 3. Jalankan semua service
docker-compose up -d

# 4. Cek status
docker-compose ps
```

## Service URLs (Development)

| Service            |           URL              |
|--------------------|----------------------------|
| Frontend (React)   | http://localhost           |
| Backend API        | http://localhost/api/v1    |
| API Docs (Swagger) | http://localhost:8000/docs |
| Keycloak Admin     | http://localhost:8080      |

## Menambahkan Modul Baru

Ikuti 4 langkah ini untuk menambahkan departemen/modul baru:

### 1. Backend — Service
Buat file `backend/app/services/nama_service.py`:
```python
class NamaService:
    async def get_summary(self) -> dict:
        return {"success": True, "data": {}}
```

### 2. Backend — Router
Buat file `backend/app/routers/dashboard/nama.py`:
```python
from fastapi import APIRouter, Depends
from app.dependencies import require_role, CurrentUser, Roles

router = APIRouter()

@router.get("/summary")
async def get_summary(user: CurrentUser = Depends(require_role(Roles.NAMA))):
    ...
```

### 3. Backend — Daftarkan di main.py
```python
from app.routers.dashboard import nama
app.include_router(nama.router, prefix=f"{API_PREFIX}/dashboard/nama", tags=["Dashboard - NAMA"])
```

### 4. Frontend — Tambahkan di Sidebar + App.jsx
- Tambahkan entry di `src/components/layout/Sidebar.jsx` (NAV_ITEMS)
- Buat page di `src/pages/dashboard/Nama.jsx`
- Daftarkan route di `src/App.jsx`

### 5. Keycloak — Tambahkan Role
Di Keycloak Admin (`http://localhost:8080`):
- Realm Settings → Roles → Add Role: `nama_staff`
- Assign role ke user yang sesuai

## Struktur Folder

```
ckdo-dashboard-v2/
├── backend/app/
│   ├── routers/dashboard/  ← Satu file per departemen
│   ├── routers/ai_tools/   ← AI features
│   ├── services/           ← Business logic (implement di sini)
│   └── main.py             ← Register semua router di sini
├── frontend/src/
│   ├── pages/dashboard/    ← Satu file per departemen
│   ├── pages/ai-tools/     ← AI tools UI
│   ├── api/dashboard.js    ← Semua API calls
│   └── components/layout/Sidebar.jsx  ← Navigation menu
├── keycloak/               ← Realm config & roles
└── docker-compose.yml
```

## Oracle Instant Client

Oracle Instant Client harus tersedia di host dan di-mount ke container:
```bash
# Download dari Oracle website, extract ke:
/opt/oracle/instantclient

# docker-compose.yml sudah mount volume oracle_client
# Pastikan path di .env: ORACLE_INSTANT_CLIENT=/opt/oracle/instantclient
```

## Teknologi

| Layer       | Stack                              |
|-------------|------------------------------------|
| Auth        | Keycloak 24 (OIDC/OAuth2)          |
| Backend     | FastAPI + SQLAlchemy 2.0 + Alembic |
| Async Tasks | Celery + Redis                     |
| Database    | PostgreSQL 15                      |
| Cache       | Redis 7                            |
| Frontend    | React 18 + Vite + Tailwind CSS     |
| Container   | Docker Compose → Kubernetes (fase lanjut) |
| AI          | Anthropic Claude API + Whisper (lokal) |
