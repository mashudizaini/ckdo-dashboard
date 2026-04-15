# CKDO Dashboard v2 — Panduan Deployment

> Dokumen ini mencakup alur deployment dari **Local → Dev Server → Production**.
> Baca dari atas ke bawah untuk setup pertama kali.

---

## Daftar Isi

1. [Arsitektur & Lingkungan](#1-arsitektur--lingkungan)
2. [Prasyarat](#2-prasyarat)
3. [Struktur File & Secrets](#3-struktur-file--secrets)
4. [Setup GitHub Repository](#4-setup-github-repository)
5. [Deploy ke Dev Server](#5-deploy-ke-dev-server)
6. [Konfigurasi Nginx + SSL (Dev)](#6-konfigurasi-nginx--ssl-dev)
7. [Konfigurasi Keycloak (Dev)](#7-konfigurasi-keycloak-dev)
8. [Konfigurasi Email — Google Workspace SMTP](#8-konfigurasi-email--google-workspace-smtp)
9. [Deploy ke Production](#9-deploy-ke-production)
10. [Alur Update / Redeploy](#10-alur-update--redeploy)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Arsitektur & Lingkungan

### Tiga Lingkungan
+-----------------+------------------+------------------------------------------+
| Lingkungan      | Host             | URL                                      |
|-----------------|------------------|------------------------------------------|
| **Local**       | Laptop developer | `http://localhost`                       |
| **Development** | 172.21.2.209     | `https://dashboard-dev.ckd-otto.com`     |
| **Production**  | *(TBD)*          | `https://dashboard.ckd-otto.com` *(TBD)* |
+-----------------+------------------+------------------------------------------+

### Stack Aplikasi

```
Browser
  └─→ Nginx (reverse proxy)
        ├─→ Frontend  (React + Vite)        :3000
        ├─→ Backend   (FastAPI + Celery)    :8000
        └─→ Keycloak  (Auth Server)         :8080
              └─→ PostgreSQL               :5432
Redis (cache + queue broker)               :6379
Oracle Instant Client (read-only EBS)
```

### Komponen Docker

| Service     | Image              | Keterangan                           |
|-------------|--------------------|--------------------------------------|
| `nginx`     | nginx:alpine       | Reverse proxy, terminasi SSL         |
| `frontend`  | build lokal        | React/Vite                           |
| `backend`   | build lokal        | FastAPI                              |
| `celery`    | build lokal        | Async task worker                    |
| `keycloak`  | keycloak:24.0      | Auth server                          |
| `postgres`  | postgres:15-alpine | Database (ckdo_dashboard + keycloak) |
| `redis`     | redis:7-alpine     | Cache + Celery broker                |

---

## 2. Prasyarat

### Server (Dev & Production)

Pastikan server sudah terinstall:

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose Plugin (sudah include di Docker Engine terbaru)
docker compose version   # harus >= 2.x

# Git
sudo apt install git -y
```

### Oracle Instant Client

Oracle Instant Client **tidak bisa di-push ke GitHub** (binary besar). Harus diinstall manual di setiap server.

1. Download dari: https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html
   - Pilih versi yang sama dengan local: **instantclient-basic-linux.x64-21.x.x.x.x.zip**
2. Letakkan file `.so` ke folder `oracle_client/` di server:
   ```bash
   unzip instantclient-basic-linux.x64-*.zip
   cp instantclient_21_*/* /path/to/ckdo-dashboard-v2/oracle_client/
   ```

### Akses GitHub

Di server, setup SSH key untuk clone repository:

```bash
ssh-keygen -t ed25519 -C "server-dev@ckd-otto.com"
cat ~/.ssh/id_ed25519.pub
# Copy output, tambahkan ke GitHub: Settings → SSH and GPG keys
```

---

## 3. Struktur File & Secrets

### Prinsip Utama

> **File `.env` TIDAK PERNAH masuk ke GitHub.**
> Setiap server punya `.env` sendiri yang dibuat manual.

### File yang Ada di Git

```
.env.example          ← template kosong, wajib di-commit
docker-compose.yml    ← base config
docker-compose.dev.yml ← override untuk dev server
docker-compose.prod.yml ← override untuk production
nginx/nginx.dev.conf
nginx/nginx.prod.conf  ← (dibuat saat setup production)
keycloak/realm-export.json
```

### `.env.example` — Template

Buat file ini di root project:

```env
# ─────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────
ENVIRONMENT=development
APP_NAME=CKDO Dashboard
APP_URL=https://DOMAIN_ANDA

# ─────────────────────────────────────────
# POSTGRESQL
# ─────────────────────────────────────────
POSTGRES_USER=postgres
POSTGRES_PASSWORD=GANTI_INI
DATABASE_URL=postgresql://postgres:GANTI_INI@postgres:5432/ckdo_dashboard

# ─────────────────────────────────────────
# REDIS
# ─────────────────────────────────────────
REDIS_PASSWORD=GANTI_INI
REDIS_URL=redis://:GANTI_INI@redis:6379/0
CELERY_BROKER_URL=redis://:GANTI_INI@redis:6379/1
CELERY_RESULT_BACKEND=redis://:GANTI_INI@redis:6379/2

# ─────────────────────────────────────────
# KEYCLOAK
# ─────────────────────────────────────────
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=GANTI_INI
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=ckdo
KEYCLOAK_CLIENT_ID=ckdo-dashboard
KEYCLOAK_CLIENT_SECRET=GANTI_INI

# ─────────────────────────────────────────
# ORACLE EBS
# ─────────────────────────────────────────
ORACLE_HOST=172.21.2.201
ORACLE_PORT=1521
ORACLE_SERVICE=PROD
ORACLE_USER=apps
ORACLE_PASSWORD=GANTI_INI
ORACLE_INSTANT_CLIENT=/opt/oracle/instantclient

# ─────────────────────────────────────────
# TALENTA HR API
# ─────────────────────────────────────────
TALENTA_API_KEY=GANTI_INI
TALENTA_API_URL=https://api.talenta.co

# ─────────────────────────────────────────
# ANTHROPIC
# ─────────────────────────────────────────
ANTHROPIC_API_KEY=GANTI_INI

# ─────────────────────────────────────────
# SMTP (Google Workspace)
# ─────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@ckd-otto.com
SMTP_PASSWORD=GANTI_INI_APP_PASSWORD

# ─────────────────────────────────────────
# FRONTEND (Vite — di-embed saat build)
# ─────────────────────────────────────────
VITE_API_URL=https://DOMAIN_ANDA/api/v1
VITE_KEYCLOAK_URL=https://DOMAIN_ANDA
VITE_KEYCLOAK_REALM=ckdo
VITE_KEYCLOAK_CLIENT_ID=ckdo-dashboard

# ─────────────────────────────────────────
# METALS API
# ─────────────────────────────────────────
METALS_API_KEY=GANTI_INI
```

### Lokasi Penyimpanan Secrets

Simpan nilai `.env` asli di salah satu:
- **Bitwarden** (rekomendasi — gratis, self-hostable)
- **Shared folder internal** yang hanya bisa diakses tim
- **Jangan di grup chat / email**

---

## 4. Setup GitHub Repository

### Langkah-langkah (dilakukan sekali dari laptop)

```bash
# 1. Pastikan .env sudah ada di .gitignore
cat .gitignore | grep ".env"   # harus muncul baris ".env"

# 2. Buat .env.example dari .env (hapus nilai asli)
cp .env .env.example
# Edit .env.example — ganti semua nilai asli dengan placeholder "GANTI_INI"

# 3. Inisialisasi remote GitHub
git remote add origin git@github.com:mashudizaini/ckdo-dashboard-v2.git

# 4. Initial push
git add .
git commit -m "Initial commit: CKDO Dashboard v2"
git push -u origin main
```

> **Cek dulu** sebelum push: `git status` — pastikan `.env` tidak ada di staged files.

---

## 5. Deploy ke Dev Server

### 5.1 Akses Server

```bash
ssh user@172.21.2.209
```

### 5.2 Clone Repository

```bash
cd /opt
sudo mkdir ckdo && sudo chown $USER:$USER ckdo
cd ckdo
git clone git@github.com:mashudizaini/ckdo-dashboard-v2.git
cd ckdo-dashboard-v2
```

### 5.3 Buat File `.env` untuk Dev

```bash
cp .env.example .env
nano .env
```

Nilai yang perlu diubah untuk dev server:

```env
ENVIRONMENT=development
APP_URL=https://dashboard-dev.ckd-otto.com

DATABASE_URL=postgresql://postgres:PASSWORD_BARU@postgres:5432/ckdo_dashboard

KEYCLOAK_ADMIN_PASSWORD=PASSWORD_KUAT
KEYCLOAK_CLIENT_SECRET=SECRET_KUAT
KEYCLOAK_URL=http://keycloak:8080

# VITE_ — sesuaikan dengan URL dev
VITE_API_URL=https://dashboard-dev.ckd-otto.com/api/v1
VITE_KEYCLOAK_URL=https://dashboard-dev.ckd-otto.com
```

> Catatan: `KEYCLOAK_URL` tetap `http://keycloak:8080` (internal Docker network).
> `VITE_KEYCLOAK_URL` menggunakan URL publik karena diakses dari browser.

### 5.4 Install Oracle Instant Client di Server

```bash
# Upload file zip dari laptop ke server
scp instantclient-basic-linux.x64-21.*.zip user@172.21.2.209:/tmp/

# Di server
cd /tmp
unzip instantclient-basic-linux.x64-*.zip
cp instantclient_21_*/* /opt/ckdo/ckdo-dashboard-v2/oracle_client/
```

### 5.5 Buat `docker-compose.dev.yml`

Buat file ini di root project:

```yaml
# docker-compose.dev.yml — override untuk dev server
services:
  keycloak:
    command: start-dev --import-realm
    environment:
      KC_HOSTNAME_STRICT: "false"
      KC_HTTP_ENABLED: "true"
      KC_PROXY: edge

  backend:
    environment:
      - ENVIRONMENT=development
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  nginx:
    volumes:
      - ./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    ports:
      - "80:80"
      - "443:443"
```

### 5.6 Jalankan Aplikasi

```bash
# Build dan jalankan semua service
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Cek status
docker compose ps

# Lihat log (opsional)
docker compose logs -f backend
docker compose logs -f keycloak
```

---

## 6. Konfigurasi Nginx + SSL (Dev)

### 6.1 Pastikan DNS Sudah Diarahkan

Di DNS manager domain `ckd-otto.com`:
```
dashboard-dev.ckd-otto.com  →  A record  →  172.21.2.209
```

Verifikasi dari server:
```bash
ping dashboard-dev.ckd-otto.com   # harus resolve ke 172.21.2.209
```

### 6.2 Install Certbot (SSL Let's Encrypt)

```bash
sudo apt install certbot -y

# Stop nginx sementara untuk certbot standalone
docker compose stop nginx

# Request certificate
sudo certbot certonly --standalone -d dashboard-dev.ckd-otto.com \
  --email mashudi.zaini@yahoo.com --agree-tos --no-eff-email

# Certificate tersimpan di: /etc/letsencrypt/live/dashboard-dev.ckd-otto.com/
```

### 6.3 Update `nginx/nginx.dev.conf` untuk HTTPS

```nginx
worker_processes 1;

events {}

http {
  upstream backend  { server backend:8000; }
  upstream frontend { server frontend:3000; }
  upstream keycloak { server keycloak:8080; }

  # Redirect HTTP ke HTTPS
  server {
    listen 80;
    server_name dashboard-dev.ckd-otto.com;
    return 301 https://$host$request_uri;
  }

  server {
    listen 443 ssl;
    server_name dashboard-dev.ckd-otto.com;

    ssl_certificate     /etc/letsencrypt/live/dashboard-dev.ckd-otto.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard-dev.ckd-otto.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Frontend
    location / {
      proxy_pass http://frontend;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
    }

    # Backend API
    location /api/ {
      proxy_pass http://backend;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Keycloak Auth
    location /auth/ {
      proxy_pass http://keycloak/auth/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
    }
  }
}
```

```bash
# Restart nginx dengan config baru
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d nginx
```

### 6.4 Auto-Renew SSL

```bash
# Test renew
sudo certbot renew --dry-run

# Tambah cron untuk auto-renew
sudo crontab -e
# Tambahkan baris:
0 3 * * * certbot renew --quiet && docker compose -C /opt/ckdo/ckdo-dashboard-v2 restart nginx
```

---

## 7. Konfigurasi Keycloak (Dev)

### 7.1 Login ke Keycloak Admin Console

```
     http://dashboard-dev.ckd-otto.com/auth/admin --valid url
URL: https://dashboard-dev.ckd-otto.com/auth/admin
User: admin
Password: (nilai KEYCLOAK_ADMIN_PASSWORD di .env)
```

### 7.2 Update Client Redirect URIs

1. Buka: **Realm: ckdo** → **Clients** → **ckdo-dashboard**
2. Tab **Settings**, update:

| Field | Nilai |
|---|---|
| Root URL | `https://dashboard-dev.ckd-otto.com` |
| Valid Redirect URIs | `https://dashboard-dev.ckd-otto.com/*` |
| Valid Post Logout Redirect URIs | `https://dashboard-dev.ckd-otto.com/*` |
| Web Origins | `https://dashboard-dev.ckd-otto.com` |

3. **Save**

### 7.3 Catat Client Secret

1. Tab **Credentials**
2. Copy nilai **Client Secret**
3. Update `.env` di server:
   ```env
   KEYCLOAK_CLIENT_SECRET=nilai_yang_dicopy
   ```
4. Restart backend:
   ```bash
   docker compose restart backend celery
   ```

### 7.4 Export Realm Setelah Setup

Setiap kali ada perubahan konfigurasi Keycloak yang signifikan, export realm untuk backup:

```bash
docker exec ckdo_keycloak /opt/keycloak/bin/kc.sh export \
  --realm ckdo \
  --file /tmp/realm-export.json

docker cp ckdo_keycloak:/tmp/realm-export.json ./keycloak/realm-export.json
```

> **Catatan:** Hapus nilai `secret` dari field client credentials sebelum commit ke git.

---

## 8. Konfigurasi Email — Google Workspace SMTP

### 8.1 Buat App Password Google Workspace

1. Login ke akun Google Workspace: `noreply@ckd-otto.com` (atau akun yang akan dipakai)
2. Masuk ke: **Manage your Google Account** → **Security**
3. Aktifkan **2-Step Verification** (wajib ada)
4. Kembali ke Security → cari **App Passwords**
5. Generate:
   - Select app: **Mail**
   - Select device: **Other** → isi "Keycloak Dev Server"
6. Catat 16-karakter App Password yang dihasilkan (format: `xxxx xxxx xxxx xxxx`)

### 8.2 Konfigurasi SMTP di Keycloak

1. Login Keycloak Admin Console
2. **Realm Settings** → **Email**
3. Isi form:

| Field | Nilai |
|---|---|
| From | `noreply@ckd-otto.com` |
| From Display Name | `CKDO Dashboard` |
| Host | `smtp.gmail.com` |
| Port | `587` |
| Encryption | `STARTTLS` |
| Authentication | **Enabled** |
| Username | `noreply@ckd-otto.com` |
| Password | *(App Password 16 karakter)* |

4. Klik **Test connection** — harus berhasil
5. **Save**

### 8.3 Update `.env` (untuk Backend jika perlu kirim email)

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@ckd-otto.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

---

## 9. Deploy ke Production

> Lakukan ini hanya setelah dev server berjalan stabil.

Langkah hampir sama dengan dev, dengan perbedaan:

| Aspek | Dev | Production |
|---|---|---|
| Docker command mode | `start-dev` + `--reload` | `start` (Keycloak production mode) |
| Keycloak command | `start-dev` | `start --optimized` |
| Frontend build | Dev server (Vite HMR) | Static build (`npm run build`) |
| Backend reload | `--reload` (auto) | Tidak ada `--reload` |
| SSL domain | `dashboard-dev.ckd-otto.com` | `dashboard.ckd-otto.com` (TBD) |

Buat `docker-compose.prod.yml`:

```yaml
services:
  keycloak:
    command: start --import-realm
    environment:
      KC_HOSTNAME: dashboard.ckd-otto.com
      KC_HOSTNAME_STRICT: "true"
      KC_HTTP_ENABLED: "false"
      KC_PROXY: edge

  backend:
    environment:
      - ENVIRONMENT=production
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    volumes:
      - uploads_data:/app/uploads
      # Tidak mount source code di production

  frontend:
    build:
      dockerfile: Dockerfile.prod   # static build

  nginx:
    volumes:
      - ./nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

---

## 10. Alur Update / Redeploy

### Update Kode (tanpa perubahan environment)

```bash
cd /opt/ckdo/ckdo-dashboard-v2

# Pull perubahan terbaru
git pull origin main

# Rebuild dan restart
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Cek status
docker compose ps
docker compose logs -f backend --tail=50
```

### Update yang Butuh Restart Total

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Rollback ke Commit Sebelumnya

```bash
git log --oneline -10           # lihat riwayat commit
git checkout <commit-hash>      # checkout ke commit tertentu
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

---

## 11. Troubleshooting

### Keycloak tidak mau start

```bash
docker compose logs keycloak --tail=50
# Sering karena PostgreSQL belum ready → tunggu atau restart
docker compose restart keycloak
```

### Backend gagal konek ke Oracle

```bash
docker compose logs backend --tail=50
# Cek oracle_client/ sudah ada .so files
ls oracle_client/*.so*
```

### Frontend tidak update setelah deploy

Karena `VITE_` env vars di-embed saat build, wajib rebuild:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build frontend
```

### SSL expired

```bash
sudo certbot renew
docker compose restart nginx
```

### Reset semua data (HATI-HATI: data hilang)

```bash
docker compose down -v    # -v menghapus volumes (database!)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

---

## Catatan Keamanan

- [ ] Ganti semua password default sebelum deploy ke server manapun
- [ ] Jangan pernah commit `.env` ke GitHub
- [ ] Rotate `ANTHROPIC_API_KEY` secara berkala
- [ ] `KEYCLOAK_CLIENT_SECRET` harus berbeda antara dev dan production
- [ ] App Password Google harus per-environment (buat 2: satu untuk dev, satu untuk prod)
- [ ] Batasi akses port 5432 (Postgres) dan 6379 (Redis) — jangan expose ke public

---

*Dokumen ini dibuat pada 2026-04-09. Update setiap ada perubahan infrastruktur.*
