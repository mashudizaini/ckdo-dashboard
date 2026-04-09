# CKDO Dashboard — Panduan Deploy Production

> Dokumen ini dibuat berdasarkan pengalaman nyata deploy ke dev server (2026-04-09).
> Berisi semua pitfall, solusi, dan konfigurasi yang benar agar production berjalan mulus.

---

## Daftar Isi

1. [Prasyarat Server](#1-prasyarat-server)
2. [Clone & Setup Awal](#2-clone--setup-awal)
3. [Konfigurasi .env Production](#3-konfigurasi-env-production)
4. [Konfigurasi Docker Compose Production](#4-konfigurasi-docker-compose-production)
5. [Konfigurasi Nginx Production](#5-konfigurasi-nginx-production)
6. [SSL dengan Let's Encrypt](#6-ssl-dengan-lets-encrypt)
7. [Keycloak — Setup Production](#7-keycloak--setup-production)
8. [Google OAuth (SSO)](#8-google-oauth-sso)
9. [Google Workspace SMTP](#9-google-workspace-smtp)
10. [Oracle Instant Client](#10-oracle-instant-client)
11. [Jalankan Aplikasi](#11-jalankan-aplikasi)
12. [Verifikasi Post-Deploy](#12-verifikasi-post-deploy)
13. [Pelajaran dari Dev Server](#13-pelajaran-dari-dev-server)

---

## 1. Prasyarat Server

### Software yang Wajib Ada

```bash
# Docker Engine (versi 20+ direkomendasikan)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Verifikasi
docker --version          # Docker version 29.x.x
docker compose version    # Docker Compose version v2.x.x
git --version             # git version 2.x.x
```

### Setup SSH Key untuk GitHub

```bash
ssh-keygen -t ed25519 -C "production-server@ckd-otto.com"
cat ~/.ssh/id_ed25519.pub
# Tambahkan ke: https://github.com/settings/ssh/new
# Title: "Production Server"

# Test koneksi
ssh -T git@github.com
# Harus muncul: Hi mashudizaini! You've successfully authenticated...
```

---

## 2. Clone & Setup Awal

```bash
# Buat direktori
sudo mkdir -p /opt/ckdo
sudo chown $USER:$USER /opt/ckdo
cd /opt/ckdo

# Clone repository
git clone git@github.com:mashudizaini/ckdo-dashboard.git
cd ckdo-dashboard
```

---

## 3. Konfigurasi .env Production

```bash
cp .env.example .env
nano .env
```

### Nilai yang Harus Diubah untuk Production

```env
# ─────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────
ENVIRONMENT=production
APP_NAME=CKDO Dashboard
APP_URL=https://dashboard.ckd-otto.com         # ← URL production dengan https

# ─────────────────────────────────────────
# POSTGRESQL
# ─────────────────────────────────────────
POSTGRES_USER=postgres
POSTGRES_PASSWORD=GantiPasswordKuat123         # ← JANGAN pakai karakter @, #, $ di password
DATABASE_URL=postgresql://postgres:GantiPasswordKuat123@postgres:5432/ckdo_dashboard
# ⚠️  PENTING: Jika password mengandung karakter @ maka harus di-encode sebagai %40
#     Contoh: Pass@word → DATABASE_URL=...Pass%40word@postgres:...
#     LEBIH MUDAH: hindari karakter spesial di password database

# ─────────────────────────────────────────
# REDIS
# ─────────────────────────────────────────
REDIS_PASSWORD=GantiRedisPassword123
REDIS_URL=redis://:GantiRedisPassword123@redis:6379/0
CELERY_BROKER_URL=redis://:GantiRedisPassword123@redis:6379/1
CELERY_RESULT_BACKEND=redis://:GantiRedisPassword123@redis:6379/2

# ─────────────────────────────────────────
# KEYCLOAK
# ─────────────────────────────────────────
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=GantiKeycloakAdmin123
KEYCLOAK_URL=https://dashboard.ckd-otto.com/auth  # ← URL PUBLIK dengan /auth, BUKAN http://keycloak:8080
KEYCLOAK_REALM=ckdo
KEYCLOAK_CLIENT_ID=ckdo-dashboard
KEYCLOAK_CLIENT_SECRET=GantiClientSecret123

# ─────────────────────────────────────────
# ORACLE EBS
# ─────────────────────────────────────────
ORACLE_HOST=172.21.2.201
ORACLE_PORT=1521
ORACLE_SERVICE=PROD
ORACLE_USER=apps
ORACLE_PASSWORD=apps
ORACLE_INSTANT_CLIENT=/opt/oracle/instantclient

# ─────────────────────────────────────────
# TALENTA HR API
# ─────────────────────────────────────────
TALENTA_API_KEY=isi_api_key_talenta
TALENTA_API_URL=https://api.talenta.co

# ─────────────────────────────────────────
# ANTHROPIC
# ─────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxx

# ─────────────────────────────────────────
# SMTP (Google Workspace)
# ─────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@ckd-otto.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx    # ← Google App Password (16 karakter)

# ─────────────────────────────────────────
# FRONTEND — WAJIB SESUAI URL PRODUCTION
# ─────────────────────────────────────────
VITE_API_URL=https://dashboard.ckd-otto.com/api/v1
VITE_KEYCLOAK_URL=https://dashboard.ckd-otto.com/auth  # ← URL PUBLIK dengan /auth
VITE_KEYCLOAK_REALM=ckdo
VITE_KEYCLOAK_CLIENT_ID=ckdo-dashboard

# Metals API
METALS_API_KEY=isi_metals_api_key
```

### ⚠️ Aturan Penting .env

| Rule | Penjelasan |
|---|---|
| Hindari `@` di password DB | Jika terpaksa, encode jadi `%40` di DATABASE_URL |
| `KEYCLOAK_URL` = URL publik | Backend validasi token butuh URL yang cocok dengan issuer token |
| `VITE_KEYCLOAK_URL` = URL publik + `/auth` | Keycloak di-proxy nginx di path `/auth/` |
| VITE_ vars di-embed saat build | Wajib rebuild frontend jika mengubah nilai VITE_ |

---

## 4. Konfigurasi Docker Compose Production

Buat file `docker-compose.prod.yml`:

```yaml
# docker-compose.prod.yml
# Digunakan bersama docker-compose.yml:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

services:
  keycloak:
    command: start --import-realm
    environment:
      KC_HOSTNAME_STRICT: "false"
      KC_HTTP_ENABLED: "true"
      KC_PROXY: edge
      KC_HTTP_RELATIVE_PATH: /auth      # ← WAJIB: agar path /auth/ di nginx bekerja

  backend:
    environment:
      - ENVIRONMENT=production
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4  # tanpa --reload
    volumes:
      - uploads_data:/app/uploads
      # Tidak mount source code di production

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod       # static build

  nginx:
    volumes:
      - ./nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    ports:
      - "80:80"
      - "443:443"
```

---

## 5. Konfigurasi Nginx Production

Buat file `nginx/nginx.prod.conf`:

```nginx
worker_processes auto;

events {
  worker_connections 1024;
}

http {
  upstream backend  { server backend:8000; }
  upstream frontend { server frontend:80; }   # production: nginx serve static files
  upstream keycloak { server keycloak:8080; }

  # Redirect HTTP ke HTTPS
  server {
    listen 80;
    server_name dashboard.ckd-otto.com;
    return 301 https://$host$request_uri;
  }

  server {
    listen 443 ssl;
    server_name dashboard.ckd-otto.com;

    ssl_certificate     /etc/letsencrypt/live/dashboard.ckd-otto.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.ckd-otto.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Upload file size
    client_max_body_size 50M;

    # Frontend (static build)
    location / {
      proxy_pass http://frontend;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
    }

    # Backend API
    location /api/ {
      proxy_pass http://backend;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 120s;
    }

    # ⚠️ KRITIS: proxy_pass HARUS pakai /auth/ di akhir
    # Tanpa trailing slash → path double: /auth/auth/...
    location /auth/ {
      proxy_pass http://keycloak/auth/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;  # ← https untuk production
    }
  }
}
```

---

## 6. SSL dengan Let's Encrypt

### Prasyarat

- DNS `dashboard.ckd-otto.com` sudah diarahkan ke IP server production (IP publik)
- Port 80 dan 443 terbuka dari internet

### Request Certificate

```bash
# Install certbot
sudo apt update && sudo apt install certbot -y

# Stop nginx sementara
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop nginx

# Request certificate
sudo certbot certonly --standalone \
  -d dashboard.ckd-otto.com \
  --email mashudi.zaini@yahoo.com \
  --agree-tos --no-eff-email

# Certificate tersimpan di:
# /etc/letsencrypt/live/dashboard.ckd-otto.com/fullchain.pem
# /etc/letsencrypt/live/dashboard.ckd-otto.com/privkey.pem

# Start nginx kembali
docker compose -f docker-compose.yml -f docker-compose.prod.yml start nginx
```

### Auto-Renew SSL

```bash
# Test renew
sudo certbot renew --dry-run

# Setup cron auto-renew
sudo crontab -e
# Tambahkan:
0 3 * * * certbot renew --quiet && docker compose -C /opt/ckdo/ckdo-dashboard restart nginx
```

> **Catatan:** Jika server production berada di jaringan internal (tidak bisa diakses internet), gunakan DNS Challenge:
> ```bash
> sudo certbot certonly --manual --preferred-challenges dns -d dashboard.ckd-otto.com
> # Ikuti instruksi untuk menambahkan TXT record di DNS
> ```

---

## 7. Keycloak — Setup Production

### 7.1 Login Admin Console

```
URL: https://dashboard.ckd-otto.com/auth/admin
User: admin
Password: (nilai KEYCLOAK_ADMIN_PASSWORD di .env)
```

### 7.2 Update Client Redirect URIs

1. **Clients** → **ckdo-dashboard** → tab **Settings**

| Field | Nilai |
|---|---|
| Root URL | `https://dashboard.ckd-otto.com` |
| Valid Redirect URIs | `https://dashboard.ckd-otto.com/*` |
| Valid Post Logout Redirect URIs | `https://dashboard.ckd-otto.com/*` |
| Web Origins | `https://dashboard.ckd-otto.com` |

2. **Save**

### 7.3 Setup Google Identity Provider

1. **Identity Providers** → **Google**
2. Isi:

| Field | Nilai |
|---|---|
| Client ID | (dari Google Cloud Console) |
| Client Secret | (dari Google Cloud Console) |
| Default Scopes | `openid email profile` |

3. **Save**

4. Di Google Cloud Console, tambahkan Authorized Redirect URI:
```
https://dashboard.ckd-otto.com/auth/realms/ckdo/broker/google/endpoint
```

### 7.4 Assign Role ke User

Setelah user pertama kali login, assign role di:
**Users** → pilih user → **Role mapping** → **Assign role** → pilih role yang sesuai

Role yang tersedia:
- `admin` — akses semua modul
- `it_staff` — IT Dashboard
- `hr_staff` — HR Dashboard
- `pac_staff` — PAC Dashboard
- `accounting_staff` — Accounting Dashboard
- `purchasing_staff` — Purchasing Dashboard

---

## 8. Google OAuth (SSO)

### Buat OAuth Credentials di Google Cloud Console

1. Buka `https://console.cloud.google.com`
2. Pilih/buat project
3. **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Authorized redirect URIs:
   ```
   https://dashboard.ckd-otto.com/auth/realms/ckdo/broker/google/endpoint
   ```
6. Copy **Client ID** dan **Client Secret** → masukkan ke Keycloak (lihat bagian 7.3)

### Batasi Login ke Domain ckd-otto.com

Di Keycloak → Identity Providers → Google → **Advanced Settings**:
- Hosted Domain: `ckd-otto.com`

Ini memastikan hanya email `@ckd-otto.com` yang bisa login via Google.

---

## 9. Google Workspace SMTP

### Buat App Password

1. Login ke akun Google: `noreply@ckd-otto.com`
2. **Manage Account** → **Security** → **2-Step Verification** (aktifkan jika belum)
3. **App Passwords** → Generate untuk "Mail" + "Keycloak Production"
4. Simpan 16-karakter App Password

### Konfigurasi di Keycloak

**Realm Settings** → **Email**:

| Field | Nilai |
|---|---|
| From | `noreply@ckd-otto.com` |
| From Display Name | `CKDO Dashboard` |
| Host | `smtp.gmail.com` |
| Port | `587` |
| Encryption | `STARTTLS` |
| Authentication | Enabled |
| Username | `noreply@ckd-otto.com` |
| Password | (App Password 16 karakter) |

Klik **Test connection** sebelum save.

---

## 10. Oracle Instant Client

File `.so` tidak bisa di-commit ke GitHub (binary besar). Upload manual ke server:

```bash
# Dari laptop — upload ke server production
scp oracle_client/lib*.so* user@IP_PRODUCTION:/opt/ckdo/ckdo-dashboard/oracle_client/

# Verifikasi di server
ls -lh /opt/ckdo/ckdo-dashboard/oracle_client/*.so*
# Harus muncul: libclntsh.so.12.1, libclntshcore.so.12.1, libipc1.so, dll
```

---

## 11. Jalankan Aplikasi

### Build dan Start

```bash
cd /opt/ckdo/ckdo-dashboard

# Build dan jalankan semua service
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Monitor progress
docker compose ps
docker compose logs -f --tail=20
```

### Urutan Container Start (otomatis dihandle Docker)

```
postgres (healthy) ─┐
redis    (healthy) ─┼─→ keycloak → backend → celery → frontend → nginx
```

### Cek Status

```bash
docker compose ps
# Semua harus STATUS: Up atau healthy
```

---

## 12. Verifikasi Post-Deploy

```bash
# 1. Test HTTPS redirect
curl -s -o /dev/null -w "%{http_code}" http://dashboard.ckd-otto.com
# Harus: 301

# 2. Test frontend
curl -s -o /dev/null -w "%{http_code}" https://dashboard.ckd-otto.com
# Harus: 200

# 3. Test backend API
curl -s -o /dev/null -w "%{http_code}" https://dashboard.ckd-otto.com/api/v1/health
# Harus: 200

# 4. Test Keycloak
curl -s -o /dev/null -w "%{http_code}" https://dashboard.ckd-otto.com/auth/
# Harus: 302

# 5. Test JWKS endpoint (dipakai backend untuk validasi token)
curl -s https://dashboard.ckd-otto.com/auth/realms/ckdo/protocol/openid-connect/certs | python3 -m json.tool | head -5
# Harus: JSON dengan field "keys"
```

---

## 13. Pelajaran dari Dev Server

Ini daftar masalah yang ditemukan saat deploy ke dev server beserta solusinya.
**Baca ini sebelum deploy ke production** untuk menghindari masalah yang sama.

---

### ❌ Password database mengandung karakter `@`

**Masalah:** `POSTGRES_PASSWORD=Dev@Ckdo2024` → DATABASE_URL parsing gagal karena `@` dianggap separator host.

**Solusi:**
```env
# Hindari karakter @ di password
POSTGRES_PASSWORD=DevCkdo2024

# Jika terpaksa pakai @, encode di URL
DATABASE_URL=postgresql://postgres:Dev%40Ckdo2024@postgres:5432/ckdo_dashboard
```

---

### ❌ `KEYCLOAK_URL` menggunakan internal Docker URL

**Masalah:** `KEYCLOAK_URL=http://keycloak:8080` → Backend gagal validasi token karena issuer token (`http://dashboard-dev.ckd-otto.com/auth/realms/ckdo`) tidak cocok dengan URL yang digunakan backend untuk fetch JWKS.

**Solusi:**
```env
# WAJIB gunakan URL publik yang sama dengan yang diakses browser
KEYCLOAK_URL=https://dashboard.ckd-otto.com/auth
```

---

### ❌ `VITE_KEYCLOAK_URL` tanpa path `/auth`

**Masalah:** `VITE_KEYCLOAK_URL=http://dashboard-dev.ckd-otto.com` → Keycloak JS adapter mencoba hit `/realms/ckdo/...` tapi nginx hanya proxy path `/auth/`.

**Solusi:**
```env
# Harus include /auth karena nginx proxy di /auth/
VITE_KEYCLOAK_URL=https://dashboard.ckd-otto.com/auth
```

---

### ❌ Nginx proxy Keycloak tanpa trailing slash

**Masalah:**
```nginx
location /auth/ {
  proxy_pass http://keycloak;    # ← salah: path jadi /auth/auth/...
}
```

**Solusi:**
```nginx
location /auth/ {
  proxy_pass http://keycloak/auth/;    # ← benar: trailing slash wajib
}
```

---

### ❌ Keycloak tanpa `KC_HTTP_RELATIVE_PATH=/auth`

**Masalah:** Keycloak 17+ default root path adalah `/`. Nginx proxy di `/auth/` tidak bekerja tanpa setting ini.

**Solusi** — di `docker-compose.prod.yml`:
```yaml
keycloak:
  environment:
    KC_HTTP_RELATIVE_PATH: /auth
```

---

### ❌ `python-keycloak` `decode_token()` bug di versi 3.9.1

**Masalah:** `kc.decode_token()` crash dengan error `byte indices must be integers or slices, not str`.

**Solusi** — gunakan JWKS endpoint langsung via httpx + python-jose (sudah diterapkan di `backend/app/dependencies.py`):
```python
async def get_jwks() -> dict:
    jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10)
        return response.json()

token_data = jwt.decode(token, jwks, algorithms=["RS256"], options={"verify_aud": False})
```

---

### ❌ Vite dev server memblokir hostname

**Masalah:** Vite memblokir request dari hostname selain `localhost`.

**Solusi** — di `frontend/vite.config.js`:
```js
server: {
  allowedHosts: ['dashboard.ckd-otto.com', 'localhost'],
}
```

---

### ❌ `docker compose restart` tidak re-read `.env`

**Masalah:** Setelah mengubah `.env`, `docker compose restart` tidak menerapkan perubahan environment variable.

**Solusi:** Gunakan `up -d` bukan `restart`:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend celery
```

---

### ❌ Oracle Instant Client tidak ada di server

**Masalah:** File `.so` tidak bisa di-push ke GitHub karena terlalu besar.

**Solusi:** Upload manual via `scp` setiap kali setup server baru (lihat bagian 10).

---

## Checklist Deploy Production

Copy-paste dan centang satu per satu:

```
PRE-DEPLOY
[ ] DNS dashboard.ckd-otto.com sudah diarahkan ke IP server production
[ ] Port 80 dan 443 terbuka dari internet
[ ] Docker dan Git terinstall di server
[ ] SSH key server sudah ditambahkan ke GitHub

SETUP
[ ] git clone berhasil
[ ] .env dibuat dari .env.example dengan semua nilai terisi
[ ] Password database tidak mengandung karakter spesial (@, #, $)
[ ] KEYCLOAK_URL = URL publik + /auth (bukan http://keycloak:8080)
[ ] VITE_KEYCLOAK_URL = URL publik + /auth
[ ] Oracle Instant Client di-upload via scp
[ ] docker-compose.prod.yml dibuat
[ ] nginx/nginx.prod.conf dibuat

SSL
[ ] certbot terinstall
[ ] Certificate berhasil di-request
[ ] nginx config menggunakan path certificate yang benar

JALANKAN
[ ] docker compose up -d --build berhasil
[ ] Semua 7 container STATUS: Up / healthy
[ ] curl health checks semua return 200/302

KEYCLOAK
[ ] Login admin console berhasil
[ ] Client redirect URIs diupdate ke URL production
[ ] Google Identity Provider dikonfigurasi
[ ] Test login dengan akun @ckd-otto.com berhasil
[ ] Role di-assign ke user yang perlu akses

EMAIL
[ ] Google App Password dibuat
[ ] SMTP dikonfigurasi di Keycloak Realm Settings
[ ] Test connection berhasil

POST-DEPLOY
[ ] Login via Google SSO berhasil
[ ] Dashboard bisa diakses setelah login
[ ] API calls berhasil (tidak ada 401)
```

---

*Dokumen ini dibuat berdasarkan deployment ke dev server pada 2026-04-09.*
*Update setiap ada perubahan konfigurasi atau ditemukan masalah baru.*
